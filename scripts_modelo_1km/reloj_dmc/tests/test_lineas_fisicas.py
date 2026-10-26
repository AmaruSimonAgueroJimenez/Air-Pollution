"""Pruebas de lineas_fisicas.py (E3, regla fina, E4 y E6).

Las que llevan «pNN» son el punto NN de §8 (grupo B). Las series son sintéticas y se fabrican aquí, sin
``sintetico`` ni funciones del módulo: una «atmósfera» horaria en UTC (marea S2 con máximo a 9,75 h
solares, S1, ciclo diario de temperatura, componentes sinópticas y ruido) y relojes verdaderos conocidos;
la etiqueta sale de ``u + c`` (F(c)) o de ``u.astimezone(ZoneInfo(Z))`` (C(Z)), como pide §8. Los
umbrales son los anclados en C0 (si faltan, las pruebas se omiten con el motivo). Correr desde
scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import math  # noqa: E402
import re  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import constantes, estados, lineas_fisicas as lf, numerico, tablas, umbrales  # noqa: E402
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_METRICAS_E3, ESQUEMA_METRICAS_E4, LINEAS, Conjunto,  # noqa: E402
                             ContextoEstacion, Estado, InfoEstacion, Linea, MotivoSinInfo, Nivel, Regla, Territorio,
                             validar_esquema)

_PAQUETE = Path(umbrales.__file__).resolve().parent
_APH = _PAQUETE.parents[1].parent / "Air-Pollution-Health-Chile"
_CACHE = {}

CONTINENTAL = (("America/Santiago",), ("F(0)", "F(-3)", "F(-4)", "C(Santiago)"))
PASCUA = (("Pacific/Easter", "America/Santiago"),
          ("F(0)", "F(-3)", "F(-4)", "F(-5)", "F(-6)", "C(Pacific/Easter)", "C(Santiago)"))
LON = -70.6
LAT = -33.4


def _U():
    if "U" not in _CACHE:
        try:
            _CACHE["U"] = umbrales.cargar_c0(_APH)
        except FileNotFoundError as e:
            raise unittest.SkipTest(f"faltan los umbrales anclados en C0 ({e}); la prueba no se da por aprobada")
    return _CACHE["U"]


def _T():
    if "T" not in _CACHE:
        _CACHE["T"] = tablas.cargar_tablas()
    return _CACHE["T"]


# ---------------------------------------------------------------------------------------------
# Generadores propios de la prueba
# ---------------------------------------------------------------------------------------------
def _eot_spencer_min(dia_del_anio):
    """Ecuación del tiempo (Spencer), escrita aquí aparte de numerico."""
    B = 2 * math.pi * (np.asarray(dia_del_anio, dtype=float) - 1) / 365
    return 229.18 * (0.000075 + 0.001868 * np.cos(B) - 0.032077 * np.sin(B) - 0.014615 * np.cos(2 * B)
                     - 0.040849 * np.sin(2 * B))


def _ar1(rng, n, phi, sigma):
    e = rng.normal(0, sigma, n)
    x = np.empty(n)
    x[0] = e[0] / math.sqrt(1 - phi * phi)
    for k in range(1, n):
        x[k] = phi * x[k - 1] + e[k]
    return x


class _SerieMemoria:
    """SerieEra5 en memoria: eje horario UTC desde t0; NaN fuera del eje o en instantes que no son HH:00."""

    def __init__(self, t0, datos):
        self.t0 = np.datetime64(t0, "h")
        self.datos = datos
        self.n_horas = len(next(iter(next(iter(datos.values())).values())))

    def tiene(self, pixel_id):
        return pixel_id in self.datos

    def valores(self, pixel_id, variable, u):
        x = self.datos[pixel_id][variable]
        k = (np.asarray(u, dtype="datetime64[ns]") - self.t0.astype("datetime64[ns]")) / np.timedelta64(1, "h")
        ok = np.isfinite(k) & (k == np.floor(k)) & (k >= 0) & (k < x.size)
        salida = np.full(k.shape, np.nan)
        salida[ok] = x[k[ok].astype(np.int64)]
        return salida

    def media(self, pixel_id, variable):
        return float(np.nanmean(self.datos[pixel_id][variable]))


class _Atmosfera:
    """Presión y temperatura «verdaderas» por hora UTC en el píxel 1, con fases solares conocidas."""

    def __init__(self, desde, hasta, *, semilla=1, lon=LON, s2=1.0, s1=0.4, ar_p=0.25, ar_t=0.4, periodo_12=False):
        margen = np.timedelta64(3, "D")
        self.u = np.arange(np.datetime64(desde, "h") - margen, np.datetime64(hasta, "h") + margen,
                           dtype="datetime64[h]")
        n = self.u.size
        rng = np.random.default_rng(semilla)
        hora = (self.u - self.u.astype("datetime64[D]")) / np.timedelta64(1, "h")
        dia = (self.u.astype("datetime64[D]") - self.u.astype("datetime64[Y]").astype("datetime64[D]")) \
            / np.timedelta64(1, "D") + 1
        self.solar = hora + lon / 15 + _eot_spencer_min(dia) / 60
        if periodo_12:      # presión exactamente periódica de 12 h (empates exactos)
            base = rng.normal(0, 1, 12)
            self.P = 950 + base[np.arange(n) % 12]
            self.sp = self.P.copy()
        else:
            self.P = (950 + s2 * np.cos(2 * math.pi * 2 * (self.solar - 9.75) / 24)
                      + s1 * np.cos(2 * math.pi * (self.solar - 7) / 24) + _ar1(rng, n, 0.95, ar_p))
            self.sp = self.P + rng.normal(0, 0.05, n)
        self.T = 15 + 6 * np.cos(2 * math.pi * (self.solar - 15) / 24) + _ar1(rng, n, 0.97, ar_t) \
            + _ar1(rng, n, 0.5, 0.3)
        self.t2m = self.T + rng.normal(0, 0.2, n)
        self.rng = rng

    def serie(self):
        return _SerieMemoria(self.u[0], {1: {"t2m": self.t2m, "sp": self.sp}})


def _fijo(c):
    return lambda u: u + np.timedelta64(c, "h")


def _civil(zona):
    z = ZoneInfo(zona)

    def reloj(u):
        return np.array([datetime.fromtimestamp(int(t), tz=timezone.utc).astimezone(z).replace(tzinfo=None)
                         for t in (u.astype("datetime64[s]").astype(np.int64))], dtype="datetime64[ns]")
    return reloj


def _extracto(atm, reloj, desde, hasta, *, paso=1, horas=None, ruido_p=0.1, ruido_t=0.3, qfe=None, ts=None,
              dias=None):
    """Extracto con L = reloj(u). ``qfe``/``ts``: funciones (atm, índices u) → valores, en lugar de P y T."""
    L = reloj(atm.u).astype("datetime64[ns]")
    _, primero = np.unique(L, return_index=True)          # hora civil repetida: queda la primera (como la DMC)
    k = np.sort(primero)
    L = L[k]
    rng = np.random.default_rng(7)
    q = (atm.P[k] if qfe is None else qfe(atm, k)) + rng.normal(0, ruido_p, k.size)
    t = (atm.T[k] if ts is None else ts(atm, k)) + rng.normal(0, ruido_t, k.size)
    hora = pd.DatetimeIndex(L).hour.to_numpy()
    sel = (L >= np.datetime64(desde, "ns")) & (L < np.datetime64(hasta, "ns")) & (hora % paso == 0)
    if horas is not None:
        sel &= np.isin(hora, list(horas))
    if dias is not None:
        sel &= np.isin(L.astype("datetime64[D]"), np.array(dias, dtype="datetime64[D]"))
    L, q, t = L[sel], q[sel], t[sel]
    idx = pd.DatetimeIndex(L)
    return pd.DataFrame({"L": L, "anio": idx.year.astype("int16"), "mes": idx.month.astype("int8"),
                         "ts": np.round(t, 1), "qfe": np.round(q, 1), "hr": np.full(L.size, np.nan)})


def _contexto(extracto, *, territorio=CONTINENTAL, lat=LAT, lon=LON, dz=10.0, costera=False, pixel=1,
              validas=True, inconsistentes=False, exclusion=True, lineas=frozenset()):
    zs, ids = territorio
    T = _T()
    info = InfoEstacion(codigo="999001", nombre="PRUEBA", lat=lat, lon=lon, alt_m=500.0, coordenadas_validas=validas,
                        coordenadas_inconsistentes=inconsistentes, territorio=Territorio.CONTINENTAL, region=13,
                        macrozona="centro", zs=zs, P=tablas.hipotesis_de_P(ids), pixel_id=pixel, distancia_km=1.0,
                        costera=costera, z_pix=490.0, dz=dz, conjunto=Conjunto.V)
    anotado = tablas.anotar_partes(extracto, info, T)
    anios = tuple(sorted(set(anotado["anio"].astype(int))))
    regimenes = {a: tablas.regimenes_del_anio(zs, a, T) for a in anios}
    util = anotado[~anotado["especial"]]
    con_datos = {a: tuple(sorted(set(util.loc[util["anio"] == a, "regimen"].dropna()))) for a in anios}
    clases = {a: tablas.fusionar(info.P, [r for r in regimenes[a] if r.id in con_datos[a]], zs) for a in anios}
    meses = {a: tuple(sorted(set(anotado.loc[anotado["anio"] == a, "mes"].astype(int)))) for a in anios}
    ctx = ContextoEstacion(info=info, tablas=T, umbrales=_U(), anios=anios, regimenes=regimenes,
                           regimenes_con_datos=con_datos, clases=clases, meses_con_datos=meses,
                           lineas_activas=frozenset(lineas), aplicar_exclusion_costera=exclusion)
    return anotado, ctx


def _estacion(reloj, desde="2019-01-01", hasta="2019-03-01", *, atm=None, semilla=1, **kw):
    atm = atm or _Atmosfera(desde, hasta, semilla=semilla)
    ext_kw = {k: kw.pop(k) for k in ("paso", "horas", "ruido_p", "ruido_t", "qfe", "ts", "dias") if k in kw}
    anotado, ctx = _contexto(_extracto(atm, reloj, desde, hasta, **ext_kw), **kw)
    return anotado, atm.serie(), ctx


def _estado(res, nivel, unidad, H, regla=None):
    e = res.estados
    sel = (e["nivel"] == str(nivel)) & (e["unidad"] == unidad) & (e["H"] == H)
    if regla is not None:
        sel &= e["regla"] == str(regla)
    filas = e[sel]
    assert len(filas) == 1, (nivel, unidad, H, len(filas))
    return filas.iloc[0]


def _metrica(res, nivel, unidad):
    m = res.metricas
    filas = m[(m["nivel"] == str(nivel)) & (m["unidad"] == unidad)]
    assert len(filas) == 1, (nivel, unidad, len(filas))
    return filas.iloc[0]


# ---------------------------------------------------------------------------------------------
# E3
# ---------------------------------------------------------------------------------------------
def _paso_por_minutos(t: np.ndarray) -> int | None:
    """La regla que tenía pasos_por_mes antes de la ola 3 (moda de diferencias en minutos), por camino propio."""
    if t.size < 2:
        return None
    valores, cuentas = np.unique(np.diff(np.sort(t)) / np.timedelta64(1, "m"), return_counts=True)
    p = float(valores[np.argmax(cuentas)]) / 60
    return int(p) if p == int(p) else None


class PruebasPasoNativo(unittest.TestCase):
    def test_paso_nativo_una_sola_regla(self):
        """pasos_por_mes (E3, E4) y extraccion.paso_nativo (p_v de los meses) dan lo mismo mes a mes."""
        from reloj_dmc import constantes, extraccion
        validos = set(constantes.valor("PASOS_NATIVOS"))
        rng = np.random.default_rng(20261024)
        # (mes, horas del mes con valor): pasos 1, 2, 3, 6 y 4 (no nativo), empate 1-2, un valor, sin valores,
        # semanal (168 h) y meses al azar con huecos.
        fijos = {1: range(0, 744, 1), 2: range(0, 672, 3), 3: range(0, 744, 6), 4: range(0, 720, 2),
                 5: range(0, 744, 4), 6: [0, 1, 2, 4, 6], 7: [5], 8: [], 9: [0, 168, 336, 504]}
        L, ts, qfe = [], [], []
        for mes in range(1, 25):
            anio, m = 2019 + (mes - 1) // 12, (mes - 1) % 12 + 1
            inicio = np.datetime64(f"{anio}-{m:02d}-01T00", "h")
            n = int((np.datetime64(f"{anio + m // 12}-{m % 12 + 1:02d}-01T00", "h") - inicio) // np.timedelta64(1, "h"))
            horas = np.arange(n)
            con_ts = np.isin(horas, list(fijos[mes])) if mes in fijos else rng.random(n) < rng.choice([0.3, 0.6, 0.9])
            con_qfe = (horas % rng.choice([1, 3, 6]) == 0) & (rng.random(n) < 0.8)
            L.append(inicio + horas.astype("timedelta64[h]"))
            ts.append(np.where(con_ts, 15.0, np.nan))
            qfe.append(np.where(con_qfe, 950.0, np.nan))
        ext = pd.DataFrame({"L": np.concatenate(L).astype("datetime64[ns]"), "ts": np.concatenate(ts),
                            "qfe": np.concatenate(qfe)})
        vistos = set()
        for variable, col in (("Ts", "ts"), ("QFE", "qfe")):
            por_mes = lf.pasos_por_mes(ext, variable)
            for (anio, m), grupo in ext.groupby([ext["L"].dt.year, ext["L"].dt.month]):
                t = grupo["L"].to_numpy(dtype="datetime64[ns]")[grupo[col].notna().to_numpy()]
                p_meses = extraccion.paso_nativo(t)
                self.assertEqual(p_meses, numerico.paso_nativo(t))
                self.assertEqual(p_meses, _paso_por_minutos(t))          # la regla de antes, sin cambios
                esperado = p_meses if p_meses in validos else None
                self.assertEqual(por_mes.get((int(anio), int(m))), esperado, (variable, anio, m))
                vistos.add(p_meses)
        self.assertTrue({None, 1, 2, 3, 4, 6, 168} <= vistos, vistos)
        with self.assertRaises(ValueError):                              # etiquetas que no son horas enteras
            lf.pasos_por_mes(pd.DataFrame({"L": pd.to_datetime(["2019-01-01 00:00", "2019-01-01 00:30"]),
                                           "ts": [1.0, 2.0]}), "Ts")


class PruebasE3(unittest.TestCase):
    def test_p11_e3_recupera_desfases(self):
        """c ∈ {0, −3, −4, −6}."""
        for c, territorio in ((0, CONTINENTAL), (-3, CONTINENTAL), (-4, CONTINENTAL), (-6, PASCUA)):
            with self.subTest(c=c):
                anotado, serie, ctx = _estacion(_fijo(c), territorio=territorio, semilla=10 + c)
                for variable in ("QFE", "Ts"):
                    res = lf.e3(anotado, serie, ctx, variable)
                    validar_esquema(res.estados, ESQUEMA_ESTADOS, nombre="estados")
                    validar_esquema(res.metricas, ESQUEMA_METRICAS_E3, nombre="métricas")
                    m = _metrica(res, Nivel.REGIMEN, "R0")
                    self.assertEqual(int(m["c_hat"]), c, variable)
                    self.assertLess(abs(m["c_hat_cont"] - c), 0.3, variable)
                    self.assertEqual(len(m["r"]), 19)
                    h_ok = f"F({c:+d})" if c else "F(0)"
                    self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", h_ok)["estado"], Estado.COMPATIBLE, variable)
                    for h in ctx.info.P:
                        c_h = tablas.desfase(h, ctx.regimenes[2019][0], ctx.info.zs)
                        fila = _estado(res, Nivel.REGIMEN, "R0", h.id)
                        self.assertFalse(fila["reloj_anomalo"])
                        if abs(c_h - c) >= 2:
                            self.assertEqual(fila["estado"], Estado.INCOMPATIBLE, (variable, h.id))
                        elif c_h == c:
                            self.assertEqual(fila["estado"], Estado.COMPATIBLE, (variable, h.id))
                    if variable == "QFE":
                        self.assertGreaterEqual(m["estab_c_hat"], 0.99)
                        self.assertEqual(int(m["c_hat_f"]), c)
                        # las partes (enero y febrero) también se evalúan solas
                        self.assertEqual(_estado(res, Nivel.PARTE, "2019-01-1", h_ok)["estado"], Estado.COMPATIBLE)

    def test_p11_e3_reloj_anomalo(self):
        """ĉ estable de +2, −1, −2 o +1."""
        for c in (2, -1, -2, 1):
            with self.subTest(c=c):
                anotado, serie, ctx = _estacion(_fijo(c), semilla=20 + c)
                res = lf.e3(anotado, serie, ctx, "QFE")
                m = _metrica(res, Nivel.REGIMEN, "R0")
                self.assertEqual(int(m["c_hat"]), c)
                self.assertGreaterEqual(m["estab_c_hat"], 0.99)
                fila = _estado(res, Nivel.REGIMEN, "R0", "F(0)")
                self.assertTrue(fila["reloj_anomalo"])
                anual = _estado(res, Nivel.ANIO, "2019", "F(0)", Regla.GRUESA)
                self.assertTrue(anual["reloj_anomalo"])
                self.assertTrue(res.estados.loc[res.estados["unidad"] == "R0", "reloj_anomalo"].all())

    def test_p11_e3_alias_12h(self):
        """Texto del v1: «−8 con F(−4) en P es alias». Por la definición de §4.3.1 el alias de −4 es +8
        (CONTRADICCIÓN R-01). La Enmienda 1, punto E1-1 (adoptada; v1.0.1), lo corrige: «+8 con F(−4) en P es
        alias de 12 h, no reloj anómalo»; «−8 … sin una H de desfase +4 … es reloj anómalo si cumple el margen».
        También E1-3 (glosa del reloj anómalo): +8 es positivo, pero es alias de 12 h de F(−4), no anómalo."""
        anotado, serie, ctx = _estacion(_fijo(8), semilla=31)
        res = lf.e3(anotado, serie, ctx, "QFE")
        self.assertEqual(int(_metrica(res, Nivel.REGIMEN, "R0")["c_hat"]), 8)
        self.assertTrue(numerico.es_alias_12(8, -4))
        for h in ctx.info.P:
            fila = _estado(res, Nivel.REGIMEN, "R0", h.id)
            self.assertEqual(fila["estado"], Estado.SIN_INFORMACION)
            self.assertEqual(fila["motivo"], "alias")
            self.assertFalse(fila["reloj_anomalo"])
        anotado, serie, ctx = _estacion(_fijo(-8), semilla=32)
        res = lf.e3(anotado, serie, ctx, "QFE")
        self.assertEqual(int(_metrica(res, Nivel.REGIMEN, "R0")["c_hat"]), -8)
        self.assertTrue(_estado(res, Nivel.REGIMEN, "R0", "F(-4)")["reloj_anomalo"])

    def test_p11_e3_empate_exacto(self):
        """ĉ indefinido y unidad sin información."""
        atm = _Atmosfera("2019-01-01", "2019-03-01", semilla=3, periodo_12=True)
        anotado, serie, ctx = _estacion(_fijo(-4), atm=atm, ruido_p=0.0)
        anotado["qfe"] = anotado["qfe"].astype(float)
        res = lf.e3(anotado, serie, ctx, "QFE")
        m = _metrica(res, Nivel.REGIMEN, "R0")
        r = np.array(m["r"])
        self.assertEqual(r[lf.ventana(ctx.umbrales).index(-4)], r[lf.ventana(ctx.umbrales).index(8)])
        self.assertTrue(pd.isna(m["c_hat"]))
        for h in ctx.info.P:
            fila = _estado(res, Nivel.REGIMEN, "R0", h.id)
            self.assertEqual((fila["estado"], fila["motivo"]), (Estado.SIN_INFORMACION, "empate"))
        self.assertIsNone(numerico.maximo_estricto(r, lf.ventana(ctx.umbrales)))

    def test_p11_e3_sin_pares_a_traves_de_huecos(self):
        """Paso 3 h y ventana diurna."""
        dias = [d for d in pd.date_range("2019-03-20", "2019-04-20", freq="D") if d.day != 1]
        anotado, serie, ctx = _estacion(_civil("America/Santiago"), "2019-03-20", "2019-04-20", paso=3,
                                        dias=[d.date() for d in dias])
        pares = lf.pares_e3(anotado, serie, ctx, "QFE")
        self.assertGreater(len(pares), 0)
        self.assertTrue((pares["paso_h"] == 3).all())
        etiquetas = anotado[~anotado["especial"]].set_index("L")["parte"]
        previa = pares["L"] - pd.to_timedelta(pares["paso_h"], unit="h")
        partes = pares.loc[pares["nivel"] == "parte", "unidad"].to_numpy()
        prev_partes = etiquetas.reindex(previa[pares["nivel"] == "parte"]).to_numpy()
        self.assertTrue((prev_partes == partes).all(), "un par cruza un hueco o un cambio de hora")
        self.assertFalse((pares["L"].dt.normalize() == pd.Timestamp("2019-04-01")).any())
        self.assertFalse(((pares["L"].dt.normalize() == pd.Timestamp("2019-04-02")) & (pares["L"].dt.hour == 0)).any())
        cambio = pd.Timestamp("2019-04-07 00:00")      # primera etiqueta de la parte 2019-04-2 (atraso)
        self.assertFalse((pares["L"] == cambio).any(), "par a través del cambio de hora")
        # ventana diurna (08-20 h), paso 1: no hay par a las 08 h
        anotado, serie, ctx = _estacion(_fijo(-4), horas=range(8, 21))
        pares = lf.pares_e3(anotado, serie, ctx, "QFE")
        self.assertTrue((pares["paso_h"] == 1).all())
        self.assertFalse((pares["L"].dt.hour == 8).any())
        self.assertEqual(set(pares["L"].dt.hour), set(range(9, 21)))
        # con filtrada, los mismos pares
        filtrados = lf.pares_e3(anotado, serie, ctx, "QFE", filtrada=True)
        self.assertTrue((filtrados["L"].to_numpy() == pares["L"].to_numpy()).all())
        self.assertFalse(np.allclose(filtrados["dy"], pares["dy"]))

    def test_p11_e3_parte_de_5_dias_no_se_evalua_sola(self):
        """Menos de 6 bloques: sus pares cuentan en el año-régimen."""
        dias = [d.date() for d in pd.date_range("2019-01-01", "2019-03-05", freq="D")]
        anotado, serie, ctx = _estacion(_fijo(-3), "2019-01-01", "2019-03-06", dias=dias, semilla=5)
        res = lf.e3(anotado, serie, ctx, "QFE")
        marzo = _metrica(res, Nivel.PARTE, "2019-03-1")
        self.assertGreater(marzo["n_pares"], 0)
        self.assertLess(marzo["n_bloques"], ctx.umbrales.f("E3_BLOQUES_PARTE"))
        fila = _estado(res, Nivel.PARTE, "2019-03-1", "F(-3)")
        self.assertEqual((fila["estado"], fila["motivo"]), (Estado.SIN_INFORMACION, "minimos"))
        partes = res.metricas[res.metricas["nivel"] == "parte"]
        self.assertEqual(int(_metrica(res, Nivel.REGIMEN, "R0")["n_pares"]), int(partes["n_pares"].sum()))
        self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", "F(-3)")["estado"], Estado.COMPATIBLE)

    def test_p05_coordenadas_no_interpretables_dan_sin_informacion(self):
        """E3 y E4 sin información."""
        for kw in ({"validas": False}, {"inconsistentes": True}):
            with self.subTest(**kw):
                anotado, serie, ctx = _estacion(_fijo(0), **kw)
                for variable in ("QFE", "Ts"):
                    res = lf.e3(anotado, serie, ctx, variable)
                    self.assertGreater(len(res.estados), 0)
                    self.assertTrue((res.estados["estado"] == Estado.SIN_INFORMACION).all())
                    self.assertEqual(set(res.estados.loc[res.estados["nivel"] == "regimen", "motivo"]), {"coordenadas"})
                    self.assertEqual(len(res.metricas), 0)
                self.assertEqual(len(lf.ajustes_e4(anotado, ctx, "QFE")), 0)
                r4 = lf.e4p(lf.ajustes_e4(anotado, ctx, "QFE"), ctx)
                self.assertTrue((r4.estados["estado"] == Estado.SIN_INFORMACION).all())
                self.assertIn("coordenadas", set(r4.estados["motivo"]))
                self.assertEqual(len(lf.pares_e3(anotado, serie, ctx, "QFE")), 0)
        anotado, serie, ctx = _estacion(_fijo(0), pixel=None)
        res = lf.e3(anotado, serie, ctx, "QFE")
        self.assertEqual(set(res.estados.loc[res.estados["nivel"] == "regimen", "motivo"]), {"sin_pixel"})

    def test_e3t_filtro_de_representatividad(self):
        """Δz, costera, cociente de A1 y correlación diaria."""
        atm = _Atmosfera("2019-01-01", "2019-03-01", semilla=41)

        def filtro(**kw):
            anotado, serie, ctx = _estacion(_fijo(-3), atm=atm, **kw)
            f = lf.filtro_representatividad(anotado, serie, ctx)
            self.assertEqual(list(f.columns), list(lf.COLUMNAS_FILTRO))
            return f.iloc[0], anotado, serie, ctx

        base, anotado, serie, ctx = filtro()
        self.assertTrue(base["pasa"])
        self.assertLess(abs(base["cociente_a1"] - 1), 0.15)
        self.assertGreater(base["r_diaria"], 0.9)
        self.assertFalse(filtro(dz=500.0)[0]["pasa"])
        self.assertTrue(filtro(dz=-390.0)[0]["pasa"])
        self.assertFalse(filtro(dz=None)[0]["pasa"])
        self.assertFalse(filtro(costera=True)[0]["pasa"])
        self.assertTrue(filtro(costera=True, exclusion=False)[0]["pasa"])
        amplia = filtro(ts=lambda a, k: a.T[k] + 12 * np.cos(2 * math.pi * (a.solar[k] - 15) / 24))[0]
        self.assertFalse(amplia["pasa"])
        self.assertGreater(amplia["cociente_a1"], 2)
        otra = _Atmosfera("2019-01-01", "2019-03-01", semilla=42, ar_t=1.5)
        ajena = filtro(ts=lambda a, k: otra.T[k])[0]
        self.assertFalse(ajena["pasa"])
        self.assertLess(ajena["r_diaria"], 0.8)
        # con el filtro fallado o sin desnivel, E3t queda sin información con su motivo
        anotado, serie, ctx = _estacion(_fijo(-3), atm=atm, ts=lambda a, k: otra.T[k])
        fila = _estado(lf.e3(anotado, serie, ctx, "Ts"), Nivel.REGIMEN, "R0", "F(-3)")
        self.assertEqual((fila["estado"], fila["motivo"]), (Estado.SIN_INFORMACION, "filtro_representatividad"))
        anotado, serie, ctx = _estacion(_fijo(-3), atm=atm, dz=None)
        res = lf.e3(anotado, serie, ctx, "Ts")
        self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", "F(-3)")["motivo"], "sin_desnivel")
        self.assertEqual(int(_metrica(res, Nivel.REGIMEN, "R0")["c_hat"]), -3)      # se calcula para el informe

    def test_e3t_no_excluye_ni_senala_anomalia(self):
        """Sus incompatibilidades sólo van a T-P, informe y apoyo en modo completo. Así lo dice el v1.0.1 desde
        la Enmienda 1, punto E1-2 (adoptada): en modo completo, la incompatibilidad sirve también al apoyo del
        paso 7."""
        anotado, serie, ctx = _estacion(_fijo(2), semilla=51)
        res = lf.e3(anotado, serie, ctx, "Ts")
        self.assertEqual(res.linea, Linea.E3T)
        self.assertEqual(int(_metrica(res, Nivel.REGIMEN, "R0")["c_hat"]), 2)
        self.assertFalse(res.estados["reloj_anomalo"].any())
        self.assertIn(Estado.INCOMPATIBLE, set(res.estados["estado"]))
        self.assertIn("anomalo_informativo", set(res.estados["motivo"].dropna()))
        self.assertEqual(set(res.estados["regla"]), {"gruesa"})
        self.assertFalse(LINEAS[Linea.E3T].excluye)
        self.assertFalse(LINEAS[Linea.E3T].no_termica)
        # E3t no remuestrea
        self.assertTrue(res.metricas["estab_c_hat"].isna().all())
        # y el anual de E3t (LF-7) existe para T-P y para el apoyo en modo completo
        anotado, serie, ctx = _estacion(_fijo(-4), semilla=52)
        res = lf.e3(anotado, serie, ctx, "Ts")
        self.assertEqual(_estado(res, Nivel.ANIO, "2019", "F(-4)")["estado"], Estado.COMPATIBLE)
        self.assertEqual(_estado(res, Nivel.ANIO, "2019", "F(0)")["estado"], Estado.INCOMPATIBLE)

    def test_replicas_son_pearson_de_sus_filas(self):
        """LF-3: r(c) por sumas de bloque = Pearson de las filas de la réplica; misma semilla, mismas réplicas."""
        rng = np.random.default_rng(3)
        n, k = 900, 19
        dx = rng.normal(size=(k, n))
        dy = dx[5] + rng.normal(size=n)
        bloques = np.repeat(np.arange(30), 30)
        pesos = lf._pesos(bloques, 50, numerico.generador(123))
        r = lf._r_replicas(dy, dx, pesos)
        indices = numerico.replicas_por_bloques(bloques, 50, numerico.generador(123))
        for q, idx in enumerate(indices):
            exacto = numerico.correlaciones_por_desfase(dy[idx], dx[:, idx])
            np.testing.assert_allclose(r[q], exacto, rtol=0, atol=1e-12)

    def test_e3_determinista_y_semilla_por_unidad(self):
        """Dos corridas dan lo mismo; la semilla depende de la unidad (R-13)."""
        anotado, serie, ctx = _estacion(_fijo(-4), semilla=61)
        a = lf.e3(anotado, serie, ctx, "QFE")
        b = lf.e3(anotado, serie, ctx, "QFE")
        pd.testing.assert_frame_equal(a.estados, b.estados)
        pd.testing.assert_frame_equal(a.metricas, b.metricas)
        self.assertNotEqual(numerico.semilla(20261022, "999001", 2019, "R0", "QFE"),
                            numerico.semilla(20261022, "999001", 2019, "2019-01-1", "QFE"))


# ---------------------------------------------------------------------------------------------
# Regla fina
# ---------------------------------------------------------------------------------------------
def _s1_local(desfase_h, amplitud=2.0):
    return lambda a, k: a.P[k] + amplitud * np.cos(2 * math.pi * (a.solar[k] - 7 - desfase_h) / 24)


class PruebasReglaFina(unittest.TestCase):
    def test_p12_fina_separa_civil_de_f_menos4_con_s1_local(self):
        """S1 local de 2 hPa desfasado 4 h: el filtro de 24 h lo quita."""
        atm = _Atmosfera("2019-02-01", "2019-06-01", semilla=71, s1=1.0)
        anotado, serie, ctx = _estacion(_civil("America/Santiago"), "2019-02-01", "2019-06-01", atm=atm,
                                        qfe=_s1_local(4))
        gruesa = lf.e3(anotado, serie, ctx, "QFE")
        for reg, c in (("R0", -3), ("R1", -4)):
            m = _metrica(gruesa, Nivel.REGIMEN, reg)
            self.assertEqual(int(m["c_hat_f"]), c)
            self.assertTrue(m["fino"], reg)
            self.assertLessEqual(abs(m["c_hat_f_cont"] - c), abs(m["c_hat_cont"] - c) + 1e-9)
        fina = lf.e3_fina(gruesa.metricas, ctx)
        validar_esquema(fina.estados, ESQUEMA_ESTADOS, nombre="fina")
        self.assertEqual(set(fina.estados["regla"]), {"fina"})
        anual = {h: _estado(fina, Nivel.ANIO, "2019", h)["estado"] for h in ("C(Santiago)", "F(-3)", "F(-4)", "F(0)")}
        self.assertEqual(anual, {"C(Santiago)": Estado.COMPATIBLE, "F(-3)": Estado.INCOMPATIBLE,
                                 "F(-4)": Estado.INCOMPATIBLE, "F(0)": Estado.INCOMPATIBLE})
        self.assertFalse(fina.estados["reloj_anomalo"].any())
        combinado = lf.e3p_anual(gruesa.estados, fina.estados, True)
        por_h = dict(zip(combinado["H"], combinado["estado"]))
        self.assertEqual(por_h["C(Santiago)"], Estado.COMPATIBLE)
        self.assertEqual(por_h["F(-4)"], Estado.INCOMPATIBLE)
        self.assertEqual(set(combinado["regla"]), {"unica"})
        # sin la fina (A3 o apagado), la gruesa sola no separa la civil de F(−4)
        sola = dict(zip(*lf.e3p_anual(gruesa.estados, fina.estados, False)[["H", "estado"]].T.to_numpy()))
        self.assertNotEqual(sola["F(-4)"], Estado.INCOMPATIBLE)

    def test_p12_media_horaria_no_es_fina(self):
        """|ĉ^f_cont − ĉ^f| > 0,25: no es año-régimen fino."""
        atm = _Atmosfera("2019-02-01", "2019-06-01", semilla=81)

        def media_hora(a, k):
            return (a.P[k] + a.P[k - 1]) / 2          # media de la hora que termina en la etiqueta
        anotado, serie, ctx = _estacion(_civil("America/Santiago"), "2019-02-01", "2019-06-01", atm=atm,
                                        qfe=media_hora)
        gruesa = lf.e3(anotado, serie, ctx, "QFE")
        for reg, c in (("R0", -3), ("R1", -4)):
            m = _metrica(gruesa, Nivel.REGIMEN, reg)
            self.assertFalse(m["fino"], reg)
            self.assertLess(abs(m["c_hat_f_cont"] - (c + 0.5)), 0.1)          # corrimiento de media hora
            self.assertGreater(abs(m["c_hat_f_cont"] - m["c_hat_f"]), ctx.umbrales.a("E3P_FINA_TAU"))
            self.assertFalse(_estado(gruesa, Nivel.REGIMEN, reg, "F(0)")["reloj_anomalo"])
        fina = lf.e3_fina(gruesa.metricas, ctx)
        regs = fina.estados[fina.estados["nivel"] == "regimen"]
        self.assertTrue((regs["estado"] == Estado.SIN_INFORMACION).all())
        self.assertTrue(regs["motivo"].str.startswith("no_fino").all())
        # el diagnóstico subhorario sí ve el corrimiento de ~0,5 h (B6: media circular de período 1 h, que
        # cerca de ±0,5 h puede quedar en cualquiera de los dos bordes de [−0,5; 0,5))
        d = lf.diagnostico_subhorario(gruesa.metricas, ctx)
        self.assertEqual(d["n"], 2)
        self.assertGreater(abs(d["rho"]), 0.35)
        self.assertFalse(d["marca"])           # con < 6 años-régimen no marca

    def test_diagnostico_subhorario_marca_con_6_anios_regimen(self):
        """§4.3.5 con la Enmienda 3 (B6, LF-18): ρ es la media circular de período 1 h de ĉ^f_cont en todos los
        años-régimen de la estación (no sólo los de años confirmados, ni restando c_H(R)), llevada a [−0,5; 0,5);
        marca con |ρ| > 0,35 h y ≥ 6 años-régimen; |lat| > 50° no entra."""
        anotado, serie, ctx = _estacion(_fijo(-3))

        def metricas(corrimientos, anios=(2016, 2017, 2018)):
            filas = []
            for k, anio in enumerate(anios):
                for reg in ("R0", "R1"):
                    fila = {c: None for c in ESQUEMA_METRICAS_E3}
                    fila.update(codigo="999001", anio=anio, nivel="regimen", unidad=reg, regimen=reg, variable="QFE",
                                n_pares=2000, n_bloques=30,
                                c_hat_f_cont=(-3 if reg == "R0" else -4) + corrimientos[k % len(corrimientos)],
                                estab_c_hat=1.0, estab_c_hat_f=1.0, c_hat_cont=np.nan, fino=False, filtro_e3t=False,
                                cociente_a1=np.nan, r_diaria=np.nan)
                    filas.append(fila)
            return pd.DataFrame(filas, columns=list(ESQUEMA_METRICAS_E3)).astype(ESQUEMA_METRICAS_E3)

        m = metricas((0.45,))
        ctx2 = ContextoEstacion(**{**ctx.__dict__, "anios": (2016, 2017, 2018),
                                   "regimenes": {a: tablas.regimenes_del_anio(ctx.info.zs, a, ctx.tablas)
                                                 for a in (2016, 2017, 2018)}})
        d = lf.diagnostico_subhorario(m, ctx2)
        self.assertEqual(d["n"], 6)
        self.assertAlmostEqual(d["rho"], 0.45)
        self.assertTrue(d["marca"])
        # Es la misma función que m de A5 (media circular de período 1 h en [−0,5; 0,5)).
        self.assertAlmostEqual(d["rho"], numerico.media_circular_en(m["c_hat_f_cont"].to_numpy(dtype=float),
                                                                     constantes.valor("A5_ENVOLVER")))
        # Circular: −0,45 y +0,55 son el mismo corrimiento; una mediana lineal de los ĉ^f_cont − c_H daría ≈ 0,05.
        d = lf.diagnostico_subhorario(metricas((-0.45, 0.55)), ctx2)
        self.assertAlmostEqual(abs(d["rho"]), 0.45)
        self.assertTrue(d["marca"])
        # Con 4 años-régimen no marca; un corrimiento de 0,2 h tampoco.
        self.assertFalse(lf.diagnostico_subhorario(metricas((0.45,), anios=(2016, 2017)), ctx2)["marca"])
        self.assertFalse(lf.diagnostico_subhorario(metricas((0.2,)), ctx2)["marca"])
        # ĉ^f_cont indefinido no cuenta.
        m_nan = m.copy()
        m_nan.loc[m_nan["anio"] == 2018, "c_hat_f_cont"] = np.nan
        self.assertEqual(lf.diagnostico_subhorario(m_nan, ctx2)["n"], 4)
        # Al sur de 50° S no entra ningún año-régimen.
        info_sur = ctx2.info.__class__(**{**ctx2.info.__dict__, "lat": -53.0})
        ctx_sur = ContextoEstacion(**{**ctx2.__dict__, "info": info_sur})
        sur = lf.diagnostico_subhorario(m, ctx_sur)
        self.assertEqual((sur["n"], sur["marca"]), (0, False))
        self.assertTrue(np.isnan(sur["rho"]))

    def test_e3p_anual_gruesa_y_fina(self):
        """§4.3.4 «E3p anual» y apagado por estación."""
        hs = ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")
        C, I, S = Estado.COMPATIBLE, Estado.INCOMPATIBLE, Estado.SIN_INFORMACION

        def tabla(regla, filas, anomalo=()):
            marcos = [estados.filas_estado("999001", 2019, Linea.E3P, Nivel(n), u, dict(zip(hs, e)), regla=regla,
                                           reloj_anomalo=(n, u) in anomalo) for n, u, e in filas]
            return pd.concat(marcos, ignore_index=True).astype(ESQUEMA_ESTADOS)

        gruesa = tabla(Regla.GRUESA, [("regimen", "R0", (I, C, S, C)), ("regimen", "R1", (I, S, S, S)),
                                      ("parte", "2019-02-1", (S, S, S, S))])
        fina = tabla(Regla.FINA, [("regimen", "R0", (I, C, I, C)), ("regimen", "R1", (I, I, C, C)),
                                  ("anio", "2019", (I, I, I, C))])
        a = lf.e3p_anual(gruesa, fina, True)
        validar_esquema(a, ESQUEMA_ESTADOS, nombre="anual")
        self.assertEqual(dict(zip(a["H"], a["estado"])), {"F(0)": I, "F(-3)": I, "F(-4)": I, "C(Santiago)": C})
        self.assertEqual(dict(zip(a["H"], a["motivo"]))["F(-3)"], "fina")
        self.assertEqual(dict(zip(a["H"], a["motivo"]))["F(0)"], "gruesa,fina")
        # sin la fina (variante R, LF-17): R0 y R1 son informativos para todas las H (la gruesa da F(0)
        # incompatible en R1); F(−3) y C(Santiago) son compatibles en R0 pero residuales en R1.
        b = dict(zip(*lf.e3p_anual(gruesa, fina, False)[["H", "estado"]].T.to_numpy()))
        self.assertEqual(b, {"F(0)": I, "F(-3)": S, "F(-4)": S, "C(Santiago)": S})
        # una sola parte incompatible es discordante y no cambia el anual; dos sí
        g2 = tabla(Regla.GRUESA, [("regimen", "R0", (S, S, S, S)), ("parte", "2019-02-1", (S, I, S, S)),
                                  ("parte", "2019-03-1", (S, I, S, S)), ("parte", "2019-04-1", (S, S, I, S))])
        c = dict(zip(*lf.e3p_anual(g2, fina.iloc[:0], True)[["H", "estado"]].T.to_numpy()))
        self.assertEqual(c["F(-3)"], I)
        self.assertEqual(c["F(-4)"], S)
        # reloj anómalo de la fina sólo con la fina activa
        f_anom = tabla(Regla.FINA, [("regimen", "R0", (S, S, S, S)), ("anio", "2019", (S, S, S, S))],
                       anomalo={("anio", "2019"), ("regimen", "R0")})
        self.assertTrue(lf.e3p_anual(gruesa, f_anom, True)["reloj_anomalo"].all())
        self.assertFalse(lf.e3p_anual(gruesa, f_anom, False)["reloj_anomalo"].any())

        # apagado: mediana de (ĉ^f_cont − ĉ^f) de los finos > E3P_FINA_APAGADO
        anotado, serie, ctx = _estacion(_fijo(-3))

        def metricas(desvio):
            filas = []
            for reg, c in (("R0", -3),):
                fila = {k: None for k in ESQUEMA_METRICAS_E3}
                fila.update(codigo="999001", anio=2019, nivel="regimen", unidad=reg, regimen=reg, variable="QFE",
                            n_pares=2000, n_bloques=30, r=[0.1] * 19, r_f=[0.5] * 19, c_hat=c, c_hat_cont=float(c),
                            c_hat_f=c, c_hat_f_cont=c + desvio, estab_c_hat=1.0, estab_c_hat_f=1.0, fino=False,
                            filtro_e3t=False, cociente_a1=np.nan, r_diaria=np.nan)
                filas.append(fila)
            return pd.DataFrame(filas, columns=list(ESQUEMA_METRICAS_E3)).astype(ESQUEMA_METRICAS_E3)

        encendida = lf.e3_fina(metricas(0.1), ctx)
        self.assertEqual(_estado(encendida, Nivel.ANIO, "2019", "F(-3)")["estado"], Estado.COMPATIBLE)
        self.assertTrue(encendida.metricas["fino"].all())
        self.assertFalse((encendida.estados["nivel"] == "estacion").any())
        apagada = lf.e3_fina(metricas(0.22), ctx)
        self.assertEqual(lf.fina_apagada(metricas(0.22), ctx)[0], True)
        self.assertTrue((apagada.estados["estado"] == Estado.SIN_INFORMACION).all())
        self.assertEqual(set(apagada.estados["motivo"]), {"apagada"})
        self.assertTrue((apagada.estados["nivel"] == "estacion").any())

    def test_e3p_anual_r52_informativo_por_h(self):
        """R-52 [D] y LF-17, VARIANTE R: «informativo» se lee por año-régimen (el nombre de la prueba se conserva
        para la traza). Dos casos con la misma forma, los estados que dan las trazas de C.21 y de la celda
        «Cv × tipo a» (E3-2): R0 no es fino y su gruesa deja residual a la candidata, pero da compatible o
        incompatible a otras H; R1 es fino y compatible con la candidata.
        - C.21 (año UTC con marzo en −4): R0 residual para F(0) e incompatible para las rivales. R0 cuenta para
          F(0), así que E3p no es compatible con F(0) (residual): E3p ya no apoya y el año queda insuficiente.
        - Cv × a: R0 incompatible para F(0) y residual para las demás. R0 cuenta para F(−4): E3p no es
          compatible con F(−4) y ya no apoya la confirmación errónea.
        Con la lectura por H (la del paquete real) E3p era compatible con la candidata en los dos."""
        hs = ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")
        C, I, S = Estado.COMPATIBLE, Estado.INCOMPATIBLE, Estado.SIN_INFORMACION

        def tabla(regla, filas):
            marcos = [estados.filas_estado("999001", 2019, Linea.E3P, Nivel(n), u, dict(zip(hs, e)), regla=regla)
                      for n, u, e in filas]
            return pd.concat(marcos, ignore_index=True).astype(ESQUEMA_ESTADOS)

        A, R0, R1 = ("anio", "2019"), ("regimen", "R0"), ("regimen", "R1")
        casos = {      # nombre: (gruesa, fina, E3p anual esperado), estados en el orden de hs
            "C.21": ([(*A, (S, I, I, I)), (*R0, (S, I, I, I)), (*R1, (C, I, I, I))],
                     [(*R0, (S, S, S, S)), (*R1, (C, I, I, I)), (*A, (C, I, I, I))],
                     {"F(0)": S, "F(-3)": I, "F(-4)": I, "C(Santiago)": I}),
            "Cv × a": ([(*A, (I, S, S, S)), (*R0, (I, S, S, S)), (*R1, (I, S, C, C))],
                       [(*R0, (S, S, S, S)), (*R1, (I, I, C, C)), (*A, (I, I, C, C))],
                       {"F(0)": I, "F(-3)": I, "F(-4)": S, "C(Santiago)": S}),
        }
        for nombre, (gruesa, fina, esperado) in casos.items():
            with self.subTest(nombre):
                a = lf.e3p_anual(tabla(Regla.GRUESA, gruesa), tabla(Regla.FINA, fina), True)
                validar_esquema(a, ESQUEMA_ESTADOS, nombre=nombre)
                self.assertEqual(dict(zip(a["H"], a["estado"])), esperado)
                candidata = "F(0)" if nombre == "C.21" else "F(-4)"
                self.assertEqual(dict(zip(a["H"], a["motivo"]))[candidata], str(MotivoSinInfo.RESIDUAL))
                # sin la fina, R0 sigue contando para la candidata: tampoco es compatible
                b = lf.e3p_anual(tabla(Regla.GRUESA, gruesa), tabla(Regla.FINA, fina), False)
                self.assertEqual(dict(zip(b["H"], b["estado"]))[candidata], S)
        # Un año-régimen sin ninguna H compatible ni incompatible (todo residual, no fino) no cuenta: basta R1.
        a = lf.e3p_anual(tabla(Regla.GRUESA, [(*A, (S, I, I, I)), (*R0, (S, S, S, S)), (*R1, (C, I, I, I))]),
                         tabla(Regla.FINA, [(*R0, (S, S, S, S)), (*R1, (C, I, I, I)), (*A, (C, I, I, I))]), True)
        self.assertEqual(dict(zip(a["H"], a["estado"]))["F(0)"], C)

    def test_encabezado_lf17_y_enmienda_1_al_dia(self):
        """El encabezado documenta la dependencia de E3-2 respecto de R-52 (LF-17, con C.21) y no da por
        pendiente la Enmienda 1, adoptada y anclada (APH 81bb100)."""
        doc = " ".join(lf.__doc__.split())
        lf17 = re.search(r"- LF-17\. (.*?)(?= - LF-\d+\.| Depende de:)", doc)
        self.assertIsNotNone(lf17)
        for cita in ("R-52", "C.21", "E3-2", "Cv × tipo a", "test_e3p_anual_r52_informativo_por_h"):
            self.assertIn(cita, lf17.group(1))
        fuente = " ".join(Path(lf.__file__).read_text(encoding="utf-8").split())
        self.assertEqual(re.findall(r"borrador de la Enmienda 1|Enmienda 1[^.;]{0,80}no adoptad", fuente), [])


class PruebasVentanaParcial(unittest.TestCase):
    """Riesgos 1 y 4 de «Ola 4a cerrada» (COORDINACION_C1.md): estaciones con ventana diurna (aeródromos).

    Con la Enmienda 3 adoptada (E3-1 en §4.3.1; E3-4, aclaración del punto 16 de §8 y de §6): la regla fina
    queda exacta en una ventana parcial, y el filtro de E3t sigue sin pasar con 13 valores por día.
    """

    def test_regla_fina_exacta_en_ventana_parcial_con_e3_1(self):
        """E3-1 (§4.3.1, LF-2): el armónico de QFE se ajusta sobre sus etiquetas (13 por día) y el de sp, para
        cada c, sobre los instantes {L − c, L − c − p : L ∈ M} que ese c empareja. Con la atmósfera en que el
        texto v1.0.2 (un solo armónico de sp sobre las 24 h) dejaba la regla fina fina y errada en 1 h (ĉ^f = +1,
        reloj anómalo para un F(0), con h0 ≡ 1 mód 3), las ventanas de 13 h quedan finas y exactas: ĉ^f = 0,
        |ĉ^f_cont| ≤ E3P_FINA_TAU, y F(0) compatible por la fina, sin reloj anómalo. La misma estación con 24 h
        da ĉ^f exacto, como antes."""
        atm = _Atmosfera("2019-01-01", "2020-01-01", semilla=5, ar_p=0.06)
        U = _U()
        completa, serie, ctx = _estacion(_fijo(0), "2019-01-01", "2020-01-01", atm=atm)
        g = lf.e3(completa, serie, ctx, "QFE")
        for reg in ("R0", "R1"):
            m = _metrica(g, Nivel.REGIMEN, reg)
            self.assertTrue(m["fino"], reg)
            self.assertEqual(int(m["c_hat_f"]), 0)
            self.assertLess(abs(m["c_hat_f_cont"]), U.a("E3P_FINA_TAU") / 5)
        for h0 in (1, 4, 7):
            with self.subTest(h0=h0):
                ventana, serie_v, ctx_v = _estacion(_fijo(0), "2019-01-01", "2020-01-01", atm=atm,
                                                    horas=range(h0, h0 + 13))
                gv = lf.e3(ventana, serie_v, ctx_v, "QFE")
                for reg in ("R0", "R1"):
                    m = _metrica(gv, Nivel.REGIMEN, reg)
                    self.assertGreaterEqual(int(m["n_pares"]), U.f("E3_PARES_REGIMEN"))
                    self.assertTrue(m["fino"], reg)
                    self.assertEqual(int(m["c_hat_f"]), 0, reg)
                    self.assertLessEqual(abs(m["c_hat_f_cont"]), U.a("E3P_FINA_TAU"), reg)
                fina = lf.e3_fina(gv.metricas, ctx_v)
                anual = _estado(fina, Nivel.ANIO, "2019", "F(0)")
                self.assertEqual(anual["estado"], Estado.COMPATIBLE)
                self.assertFalse(anual["reloj_anomalo"])

    def test_filtro_e3t_sin_dias_de_20_valores_en_ventana_de_13h(self):
        """E3-4 (ORQ-10). §4.3.3: el filtro usa los días de etiqueta con ≥ 20 valores (p = 1). Una ventana de
        13 h nunca los tiene: la correlación diaria queda indefinida y el filtro no pasa, aunque la misma
        estación con 24 h lo pase. Así E3t (y T-P) quedan sin información en un aeródromo de 11 a 23 h."""
        atm = _Atmosfera("2019-01-01", "2019-07-01", semilla=6)
        completa, serie, ctx = _estacion(_fijo(0), "2019-01-01", "2019-07-01", atm=atm)
        f = lf.filtro_representatividad(completa, serie, ctx)
        self.assertTrue(f["pasa"].all(), f)
        ventana, serie_v, ctx_v = _estacion(_fijo(0), "2019-01-01", "2019-07-01", atm=atm, horas=range(11, 24))
        fv = lf.filtro_representatividad(ventana, serie_v, ctx_v)
        self.assertEqual(len(fv), len(f))
        self.assertFalse(fv["pasa"].any())
        self.assertTrue(fv["r_diaria"].isna().all())
        e3t = lf.e3(ventana, serie_v, ctx_v, "Ts")
        reg = e3t.estados[e3t.estados["nivel"] == "regimen"]
        self.assertTrue((reg["estado"] == Estado.SIN_INFORMACION).all())


# ---------------------------------------------------------------------------------------------
# E4
# ---------------------------------------------------------------------------------------------
class PruebasE4(unittest.TestCase):
    def test_p13_e4_fases_paso_1_y_3(self):
        """Recupera fases conocidas."""
        for paso, c in ((1, -4), (3, -4), (1, 0), (3, -3)):
            with self.subTest(paso=paso, c=c):
                anotado, serie, ctx = _estacion(_fijo(c), "2019-01-01", "2019-04-01", paso=paso, semilla=90 + paso,
                                                ruido_p=0.05)
                m = lf.ajustes_e4(anotado, ctx, "QFE")
                validar_esquema(m, ESQUEMA_METRICAS_E4, nombre="E4")
                reg = m[(m["nivel"] == "regimen") & (m["unidad"] == "R0")].iloc[0]
                self.assertEqual(reg["n_h"], 24 // paso)
                self.assertEqual(reg["hueco_max_h"], paso)
                self.assertEqual(reg["K"], 3)
                psi_solar = numerico.envolver(reg["psi2"] - c, 0, 12)
                self.assertLess(numerico.distancia_circular(psi_solar, 9.75, 12), 0.3)
                res = lf.e4p(m, ctx)
                h_ok = f"F({c:+d})" if c else "F(0)"
                self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", h_ok)["estado"], Estado.COMPATIBLE)
                self.assertEqual(_estado(res, Nivel.ANIO, "2019", h_ok)["estado"], Estado.COMPATIBLE)
                lejana = "F(0)" if c != 0 else "F(-4)"
                self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", lejana)["estado"], Estado.INCOMPATIBLE)
                self.assertEqual(_estado(res, Nivel.ANIO, "2019", lejana)["estado"], Estado.INCOMPATIBLE)
                self.assertIn(_estado(res, Nivel.PARTE, "2019-01-1", h_ok)["estado"], (Estado.COMPATIBLE,))
                # Ts: φ1 en hora solar a 15 h (máximo del ciclo sintético)
                t = lf.ajustes_e4(anotado, ctx, "Ts")
                rt = t[(t["nivel"] == "regimen") & (t["unidad"] == "R0")].iloc[0]
                self.assertLess(numerico.distancia_circular(rt["phi1"] - c, 15, 24), 0.3)

    def test_p13_e4_paso_6_sin_informacion_y_e4t_k1(self):
        """Con tercer armónico fuerte."""
        def con_tercero(a, k):
            return a.T[k] + 3 * np.cos(2 * math.pi * 3 * (a.solar[k] - 2) / 24)
        anotado, serie, ctx = _estacion(_fijo(-4), "2019-01-01", "2019-04-01", paso=6, ts=con_tercero)
        q = lf.ajustes_e4(anotado, ctx, "QFE")
        t = lf.ajustes_e4(anotado, ctx, "Ts")
        for m in (q, t):
            reg = m[(m["nivel"] == "regimen") & (m["unidad"] == "R0")].iloc[0]
            self.assertEqual((reg["n_h"], reg["K"], reg["paso_h"]), (4, 1, 6))
            self.assertTrue(np.isnan(reg["A2"]) and np.isnan(reg["psi2"]))
            self.assertTrue(np.isfinite(reg["phi1"]) and np.isfinite(reg["EE_A1"]))
        res = lf.e4p(q, ctx)
        regs = res.estados[res.estados["nivel"].isin(["regimen", "parte"])]
        self.assertTrue((regs["estado"] == Estado.SIN_INFORMACION).all())
        self.assertEqual(set(regs["motivo"]), {"paso"})
        self.assertTrue((res.estados.loc[res.estados["nivel"] == "anio", "estado"] == Estado.SIN_INFORMACION).all())

    def test_e4p_hueco_y_amplitud(self):
        """Hueco circular > 3 h y S2 débil (A2 < 0,15 hPa) dan sin información; la ventana diurna, por mínimos."""
        anotado, serie, ctx = _estacion(_fijo(0), "2019-01-01", "2019-04-01", horas=range(8, 21))
        res = lf.e4p(lf.ajustes_e4(anotado, ctx, "QFE"), ctx)
        self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", "F(0)")["motivo"], "minimos")   # días de 13 valores
        anotado, serie, ctx = _estacion(_fijo(0), "2019-01-01", "2019-04-01", horas=range(0, 21))
        m = lf.ajustes_e4(anotado, ctx, "QFE")
        self.assertEqual(int(m.loc[(m["nivel"] == "regimen"), "hueco_max_h"].iloc[0]), 4)
        res = lf.e4p(m, ctx)
        self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", "F(0)")["motivo"], "hueco")
        atm = _Atmosfera("2019-01-01", "2019-04-01", semilla=93, s2=0.05)
        anotado, serie, ctx = _estacion(_fijo(0), "2019-01-01", "2019-04-01", atm=atm)
        res = lf.e4p(lf.ajustes_e4(anotado, ctx, "QFE"), ctx)
        self.assertEqual(_estado(res, Nivel.REGIMEN, "R0", "F(0)")["motivo"], "amplitud")


# ---------------------------------------------------------------------------------------------
# E6
# ---------------------------------------------------------------------------------------------
def _isd(anotado, reloj_c, tipo, *, jitter_min=0):
    """Partes ISD sintéticos: en u = L − c, el TMP de la Ts de la etiqueta (FM-12 en décimas, FM-15 entero)."""
    L = anotado["L"].to_numpy(dtype="datetime64[ns]")
    u = L - np.timedelta64(reloj_c, "h") + np.timedelta64(jitter_min, "m")
    tmp = anotado["ts"].to_numpy(float)
    tmp = np.round(tmp, 1) if tipo == "FM-12" else np.round(tmp)
    return pd.DataFrame({"codigo": "999001", "u": u, "tipo_parte": tipo, "tmp": tmp}).astype(
        {"codigo": "string", "u": "datetime64[ns]", "tipo_parte": "string", "tmp": "float64"})


class PruebasE6(unittest.TestCase):
    def test_p15_e6_fm12_decide_fm15_separa_2h(self):
        """ISD sintético."""
        anotado, serie, ctx = _estacion(_fijo(-4), lineas={Linea.E6}, semilla=101)
        self.assertEqual(len(lf.e6(anotado, _isd(anotado, -4, "FM-12"), _contexto(
            anotado.drop(columns=["parte", "regimen", "especial"]))[1]).estados), 0)   # inactiva: sin filas
        # FM-12 decide: la verdadera compatible y toda otra H incompatible
        res = lf.e6(anotado, _isd(anotado, -4, "FM-12", jitter_min=7), ctx)
        validar_esquema(res.estados, ESQUEMA_ESTADOS, nombre="E6")
        for unidad, nivel in (("2019", Nivel.ANIO), ("2019-01", Nivel.MES)):
            por_h = {h.id: _estado(res, nivel, unidad, h.id)["estado"] for h in ctx.info.P}
            self.assertEqual(por_h, {"F(0)": Estado.INCOMPATIBLE, "F(-3)": Estado.INCOMPATIBLE,
                                     "F(-4)": Estado.COMPATIBLE, "C(Santiago)": Estado.INCOMPATIBLE})
        self.assertFalse(res.estados["reloj_anomalo"].any())
        # partes a más de ±10 min no cuentan
        lejos = lf.e6(anotado, _isd(anotado, -4, "FM-12", jitter_min=11), ctx)
        self.assertEqual(_estado(lejos, Nivel.ANIO, "2019", "F(-4)")["estado"], Estado.SIN_INFORMACION)
        # FM-15 sólo separa a ≥ 2 h (R-28): F(0) incompatible, F(−3) (a 1 h) no
        res = lf.e6(anotado, _isd(anotado, -4, "FM-15"), ctx)
        anual = {h.id: _estado(res, Nivel.ANIO, "2019", h.id)["estado"] for h in ctx.info.P}
        self.assertEqual(anual["F(-4)"], Estado.COMPATIBLE)
        self.assertEqual(anual["F(0)"], Estado.INCOMPATIBLE)
        self.assertNotEqual(anual["F(-3)"], Estado.INCOMPATIBLE)
        self.assertNotEqual(anual["C(Santiago)"], Estado.INCOMPATIBLE)
        # con los dos tipos en la misma hora se prefiere el FM-12
        ambos = pd.concat([_isd(anotado, -4, "FM-15"), _isd(anotado, 0, "FM-12")], ignore_index=True)
        res = lf.e6(anotado, ambos, ctx)
        self.assertEqual(_estado(res, Nivel.ANIO, "2019", "F(0)")["estado"], Estado.COMPATIBLE)
        # reloj anómalo: un c fuera de P es compatible
        res = lf.e6(anotado, _isd(anotado, 1, "FM-12"), ctx)
        self.assertTrue(_estado(res, Nivel.ANIO, "2019", "F(0)")["reloj_anomalo"])
        # sin partes: sin información
        res = lf.e6(anotado, None, ctx)
        self.assertTrue((res.estados["estado"] == Estado.SIN_INFORMACION).all())

    def test_normalizar_nombre_isd(self):
        """NFKD, mayúsculas, sin las palabras de §4.6."""
        casos = {
            "Santiago, Aeropuerto Arturo Merino Benítez": "SANTIAGO ARTURO MERINO BENITEZ",
            "ISLA DE PASCUA/MATAVERI INTL": "ISLA DE PASCUA MATAVERI",
            "Aeródromo  Pdte. Ibáñez, Punta-Arenas": "PDTE IBANEZ PUNTA ARENAS",
            "Concepción Ad.": "CONCEPCION",
            "Estación   Quinta Normal": "QUINTA NORMAL",
            "Aeropuerto Internacional Ñuñoa AP": "NUNOA",
        }
        for crudo, esperado in casos.items():
            self.assertEqual(lf.normalizar_nombre_isd(crudo), esperado)

    def test_cruce_isd(self):
        """OMM, luego OACI; sin indicativos, mismo nombre a ≤ 2 km."""
        cat = pd.DataFrame({"codigo": ["330020", "270001", "999002", "999003"],
                            "nombre": ["Quinta Normal", "Mataveri", "Chacalluta Ap.", "Lejana"],
                            "lat": [-33.44, -27.16, -18.35, -40.0], "lon": [-70.68, -109.42, -70.34, -72.0],
                            "omm": ["85574", None, None, None], "oaci": [None, "SCIP", None, None]})
        isd = pd.DataFrame({"id_isd": ["855740-99999", "854690-99999", "854060-99999", "800000-99999"],
                            "nombre": ["QUINTA NORMAL", "ISLA DE PASCUA", "CHACALLUTA", "LEJANA"],
                            "lat": [-33.45, -27.16, -18.355, -40.1], "lon": [-70.68, -109.42, -70.34, -72.0],
                            "omm": ["85574", "85469", "85406", "80000"], "oaci": [None, "SCIP", "SCAR", None]})
        cruce = lf.cruce_isd(cat, isd, umbrales=_U())
        self.assertEqual(list(cruce.columns), list(lf.COLUMNAS_CRUCE))
        self.assertEqual(dict(zip(cruce["codigo"], cruce["criterio"])),
                         {"330020": "omm", "270001": "oaci", "999002": "nombre"})


if __name__ == "__main__":
    unittest.main()
