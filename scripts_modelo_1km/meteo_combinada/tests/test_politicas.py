"""Pruebas de politicas.py (§2.1-§2.5).

Las que llevan «sNN» son la prueba NN de §9 del texto. Dueño: I6 (ola 2). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos, en carpetas temporales: ninguna prueba abre DMC, la meteorología SINCA real, NASADEM real ni
GHS-POP real. Leen, sin escribir, el código fijado (descargador, adaptador y ``dmc_features``), la clausura del reloj
(``validar_regla_reloj_dmc`` por ``fijados.cargar_validador_reloj``) y los textos anclados de APH (umbrales y el
ejemplo de §2.5); si falta un archivo o cambió de huella, la prueba se omite con el motivo y no se da por aprobada.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import copy  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import fijados, numerico, politicas, tipos, umbrales  # noqa: E402
from meteo_combinada import sintetico as S  # noqa: E402

AP = _RAIZ.parent
APH = AP.parent / "Air-Pollution-Health-Chile"
SHA_CATALOGO = hashlib.sha256(b"catalogo DMC sintetico de las pruebas de politicas").hexdigest()
UTC_MENOS_4 = -240
UTC_MENOS_3 = -180


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Insumos fijados (se omite la prueba si faltan o cambiaron)
# ---------------------------------------------------------------------------
_U: list = []


def _umbrales(prueba) -> umbrales.Umbrales:
    if not _U:
        for rel in (umbrales.TEXTO_M0, umbrales.JSON_M0, umbrales.TEXTO_VIGENTE):
            if not (APH / rel).is_file():
                prueba.skipTest(f"falta {rel} en APH: no se da por aprobada")
        try:
            _U.append(umbrales.cargar_m0(APH))
        except umbrales.ErrorUmbrales as e:
            prueba.skipTest(f"los umbrales anclados no cargan ({e}); no se da por aprobada")
    return _U[0]


def _codigo_fijado(prueba):
    """Descargador, adaptador y dmc_features con sus huellas de §9.3."""
    for ruta, sha in ((AP / fijados.RUTA_DESCARGADOR, fijados.SHA_DESCARGADOR),
                      (AP / fijados.RUTA_ADAPTADOR, fijados.SHA_ADAPTADOR),
                      (AP / fijados.RUTA_DMC_FEATURES, fijados.SHA_DMC_FEATURES)):
        if not ruta.is_file() or _sha(ruta) != sha:
            prueba.skipTest(f"{ruta.name} falta o cambió de huella; no se da por aprobada")
    return fijados.cargar_descargador(AP), fijados.cargar_adaptador(AP), fijados.cargar_dmc_features(AP)


def _validador(prueba):
    """``validar_regla_reloj_dmc`` con la huella de la clausura del reloj (MC-17, FIJ-1)."""
    esperadas = dict(fijados.HUELLAS_RELOJ)
    try:
        actuales = fijados.huellas_reloj(AP)
    except (OSError, ValueError) as e:
        prueba.skipTest(f"no se puede leer la clausura del reloj ({e}); no se da por aprobada")
    if actuales != esperadas:
        prueba.skipTest("la clausura del reloj cambió respecto de la fijada (FIJ-1, AP 1da0236); no se da por aprobada")
    return fijados.cargar_validador_reloj(AP, esperadas, permitir_cargados=True)


# ---------------------------------------------------------------------------
# Fabricación sintética
# ---------------------------------------------------------------------------
def _info(codigo: str, *, lat=-33.45, lon=-70.66, z=520.0, k3=True, fuente="catalogo") -> tipos.InfoEstacion:
    """Una InfoEstacion de M2a hecha a mano (lo que llenará estaticas_nasadem; A8)."""
    nan = math.nan
    return tipos.InfoEstacion(
        codigo=codigo, nombre=f"Estación sintética {codigo}", conjunto="N", macrozona="centro",
        grupo=tipos.id_grupo([codigo]), omm=None, tipo=None, propietario=None, lat_txt=str(lat), lon_txt=str(lon),
        alt_txt=None if fuente != "catalogo" else str(z), lat=lat, lon=lon,
        z_cat=z if fuente == "catalogo" else nan, rho_km=0.1, k3_pasa=k3, z_s=z, z_s_fuente=fuente, celda=None,
        utm_e=nan, utm_n=nan, bloque="", pix0=-1, pix1=-1, pix2=-1, pix3=-1, w0=nan, w1=nan, w2=nan, w3=nan,
        respaldo_16km=False, sin_fondo=True, excluida=not k3, motivo=None if k3 else "k3")


def _horas(*tramos) -> list:
    """Etiquetas ingenuas: la unión de (desde, n horas)."""
    salida = []
    for desde, n in tramos:
        salida += list(pd.date_range(desde, periods=n, freq="h"))
    return salida


def _estacion(codigo: str, L, *, qfe=955.0, qff=1015.0, lat=-33.45, lon=-70.66, z=520.0) -> S.EstacionSintetica:
    n = len(L)
    return S.estacion_sintetica(codigo, lat, lon, z, L, Ts=np.full(n, 15.0), Td=np.full(n, 5.0),
                                relative_humidity=np.full(n, 50.0), wind_direction_instant=np.full(n, 270.0),
                                wind_speed_instant=np.full(n, 10.0), QFE=np.broadcast_to(qfe, n),
                                QFF=np.broadcast_to(qff, n), RR06=["s/p"] * n)


def _tramo(tramo: str, desde: str, hasta: str, minutos: int = UTC_MENOS_4, veredicto: str | None = "F(-4)") -> dict:
    return {"tramo": tramo, "valid_from": desde, "valid_to": hasta, "minutos": minutos, "veredicto": veredicto}


class Mundo:
    """Una descarga sintética por ``run_download`` y la publicación de RELOJ con su registro de C5, en ``raiz``."""

    def __init__(self, prueba, raiz: Path, estaciones, reglas, *, desde, hasta, evaluados=None, **kw):
        self.descargador, self.adaptador, self.dmc_features = _codigo_fijado(prueba)
        self.dmc = S.fabricar_descarga(estaciones, raiz / "descarga", self.descargador, desde, hasta)
        self.manifiestos = S.manifiestos_de(self.dmc)
        shas = S.artefactos_de_descarga(self.dmc)
        self.ruta_politica = S.politica_reloj_sintetica(raiz / "publicacion", shas if evaluados is None else evaluados,
                                                        reglas, **kw)
        self.rutas = S.rutas_politica_sintetica(raiz / "publicacion")
        self.ap = raiz / "publicacion" / "AP"

    def leer(self):
        registro = politicas.leer_registro_c5(self.rutas["registro"], ap=self.ap)
        pol, artefactos = politicas.leer_politica_reloj(registro, ap=self.ap)
        return registro, pol, artefactos

    def meses(self, codigo: str) -> set:
        return {tuple(int(x) for x in r.name[:7].split("-")) for r in self.manifiestos.get(codigo, [])}

    def cargar(self, manifiesto: Path, pols, codigo: str, validar=None):
        """El paso 1 de §2.1, como lo hará qc_dmc_meteo: las políticas que cruzan el mes, el validador de RELOJ y
        ``cargar_dmc``. Devuelve (tabla larga, ids de RELOJ rechazados)."""
        anio, mes = (int(x) for x in manifiesto.name[:7].split("-"))
        _, meta = self.adaptador.leer_artefacto(manifiesto)
        cruzan = politicas.politicas_que_cruzan(pols, codigo, anio, mes)
        rechazadas: tuple = ()
        if validar is not None:
            cruzan, rechazadas = politicas.validar_reglas(
                cruzan, meta["content_sha256"], lambda r, s: validar(r, s, politica_ruta=self.ruta_politica))
        larga, _ = self.dmc_features.cargar_dmc([manifiesto], cruzan, adapter_sha256=fijados.SHA_ADAPTADOR)
        return larga, rechazadas


def _lectura(pol, info, U, meses, *, k2=frozenset()):
    tramos = politicas.tramos_de_lectura(pol, info.codigo, meses, politicas.marcas_g(pol, info.codigo), info=info,
                                         k2=k2)
    return tramos, politicas.politicas_de_lectura(pol, info, tramos, U, sha_protocolo=U.sha256_texto_vigente,
                                                  sha_catalogo=SHA_CATALOGO)


def _politica_reloj(tmp: Path, reglas, **kw) -> dict:
    """La política de RELOJ sintética, leída como dict (para las pruebas puras)."""
    ruta = S.politica_reloj_sintetica(tmp, {c: [hashlib.sha256(c.encode()).hexdigest()] for c in reglas}, reglas, **kw)
    return json.loads(ruta.read_text(encoding="utf-8"))


def _tipos(x):
    """La estructura de tipos exactos de un JSON en memoria."""
    if type(x) is dict:
        return {k: _tipos(v) for k, v in x.items()}
    if type(x) is list:
        return [_tipos(v) for v in x]
    return type(x).__name__


def _mes2000(ts) -> np.ndarray:
    u = pd.DatetimeIndex(pd.to_datetime(ts, utc=True)).tz_convert("UTC").tz_localize(None)
    return np.asarray(u.year - 2000) * 12 + np.asarray(u.month) - 1


def _reescribir(rutas, *, politica=None, informe=None) -> None:
    """Reescribe el informe o la política sintéticos con sus huellas al día (política → informe; registro → política),
    para las pruebas que necesitan una publicación distinta de la que fabrica ``sintetico``."""
    pol = json.loads(rutas["politica"].read_text(encoding="utf-8")) if politica is None else politica
    if informe is not None:
        datos = json.dumps(informe, ensure_ascii=False, sort_keys=True).encode("utf-8")
        rutas["informe"].write_bytes(datos)
        pol["informe"]["sha256"] = hashlib.sha256(datos).hexdigest()
    datos = json.dumps(pol, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    rutas["politica"].write_bytes(datos)
    registro = json.loads(rutas["registro"].read_text(encoding="utf-8"))
    registro["sha256_politica"] = hashlib.sha256(datos).hexdigest()
    rutas["registro"].write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _por(larga, variable):
    return larga[larga.variable == variable]


K_FEBRERO_2019 = (2019 - 2000) * 12 + 1             # mes2000 de febrero de 2019: u_k = 2019-02-01T00:00 UTC


def _k4(codigo: str, traslado: int, barometro: int | None = None) -> tipos.ResultadoK4:
    """Un ResultadoK4 hecho a mano (acuerdo A4): un traslado y, si se pide, un quiebre de barómetro (meses2000)."""
    quiebres = [tipos.Quiebre(tipos.Estadistico.T2B.value, traslado, 0.0, tipos.ClaseQuiebre.TRASLADO)]
    if barometro is not None:
        quiebres.append(tipos.Quiebre(tipos.Estadistico.T2B.value, barometro, 0.0, tipos.ClaseQuiebre.BAROMETRO))
    return tipos.ResultadoK4(codigo=codigo, quiebres=tuple(quiebres), ultimo_traslado=traslado,
                             ultimo_barometro=barometro, sin_prueba=False)


def _piezas(politicas_) -> list:
    return [(p["valid_from"], p["valid_to"], p["coordinates"]["verified"]) for p in politicas_]


# ---------------------------------------------------------------------------
# S2 (la parte de las políticas)
# ---------------------------------------------------------------------------
class PruebasS2(unittest.TestCase):
    def test_s02_reglas_escritas_y_releidas_del_json_pasan_cargar_dmc(self):
        """Las reglas de §2.2 y §2.3, escritas y releídas del JSON (números de Python), pasan cargar_dmc con artefactos de run_download (cliente y guarda falsos)."""
        U = _umbrales(self)
        validar = _validador(self)
        L = _horas(("2019-09-01", 72))
        n = len(L)
        malas = np.zeros(n, dtype=bool)
        malas[10:14] = True                 # QFE sobre p_std(z_s) + 50 y QFF de 40 hPa (dentro del rango de FF)
        qfe = np.where(malas, 1010.0, 955.0)
        qff = np.where(malas, 40.0, 1015.0)
        estaciones = [_estacion("900101", L, qfe=qfe, qff=qff), _estacion("900102", L)]
        reglas = {c: [_tramo("1.1", "2019-09-01T00:00:00", "2019-09-03T23:00:00")] for c in ("900101", "900102")}
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), estaciones, reglas, desde="2019-09-01", hasta="2019-09-30")
            registro, pol, artefactos = m.leer()
            self.assertEqual(politicas.comprobar_c5(registro, pol), [])
            self.assertEqual(sorted(set(artefactos.values())), ["900101", "900102"])
            k2 = politicas.coordenadas_inconsistentes(registro, ap=m.ap)
            self.assertEqual(k2, frozenset())
            infos = {"900101": _info("900101"), "900102": _info("900102", fuente="nasadem")}
            for codigo, info in infos.items():
                tramos, pols = _lectura(pol, info, U, m.meses(codigo), k2=k2)
                self.assertEqual([t.id for t in tramos], ["1.1/1"])
                # Escritas y releídas del disco (§2.1: «S2 lo prueba con el JSON releído del disco»).
                ruta_json = Path(tmp) / f"politicas_{codigo}.json"
                ruta_json.write_bytes(politicas.a_json(pols))
                releidas = politicas.de_json(ruta_json.read_bytes())
                self.assertEqual(releidas, pols)
                self.assertEqual(_tipos(releidas), _tipos(pols))
                (manifiesto,) = m.manifiestos[codigo]
                larga, rechazadas = m.cargar(manifiesto, releidas, codigo, validar)
                self.assertEqual(rechazadas, ())
                self.assertTrue(larga.clock_verified.all() and larga.coordinates_verified.all())
                utc = np.asarray(pd.DatetimeIndex(larga.timestamp_utc).tz_convert(None))
                local = np.asarray(pd.to_datetime(larga.timestamp_source) + pd.Timedelta(hours=4))
                self.assertTrue((utc == local).all())
                for v in ("Ts", "Td", "relative_humidity", "wind_speed_instant", "wind_direction_instant", "wind_u",
                          "wind_v"):
                    with self.subTest(codigo=codigo, variable=v):
                        self.assertTrue(_por(larga, v).usable.all())
                self.assertFalse(_por(larga, "RR06").usable.any())          # sum 360: nunca model_ready
                self.assertFalse(_por(larga, "QNH").usable.any())           # sin regla
                ts = _por(larga, "Ts")
                self.assertTrue((ts.quality_reason == "documented_numeric_checks_unknown_source_qc").all())
            # 900101: QFE con p_std(z_s) − 80/+50 y QFF con 920-1.065 (QQFF_*), no con el rango de la rapidez.
            (manifiesto,) = m.manifiestos["900101"]
            _, pols = _lectura(pol, infos["900101"], U, m.meses("900101"))
            larga, _ = m.cargar(manifiesto, pols, "900101", validar)
            esperadas = np.where(malas, "documented_numeric_range_rejected",
                                 "documented_numeric_checks_unknown_source_qc")
            for v in ("QFE", "QFF"):
                with self.subTest(variable=v):
                    g = _por(larga, v).sort_values("timestamp_source")
                    self.assertEqual(list(g.quality_reason), list(esperadas))
                    self.assertEqual(list(g.usable), list(~malas))
            # 900102: z_s de NASADEM (sin z_cat legible) → QFE sin regla (§2.5, MC-11); QFF sigue con la suya.
            (manifiesto,) = m.manifiestos["900102"]
            _, pols = _lectura(pol, infos["900102"], U, m.meses("900102"))
            self.assertNotIn("QFE", pols[0]["quality"])
            larga, _ = m.cargar(manifiesto, pols, "900102", validar)
            self.assertTrue((_por(larga, "QFE").quality_reason == "quality_policy_unverified").all())
            self.assertFalse(_por(larga, "QFE").usable.any())
            self.assertTrue(_por(larga, "QFF").usable.all())

    def test_s02_fuera_de_los_tramos_de_reloj_nada_es_usable(self):
        """Fuera de los tramos de reloj nada queda usable."""
        U = _umbrales(self)
        validar = _validador(self)
        L = _horas(("2019-09-01", 72), ("2019-10-01", 48))
        reglas = {"900201": [_tramo("1.1", "2019-09-02T00:00:00", "2019-09-03T23:00:00")]}
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion("900201", L)], reglas, desde="2019-09-01", hasta="2019-10-31")
            _, pol, _ = m.leer()
            self.assertEqual(m.meses("900201"), {(2019, 9), (2019, 10)})
            _, pols = _lectura(pol, _info("900201"), U, m.meses("900201"))
            self.assertEqual([(p["valid_from"], p["valid_to"]) for p in pols],
                             [("2019-09-02T00:00:00", "2019-09-03T23:00:00")])
            septiembre, octubre = sorted(m.manifiestos["900201"])
            larga, _ = m.cargar(septiembre, pols, "900201", validar)
            dentro = pd.to_datetime(larga.timestamp_source) >= pd.Timestamp("2019-09-02T00:00")
            self.assertTrue(dentro.any() and (~dentro).any())
            self.assertFalse(larga[~dentro].usable.any())
            self.assertFalse(larga[~dentro].clock_verified.any())
            self.assertTrue(larga[~dentro].timestamp_utc.isna().all())       # sin regla no se inventa UTC
            self.assertTrue(_por(larga[dentro], "Ts").usable.all())
            # Octubre: ningún tramo de RELOJ lo cruza → ninguna política → nada usable.
            self.assertEqual(politicas.politicas_que_cruzan(pols, "900201", 2019, 10), [])
            larga, rechazadas = m.cargar(octubre, pols, "900201", validar)
            self.assertEqual(rechazadas, ())
            self.assertFalse(larga.usable.any())
            self.assertFalse(larga.clock_verified.any())

    def test_s02_g_hr_g_viento_y_media_horaria_inhabilitan_lo_suyo(self):
        """G-HR (HR y Td del estación-año), G-viento (DD y FF) y «posible media horaria» (todo el registro)."""
        U = _umbrales(self)
        validar = _validador(self)
        L = _horas(("2019-12-30", 48), ("2020-01-01", 48))
        tramo = [_tramo("1.1", "2019-12-30T00:00:00", "2020-01-02T23:00:00")]
        marcas = {"900301": {"posible_media_horaria": False, "reloj_no_verificado": [
                      {"anio": 2019, "variables": ["wind_speed_instant", "wind_direction_instant"]},
                      {"anio": 2020, "variables": ["Td", "relative_humidity"]}]},
                  "900302": {"posible_media_horaria": True, "reloj_no_verificado": []}}
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion("900301", L), _estacion("900302", L)],
                      {"900301": tramo, "900302": tramo}, desde="2019-12-01", hasta="2020-01-31", marcas=marcas)
            _, pol, _ = m.leer()
            self.assertEqual(politicas.marcas_g(pol, "900301"),
                             {2019: frozenset({"wind_speed_instant", "wind_direction_instant"}),
                              2020: frozenset({"Td", "relative_humidity"})})
            tramos, pols = _lectura(pol, _info("900301"), U, m.meses("900301"))
            self.assertEqual([(t.id, t.valid_from, t.valid_to) for t in tramos],
                             [("1.1/1", "2019-12-30T00:00:00", "2019-12-31T23:00:00"),
                              ("1.1/2", "2020-01-01T00:00:00", "2020-01-02T23:00:00")])
            self.assertIn("motivo=g_viento", pols[0]["measurements"]["wind_speed_instant"]["source"])
            self.assertIn("motivo=g_hr", pols[1]["measurements"]["Td"]["source"])
            diciembre, enero = sorted(m.manifiestos["900301"])
            esperado = {diciembre: {"wind_speed_instant", "wind_direction_instant", "wind_u", "wind_v"},
                        enero: {"Td", "relative_humidity"}}
            for manifiesto, sin_verificar in esperado.items():
                larga, rechazadas = m.cargar(manifiesto, pols, "900301", validar)
                self.assertEqual(rechazadas, ())
                for v in ("Ts", "Td", "relative_humidity", "wind_speed_instant", "wind_direction_instant", "wind_u",
                          "wind_v", "QFE", "QFF"):
                    with self.subTest(mes=manifiesto.name, variable=v):
                        g = _por(larga, v)
                        self.assertEqual(bool(g.measurement_verified.any()), v not in sin_verificar)
                        self.assertEqual(bool(g.usable.all()), v not in sin_verificar)
                        self.assertFalse(v in sin_verificar and g.usable.any())
            # «Posible media horaria»: todas las variables sin verificar en todo su registro, con el motivo en source.
            _, pols = _lectura(pol, _info("900302"), U, m.meses("900302"))
            for p in pols:
                for v, regla in p["measurements"].items():
                    self.assertIs(regla["verified"], False, v)
                    self.assertTrue(regla["source"].endswith(" motivo=posible_media_horaria"), v)
            for manifiesto in m.manifiestos["900302"]:
                larga, _ = m.cargar(manifiesto, pols, "900302", validar)
                self.assertFalse(larga.measurement_verified.any())
                self.assertFalse(larga.usable.any())
                self.assertTrue(larga.clock_verified.all())

    def test_s02_rechazo_de_validar_regla_deja_sin_regla(self):
        """Un rechazo de validar_regla_reloj_dmc (huella del módulo de RELOJ y política sintética en su propia ruta, MC-40) deja sin regla."""
        U = _umbrales(self)
        validar = _validador(self)
        L = _horas(("2019-09-01", 48))
        reglas = {"900401": [_tramo("1.1", "2019-09-01T00:00:00", "2019-09-02T23:00:00")]}
        otro = hashlib.sha256("un artefacto que RELOJ no evaluó".encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            # Caso 1 (su carpeta): el artefacto descargado no está en artefactos_evaluados.
            m = Mundo(self, Path(tmp) / "caso1", [_estacion("900401", L)], reglas, desde="2019-09-01",
                      hasta="2019-09-30", evaluados={"900401": [otro]})
            _, pol, _ = m.leer()
            _, pols = _lectura(pol, _info("900401"), U, {(2019, 9)})
            (manifiesto,) = m.manifiestos["900401"]
            larga, rechazadas = m.cargar(manifiesto, pols, "900401", validar)
            self.assertEqual(rechazadas, ("1.1",))
            self.assertFalse(larga.usable.any())
            self.assertFalse(larga.clock_verified.any())
            # Caso 2 (otra carpeta): el clock de la política no es el publicado (−180 en vez de −240).
            m2 = Mundo(self, Path(tmp) / "caso2", [_estacion("900401", L)], reglas, desde="2019-09-01",
                       hasta="2019-09-30")
            _, pol2, _ = m2.leer()
            _, pols2 = _lectura(pol2, _info("900401"), U, {(2019, 9)})
            (manifiesto2,) = m2.manifiestos["900401"]
            larga, rechazadas = m2.cargar(manifiesto2, pols2, "900401", validar)
            self.assertEqual(rechazadas, ())
            self.assertTrue(_por(larga, "Ts").usable.all())
            alterada = copy.deepcopy(pols2)
            alterada[0]["clock"]["fixed_offset_minutes"] = UTC_MENOS_3
            larga, rechazadas = m2.cargar(manifiesto2, alterada, "900401", validar)
            self.assertEqual(rechazadas, ("1.1",))
            self.assertFalse(larga.usable.any())
            # El regreso: politicas_de_lectura tampoco acepta un tramo con otro clock que el publicado.
            tramos2 = politicas.tramos_de_lectura(pol2, "900401", {(2019, 9)}, {}, info=_info("900401"), k2=())
            malo = [tipos.TramoPolitica(**{**t.__dict__, "clock": {**t.clock, "fixed_offset_minutes": UTC_MENOS_3}})
                    for t in tramos2]
            with self.assertRaises(ValueError):
                politicas.politicas_de_lectura(pol2, _info("900401"), malo, U, sha_protocolo=U.sha256_texto_vigente,
                                               sha_catalogo=SHA_CATALOGO)

    def test_s02_menos240_sin_veredicto_se_rechaza(self):
        """Una plantilla −240 sin veredicto F(−4) se rechaza."""
        U = _umbrales(self)
        validar = _validador(self)
        L = _horas(("2019-09-01", 48))
        with tempfile.TemporaryDirectory() as tmp:
            for caso, veredicto, aceptada in (("sin_veredicto", None, False), ("con_F-4", "F(-4)", True),
                                              ("con_F0", "F(0)", False)):
                with self.subTest(caso=caso):
                    reglas = {"900501": [_tramo("1.1", "2019-09-01T00:00:00", "2019-09-02T23:00:00",
                                                UTC_MENOS_4, veredicto)]}
                    m = Mundo(self, Path(tmp) / caso, [_estacion("900501", L)], reglas, desde="2019-09-01",
                              hasta="2019-09-30")
                    registro, pol, _ = m.leer()
                    fallas_c5 = politicas.comprobar_c5(registro, pol)
                    self.assertEqual(any("sin veredicto" in f for f in fallas_c5), veredicto is None)
                    _, pols = _lectura(pol, _info("900501"), U, {(2019, 9)})
                    (manifiesto,) = m.manifiestos["900501"]
                    larga, rechazadas = m.cargar(manifiesto, pols, "900501", validar)
                    self.assertEqual(rechazadas, () if aceptada else ("1.1",))
                    self.assertEqual(bool(_por(larga, "Ts").usable.all()), aceptada)
                    self.assertEqual(bool(larga.usable.any()), aceptada)


# ---------------------------------------------------------------------------
# Políticas: JSON, tramos, política efectiva, K2, textos source y registro de C5
# ---------------------------------------------------------------------------
class PruebasPoliticas(unittest.TestCase):
    def test_numeros_de_python_ida_y_vuelta(self):
        """a_json: int 0 y 360, interval_minutes entero y límites float."""
        U = _umbrales(self)
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), {"900801": [_tramo("1.1", "2019-01-01T00:00:00",
                                                                "2019-12-31T23:00:00")]})
        _, pols = _lectura(pol, _info("900801"), U, {(2019, m) for m in range(1, 13)})
        (p,) = pols
        self.assertEqual(list(p), ["station_code", "valid_from", "valid_to", "clock", "coordinates", "measurements",
                                   "quality"])
        dd = p["quality"]["wind_direction_instant"]
        self.assertEqual((dd["minimum"], dd["maximum"]), (0, 360))
        self.assertEqual((type(dd["minimum"]), type(dd["maximum"])), (int, int))
        for v, regla in p["quality"].items():
            if v != "wind_direction_instant":
                self.assertEqual((type(regla["minimum"]), type(regla["maximum"])), (float, float), v)
            self.assertEqual(regla["accepted_source_codes"], [])
            self.assertIs(regla["allow_unknown_source_qc"], True)
            self.assertEqual(regla["method"], "documented_numeric_checks")
        for v, regla in p["measurements"].items():
            self.assertIs(type(regla["interval_minutes"]), int, v)
            self.assertEqual((regla["statistic"], regla["interval_minutes"]),
                             ("sum", 360) if v == "RR06" else ("instantaneous", 0), v)
        self.assertNotIn("QNH", p["measurements"])
        self.assertNotIn("QNH", p["quality"])
        self.assertNotIn("RR06", p["quality"])
        self.assertEqual(p["quality"]["Ts"]["minimum"], -39.0)
        self.assertEqual(type(p["coordinates"]["latitude"]), float)
        datos = politicas.a_json(pols)
        self.assertEqual(politicas.de_json(datos), pols)
        self.assertEqual(_tipos(politicas.de_json(datos)), _tipos(pols))
        self.assertEqual(politicas.a_json(politicas.de_json(datos)), datos)
        # Números de numpy (también np.float64, subclase de float), tuplas y no finitos se rechazan.
        for camino, valor, error in ((("quality", "Ts", "minimum"), np.float64(-39.0), TypeError),
                                     (("quality", "Ts", "maximum"), np.float32(50.0), TypeError),
                                     (("measurements", "Ts", "interval_minutes"), np.int64(0), TypeError),
                                     (("quality", "Ts", "maximum"), math.nan, ValueError),
                                     (("quality", "Ts", "accepted_source_codes"), (), TypeError)):
            with self.subTest(camino=camino, valor=repr(valor)):
                malo = copy.deepcopy(pols)
                malo[0][camino[0]][camino[1]][camino[2]] = valor
                with self.assertRaises(error):
                    politicas.a_json(malo)
        with self.assertRaises(TypeError):
            politicas.a_json(tuple(pols))
        with self.assertRaises(ValueError):
            politicas.de_json(b'[{"station_code": "900801", "station_code": "900801"}]')
        with self.assertRaises(ValueError):
            politicas.de_json(b'[{"x": NaN}]')

    def test_qff_usa_qqff_y_no_la_rapidez(self):
        """§2.3 (UMB-11): la regla de QFF va de QQFF_MIN a QQFF_MAX (hPa); QFF_MIN/QFF_MAX son la rapidez (m/s). QFE va
        de p_std(z_s) + QQFE_BAJO a p_std(z_s) + QQFE_ALTO, con z_s del catálogo; con z_s de NASADEM, sin regla."""
        U = _umbrales(self)
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), {"900811": [_tramo("1.1", "2019-01-01T00:00:00",
                                                                "2019-01-31T23:00:00")]})
        _, (p,) = _lectura(pol, _info("900811", z=1234.0), U, {(2019, 1)})
        qff, ff, qfe = p["quality"]["QFF"], p["quality"]["wind_speed_instant"], p["quality"]["QFE"]
        self.assertEqual((qff["unit"], qff["minimum"], qff["maximum"]),
                         ("hPa", float(U.a("QQFF_MIN")), float(U.a("QQFF_MAX"))))
        self.assertNotEqual((qff["minimum"], qff["maximum"]), (float(U.a("QFF_MIN")), float(U.a("QFF_MAX"))))
        self.assertEqual((ff["unit"], ff["minimum"], ff["maximum"]),
                         ("m/s", float(U.a("QFF_MIN")), float(U.a("QFF_MAX"))))
        p0 = float(numerico.p_std(1234.0))
        self.assertEqual((qfe["unit"], qfe["minimum"], qfe["maximum"]),
                         ("hPa", p0 + U.a("QQFE_BAJO"), p0 + U.a("QQFE_ALTO")))
        self.assertLess(qfe["minimum"], p0)
        self.assertGreater(qfe["maximum"], p0)
        for info in (_info("900811", z=1234.0, fuente="nasadem"), _info("900811", z=1234.0, k3=False)):
            _, (p,) = _lectura(pol, info, U, {(2019, 1)})
            self.assertNotIn("QFE", p["quality"])
            self.assertIn("QFF", p["quality"])

    def test_tramos_partidos_por_anios_g_sin_meses_sin_artefacto(self):
        """Tramos de RELOJ partidos por los años G (D25: el 1 de enero de cada año marcado y del siguiente, también entre
        2019 y 2020 con las mismas marcas); ninguno cubre un mes sin artefacto evaluado (§2.5)."""
        U = _umbrales(self)
        reglas = {"900901": [_tramo("1.1", "2018-11-15T05:00:00", "2021-02-10T20:00:00"),
                             _tramo("2.1", "2021-03-01T00:00:00", "2021-03-31T23:00:00")]}
        marcas = {"900901": {"posible_media_horaria": False, "reloj_no_verificado": [
            {"anio": 2019, "variables": ["Td", "relative_humidity"]},
            {"anio": 2020, "variables": ["Td", "relative_humidity"]},
            {"anio": 2021, "variables": ["wind_speed_instant", "wind_direction_instant"]}]}}
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), reglas, marcas=marcas)
        meses = {(a, m) for a in range(2018, 2022) for m in range(1, 13)} - {(2019, 6)}
        info = _info("900901")
        tramos, pols = _lectura(pol, info, U, meses)
        self.assertEqual([(t.id, t.valid_from, t.valid_to) for t in tramos], [
            ("1.1/1", "2018-11-15T05:00:00", "2018-12-31T23:00:00"),
            ("1.1/2", "2019-01-01T00:00:00", "2019-05-31T23:00:00"),
            ("1.1/3", "2019-07-01T00:00:00", "2019-12-31T23:00:00"),
            ("1.1/4", "2020-01-01T00:00:00", "2020-12-31T23:00:00"),        # D25: aunque 2019 y 2020 coincidan
            ("1.1/5", "2021-01-01T00:00:00", "2021-02-10T20:00:00"),
            ("2.1/1", "2021-03-01T00:00:00", "2021-03-31T23:00:00")])
        for t in tramos:
            desde, hasta = pd.Timestamp(t.valid_from), pd.Timestamp(t.valid_to)
            cubiertos = {(d.year, d.month) for d in pd.date_range(desde, hasta, freq="h")}
            self.assertLessEqual(cubiertos, meses, t.id)
            self.assertTrue(t.coordenadas_confirmadas)
            self.assertIsNone(t.motivo)
        self.assertEqual([t.id for t in politicas.tramos_de_politicas(pols)], [t.id for t in tramos])
        sin_verificar = [sorted(v for v, r in p["measurements"].items() if not r["verified"]) for p in pols]
        self.assertEqual(sin_verificar, [[], ["Td", "relative_humidity"], ["Td", "relative_humidity"],
                                         ["Td", "relative_humidity"], ["wind_direction_instant", "wind_speed_instant"],
                                         ["wind_direction_instant", "wind_speed_instant"]])
        # Sin artefacto evaluado en ningún mes, no hay tramo; sin partir por los años G, la política no se arma.
        self.assertEqual(politicas.tramos_de_lectura(pol, "900901", set(), {}, info=info, k2=()), [])
        enteros = politicas.tramos_de_lectura(pol, "900901", meses | {(2019, 6)}, {}, info=info, k2=())
        self.assertEqual([t.id for t in enteros], ["1.1/1", "2.1/1"])
        with self.assertRaises(ValueError):
            politicas.politicas_de_lectura(pol, info, enteros, U, sha_protocolo=U.sha256_texto_vigente,
                                           sha_catalogo=SHA_CATALOGO)
        # Coordenadas de lectura (POL-5): K2, K3 y sin coordenadas legibles, en todo el registro.
        for info_caso, k2, motivo in ((info, {"900901"}, "k2"), (_info("900901", k3=False), (), "k3"),
                                      (_info("900901", lat=math.nan), (), "sin_coordenadas")):
            with self.subTest(motivo=motivo):
                tramos, pols = _lectura(pol, info_caso, U, meses, k2=frozenset(k2))
                self.assertTrue(all(t.coordenadas_confirmadas is False and t.motivo == motivo for t in tramos))
                for p in pols:
                    self.assertIs(p["coordinates"]["verified"], False)
                    self.assertTrue(p["coordinates"]["source"].endswith(f" motivo={motivo}"))
                    self.assertEqual("latitude" in p["coordinates"], motivo != "sin_coordenadas")
                self.assertEqual({t.motivo for t in politicas.tramos_de_politicas(pols)}, {motivo})

    def test_politica_efectiva_coincide_con_marca_1(self):
        """MC-53: releer con la política efectiva da el mismo conjunto de filas usables de coordenadas que la marca 1."""
        U = _umbrales(self)
        L = _horas(("2019-01-30", 48), ("2019-02-01", 48), ("2019-03-01", 24))
        k_traslado = (2019 - 2000) * 12 + 1             # febrero de 2019 (mes2000)
        k_barometro = k_traslado + 1                    # marzo de 2019
        k4 = {c: tipos.ResultadoK4(codigo=c, quiebres=(
                  tipos.Quiebre(tipos.Estadistico.T2B.value, k_traslado, 0.0, tipos.ClaseQuiebre.TRASLADO),
                  tipos.Quiebre(tipos.Estadistico.T2B.value, k_barometro, 0.0, tipos.ClaseQuiebre.BAROMETRO)),
                  ultimo_traslado=k_traslado, ultimo_barometro=k_barometro, sin_prueba=False)
              for c in ("900611", "900612")}
        reglas = {"900611": [_tramo("1.1", "2019-01-30T00:00:00", "2019-03-01T23:00:00", UTC_MENOS_4, "F(-4)")],
                  "900612": [_tramo("1.1", "2019-01-30T00:00:00", "2019-03-01T23:00:00", UTC_MENOS_3, "F(-3)")]}
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion("900611", L), _estacion("900612", L)], reglas, desde="2019-01-01",
                      hasta="2019-03-31")
            _, pol, _ = m.leer()
            for codigo, minutos in (("900611", UTC_MENOS_4), ("900612", UTC_MENOS_3)):
                with self.subTest(codigo=codigo):
                    _, lectura = _lectura(pol, _info(codigo), U, m.meses(codigo))
                    self.assertEqual(len(lectura), 1)
                    efectivas = politicas.politicas_efectivas(lectura, {codigo: k4[codigo]})
                    corte = pd.Timestamp("2019-02-01T00:00") + pd.Timedelta(minutes=minutos)
                    corte_b = pd.Timestamp("2019-03-01T00:00") + pd.Timedelta(minutes=minutos)
                    self.assertEqual([(p["valid_from"], p["valid_to"], p["coordinates"]["verified"]) for p in efectivas],
                                     [("2019-01-30T00:00:00", (corte - pd.Timedelta(hours=1)).isoformat(), False),
                                      (corte.isoformat(), (corte_b - pd.Timedelta(hours=1)).isoformat(), True),
                                      (corte_b.isoformat(), "2019-03-01T23:00:00", True)])
                    tramos = politicas.tramos_de_politicas(efectivas)
                    self.assertEqual([(t.id, t.motivo) for t in tramos],
                                     [("1.1/1", "traslado"), ("1.1/2", None), ("1.1/3", None)])
                    for p in efectivas:
                        self.assertEqual(p["clock"], lectura[0]["clock"])          # el clock no cambia
                        for regla in (p["coordinates"], *p["measurements"].values(), *p["quality"].values()):
                            self.assertEqual((regla["valid_from"], regla["valid_to"]), (p["valid_from"], p["valid_to"]))
                    releidas = politicas.de_json(politicas.a_json(efectivas))
                    for manifiesto in m.manifiestos[codigo]:
                        larga, _ = m.cargar(manifiesto, releidas, codigo)
                        self.assertTrue(larga.clock_verified.all())
                        esperado = _mes2000(larga.timestamp_utc) >= k_traslado
                        self.assertEqual(list(larga.coordinates_verified), list(esperado), manifiesto.name)
                        larga_l, _ = m.cargar(manifiesto, lectura, codigo)
                        self.assertTrue(larga_l.coordinates_verified.all())
                    vecino = (corte - pd.Timedelta(hours=1)).isoformat()
                    self.assertTrue(any(x.isoformat() == vecino for x in pd.to_datetime(L)))    # el borde tiene datos
            # Sin K4 de la estación, la efectiva es la de lectura.
            _, lectura = _lectura(pol, _info("900611"), U, m.meses("900611"))
            self.assertEqual(politicas.politicas_efectivas(lectura, {}), lectura)
            with self.assertRaises(ValueError):
                politicas.politicas_efectivas(lectura, {"900611": k4["900612"]})

    def test_politica_efectiva_bordes_del_corte_con_cargar_dmc(self):
        """MC-53 en los bordes del corte, con cargar_dmc: con −240 y −180, un tramo de RELOJ que termina justo en L_k y
        otro que termina entre L_k y u_k (horas de etiqueta de enero que en UTC ya son de febrero), con datos en esas
        horas. Fila por fila, coordinates_verified == (mes2000(h) ≥ k) dentro de la política, y falso fuera de ella."""
        U = _umbrales(self)
        L = _horas(("2019-01-30", 48))
        k = K_FEBRERO_2019
        casos = {"900621": (UTC_MENOS_4, "F(-4)", "2019-01-31T20:00:00"),      # termina en L_k
                 "900622": (UTC_MENOS_4, "F(-4)", "2019-01-31T22:00:00"),      # termina entre L_k y u_k
                 "900623": (UTC_MENOS_3, "F(-3)", "2019-01-31T21:00:00"),      # termina en L_k
                 "900624": (UTC_MENOS_3, "F(-3)", "2019-01-31T22:00:00")}      # termina entre L_k y u_k
        reglas = {c: [_tramo("1.1", "2019-01-30T00:00:00", fin, minutos, veredicto)]
                  for c, (minutos, veredicto, fin) in casos.items()}
        with tempfile.TemporaryDirectory() as tmp:
            m = Mundo(self, Path(tmp), [_estacion(c, L) for c in casos], reglas, desde="2019-01-01",
                      hasta="2019-01-31")
            _, pol, _ = m.leer()
            for codigo, (minutos, _, fin) in casos.items():
                with self.subTest(codigo=codigo, minutos=minutos, fin=fin):
                    corte = pd.Timestamp("2019-02-01T00:00") + pd.Timedelta(minutes=minutos)       # L_k
                    _, lectura = _lectura(pol, _info(codigo), U, m.meses(codigo))
                    efectivas = politicas.politicas_efectivas(lectura, {codigo: _k4(codigo, k)})
                    self.assertEqual(_piezas(efectivas),
                                     [("2019-01-30T00:00:00", (corte - pd.Timedelta(hours=1)).isoformat(), False),
                                      (corte.isoformat(), fin, True)])
                    (manifiesto,) = m.manifiestos[codigo]
                    larga, _ = m.cargar(manifiesto, politicas.de_json(politicas.a_json(efectivas)), codigo)
                    etiquetas = pd.to_datetime(larga.timestamp_source)
                    for hora in (corte - pd.Timedelta(hours=1), corte, pd.Timestamp(fin)):    # los bordes tienen datos
                        self.assertTrue((etiquetas == hora).any(), hora)
                    dentro = np.asarray(etiquetas <= pd.Timestamp(fin))
                    self.assertTrue(dentro.any() and (~dentro).any())
                    self.assertEqual(list(larga.clock_verified), list(dentro))
                    esperado = _mes2000(larga.timestamp_utc[dentro]) >= k
                    self.assertEqual(list(larga.coordinates_verified[dentro]), list(esperado))
                    self.assertFalse(larga.coordinates_verified[~dentro].any())
                    # Lo que el corte confirma son horas de etiqueta de enero que en UTC son de febrero.
                    tras = dentro & np.asarray(etiquetas >= corte)
                    self.assertTrue(tras.any() and larga.coordinates_verified[tras].all())
                    self.assertTrue((etiquetas[tras].dt.month == 1).all())

    def test_politica_efectiva_piezas_en_los_bordes(self):
        """MC-53, caso puro: intervalos y ``coordinates.verified`` de cada pieza, con el traslado en febrero de 2019
        (u_k = 02-01T00:00 UTC) y −240 (L_k = 01-31T20:00) o −180 (L_k = 01-31T21:00). El tramo termina una hora antes de
        L_k, en L_k o entre L_k y u_k; empieza en L_k; o sigue hasta 02-01T02:00 (enero y febrero con artefacto quedan en
        una pieza de lectura, POL-4, y la pieza posterior al corte cruza u_k)."""
        U = _umbrales(self)

        def h(x):
            return f"2019-{x}:00:00"
        casos = {   # código: (minutos, desde, hasta, piezas esperadas (desde, hasta, coordenadas confirmadas))
            "900631": (UTC_MENOS_4, "01-15T00", "01-31T19", [("01-15T00", "01-31T19", False)]),
            "900632": (UTC_MENOS_4, "01-15T00", "01-31T20", [("01-15T00", "01-31T19", False),
                                                            ("01-31T20", "01-31T20", True)]),
            "900633": (UTC_MENOS_4, "01-15T00", "01-31T23", [("01-15T00", "01-31T19", False),
                                                            ("01-31T20", "01-31T23", True)]),
            "900634": (UTC_MENOS_4, "01-31T20", "01-31T23", [("01-31T20", "01-31T23", True)]),
            "900635": (UTC_MENOS_4, "01-15T00", "02-01T02", [("01-15T00", "01-31T19", False),
                                                            ("01-31T20", "02-01T02", True)]),
            "900641": (UTC_MENOS_3, "01-15T00", "01-31T20", [("01-15T00", "01-31T20", False)]),
            "900642": (UTC_MENOS_3, "01-15T00", "01-31T21", [("01-15T00", "01-31T20", False),
                                                            ("01-31T21", "01-31T21", True)]),
            "900643": (UTC_MENOS_3, "01-15T00", "01-31T23", [("01-15T00", "01-31T20", False),
                                                            ("01-31T21", "01-31T23", True)]),
            "900644": (UTC_MENOS_3, "01-31T21", "01-31T23", [("01-31T21", "01-31T23", True)]),
            "900645": (UTC_MENOS_3, "01-15T00", "02-01T02", [("01-15T00", "01-31T20", False),
                                                            ("01-31T21", "02-01T02", True)]),
        }
        reglas = {c: [_tramo("1.1", h(a), h(b), minutos, "F(-4)" if minutos == UTC_MENOS_4 else "F(-3)")]
                  for c, (minutos, a, b, _) in casos.items()}
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), reglas)
        for codigo, (minutos, _, _, esperadas) in casos.items():
            with self.subTest(codigo=codigo, minutos=minutos):
                _, lectura = _lectura(pol, _info(codigo), U, {(2019, 1), (2019, 2)})
                efectivas = politicas.politicas_efectivas(lectura, {codigo: _k4(codigo, K_FEBRERO_2019)})
                self.assertEqual(_piezas(efectivas), [(h(a), h(b), v) for a, b, v in esperadas])
                self.assertEqual([t.motivo for t in politicas.tramos_de_politicas(efectivas)],
                                 [None if v else "traslado" for _, _, v in esperadas])

    def test_precedencia_de_motivos(self):
        """POL-5: sin coordenadas legibles, K3 y K2, en ese orden; POL-9: el traslado no pisa el motivo de unas
        coordenadas ya sin confirmar (tampoco antes del traslado); POL-6 y §2.2: «posible media horaria» prevalece sobre
        G-HR y G-viento («con el motivo en `source`»)."""
        U = _umbrales(self)
        tramo = [_tramo("1.1", "2019-01-01T00:00:00", "2019-03-31T23:00:00")]
        g = ["Td", "relative_humidity", "wind_speed_instant", "wind_direction_instant"]
        marcas = {"900652": {"posible_media_horaria": True, "reloj_no_verificado": [{"anio": 2019, "variables": g}]}}
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), {"900651": tramo, "900652": tramo}, marcas=marcas)
        meses = {(2019, 1), (2019, 2), (2019, 3)}
        k4 = {"900651": _k4("900651", K_FEBRERO_2019, K_FEBRERO_2019 + 1)}
        casos = (("k3_y_k2", _info("900651", k3=False), {"900651"}, "k3"),
                 ("sin_coordenadas_k3_y_k2", _info("900651", lat=math.nan, k3=False), {"900651"}, "sin_coordenadas"),
                 ("k2", _info("900651"), {"900651"}, "k2"),
                 ("k3", _info("900651", k3=False), set(), "k3"))
        for nombre, info, k2, motivo in casos:
            with self.subTest(caso=nombre):
                tramos, lectura = _lectura(pol, info, U, meses, k2=frozenset(k2))
                self.assertEqual([(t.coordenadas_confirmadas, t.motivo) for t in tramos], [(False, motivo)])
                efectivas = politicas.politicas_efectivas(lectura, k4)
                self.assertEqual(len(efectivas), 3)                 # antes del traslado, entre traslado y barómetro, y después
                for p in efectivas:
                    self.assertIs(p["coordinates"]["verified"], False)
                    self.assertTrue(p["coordinates"]["source"].endswith(f" motivo={motivo}"),
                                    p["coordinates"]["source"])
                self.assertEqual([t.motivo for t in politicas.tramos_de_politicas(efectivas)], [motivo] * 3)
        self.assertEqual(politicas.marcas_g(pol, "900652"), {2019: frozenset(g)})
        self.assertIs(politicas.media_horaria(pol, "900652"), True)
        _, (p,) = _lectura(pol, _info("900652"), U, meses)
        self.assertEqual(sorted(p["measurements"]), sorted(politicas.MEDICIONES))
        for v, regla in p["measurements"].items():
            with self.subTest(variable=v):
                self.assertIs(regla["verified"], False)
                self.assertTrue(regla["source"].endswith(" motivo=posible_media_horaria"), regla["source"])

    def test_k2_por_codigo_en_tramos_de_lectura(self):
        """POL-5: ``k2`` es un conjunto de códigos de 6 dígitos. Un texto, un objeto o códigos mal formados se rechazan:
        con k2 = "900681" quedaría el conjunto de sus dígitos y la estación saldría confirmada sin aviso."""
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), {"900681": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T23:00:00")]})
        info = _info("900681")

        def tramos(k2):
            return politicas.tramos_de_lectura(pol, "900681", {(2019, 1)}, {}, info=info, k2=k2)
        for k2 in ("900681", b"900681", {"900681": True}, ["90068"], [900681], ["900681", None]):
            with self.subTest(k2=repr(k2)):
                with self.assertRaises(ValueError):
                    tramos(k2)
        for k2 in (frozenset({"900681"}), {"900681"}, ["900681"], ("900682", "900681")):
            with self.subTest(k2=repr(k2)):
                self.assertEqual([(t.coordenadas_confirmadas, t.motivo) for t in tramos(k2)], [(False, "k2")])
        self.assertEqual([(t.coordenadas_confirmadas, t.motivo) for t in tramos(frozenset({"900682"}))], [(True, None)])

    def test_politicas_de_lectura_rechaza_tramos_solapados_o_fuera_de_orden(self):
        """POL-4: politicas_de_lectura rechaza tramos que comparten una hora, se solapan, se repiten o vienen fuera de
        orden (cargar_dmc los rechazaría después con «Políticas históricas solapadas para una observación»)."""
        U = _umbrales(self)
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), {"900691": [_tramo("1.1", "2019-01-01T00:00:00", "2019-03-31T23:00:00")]})
        info = _info("900691")
        t1, t2 = politicas.tramos_de_lectura(pol, "900691", {(2019, 1), (2019, 3)}, {}, info=info, k2=())
        self.assertEqual([(t.id, t.valid_from, t.valid_to) for t in (t1, t2)],
                         [("1.1/1", "2019-01-01T00:00:00", "2019-01-31T23:00:00"),
                          ("1.1/2", "2019-03-01T00:00:00", "2019-03-31T23:00:00")])

        def leer(tramos):
            return politicas.politicas_de_lectura(pol, info, tramos, U, sha_protocolo=U.sha256_texto_vigente,
                                                  sha_catalogo=SHA_CATALOGO)

        def desde(t, valid_from):
            return tipos.TramoPolitica(**{**t.__dict__, "valid_from": valid_from})
        self.assertEqual(len(leer([t1, t2])), 2)
        self.assertEqual(len(leer([t1, desde(t2, "2019-02-01T00:00:00")])), 2)     # contiguos: se aceptan
        for nombre, tramos in (("comparten_una_hora", [t1, desde(t2, t1.valid_to)]),
                               ("solapados", [t1, desde(t2, "2019-01-15T00:00:00")]),
                               ("repetidos", [t1, t1]),
                               ("fuera_de_orden", [t2, t1])):
            with self.subTest(caso=nombre):
                with self.assertRaises(ValueError):
                    leer(tramos)

    def test_k2_lee_solo_la_lista_por_codigo(self):
        """MC-19: sólo la clave o las dos columnas de la lista K2."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "caso"
            S.politica_reloj_sintetica(raiz, {"900701": [hashlib.sha256(b"a").hexdigest()]},
                                       {"900701": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T23:00:00")]},
                                       coordenadas_inconsistentes=["900702", "900701"])
            rutas = S.rutas_politica_sintetica(raiz)
            ap = raiz / "AP"
            registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
            k2 = politicas.coordenadas_inconsistentes(registro, ap=ap)
            self.assertEqual(k2, frozenset({"900701", "900702"}))
            self.assertIsInstance(k2, frozenset)
            # Un informe con todo lo demás de RELOJ: sólo se devuelve la lista.
            informe = {"schema": "dmc-reloj-informe/1", "coordenadas_inconsistentes": ["900701"],
                       "estaciones": {"900701": {"r_Ts": [0.1, 0.2]}}, "controles": {"A3": "evidencia"}}
            _reescribir(rutas, informe=informe)
            registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
            self.assertEqual(politicas.coordenadas_inconsistentes(registro, ap=ap), frozenset({"900701"}))
            # Informe cambiado sin la cita de la política al día, sin la clave o con un código malo: ErrorC5.
            rutas["informe"].write_bytes(rutas["informe"].read_bytes() + b" ")
            with self.assertRaises(politicas.ErrorC5):
                politicas.coordenadas_inconsistentes(registro, ap=ap)
            for malo in ({"schema": "x"}, {"coordenadas_inconsistentes": ["90070"]},
                         {"coordenadas_inconsistentes": ["900701", "900701"]}, {"coordenadas_inconsistentes": "900701"}):
                with self.subTest(informe=malo):
                    _reescribir(rutas, informe=malo)
                    registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
                    with self.assertRaises(politicas.ErrorC5):
                        politicas.coordenadas_inconsistentes(registro, ap=ap)

    def test_source_con_huellas(self):
        """Textos source de §2.5 con el sha256 del catálogo y del protocolo vigente (v2.3)."""
        U = _umbrales(self)
        texto = (APH / umbrales.TEXTO_VIGENTE).read_bytes()
        if hashlib.sha256(texto).hexdigest() != umbrales.SHA_TEXTO_VIGENTE:
            self.skipTest("el texto vigente cambió de huella; no se da por aprobada")
        ejemplos = re.findall(r'"source": "(meteo-combinada/v1 [^"]+)"', texto.decode("utf-8"))
        self.assertEqual(len(ejemplos), 3)                  # coordenadas, medicion=Ts y calidad=Ts (§2.5)

        def patron(ejemplo):
            return re.compile(re.escape(ejemplo).replace(re.escape("<64>"), "[0-9a-f]{64}")
                              .replace(re.escape("<código>"), r"\d{6}"))
        pc, pm, pq = (patron(e) for e in ejemplos)
        sha_p = U.sha256_texto_vigente
        self.assertEqual(sha_p, umbrales.SHA_TEXTO_VIGENTE)
        c = politicas.source_coordenadas("330020", SHA_CATALOGO, sha_p)
        self.assertEqual(c, f"meteo-combinada/v1 coordenadas=catalogo sha256={SHA_CATALOGO} continuidad=supuesta "
                            f"estacion=330020 protocolo={sha_p}")
        self.assertIsNotNone(pc.fullmatch(c))
        self.assertEqual(politicas.source_medicion("Ts", sha_p), f"meteo-combinada/v1 medicion=Ts protocolo={sha_p}")
        self.assertIsNotNone(pm.fullmatch(politicas.source_medicion("Ts", sha_p)))
        self.assertEqual(politicas.source_calidad("Ts", sha_p), f"meteo-combinada/v1 calidad=Ts protocolo={sha_p}")
        self.assertIsNotNone(pq.fullmatch(politicas.source_calidad("Ts", sha_p)))
        self.assertEqual(politicas.source_medicion("Td", sha_p, motivo="g_hr"),
                         f"meteo-combinada/v1 medicion=Td protocolo={sha_p} motivo=g_hr")
        self.assertTrue(politicas.source_coordenadas("330020", SHA_CATALOGO, sha_p, motivo="k3").endswith(" motivo=k3"))
        for llamada in (lambda: politicas.source_coordenadas("33002", SHA_CATALOGO, sha_p),
                        lambda: politicas.source_coordenadas("330020", "abc", sha_p),
                        lambda: politicas.source_medicion("QNH", sha_p),
                        lambda: politicas.source_calidad("RR06", sha_p),
                        lambda: politicas.source_medicion("Ts", sha_p.upper()),
                        lambda: politicas.source_medicion("Ts", sha_p, motivo="con espacio")):
            with self.assertRaises(ValueError):
                llamada()
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), {"900711": [_tramo("1.1", "2019-01-01T00:00:00",
                                                                "2019-01-31T23:00:00")]})
        info = _info("900711")
        tramos = politicas.tramos_de_lectura(pol, "900711", {(2019, 1)}, {}, info=info, k2=())
        (p,) = politicas.politicas_de_lectura(pol, info, tramos, U, sha_protocolo=sha_p, sha_catalogo=SHA_CATALOGO)
        self.assertIsNotNone(pc.fullmatch(p["coordinates"]["source"]))
        for v, regla in p["measurements"].items():
            self.assertEqual(regla["source"], politicas.source_medicion(v, sha_p))
        for v, regla in p["quality"].items():
            self.assertEqual(regla["source"], politicas.source_calidad(v, sha_p))
        for sha_protocolo, sha_catalogo in ((umbrales.SHA_TEXTO_M0, SHA_CATALOGO), (sha_p, "0" * 63)):
            with self.assertRaises(ValueError):
                politicas.politicas_de_lectura(pol, info, tramos, U, sha_protocolo=sha_protocolo,
                                               sha_catalogo=sha_catalogo)

    def test_registro_c5_post_hoc_y_errata(self):
        """comprobar_c5: post_hoc, errata_post_c4 y sha256."""
        reglas = {"900721": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T23:00:00")]}
        evaluados = {"900721": [hashlib.sha256(b"artefacto").hexdigest()]}
        errata = {"ruta": "APH/auditoria/20261105/reloj_dmc/errata_1.md",
                  "sha256": hashlib.sha256(b"errata").hexdigest(), "commit": "a" * 40}
        with tempfile.TemporaryDirectory() as tmp:
            def caso(nombre, **kw):
                raiz = Path(tmp) / nombre
                S.politica_reloj_sintetica(raiz, evaluados, reglas, **kw)
                return S.rutas_politica_sintetica(raiz), raiz / "AP"

            # Válido: rutas, huellas y commit; las banderas, de la política.
            rutas, ap = caso("valido")
            registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
            self.assertEqual(registro.ruta, "APH/auditoria/20261101/meteo_combinada/registro_politica_reloj.json")
            self.assertEqual((registro.sha256_politica, registro.sha256_artefactos),
                             (_sha(rutas["politica"]), _sha(rutas["artefactos"])))
            self.assertEqual((registro.post_hoc, registro.errata_post_c4, registro.errata_confirmada),
                             (False, False, None))
            pol, artefactos = politicas.leer_politica_reloj(registro, ap=ap)
            self.assertEqual(artefactos, {evaluados["900721"][0]: "900721"})
            self.assertEqual(politicas.comprobar_c5(registro, pol), [])
            # El formato es el que fabrica sintetico (SIN-5), salvo errata_confirmada, que ahora es un objeto o null.
            self.assertEqual(set(json.loads(rutas["registro"].read_text(encoding="utf-8"))),
                             set(politicas.CLAVES_REGISTRO_C5))
            self.assertEqual(politicas.ESQUEMA_REGISTRO_C5, S.ESQUEMA_REGISTRO_C5)
            # post_hoc y errata_post_c4.
            for nombre, kw, texto in (("post_hoc", {"post_hoc": True}, "post_hoc = true"),
                                      ("errata_sin_confirmar", {"errata_post_c4": True}, "sin una errata confirmada"),
                                      ("errata_sin_bandera", {"errata_confirmada": errata}, "no lleva errata_post_c4")):
                with self.subTest(caso=nombre):
                    rutas, ap = caso(nombre, **kw)
                    registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
                    pol, _ = politicas.leer_politica_reloj(registro, ap=ap)
                    fallas = politicas.comprobar_c5(registro, pol)
                    self.assertTrue(any(texto in f for f in fallas), fallas)
            rutas, ap = caso("errata_confirmada", errata_post_c4=True, errata_confirmada=errata)
            registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
            pol, _ = politicas.leer_politica_reloj(registro, ap=ap)
            self.assertEqual(politicas.comprobar_c5(registro, pol), [])
            self.assertEqual(registro.errata_confirmada, tipos.ErrataConfirmada(**errata))     # TIP-13
            # sha256 distinta, registro ausente o mal formado: ErrorC5 al leer.
            negativas = (("sha_politica", {"sha256_politica": "0" * 64}),
                         ("clave_de_mas", {"post_hoc": False}),
                         ("otra_ruta", {"politica_ruta": "AP/config/otra/politica_reloj_dmc.json"}),
                         ("commit_malo", {"commit_c5": "abc"}),
                         ("errata_texto", {"errata_confirmada": "errata-1"}),
                         ("errata_sin_commit", {"errata_confirmada": {k: errata[k] for k in ("ruta", "sha256")}}),
                         ("esquema", {"schema": "otro/1"}))
            for nombre, cambio in negativas:
                with self.subTest(caso=nombre):
                    rutas, ap = caso(nombre, alterar_registro=cambio)
                    with self.assertRaises(politicas.ErrorC5):
                        politicas.leer_registro_c5(rutas["registro"], ap=ap)
            rutas, ap = caso("sha_artefactos", alterar_registro={"sha256_artefactos": "1" * 64})
            registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
            with self.assertRaises(politicas.ErrorC5):
                politicas.leer_politica_reloj(registro, ap=ap)
            with self.assertRaises(politicas.ErrorC5):
                politicas.leer_registro_c5(Path(tmp) / "nada" / "APH" / "auditoria" / "20261101" / "meteo_combinada"
                                           / politicas.ARCHIVO_REGISTRO_C5, ap=ap)
            rutas, ap = caso("fuera_de_lugar")
            otra = Path(tmp) / "fuera_de_lugar" / "registro_politica_reloj.json"
            otra.write_bytes(rutas["registro"].read_bytes())
            with self.assertRaises(politicas.ErrorC5):
                politicas.leer_registro_c5(otra, ap=ap)
            # La política cambiada después de C5 (sha distinta) se rechaza; con el registro al día, comprobar_c5 ve
            # el adaptador ajeno y la cita de artefactos que no es la del registro.
            rutas, ap = caso("politica_cambiada")
            pol = json.loads(rutas["politica"].read_text(encoding="utf-8"))
            rutas["politica"].write_text(json.dumps(pol) + " ", encoding="utf-8")
            with self.assertRaises(politicas.ErrorC5):
                politicas.leer_registro_c5(rutas["registro"], ap=ap)
            pol["adaptador_sha256"] = "2" * 64
            pol["artefactos_evaluados"]["ruta"] = "config/otra/artefactos_evaluados.json.gz"
            pol["transiciones_sha256"] = "3" * 64
            pol["ajuste_documental"] = True
            _reescribir(rutas, politica=pol)
            registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
            fallas = politicas.comprobar_c5(registro, politicas.leer_politica_reloj(registro, ap=ap)[0])
            for texto in ("adaptador", "artefactos_evaluados", "cambios de hora"):
                self.assertTrue(any(texto in f for f in fallas), (texto, fallas))
            self.assertFalse(any("ajuste_documental" in f for f in fallas), fallas)       # D23: se acepta

    def test_c5_negativas_de_forma(self):
        """POL-1 y POL-2, cada caso en su carpeta (MC-40). comprobar_c5 informa el informe citado con otra ruta o sin
        sha256, dos tramos de RELOJ que comparten una hora, un clock sin verificar o no instantáneo y marcas G que no son
        pares completos; leer_registro_c5 rechaza una errata cuya ruta no es de AP ni de APH y una fecha de C5 que no
        existe. Cada negativa tiene su control aceptado."""
        reglas = {"900671": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T23:00:00")]}
        evaluados = {"900671": [hashlib.sha256(b"artefacto").hexdigest()]}
        errata = {"ruta": "APH/auditoria/20261105/reloj_dmc/errata_1.md",
                  "sha256": hashlib.sha256(b"errata").hexdigest(), "commit": "b" * 40}
        with tempfile.TemporaryDirectory() as tmp:
            def caso(nombre, reglas_=reglas, **kw):
                raiz = Path(tmp) / nombre
                S.politica_reloj_sintetica(raiz, evaluados, reglas_, **kw)
                return S.rutas_politica_sintetica(raiz, kw.get("fecha_c5", S.FECHA_C5_SINTETICA)), raiz / "AP"

            def leer(rutas, ap):
                registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
                return registro, politicas.leer_politica_reloj(registro, ap=ap)[0]

            def fallas_de(rutas, ap):
                return politicas.comprobar_c5(*leer(rutas, ap))

            # La política retocada después de fabricarla (el registro queda al día con su sha256).
            retoques = (
                ("informe_otra_ruta", lambda p: p["informe"].update(ruta="config/meteorologia/reloj_dmc/v1/otro.json"),
                 "no cita el informe"),
                ("informe_sin_sha", lambda p: p["informe"].update(sha256="no es un sha256"), "no cita el informe"),
                ("clock_sin_verificar", lambda p: p["politicas_reloj"][0]["clock"].update(verified=False),
                 "no verificado o no instantáneo"),
                ("clock_no_instantaneo", lambda p: p["politicas_reloj"][0]["clock"].update(timestamp_semantics="mean"),
                 "no verificado o no instantáneo"))
            for nombre, cambio, texto in retoques:
                with self.subTest(caso=nombre):
                    rutas, ap = caso(nombre)
                    self.assertEqual(fallas_de(rutas, ap), [])
                    pol = json.loads(rutas["politica"].read_text(encoding="utf-8"))
                    cambio(pol)
                    _reescribir(rutas, politica=pol)
                    fallas = fallas_de(rutas, ap)
                    self.assertTrue(any(texto in f for f in fallas), fallas)
            # Dos tramos de RELOJ que comparten una hora: el segundo empieza en la hora final del primero.
            for nombre, desde, solapados in (("tramos_comparten_hora", "2019-01-31T23:00:00", True),
                                             ("tramos_contiguos", "2019-02-01T00:00:00", False)):
                with self.subTest(caso=nombre):
                    dos = {"900671": [reglas["900671"][0], _tramo("2.1", desde, "2019-02-28T23:00:00")]}
                    rutas, ap = caso(nombre, dos)
                    fallas = fallas_de(rutas, ap)
                    self.assertEqual(any("solapados" in f for f in fallas), solapados, fallas)
                    self.assertEqual(fallas == [], not solapados, fallas)
                    _, pol = leer(rutas, ap)
                    args = (pol, "900671", {(2019, 1), (2019, 2)}, {})
                    if solapados:
                        with self.assertRaises(ValueError):
                            politicas.tramos_de_lectura(*args, info=_info("900671"), k2=())
                    else:
                        self.assertEqual(len(politicas.tramos_de_lectura(*args, info=_info("900671"), k2=())), 2)
            # Marcas G: las variables de cada año deben ser pares completos (Td con HR, FF con DD).
            for nombre, variables, completas in (("g_hr_sin_par", ["Td"], False),
                                                 ("g_viento_sin_par", ["wind_direction_instant"], False),
                                                 ("g_par_y_medio", ["Td", "relative_humidity", "wind_speed_instant"],
                                                  False),
                                                 ("g_otra_variable", ["Ts"], False),
                                                 ("g_dos_pares", ["relative_humidity", "Td", "wind_direction_instant",
                                                                  "wind_speed_instant"], True)):
                with self.subTest(caso=nombre):
                    marcas = {"900671": {"posible_media_horaria": False,
                                         "reloj_no_verificado": [{"anio": 2019, "variables": variables}]}}
                    rutas, ap = caso(nombre, marcas=marcas)
                    fallas = fallas_de(rutas, ap)
                    self.assertEqual(fallas == [], completas, fallas)
                    self.assertEqual(any("pares completos" in f for f in fallas), not completas, fallas)
                    _, pol = leer(rutas, ap)
                    if completas:
                        self.assertEqual(politicas.marcas_g(pol, "900671"), {2019: frozenset(variables)})
                    else:
                        with self.assertRaises(ValueError):
                            politicas.marcas_g(pol, "900671")
            # Errata con una ruta que no es de AP ni de APH, y fecha de C5 que no existe: ErrorC5 al leer el registro.
            for nombre, kw in (("errata_otra_ruta", {"errata_post_c4": True, "errata_confirmada": {
                                    **errata, "ruta": "otra/auditoria/20261105/reloj_dmc/errata_1.md"}}),
                               ("errata_sin_alias", {"errata_post_c4": True, "errata_confirmada": {
                                    **errata, "ruta": "auditoria/20261105/reloj_dmc/errata_1.md"}}),
                               ("fecha_mes_13", {"fecha_c5": "20261341"}),
                               ("fecha_30_de_febrero", {"fecha_c5": "20270230"}),
                               ("fecha_de_siete_cifras", {"fecha_c5": "2026110"})):
                with self.subTest(caso=nombre):
                    rutas, ap = caso(nombre, **kw)
                    self.assertTrue(rutas["registro"].is_file())
                    with self.assertRaises(politicas.ErrorC5):
                        politicas.leer_registro_c5(rutas["registro"], ap=ap)
            # Controles: una errata de AP y un 29 de febrero que existe.
            rutas, ap = caso("errata_de_ap", errata_post_c4=True,
                             errata_confirmada={**errata, "ruta": "AP/config/meteorologia/reloj_dmc/v1/errata_1.md"})
            self.assertEqual(fallas_de(rutas, ap), [])
            rutas, ap = caso("fecha_bisiesta", fecha_c5="20280229")
            self.assertEqual(politicas.leer_registro_c5(rutas["registro"], ap=ap).ruta,
                             "APH/auditoria/20280229/meteo_combinada/registro_politica_reloj.json")

    def test_registro_c5_solo_en_el_aph_de_ap(self):
        """POL-1 (§2.1: el registro «es `APH/auditoria/<fecha de C5>/meteo_combinada/registro_politica_reloj.json`»):
        debe estar en el APH hermano de ``ap``. Una copia en «<otra>/auditoria/…», en AP, más adentro de APH o en el APH
        de otra raíz se rechaza aunque termine igual; también un ``ap`` que no es el AP real ni un «<raíz>/AP»
        sintético (una copia de AP con otro nombre), o uno dentro de los repositorios reales (sin leer nada: la ruta se
        juzga antes)."""
        reglas = {"900672": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T23:00:00")]}
        evaluados = {"900672": [hashlib.sha256(b"artefacto").hexdigest()]}
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "publicacion"
            S.politica_reloj_sintetica(raiz, evaluados, reglas)
            rutas = S.rutas_politica_sintetica(raiz)
            ap = raiz / "AP"
            self.assertEqual(politicas.leer_registro_c5(rutas["registro"], ap=ap).ruta,
                             "APH/auditoria/20261101/meteo_combinada/registro_politica_reloj.json")
            cola = Path("auditoria") / S.FECHA_C5_SINTETICA / "meteo_combinada" / politicas.ARCHIVO_REGISTRO_C5
            for nombre, destino in (("cualquiera", Path(tmp) / "cualquiera" / cola),
                                    ("en_ap", ap / cola),
                                    ("bajo_otra_carpeta_de_aph", raiz / "APH" / "copia" / cola),
                                    ("aph_de_otra_raiz", Path(tmp) / "otra" / "APH" / cola)):
                with self.subTest(caso=nombre):
                    destino.parent.mkdir(parents=True)
                    destino.write_bytes(rutas["registro"].read_bytes())
                    with self.assertRaises(politicas.ErrorC5):
                        politicas.leer_registro_c5(destino, ap=ap)
            # Un «ap» que no se llama AP, aunque traiga la publicación y su hermano APH el registro.
            shutil.copytree(ap, raiz / "copia_de_AP")
            self.assertEqual(politicas.leer_registro_c5(rutas["registro"], ap=raiz / "AP").ruta,
                             "APH/auditoria/20261101/meteo_combinada/registro_politica_reloj.json")
            with self.assertRaisesRegex(politicas.ErrorC5, "no es el AP real"):
                politicas.leer_registro_c5(rutas["registro"], ap=raiz / "copia_de_AP")
            # Un «<raíz>/AP» dentro de los repositorios reales: se rechaza antes de leer (nada de eso existe).
            for nombre, repo in (("ap_dentro_de_ap_real", AP), ("ap_dentro_de_aph_real", APH)):
                with self.subTest(caso=nombre):
                    with self.assertRaisesRegex(politicas.ErrorC5, "no es el AP real"):
                        politicas.leer_registro_c5(repo / "copia" / "APH" / cola, ap=repo / "copia" / "AP")

    def test_constantes_del_reloj(self):
        """Las constantes copiadas de RELOJ (esquema, claves, rutas, patrón de source y variables de las marcas G) son
        las de reloj_dmc.politica y reloj_dmc.orquestacion (esta última por AST, sin importarla)."""
        from reloj_dmc import politica, tablas
        self.assertEqual(politicas.SHA_TRANSICIONES_RELOJ, tablas.SHA_ANEXO_A)
        self.assertEqual(politicas.SHA_TRANSICIONES_RELOJ, S.SHA_ANEXO_A_RELOJ)
        self.assertEqual(politicas.ESQUEMA_POLITICA_RELOJ, politica.ESQUEMA_POLITICA)
        self.assertEqual(politicas.CLAVES_POLITICA_RELOJ, politica.CLAVES_POLITICA)
        self.assertEqual(politicas.CLAVES_TRAMO_RELOJ, politica.CLAVES_TRAMO)
        self.assertEqual(politicas.CLAVES_CLOCK_RELOJ, politica.CLAVES_CLOCK)
        self.assertEqual(politicas.PATRON_SOURCE_RELOJ, politica.PATRON_SOURCE)
        self.assertEqual(politicas.RUTA_PUBLICACION_RELOJ, politica.RUTA_PUBLICACION_AP)
        self.assertEqual((politicas.ARCHIVO_POLITICA_RELOJ, politicas.ARCHIVO_INFORME_RELOJ,
                          politicas.ARCHIVO_ARTEFACTOS_RELOJ),
                         (politica.ARCHIVO_POLITICA, politica.ARCHIVO_INFORME, politica.ARCHIVO_ARTEFACTOS))
        self.assertEqual((politicas.RUTA_INFORME_RELOJ, politicas.RUTA_ARTEFACTOS_RELOJ),
                         (politica.RUTA_INFORME_AP, politica.RUTA_ARTEFACTOS_AP))
        self.assertEqual(politicas.CLAVE_TRAMOS_ESTACION, politica.CLAVE_TRAMOS_ESTACION)
        self.assertEqual(politicas.VEREDICTO_CONFIRMADA, str(politica.VeredictoEstacion.CONFIRMADA))
        arbol = ast.parse((_RAIZ / "reloj_dmc" / "orquestacion.py").read_text(encoding="utf-8"))
        (nodo,) = [n for n in arbol.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "VARIABLES_MARCA" for t in n.targets)]
        valores = sorted(tuple(ast.literal_eval(v)) for v in nodo.value.values)
        self.assertEqual(valores, sorted(politicas.VARIABLES_G.values()))
        from meteo_combinada import ceguera
        self.assertEqual(politicas.ARCHIVO_REGISTRO_C5, ceguera.REGISTRO_C5)
        for ruta in (politicas.RUTA_POLITICA_AP, politicas.RUTA_ARTEFACTOS_AP,
                     politicas.PREFIJO_AP + politicas.RUTA_INFORME_RELOJ):
            self.assertTrue(ceguera.permitido_de_reloj("/x/" + ruta, k2=True), ruta)
        self.assertTrue(ceguera.permitido_de_reloj(
            "/x/APH/auditoria/20261101/meteo_combinada/" + politicas.ARCHIVO_REGISTRO_C5))

    def test_politicas_que_cruzan_y_regla_reloj(self):
        """POL-13: las que cortan el mes de etiqueta; POL-11: la regla de RELOJ detrás de cada pieza es la publicada."""
        U = _umbrales(self)
        reglas = {"900731": [_tramo("1.1", "2019-01-15T00:00:00", "2019-03-10T23:00:00"),
                             _tramo("2.1", "2019-05-01T00:00:00", "2019-05-31T23:00:00")]}
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), reglas)
        meses = {(2019, 1), (2019, 3), (2019, 5)}
        tramos, pols = _lectura(pol, _info("900731"), U, meses)
        self.assertEqual([(t.id, t.valid_from, t.valid_to) for t in tramos],
                         [("1.1/1", "2019-01-15T00:00:00", "2019-01-31T23:00:00"),
                          ("1.1/2", "2019-03-01T00:00:00", "2019-03-10T23:00:00"),
                          ("2.1/1", "2019-05-01T00:00:00", "2019-05-31T23:00:00")])
        cruzan = {mes: [p["valid_from"] for p in politicas.politicas_que_cruzan(pols, "900731", 2019, mes)]
                  for mes in range(1, 7)}
        self.assertEqual(cruzan, {1: ["2019-01-15T00:00:00"], 2: [], 3: ["2019-03-01T00:00:00"], 4: [],
                                  5: ["2019-05-01T00:00:00"], 6: []})
        self.assertEqual(politicas.politicas_que_cruzan(pols, "900732", 2019, 1), [])
        publicadas = pol["politicas_reloj"]
        for p in pols:
            self.assertIn(politicas.regla_reloj(p), publicadas)
        vistas = []

        def validar(regla, sha):
            vistas.append(regla["clock"]["source"][-90:])
            if regla["valid_from"].startswith("2019-05"):
                raise ValueError("rechazada")
        aceptadas, rechazadas = politicas.validar_reglas(pols, "f" * 64, validar)
        self.assertEqual([p["valid_from"][:7] for p in aceptadas], ["2019-01", "2019-03"])
        self.assertEqual(rechazadas, ("2.1",))
        self.assertEqual(len(vistas), 2)                    # una vez por tramo de RELOJ

        def roto(regla, sha):
            raise KeyError("error de código")
        with self.assertRaises(KeyError):                    # MC-57: sólo ValueError deja sin regla
            politicas.validar_reglas(pols, "f" * 64, roto)

    def test_politicas_que_cruzan_bordes_del_mes(self):
        """POL-13 en los bordes: una política que termina en la primera hora del mes (AAAA-MM-01T00:00:00) o que empieza
        en su última hora (último día T23:00:00) cruza ese mes; si termina justo antes o empieza justo después, no. Un
        tramo de RELOJ termina en «la última etiqueta con dato», que puede ser la primera hora de un mes."""
        def p(desde, hasta):
            return {"station_code": "900741", "valid_from": desde, "valid_to": hasta}
        pols = [p("2019-01-20T00:00:00", "2019-02-01T00:00:00"),       # termina en la primera hora de febrero
                p("2019-03-31T23:00:00", "2019-04-10T00:00:00"),       # empieza en la última hora de marzo
                p("2019-06-01T00:00:00", "2019-06-30T23:00:00"),       # exactamente junio
                p("2019-12-31T23:00:00", "2020-01-01T00:00:00")]       # dos horas, en dos años
        esperado = {(2019, 1): [0], (2019, 2): [0], (2019, 3): [1], (2019, 4): [1], (2019, 5): [], (2019, 6): [2],
                    (2019, 7): [], (2019, 11): [], (2019, 12): [3], (2020, 1): [3], (2020, 2): []}
        for (anio, mes), indices in esperado.items():
            with self.subTest(anio=anio, mes=mes):
                self.assertEqual(politicas.politicas_que_cruzan(pols, "900741", anio, mes), [pols[i] for i in indices])


# ---------------------------------------------------------------------------
# Ola 3: decisiones D23 a D26 [delegadas] (APH/auditoria/20261023/meteo_combinada/m1/decisiones_autor_m1_20261026.md)
# ---------------------------------------------------------------------------
_HR = ["Td", "relative_humidity"]
_VIENTO = ["wind_speed_instant", "wind_direction_instant"]


def _marcas(*pares, media_horaria=False) -> dict:
    return {"posible_media_horaria": media_horaria,
            "reloj_no_verificado": [{"anio": a, "variables": list(v)} for a, v in pares]}


def _errata(texto: bytes, letra: str) -> dict:
    return {"ruta": "APH/auditoria/20261105/reloj_dmc/errata_1.md", "sha256": hashlib.sha256(texto).hexdigest(),
            "commit": letra * 40}


class PruebasOla3(unittest.TestCase):
    def test_d25_cortes_literales_por_anios_g(self):
        """D25 (POL-4): se corta el 1 de enero de cada año con marcas G y el del año siguiente, aunque dos años seguidos
        tengan las mismas marcas (2015 y 2016); años sin marcas seguidos quedan juntos (2020 y 2021); un año marcado
        antes del tramo (2013) no corta; un tramo que empieza el 1 de enero del año marcado no se parte ahí, y uno que
        termina el 1 de enero siguiente deja esa hora sola. politicas_de_lectura rechaza el tramo sin partir."""
        U = _umbrales(self)
        reglas = {"900751": [_tramo("1.1", "2014-03-10T00:00:00", "2022-06-30T23:00:00")],
                  "900752": [_tramo("1.1", "2015-01-01T00:00:00", "2015-12-31T23:00:00")],
                  "900753": [_tramo("1.1", "2015-06-01T00:00:00", "2016-01-01T00:00:00")]}
        marcas = {"900751": _marcas((2013, _HR), (2015, _HR), (2016, _HR), (2018, _VIENTO), (2019, _HR),
                                    (2022, _VIENTO)),
                  "900752": _marcas((2015, _HR)), "900753": _marcas((2015, _HR))}
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), reglas, marcas=marcas)
        meses = {(a, m) for a in range(2013, 2023) for m in range(1, 13)}
        esperado = {
            "900751": [("2014-03-10T00:00:00", "2014-12-31T23:00:00", []),
                       ("2015-01-01T00:00:00", "2015-12-31T23:00:00", _HR),
                       ("2016-01-01T00:00:00", "2016-12-31T23:00:00", _HR),
                       ("2017-01-01T00:00:00", "2017-12-31T23:00:00", []),
                       ("2018-01-01T00:00:00", "2018-12-31T23:00:00", _VIENTO),
                       ("2019-01-01T00:00:00", "2019-12-31T23:00:00", _HR),
                       ("2020-01-01T00:00:00", "2021-12-31T23:00:00", []),
                       ("2022-01-01T00:00:00", "2022-06-30T23:00:00", _VIENTO)],
            "900752": [("2015-01-01T00:00:00", "2015-12-31T23:00:00", _HR)],
            "900753": [("2015-06-01T00:00:00", "2015-12-31T23:00:00", _HR),
                       ("2016-01-01T00:00:00", "2016-01-01T00:00:00", [])]}
        for codigo, piezas in esperado.items():
            with self.subTest(codigo=codigo):
                tramos, pols = _lectura(pol, _info(codigo), U, meses)
                self.assertEqual([(t.id, t.valid_from, t.valid_to) for t in tramos],
                                 [(f"1.1/{k}", a, b) for k, (a, b, _) in enumerate(piezas, start=1)])
                self.assertEqual([sorted(v for v, r in p["measurements"].items() if not r["verified"]) for p in pols],
                                 [sorted(v) for _, _, v in piezas])
                self.assertEqual([t.id for t in politicas.tramos_de_politicas(pols)], [t.id for t in tramos])
        # Sin partir 2015 y 2016 (mismas marcas: la lectura anterior a D25 lo aceptaba), politicas_de_lectura no arma la
        # política; tampoco 2016 con 2017 (marcas distintas). Los que D25 deja juntos (2020-2021) sí.
        info = _info("900751")
        tramos = politicas.tramos_de_lectura(pol, "900751", meses, politicas.marcas_g(pol, "900751"), info=info, k2=())

        def unir(i, j):
            return tipos.TramoPolitica(**{**tramos[i].__dict__, "valid_to": tramos[j].valid_to})

        def leer(lista):
            return politicas.politicas_de_lectura(pol, info, lista, U, sha_protocolo=U.sha256_texto_vigente,
                                                  sha_catalogo=SHA_CATALOGO)
        self.assertEqual(len(leer(tramos)), len(esperado["900751"]))
        for nombre, i, j in (("2015_y_2016", 1, 2), ("2016_y_2017", 2, 3), ("2019_a_2021", 5, 6)):
            with self.subTest(sin_partir=nombre):
                with self.assertRaisesRegex(ValueError, "D25"):
                    leer([*tramos[:i], unir(i, j), *tramos[j + 1:]])
        # Los cortes se calculan igual con marcas a mano: un año con marcas vacías no corta.
        a, b = tramos[0].valid_from, tramos[-1].valid_to
        self.assertEqual(len(politicas.tramos_de_lectura(pol, "900751", meses, {2015: frozenset()}, info=info, k2=())),
                         1)
        self.assertEqual([(t.valid_from, t.valid_to) for t in politicas.tramos_de_lectura(
            pol, "900751", meses, {2016: frozenset(_HR)}, info=info, k2=())],
            [(a, "2015-12-31T23:00:00"), ("2016-01-01T00:00:00", "2016-12-31T23:00:00"), ("2017-01-01T00:00:00", b)])

    def test_d24_tramos_marca_14_son_los_de_la_efectiva(self):
        """D24 (POL-14): los tramos de la marca 14 son los de la política efectiva: partidos por todos los quiebres de K4
        (también el de T2a sin T2b), por los años G (D25) y por los meses sin artefacto, con los ids de
        tramos_de_politicas sobre la lista completa (POL-10), sólo de la estación pedida y en orden."""
        U = _umbrales(self)
        reglas = {"900761": [_tramo("1.1", "2017-01-01T00:00:00", "2019-12-31T23:00:00"),
                             _tramo("2.1", "2020-03-01T00:00:00", "2020-12-31T23:00:00")],
                  "900762": [_tramo("1.1", "2019-01-01T00:00:00", "2019-12-31T23:00:00")]}
        with tempfile.TemporaryDirectory() as tmp:
            pol = _politica_reloj(Path(tmp), reglas, marcas={"900761": _marcas((2018, _HR))})
        meses = {(a, m) for a in range(2017, 2021) for m in range(1, 13)}

        def mes2000(anio, mes):
            return (anio - 2000) * 12 + mes - 1
        T2A, T2B = tipos.Estadistico.T2A.value, tipos.Estadistico.T2B.value
        k4 = tipos.ResultadoK4(codigo="900761", quiebres=(
            tipos.Quiebre(T2A, mes2000(2017, 7), 0.0, tipos.ClaseQuiebre.METODO_REDUCCION),
            tipos.Quiebre(T2B, mes2000(2019, 4), 0.0, tipos.ClaseQuiebre.TRASLADO),
            tipos.Quiebre(T2B, mes2000(2020, 6), 0.0, tipos.ClaseQuiebre.BAROMETRO)),
            ultimo_traslado=mes2000(2019, 4), ultimo_barometro=mes2000(2020, 6), sin_prueba=False)
        _, lectura_1 = _lectura(pol, _info("900761"), U, meses)
        _, lectura_2 = _lectura(pol, _info("900762"), U, meses)
        efectivas = politicas.politicas_efectivas(lectura_1 + lectura_2, {"900761": k4})
        esperado = [("1.1/1", "2017-01-01T00:00:00", "2017-06-30T19:00:00", "traslado"),     # L_k = u_k − 4 h
                    ("1.1/2", "2017-06-30T20:00:00", "2017-12-31T23:00:00", "traslado"),     # T2a sin T2b
                    ("1.1/3", "2018-01-01T00:00:00", "2018-12-31T23:00:00", "traslado"),     # año G (D25)
                    ("1.1/4", "2019-01-01T00:00:00", "2019-03-31T19:00:00", "traslado"),
                    ("1.1/5", "2019-03-31T20:00:00", "2019-12-31T23:00:00", None),           # tras el traslado
                    ("2.1/1", "2020-03-01T00:00:00", "2020-05-31T19:00:00", None),
                    ("2.1/2", "2020-05-31T20:00:00", "2020-12-31T23:00:00", None)]           # barómetro
        tramos = politicas.tramos_marca_14(efectivas, "900761")
        self.assertEqual([(t.id, t.valid_from, t.valid_to, t.motivo) for t in tramos], esperado)
        self.assertEqual(tramos, [t for t in politicas.tramos_de_politicas(efectivas) if t.codigo == "900761"])
        self.assertTrue(all(isinstance(t, tipos.TramoPolitica) and t.codigo == "900761" for t in tramos))
        self.assertEqual(len(politicas.tramos_de_politicas(lectura_1)), 4)              # no son los de lectura
        # El orden de la lista no cambia ids ni orden (POL-10); la otra estación tiene los suyos.
        self.assertEqual(politicas.tramos_marca_14(list(reversed(efectivas)), "900761"), tramos)
        self.assertEqual([(t.id, t.valid_from) for t in politicas.tramos_marca_14(efectivas, "900762")],
                         [("1.1/1", "2019-01-01T00:00:00")])
        self.assertEqual(politicas.tramos_marca_14(efectivas, "900763"), [])
        for malo in ("90076", 900761, None):
            with self.subTest(codigo=repr(malo)):
                with self.assertRaises(ValueError):
                    politicas.tramos_marca_14(efectivas, malo)

    def test_d23_ajuste_documental_se_acepta_y_se_declara(self):
        """D23 (POL-2, POL-15): con ajuste_documental = true C5 es válido y declaracion_c5 lo declara; sólo rutas,
        huellas, commit y banderas, con tipos de Python. Un valor no booleano es una falla; de un C5 no válido no hay
        declaración (ErrorC5)."""
        reglas = {"900781": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T23:00:00")]}
        evaluados = {"900781": [hashlib.sha256(b"artefacto").hexdigest()]}
        errata = _errata(b"errata del ajuste", "d")
        with tempfile.TemporaryDirectory() as tmp:
            def caso(nombre, ajuste, **kw):
                raiz = Path(tmp) / nombre
                S.politica_reloj_sintetica(raiz, evaluados, reglas, **kw)
                rutas, ap = S.rutas_politica_sintetica(raiz), raiz / "AP"
                if ajuste is not False:
                    pol = json.loads(rutas["politica"].read_text(encoding="utf-8"))
                    pol["ajuste_documental"] = ajuste
                    _reescribir(rutas, politica=pol)
                registro = politicas.leer_registro_c5(rutas["registro"], ap=ap)
                return registro, politicas.leer_politica_reloj(registro, ap=ap)[0]

            for nombre, ajuste, kw in (("sin_ajuste", False, {}), ("con_ajuste", True, {}),
                                       ("con_ajuste_y_errata", True, {"errata_post_c4": True,
                                                                     "errata_confirmada": errata})):
                with self.subTest(caso=nombre):
                    registro, pol = caso(nombre, ajuste, **kw)
                    self.assertEqual(politicas.comprobar_c5(registro, pol), [])
                    d = politicas.declaracion_c5(registro, pol)
                    self.assertEqual(tuple(d), politicas.CLAVES_DECLARACION_C5)
                    self.assertIs(d["ajuste_documental"], ajuste)
                    self.assertEqual((d["registro"], d["sha256_politica"], d["sha256_artefactos"], d["commit_c5"]),
                                     (registro.ruta, registro.sha256_politica, registro.sha256_artefactos,
                                      registro.commit_c5))
                    self.assertIs(d["post_hoc"], False)
                    self.assertIs(d["errata_post_c4"], "errata_post_c4" in kw)
                    self.assertEqual(d["errata_confirmada"], errata if "errata_confirmada" in kw else None)
                    # Sólo textos, booleanos y null (ningún número de datos); ida y vuelta por el JSON canónico.
                    hojas = [v for v in d.values() if not isinstance(v, dict)] + list((d["errata_confirmada"] or {})
                                                                                     .values())
                    self.assertTrue(all(type(v) in (str, bool, type(None)) for v in hojas), d)
                    self.assertEqual(politicas._leer_json(politicas.entorno.json_canonico(d)), d)
                    self.assertTrue(d["registro"].startswith("APH/auditoria/"))
                    self.assertTrue(all(politicas.entorno.sin_datos_privados(v) for v in hojas if isinstance(v, str)))
            for nombre, ajuste in (("ajuste_entero", 1), ("ajuste_texto", "true"), ("ajuste_nulo", None)):
                with self.subTest(caso=nombre):
                    registro, pol = caso(nombre, ajuste)
                    fallas = politicas.comprobar_c5(registro, pol)
                    self.assertTrue(any("«ajuste_documental» booleano" in f for f in fallas), fallas)
                    with self.assertRaises(politicas.ErrorC5):
                        politicas.declaracion_c5(registro, pol)
            registro, pol = caso("post_hoc", True, post_hoc=True)
            with self.assertRaisesRegex(politicas.ErrorC5, "post_hoc"):
                politicas.declaracion_c5(registro, pol)
            with self.assertRaises(TypeError):
                politicas.declaracion_c5({"ruta": registro.ruta}, pol)

    def _publicacion_con_errata(self, raiz: Path):
        """D26: la publicación de C5, su original archivada con sufijo y la corregida por una errata en la misma ruta,
        con su registro en la carpeta de la fecha de la errata. Devuelve (rutas de la original, rutas de la corregida,
        ruta archivada, bytes de la original, errata)."""
        reglas = {"900771": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T23:00:00")]}
        corregidas = {"900771": [_tramo("1.1", "2019-01-01T00:00:00", "2019-01-31T22:00:00")]}
        evaluados = {"900771": [hashlib.sha256(b"artefacto 900771").hexdigest()]}
        errata = _errata(b"errata de RELOJ", "c")
        S.politica_reloj_sintetica(raiz, evaluados, reglas)
        antes = S.rutas_politica_sintetica(raiz)
        original = antes["politica"].read_bytes()
        archivada = antes["politica"].with_name("politica_reloj_dmc_ERRATA1_original.json")
        archivada.write_bytes(original)
        S.politica_reloj_sintetica(raiz, evaluados, corregidas, errata_post_c4=True, errata_confirmada=errata,
                                   fecha_c5="20261105")
        return antes, S.rutas_politica_sintetica(raiz, "20261105"), archivada, original, errata, evaluados

    def test_d26_errata_en_la_misma_ruta(self):
        """D26 (POL-1): la política corregida por una errata va en la misma ruta de publicación, con su nueva sha256 en
        el registro y la errata citada; la original queda archivada con sufijo y M1 no la cita. El registro anterior
        ya no calza; uno que cite la archivada o la corregida en otra ruta se rechaza."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "publicacion"
            ap = raiz / "AP"
            antes, despues, archivada, original, errata, _ = self._publicacion_con_errata(raiz)
            self.assertEqual(despues["politica"], antes["politica"])                     # la misma ruta
            self.assertEqual(antes["politica"].relative_to(ap).as_posix(),
                             politicas.RUTA_POLITICA_AP[len(politicas.PREFIJO_AP):])
            registro = politicas.leer_registro_c5(despues["registro"], ap=ap)
            self.assertEqual(registro.ruta, "APH/auditoria/20261105/meteo_combinada/registro_politica_reloj.json")
            self.assertEqual(registro.sha256_politica, _sha(despues["politica"]))
            self.assertNotEqual(registro.sha256_politica, hashlib.sha256(original).hexdigest())
            self.assertEqual(registro.errata_confirmada, tipos.ErrataConfirmada(**errata))
            pol, _ = politicas.leer_politica_reloj(registro, ap=ap)
            self.assertEqual([r["valid_to"] for r in pol["politicas_reloj"]], ["2019-01-31T22:00:00"])
            self.assertEqual(politicas.comprobar_c5(registro, pol), [])
            d = politicas.declaracion_c5(registro, pol)
            self.assertEqual((d["sha256_politica"], d["errata_post_c4"], d["errata_confirmada"]),
                             (registro.sha256_politica, True, errata))
            self.assertNotIn(archivada.name, json.dumps(d))                              # M1 no cita la original
            info = _info("900771")
            tramos = politicas.tramos_de_lectura(pol, "900771", {(2019, 1)}, {}, info=info, k2=())
            self.assertEqual([(t.valid_from, t.valid_to) for t in tramos],
                             [("2019-01-01T00:00:00", "2019-01-31T22:00:00")])
            # El registro de C5 anterior a la errata ya no calza con la política publicada.
            with self.assertRaisesRegex(politicas.ErrorC5, "sha256"):
                politicas.leer_registro_c5(antes["registro"], ap=ap)
            # Un registro que cite la original archivada, o la corregida en otra carpeta, no es el de RELOJ §7.1.
            otra = ap / "config" / "meteorologia" / "reloj_dmc" / "v1_errata1" / politicas.ARCHIVO_POLITICA_RELOJ
            otra.parent.mkdir(parents=True)
            otra.write_bytes(despues["politica"].read_bytes())
            base = json.loads(despues["registro"].read_text(encoding="utf-8"))
            for fecha, nombre, cambio in (
                    ("20261106", "cita_la_archivada", {"politica_ruta": "AP/config/meteorologia/reloj_dmc/v1/"
                                                                       + archivada.name,
                                                       "sha256_politica": hashlib.sha256(original).hexdigest()}),
                    ("20261107", "corregida_en_otra_ruta", {"politica_ruta": "AP/" + otra.relative_to(ap).as_posix()})):
                with self.subTest(caso=nombre):
                    ruta = raiz / "APH" / "auditoria" / fecha / "meteo_combinada" / politicas.ARCHIVO_REGISTRO_C5
                    ruta.parent.mkdir(parents=True)
                    ruta.write_text(json.dumps({**base, **cambio}, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaisesRegex(politicas.ErrorC5, "debe citar"):
                        politicas.leer_registro_c5(ruta, ap=ap)
            # La corregida sin errata_post_c4 o sin la errata en el registro no es válida (§2.1).
            for nombre, kw, texto in (("sin_errata_en_el_registro", {"errata_post_c4": True}, "sin una errata"),
                                      ("sin_bandera", {"errata_confirmada": errata}, "no lleva errata_post_c4")):
                with self.subTest(caso=nombre):
                    raiz_k = Path(tmp) / nombre
                    S.politica_reloj_sintetica(raiz_k, {"900771": ["e" * 64]},
                                               {"900771": [_tramo("1.1", "2019-01-01T00:00:00",
                                                                  "2019-01-31T22:00:00")]}, **kw)
                    registro_k = politicas.leer_registro_c5(S.rutas_politica_sintetica(raiz_k)["registro"],
                                                            ap=raiz_k / "AP")
                    pol_k, _ = politicas.leer_politica_reloj(registro_k, ap=raiz_k / "AP")
                    fallas = politicas.comprobar_c5(registro_k, pol_k)
                    self.assertTrue(any(texto in f for f in fallas), fallas)
                    with self.assertRaises(politicas.ErrorC5):
                        politicas.declaracion_c5(registro_k, pol_k)

    def test_d26_validar_regla_usa_la_corregida(self):
        """D26 con validar_regla_reloj_dmc (huella de la clausura del reloj): en la ruta de publicación, la regla de la
        política corregida se acepta y la de la original archivada ya no es una regla publicada (se rechaza)."""
        U = _umbrales(self)
        validar = _validador(self)
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "publicacion"
            ap = raiz / "AP"
            _, despues, archivada, original, _, evaluados = self._publicacion_con_errata(raiz)
            registro = politicas.leer_registro_c5(despues["registro"], ap=ap)
            pol, _ = politicas.leer_politica_reloj(registro, ap=ap)
            pol_original = json.loads(original.decode("utf-8"))
            info = _info("900771")
            (sha_artefacto,) = evaluados["900771"]

            def contra_la_publicada(regla, sha):
                validar(regla, sha, politica_ruta=despues["politica"])
            for nombre, politica, rechazadas in (("corregida", pol, ()), ("original_archivada", pol_original, ("1.1",))):
                with self.subTest(politica=nombre):
                    _, pols = _lectura(politica, info, U, {(2019, 1)})
                    aceptadas, rech = politicas.validar_reglas(pols, sha_artefacto, contra_la_publicada)
                    self.assertEqual(rech, rechazadas)
                    self.assertEqual(len(aceptadas), 0 if rechazadas else len(pols))
            self.assertTrue(archivada.is_file())


if __name__ == "__main__":
    unittest.main()
