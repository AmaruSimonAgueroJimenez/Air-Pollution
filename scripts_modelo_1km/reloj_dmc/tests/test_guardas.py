"""Pruebas de guardas.py (guardas y marcas).

Las que llevan «pNN» son el punto NN de §8 (grupo B). Las series son sintéticas y se fabrican aquí, sin
``sintetico`` ni funciones del módulo: una «atmósfera» horaria en UTC (ciclo diario de temperatura con
máximo a las 15 h solares, marea S2 con máximo a 9,75 h solares, S1, variación sinóptica diaria, ruido
y viento con brisa) y relojes fijos conocidos por variable; la etiqueta es L = u + c. Los umbrales son
los anclados en C0 (si faltan, las pruebas se omiten con el motivo). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import math  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import constantes, decision, guardas, lineas_fisicas as lf, tablas, umbrales  # noqa: E402
from reloj_dmc.tipos import (ESQUEMA_EXTRACTO_HORA, ESQUEMA_GUARDAS, ESQUEMA_MARCAS, ESQUEMA_MES,  # noqa: E402
                             ESQUEMA_METRICAS_E3, Conjunto, ContextoEstacion, InfoEstacion, Linea, ResultadoGuarda,
                             Territorio, validar_esquema)

_PAQUETE = Path(umbrales.__file__).resolve().parent
_APH = _PAQUETE.parents[1].parent / "Air-Pollution-Health-Chile"
_CACHE = {}

CONTINENTAL = (("America/Santiago",), ("F(0)", "F(-3)", "F(-4)", "C(Santiago)"))
LON = -70.6
LAT = -33.4
DESDE, HASTA = "2019-05-01", "2019-08-01"          # invierno de 2019: un solo año-régimen (R1, −4)
F4 = "F(-4)"
TODAS = frozenset({Linea.E3D, Linea.P7, Linea.TP, Linea.E4T, Linea.G_VERSION, Linea.G_HR, Linea.G_VIENTO})
VERSION_A = "a1b2c3d4" + "0" * 56
VERSION_B = "e5f60718" + "1" * 56
KT_POR_MS = 1.943844


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
    """Temperatura, presión y viento «verdaderos» por hora UTC en el píxel 1, con fases solares conocidas."""

    def __init__(self, desde=DESDE, hasta=HASTA, *, semilla=1, lon=LON):
        margen = np.timedelta64(4, "D")
        self.u = np.arange(np.datetime64(desde, "h") - margen, np.datetime64(hasta, "h") + margen,
                           dtype="datetime64[h]")
        n = self.u.size
        rng = np.random.default_rng(semilla)
        hora = (self.u - self.u.astype("datetime64[D]")) / np.timedelta64(1, "h")
        dia = (self.u.astype("datetime64[D]") - self.u.astype("datetime64[Y]").astype("datetime64[D]")) \
            / np.timedelta64(1, "D") + 1
        solar = hora + lon / 15 + _eot_spencer_min(dia) / 60
        # variación sinóptica: un valor por día (AR(1) entre días), interpolado a la hora
        n_dias = n // 24 + 2
        posicion = np.arange(n) / 24

        def sinoptica(sd):
            diaria = _ar1(rng, n_dias, 0.6, sd * math.sqrt(1 - 0.36))
            return np.interp(posicion, np.arange(n_dias) + 0.5, diaria)

        self.T = (12 + 3 * np.cos(2 * math.pi * (solar - 15) / 24) + sinoptica(3.0) + _ar1(rng, n, 0.8, 0.1))
        self.P = (950 + 1.0 * np.cos(2 * math.pi * 2 * (solar - 9.75) / 24) + 0.4 * np.cos(2 * math.pi * (solar - 7) / 24)
                  + _ar1(rng, n, 0.95, 0.25) + sinoptica(4.0))
        self.U = _ar1(rng, n, 0.9, 0.9) + 1.0 * np.cos(2 * math.pi * (solar - 15) / 24)
        self.V = _ar1(rng, n, 0.9, 0.9) + 0.5 * np.sin(2 * math.pi * (solar - 15) / 24)
        self.t2m = self.T + rng.normal(0, 0.2, n)
        self.sp = self.P + rng.normal(0, 0.05, n)

    def serie(self):
        return _SerieMemoria(self.u[0], {1: {"t2m": self.t2m, "sp": self.sp, "u10": self.U, "v10": self.V}})

    def en(self, u, nombre, adelanto=0.0):
        """Valor «verdadero» en los instantes u + adelanto (h), con interpolación lineal entre horas."""
        k = (np.asarray(u, dtype="datetime64[ns]") - self.u[0].astype("datetime64[ns]")) / np.timedelta64(1, "h")
        return np.interp(k + adelanto, np.arange(self.u.size), getattr(self, nombre))


def _horas(c):
    return np.timedelta64(int(c), "h")


def _extracto(atm, desde=DESDE, hasta=HASTA, *, c=-4, c_ts=None, c_hr=None, c_viento=None, adelanto_ts=0.0,
              corrida=False, semilla=7):
    """Extracto con el esquema completo. Cada variable tiene su reloj fijo (L = u + c); ``corrida``: las
    etiquetas 00-03 traen los valores del día siguiente (fecha corrida un día)."""
    c_ts = c if c_ts is None else c_ts
    c_hr = c_ts if c_hr is None else c_hr
    c_viento = c if c_viento is None else c_viento
    L = np.arange(np.datetime64(desde, "h"), np.datetime64(hasta, "h"), dtype="datetime64[h]").astype("datetime64[ns]")
    hora = pd.DatetimeIndex(L).hour.to_numpy()
    fuente = np.where((hora < 4) & corrida, L + _horas(24), L) if corrida else L
    rng = np.random.default_rng(semilla)
    n = L.size
    qfe = np.round(atm.en(fuente - _horas(c), "P") + rng.normal(0, 0.1, n), 1)
    t_ts = atm.en(fuente - _horas(c_ts), "T", adelanto_ts)
    ts = np.round(t_ts + rng.normal(0, 0.1, n), 1)
    hr = np.clip(np.round(75 - 3 * (atm.en(fuente - _horas(c_hr), "T") - 12) + rng.normal(0, 1.0, n)), 5, 100)
    u = atm.en(fuente - _horas(c_viento), "U") + rng.normal(0, 0.5, n)
    v = atm.en(fuente - _horas(c_viento), "V") + rng.normal(0, 0.5, n)
    ff = np.round(np.hypot(u, v) * KT_POR_MS, 1)
    dd = np.round(np.mod(np.degrees(np.arctan2(-u, -v)), 360), 0)
    u_q = fuente - _horas(c)
    rr = (pd.DatetimeIndex(u_q).hour.to_numpy() % 6) == 0     # RR06 en las horas sinópticas UTC
    idx = pd.DatetimeIndex(L)
    df = pd.DataFrame({
        "L": L, "anio": idx.year, "mes": idx.month, "id_artefacto": idx.year * 12 + idx.month,
        "medida": True, "ts": ts, "motivo_ts": 0, "qfe": qfe, "motivo_qfe": 0, "td": np.nan, "hr": hr,
        "ff_kt": ff, "dd_grados": dd, "viento_valido": True, "qff_numerica": False, "rr": rr, "tx": False,
        "tn": False, "observador": rr, "huella": [f"fila{i}" for i in range(n)]})
    return df.astype(ESQUEMA_EXTRACTO_HORA)


def _contexto(extracto, *, lat=LAT, lon=LON, dz=10.0, pixel=1, inconsistentes=False, lineas=TODAS):
    zs, ids = CONTINENTAL
    T = _T()
    info = InfoEstacion(codigo="999002", nombre="PRUEBA", lat=lat, lon=lon, alt_m=500.0, coordenadas_validas=True,
                        coordenadas_inconsistentes=inconsistentes, territorio=Territorio.CONTINENTAL, region=13,
                        macrozona="centro", zs=zs, P=tablas.hipotesis_de_P(ids), pixel_id=pixel, distancia_km=1.0,
                        costera=False, z_pix=490.0, dz=dz, conjunto=Conjunto.V)
    anotado = tablas.anotar_partes(extracto, info, T)
    anios = tuple(sorted(set(anotado["anio"].astype(int))))
    regimenes = {a: tablas.regimenes_del_anio(zs, a, T) for a in anios}
    util = anotado[~anotado["especial"]]
    con_datos = {a: tuple(sorted(set(util.loc[util["anio"] == a, "regimen"].dropna()))) for a in anios}
    clases = {a: tablas.fusionar(info.P, [r for r in regimenes[a] if r.id in con_datos[a]], zs) for a in anios}
    meses = {a: tuple(sorted(set(anotado.loc[anotado["anio"] == a, "mes"].astype(int)))) for a in anios}
    ctx = ContextoEstacion(info=info, tablas=T, umbrales=_U(), anios=anios, regimenes=regimenes,
                           regimenes_con_datos=con_datos, clases=clases, meses_con_datos=meses,
                           lineas_activas=frozenset(lineas))
    return anotado, ctx


def _estacion(*, semilla=1, ctx_kw=None, **kw):
    atm = _Atmosfera(semilla=semilla)
    anotado, ctx = _contexto(_extracto(atm, semilla=semilla + 100, **kw), **(ctx_kw or {}))
    return anotado, atm.serie(), ctx


def _meses(anotado, version_de_mes, codigo="999002"):
    claves = sorted(set(zip(anotado["anio"].astype(int), anotado["mes"].astype(int))))
    filas = [{c: None for c in ESQUEMA_MES} | {
        "codigo": codigo, "anio": a, "mes": m, "manifiesto": f"DMC/estaciones/{codigo}/{a:04d}-{m:02d}.manifest.json",
        "id_artefacto": a * 12 + m, "script_sha256": version_de_mes[(a, m)], "entra": True, "campos_faltantes": []}
        for a, m in claves]
    return pd.DataFrame(filas, columns=list(ESQUEMA_MES)).astype(ESQUEMA_MES)


def _una(tabla, columna, nombre, H, unidad=None):
    sel = (tabla[columna] == nombre) & (tabla["H"] == H)
    if unidad is not None:
        sel &= tabla["unidad"] == unidad
    filas = tabla[sel]
    assert len(filas) == 1, (nombre, H, unidad, len(filas))
    return filas.iloc[0]


def _tp(anotado, serie, ctx):
    filtro = lf.filtro_representatividad(anotado, serie, ctx)
    metricas = lf.e3(anotado, serie, ctx, "Ts").metricas
    return metricas, filtro, guardas.tp(metricas, filtro, ctx), guardas.desfase_termico_local(metricas, filtro, ctx)


# ---------------------------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------------------------
class PruebasGuardas(unittest.TestCase):
    def test_p14_e3d_falla_con_horas_corridas_un_dia(self):
        """Horas 00-03 corridas un día."""
        anotado, serie, ctx = _estacion(semilla=11, corrida=True)
        g = guardas.e3d(anotado, serie, ctx)
        validar_esquema(g, ESQUEMA_GUARDAS, nombre="E3d")
        self.assertEqual(set(g["H"]), {h.id for h in ctx.info.P})
        self.assertEqual(set(g["unidad"]), {"2019"})
        fila = _una(g, "guarda", "E3d", F4)
        self.assertEqual(fila["resultado"], ResultadoGuarda.FALLA)
        self.assertIn("Ts: 00-05", fila["detalle"])
        self.assertIn("QFE: 00-05", fila["detalle"])
        # sin la fecha corrida pasa, y los cuatro bloques de Ts y de QFE son informativos
        anotado0, serie0, ctx0 = _estacion(semilla=11)
        fila0 = _una(guardas.e3d(anotado0, serie0, ctx0), "guarda", "E3d", F4)
        self.assertEqual(fila0["resultado"], ResultadoGuarda.PASA)
        self.assertNotIn("falla", fila0["detalle"])
        self.assertEqual(fila0["detalle"].count("Δr="), 8)

    def test_e3d_sin_pixel_desnivel_o_coordenadas(self):
        """§3.1 y §3.3: sin píxel o con coordenadas inconsistentes, no evaluable; |Δz| > 1.000 m deja sólo QFE."""
        for ctx_kw in ({"pixel": 99}, {"inconsistentes": True}):
            with self.subTest(**ctx_kw):
                anotado, serie, ctx = _estacion(semilla=12, corrida=True, ctx_kw=ctx_kw)
                g = guardas.e3d(anotado, serie, ctx)
                self.assertTrue((g["resultado"] == ResultadoGuarda.NO_EVALUABLE).all())
        anotado, serie, ctx = _estacion(semilla=12, corrida=True, ctx_kw={"dz": 1500.0})
        fila = _una(guardas.e3d(anotado, serie, ctx), "guarda", "E3d", F4)
        self.assertEqual(fila["resultado"], ResultadoGuarda.FALLA)
        self.assertIn("Ts: desnivel", fila["detalle"])

    def test_p14_p7_falla_con_horas_corridas_un_dia(self):
        """Mismo caso."""
        anotado, serie, ctx = _estacion(semilla=11, corrida=True)
        g = guardas.p7(anotado, ctx)
        validar_esquema(g, ESQUEMA_GUARDAS, nombre="P7")
        fila = _una(g, "guarda", "P7", guardas.H_TODAS, "2019")
        self.assertEqual(fila["resultado"], ResultadoGuarda.FALLA)
        self.assertIn("23 h", fila["detalle"])                 # 23 h contra las 00 h del día siguiente
        self.assertIn("03 h", fila["detalle"])
        anotado0, _, ctx0 = _estacion(semilla=11)
        self.assertEqual(_una(guardas.p7(anotado0, ctx0), "guarda", "P7", "*")["resultado"], ResultadoGuarda.PASA)
        # con paso de 3 h no hay 22 etiquetas de presencia ≥ 0,8
        ralo = anotado0[pd.DatetimeIndex(anotado0["L"]).hour % 3 == 0].reset_index(drop=True)
        self.assertEqual(_una(guardas.p7(ralo, ctx0), "guarda", "P7", "*")["resultado"], ResultadoGuarda.NO_EVALUABLE)

    def test_p14_tp_falla_con_ts_corrida_4h(self):
        """Forma de reloj."""
        anotado, serie, ctx = _estacion(semilla=21, c_ts=0)          # QFE en F(−4), Ts en F(0)
        metricas, _, g, _ = _tp(anotado, serie, ctx)
        validar_esquema(g, ESQUEMA_GUARDAS, nombre="T-P")
        self.assertEqual(int(metricas.loc[metricas["unidad"] == "R1", "c_hat"].iloc[0]), 0)
        fila = _una(g, "guarda", "T-P", F4, "R1")
        self.assertEqual(fila["resultado"], ResultadoGuarda.FALLA)
        self.assertIn("k=+4", fila["detalle"])
        # bajo F(0), el reloj de Ts, no hay discrepancia con forma de reloj
        self.assertEqual(_una(g, "guarda", "T-P", "F(0)", "R1")["resultado"], ResultadoGuarda.PASA)

    def test_p14_tp_no_falla_con_desfase_fisico_1_5h(self):
        """Desfase térmico físico de −1,5 h."""
        anotado, serie, ctx = _estacion(semilla=22, adelanto_ts=1.5)
        _, _, g, m = _tp(anotado, serie, ctx)
        self.assertEqual(_una(g, "guarda", "T-P", F4, "R1")["resultado"], ResultadoGuarda.PASA)
        delta = _una(m, "marca", guardas.MARCA_DESFASE_TERMICO_LOCAL, F4)["valor"]
        self.assertAlmostEqual(delta, -1.5, delta=0.3)
        self.assertLessEqual(abs(delta), ctx.umbrales.f("DTL_DELTA_H"))       # sin marca

    def test_tp_no_evaluable_sin_condiciones(self):
        """R-46 y filtro: sin ĉt_cont, sin filtro o con < 1.000 pares, T-P no es evaluable; la marca queda None."""
        anotado, serie, ctx = _estacion(semilla=21, c_ts=0)
        metricas, filtro, _, _ = _tp(anotado, serie, ctx)
        sin_cont = metricas.assign(c_hat_cont=np.nan)
        pocos = metricas.assign(n_pares=np.int32(ctx.umbrales.f("E3_PARES_REGIMEN") - 1))
        sin_filtro = filtro.assign(pasa=False)
        for nombre, (m, f) in {"sin ĉt_cont": (sin_cont, filtro), "pocos pares": (pocos, filtro),
                               "filtro": (metricas, sin_filtro), "columna del filtro": (metricas.assign(filtro_e3t=False),
                                                                                        None)}.items():
            with self.subTest(nombre):
                g = guardas.tp(m, f, ctx)
                self.assertTrue((g["resultado"] == ResultadoGuarda.NO_EVALUABLE).all())
                marcas = guardas.desfase_termico_local(m, f, ctx)
                validar_esquema(marcas, ESQUEMA_MARCAS, nombre="marca")
                self.assertTrue(all(v is None for v in marcas["valor"]))
        self.assertIn("R-46", _una(guardas.tp(sin_cont, filtro, ctx), "guarda", "T-P", F4, "R1")["detalle"])

    def test_p14_e4t_falla_con_error_de_12h(self):
        """(φ1 − c_H) mód 24 fuera de [10, 19]."""
        anotado, _, ctx = _estacion(semilla=31, c_ts=8)               # Ts con reloj F(+8): F(−4) + 12 h
        g = guardas.e4t(lf.ajustes_e4(anotado, ctx, "Ts"), ctx)
        validar_esquema(g, ESQUEMA_GUARDAS, nombre="E4t")
        for h in ctx.info.P:                                           # detecta 12 h y ≥ 5 h en toda H de P
            self.assertEqual(_una(g, "guarda", "E4t", h.id, "R1")["resultado"], ResultadoGuarda.FALLA, h.id)
        anotado0, _, ctx0 = _estacion(semilla=31)
        g0 = guardas.e4t(lf.ajustes_e4(anotado0, ctx0, "Ts"), ctx0)
        for h in ctx0.info.P:                                          # no separa F(0) de F(−3) ni de F(−4)
            self.assertEqual(_una(g0, "guarda", "E4t", h.id, "R1")["resultado"], ResultadoGuarda.PASA, h.id)

    def test_p14_g_version_falla_con_4h(self):
        """Dos versiones que difieren en 4 h."""
        atm = _Atmosfera("2019-05-01", "2019-09-01", semilla=41)
        a = _extracto(atm, "2019-05-01", "2019-07-01", c=-4, semilla=1)
        version = {(2019, 5): VERSION_A, (2019, 6): VERSION_A, (2019, 7): VERSION_B, (2019, 8): VERSION_B}
        for c_b, esperado in ((0, ResultadoGuarda.FALLA), (-4, ResultadoGuarda.PASA)):
            with self.subTest(c_b=c_b):
                b = _extracto(atm, "2019-07-01", "2019-09-01", c=c_b, semilla=2)
                anotado, ctx = _contexto(pd.concat([a, b], ignore_index=True))
                resumen = guardas.resumen_por_version(anotado, atm.serie(), _meses(anotado, version), ctx)
                self.assertEqual(list(resumen.columns), list(guardas.COLUMNAS_RESUMEN_VERSION))
                por_version = {v: f for v, (_, f) in zip(resumen["version"], resumen.iterrows())}
                self.assertEqual(set(por_version), {VERSION_A, VERSION_B})
                self.assertEqual(int(por_version[VERSION_A]["c_hat"]), -4)
                self.assertEqual(int(por_version[VERSION_B]["c_hat"]), c_b)
                self.assertGreaterEqual(por_version[VERSION_B]["estab_c_hat"], ctx.umbrales.f("GVER_ESTAB"))
                self.assertEqual(int(por_version[VERSION_A]["j_estrella"]), 2)             # F(−4): clase 2
                self.assertEqual(int(por_version[VERSION_B]["j_estrella"]), c_b % 3)
                g = guardas.g_version(resumen, ctx)
                validar_esquema(g, ESQUEMA_GUARDAS, nombre="G-versión")
                fila = _una(g, "guarda", "G-version", guardas.H_TODAS, "2019")
                self.assertEqual(fila["resultado"], esperado)
                if esperado == ResultadoGuarda.FALLA:
                    self.assertIn("ĉ", fila["detalle"])
                    self.assertIn("j*", fila["detalle"])
        # con una sola versión de ≥ 2 meses, no se aplica
        solo = {k: VERSION_A for k in version}
        anotado, ctx = _contexto(a)
        resumen = guardas.resumen_por_version(anotado, atm.serie(), _meses(anotado, solo), ctx)
        self.assertEqual(len(resumen), 0)
        self.assertEqual(_una(guardas.g_version(resumen, ctx), "guarda", "G-version", "*")["resultado"],
                         ResultadoGuarda.NO_EVALUABLE)

    def test_g_version_compara_dentro_del_anio_regimen(self):
        """GU-6: una estación civil con cada versión en un régimen distinto no falla (ĉ −3 en R0 y −4 en R1)."""
        atm = _Atmosfera("2019-01-01", "2019-07-01", semilla=42)
        a = _extracto(atm, "2019-01-01", "2019-03-01", c=-3, semilla=3)    # verano: C(Santiago) = −3
        b = _extracto(atm, "2019-05-01", "2019-07-01", c=-4, semilla=4)    # invierno: C(Santiago) = −4
        anotado, ctx = _contexto(pd.concat([a, b], ignore_index=True))
        version = {(2019, 1): VERSION_A, (2019, 2): VERSION_A, (2019, 5): VERSION_B, (2019, 6): VERSION_B}
        resumen = guardas.resumen_por_version(anotado, atm.serie(), _meses(anotado, version), ctx)
        self.assertEqual(sorted(zip(resumen["version"], resumen["regimen"])), [(VERSION_A, "R0"), (VERSION_B, "R1")])
        self.assertEqual(_una(guardas.g_version(resumen, ctx), "guarda", "G-version", "*")["resultado"],
                         ResultadoGuarda.NO_EVALUABLE)

    def test_desfase_termico_local(self):
        """|δt| > 2,0 h sin forma de reloj: marca y E3t no apoya."""
        anotado, serie, ctx = _estacion(semilla=23, adelanto_ts=2.5)
        _, _, g, m = _tp(anotado, serie, ctx)
        self.assertEqual(_una(g, "guarda", "T-P", F4, "R1")["resultado"], ResultadoGuarda.PASA)
        validar_esquema(m, ESQUEMA_MARCAS, nombre="marca térmica")
        self.assertEqual(set(m["H"]), {h.id for h in ctx.info.P})
        self.assertEqual(guardas.MARCA_DESFASE_TERMICO_LOCAL, decision.MARCA_DESFASE_TERMICO_LOCAL)
        delta = _una(m, "marca", guardas.MARCA_DESFASE_TERMICO_LOCAL, F4)["valor"]
        self.assertAlmostEqual(delta, -2.5, delta=0.3)
        # decision aplica la marca (y E3t deja de apoyar, paso 7) cuando T-P pasa y |δt| > DTL_DELTA_H
        self.assertGreater(abs(delta), ctx.umbrales.f("DTL_DELTA_H"))

    def test_tp_falla_en_f0_con_fase_termica_corrida_2_5h_texto_anclado(self):
        """Riesgo 2 de «Ola 4a cerrada»: PROPIEDAD DEL TEXTO ANCLADO (§4.7), no un error del código. Un
        corrimiento de fase térmica de 2,5 h entre Ts y t2m (el sesgo de referencia de +2,5 h de §8.D2, o un
        desfase físico de la estación de −2,5 h) da δt ≈ −2,5 h para cualquier reloj. Bajo F(0), D_R = {−3, −4}
        y |δt − (−3)| ≤ TP_VENTANA: «forma de reloj», T-P falla y el año queda discrepante. Bajo F(−4) (prueba
        anterior) D_R = {+4} y sólo queda la marca térmica. Ver PROPUESTA_ENMIENDA_3.md, punto E3-3."""
        anotado, serie, ctx = _estacion(semilla=23, c=0, adelanto_ts=2.5)        # QFE y Ts en F(0)
        metricas, _, g, m = _tp(anotado, serie, ctx)
        U = ctx.umbrales
        fila = _una(g, "guarda", "T-P", "F(0)", "R1")
        self.assertEqual(fila["resultado"], ResultadoGuarda.FALLA, fila["detalle"])
        self.assertIn("k=-3", fila["detalle"])
        delta = _una(m, "marca", guardas.MARCA_DESFASE_TERMICO_LOCAL, "F(0)")["valor"]
        self.assertAlmostEqual(delta, -2.5, delta=0.3)
        self.assertLessEqual(abs(delta - (-3)), U.a("TP_VENTANA"))
        r = np.asarray(metricas.loc[metricas["unidad"] == "R1", "r"].iloc[0])
        vent = list(range(-int(U.f("E3_VENTANA")), int(U.f("E3_VENTANA")) + 1))
        self.assertGreaterEqual(r[vent.index(-3)] - r[vent.index(0)], U.a("TP_MARGEN"))
        # Las demás H de P no tienen un rival a −3 h o menos: no hay forma de reloj.
        for h in ("F(-3)", "F(-4)", "C(Santiago)"):
            self.assertEqual(_una(g, "guarda", "T-P", h, "R1")["resultado"], ResultadoGuarda.PASA, h)

    def test_tp_banda_de_f0_llega_a_k_menos4_texto_anclado(self):
        """GU-10 y E3-3: bajo F(0), D_R = {−3, −4} (§4.7), así que T-P falla con δt_R entre
        −4 − TP_VENTANA y −3 + TP_VENTANA (de −4,75 a −2,25 h con el valor anclado): la banda llega a k = −4,
        no se queda en k = −3. Con Ts adelantada 4,25 h (δt ≈ −4,2) falla con k = −4; con 5,0 h (δt ≈ −5,0),
        fuera de la banda, pasa. El encabezado de guardas cita esa banda (y la de TP_VENTANA ajustado), que aquí
        se calcula desde los umbrales y desde P."""
        U = _U()
        _, _, ctx0 = _estacion(semilla=23, c=0)
        f0 = next(h for h in ctx0.info.P if h.id == "F(0)")
        r1 = next(r for r in ctx0.regimenes[2019] if r.id == "R1")
        c0 = tablas.desfase(f0, r1, ctx0.info.zs)
        d_r = sorted({k for k in (tablas.desfase(h, r1, ctx0.info.zs) - c0 for h in ctx0.info.P)
                      if abs(k) >= constantes.valor("TP_DIST_RIVAL")})
        self.assertEqual(d_r, [-4, -3])

        def banda(ventana):
            return min(d_r) - ventana, max(d_r) + ventana

        lo, hi = banda(U.a("TP_VENTANA"))
        for adelanto, falla in ((4.25, True), (5.0, False)):
            anotado, serie, ctx = _estacion(semilla=23, c=0, adelanto_ts=adelanto)
            _, _, g, m = _tp(anotado, serie, ctx)
            fila = _una(g, "guarda", "T-P", "F(0)", "R1")
            delta = _una(m, "marca", guardas.MARCA_DESFASE_TERMICO_LOCAL, "F(0)")["valor"]
            with self.subTest(adelanto=adelanto):
                self.assertEqual(lo <= delta <= hi, falla, delta)
                if falla:
                    self.assertEqual(fila["resultado"], ResultadoGuarda.FALLA, fila["detalle"])
                    self.assertIn(f"k={min(d_r)}", fila["detalle"])
                else:
                    self.assertEqual(fila["resultado"], ResultadoGuarda.PASA, fila["detalle"])
                for h in ("F(-3)", "F(-4)", "C(Santiago)"):
                    self.assertEqual(_una(g, "guarda", "T-P", h, "R1")["resultado"], ResultadoGuarda.PASA, h)

        def es(x, decimales):
            return f"{x:.{decimales}f}".replace(".", ",").replace("-", "−")

        gu10 = " ".join(guardas.__doc__.split()).split("- GU-10.")[1]
        self.assertIn(f"entre {es(lo, 2)} y {es(hi, 2)} h", gu10)
        self.assertIn(f"k = {es(min(d_r), 0)}", gu10)
        lo2, hi2 = banda(U.ajustado("TP_VENTANA").a("TP_VENTANA"))
        self.assertIn(f"de {es(lo2, 1)} a {es(hi2, 1)} h", gu10)
        self.assertIn("BAT-5", gu10)

    def test_guardas_reune_las_activas(self):
        """guardas() y marcas(): esquemas, «*» en las que no dependen de H y respeto de lineas_activas."""
        anotado, serie, ctx = _estacion(semilla=51)
        meses = _meses(anotado, {(2019, m): VERSION_A for m in (5, 6, 7)})
        g = guardas.guardas(anotado, serie, meses, {}, ctx)
        validar_esquema(g, ESQUEMA_GUARDAS, nombre="guardas")
        self.assertEqual(set(g["guarda"]), {"E3d", "P7", "T-P", "E4t", "G-version"})
        self.assertEqual(set(g.loc[g["guarda"].isin(["P7", "G-version"]), "H"]), {"*"})
        # bajo el reloj verdadero (F(−4) ≡ C(Santiago) en invierno) ninguna guarda falla; bajo F(0) T-P sí ve
        # la forma de reloj (k = −4), pero decision sólo la consulta con K = {H}
        verdadero = g["H"].isin([F4, "C(Santiago)", "*"])
        self.assertFalse((verdadero & (g["resultado"] == ResultadoGuarda.FALLA)).any(), g[g["resultado"] == "falla"])
        self.assertEqual(_una(g, "guarda", "T-P", "F(0)", "R1")["resultado"], ResultadoGuarda.FALLA)
        metricas = {guardas.METRICAS_E3: lf.e3(anotado, serie, ctx, "Ts").metricas,
                    guardas.METRICAS_E4: pd.concat([lf.ajustes_e4(anotado, ctx, v) for v in ("Ts", "HR")],
                                                   ignore_index=True),
                    guardas.FILTRO_E3T: lf.filtro_representatividad(anotado, serie, ctx)}
        m = guardas.marcas(anotado, serie, metricas, ctx)
        validar_esquema(m, ESQUEMA_MARCAS, nombre="marcas")
        self.assertEqual(set(m["marca"]), {"G-HR", "G-viento", guardas.MARCA_DESFASE_TERMICO_LOCAL})
        self.assertEqual(set(m.loc[m["marca"] == "G-HR", "H"]), {"*"})
        de_variable = m["marca"].isin(["G-HR", "G-viento"]) & m["H"].isin([F4, "C(Santiago)", "*"])
        self.assertEqual(list(m.loc[de_variable, "valor"].unique()), [False])
        self.assertIs(_una(m, "marca", "G-viento", "F(0)")["valor"], True)      # bajo F(0) el viento sí se marca
        solo = ContextoEstacion(**{**ctx.__dict__, "lineas_activas": frozenset({Linea.E3D})})
        self.assertEqual(set(guardas.guardas(anotado, serie, meses, metricas, solo)["guarda"]), {"E3d"})
        self.assertEqual(len(guardas.marcas(anotado, serie, metricas, solo)), 0)


# ---------------------------------------------------------------------------------------------
# Marcas
# ---------------------------------------------------------------------------------------------
class PruebasMarcas(unittest.TestCase):
    def test_p14_g_hr_marca_hr_corrida_4h(self):
        """HR y Td «reloj no verificado»."""
        for c_hr, esperado in ((0, True), (-4, False)):                # Ts en F(−4); HR corrida 4 h o no
            with self.subTest(c_hr=c_hr):
                anotado, _, ctx = _estacion(semilla=61, c_hr=c_hr)
                m = guardas.g_hr(lf.ajustes_e4(anotado, ctx, "Ts"), lf.ajustes_e4(anotado, ctx, "HR"), ctx,
                                 extracto=anotado)
                validar_esquema(m, ESQUEMA_MARCAS, nombre="G-HR")
                self.assertIs(_una(m, "marca", "G-HR", guardas.H_TODAS)["valor"], esperado)
        # con < 1.000 horas con Ts y HR no se aplica
        anotado, _, ctx = _estacion(semilla=61, c_hr=0)
        corto = anotado[anotado["L"] < np.datetime64("2019-06-01")].reset_index(drop=True)
        m = guardas.g_hr(lf.ajustes_e4(corto, ctx, "Ts"), lf.ajustes_e4(corto, ctx, "HR"), ctx, extracto=corto)
        self.assertIsNone(_una(m, "marca", "G-HR", "*")["valor"])

    def test_p14_g_viento_marca_viento_corrido_4h(self):
        """Viento «reloj no verificado»."""
        anotado, serie, ctx = _estacion(semilla=71, c_viento=0)       # QFE y Ts en F(−4); viento en F(0)
        m = guardas.g_viento(anotado, serie, ctx)
        validar_esquema(m, ESQUEMA_MARCAS, nombre="G-viento")
        self.assertIs(_una(m, "marca", "G-viento", F4)["valor"], True)
        self.assertIs(_una(m, "marca", "G-viento", "F(0)")["valor"], False)      # ĉw = c_H: sin marca
        anotado0, serie0, ctx0 = _estacion(semilla=71)
        m0 = guardas.g_viento(anotado0, serie0, ctx0)
        self.assertIs(_una(m0, "marca", "G-viento", F4)["valor"], False)
        # sin píxel no se aplica
        anotado1, serie1, ctx1 = _estacion(semilla=71, c_viento=0, ctx_kw={"pixel": 99})
        self.assertTrue(all(v is None for v in guardas.g_viento(anotado1, serie1, ctx1)["valor"]))

    def test_p12_marca_posible_media_horaria(self):
        """Media de la hora que termina en la etiqueta: |ρ| > 0,35 h con ≥ 6 años-régimen (§4.3.5 con B6)."""
        anios = (2016, 2017, 2018)
        _, _, ctx = _estacion(semilla=81)
        ctx = ContextoEstacion(**{**ctx.__dict__, "anios": anios,
                                  "regimenes": {a: tablas.regimenes_del_anio(ctx.info.zs, a, ctx.tablas) for a in anios}})

        def metricas(corrimiento, regimenes=("R0", "R1")):
            filas = []
            for anio in anios:
                for reg in regimenes:
                    fila = {c: None for c in ESQUEMA_METRICAS_E3}
                    fila.update(codigo="999002", anio=anio, nivel="regimen", unidad=reg, regimen=reg, variable="QFE",
                                n_pares=2000, n_bloques=30, c_hat_cont=np.nan, estab_c_hat=1.0, estab_c_hat_f=1.0,
                                c_hat_f_cont=(-3 if reg == "R0" else -4) + corrimiento, fino=False, filtro_e3t=False,
                                cociente_a1=np.nan, r_diaria=np.nan)
                    filas.append(fila)
            return pd.DataFrame(filas, columns=list(ESQUEMA_METRICAS_E3)).astype(ESQUEMA_METRICAS_E3)

        self.assertTrue(guardas.marca_media_horaria(metricas(0.5), ctx))                   # 6 años-régimen
        self.assertTrue(guardas.marca_media_horaria(metricas(-0.5), ctx))                  # el mismo, circular
        self.assertFalse(guardas.marca_media_horaria(metricas(0.5, ("R0",)), ctx))         # sólo 3
        self.assertFalse(guardas.marca_media_horaria(metricas(0.2), ctx))                  # |ρ| ≤ 0,35 h
        # Enmienda 3 (B6): ρ usa todos los años-régimen de la estación, no sólo los de años confirmados. Con el
        # texto v1.0.2, una estación con 1 o 2 años confirmados nunca llegaba a 6 años-régimen y no podía
        # llevar la marca (la causa estructural de BAT-6); ahora la firma ya no recibe los años confirmados.
        self.assertNotIn("anios_confirmados", guardas.marca_media_horaria.__code__.co_varnames)


if __name__ == "__main__":
    unittest.main()
