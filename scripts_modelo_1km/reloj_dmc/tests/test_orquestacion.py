"""Pruebas de orquestacion.py (pipeline de §5.2 y grupo C de §8).

Las que llevan «pNN» son el punto NN de §8. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
De punta a punta: las estaciones del grupo C se fabrican con el formato real (``sintetico.fabricar_descarga``:
``run_download`` del descargador vigente, con cliente y guarda falsos y ``defer_heavy_checks = True``), se
extraen con ``extraccion.extraer_dmc`` y el adaptador fijado, y se evalúan con ``orquestacion.evaluar_red``.
Todo en una carpeta temporal (``tempfile.TemporaryDirectory``), que se fabrica una sola vez para el módulo.
Las estaciones que sólo hacen falta para la calibración de E3t (≥ 30 estación-años) van en memoria
(``sintetico.entrada_en_memoria``), como en la batería D. La referencia «ERA5» es ``SerieEra5Memoria``.
A ciegas: ningún dato DMC ni nada bajo /Volumes. Si falta el código fijado o los umbrales de C0, la prueba se
omite con el motivo y no se da por aprobada.
"""
import sys

sys.dont_write_bytecode = True

import functools  # noqa: E402
import gzip  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zoneinfo  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import (decision, entorno, extraccion, fijados, orquestacion, politica, red,  # noqa: E402
                       sintetico, tablas, umbrales)
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_GUARDAS, ESQUEMA_HORAS,  # noqa: E402
                             ESQUEMA_MARCAS, ESQUEMA_RACHAS, Estado, Hipotesis, Linea, ModoE3t, MotivoAnio, Nivel,
                             Regla, Tramo, Veredicto, validar_esquema)

S = sintetico
O = orquestacion
AP = _RAIZ.parent
APH = AP.parent / "Air-Pollution-Health-Chile"
C0 = O.LINEAS_ACTIVAS_C0
CON_E6 = C0 | {Linea.E6}

# Estaciones del grupo C, fabricadas con el formato real (una sola descarga para el módulo).
CASOS = {
    "utc": S.caso_simple("901601", "F(0)", "a", anios=(2018, 2019)),
    "aerodromo": S.caso_simple("901602", "F(0)", "c", anios=(2019, 2019)),
    "f4_e2": S.caso_simple("901701", "F(-4)", "b", anios=(2015, 2015)),
    "f4_e1a": S.caso_simple("901702", "F(-4)", "a", anios=(2019, 2019)),
    "f4_sin": S.caso_simple("901703", "F(-4)", "a", anios=(2015, 2015)),
    "civil": S.caso_simple("901801", "C(America/Santiago)", "b", anios=(2014, 2016)),
    "p19": S.caso_simple("901901", "Ts:F(0)|QFE:F(0)|marcas:F(-4)", "b", anios=(2019, 2019)),
    "cambio": S.caso_simple("902001", "F(-4);F(0)@2018-07-01T00:00Z", "b", anios=(2016, 2020)),
    "parte1": S.caso_simple("902101", "F(0);F(-4)@2019-03-01T00:00Z;F(0)@2019-04-01T00:00Z", "b",
                            anios=(2019, 2019)),
    "parte2": S.caso_simple("902102", "F(0);F(-4)@2019-03-01T00:00Z;F(0)@2019-04-01T00:00Z;"
                                      "F(-4)@2019-11-01T00:00Z;F(0)@2019-12-01T00:00Z", "b", anios=(2019, 2019)),
    "termica": S.caso_simple("902201", "F(0)", "e", anios=(2019, 2019)),
    "pascua": S.caso_simple("902301", S.PASCUA_PROPIO, "b", sitio="pascua", anios=(2019, 2019)),
}
# Estaciones en memoria para la calibración de E3t (3 × 10 = 30 estación-años, CAL_E3T_MIN).
CALIBRACION = tuple(S.caso_simple(f"9100{i:02d}", "F(0)", "a", anios=(2010, 2019)) for i in range(3))
# Un «aeródromo» UTC de 20 h (04-23 UTC, en memoria): sin E4p (hueco circular de 5 h) y con días de ≥ 20
# valores, así que E3t puede pasar el filtro de §4.3.3 (ORQ-10).
AERODROMO_20H = S.caso_simple("902002", "F(0)", "a", anios=(2019, 2019))
HORAS_CERRADO = (0, 1, 2, 3)

_ESTADO: dict = {}


def setUpModule():
    zoneinfo.reset_tzpath(to=[])               # §9 y §8.A.2: sólo el paquete tzdata del intérprete
    zoneinfo.ZoneInfo.clear_cache()
    for ruta in (APH / umbrales.PROTOCOLO_C0, APH / umbrales.JSON_C0):
        if not ruta.is_file():
            raise unittest.SkipTest(f"falta {ruta.name} anclado en C0; las pruebas no se dan por aprobadas")
    for ruta in (AP / fijados.RUTA_DESCARGADOR, AP / fijados.RUTA_ADAPTADOR, AP / fijados.RUTA_COMUN_MODELO):
        if not ruta.is_file():
            raise unittest.SkipTest(f"falta el código fijado {ruta.name}; las pruebas no se dan por aprobadas")
    sha = entorno.sha256_archivo(AP / fijados.RUTA_DESCARGADOR)
    if sha not in fijados.VERSIONES_ADMITIDAS_C0:
        raise unittest.SkipTest(f"el descargador en AP ({sha[:8]}…) no es una versión admitida en C0")
    _ESTADO.update(U=umbrales.cargar_c0(APH), T=tablas.cargar_tablas(), MZ=fijados.macrozona_region(AP),
                   D=fijados.cargar_descargador(AP, sha), A=fijados.cargar_adaptador(AP))


def tearDownModule():
    carpeta = _ESTADO.pop("carpeta", None)
    if carpeta is not None:
        carpeta.cleanup()


# ---------------------------------------------------------------------------------------------
# Fabricación (una vez) y redes
# ---------------------------------------------------------------------------------------------
def _descarga() -> dict:
    """Fabrica todas las estaciones de CASOS con run_download y las extrae (una vez por módulo)."""
    if "descarga" not in _ESTADO:
        carpeta = tempfile.TemporaryDirectory()
        _ESTADO["carpeta"] = carpeta
        raiz = Path(carpeta.name)
        casos = list(CASOS.values())
        desde = f"{min(c.anios[0] for c in casos)}-01-01"
        hasta = f"{max(c.anios[1] for c in casos)}-12-31"
        dmc = S.fabricar_descarga(casos, raiz, _ESTADO["D"], desde, hasta)
        destino = raiz / "corrida"
        resumen = extraccion.extraer_dmc(dmc, _ESTADO["A"], set(fijados.VERSIONES_ADMITIDAS_C0), _ESTADO["U"], destino,
                                         hecho=lambda u, h: False, registrar=lambda *a: None, avance=lambda *a: None)
        _ESTADO["descarga"] = {"raiz": raiz, "dmc": dmc, "destino": destino, "resumen": resumen,
                               "meses": extraccion.leer_meses(destino)}
    return _ESTADO["descarga"]


def _infos(casos, serie, carpeta: Path):
    """Catálogo DMC sintético (el que deja parse_catalog) e InfoEstacion de cada caso (§3.3)."""
    ruta = carpeta / f"catalogo_{len(list(carpeta.iterdir()))}.json.gz"
    ruta.write_bytes(gzip.compress(json.dumps({"stations": S.catalogo_dmc_sintetico(casos)}).encode("utf-8")))
    catalogo, _ = extraccion.leer_catalogo_dmc(ruta)
    pixeles = S.catalogo_pixeles_sintetico(casos)
    validos = {int(p) for p in pixeles.loc[pixeles["valido"], "pixel_id"]}
    enlaces = extraccion.enlazar_pixeles(catalogo, pixeles, validos, _ESTADO["U"])
    medias = {p: serie.media(p, "sp") for p in validos}
    infos = extraccion.info_estaciones(catalogo, pixeles, enlaces, medias, {}, _ESTADO["MZ"], _ESTADO["U"])
    return catalogo, infos


def _huellas() -> politica.HuellasPolitica:
    """Huellas de una política de prueba (sólo para armarla en memoria y releerla en una carpeta temporal)."""
    return politica.HuellasPolitica(
        protocolo_sha256=umbrales.SHA_PROTOCOLO_C0, commit_ap="0" * 40, configuracion_sha256=umbrales.SHA_JSON_C0,
        informe_sha256=entorno.sha256_bytes(b"informe de prueba"),
        artefactos_evaluados_sha256=entorno.sha256_bytes(b"artefactos de prueba"),
        adaptador_sha256=fijados.SHA_ADAPTADOR, python=platform.python_version(),
        tzdata=tablas.version_de_base(), transiciones_sha256=tablas.SHA_ANEXO_A)


def _red(nombres=(), *, memoria=(), transformar=None, sesgo=None, lineas=C0, isd=False, opciones=None):
    """Red con las estaciones fabricadas ``nombres`` (de CASOS) y los casos ``memoria``; devuelve
    (ResultadoRed, política en memoria, casos). ``transformar``: código → función sobre el extracto."""
    fabricados = [CASOS[n] for n in nombres]
    casos = fabricados + list(memoria)
    serie = S.serie_era5_de_casos(casos, sesgo_termico_h=sesgo)
    d = _descarga() if fabricados else None
    with tempfile.TemporaryDirectory() as carpeta:
        catalogo, infos = _infos(casos, serie, Path(carpeta))
    transformar = transformar or {}
    opciones = opciones or O.OpcionesCorrida(lineas_activas=frozenset(lineas))

    def fabrica():
        if fabricados:
            codigos = [c.codigo for c in fabricados]
            meses = d["meses"]
            marcadas = extraccion.marcar_coordenadas_inconsistentes({c: infos[c] for c in codigos}, catalogo,
                                                                    meses, _ESTADO["U"])
            for caso in fabricados:
                ext = extraccion.leer_extracto(d["destino"], caso.codigo)
                propios = meses[meses["codigo"] == caso.codigo].reset_index(drop=True)
                yield O.EntradaEstacion(marcadas[caso.codigo], transformar.get(caso.codigo, lambda x: x)(ext),
                                        propios, isd=S.isd_sintetico(caso) if isd else None)
        for caso in memoria:
            ext, meses = S.entrada_en_memoria(caso)
            yield O.EntradaEstacion(infos[caso.codigo], transformar.get(caso.codigo, lambda x: x)(ext), meses,
                                    isd=S.isd_sintetico(caso) if isd else None)

    resultado = O.evaluar_red(fabrica, serie, _ESTADO["T"], _ESTADO["U"], opciones, huellas=_huellas())
    return resultado, resultado.politica, casos


def _sin_horas(extracto: pd.DataFrame) -> pd.DataFrame:
    return extracto[~extracto["L"].dt.hour.isin(HORAS_CERRADO)].reset_index(drop=True)


@functools.lru_cache(maxsize=None)
def _red_e3t_completa():
    """El aeródromo de 13 h (fabricado), el de 20 h y la calibración (en memoria), sin sesgo de referencia."""
    return _red(["aerodromo"], memoria=CALIBRACION + (AERODROMO_20H,),
                transformar={AERODROMO_20H.codigo: _sin_horas})


def _decisiones(r, codigo: str) -> dict[int, object]:
    return {d.anio: d for d in r.decisiones if d.codigo == codigo}


def _evidencia(r, codigo: str):
    return next(e for e in r.evidencias if e.info.codigo == codigo)


def _anual(r, codigo: str, linea: Linea, regla: str | None = None) -> dict[tuple[int, str], str]:
    e = _evidencia(r, codigo).estados
    sel = (e["linea"] == str(linea)) & (e["nivel"] == "anio")
    if regla is not None:
        sel &= e["regla"] == regla
    return {(int(a), h): s for a, h, s in zip(e.loc[sel, "anio"], e.loc[sel, "H"], e.loc[sel, "estado"])}


class _Base(unittest.TestCase):
    def assertIdaYVuelta(self, pol, casos):
        """R-34 y §8, reglas comunes: _utc(L, regla emitida) == u para toda etiqueta con regla."""
        self.assertIsNotNone(pol)
        self.assertEqual(S.comprobar_ida_y_vuelta(pol, casos, _ESTADO["A"]), [])

    def assertVeredicto(self, d, veredicto, clase=None, motivo=None):
        self.assertEqual(d.veredicto, veredicto, (d.anio, d.motivo, d.detalle))
        self.assertEqual(d.clase_confirmada, clase)
        if motivo is not None:
            self.assertEqual(d.motivo, motivo, d.detalle)


# ---------------------------------------------------------------------------------------------
# Grupo C de §8 (puntos 16 a 23), de punta a punta
# ---------------------------------------------------------------------------------------------
class PruebasGrupoC(_Base):
    def test_p16_estacion_utc_da_f0_en_un_tramo(self):
        """Estación de 24 h con QFE: F(0), desfase 0, un solo tramo (2018-2019)."""
        r, pol, casos = _red(["utc"])
        codigo = CASOS["utc"].codigo
        decs = _decisiones(r, codigo)
        self.assertEqual(sorted(decs), [2018, 2019])
        for d in decs.values():
            self.assertVeredicto(d, Veredicto.CONFIRMADO, "F(0)")
            self.assertTrue({"E3p", "E4p"} <= set(d.lineas_apoyo), d.lineas_apoyo)
        (tramo,) = r.tramos[codigo]
        self.assertEqual((tramo.id, tramo.valid_from, tramo.valid_to, tramo.fixed_offset_minutes, tramo.clase),
                         ("1.1", datetime(2018, 1, 1), datetime(2019, 12, 31, 23), 0, "F(0)"))
        self.assertEqual(r.estaciones[codigo]["veredicto"], "confirmada")
        self.assertEqual(r.estaciones[codigo]["reloj"], "F(0)")
        reglas = [p for p in pol["politicas_reloj"] if p["station_code"] == codigo]
        self.assertEqual([p["clock"]["fixed_offset_minutes"] for p in reglas], [0])
        self.assertEqual(pol["estaciones"][codigo]["tramos"], {"1.1": "F(0)"})
        self.assertIdaYVuelta(pol, casos)
        # §1.13 (RED-10, ola 4b): la red UTC cumple las predicciones de F(0) que puede medir y no las de F(−4).
        p = r.predicciones
        self.assertEqual((p["conjunto"], p["n_estaciones"], p["n_estacion_anios"]), ("N", 1, 2))
        f0 = {x["id"]: x["resultado"] for x in p["por_reloj"]["F(0)"]["predicciones"]}
        f4 = {x["id"]: x["resultado"] for x in p["por_reloj"]["F(-4)"]["predicciones"]}
        self.assertEqual((f0["E1a_presente"], f0["E3p_E4p"], f0["A3_A5_sin_alto"]), ("cumplida",) * 3)
        self.assertEqual(f4["E3p"], "predicción no cumplida")
        json.dumps(p, allow_nan=False)

    def test_p16_aerodromo_utc_insuficiente_salvo_e3t_completo_o_e6(self):
        """Sin E4p: insuficiente; confirma F(0) con E6 (FM-12) o con E3t en modo completo."""
        codigo = CASOS["aerodromo"].codigo
        r, _, _ = _red(["aerodromo"])
        d = _decisiones(r, codigo)[2019]
        self.assertVeredicto(d, Veredicto.INSUFICIENTE, motivo=MotivoAnio.APOYO)
        self.assertEqual(d.K, ("F(0)",))
        self.assertEqual(d.lineas_apoyo, ("E3p",))
        self.assertEqual(set(_anual(r, codigo, Linea.E4P).values()), {"sin_informacion"})
        self.assertEqual(r.tramos[codigo], [])
        self.assertEqual(r.estaciones[codigo]["veredicto"], "sin_confirmar")
        # Con E6 (ISD sintético, FM-12): E3p y E6.
        r6, pol6, casos6 = _red(["aerodromo"], lineas=CON_E6, isd=True)
        d6 = _decisiones(r6, codigo)[2019]
        self.assertVeredicto(d6, Veredicto.CONFIRMADO, "F(0)")
        self.assertEqual(set(d6.lineas_apoyo), {"E3p", "E6"})
        self.assertEqual([t.fixed_offset_minutes for t in r6.tramos[codigo]], [0])
        self.assertIdaYVuelta(pol6, casos6)
        # Con E3t en modo completo (calibración con 30 estación-años sin sesgo).
        rc, polc, casosc = _red_e3t_completa()
        mz = _evidencia(rc, codigo).info.macrozona
        self.assertEqual(rc.consecuencias.modo_e3t_en(mz), ModoE3t.COMPLETO)
        largo = AERODROMO_20H.codigo
        self.assertEqual(set(_anual(rc, largo, Linea.E4P).values()), {"sin_informacion"})
        d20 = _decisiones(rc, largo)[2019]
        self.assertVeredicto(d20, Veredicto.CONFIRMADO, "F(0)")
        self.assertEqual(set(d20.lineas_apoyo), {"E3p", "E3t"})
        self.assertEqual(d20.modo_e3t, ModoE3t.COMPLETO)
        self.assertIdaYVuelta(polc, casosc)
        # ORQ-10: el aeródromo de 13 h nunca tiene días con ≥ 20 valores; el filtro de §4.3.3 no pasa y E3t
        # queda sin información aun en modo completo: sigue insuficiente (lectura que pide enmienda).
        e = _evidencia(rc, codigo).estados
        e3t = e[(e["linea"] == "E3t") & (e["nivel"] == "regimen")]
        self.assertEqual(set(e3t["motivo"]), {"filtro_representatividad"})
        self.assertVeredicto(_decisiones(rc, codigo)[2019], Veredicto.INSUFICIENTE, motivo=MotivoAnio.APOYO)

    def test_p17_f_menos4_con_e2_o_e1a_y_fina(self):
        """F(−4) fija: −240 con E2 (2015, sinóptica) o con E1a (2019, automática), más la regla fina."""
        r, pol, casos = _red(["f4_e2", "f4_e1a"])
        for nombre, anio, registro in (("f4_e2", 2015, "E2"), ("f4_e1a", 2019, "E1a")):
            codigo = CASOS[nombre].codigo
            d = _decisiones(r, codigo)[anio]
            self.assertVeredicto(d, Veredicto.CONFIRMADO, "F(-4)")
            self.assertTrue({registro, "E3p"} <= set(d.lineas_apoyo), (nombre, d.lineas_apoyo))
            fina = _anual(r, codigo, Linea.E3P, "fina")
            self.assertEqual(fina[(anio, "F(-4)")], "compatible")
            self.assertEqual(fina[(anio, "F(-3)")], "incompatible")
            self.assertEqual({t.fixed_offset_minutes for t in r.tramos[codigo]}, {-240})
            self.assertEqual(r.estaciones[codigo]["reloj"], "F(-4)")
        self.assertIdaYVuelta(pol, casos)

    def test_p17_f_menos4_sin_ellas_insuficiente(self):
        """Sin E2 (automática, sin observador) ni E1a (2015, sin cambios de hora): insuficiente."""
        r, _, _ = _red(["f4_sin"])
        codigo = CASOS["f4_sin"].codigo
        d = _decisiones(r, codigo)[2015]
        self.assertVeredicto(d, Veredicto.INSUFICIENTE, motivo=MotivoAnio.APOYO)
        self.assertEqual(d.K, ("F(-4)",))
        self.assertEqual(d.lineas_apoyo, ("E3p",))
        self.assertEqual(d.clases, ("F(0)", "F(-3)|C(Santiago)", "F(-4)"))
        for linea in (Linea.E1A, Linea.E2):
            self.assertEqual(set(_anual(r, codigo, linea).values()), {"sin_informacion"}, linea)
        self.assertEqual(r.tramos[codigo], [])

    def test_p18_hora_civil_santiago_2014_2016(self):
        """Tramos −180/−240 con huecos; 2015 en −180 dentro de la misma racha; §7.3 completa (con
        ``normalizar`` y ``cargar_dmc``) sin fallas ni abortos."""
        r, pol, casos = _red(["civil"])
        codigo = CASOS["civil"].codigo
        decs = _decisiones(r, codigo)
        self.assertVeredicto(decs[2014], Veredicto.CONFIRMADO, "C(Santiago)")
        self.assertVeredicto(decs[2015], Veredicto.CONFIRMADO, "F(-3)|C(Santiago)")
        self.assertVeredicto(decs[2016], Veredicto.CONFIRMADO, "C(Santiago)")
        self.assertIn("F(-3)|C(Santiago)", [c.id for c in _evidencia(r, codigo).clases[2015]])
        rachas = r.rachas[r.rachas["codigo"] == codigo]
        self.assertEqual([(int(a), int(b), c, bool(x)) for a, b, c, x in
                          zip(rachas["anio_desde"], rachas["anio_hasta"], rachas["clase"], rachas["aceptada"])],
                         [(2014, 2016, "C(Santiago)", True)])
        esperado = [("1.1", datetime(2014, 1, 1, 0), datetime(2014, 4, 26, 22), -180),
                    ("1.2", datetime(2014, 4, 27, 0), datetime(2014, 9, 6, 23), -240),
                    ("1.3", datetime(2014, 9, 7, 1), datetime(2016, 5, 14, 22), -180),
                    ("1.4", datetime(2016, 5, 15, 0), datetime(2016, 8, 13, 23), -240),
                    ("1.5", datetime(2016, 8, 14, 1), datetime(2016, 12, 31, 23), -180)]
        self.assertEqual([(t.id, t.valid_from, t.valid_to, t.fixed_offset_minutes) for t in r.tramos[codigo]],
                         esperado)
        for especial in (datetime(2014, 4, 26, 23), datetime(2014, 9, 7, 0), datetime(2016, 5, 14, 23),
                         datetime(2016, 8, 14, 0)):
            self.assertFalse(any(t.valid_from <= especial <= t.valid_to for t in r.tramos[codigo]), especial)
        self.assertIdaYVuelta(pol, casos)
        # §7.3 sobre la política releída desde disco, con el lector real en la muestra fijada.
        adaptador, dmc_features, preflight = _codigo_fijado(self)
        d = _descarga()
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / politica.ARCHIVO_POLITICA
            politica.escribir_politica(pol, ruta)
            ctx = O.contexto_verificacion(r, pol, d["destino"], d["dmc"], adaptador=adaptador, preflight=preflight,
                                          dmc_features=dmc_features, tablas=_ESTADO["T"])
            # La civil entra en sus meses con cambio de hora y, por ser la confirmada de menor código de su
            # macrozona, con todos sus meses con regla (R-48).
            self.assertEqual(sorted(ctx.muestra_lector_real), [codigo])
            muestra = {p.name for p in ctx.muestra_lector_real[codigo]}
            self.assertTrue({f"{m}.manifest.json" for m in ("2014-04", "2014-09", "2016-05", "2016-08")} <= muestra)
            self.assertEqual(muestra, {f"{m}.manifest.json" for m in r.meses_con_regla[codigo]})
            # ORQ-12: el ``verificar`` de salidas.escribir_corrida corre §7.3 sobre la política releída de la
            # ruta y no toca el resultado (A7 y no_normalizables.csv los escribe salidas antes del informe).
            verificar = O.verificador_7_3(r, d["destino"], d["dmc"], adaptador=adaptador, preflight=preflight,
                                          dmc_features=dmc_features, tablas=_ESTADO["T"])
            fallas, no_normalizables = verificar(ruta)
            self.assertNotIn("A7", r.controles)
            # Un JSON que no se relee es una falla de §7.3 (A7), no una excepción.
            roto = Path(carpeta) / "roto.json"
            roto.write_text("{", encoding="utf-8")
            fallas_roto, _ = verificar(roto)
            # comprobar_politica (sólo pruebas) deja A7 en el resultado.
            control = O.comprobar_politica(r, roto, ctx)
        self.assertEqual(fallas, [])
        self.assertEqual(no_normalizables, [])                           # normalizar y cargar_dmc no abortan
        self.assertTrue(fallas_roto)
        self.assertTrue(all(f.startswith("comprobación ") for f in fallas_roto), fallas_roto)
        self.assertFalse(control.pasa)
        self.assertFalse(r.controles["A7"]["pasa"])

    def test_p19_presion_en_0_y_rr_en_clase_2(self):
        """QFE en F(0) y RR06 con observador en F(−4) (clase 2): E2 excluye F(0), E3p excluye F(−4)."""
        r, _, _ = _red(["p19"])
        codigo = CASOS["p19"].codigo
        d = _decisiones(r, codigo)[2019]
        self.assertVeredicto(d, Veredicto.DISCREPANTE, motivo=MotivoAnio.LINEAS_EN_CONFLICTO)
        self.assertEqual(d.K, ())
        self.assertIn("E2", d.excluidas["F(0)"])
        self.assertIn("E3p", d.excluidas["F(-4)"])
        self.assertEqual(r.tramos[codigo], [])
        self.assertEqual((r.estaciones[codigo]["veredicto"], r.estaciones[codigo]["motivo"]),
                         ("sin_confirmar", "discrepante"))

    def test_p20_cambio_f_menos4_a_f0_2018(self):
        """2018 discrepante; dos rachas aceptadas con cuarentena; reloj «F(-4)→F(0)»."""
        r, pol, casos = _red(["cambio"])
        codigo = CASOS["cambio"].codigo
        decs = _decisiones(r, codigo)
        for anio, clase in ((2016, "F(-4)"), (2017, "F(-4)"), (2019, "F(0)"), (2020, "F(0)")):
            self.assertVeredicto(decs[anio], Veredicto.CONFIRMADO, clase)
        self.assertVeredicto(decs[2018], Veredicto.DISCREPANTE)
        rachas = r.rachas[r.rachas["codigo"] == codigo]
        validar_esquema(r.rachas, ESQUEMA_RACHAS, nombre="rachas")
        self.assertEqual([(int(a), int(b), c, bool(x)) for a, b, c, x in
                          zip(rachas["anio_desde"], rachas["anio_hasta"], rachas["clase"], rachas["aceptada"])],
                         [(2016, 2017, "F(-4)", True), (2019, 2020, "F(0)", True)])
        res = r.resultados_rachas[codigo]
        self.assertEqual(res.cambios, [(2017, 2019)])
        self.assertTrue({"2017-12", "2019-01"} <= res.cuarentena)
        mcr = r.meses_con_regla[codigo]
        self.assertNotIn("2017-12", mcr)
        self.assertNotIn("2019-01", mcr)
        self.assertFalse(any(m.startswith("2018-") for m in mcr))
        self.assertEqual([(t.id, t.valid_from, t.valid_to, t.fixed_offset_minutes) for t in r.tramos[codigo]],
                         [("1.1", datetime(2016, 1, 1), datetime(2017, 11, 30, 23), -240),
                          ("2.1", datetime(2019, 2, 1), datetime(2020, 12, 31, 23), 0)])
        self.assertEqual(r.estaciones[codigo]["reloj"], "F(-4)→F(0)")
        self.assertEqual(pol["estaciones"][codigo]["reloj"], "F(-4)→F(0)")
        self.assertIdaYVuelta(pol, casos)

    def test_p20_dos_rachas_del_mismo_reloj_no_son_un_cambio(self):
        """§5.3.3 y R-25: F(0) en 2016-2020 con dos partes en −4 en 2018. 2018 queda discrepante y corta la
        racha, pero no hay cambio de reloj: el «reloj» de la estación es «F(0)», no «F(0)→F(0)»."""
        reloj = "F(0);F(-4)@2018-03-01T00:00Z;F(0)@2018-04-01T00:00Z;F(-4)@2018-10-01T00:00Z;F(0)@2018-11-01T00:00Z"
        caso = S.caso_simple("902003", reloj, "b", anios=(2016, 2020))
        r, pol, casos = _red(memoria=(caso,))
        decs = _decisiones(r, caso.codigo)
        self.assertVeredicto(decs[2018], Veredicto.DISCREPANTE)
        rachas = r.rachas[r.rachas["codigo"] == caso.codigo]
        self.assertEqual([(int(a), int(b), c, bool(x)) for a, b, c, x in
                          zip(rachas["anio_desde"], rachas["anio_hasta"], rachas["clase"], rachas["aceptada"])],
                         [(2016, 2017, "F(0)", True), (2019, 2020, "F(0)", True)])
        self.assertEqual(r.resultados_rachas[caso.codigo].cambios, [])
        self.assertEqual({t.id.split(".")[0] for t in r.tramos[caso.codigo]}, {"1", "2"})
        self.assertEqual(r.estaciones[caso.codigo]["reloj"], "F(0)")
        self.assertEqual(pol["estaciones"][caso.codigo]["reloj"], "F(0)")
        self.assertIdaYVuelta(pol, casos)

    def test_reloj_de_estacion_por_interseccion(self):
        """ORQ-7: rachas consecutivas con intersección no vacía van en un término, con su intersección;
        «→» sólo entre relojes de intersección vacía."""
        def tabla(*clases):
            return pd.DataFrame({"racha": list(range(1, len(clases) + 1)), "clase": list(clases)})

        def tramos(*rachas):
            return [Tramo(codigo="909001", id=f"{n}.1", valid_from=datetime(2019, 1, 1),
                          valid_to=datetime(2019, 1, 1), fixed_offset_minutes=0, clase="F(0)", meses=("2019-01",))
                    for n in rachas]
        self.assertEqual(O._reloj_de_estacion(tabla("F(0)", "F(0)"), tramos(1, 2)), "F(0)")
        self.assertEqual(O._reloj_de_estacion(tabla("F(-3)|C(Santiago)", "C(Santiago)"), tramos(1, 2)),
                         "C(Santiago)")
        self.assertEqual(O._reloj_de_estacion(tabla("F(-4)", "F(0)"), tramos(1, 2)), "F(-4)→F(0)")
        self.assertEqual(O._reloj_de_estacion(tabla("F(-4)", "F(0)", "F(0)"), tramos(1, 2, 3)), "F(-4)→F(0)")
        self.assertEqual(O._reloj_de_estacion(tabla("F(-4)", "F(0)"), tramos(2)), "F(0)")     # sólo con tramos

    def test_p21_parte_menos4_en_anio_utc(self):
        """§8.21 con la Enmienda 3 (opción R de E3-2; LF-17): un año UTC con una parte con −4 (marzo).
        - Sin E6: el año-régimen de marzo deja a F(0) residual y da compatible o incompatible a las rivales, así
          que cuenta para F(0) en E3p anual (informativo por año-régimen) y E3p ya no apoya: el año queda
          insuficiente y ningún mes tiene regla.
        - Con E6 (FM-12 sintético): F(0) se confirma con E4p y E6, y marzo queda sin regla.
        - Con dos partes (marzo y noviembre): el año queda discrepante, con o sin E6."""
        r, pol, casos = _red(["parte1", "parte2"])
        una = CASOS["parte1"].codigo
        d = _decisiones(r, una)[2019]
        self.assertVeredicto(d, Veredicto.INSUFICIENTE, motivo=MotivoAnio.APOYO)
        self.assertNotIn("E3p", d.lineas_apoyo)                          # E3p anual ya no es compatible con F(0)
        self.assertEqual(r.meses_con_regla[una], {})
        self.assertEqual(r.tramos[una], [])
        dos = _decisiones(r, CASOS["parte2"].codigo)[2019]
        self.assertVeredicto(dos, Veredicto.DISCREPANTE)
        self.assertIn("E2", dos.excluidas["F(0)"])
        self.assertIdaYVuelta(pol, casos)
        r6, pol6, casos6 = _red(["parte1", "parte2"], lineas=CON_E6, isd=True)
        d6 = _decisiones(r6, una)[2019]
        self.assertVeredicto(d6, Veredicto.CONFIRMADO, "F(0)")
        self.assertEqual(set(d6.lineas_apoyo), {"E4p", "E6"})
        self.assertVeredicto(_decisiones(r6, CASOS["parte2"].codigo)[2019], Veredicto.DISCREPANTE)
        mcr = r6.meses_con_regla[una]
        self.assertNotIn("2019-03", mcr)
        self.assertTrue({"2019-02", "2019-04", "2019-12"} <= set(mcr))
        self.assertEqual([(t.valid_from, t.valid_to) for t in r6.tramos[una]],
                         [(datetime(2019, 1, 1), datetime(2019, 2, 28, 23)),
                          (datetime(2019, 4, 1), datetime(2019, 12, 31, 23))])
        self.assertIdaYVuelta(pol6, casos6)

    def test_p22_sesgo_termico_2_5h(self):
        """Sesgo de la referencia +2,5 h: la calibración (con ≥ 30 estación-años) deja E3t restringida y
        ninguna estación sólo térmica se confirma."""
        r, _, _ = _red(["termica"], memoria=CALIBRACION, sesgo=2.5)
        codigo = CASOS["termica"].codigo
        mz = _evidencia(r, codigo).info.macrozona
        resumen = r.controles["calibracion_e3t"]["por_macrozona"][mz]
        self.assertGreaterEqual(resumen["n"], _ESTADO["U"].f("CAL_E3T_MIN"))
        self.assertGreater(resumen["frac_fuera"], _ESTADO["U"].frac("CAL_E3T_PCT"))
        self.assertEqual(resumen["modo"], "restringido")
        self.assertEqual(r.consecuencias.modo_e3t_en(mz), ModoE3t.RESTRINGIDO)
        solo_ts = [ev.info.codigo for ev in r.evidencias
                   if not (ev.metricas_e3["variable"] == "QFE").any() and len(ev.metricas_e3)]
        self.assertEqual(solo_ts, [codigo])
        for d in r.decisiones:
            if d.codigo in solo_ts:
                self.assertNotEqual(d.veredicto, Veredicto.CONFIRMADO, d)
        self.assertEqual(r.tramos[codigo], [])

    def test_p23_pascua_utc_sin_pixel(self):
        """Mataveri en UTC con el calendario propio, sin píxel: sin E6, insuficiente (sólo E4p separa de
        F(−3)); con E6 FM-12 sintético, F(0)."""
        codigo = CASOS["pascua"].codigo
        r, _, _ = _red(["pascua"])
        info = _evidencia(r, codigo).info
        self.assertIsNone(info.pixel_id)
        self.assertEqual(len(info.P), 7)
        d = _decisiones(r, codigo)[2019]
        self.assertVeredicto(d, Veredicto.INSUFICIENTE, motivo=MotivoAnio.APOYO)
        self.assertEqual(d.lineas_apoyo, ("E4p",))
        self.assertEqual(set(_anual(r, codigo, Linea.E3T).values()), {"sin_informacion"})
        r6, pol6, casos6 = _red(["pascua"], lineas=CON_E6, isd=True)
        d6 = _decisiones(r6, codigo)[2019]
        self.assertVeredicto(d6, Veredicto.CONFIRMADO, "F(0)")
        self.assertEqual(set(d6.lineas_apoyo), {"E4p", "E6"})
        self.assertEqual([t.fixed_offset_minutes for t in r6.tramos[codigo]], [0])
        self.assertIdaYVuelta(pol6, casos6)


def _codigo_fijado(caso: unittest.TestCase):
    """(adaptador, dmc_features, preflight_v3) fijados; restituye los hilos que fija runner_v3."""
    rutas = (AP / fijados.RUTA_ADAPTADOR, AP / fijados.RUTA_DMC_FEATURES, AP / fijados.RUTA_PREFLIGHT_V3)
    faltan = [r.name for r in rutas if not r.is_file()]
    if faltan:
        caso.skipTest(f"falta el código fijado: {', '.join(faltan)}")
    if "fijados" not in _ESTADO:
        hilos = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                 "NUMEXPR_NUM_THREADS")
        antes = {v: os.environ.get(v) for v in hilos}
        import pyarrow as pa
        cpu, io = pa.cpu_count(), pa.io_thread_count()
        try:
            adaptador = fijados.cargar_adaptador(AP)
            preflight = fijados.cargar_preflight(AP)
            dmc_features = sys.modules[fijados.MODULO_DMC_FEATURES]
        finally:
            for v, valor in antes.items():
                if valor is None:
                    os.environ.pop(v, None)
                else:
                    os.environ[v] = valor
            pa.set_cpu_count(cpu)
            pa.set_io_thread_count(io)
        _ESTADO["fijados"] = (adaptador, dmc_features, preflight)
    return _ESTADO["fijados"]


# ---------------------------------------------------------------------------------------------
# Pipeline de §5.2
# ---------------------------------------------------------------------------------------------
class PruebasPipeline(_Base):
    def test_orden_de_5_2_y_una_sola_decision(self):
        """La decisión se calcula una vez, tras A3, A5 y la calibración; A4 entre los pasos 6 y 7; el
        avance sólo recibe conteos."""
        eventos: list[tuple[str, object]] = []

        def espiar(modulo, nombre, clave=None):
            original = getattr(modulo, nombre)

            def envoltura(*a, **k):
                eventos.append((nombre, clave(*a) if clave else None))
                return original(*a, **k)
            return mock.patch.object(modulo, nombre, envoltura)

        avances: list[tuple] = []
        casos = (S.caso_simple("903001", "F(0)", "a", anios=(2019, 2019)),
                 S.caso_simple("903002", "C(America/Santiago)", "b", anios=(2018, 2019)))
        with espiar(red, "controles_red"), espiar(red, "a4"), espiar(red, "fijar_a4"), \
                espiar(decision, "pasos_1_a_6", lambda ins, *_: (ins.codigo, ins.anio)), \
                espiar(decision, "pasos_7_a_9", lambda p, *_: (p.codigo, p.anio)), \
                espiar(decision, "rachas"), espiar(politica, "tramos"), espiar(decision, "decidir_anio"):
            serie = S.serie_era5_de_casos(casos)
            with tempfile.TemporaryDirectory() as carpeta:
                _, infos = _infos(casos, serie, Path(carpeta))
            entradas = [O.EntradaEstacion(infos[c.codigo], *S.entrada_en_memoria(c)) for c in casos]
            r = O.evaluar_red(lambda: entradas, serie, _ESTADO["T"], _ESTADO["U"], O.OpcionesCorrida(),
                              avance=lambda *a: avances.append(a))
        nombres = [n for n, _ in eventos]
        self.assertNotIn("decidir_anio", nombres)
        self.assertEqual(nombres.count("controles_red"), 1)
        self.assertEqual(nombres.count("a4"), 1)
        primero = {n: nombres.index(n) for n in set(nombres)}
        ultimo = {n: len(nombres) - 1 - nombres[::-1].index(n) for n in set(nombres)}
        self.assertLess(primero["controles_red"], primero["pasos_1_a_6"])
        self.assertLess(ultimo["pasos_1_a_6"], primero["a4"])
        self.assertEqual(primero["fijar_a4"], primero["a4"] + 1)
        self.assertLess(primero["fijar_a4"], primero["pasos_7_a_9"])
        self.assertLess(ultimo["pasos_7_a_9"], primero["rachas"])
        self.assertLess(ultimo["rachas"], primero["tramos"])
        anios = [k for n, k in eventos if n == "pasos_1_a_6"]
        self.assertEqual(sorted(anios), [("903001", 2019), ("903002", 2018), ("903002", 2019)])
        # Una decisión por estación-año, y otra sólo para la comparación con E3t restringida (ORQ-4).
        self.assertEqual(sorted(k for n, k in eventos if n == "pasos_7_a_9"), sorted(anios * 2))
        self.assertEqual(len(r.decisiones), len(anios))
        self.assertEqual(len(r.decisiones_e3t_restringida), len(anios))
        # Sin veredictos a la vista: (fase, hechos, total) con conteos enteros y fases conocidas.
        self.assertTrue(avances)
        for fase, hechos, total in avances:
            self.assertIn(fase, O.FASES)
            self.assertIsInstance(hechos, int)
            self.assertIsInstance(total, int)
        self.assertEqual([f for f in dict.fromkeys(f for f, _, _ in avances)],
                         [f for f in O.FASES if f in {a[0] for a in avances}])
        # ORQ-11: la segunda pasada cuenta cada estación leída, se diagnostique o no.
        self.assertEqual([(h, t) for f, h, t in avances if f == "segunda_pasada"], [(1, 2), (2, 2)])
        for ev in r.evidencias:
            for tabla, esquema in ((ev.estados, ESQUEMA_ESTADOS), (ev.eventos, ESQUEMA_EVENTOS),
                                   (ev.guardas, ESQUEMA_GUARDAS), (ev.marcas, ESQUEMA_MARCAS),
                                   (ev.horas, ESQUEMA_HORAS)):
                validar_esquema(tabla, esquema, nombre=ev.info.codigo)
            self.assertEqual(sorted(ev.clases), sorted({d.anio for d in r.decisiones if d.codigo == ev.info.codigo}))
        self.assertGreater(r.tiempos["estacion_anios"], 0)

    def test_comparacion_e3t_restringida(self):
        """Se informa la decisión que habría resultado con E3t restringida en todas las macrozonas."""
        r, _, _ = _red_e3t_completa()
        restringidas = {(d.codigo, d.anio): d for d in r.decisiones_e3t_restringida}
        self.assertEqual(len(restringidas), len(r.decisiones_e3t_restringida))      # una por estación-año
        self.assertEqual(set(restringidas), {(d.codigo, d.anio) for d in r.decisiones})
        largo = (AERODROMO_20H.codigo, 2019)
        self.assertEqual(restringidas[largo].veredicto, Veredicto.INSUFICIENTE)
        self.assertEqual(restringidas[largo].motivo, MotivoAnio.APOYO)
        self.assertEqual(restringidas[largo].modo_e3t, ModoE3t.RESTRINGIDO)
        distintas = r.controles["comparacion_e3t_restringida"]["distintas"]
        self.assertIn({"codigo": largo[0], "anio": 2019, "veredicto": "confirmado",
                       "veredicto_e3t_restringida": "insuficiente", "clase": "F(0)", "clase_e3t_restringida": None},
                      distintas)
        calibracion = {c.codigo for c in CALIBRACION}
        self.assertFalse([x for x in distintas if x["codigo"] in calibracion])     # E3p y E4p bastan

    def test_comparacion_e3t_restringida_no_mide_a6(self):
        """ORQ-4 y ORQ-5: A6 se aplica también a la decisión con E3t restringida. Un D1 que contradice un
        F(0) confirmado deja las dos sin confirmar, y la diferencia de A6 no aparece como si fuera de E3t."""
        caso = S.caso_simple("907101", "F(0)", "a", anios=(2019, 2019))
        d1 = {"id": "DOC-PRUEBA", "nivel": "D1", "estado": "verificado", "cita_literal": "Hora en UTC−4",
              "reloj_declarado": "F(-4)", "alcance": {"estaciones": [caso.codigo]}}
        serie = S.serie_era5_de_casos([caso])
        with tempfile.TemporaryDirectory() as carpeta:
            _, infos = _infos([caso], serie, Path(carpeta))
        entradas = [O.EntradaEstacion(infos[caso.codigo], *S.entrada_en_memoria(caso))]
        r = O.evaluar_red(lambda: entradas, serie, _ESTADO["T"], _ESTADO["U"], O.OpcionesCorrida(),
                          registro_documental=(d1,))
        final = _decisiones(r, caso.codigo)[2019]
        restringida = {d.anio: d for d in r.decisiones_e3t_restringida if d.codigo == caso.codigo}[2019]
        for d in (final, restringida):
            self.assertEqual((d.veredicto, d.motivo, d.clase_confirmada),
                             (Veredicto.SIN_CONFIRMAR, MotivoAnio.DOCUMENTAL_A6, "F(0)"))
        self.assertEqual(r.controles["A6"]["contrarios"], [[caso.codigo, 2019]])
        self.assertEqual(r.controles["comparacion_e3t_restringida"]["distintas"], [])

    def test_ida_y_vuelta_en_todo_caso_de_b_a_e(self):
        """R-34: casos de las líneas (grupo B: relojes de P en sus sitios, el S1 local de 2 hPa de B.12 y el
        paso de 3 h de B.13) pasan por el pipeline con E6, cada uno con su veredicto esperado, y su política
        vuelve a dar u (sintetico.comprobar_ida_y_vuelta vacío). Los del grupo C lo comprueban en sus
        pruebas; D y E, en la batería y en C3. El aeródromo con cambio administrativo (tipo d) va aparte."""
        def paso_3h(extracto):
            return extracto[extracto["L"].dt.hour % 3 == 0].reset_index(drop=True)
        s1_local = {"s1_local_amplitud": 2.0, "s1_local_desfase": 4.0}
        esperados = {   # código → (caso, veredicto, clase confirmada)
            "904001": (S.caso_simple("904001", "F(0)", "a"), Veredicto.CONFIRMADO, "F(0)"),
            "904002": (S.caso_simple("904002", "F(-3)", "b"), Veredicto.CONFIRMADO, "F(-3)"),
            "904003": (S.caso_simple("904003", "F(-4)", "b"), Veredicto.CONFIRMADO, "F(-4)"),
            "904004": (S.caso_simple("904004", "C(America/Santiago)", "a"), Veredicto.CONFIRMADO, "C(Santiago)"),
            "904005": (S.caso_simple("904005", "C(America/Santiago)", "b"), Veredicto.CONFIRMADO, "C(Santiago)"),
            # §6, series cada 6 h: E4p sin información y E2 no separa F(0) de F(−3); sólo E6 apoya.
            "904006": (S.caso_simple("904006", "F(0)", "f"), Veredicto.INSUFICIENTE, None),
            "904007": (S.caso_simple("904007", "F(-4)", "c"), Veredicto.CONFIRMADO, "F(-4)"),
            "904009": (S.caso_simple("904009", "C(America/Punta_Arenas)", "b", sitio="punta_arenas"),
                       Veredicto.CONFIRMADO, "F(-3)|C(Punta_Arenas)"),
            "904010": (S.caso_simple("904010", "C(America/Coyhaique)", "b", sitio="coyhaique"),
                       Veredicto.CONFIRMADO, "C(Santiago)|C(Coyhaique)"),
            "904011": (S.caso_simple("904011", "C(Pacific/Easter)", "b", sitio="pascua"),
                       Veredicto.CONFIRMADO, "C(Pacific/Easter)"),
            # B.12: S1 local de 2 hPa desfasado 4 h; la regla fina separa C(Santiago) de F(−4).
            "904012": (S.caso_simple("904012", "C(America/Santiago)", "b", perturbaciones=s1_local),
                       Veredicto.CONFIRMADO, "C(Santiago)"),
            # B.13: paso nativo de 3 h (E3 y E4 con su paso).
            "904014": (S.caso_simple("904014", "F(0)", "b"), Veredicto.CONFIRMADO, "F(0)"),
            "904015": (S.caso_simple("904015", "F(-3)", "b"), Veredicto.CONFIRMADO, "F(-3)"),
            "904016": (S.caso_simple("904016", "C(America/Santiago)", "b"), Veredicto.CONFIRMADO, "C(Santiago)"),
        }
        casos = tuple(c for c, _, _ in esperados.values())
        r, pol, _ = _red(memoria=casos, lineas=CON_E6, isd=True,
                         transformar={c: paso_3h for c in ("904014", "904015", "904016")})
        for codigo, (_, veredicto, clase) in esperados.items():
            with self.subTest(codigo=codigo):
                self.assertVeredicto(_decisiones(r, codigo)[2019], veredicto, clase)
                self.assertEqual(bool(r.tramos[codigo]), veredicto == Veredicto.CONFIRMADO)
        fina = _anual(r, "904012", Linea.E3P, "fina")
        self.assertEqual((fina[(2019, "C(Santiago)")], fina[(2019, "F(-4)")]), ("compatible", "incompatible"))
        for codigo in ("904014", "904015", "904016"):
            m = _evidencia(r, codigo).metricas_e4
            self.assertEqual(set(m.loc[m["variable"] == "QFE", "paso_h"].dropna().astype(int)), {3}, codigo)
        self.assertEqual(r.controles["reglas_vencidas"]["lineas_sin_cv"], ["E6"])          # ORQ-3f
        self.assertIdaYVuelta(pol, casos)

    def test_ida_y_vuelta_aerodromo_tipo_d(self):
        """C(Santiago) en un aeródromo con cambio administrativo de horario (tipo d; la ventana pasa de 08-20 h a
        09-21 h el 2016-07-01), 2016-2018. Con el texto v1.0.2 2016 quedaba discrepante por «líneas en
        conflicto»: un solo armónico de sp corría ĉ^f en la ventana diurna y la regla fina de R1 excluía al
        reloj verdadero. Con la Enmienda 3:
        - E3-1 (armónico de sp para cada c, §4.3.1; LF-2): ningún año discrepante y ninguna exclusión del reloj
          verdadero; 2018 se confirma C(Santiago) y la ida y vuelta pasa;
        - R (LF-17), su costo en los aeródromos: en 2016 y 2017 R1 es corto (≈ 1.090 pares) y no es fino
          (|ĉ^f_cont − ĉ^f| ≈ 0,3 h), su gruesa da F(0) incompatible y deja residual a C(Santiago), así que
          cuenta para C(Santiago) y E3p no apoya: esos dos años quedan insuficientes («apoyo»)."""
        caso = S.caso_simple("904008", "C(America/Santiago)", "d", anios=(2016, 2018))
        r, pol, casos = _red(memoria=(caso,))
        decs = _decisiones(r, caso.codigo)
        for anio in (2016, 2017):
            self.assertVeredicto(decs[anio], Veredicto.INSUFICIENTE, motivo=MotivoAnio.APOYO)
            self.assertNotIn("E3p", decs[anio].lineas_apoyo)
        self.assertVeredicto(decs[2018], Veredicto.CONFIRMADO, "C(Santiago)")
        for d in decs.values():                                   # nadie excluye al reloj verdadero
            self.assertEqual([c for c in d.excluidas if "C(Santiago)" in c.split("|")], [], d.anio)
        self.assertFalse(r.resultados_rachas[caso.codigo].inestable)
        self.assertIdaYVuelta(pol, casos)

    def test_b6_marca_de_media_horaria_con_un_solo_anio_confirmado(self):
        """Enmienda 3, B6 (§4.3.5; LF-18). Semántica de −0,5 h en una automática F(0), 2010-2014: se confirma un
        solo año (2012), con el reloj entero verdadero. Con el texto v1.0.2, ρ usaba sólo los años-régimen de
        los años confirmados (2 < 6) y la estación no podía llevar la marca «posible media horaria», que §8.D
        exige para contarla como correcta (la causa estructural de BAT-6). Con B6 ρ es la media circular de
        período 1 h de ĉ^f_cont en todos sus años-régimen, cerca de ±0,5 h, y la estación lleva la marca."""
        caso = S.caso_simple("906002", "F(0)", "a", anios=(2010, 2014), perturbaciones={"semantica": -0.5},
                             replica=1, semilla=2)
        r, pol, casos = _red(memoria=(caso,))
        decs = _decisiones(r, caso.codigo)
        confirmados = [a for a, d in decs.items() if d.veredicto == Veredicto.CONFIRMADO]
        self.assertEqual(confirmados, [2012])
        self.assertVeredicto(decs[2012], Veredicto.CONFIRMADO, "F(0)")
        U = _ESTADO["U"]
        m = _evidencia(r, caso.codigo).metricas_e3
        regimenes = m[(m["variable"] == "QFE") & (m["nivel"] == "regimen") & m["c_hat_f_cont"].notna()]
        self.assertLess(int((regimenes["anio"] == 2012).sum()), U.f("SUBH_MIN_REGIMENES"))   # v1.0.2: sin marca
        self.assertGreaterEqual(len(regimenes), U.f("SUBH_MIN_REGIMENES"))
        self.assertTrue(r.estaciones[caso.codigo]["marcas"]["posible_media_horaria"])
        self.assertIdaYVuelta(pol, casos)

    def test_reglas_vencidas_diagnostico_sin_marca_y_patron_de_regla_vencida(self):
        """§4.1.4 con E1-4 (ORQ-3): hora civil con la regla anterior (Mar/Oct, domingo ≥ 9) en 2011-2013.
        2011 y 2012 son años del Anexo A2 y se diagnostican; 2013 no está en el anexo.
        Enmienda 3, E3-2 (opción A′; ORQ-13). Los adelantos de octubre de esa regla (2011-10-09, 2012-10-14 y
        2013-10-13), eventos de regla vencida de «octubre, domingo ≥ 9», quedan ausentes y forman el patrón de
        regla vencida: E1a señala reloj anómalo en los tres años. Con «las mismas reglas», ese reloj anómalo
        sigue en P ∪ {Cv}, así que el diagnóstico no pone la marca (con el texto v1.0.2, 2011 y 2012 la
        llevaban y la estación no quedaba inestable: la fila de §5.5 «no cuenta para la inestabilidad», que
        la enmienda reescribe), y la estación queda inestable por la tercera condición de §5.3, punto 1. El
        resto del diagnóstico no cambia. Sin el diagnóstico, la estación queda inestable igual."""
        from reloj_dmc import decision as mod_decision
        caso = S.caso_simple("905001", "Cv(America/Santiago)", "b", anios=(2011, 2013))
        r, _, _ = _red(memoria=(caso,))
        decs = _decisiones(r, caso.codigo)
        for anio in (2011, 2012, 2013):
            self.assertVeredicto(decs[anio], Veredicto.DISCREPANTE)
            self.assertEqual(decs[anio].motivo, MotivoAnio.RELOJ_ANOMALO, anio)
        self.assertEqual([decs[a].reglas_vencidas for a in (2011, 2012, 2013)], [False, False, False])
        self.assertEqual(r.controles["reglas_vencidas"]["diagnosticados"], {caso.codigo: [2011, 2012]})
        self.assertEqual(r.controles["reglas_vencidas"]["con_marca"], [])
        self.assertEqual(r.controles["reglas_vencidas"]["lineas_sin_cv"], [])        # C0: sin E6 (ORQ-3f)
        self.assertTrue(r.resultados_rachas[caso.codigo].inestable)
        self.assertIn(mod_decision.MOTIVO_INESTABLE_REGLAS_VENCIDAS, r.resultados_rachas[caso.codigo].motivos_inestable)
        e = r.estados_reglas_vencidas
        validar_esquema(e, ESQUEMA_ESTADOS, nombre="estados con Cv")
        e2 = e[(e["linea"] == "E2") & (e["nivel"] == "anio") & (e["anio"] == 2011)]
        self.assertEqual(dict(zip(e2["H"], e2["estado"])),
                         {"F(0)": "incompatible", "F(-3)": "incompatible", "F(-4)": "incompatible",
                          "C(Santiago)": "incompatible", "Cv(Santiago)": "compatible"})
        cv = e[(e["H"] == "Cv(Santiago)") & (e["nivel"] == "anio")]
        self.assertEqual(sorted(set(cv["linea"])), ["E1a", "E1b", "E1c", "E2", "E3p", "E3t", "E4p"])
        self.assertFalse((cv["estado"] == "incompatible").any(), cv)
        sin = O.OpcionesCorrida(diagnostico_reglas_vencidas=False)
        r0, _, _ = _red(memoria=(caso,), opciones=sin)
        self.assertFalse(any(d.reglas_vencidas for d in r0.decisiones))
        self.assertTrue(r0.resultados_rachas[caso.codigo].inestable)
        self.assertEqual(r0.estaciones[caso.codigo]["motivo"], "inestable")

    def test_partes_cortadas_en_las_etiquetas_de_cv(self):
        """ORQ-3b: con Cv(Santiago, 2016) se corta también en la 23:00 repetida del 2016-04-23 y en la
        00:00 inexistente del 2016-09-04 (las del Anexo A2), que quedan especiales."""
        T = _ESTADO["T"]
        cv = Hipotesis("Cv", None, "America/Santiago")
        calendario = T.con_cortes_reglas_vencidas([cv.zona], [2016])      # interfaz pública de tablas (ola 4b)
        cortes = {cv.zona: [O._intervalo_especial(c) for c in T.cambios_reglas_vencidas(cv.zona, 2016)]}
        de_orquestacion = O._CalendarioConCortes(T, cortes)                # el nombre de la ola 4a la usa
        caso = S.caso_simple("905002", "F(-4)", "a", anios=(2016, 2016))
        extracto, _ = S.entrada_en_memoria(caso)
        serie = S.serie_era5_de_casos([caso])
        with tempfile.TemporaryDirectory() as carpeta:
            _, infos = _infos([caso], serie, Path(carpeta))
        info = infos[caso.codigo]
        normal = tablas.anotar_partes(extracto, info, T)
        cortado = tablas.anotar_partes(extracto, info, calendario)
        pd.testing.assert_frame_equal(tablas.anotar_partes(extracto, info, de_orquestacion), cortado)
        L = cortado["L"]

        def fila(t):
            return cortado.loc[L == pd.Timestamp(t)].iloc[0]
        for especial in ("2016-04-23 23:00", "2016-09-04 00:00"):
            self.assertTrue(bool(fila(especial)["especial"]), especial)
        self.assertEqual(fila("2016-04-23 22:00")["parte"], "2016-04-1")
        self.assertEqual(fila("2016-04-24 00:00")["parte"], "2016-04-2")
        self.assertEqual(fila("2016-09-04 01:00")["parte"], "2016-09-2")
        self.assertEqual(fila("2016-09-04 01:00")["regimen"], fila("2016-09-03 23:00")["regimen"])
        # Fuera de los cortes la anotación no cambia, y los años-régimen son los de Zs.
        iguales = ~cortado["especial"].to_numpy() & ~L.dt.month.isin([4, 9]).to_numpy()
        self.assertTrue((cortado.loc[iguales, "parte"] == normal.loc[iguales, "parte"]).all())
        self.assertEqual(tablas.regimenes_del_anio(info.zs, 2016, calendario),
                         tablas.regimenes_del_anio(info.zs, 2016, T))
        with self.assertRaises(ValueError):
            O.diagnostico_reglas_vencidas(O.EntradaEstacion(info, extracto, S.entrada_en_memoria(caso)[1]), serie,
                                          2017, T, _ESTADO["U"], O.OpcionesCorrida())

    def test_entradas_desde_extraccion_marca_coordenadas_inconsistentes(self):
        """Después de extraer_dmc: §3.1 con los textos de los artefactos evaluados, y una fábrica que lee
        un extracto a la vez."""
        d = _descarga()
        casos = list(CASOS.values())
        serie = S.serie_era5_de_casos(casos)
        with tempfile.TemporaryDirectory() as carpeta:
            catalogo, infos = _infos(casos, serie, Path(carpeta))
        marcadas, fabrica = O.entradas_desde_extraccion(d["destino"], catalogo, infos, _ESTADO["U"])
        self.assertFalse(any(i.coordenadas_inconsistentes for i in marcadas.values()))
        entradas = list(fabrica())
        self.assertEqual([e.info.codigo for e in entradas], sorted(c.codigo for c in casos))
        for e in entradas:
            self.assertEqual(set(e.meses["codigo"]), {e.info.codigo})
            self.assertEqual(len(e.extracto), int(e.meses.loc[e.meses["entra"], "row_count"].sum()))
        # Un catálogo cuya latitud difiere en más de 0,0005° de la de los artefactos marca la estación.
        movido = catalogo.copy()
        codigo = CASOS["utc"].codigo
        movido.loc[movido["codigo"] == codigo, "lat_txt"] = "-33.41"
        marcadas, _ = O.entradas_desde_extraccion(d["destino"], movido, infos, _ESTADO["U"])
        self.assertTrue(marcadas[codigo].coordenadas_inconsistentes)
        self.assertFalse(marcadas[CASOS["civil"].codigo].coordenadas_inconsistentes)

    def test_politica_y_opciones(self):
        """Sin política con A5 alto (§5.4); el remuestreo de §4.0 no es opcional."""
        r, pol, _ = _red(memoria=(S.caso_simple("906001", "F(0)", "a", anios=(2019, 2019)),))
        self.assertIsNotNone(pol)
        self.assertEqual(O.politica_de(r, _huellas()), pol)
        alto = replace(r, consecuencias=replace(r.consecuencias, a5_alto=True))
        self.assertIsNone(O.politica_de(alto, _huellas()))
        self.assertTrue(alto.tramos["906001"])                          # los tramos sí van al informe
        with self.assertRaises(ValueError):
            O.evaluar_red(lambda: [], None, _ESTADO["T"], _ESTADO["U"], O.OpcionesCorrida(remuestreo=False))
        self.assertTrue(np.isfinite(r.tiempos["por_estacion_anio"]))
        vacia = O.evaluar_red(lambda: [], None, _ESTADO["T"], _ESTADO["U"], O.OpcionesCorrida())
        self.assertIsNone(vacia.tiempos["por_estacion_anio"])            # el informe es JSON sin NaN
        self.assertEqual((vacia.decisiones, dict(vacia.tramos)), ([], {}))
        # La segunda pasada (etiquetas de los tramos) exige que la fábrica vuelva a dar la estación; con
        # ``conservar_etiquetas`` no hace falta y el resultado es el mismo.
        caso = S.caso_simple("906001", "F(0)", "a", anios=(2019, 2019))
        serie = S.serie_era5_de_casos([caso])
        with tempfile.TemporaryDirectory() as carpeta:
            _, infos = _infos([caso], serie, Path(carpeta))
        entrada = O.EntradaEstacion(infos[caso.codigo], *S.entrada_en_memoria(caso))
        llamadas = []

        def una_vez():
            llamadas.append(1)
            return [entrada] if len(llamadas) == 1 else []
        # El diagnóstico de reglas vencidas también pide la segunda pasada, aunque nada quede discrepante
        # (ORQ-11), y su error da sólo conteos, nunca códigos.
        for opciones in (O.OpcionesCorrida(), O.OpcionesCorrida(conservar_etiquetas=True)):
            llamadas.clear()
            with self.assertRaises(ValueError) as error:
                O.evaluar_red(una_vez, serie, _ESTADO["T"], _ESTADO["U"], opciones)
            self.assertEqual(len(llamadas), 2)
            self.assertNotIn(caso.codigo, str(error.exception))
        llamadas.clear()
        conservadas = O.evaluar_red(una_vez, serie, _ESTADO["T"], _ESTADO["U"],
                                    O.OpcionesCorrida(conservar_etiquetas=True, diagnostico_reglas_vencidas=False))
        self.assertEqual(len(llamadas), 1)
        self.assertEqual(conservadas.tramos, r.tramos)


class PruebasCeguera(_Base):
    def test_avance_no_depende_de_los_veredictos(self):
        """§5.2, «Sin veredictos a la vista» (ORQ-11): dos redes de la misma forma (dos estaciones, 2011),
        una con la estación civil en la regla anterior (2011 discrepante y diagnosticado por reglas
        vencidas) y otra con la regla vigente (confirmado), dan el mismo avance."""
        flujos, veredictos = [], []
        for reloj in ("Cv(America/Santiago)", "C(America/Santiago)"):
            casos = (S.caso_simple("907001", reloj, "b", anios=(2011, 2011)),
                     S.caso_simple("907002", "F(0)", "a", anios=(2011, 2011)))
            serie = S.serie_era5_de_casos(casos)
            with tempfile.TemporaryDirectory() as carpeta:
                _, infos = _infos(casos, serie, Path(carpeta))
            entradas = [O.EntradaEstacion(infos[c.codigo], *S.entrada_en_memoria(c)) for c in casos]
            llamadas: list[tuple] = []
            r = O.evaluar_red(lambda: entradas, serie, _ESTADO["T"], _ESTADO["U"], O.OpcionesCorrida(),
                              avance=lambda *a: llamadas.append(a))
            flujos.append(llamadas)
            veredictos.append((_decisiones(r, "907001")[2011].veredicto, r.controles["reglas_vencidas"]))
        (con_cv, rv_cv), (vigente, rv_vigente) = veredictos
        self.assertEqual((con_cv, rv_cv["diagnosticados"]), (Veredicto.DISCREPANTE, {"907001": [2011]}))
        self.assertEqual((vigente, rv_vigente["diagnosticados"]), (Veredicto.CONFIRMADO, {}))
        self.assertEqual(flujos[0], flujos[1])
        self.assertIn(("segunda_pasada", 2, 2), flujos[0])


def _filas(anio, linea, regla, nivel, unidad, por_h, motivo=None):
    return pd.DataFrame([{"codigo": "907201", "anio": anio, "linea": str(linea), "regla": str(regla),
                          "nivel": str(nivel), "unidad": unidad, "H": h, "estado": str(e), "reloj_anomalo": False,
                          "discordante": False, "motivo": motivo} for h, e in por_h.items()],
                        columns=list(ESQUEMA_ESTADOS)).astype(ESQUEMA_ESTADOS)


class PruebasReglaAnualDeCv(unittest.TestCase):
    """ORQ-3d: las filas anuales de Cv salen de la regla de cada línea. §4.3.4: «H es compatible si todos
    los años-régimen finos, y al menos uno, tienen ĉ^f = c_H(R)»; §4.4 (E4p): «compatible si lo es en todos
    los años-régimen evaluables (al menos uno)». Donde el desfase de Cv no es constante no hay c_Cv(R)."""
    CV = "Cv(Santiago)"
    R0 = {"F(0)": Estado.INCOMPATIBLE, "F(-3)": Estado.COMPATIBLE, "F(-4)": Estado.INCOMPATIBLE,
          "C(Santiago)": Estado.COMPATIBLE}
    R1 = {"F(0)": Estado.INCOMPATIBLE, "F(-3)": Estado.INCOMPATIBLE, "F(-4)": Estado.COMPATIBLE,
          "C(Santiago)": Estado.COMPATIBLE}

    def _cv(self, linea, regla, r1, motivo_r1=None):
        return pd.concat([_filas(2011, linea, regla, Nivel.REGIMEN, "R0", {self.CV: Estado.COMPATIBLE}),
                          _filas(2011, linea, regla, Nivel.REGIMEN, "R1", {self.CV: r1}, motivo_r1)],
                         ignore_index=True)

    def _anual(self, marcos):
        (anual,) = marcos
        return anual["estado"].iloc[0], anual["motivo"].iloc[0]

    def test_fina_sin_desfase_constante_en_un_regimen_fino(self):
        P = pd.concat([_filas(2011, Linea.E3P, Regla.FINA, Nivel.REGIMEN, "R0", self.R0),
                       _filas(2011, Linea.E3P, Regla.FINA, Nivel.REGIMEN, "R1", self.R1)], ignore_index=True)
        sin = self._cv(Linea.E3P, Regla.FINA, Estado.SIN_INFORMACION, O.MOTIVO_DESFASE_CV)
        self.assertEqual(self._anual(O._anual_fina(sin, P, self.CV, [2011], "907201")),
                         ("sin_informacion", O.MOTIVO_DESFASE_CV))
        con = self._cv(Linea.E3P, Regla.FINA, Estado.COMPATIBLE)
        self.assertEqual(self._anual(O._anual_fina(con, P, self.CV, [2011], "907201"))[0], "compatible")
        incompatible = self._cv(Linea.E3P, Regla.FINA, Estado.INCOMPATIBLE)
        self.assertEqual(self._anual(O._anual_fina(incompatible, P, self.CV, [2011], "907201"))[0], "incompatible")
        # Un año-régimen que no es fino (P sin información) no cuenta.
        no_fino = {h: Estado.SIN_INFORMACION for h in self.R1}
        P_r0 = pd.concat([_filas(2011, Linea.E3P, Regla.FINA, Nivel.REGIMEN, "R0", self.R0),
                          _filas(2011, Linea.E3P, Regla.FINA, Nivel.REGIMEN, "R1", no_fino, "no_fino:pares")],
                         ignore_index=True)
        self.assertEqual(self._anual(O._anual_fina(sin, P_r0, self.CV, [2011], "907201"))[0], "compatible")

    def test_e4p_y_e3t_sin_desfase_constante_en_un_regimen_evaluable(self):
        for linea, regla in ((Linea.E4P, Regla.UNICA), (Linea.E3T, Regla.GRUESA)):
            with self.subTest(linea=linea):
                P = pd.concat([_filas(2011, linea, regla, Nivel.REGIMEN, "R0", self.R0),
                               _filas(2011, linea, regla, Nivel.REGIMEN, "R1", self.R1)], ignore_index=True)
                sin = self._cv(linea, regla, Estado.SIN_INFORMACION, O.MOTIVO_DESFASE_CV)
                self.assertEqual(self._anual(O._anual_por_regimenes(sin, P, self.CV, linea, regla, [2011], "907201")),
                                 ("sin_informacion", O.MOTIVO_DESFASE_CV))
                con = self._cv(linea, regla, Estado.COMPATIBLE)
                self.assertEqual(self._anual(O._anual_por_regimenes(con, P, self.CV, linea, regla, [2011],
                                                                    "907201"))[0], "compatible")
                # R1 no evaluable para P: sólo cuenta R0.
                no_eval = {h: Estado.SIN_INFORMACION for h in self.R1}
                P_r0 = pd.concat([_filas(2011, linea, regla, Nivel.REGIMEN, "R0", self.R0),
                                  _filas(2011, linea, regla, Nivel.REGIMEN, "R1", no_eval, "minimos")],
                                 ignore_index=True)
                self.assertEqual(self._anual(O._anual_por_regimenes(sin, P_r0, self.CV, linea, regla, [2011],
                                                                    "907201"))[0], "compatible")


if __name__ == "__main__":
    unittest.main()
