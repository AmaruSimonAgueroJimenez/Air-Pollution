"""Pruebas de lineas_registro.py (E1a, E1b, E1c y E2).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
Datos sintéticos fabricados aquí mismo (no importan ``sintetico``): cada reloj fabrica su etiqueta por un
camino propio desde u consciente de UTC (§8, reglas comunes): C(Z) con ``astimezone(ZoneInfo(Z))`` y F(c)
con u + c h. No abren datos DMC ni /Volumes. Leen sólo los umbrales anclados en C0 (texto y JSON de APH,
con su sha256); si faltan, se omiten con el motivo y no se dan por aprobadas.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import calendar  # noqa: E402
import hashlib  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import unittest  # noqa: E402
import zoneinfo  # noqa: E402
from datetime import date, datetime, time, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import constantes, estados, lineas_registro, tablas, umbrales  # noqa: E402
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_EXTRACTO_HORA, ESQUEMA_MES,  # noqa: E402
                             ESQUEMA_METRICAS_E2, Conjunto, ContextoEstacion, Estado, InfoEstacion, Linea, Territorio,
                             validar_esquema)

_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
UTC = timezone.utc
H = timedelta(hours=1)
C, I, D, S = Estado.COMPATIBLE, Estado.INCOMPATIBLE, Estado.DUDOSA, Estado.SIN_INFORMACION
SANTIAGO, PASCUA = "America/Santiago", "Pacific/Easter"
ZONAS = {"Santiago": SANTIAGO, "Pacific/Easter": PASCUA}
CODIGO = "999001"

# Domingos de adelanto del Anexo A (copiados del texto; 2015 no tuvo cambios).
ADELANTOS = {2014: date(2014, 9, 7), 2016: date(2016, 8, 14), 2017: date(2017, 8, 13), 2018: date(2018, 8, 12),
             2019: date(2019, 9, 8)}
# Cv(Santiago, 2016): la regla anterior del Anexo A2 (atraso sáb 2016-04-23, adelanto dom 2016-09-04),
# en los instantes UTC del Anexo A (03:00 y 04:00 UTC del domingo).
CV2016_ATRASO_U = datetime(2016, 4, 24, 3, tzinfo=UTC)
CV2016_ADELANTO_U = datetime(2016, 9, 4, 4, tzinfo=UTC)

_T = None
_U = None


def setUpModule():
    global _T, _U
    zoneinfo.reset_tzpath(to=[])           # §9 y §8.A.2: sólo el paquete tzdata del intérprete
    zoneinfo.ZoneInfo.clear_cache()
    for ruta in (_APH / umbrales.PROTOCOLO_C0, _APH / umbrales.JSON_C0):
        if not ruta.is_file():
            raise unittest.SkipTest(f"falta {ruta.name} anclado en C0; las pruebas no se dan por aprobadas")
    _U = umbrales.cargar_c0(_APH)
    _T = tablas.cargar_tablas()


# ---------------------------------------------------------------------------
# Generadores independientes
# ---------------------------------------------------------------------------
def _cv_2016(u: datetime) -> datetime:
    if not datetime(2016, 1, 1, tzinfo=UTC) <= u < datetime(2017, 1, 1, tzinfo=UTC):
        raise ValueError("el reloj Cv2016 sólo se fabrica en 2016")
    c = -4 if CV2016_ATRASO_U <= u < CV2016_ADELANTO_U else -3
    return (u + timedelta(hours=c)).replace(tzinfo=None)


def _domingo_desde(anio: int, mes: int, dia: int) -> date:
    """El primer domingo ≥ ``dia`` del mes (camino propio, con calendar)."""
    d = date(anio, mes, dia)
    return d + timedelta(days=(calendar.SUNDAY - d.weekday()) % 7)


def _cv_2008(u: datetime) -> datetime:
    """Hora civil de Santiago con la regla anterior a 2008 en todos los años (como el tipo Cv de §8.D):
    −4 desde el domingo ≥ 9 de marzo a las 03:00 UTC hasta el domingo ≥ 9 de octubre a las 04:00 UTC."""
    a = u.year
    atraso = datetime.combine(_domingo_desde(a, 3, 9), time(3), tzinfo=UTC)
    adelanto = datetime.combine(_domingo_desde(a, 10, 9), time(4), tzinfo=UTC)
    c = -4 if atraso <= u < adelanto else -3
    return (u + timedelta(hours=c)).replace(tzinfo=None)


def _reloj(reloj: str):
    """u (consciente de UTC) → L, por un camino propio: «F(c)», «C(<abreviatura>)», «Cv2016» o «Cv2008»."""
    if reloj.startswith("F("):
        c = int(reloj[2:-1])
        return lambda u: (u + timedelta(hours=c)).replace(tzinfo=None)
    if reloj == "Cv2016":
        return _cv_2016
    if reloj == "Cv2008":
        return _cv_2008
    zona = zoneinfo.ZoneInfo(ZONAS[reloj[2:-1]])
    return lambda u: u.astimezone(zona).replace(tzinfo=None)


def _ts(u: datetime) -> float:
    return 15.0 + 5.0 * math.sin(2 * math.pi * (u.hour - 15) / 24)


def _horarias(reloj: str, desde: datetime, hasta: datetime) -> dict:
    """Una fila medida con Ts por hora UTC en [desde, hasta); una etiqueta repetida guarda la primera."""
    f, filas, u = _reloj(reloj), {}, desde
    while u < hasta:
        filas.setdefault(f(u), {"ts": _ts(u)})
        u += H
    return filas


def _ventanas(reloj: str, anios, dias: int = 35) -> dict:
    """Datos horarios ±``dias`` alrededor del adelanto de cada año (2015: alrededor del 2015-09-06)."""
    filas = {}
    for a in anios:
        D = datetime.combine(ADELANTOS.get(a, date(a, 9, 6)), time(), tzinfo=UTC)
        filas.update(_horarias(reloj, D - timedelta(days=dias), D + timedelta(days=dias)))
    return filas


def _diurna(etiquetas: str, operacion: str, anios, *, abre=8, cierra=19, corrimiento=lambda d: 0) -> dict:
    """Aeródromo diurno: opera de ``abre`` a ``cierra`` en la hora del reloj de operación (más un
    corrimiento administrativo por fecha) y etiqueta con el otro reloj."""
    f_L, f_op, filas = _reloj(etiquetas), _reloj(operacion), {}
    for a in anios:
        u, fin = datetime(a, 1, 1, tzinfo=UTC), datetime(a + 1, 1, 1, tzinfo=UTC)
        while u < fin:
            op = f_op(u)
            k = corrimiento(op.date())
            if abre + k <= op.hour <= cierra + k:
                filas.setdefault(f_L(u), {"ts": _ts(u)})
            u += H
    return filas


def _sinoptica(reloj: str, desde: date, hasta: date, *, horas_utc=(0, 6, 12, 18), observador=True, tx=None,
               tn=None, solo_rr=False) -> dict:
    """Marcas RR (y TX/TN) en horas UTC dadas, cada día de [desde, hasta)."""
    f, filas, d = _reloj(reloj), {}, desde
    todas = sorted(set(horas_utc) | {x for x in (tx, tn) if x is not None})
    while d < hasta:
        for hu in todas:
            u = datetime.combine(d, time(hu), tzinfo=UTC)
            fila = filas.setdefault(f(u), {"ts": math.nan if solo_rr else _ts(u), "medida": not solo_rr})
            if hu in horas_utc:
                fila["rr"], fila["observador"] = True, observador
            if hu == tx:
                fila["tx"] = True
            if hu == tn:
                fila["tn"] = True
        d += timedelta(days=1)
    return filas


_POR_OMISION = {"id_artefacto": 0, "medida": True, "ts": math.nan, "motivo_ts": 0, "qfe": math.nan, "motivo_qfe": 1,
                "td": math.nan, "hr": math.nan, "ff_kt": math.nan, "dd_grados": math.nan, "viento_valido": False,
                "qff_numerica": False, "rr": False, "tx": False, "tn": False, "observador": False}


def _extracto(filas: dict, info: InfoEstacion, cal=None) -> pd.DataFrame:
    """ESQUEMA_EXTRACTO_HORA anotado con tablas.anotar_partes; huella propia por etiqueta salvo que se dé."""
    registros = []
    for L in sorted(filas):
        r = dict(_POR_OMISION)
        r.update({k: v for k, v in filas[L].items() if k in ESQUEMA_EXTRACTO_HORA})
        r.update({"L": L, "anio": L.year, "mes": L.month})
        r.setdefault("huella", hashlib.sha256(L.isoformat().encode()).hexdigest())
        if "huella" in filas[L]:
            r["huella"] = filas[L]["huella"]
        registros.append(r)
    df = pd.DataFrame(registros, columns=list(ESQUEMA_EXTRACTO_HORA)).astype(ESQUEMA_EXTRACTO_HORA)
    return tablas.anotar_partes(df, info, cal or _T)


def _info(territorio=Territorio.CONTINENTAL, extra=()) -> InfoEstacion:
    zs, ids = tablas.ZS_Y_P[territorio]
    return InfoEstacion(codigo=CODIGO, nombre=None, lat=None, lon=None, alt_m=None, coordenadas_validas=True,
                        coordenadas_inconsistentes=False, territorio=territorio, region=None, macrozona="x",
                        zs=tuple(zs), P=tablas.hipotesis_de_P(list(ids) + list(extra)), pixel_id=None,
                        distancia_km=None, costera=False, z_pix=None, dz=None, conjunto=Conjunto.N)


def _ctx(info: InfoEstacion, extracto=None, *, anios=None, cal=None) -> ContextoEstacion:
    cal = cal or _T
    if anios is None:
        anios = sorted(set(extracto["anio"].astype(int)))
    regimenes = {a: tablas.regimenes_del_anio(info.zs, a, cal) for a in anios}
    con_datos, meses = {}, {}
    for a in anios:
        if extracto is None:
            con_datos[a], meses[a] = tuple(r.id for r in regimenes[a]), tuple(range(1, 13))
            continue
        del_anio = extracto[extracto["anio"] == a]
        usables = del_anio[~del_anio["especial"] & del_anio["regimen"].notna()]
        con_datos[a] = tuple(sorted(set(usables["regimen"])))
        meses[a] = tuple(sorted(set(del_anio["mes"].astype(int))))
    sin_cv = [h for h in info.P if h.tipo != "Cv"]
    clases = {a: tablas.fusionar(sin_cv, [r for r in regimenes[a] if r.id in con_datos[a]], info.zs) for a in anios}
    return ContextoEstacion(info=info, tablas=cal, umbrales=_U, anios=tuple(anios), regimenes=regimenes,
                            regimenes_con_datos=con_datos, clases=clases, meses_con_datos=meses,
                            lineas_activas=frozenset(Linea))


def _anual(res, anio) -> dict:
    e = res.estados
    sel = e[(e["nivel"] == "anio") & (e["anio"] == anio)]
    return {h: Estado(s) for h, s in zip(sel["H"], sel["estado"])}


def _motivos_anuales(res, anio) -> dict:
    e = res.estados
    sel = e[(e["nivel"] == "anio") & (e["anio"] == anio)]
    return {h: (None if pd.isna(m) else m) for h, m in zip(sel["H"], sel["motivo"])}


def _evento(res_o_eventos, zona, etiqueta, clase=None):
    e = res_o_eventos.eventos if hasattr(res_o_eventos, "eventos") else res_o_eventos
    sel = e[(e["zona"] == zona) & (e["etiqueta"] == etiqueta)]
    if clase is not None:
        sel = sel[sel["clase_evento"] == clase]
    if len(sel) != 1:
        raise AssertionError(f"{len(sel)} eventos {zona} {etiqueta} {clase}")
    return sel.iloc[0]


def _unidad(res, nivel, unidad) -> dict:
    e = res.estados
    sel = e[(e["nivel"] == nivel) & (e["unidad"] == unidad)]
    return {h: Estado(s) for h, s in zip(sel["H"], sel["estado"])}


def _metrica(res, unidad, anio=None):
    m = res.metricas
    sel = m[m["unidad"] == unidad]
    if anio is not None:
        sel = sel[sel["anio"] == anio]
    if len(sel) != 1:
        raise AssertionError(f"{len(sel)} filas de métricas para {unidad}")
    return sel.iloc[0]


FIJAS_INCOMPATIBLES = {"F(0)": I, "F(-3)": I, "F(-4)": I, "C(Santiago)": C}
FIJAS_COMPATIBLES = {"F(0)": C, "F(-3)": C, "F(-4)": C, "C(Santiago)": I}
TODO_SIN_INFO = {"F(0)": S, "F(-3)": S, "F(-4)": S, "C(Santiago)": S}


class _Base(unittest.TestCase):
    def assertEsquemas(self, res):
        validar_esquema(res.estados, ESQUEMA_ESTADOS, nombre="estados")
        if res.eventos is not None:
            validar_esquema(res.eventos, ESQUEMA_EVENTOS, nombre="eventos")
        if res.metricas is not None:
            validar_esquema(res.metricas, ESQUEMA_METRICAS_E2, nombre="metricas")
        self.assertFalse(res.estados.duplicated(["anio", "nivel", "unidad", "H"]).any())


# ---------------------------------------------------------------------------
# E1a
# ---------------------------------------------------------------------------
class PruebasE1a(_Base):
    def test_p08_e1a_evento_presente(self):
        """Fila medida con huella propia en h0: C(Z) incompatible, fijas compatibles."""
        info = _info()
        ext = _extracto(_ventanas("F(-4)", [2019]), info)
        res = lineas_registro.e1a(ext, _ctx(info, ext))
        self.assertEsquemas(res)
        self.assertEqual(res.linea, Linea.E1A)
        self.assertEqual(_evento(res, SANTIAGO, "2019-09-08T00:00", "real")["resultado"], "presente")
        self.assertEqual(_anual(res, 2019), FIJAS_COMPATIBLES)
        self.assertEqual(_unidad(res, "evento", "America/Santiago|2019-09-08|adelanto|real"), FIJAS_COMPATIBLES)
        pd.testing.assert_frame_equal(res.eventos, lineas_registro.eventos_e1a(ext, _ctx(info, ext)))

    def test_p08_e1a_evento_ausente_con_patron_civil(self):
        """Ausente + patrón: fijas incompatibles, C(Z) compatible."""
        info = _info()
        ext = _extracto(_ventanas("C(Santiago)", [2018, 2019]), info)
        res = lineas_registro.e1a(ext, _ctx(info, ext))
        self.assertEsquemas(res)
        for anio, etiqueta in ((2018, "2018-08-12T00:00"), (2019, "2019-09-08T00:00")):
            ev = _evento(res, SANTIAGO, etiqueta, "real")
            self.assertEqual(ev["resultado"], "ausente")
            self.assertEqual((ev["p14"], ev["pdom"], ev["p"]), (1.0, 1.0, 1.0))
            self.assertEqual(_anual(res, anio), FIJAS_INCOMPATIBLES)
        # Sin patrón (un solo ausente), el ausente no informa.
        ext1 = _extracto(_ventanas("C(Santiago)", [2019]), info)
        res1 = lineas_registro.e1a(ext1, _ctx(info, ext1))
        self.assertEqual(_anual(res1, 2019), TODO_SIN_INFO)
        self.assertEqual(set(_motivos_anuales(res1, 2019).values()), {lineas_registro.MOTIVO_SIN_PATRON})

    def test_p08_e1a_copia_de_un_vecino_no_es_presente(self):
        """Huella igual a t− o t+: sin evidencia."""
        info = _info()
        h0, t_menos, t_mas = datetime(2019, 9, 8, 0), datetime(2019, 9, 7, 23), datetime(2019, 9, 8, 1)

        def con(cambio):
            filas = _ventanas("F(-4)", [2019])
            cambio(filas)
            ext = _extracto(filas, info)
            res = lineas_registro.e1a(ext, _ctx(info, ext))
            return _evento(res, SANTIAGO, "2019-09-08T00:00", "real")["resultado"], _anual(res, 2019)

        def copia(vecino):
            def cambio(filas):
                filas[h0]["huella"] = hashlib.sha256(vecino.isoformat().encode()).hexdigest()
            return cambio

        for vecino in (t_menos, t_mas):
            self.assertEqual(con(copia(vecino)), ("sin_evidencia", TODO_SIN_INFO), vecino)

        # |ΔTs| con el vecino más cercano: en un empate (t− y t+ a 1 h), manda el anterior (R-44).
        def salto(dts):
            def cambio(filas):
                filas[h0]["ts"] = filas[t_menos]["ts"] + dts
                filas[t_mas]["ts"] = filas[h0]["ts"]
            return cambio
        maximo = _U.f("E1A_DTS_MAX")
        self.assertEqual(con(salto(maximo + 0.5))[0], "sin_evidencia")
        self.assertEqual(con(salto(maximo - 0.1))[0], "presente")

        # Una fila con sólo marcas (H = 0) no basta.
        def solo_marcas(filas):
            filas[h0].update({"medida": False, "ts": math.nan, "rr": True})
        self.assertEqual(con(solo_marcas)[0], "sin_evidencia")

    def test_p08_e1a_p0_y_umbral_de_80(self):
        """P0 ≤ 0,01 y ausentes ≥ 80 % de los evaluables."""
        info = _info()

        def estacion(anios, quitar=(), presentes=()):
            filas = _ventanas("C(Santiago)", anios)
            for a in quitar:                   # deja p14 = 12/14 sin tocar las fechas del mismo día
                for k in (1, 2):
                    del filas[datetime.combine(ADELANTOS[a] + timedelta(days=k), time())]
            for a in presentes:                # una fila medida propia en h0 (evento presente)
                h0 = datetime.combine(ADELANTOS[a], time())
                filas[h0] = {"ts": filas[h0 - H]["ts"], "huella": "propia" + str(a)}
            ext = _extracto(filas, info)
            return lineas_registro.e1a(ext, _ctx(info, ext))

        # P0: dos ausentes con p = 12/14 dan (2/14)² ≈ 0,020 > E1A_P0; con tres, (1/7)³ ≈ 0,0029.
        res = estacion([2017, 2018], quitar=[2017, 2018])
        ev = _evento(res, SANTIAGO, "2018-08-12T00:00", "real")
        self.assertEqual(ev["resultado"], "ausente")
        self.assertAlmostEqual(ev["p"], 12 / 14)
        self.assertGreater((2 / 14) ** 2, _U.a("E1A_P0"))
        self.assertEqual(_anual(res, 2018), TODO_SIN_INFO)
        res = estacion([2016, 2017, 2018], quitar=[2016, 2017, 2018])
        self.assertLessEqual((2 / 14) ** 3, _U.a("E1A_P0"))
        self.assertEqual(_anual(res, 2018), FIJAS_INCOMPATIBLES)

        # 80 %: 3 ausentes de 4 evaluables (75 %) no dan patrón; 4 de 5 (80 %) sí.
        res = estacion([2016, 2017, 2018, 2019], presentes=[2019])
        self.assertEqual(_anual(res, 2019), FIJAS_COMPATIBLES)            # el presente decide solo
        self.assertEqual(_anual(res, 2018), TODO_SIN_INFO)
        res = estacion([2014, 2016, 2017, 2018, 2019], presentes=[2019])
        self.assertEqual(_anual(res, 2019), FIJAS_COMPATIBLES)
        self.assertEqual(_anual(res, 2018), FIJAS_INCOMPATIBLES)

    def test_p08_e1a_placebos_mismo_dia_y_anexo_a2(self):
        """Placebos de la semana a ≥ 3 días de un cambio y fechas del A2 (2015-09-06)."""
        info = _info()
        ext = _extracto(_ventanas("C(Santiago)", [2019]), info)
        ev = lineas_registro.eventos_e1a(ext, _ctx(info, ext))
        # Enmienda 3 (A′): los eventos de regla vencida («regla_vencida», el 2019-10-13) no son placebos.
        placebos = {(c, e) for c, e in zip(ev["clase_evento"], ev["etiqueta"]) if c not in ("real", "regla_vencida")}
        self.assertEqual(set(ev.loc[ev["clase_evento"] == "regla_vencida", "etiqueta"]), {"2019-10-13T00:00"})
        semana = {f"2019-{md}T00:00" for md in ("08-18", "08-25", "09-01", "09-15", "09-22", "09-29", "10-06")}
        # El 2019-08-11 es D − 28 y fecha del Anexo A2: se cuenta una vez, como placebo del A2.
        self.assertEqual(placebos, {("placebo_semana", e) for e in semana} | {("placebo_A2", "2019-08-11T00:00")})

        # 2015: sin cambios, sólo placebos; el del A2 es el 2015-09-06 00:00 (en Pascua, el 05 a las 22:00).
        santiago_2015, pascua_2015 = constantes.valor("E1A_PLACEBO_2015")
        ext = _extracto(_ventanas("F(-3)", [2015]), info)
        res = lineas_registro.e1a(ext, _ctx(info, ext))
        self.assertEqual(_evento(res, SANTIAGO, santiago_2015)["clase_evento"], "placebo_A2")
        self.assertEqual(_anual(res, 2015), TODO_SIN_INFO)
        self.assertEqual(set(_motivos_anuales(res, 2015).values()), {lineas_registro.MOTIVO_SIN_EVENTOS})
        info_p = _info(Territorio.PASCUA_SALA_Y_GOMEZ)
        ext = _extracto(_ventanas("C(Pacific/Easter)", [2015]), info_p)
        ev = lineas_registro.eventos_e1a(ext, _ctx(info_p, ext))
        self.assertEqual(_evento(ev, PASCUA, pascua_2015)["clase_evento"], "placebo_A2")
        self.assertEqual(_evento(ev, SANTIAGO, santiago_2015)["clase_evento"], "placebo_A2")

        # «≥ 3 días de cualquier cambio»: con un par de cambios ficticios (atraso con la 23:00 del lunes
        # 2019-09-23 repetida y adelanto sin la 00:00 del lunes 2019-09-30), caen el 09-22 y el 09-29.
        anexo = {z: [list(f) for f in filas] for z, filas in _T.anexo_a.items()}
        anexo[SANTIAGO] = sorted(anexo[SANTIAGO] + [["2019-09-24T03:00Z", -180, -240],
                                                    ["2019-09-30T04:00Z", -240, -180]])
        ficticia = tablas.TablasCalendario(anexo, _T.anexo_a2)
        ext = _extracto(_ventanas("F(-4)", [2019]), info, ficticia)
        ev = lineas_registro.eventos_e1a(ext, _ctx(info, ext, cal=ficticia))
        etiquetas = set(ev.loc[ev["clase_evento"] == "placebo_semana", "etiqueta"])
        self.assertTrue({"2019-09-15T00:00", "2019-10-06T00:00"} <= etiquetas)
        self.assertFalse({"2019-09-22T00:00", "2019-09-29T00:00"} & etiquetas)

        # La tasa de placebos ausentes: 1 de 16 (6 %) deja el patrón; 2 de 16 (12,5 %) lo apagan.
        def con_placebos_ausentes(anios):
            filas = _ventanas("C(Santiago)", [2018, 2019])
            for a in anios:
                del filas[datetime.combine(ADELANTOS[a] - timedelta(days=7), time())]
            ext = _extracto(filas, info)
            return lineas_registro.e1a(ext, _ctx(info, ext))
        res = con_placebos_ausentes([2019])
        self.assertEqual(_evento(res, SANTIAGO, "2019-09-01T00:00")["resultado"], "ausente")
        self.assertEqual(_anual(res, 2019), FIJAS_INCOMPATIBLES)
        self.assertLessEqual(1 / 16, _U.a("E1A_PLACEBO"))
        self.assertGreater(2 / 16, _U.a("E1A_PLACEBO"))
        self.assertEqual(_anual(con_placebos_ausentes([2018, 2019]), 2019), TODO_SIN_INFO)

    def test_e1a_pascua_sabado_22(self):
        """h0 de Pacific/Easter es el sábado 22:00."""
        info = _info(Territorio.PASCUA_SALA_Y_GOMEZ)
        ext = _extracto(_ventanas("C(Pacific/Easter)", [2018, 2019]), info)
        res = lineas_registro.e1a(ext, _ctx(info, ext))
        self.assertEsquemas(res)
        self.assertEqual(_evento(res, PASCUA, "2019-09-07T22:00", "real")["resultado"], "ausente")
        self.assertEqual(_evento(res, SANTIAGO, "2019-09-08T00:00", "real")["resultado"], "presente")
        esperado = {"F(0)": I, "F(-3)": I, "F(-4)": I, "F(-5)": I, "F(-6)": I, "C(Pacific/Easter)": C,
                    "C(Santiago)": I}
        self.assertEqual(_anual(res, 2019), esperado)

    def test_p08_e1a_reglas_vencidas_cv_en_P(self):
        """Diagnóstico (§4.1.4, Enmienda 1 E1-4 en borrador): Cv(Santiago, 2016) en P. El adelanto real
        trae fila (Cv compatible, C incompatible) y la fecha del A2 queda ausente como placebo."""
        info = _info(extra=("Cv(Santiago)",))
        filas = _horarias("Cv2016", datetime(2016, 7, 10, tzinfo=UTC), datetime(2016, 9, 25, tzinfo=UTC))
        ext = _extracto(filas, info)
        res = lineas_registro.e1a(ext, _ctx(info, ext))
        self.assertEsquemas(res)
        self.assertEqual(_evento(res, SANTIAGO, "2016-08-14T00:00", "real")["resultado"], "presente")
        self.assertEqual(_evento(res, SANTIAGO, "2016-09-04T00:00", "placebo_A2")["resultado"], "ausente")
        self.assertEqual(_anual(res, 2016), {**FIJAS_COMPATIBLES, "Cv(Santiago)": C})
        # Fuera de los años del Anexo A2, Cv no existe: sin información, sin error.
        ext = _extracto(_ventanas("F(-4)", [2018]), info)
        res = lineas_registro.e1a(ext, _ctx(info, ext))
        self.assertEqual(_anual(res, 2018)["Cv(Santiago)"], S)
        self.assertEqual(_motivos_anuales(res, 2018)["Cv(Santiago)"], lineas_registro.MOTIVO_FUERA_A2)

    def test_p08_e1a_enmienda_3_eventos_y_patron_de_reglas_vencidas(self):
        """Enmienda 3, E3-2 (opción A′, con el patrón por regla vencida; lectura 9). Hora civil con la regla anterior a 2008
        (automática de 24 h, 2016-2019, datos ±35 días alrededor del adelanto real y del de octubre):
        - los adelantos de la regla vencida (domingo ≥ 9 de octubre, 00:00) quedan ausentes; las fechas que
          sólo da el A2 (2016-09-04 y 2019-08-11) existen bajo esa regla y quedan presentes;
        - con los eventos de todas las reglas juntos (la letra del borrador) no hay patrón: 4 ausentes de 6
          (67 % < 80 %); por regla, «octubre, domingo ≥ 9» tiene 4 de 4 y hay patrón;
        - consecuencia: las filas anuales de los cuatro años señalan reloj anómalo (todas las H) y
          ``patron_regla_vencida`` lo reconoce. Los estados por H no cambian (el adelanto real está
          presente: C(Santiago) incompatible).
        Con C(Santiago) y F(−4) en las mismas ventanas, los eventos de regla vencida están presentes y nada
        cambia."""
        info = _info()
        anios = [2016, 2017, 2018, 2019]

        def ventanas(reloj):
            filas = {}
            for a in anios:
                for dia in (ADELANTOS[a], _domingo_desde(a, 10, 9)):
                    D = datetime.combine(dia, time(), tzinfo=UTC)
                    filas.update(_horarias(reloj, D - timedelta(days=35), D + timedelta(days=35)))
            return filas

        ext = _extracto(ventanas("Cv2008"), info)
        ctx = _ctx(info, ext)
        res = lineas_registro.e1a(ext, ctx)
        self.assertEsquemas(res)
        octubre = {a: f"{_domingo_desde(a, 10, 9).isoformat()}T00:00" for a in anios}
        for a, etiqueta in octubre.items():
            ev = _evento(res, SANTIAGO, etiqueta)
            self.assertEqual((ev["clase_evento"], ev["resultado"], ev["p"]), ("regla_vencida", "ausente", 1.0), a)
            self.assertEqual(_evento(res, SANTIAGO, f"{ADELANTOS[a].isoformat()}T00:00", "real")["resultado"],
                             "presente")
        for etiqueta in ("2016-09-04T00:00", "2019-08-11T00:00"):
            self.assertEqual(_evento(res, SANTIAGO, etiqueta, "placebo_A2")["resultado"], "presente")
        # La letra del borrador (todos los eventos juntos) no da patrón; por regla, sí.
        eventos = lineas_registro._eventos_e1a(ext, ctx)
        rv = lineas_registro._etiquetas_reglas_vencidas(_T, SANTIAGO, anios)
        self.assertEqual(sorted(set(rv.values())), ["agosto, domingo ≥ 9", "octubre, domingo ≥ 9",
                                                   "septiembre, domingo ≥ 2"])
        placebos = [e for e in eventos if e.clase == "placebo_semana" and e.etiqueta not in rv]
        juntos = lineas_registro._patron([e for e in eventos if e.etiqueta in rv], placebos, _U)
        self.assertEqual((juntos.n_evaluables, juntos.n_ausentes, juntos.civil), (6, 4, False))
        por_regla = lineas_registro._patrones_regla_vencida(eventos, rv, _U)
        self.assertEqual({r: (p.n_evaluables, p.n_ausentes, p.civil) for r, p in por_regla.items()},
                         {"octubre, domingo ≥ 9": (4, 4, True), "septiembre, domingo ≥ 2": (1, 0, False),
                          "agosto, domingo ≥ 9": (1, 0, False)})
        e = res.estados
        anual = e[e["nivel"] == "anio"]
        self.assertTrue(anual["reloj_anomalo"].all())
        self.assertFalse(e.loc[e["nivel"] != "anio", "reloj_anomalo"].any())
        self.assertTrue(lineas_registro.patron_regla_vencida(e))
        for a in anios:
            self.assertEqual(_anual(res, a), FIJAS_COMPATIBLES, a)
        # Relojes de P: los eventos de regla vencida están presentes; ni reloj anómalo ni patrón.
        for reloj in ("C(Santiago)", "F(-4)"):
            ext = _extracto(ventanas(reloj), info)
            res = lineas_registro.e1a(ext, _ctx(info, ext))
            for a, etiqueta in octubre.items():
                self.assertEqual(_evento(res, SANTIAGO, etiqueta, "regla_vencida")["resultado"], "presente", reloj)
            self.assertFalse(res.estados["reloj_anomalo"].any(), reloj)
            self.assertFalse(lineas_registro.patron_regla_vencida(res.estados), reloj)
        # Con un solo año no hay patrón (≥ 2 ausentes): riesgo residual de la Enmienda 3.
        ext = _extracto({L: v for L, v in ventanas("Cv2008").items() if L.year == 2017}, info)
        res = lineas_registro.e1a(ext, _ctx(info, ext))
        self.assertEqual(_evento(res, SANTIAGO, octubre[2017], "regla_vencida")["resultado"], "ausente")
        self.assertFalse(lineas_registro.patron_regla_vencida(res.estados))

    def test_e1a_fusion_por_datos_no_rompe_la_clase(self):
        """Año sólo con datos de verano (C(Santiago) ≡ F(−3)) y fila en h0: la clase queda sin información."""
        info = _info()
        filas = _horarias("F(-3)", datetime(2019, 9, 8, 3, tzinfo=UTC), datetime(2019, 10, 31, tzinfo=UTC))
        ext = _extracto(filas, info)
        ctx = _ctx(info, ext)
        self.assertIn("F(-3)|C(Santiago)", {c.id for c in ctx.clases[2019]})
        res = lineas_registro.e1a(ext, ctx)
        self.assertEqual(_evento(res, SANTIAGO, "2019-09-08T00:00", "real")["resultado"], "presente")
        anual = _anual(res, 2019)
        self.assertEqual(anual, {"F(0)": C, "F(-3)": S, "F(-4)": C, "C(Santiago)": S})
        self.assertEqual(_motivos_anuales(res, 2019)["C(Santiago)"], lineas_registro.MOTIVO_FUSION)
        self.assertEqual(estados.estado_de_clase({h: anual[h] for h in ("F(-3)", "C(Santiago)")}), S)


# ---------------------------------------------------------------------------
# E1b y E1c
# ---------------------------------------------------------------------------
def _meses(anios, *, menos=(), sin_vacias=()) -> pd.DataFrame:
    filas = []
    for a in anios:
        for m in range(1, 13):
            esperadas = 24 * calendar.monthrange(a, m)[1]
            vacias = 30 - (1 if (a, m) in menos else 0)
            falta = (a, m) in sin_vacias
            filas.append({
                "codigo": CODIGO, "anio": a, "mes": m,
                "manifiesto": f"DMC/estaciones/{CODIGO}/{a:04d}-{m:02d}.manifest.json",
                "manifiesto_sha256": "0" * 64, "artefacto_sha256": "1" * 64, "id_artefacto": len(filas),
                "script_sha256": "2" * 64, "entra": True, "motivo_exclusion": None, "row_count": esperadas - 30,
                "source_empty_slots": None if falta else vacias, "expected_hour_slots": esperadas,
                "n_available_hours": esperadas - 30, "duplicate_display_rows_removed": 0, "source_sha256": "3" * 64,
                "requested_start": f"{a:04d}-{m:02d}-01", "requested_end": f"{a:04d}-{m:02d}-28",
                "campos_faltantes": ["source_empty_slots"] if falta else [], "p_ts": 1, "p_qfe": 1,
                "lat_txt": None, "lon_txt": None, "alt_txt": None,
            })
    return pd.DataFrame(filas, columns=list(ESQUEMA_MES)).astype(ESQUEMA_MES)


class PruebasE1bE1c(_Base):
    @classmethod
    def setUpClass(cls):
        cls.info = _info()

    def _e1b(self, filas):
        ext = _extracto(filas, self.info)
        return lineas_registro.e1b(ext, _ctx(self.info, ext)), ext

    def test_p09_e1b_cuatro_casos_de_signo(self):
        """Adelanto y atraso con δ = −1 y δ = +1."""
        # δ = −1: etiquetas fijas F(−4), operación en hora civil.
        res, ext = self._e1b(_diurna("F(-4)", "C(Santiago)", [2018, 2019]))
        self.assertEsquemas(res)
        self.assertTrue(lineas_registro.es_estacion_diurna(ext[ext["anio"] == 2019], _ctx(self.info, ext)))
        for etiqueta in ("2019-04-06T23:00", "2019-09-08T00:00"):
            ev = _evento(res, SANTIAGO, etiqueta, "real")
            self.assertEqual((ev["resultado"], ev["delta"]), ("evaluado", -1), etiqueta)
        self.assertEqual(_evento(res, SANTIAGO, "2019-09-08T00:00", "real")["delta_s"], -1)   # adelanto: δ = Δ
        self.assertEqual(_evento(res, SANTIAGO, "2019-04-06T23:00", "real")["delta_s"], 1)    # atraso: δ = −Δ
        self.assertEqual(_anual(res, 2019), FIJAS_COMPATIBLES)
        self.assertEqual(_anual(res, 2018), FIJAS_COMPATIBLES)
        # δ = +1: etiquetas civiles, operación en hora fija.
        res, _ = self._e1b(_diurna("C(Santiago)", "F(-4)", [2018, 2019]))
        for etiqueta in ("2019-04-06T23:00", "2019-09-08T00:00"):
            ev = _evento(res, SANTIAGO, etiqueta, "real")
            self.assertEqual((ev["resultado"], ev["delta"]), ("evaluado", 1), etiqueta)
        self.assertEqual(_anual(res, 2019), FIJAS_INCOMPATIBLES)
        # Los placebos (±42, ±63 y Anexo A2) no muestran escalón.
        pl = res.eventos[res.eventos["clase_evento"] != "real"]
        self.assertTrue((pl["resultado"] == "evaluado").all())
        self.assertTrue((pl["delta_s"] == 0).all())
        self.assertIn("placebo_A2", set(pl["clase_evento"]))
        self.assertIn("2019-05-12", set(pl.loc[pl["clase_evento"] == "placebo_A2", "fecha_D"]))   # D = domingo

    def test_p09_e1b_cambio_administrativo_de_horario(self):
        """Un cambio de horario fuera de un cambio de hora no da patrón (placebos)."""
        # Etiqueta y operación fijas, con un corrimiento administrativo de +1 h desde el 2019-06-15.
        res, _ = self._e1b(_diurna("F(-4)", "F(-4)", [2018, 2019],
                                   corrimiento=lambda d: 1 if d >= date(2019, 6, 15) else 0))
        for etiqueta in ("2019-04-06T23:00", "2019-09-08T00:00", "2018-08-12T00:00"):
            self.assertEqual(_evento(res, SANTIAGO, etiqueta, "real")["delta"], 0, etiqueta)
        self.assertEqual(abs(_evento(res, SANTIAGO, "2019-06-08T23:00", "placebo_desplazado")["delta_s"]), 1)
        self.assertEqual(_anual(res, 2019), TODO_SIN_INFO)
        # Operación civil (δ = −1 en los cambios reales) con corrimientos administrativos de junio y julio:
        # los placebos los ven (> 10 %) y el patrón fijo no se establece.
        admin = lambda d: 1 if date(d.year, 6, 1) <= d < date(d.year, 7, 20) else 0   # noqa: E731
        res, _ = self._e1b(_diurna("F(-4)", "C(Santiago)", [2018, 2019], corrimiento=admin))
        reales = res.eventos[res.eventos["clase_evento"] == "real"]
        self.assertTrue((reales["delta"] == -1).all())
        pl = res.eventos[(res.eventos["clase_evento"] != "real") & (res.eventos["resultado"] == "evaluado")]
        tasa = (pl["delta_s"].abs() >= _U.f("E1B_PLACEBO_DELTA")).mean()
        self.assertGreater(tasa, _U.frac("E1B_PLACEBO_PCT"))
        self.assertEqual(_anual(res, 2019), TODO_SIN_INFO)
        self.assertEqual(set(_motivos_anuales(res, 2019).values()), {lineas_registro.MOTIVO_SIN_PATRON})

    def test_e1b_estacion_no_diurna(self):
        """Una estación de 24 h no es diurna: E1b no informa."""
        filas = _horarias("F(-4)", datetime(2019, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, tzinfo=UTC))
        res, ext = self._e1b(filas)
        self.assertFalse(lineas_registro.es_estacion_diurna(ext[ext["anio"] == 2019], _ctx(self.info, ext)))
        self.assertEqual(_anual(res, 2019), TODO_SIN_INFO)
        self.assertEqual(set(_motivos_anuales(res, 2019).values()), {lineas_registro.MOTIVO_NO_DIURNA})

    def test_p09_e1c_con_y_sin_source_empty_slots(self):
        """Rejilla civil con una casilla menos; sin el campo, sin información."""
        ctx = _ctx(self.info, anios=(2018, 2019))
        res = lineas_registro.e1c(_meses([2018, 2019], menos={(2018, 8), (2019, 9)}), ctx)
        self.assertEsquemas(res)
        self.assertEqual(_anual(res, 2018), FIJAS_INCOMPATIBLES)
        self.assertEqual(_anual(res, 2019), FIJAS_INCOMPATIBLES)
        self.assertEqual(_unidad(res, "mes", "2019-09"), FIJAS_INCOMPATIBLES)
        self.assertEqual(_unidad(res, "mes", "2019-03"), TODO_SIN_INFO)
        ev = _evento(res, SANTIAGO, "2019-09-08T00:00", "real")
        self.assertEqual((ev["resultado"], ev["casillas"], ev["esperadas"]), ("casilla_menos", 719, 720))
        # E1c informa además el mes de la fecha de adelanto del Anexo A2 (2019-08-11), aquí completo.
        self.assertEqual(_evento(res, SANTIAGO, "2019-08-11T00:00", "placebo_A2")["resultado"], "completa")

        # Sin source_empty_slots en 2019-09: ese mes queda sin información y no hay patrón (un solo mes).
        res = lineas_registro.e1c(_meses([2018, 2019], menos={(2018, 8), (2019, 9)}, sin_vacias={(2019, 9)}), ctx)
        self.assertEqual(_unidad(res, "mes", "2019-09"), TODO_SIN_INFO)
        motivos = res.estados[(res.estados["unidad"] == "2019-09")]["motivo"]
        self.assertEqual(set(motivos), {"campos_faltantes"})
        self.assertEqual(_evento(res, SANTIAGO, "2019-09-08T00:00", "real")["resultado"], "campos_faltantes")
        self.assertEqual(_anual(res, 2018), TODO_SIN_INFO)

        # «Y en ningún otro mes»: una casilla menos fuera de un adelanto (o en el mes del A2) apaga el patrón.
        for otro in ((2019, 3), (2019, 8)):
            res = lineas_registro.e1c(_meses([2018, 2019], menos={(2018, 8), (2019, 9), otro}), ctx)
            self.assertEqual(_anual(res, 2019), TODO_SIN_INFO, otro)
        self.assertEqual(_evento(res, SANTIAGO, "2019-08-11T00:00", "placebo_A2")["resultado"], "casilla_menos")

    def test_e1c_pascua_r10_mes_por_mes(self):
        """Lectura 10 (R-10 mes por mes): en Pascua los adelantos de Pacific/Easter (sábado 22:00) y de Santiago
        (domingo 00:00) caen en el mismo mes y las dos zonas tienen patrón. «Las fijas» son las H sin etiqueta
        inexistente en el mes: quedan incompatibles; C(Pacific/Easter) y C(Santiago) quedan compatibles (E1c no
        las separa; E1a y E2 sí). Con la lectura zona por zona todas quedaban incompatibles."""
        info = _info(Territorio.PASCUA_SALA_Y_GOMEZ)
        ctx = _ctx(info, anios=(2018, 2019))
        res = lineas_registro.e1c(_meses([2018, 2019], menos={(2018, 8), (2019, 9)}), ctx)
        self.assertEsquemas(res)
        esperado = {"F(0)": I, "F(-3)": I, "F(-4)": I, "F(-5)": I, "F(-6)": I, "C(Pacific/Easter)": C,
                    "C(Santiago)": C}
        for anio in (2018, 2019):
            self.assertEqual(_anual(res, anio), esperado, anio)
        self.assertEqual(_unidad(res, "mes", "2019-09"), esperado)
        for zona, etiqueta in ((PASCUA, "2019-09-07T22:00"), (SANTIAGO, "2019-09-08T00:00")):
            self.assertEqual(_evento(res, zona, etiqueta, "real")["resultado"], "casilla_menos")
        # Cada sub-evaluación, por separado: la C de la otra zona queda sin información, no incompatible.
        cal = ctx.tablas
        del_mes = lineas_registro._etiquetas_adelanto_del_mes(cal, info.zs, 2019, 9)
        self.assertEqual(del_mes, (datetime(2019, 9, 7, 22), datetime(2019, 9, 8, 0)))
        por_pascua = lineas_registro._estados_mes_e1c(info.P, datetime(2019, 9, 7, 22), del_mes, cal)
        self.assertEqual(por_pascua["C(Pacific/Easter)"][0], C)
        self.assertEqual(por_pascua["C(Santiago)"], (S, lineas_registro.MOTIVO_OTRA_ETIQUETA))
        self.assertEqual(por_pascua["F(-6)"][0], I)
        # Continental: una sola h0 por mes, nada cambia (lo mismo que p09).
        ctx_c = _ctx(self.info, anios=(2018, 2019))
        res_c = lineas_registro.e1c(_meses([2018, 2019], menos={(2018, 8), (2019, 9)}), ctx_c)
        self.assertEqual(_anual(res_c, 2019), FIJAS_INCOMPATIBLES)


# ---------------------------------------------------------------------------
# E2
# ---------------------------------------------------------------------------
def _cortar_en_cv_2016(ext: pd.DataFrame) -> pd.DataFrame:
    """Lo que hará orquestacion en el diagnóstico (Enmienda 1, E1-4): cortar también las partes en las
    etiquetas especiales de Cv(Santiago, 2016): la 23:00 repetida del 2016-04-23 y la 00:00 inexistente
    del 2016-09-04."""
    x = ext.copy()
    especial = x["L"] == pd.Timestamp("2016-04-23 23:00")
    x.loc[especial, "especial"] = True
    x.loc[especial, ["parte", "regimen"]] = pd.NA
    x.loc[(x["parte"] == "2016-04-1") & (x["L"] > pd.Timestamp("2016-04-23 23:00")), "parte"] = "2016-04-2"
    x.loc[(x["parte"] == "2016-09-1") & (x["L"] > pd.Timestamp("2016-09-04 00:00")), "parte"] = "2016-09-2"
    return x


class PruebasE2(_Base):
    @classmethod
    def setUpClass(cls):
        cls.info = _info()

    def _e2(self, filas, info=None, transformar=None):
        info = info or self.info
        ext = _extracto(filas, info)
        if transformar is not None:
            ext = transformar(ext)
        return lineas_registro.e2(ext, _ctx(info, ext))

    def test_p10_e2_clases_0_y_2(self):
        """00/06/12/18 y 03/09/15/21 → clase 0; 20/02/08/14 → clase 2."""
        for horas, clase in (((0, 6, 12, 18), 0), ((3, 9, 15, 21), 0), ((20, 2, 8, 14), 2)):
            self.assertEqual({lineas_registro.clase_mod3(h) for h in horas}, {clase}, horas)
        self.assertEqual(lineas_registro.clase_mod3(-4), 2)
        for reloj, clase in (("F(0)", 0), ("F(-3)", 0), ("F(-4)", 2)):
            res = self._e2(_sinoptica(reloj, date(2019, 1, 1), date(2019, 3, 1)))
            self.assertEsquemas(res)
            m = _metrica(res, "2019-01-1")
            self.assertEqual((m["j_estrella"], m["kappa3"], bool(m["informativa"])), (clase, 1.0, True), reloj)

    def test_e2_clase_1_es_reloj_anomalo(self):
        """Marcas en clase 1 en el continente: ninguna H de P la tiene."""
        res = self._e2(_sinoptica("F(+1)", date(2019, 1, 1), date(2019, 3, 1)))
        e = res.estados
        self.assertTrue(e.loc[e["unidad"] == "2019-01-1", "reloj_anomalo"].all())
        anual = e[(e["nivel"] == "anio") & (e["anio"] == 2019)]
        self.assertTrue(anual["reloj_anomalo"].all())
        self.assertEqual(_anual(res, 2019), {"F(0)": I, "F(-3)": I, "F(-4)": I, "C(Santiago)": I})

    def test_p10_e2_hora_civil_alterna_de_clase(self):
        """C(Santiago): 0 en verano, 2 en invierno."""
        res = self._e2(_sinoptica("C(Santiago)", date(2019, 1, 1), date(2020, 1, 1)))
        self.assertEsquemas(res)
        self.assertEqual(_metrica(res, "R0", 2019)["j_estrella"], 0)
        self.assertEqual(_metrica(res, "R1", 2019)["j_estrella"], 2)
        self.assertEqual(_metrica(res, "2019-04-1")["j_estrella"], 0)     # hasta el atraso del 2019-04-06
        self.assertEqual(_metrica(res, "2019-04-2")["j_estrella"], 2)
        self.assertEqual(_unidad(res, "parte", "2019-07-1"), {"F(0)": I, "F(-3)": I, "F(-4)": C, "C(Santiago)": C})
        self.assertEqual(_anual(res, 2019), FIJAS_INCOMPATIBLES)

    def test_p10_e2_sp_cuenta_como_marca(self):
        """«s/p» en RR06 es marca RR."""
        # extraccion pone rr = True con «s/p» (§3.2). Aquí, filas con sólo RR06 (H = 0, sin valores)
        # cuentan como marcas, como en Copiapó a las 06 h (§6).
        res = self._e2(_sinoptica("F(0)", date(2019, 1, 1), date(2019, 3, 1), solo_rr=True))
        m = _metrica(res, "2019-01-1")
        self.assertEqual((int(m["n_rr"]), bool(m["informativa"])), (31 * 4, True))
        self.assertEqual(_anual(res, 2019), {"F(0)": C, "F(-3)": C, "F(-4)": I, "C(Santiago)": C})

    def test_p10_e2_rr_en_todas_las_horas_o_sin_observador(self):
        """Sin información."""
        todas = self._e2(_sinoptica("F(0)", date(2019, 1, 1), date(2019, 3, 1), horas_utc=tuple(range(24))))
        m = _metrica(todas, "2019-01-1")
        self.assertTrue(bool(m["valida"]))
        self.assertFalse(bool(m["informativa"]))
        self.assertAlmostEqual(m["kappa3"], 1 / 3)
        self.assertEqual(_unidad(todas, "parte", "2019-01-1"), TODO_SIN_INFO)
        self.assertEqual(_anual(todas, 2019), TODO_SIN_INFO)
        sin_obs = self._e2(_sinoptica("F(0)", date(2019, 1, 1), date(2019, 3, 1), observador=False))
        m = _metrica(sin_obs, "2019-01-1")
        self.assertEqual((float(m["frac_observador"]), bool(m["valida"])), (0.0, False))
        self.assertEqual(set(sin_obs.estados.loc[sin_obs.estados["unidad"] == "2019-01-1", "motivo"]),
                         {"sin_observador"})
        self.assertEqual(_anual(sin_obs, 2019), TODO_SIN_INFO)

    def test_p10_e2_tx_discordante_da_dudosa(self):
        """TX fuera de j*: la unidad compatible pasa a dudosa."""
        def anual(**kw):
            return _anual(self._e2(_sinoptica("F(-4)", date(2019, 1, 1), date(2019, 3, 1), **kw)), 2019)
        # F(−4): RR en clase 2 (20/02/08/14). TX a las 00 UTC (20 h) y TN a las 12 UTC (08 h): 12 h y clase 2.
        self.assertEqual(anual(tx=0, tn=12)["F(-4)"], C)
        # TX a las 01 UTC (21 h, clase 0): discordante.
        res = self._e2(_sinoptica("F(-4)", date(2019, 1, 1), date(2019, 3, 1), tx=1, tn=12))
        self.assertEqual(_unidad(res, "parte", "2019-01-1")["F(-4)"], D)
        self.assertEqual(_anual(res, 2019)["F(-4)"], D)
        self.assertEqual(_anual(res, 2019)["F(0)"], I)                  # una incompatible no cambia
        # Clase 2 en ambas, pero las horas modales distan 6 h (TN a las 06 UTC).
        self.assertEqual(anual(tx=0, tn=6)["F(-4)"], D)
        # Lectura A de R-11: con menos de E2_TXTN_MIN marcas de TX no se exige nada.
        pocas = _sinoptica("F(-4)", date(2019, 1, 1), date(2019, 3, 1), tx=1, tn=12)
        dias_tx = sorted(L for L, f in pocas.items() if f.get("tx"))
        for L in dias_tx[int(_U.f("E2_TXTN_MIN")) - 1:]:
            pocas[L]["tx"] = False
        res = self._e2(pocas)
        self.assertEqual(_unidad(res, "parte", "2019-01-1")["F(-4)"], C)

    def test_p10_e2_una_parte_discordante_dos_incompatible(self):
        """Estado anual por §4.0."""
        def estacion(meses_raros):
            filas = _sinoptica("F(0)", date(2019, 1, 1), date(2020, 1, 1))
            for m in meses_raros:            # ese mes, marcas en clase 2 (como F(−4))
                desde = date(2019, m, 1)
                hasta = date(2019, m + 1, 1)
                for L in [L for L in filas if desde <= L.date() < hasta]:
                    del filas[L]
                filas.update(_sinoptica("F(-4)", desde, hasta))
            return self._e2(filas)
        res = estacion([3])
        parte = res.estados[(res.estados["unidad"] == "2019-03-1") & (res.estados["H"] == "F(0)")].iloc[0]
        self.assertEqual((parte["estado"], bool(parte["discordante"])), ("incompatible", True))
        self.assertEqual(_anual(res, 2019)["F(0)"], C)
        res = estacion([3, 11])
        self.assertEqual(_anual(res, 2019)["F(0)"], I)
        self.assertEqual(_anual(res, 2019)["F(-3)"], I)

    def test_e2_compatible_anual_exige_dos_partes(self):
        """Compatible sólo con ≥ 2 partes informativas."""
        res = self._e2(_sinoptica("F(0)", date(2019, 1, 1), date(2019, 2, 1)))
        self.assertEqual(_unidad(res, "regimen", "R0")["F(0)"], C)
        self.assertEqual(_anual(res, 2019), {"F(0)": S, "F(-3)": S, "F(-4)": I, "C(Santiago)": S})
        res = self._e2(_sinoptica("F(0)", date(2019, 1, 1), date(2019, 3, 1)))
        self.assertEqual(_anual(res, 2019), {"F(0)": C, "F(-3)": C, "F(-4)": I, "C(Santiago)": C})

    def test_p10_e2_reglas_vencidas_cv_en_P(self):
        """Diagnóstico (§4.1.4, Enmienda 1 E1-4 en borrador): con las partes cortadas también en las
        etiquetas de Cv(Santiago, 2016), E2 deja compatible sólo a Cv."""
        info = _info(extra=("Cv(Santiago)",))
        res = self._e2(_sinoptica("Cv2016", date(2016, 1, 1), date(2017, 1, 1)), info, _cortar_en_cv_2016)
        self.assertEsquemas(res)
        self.assertEqual(_anual(res, 2016), {"F(0)": I, "F(-3)": I, "F(-4)": I, "C(Santiago)": I,
                                             "Cv(Santiago)": C})
        # Entre el atraso de Cv y el real (2016-04-24 a 05-14) y entre el adelanto real y el de Cv
        # (2016-08-14 a 09-04), Cv tiene −4 y C(Santiago) −3.
        for parte in ("2016-04-2", "2016-08-2"):
            self.assertEqual(_unidad(res, "parte", parte), {"F(0)": I, "F(-3)": I, "F(-4)": C, "C(Santiago)": I,
                                                            "Cv(Santiago)": C}, parte)
        # En R0, Cv mezcla −3 y −4: sin información en ese año-régimen.
        r0 = res.estados[(res.estados["unidad"] == "R0") & (res.estados["H"] == "Cv(Santiago)")
                         & (res.estados["anio"] == 2016)].iloc[0]
        self.assertEqual(r0["estado"], "sin_informacion")
        # Sin cortar en las etiquetas de Cv, la parte 2016-04-1 (abril entero) mezcla sus dos desfases.
        res = self._e2(_sinoptica("F(-4)", date(2016, 1, 1), date(2017, 1, 1)), info)
        fila = res.estados[(res.estados["unidad"] == "2016-04-1") & (res.estados["H"] == "Cv(Santiago)")].iloc[0]
        self.assertEqual((fila["estado"], fila["motivo"]), ("sin_informacion", lineas_registro.MOTIVO_DESFASE))
        self.assertEqual(_unidad(res, "parte", "2016-04-1")["F(-4)"], C)



class PruebasCitasDeLecturas(unittest.TestCase):
    """Las pruebas citan las lecturas propias de lineas_registro (su encabezado, «Lecturas propias de este
    módulo») por número; un número equivocado lleva al revisor a la lectura de otro tema."""

    _ITEM = re.compile(r"^(\d+)\. ", re.M)
    _CITA_AQUI = re.compile(r"\b[Ll]ectura (\d+)\b(?: \(([^)]*)\))?")
    _CITA_FUERA = re.compile(r"lineas_registro, lectura (\d+)\b(?: \(([^)]*)\))?")

    @classmethod
    def _lecturas(cls) -> dict[int, str]:
        doc = lineas_registro.__doc__
        tramo = doc[doc.index("Lecturas propias de este módulo"):doc.index("\nDepende de:")]
        marcas = list(cls._ITEM.finditer(tramo))
        return {int(m.group(1)): " ".join(tramo[m.start():(marcas[i + 1].start() if i + 1 < len(marcas)
                                                           else len(tramo))].split())
                for i, m in enumerate(marcas)}

    @staticmethod
    def _docstrings(ruta: Path):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.ClassDef, ast.Module)):
                doc = ast.get_docstring(nodo)
                if doc:
                    yield getattr(nodo, "name", ruta.name), " ".join(doc.split())

    def test_citas_de_lecturas_con_su_numero(self):
        """Cada «Lectura N» de las docstrings de este archivo, y cada «lineas_registro, lectura N» de las demás
        pruebas, nombra una lectura que existe; si la cita trae un paréntesis («Lectura 10 (R-10 mes por
        mes)»), su texto está en esa lectura."""
        lecturas = self._lecturas()
        self.assertEqual(sorted(lecturas), list(range(1, len(lecturas) + 1)))
        self.assertIn("E1c en Pascua", lecturas[10])
        citas, malas = 0, []
        for ruta in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
            patron = self._CITA_AQUI if ruta.name == Path(__file__).name else self._CITA_FUERA
            for nombre, doc in self._docstrings(ruta):
                for m in patron.finditer(doc):
                    citas += 1
                    n, tema = int(m.group(1)), m.group(2)
                    if n not in lecturas or (tema and tema not in lecturas[n]):
                        malas.append(f"{ruta.name}:{nombre}: «{m.group(0)}»")
        self.assertGreaterEqual(citas, 3)
        self.assertEqual(malas, [], "citas de lecturas de lineas_registro con otro número")


if __name__ == "__main__":
    unittest.main()
