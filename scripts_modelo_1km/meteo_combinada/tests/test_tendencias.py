"""Pruebas de tendencias.py (§5.7 y Anexo B).

Dueño: I15 (ola 4). Las que llevan «sNN» son la prueba NN de §9 del texto: S6 (tendencias falsas y compuerta de deriva) y
la parte de la TF de contaminantes de S16. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos y en memoria; nada se escribe en el disco, y ninguna prueba abre DMC, la meteorología SINCA real,
NASADEM real, ERA5-Land real ni GHS-POP real. Los umbrales son los anclados en M0 (``umbrales.cargar_m0``); sólo se leen
el texto y el JSON de umbrales de APH.

S6 usa la red de ``sintetico.red_s6`` con los parámetros que fijó la coordinación antes de correrla (D15, S6-1 a S6-6;
``sintetico.py`` f87148e7…). Lo que la prueba arma por su cuenta, y se declara:
- los estáticos de C y C_est (``_estaticos``): funciones simples de z, lat y lon, con ``z_e5l`` = 600 m;
- el estado del fondo que S6 no trae (S6-6: «Sólo T»): T_F − Td_F con un ciclo diario fijo (``_depresion``), viento
  constante (u_F = 2, v_F = 1 m/s) y p_F = 900 hPa; la amplitud de T_F con ``fondo_era5l.amplitud_dia_utc``; el clima
  del estado (C_est), las medias por mes y hora UTC de esos campos en 2000-2024;
- ids propios de celda y de estación: ``red_s6`` puede repetir el id de dos celdas que caen en la misma celda de 0,01°
  (pasa en dos de sus 100), y aquí cada punto es una celda distinta;
- los grupos a ≤ 2 km de ``particiones.grupos_mismo_sitio`` (en la red hay cuatro pares);
- las horas válidas de 2025, en 0: la red de S6 termina en 2024.
Las pruebas de la TF por uso (MC-04) y de paridad usan una red chica hecha aquí (``_Mini``): 12 estaciones con reportes
cada 2 h (10 desde 2005 y 2 desde 2018), 10 celdas en 4 comunas y un fondo analítico.
Semilla: ``SEMILLA`` del Anexo A (20261023), que no se eligió probando semillas.
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import (candidatos, ceguera, constantes, decision, fondo_era5l, numerico,  # noqa: E402
                             particiones, salidas, sintetico, tendencias, tipos, umbrales)
from meteo_combinada.tipos import Hiper  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_EPOCA = np.datetime64("2000-01-01T00", "h")
NAN = float("nan")
# D15: la huella de sintetico.py con los parámetros de S6 fijados antes de correrla (COORDINACION_M1, «Ola 4»).
SHA_SINTETICO_S6 = "f87148e775c52243a288c2ca045806f4b567ecbd0ebf4e868dad68849fd3fe0e"
# S6-1 a S6-3 de la coordinación, tal como los guarda red_s6 en «parametros».
PARAMETROS_S6 = {"paso_h": 1, "anios": (2000, 2024), "semilla": 20261023, "sesgo_valle_k": -1.5, "sigma_k": 1.5,
                 "L_km": 100.0, "tau_h": 48.0, "anio_nuevas": 2010}
P_F_S6, U_F_S6, V_F_S6 = 900.0, 2.0, 1.0
# H9 (revisor de la ola 4): la medición de la compuerta de deriva, fijada como regla de regresión (como TASAS_S4): cuántas
# de las 60 combinaciones pasan TF2 con 0,3 K por década. Si el código o la red cambian y la medición cambia, la prueba
# falla y hay que volver a declararla (y al addendum).
MEDICION_DERIVA_S6 = {"B": 0, "AB": 30}
_U = None


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


def _h(fecha: str) -> int:
    return int((np.datetime64(fecha, "h") - _EPOCA).astype(np.int64))


def _info(codigo: str, lat: float, lon: float, z: float, celda) -> tipos.InfoEstacion:
    e, n = (float(x[0]) for x in numerico.utm19s(np.array([lat, lat]), np.array([lon, lon])))
    return tipos.InfoEstacion(
        codigo=codigo, nombre=f"E{codigo}", conjunto="V", macrozona="centro", grupo=tipos.id_grupo([codigo]),
        omm=None, tipo=None, propietario=None, lat_txt=f"{lat:.4f}", lon_txt=f"{lon:.4f}", alt_txt=f"{z:.0f}",
        lat=float(lat), lon=float(lon), z_cat=float(z), rho_km=0.1, k3_pasa=True, z_s=float(z),
        z_s_fuente="catalogo", celda=celda, utm_e=e, utm_n=n, bloque="", pix0=0, pix1=-1, pix2=-1, pix3=-1, w0=1.0,
        w1=0.0, w2=0.0, w3=0.0, respaldo_16km=False, sin_fondo=False, excluida=False, motivo=None)


def _con_grupos(infos: dict) -> dict:
    grupos = particiones.grupos_mismo_sitio(infos, _umbrales())
    return {c: dataclasses.replace(i, grupo=grupos.get(c, i.grupo)) for c, i in infos.items()}


def _estaticos(ids, lat, lon, z, cod) -> pd.DataFrame:
    """Estáticos sintéticos mínimos de C (``ESQUEMA_ESTATICAS_CELDA_C``), funciones de z, lat y lon (declarados)."""
    ids, lat, lon, z = (np.asarray(x, dtype=t) for x, t in ((ids, np.int64), (lat, float), (lon, float), (z, float)))
    n = ids.size
    d = {"celda": ids, "z_media": z, "z_poblada": z, "z_poblada_es_media": np.ones(n, bool), "frac_dato": np.ones(n),
         "tpi1": 0.05 * (z - 600.0), "tpi5": 0.1 * (z - 600.0), "tpi1_truncado": np.zeros(n, bool),
         "tpi5_truncado": np.zeros(n, bool), "pendiente_deg": 2.0 + 3.0 * np.abs(lon + 70.8),
         "log_dist_costa": np.log1p(100.0 * (lon + 72.0))}
    fr = {"lulc_urbano": np.clip(0.2 + 0.1 * (lat + 34.0), 0, 1), "lulc_cultivo": 0.3 - 0.05 * (lat + 34.0),
          "lulc_bosque": 0.1 + 0.02 * (lon + 71.0), "lulc_matorral_pastizal": np.full(n, 0.2),
          "lulc_desnudo": 0.05 + 0.01 * (z / 1000.0), "lulc_agua": np.full(n, 0.01), "lulc_nieve_hielo": np.zeros(n)}
    for c in tipos.LULC:
        d[c] = fr[c]
    d.update({"lat": lat, "macrozona_cod": np.full(n, tipos.MACROZONA_COD["centro"], np.int8),
              "cod_comuna": np.asarray(cod, np.int32), "z_e5l": np.full(n, 600.0)})
    esquema = {**dict(tipos.ESQUEMA_ESTATICAS_CELDA), "z_e5l": "float64"}
    return pd.DataFrame(d).astype(esquema)[list(tipos.ESQUEMA_ESTATICAS_CELDA_C)]


def _depresion(h) -> np.ndarray:
    """T_F − Td_F de S6 (declarado): 4 K más un ciclo diario de 2 K con el máximo a las 19 UTC."""
    return 4.0 + 2.0 * np.cos(2 * np.pi * ((np.asarray(h) % 24) - 19.0) / 24.0)


def _clima_mes_hora(h: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Medias por mes y hora UTC (12 × 24) de cada columna de x (tiempo × punto) → punto × 12 × 24."""
    i = (tendencias.mes2000(h) % 12) * 24 + h % 24
    x = np.atleast_2d(x.T).T if x.ndim == 1 else x
    salida = np.empty((x.shape[1], 12, 24))
    for j in range(x.shape[1]):
        ok = np.isfinite(x[:, j])
        s = np.bincount(i[ok], weights=x[ok, j], minlength=288)
        n = np.bincount(i[ok], minlength=288)
        salida[j] = (s / n).reshape(12, 24)
    return salida


def _horas_validas(h: np.ndarray, validos: np.ndarray, codigos, anios) -> dict:
    """TEN-1: año → tabla (codigo, horas) desde la validez hora × estación."""
    anio = tendencias.anio_de(h)
    return {y: pd.DataFrame({"codigo": list(codigos), "horas": validos[anio == y].sum(axis=0).astype(np.int64)})
            for y in anios}


def _resultados_por(res: dict, cand: str, prueba: str) -> dict:
    return {et: r[prueba] for (c, et, v), r in res.items() if c == cand}


# ---------------------------------------------------------------------------
# S6 (D15: S6-1 a S6-6)
# ---------------------------------------------------------------------------
class _S6:
    """Todo lo caro de S6, calculado una vez: la red, los residuos con y sin deriva, las dos pasadas y sus TF."""

    def __init__(self) -> None:
        t0 = time.perf_counter()
        U = self.U = _umbrales()
        self.red = sintetico.red_s6()
        self.red_d = sintetico.red_s6(deriva_k_decada=constantes.valor("DERIVA_K_DECADA"))
        est, cel = self.red["estaciones"], self.red["celdas"]
        self.codigos = est["codigo"].astype(str).tolist()
        ids_est = 5_000_000_000 + np.arange(len(est), dtype=np.int64)
        infos = {c: _info(c, f.lat, f.lon, f.z_m, int(ids_est[k])) for k, (c, f) in
                 enumerate(zip(self.codigos, est.itertuples()))}
        self.infos = _con_grupos(infos)
        self.estaticos_est = _estaticos(ids_est, est["lat"], est["lon"], est["z_m"], np.zeros(len(est)))
        h, obs, r, r_d, T_est = [], [], [], [], []
        for y in range(PARAMETROS_S6["anios"][0], PARAMETROS_S6["anios"][1] + 1):
            c = sintetico.campos_s6(self.red, "estaciones", anios=(y, y))
            cd = sintetico.campos_s6(self.red_d, "estaciones", anios=(y, y))
            h.append(c["h"])
            obs.append(np.isfinite(c["obs"]))
            r.append((c["obs"] - c["fondo"]).astype(np.float32))
            r_d.append((cd["obs"] - cd["fondo"]).astype(np.float32))
            T_est.append(c["fondo"].astype(np.float32))
        self.h = np.concatenate(h)
        self.validos = np.concatenate(obs)
        r, r_d, T_est = np.concatenate(r), np.concatenate(r_d), np.concatenate(T_est)
        self.horas_validas = _horas_validas(self.h, self.validos, self.codigos, range(2000, 2026))
        self.escenarios = tendencias.escenarios_tf(self.horas_validas, "T", U)
        self.datos = self._datos(r, T_est, con_c=True)
        self.datos_d = self._datos(r_d, None, con_c=False)
        del r, r_d, T_est
        cel = cel.assign(celda=6_000_000_000 + np.arange(len(cel), dtype=np.int64))
        self.celdas_tabla = cel
        T_cel = np.concatenate([sintetico.campos_s6(self.red, "celdas", anios=(y, y))["fondo"]
                                for y in range(2000, 2025)])
        amp = fondo_era5l.amplitud_dia_utc(T_cel, self.h)
        n = len(cel)
        clima = {"T": _clima_mes_hora(self.h, T_cel), "amp": _clima_mes_hora(self.h, amp),
                 "T_menos_Td": np.broadcast_to(_depresion(np.arange(24))[None, None, :], (n, 12, 24)).copy(),
                 "rapidez": np.full((n, 12, 24), math.hypot(U_F_S6, V_F_S6))}
        del T_cel, amp
        self.celdas = tendencias.celdas_tf(
            cel, cel["z_m"].to_numpy(), clima_estado=clima,
            estaticos=_estaticos(cel["celda"], cel["lat"], cel["lon"], cel["z_m"], cel["cod_comuna"]))
        self.combos = tendencias.combinaciones_nucleo(U)
        alfas = [float(a) for a in U.a("C_ALFAS")]
        et = tendencias.etiqueta_hiper
        self.cfg = {"A": {et(x): {"T": x} for x in self.combos}, "B": {et(x): {"T": x} for x in self.combos},
                    "AB": {et(x): {"T": (x, x)} for x in self.combos},
                    "C": {et(a): {"T": a} for a in alfas}, "C_est": {et(a): {"T": a} for a in alfas}}
        t1 = time.perf_counter()
        self.pasada = tendencias.PasadaTF(self.datos, self.celdas, {"T": self.escenarios}, self.cfg, U,
                                          variables=("T",))
        self.medias = self.pasada.correr(self.h, self._fondo(self.red))
        self.res = tendencias.resultados_tf(self.medias, U, comprobar=False)
        cfg_d = {k: self.cfg[k] for k in tendencias.CON_DERIVA}
        self.pasada_d = tendencias.PasadaTF(self.datos_d, self.celdas, {"T": self.escenarios}, cfg_d, U,
                                            variables=("T",), pruebas=("TF2",))
        self.res_d = tendencias.resultados_tf(self.pasada_d.correr(self.h, self._fondo(self.red_d)), U,
                                              comprobar=False)
        self.deriva = {c: _resultados_por(self.res_d, c, "TF2") for c in tendencias.CON_DERIVA}
        self.segundos = {"preparacion": t1 - t0, "pasadas": time.perf_counter() - t1}

    def _datos(self, r, T_est, *, con_c: bool) -> tipos.DatosCompetencia:
        U, h = self.U, self.h
        residuos, tramos = {}, []
        fc = {v: {} for v in candidatos.VARIABLES}
        fce = {v: {} for v in candidatos.VARIABLES}
        clima_estado = {}
        for j, c in enumerate(self.codigos):
            ok = self.validos[:, j]
            nan = np.full(int(ok.sum()), NAN)
            df, tr = candidatos.residuos_estacion(c, h[ok], {"T": r[ok, j].astype(np.float64), "Td": nan, "u": nan,
                                                             "v": nan, "p": nan}, U)
            residuos[c] = df
            tramos.append(tr)
            if con_c:
                T = T_est[:, j].astype(np.float64)
                amp = fondo_era5l.amplitud_dia_utc(T, h)
                pe = pd.DataFrame({"h": h.astype(np.int32), "T_F": T, "Td_F": T - _depresion(h),
                                   "p_F": np.full(h.size, P_F_S6), "u_F": np.full(h.size, U_F_S6),
                                   "v_F": np.full(h.size, V_F_S6), "amp_TF": amp}).astype(
                    dict(tipos.ESQUEMA_PUNTOS_E5L))
                ce = {"T": _clima_mes_hora(h, T)[0], "amp": _clima_mes_hora(h, amp)[0],
                      "T_menos_Td": np.broadcast_to(_depresion(np.arange(24)), (12, 24)).copy(),
                      "rapidez": np.full((12, 24), math.hypot(U_F_S6, V_F_S6))}
                clima_estado[c] = ce
                r1 = candidatos.filas_c({c: df}, self.estaticos_est, {c: pe}, U, infos=self.infos)
                r2 = candidatos.filas_c({c: df}, self.estaticos_est, {c: ce}, U, infos=self.infos,
                                        climatologico=True)
                for v in candidatos.VARIABLES:
                    fc[v].update(r1[v])
                    fce[v].update(r2[v])
        return tipos.DatosCompetencia(
            residuos=residuos, climatologias=candidatos.climatologias_a(residuos, U),
            tramos=pd.concat(tramos, ignore_index=True), filas_c={"C": fc, "C_est": fce} if con_c else {},
            estaticos=self.estaticos_est, estaciones=self.infos, pliegues=(), puntos_e5l={},
            clima_estado=clima_estado)

    def _fondo(self, red: dict):
        cache: dict = {}

        def fondo(hh, idx):
            y = int(tendencias.anio_de(hh[:1])[0])
            if y not in cache:
                cache.clear()
                c = sintetico.campos_s6(red, "celdas", anios=(y, y))
                cache[y] = (c["h"], c["fondo"])
            h_y, F = cache[y]
            T = F[np.searchsorted(h_y, hh)][:, idx]
            return {"T_F": T, "Td_F": T - _depresion(hh)[:, None], "p_F": np.full(T.shape, P_F_S6),
                    "u_F": np.full(T.shape, U_F_S6), "v_F": np.full(T.shape, V_F_S6)}
        return fondo


_S6_CACHE = None


def _s6() -> _S6:
    global _S6_CACHE
    if _S6_CACHE is None:
        _S6_CACHE = _S6()
    return _S6_CACHE


class PruebasS6(unittest.TestCase):
    """S6 de §9 con los parámetros de D15 (S6-1 a S6-6), en las 60 combinaciones (S6-4; TEN-15)."""

    @classmethod
    def setUpClass(cls):
        cls.s6 = _s6()
        cls.U = cls.s6.U

    def _fallas(self, cand: str, prueba: str, quiere: str) -> list[str]:
        return [f"{et}: {r['resultado']} (media {r['media_pond']:.4g}, P95 {r['p95_pond']:.4g})"
                for et, r in _resultados_por(self.s6.res, cand, prueba).items() if r["resultado"] != quiere]

    def test_s06_parametros_fijados_antes_de_correr(self):
        """D15: ``sintetico.py`` es el de la coordinación y la red trae S6-1 a S6-3; el 0,3 K por década, el 2010, el
        −1,5 K y la red (20 en 2000-2009 y 120 en 2010-2024) son los del A2."""
        self.assertEqual(hashlib.sha256((_RAIZ / "meteo_combinada" / "sintetico.py").read_bytes()).hexdigest(),
                         SHA_SINTETICO_S6)
        p = self.s6.red["parametros"]
        for k, v in PARAMETROS_S6.items():
            self.assertEqual(p[k], v, k)
        self.assertEqual(p["deriva_k_decada"], 0.0)
        self.assertEqual(self.s6.red_d["parametros"]["deriva_k_decada"], constantes.valor("DERIVA_K_DECADA"))
        self.assertEqual(p["sesgo_valle_k"], constantes.valor("S6_SESGO_K"))
        n_hist, a0, _, n_nuevas, a_nuevas, a1 = constantes.valor("S6_RED")
        est = self.s6.red["estaciones"]
        self.assertEqual((int(est["historica"].sum()), int((~est["historica"]).sum())), (n_hist, n_nuevas))
        self.assertEqual(p["anio_nuevas"], a_nuevas)
        self.assertEqual(constantes.valor("DERIVA_ANIO"), a_nuevas)
        self.assertEqual((p["anios"][0], p["anios"][1]), (a0, a1))        # MC-07: las 20 siguen hasta 2024
        self.assertEqual(len(self.s6.combos), 60)
        self.assertEqual(self.s6.celdas.n, 100)
        self.assertEqual(np.unique(self.s6.celdas.cod_comuna).size, 25)

    def test_s06_b_falla_tf1_con_sesgo_en_los_valles(self):
        """Fondo con sesgo fijo de −1,5 K en los valles: B falla TF1 en las 60 combinaciones (S6-4)."""
        res = _resultados_por(self.s6.res, "B", "TF1")
        self.assertEqual(len(res), 60)
        self.assertEqual(self._fallas("B", "TF1", "falla"), [], "B no falla TF1 en estas combinaciones")

    def test_s06_a_c_y_c_est_dan_cero(self):
        """A, C y C_est dan exactamente 0 (≤ 10⁻⁶) en TF1 y TF2: A en las 60 combinaciones, C y C_est en sus 5 α."""
        tol = constantes.valor("TF_CERO_TOL")
        esperadas = {"A": 60, "C": 5, "C_est": 5}
        for cand, n in esperadas.items():
            for prueba in tendencias.PRUEBAS:
                res = _resultados_por(self.s6.res, cand, prueba)
                self.assertEqual(len(res), n, (cand, prueba))
                malos = {et: (r["media_pond"], r["p95_pond"], r["max_abs"]) for et, r in res.items()
                         if not (r["media_pond"] <= tol and r["p95_pond"] <= tol and r["max_abs"] <= tol)}
                self.assertEqual(malos, {}, f"{cand} {prueba} > 10⁻⁶")
                self.assertTrue(all(r["resultado"] == "pasa" for r in res.values()))
                for r in res.values():
                    tendencias.comprobar_cero(cand, r)          # TEN-10: no lanza

    def test_s06_ab_pasa(self):
        """AB pasa TF1 y TF2 con sesgos estacionarios (MC-50), en las 60 combinaciones (TEN-17)."""
        for prueba in tendencias.PRUEBAS:
            with self.subTest(prueba=prueba):
                self.assertEqual(len(_resultados_por(self.s6.res, "AB", prueba)), 60)
                self.assertEqual(self._fallas("AB", prueba, "pasa"), [], f"AB no pasa {prueba}")

    def test_s06_compuerta_de_deriva(self):
        """Deriva del fondo de 0,3 K por década; TF2 a B y AB en las 60 combinaciones; el contenido de
        ``deriva_s6.json`` pasa la guarda de su clase (resumen). El resultado es una medición para el addendum."""
        compuerta = tendencias.compuerta_deriva(self.s6.deriva, umbrales=self.U)
        self.assertEqual(set(compuerta), {"B", "AB"})
        self.assertTrue(all(isinstance(x, bool) for x in compuerta.values()))
        for cand in ("B", "AB"):
            self.assertEqual(compuerta[cand], all(r["resultado"] == "pasa" for r in self.s6.deriva[cand].values()))
        contenido = tendencias.contenido_deriva_s6(self.s6.deriva, compuerta, regla=self.s6.escenarios.regla,
                                                   n_red=self.s6.escenarios.n_red, parametros=self.s6.red_d["parametros"])
        ceguera.vigilar_salida("deriva_s6.json", contenido, clase="resumen")
        self.assertEqual(ceguera.clase_de_ruta("deriva_s6.json"), "resumen")
        self.assertEqual(contenido["red_tf2"], {"regla": "r2000_2025", "n_red": 20})
        cotas = constantes.valor("TF_COTAS_T")
        self.assertEqual((contenido["cotas"]["media"], contenido["cotas"]["p95"]), (cotas[2], cotas[3]))
        for cand in ("B", "AB"):
            c = contenido["candidatos"][cand]
            self.assertEqual(c["n_combinaciones"], 60)
            self.assertEqual(c["pasa"], compuerta[cand])
            self.assertEqual(c["n_pasan"] == 60, compuerta[cand])
            self.assertEqual(c["peor_media"]["media_pond"], max(x["media_pond"] for x in c["combinaciones"]))
        # La compuerta no sale de B y AB, exige las 60, y una TF2 no evaluable hace fallar S6 (EMC1-2).
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.compuerta_deriva({"B": self.s6.deriva["B"]}, umbrales=self.U)
        uno = dict(list(self.s6.deriva["B"].items())[:1])
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.compuerta_deriva({"B": uno, "AB": self.s6.deriva["AB"]}, umbrales=self.U)
        ne = {k: {**r, "resultado": "no_evaluable"} for k, r in self.s6.deriva["AB"].items()}
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.compuerta_deriva({"B": self.s6.deriva["B"], "AB": ne}, umbrales=self.U)
        # H4: umbrales obligatorio; sólo TF2, de T y con las cotas de T; el resultado debe ser el de sus cotas.
        with self.assertRaises(TypeError):
            tendencias.compuerta_deriva(self.s6.deriva)
        tf1 = {c: _resultados_por(self.s6.res, c, "TF1") for c in ("B", "AB")}
        for malo in (tf1, {c: {k: {**r, "variable": "Td"} for k, r in self.s6.deriva[c].items()} for c in ("B", "AB")},
                     {c: {k: {**r, "cota_media": 0.1} for k, r in self.s6.deriva[c].items()} for c in ("B", "AB")},
                     {c: {k: {**r, "resultado": "pasa"} for k, r in self.s6.deriva[c].items()} for c in ("B", "AB")}):
            with self.assertRaises(tendencias.ErrorTendencias):
                tendencias.compuerta_deriva(malo, umbrales=self.U)
        # H9: la deriva entró (TF2 con deriva distinta de sin deriva en cada combinación) y la medición es la declarada.
        for cand in ("B", "AB"):
            for et, r in self.s6.deriva[cand].items():
                self.assertNotEqual(r["media_pond"], self.s6.res[(cand, et, "T")]["TF2"]["media_pond"], (cand, et))
        self.assertEqual({c: contenido["candidatos"][c]["n_pasan"] for c in ("B", "AB")}, MEDICION_DERIVA_S6,
                         "la medición de la compuerta de deriva cambió: volver a declararla (H9) y al addendum")
        # H8: la escribe salidas (clase resumen) en una carpeta temporal, y se relee igual.
        with tempfile.TemporaryDirectory() as tmp:
            sha = salidas.escribir("deriva_s6.json", contenido, clase="resumen", raiz=tmp)
            datos = (Path(tmp) / "deriva_s6.json").read_bytes()
        self.assertEqual(hashlib.sha256(datos).hexdigest(), sha)
        self.assertEqual(json.loads(datos), json.loads(json.dumps(contenido)))

    def test_s06_red_sintetica_da_tf2_evaluable(self):
        """EMC1-2: la red de S6 da TF2 evaluable (sin y con deriva, que tienen las mismas estaciones); si no, S6 falla."""
        red, regla = tendencias.red_constante(self.s6.horas_validas, "T", self.U)
        self.assertNotEqual(regla, "ninguna", "la red de S6 da TF2 no evaluable: S6 falla (EMC1-2)")
        self.assertGreaterEqual(len(red), constantes.valor("TF2_RED_MIN_ESTACIONES"))
        historicas = set(self.s6.red["estaciones"].loc[self.s6.red["estaciones"]["historica"], "codigo"].astype(str))
        self.assertEqual((regla, set(red)), ("r2000_2025", historicas))
        self.assertEqual(tendencias.red_historica(self.s6.horas_validas, "T", self.U), frozenset(historicas))
        for res in (self.s6.res, self.s6.res_d):
            self.assertTrue(all(r["TF2"]["resultado"] != "no_evaluable" and r["TF2"]["regla"] == "r2000_2025"
                                for r in res.values()))

    def test_s06_ab_no_depende_de_la_a_elegida(self):
        """TEN-15: en AB, A es el mismo en los dos escenarios y se cancela; con otra A, la TF de AB es la misma."""
        U = self.U
        x = self.s6.combos[25]
        otra = Hiper(10.0, 0.0, 1.0)
        cfg = {"AB": {"igual": {"T": (x, x)}, "otra": {"T": (otra, x)}}}
        pasada = tendencias.PasadaTF(self.s6.datos, self.s6.celdas, {"T": self.s6.escenarios}, cfg, U,
                                     variables=("T",), pruebas=("TF1",))
        res = tendencias.resultados_tf(pasada.correr(self.s6.h, self.s6._fondo(self.s6.red)), U)
        a, b = res[("AB", "igual", "T")]["TF1"], res[("AB", "otra", "T")]["TF1"]
        self.assertAlmostEqual(a["media_pond"], b["media_pond"], delta=1e-9)
        self.assertAlmostEqual(a["p95_pond"], b["p95_pond"], delta=1e-9)
        self.assertEqual(a["media_pond"], self.s6.res[("AB", tendencias.etiqueta_hiper(x), "T")]["TF1"]["media_pond"])

    def test_s06_filas_reales_en_la_decision(self):
        """Las filas reales de S6 (como lo crónico, que sólo usa T) pasan por ``decision.compuertas`` y
        ``decidir_combinacion``: B queda fuera por TF y la red de TF2 es la de S6."""
        U = self.U
        x, alfa = tendencias.etiqueta_hiper(self.s6.combos[25]), tendencias.etiqueta_hiper(10.0)
        por_uso = {"cronico": {(c, "T"): self.s6.res[(c, x if c != "C_est" else alfa, "T")]
                               for c in ("A", "B", "AB", "C_est")}}
        tf = tendencias.filas_tf(por_uso, {"T": self.s6.escenarios})
        tipos.validar_esquema(tf, tipos.ESQUEMA_TF, nombre="tf")
        self.assertEqual(len(tf), 8)
        d = next(d for d in (sintetico.tablas_metricas(c) for c in sintetico.CASOS_METRICAS if c != "soporte")
                 if d["uso"] == "cronico" and not d["e0_excluidos"])
        entradas = tipos.EntradasDecision(tipos.Uso.CRONICO, tipos.Grupo.T_TD, d["validacion"], tf, d["replicas"], {})
        tabla = decision.compuertas("cronico", "T_Td", entradas, U)
        tf_b = tabla[(tabla["candidato"] == "B") & (tabla["compuerta"] == "TF")]
        self.assertFalse(bool(tf_b["pasa"].all()))
        r = decision.decidir_combinacion("cronico", "T_Td", entradas, umbrales=U)
        self.assertIn("TF", r.motivos.get("B", ()))
        self.assertEqual(r.red_tf2["T"].value, "r2000_2025")


# ---------------------------------------------------------------------------
# Red chica para la TF por uso (MC-04) y las pruebas de paridad
# ---------------------------------------------------------------------------
class _Mini:
    """12 estaciones con reportes cada 2 h (10 desde 2005 y 2 desde 2018), 10 celdas en 4 comunas y un fondo analítico."""
    DESDE, HASTA = "2005-01-01T00", "2026-01-01T00"

    def __init__(self) -> None:
        U = self.U = _umbrales()
        rng = numerico.generador(U.a("SEMILLA"), "test_tendencias", "mini")
        infos = {}
        for k in range(12):
            lat = -33.0 - 0.06 * (k // 4) - 0.01 * (k % 3)
            lon = -70.95 + 0.11 * (k % 4) + 0.01 * (k // 4)
            z = 400.0 + 150.0 * (k % 4) + 40.0 * (k // 4)
            infos[f"{800001 + k:06d}"] = _info(f"{800001 + k:06d}", lat, lon, z, 7_000_000_000 + k)
        self.infos = _con_grupos(infos)
        self.codigos = sorted(self.infos)
        info = [self.infos[c] for c in self.codigos]
        self.estaticos_est = _estaticos([i.celda for i in info], [i.lat for i in info], [i.lon for i in info],
                                        [i.z_s for i in info], np.zeros(12))
        h_todo = np.arange(_h(self.DESDE), _h(self.HASTA), dtype=np.int64)
        residuos, tramos, puntos, clima_estado = {}, [], {}, {}
        validos = np.zeros((h_todo.size, 12), bool)
        for j, c in enumerate(self.codigos):
            desde = _h("2005-01-01T00") if j < 10 else _h("2018-01-01T00")
            hh = h_todo[(h_todo >= desde) & (h_todo % 2 == 0)]
            validos[np.searchsorted(h_todo, hh), j] = True
            n = hh.size
            r = {"T": 0.5 + 0.3 * (j % 3) + rng.normal(0, 0.6, n), "Td": -0.4 + 0.2 * (j % 2) + rng.normal(0, 0.8, n),
                 "u": 0.2 * (j % 3 - 1) + rng.normal(0, 0.5, n), "v": -0.1 + rng.normal(0, 0.5, n),
                 "p": 0.001 * (j % 4) + rng.normal(0, 2e-4, n)}
            residuos[c], tr = candidatos.residuos_estacion(c, hh, r, U)
            tramos.append(tr)
            F = self.fondo_en(h_todo, np.array([info[j].lat]), np.array([info[j].z_s]))
            amp = fondo_era5l.amplitud_dia_utc(F["T_F"][:, 0], h_todo)
            puntos[c] = pd.DataFrame({"h": h_todo.astype(np.int32), **{k: F[k][:, 0] for k in fondo_era5l.CAMPOS_F},
                                      "amp_TF": amp}).astype(dict(tipos.ESQUEMA_PUNTOS_E5L))[
                list(tipos.ESQUEMA_PUNTOS_E5L)]
            clima_estado[c] = self._clima(h_todo, F, amp[:, None], 0)
        self.h_todo, self.validos = h_todo, validos
        datos_base = dict(residuos=residuos, climatologias=candidatos.climatologias_a(residuos, U),
                          tramos=pd.concat(tramos, ignore_index=True), estaticos=self.estaticos_est,
                          estaciones=self.infos, pliegues=(), puntos_e5l=puntos, clima_estado=clima_estado)
        filas = {"C": candidatos.filas_c(residuos, self.estaticos_est, puntos, U, infos=self.infos),
                 "C_est": candidatos.filas_c(residuos, self.estaticos_est, clima_estado, U, infos=self.infos,
                                             climatologico=True)}
        self.datos = tipos.DatosCompetencia(filas_c=filas, **datos_base)
        # Celdas: 10 en 4 comunas, con w_ghs; más una sin comuna y una sin población, que no entran (TEN-6).
        lat = np.array([-33.02, -33.05, -33.08, -33.11, -33.14, -33.04, -33.09, -33.12, -33.15, -33.03, -33.06, -33.1])
        lon = np.array([-70.9, -70.85, -70.8, -70.75, -70.7, -70.65, -70.6, -70.88, -70.72, -70.62, -70.8, -70.7])
        com = np.array([13101, 13101, 13101, 13102, 13102, 13102, 13103, 13103, 13104, 13104, 0, 13104])
        w = np.array([1200.0, 300.0, 800.0, 2500.0, 150.0, 900.0, 1800.0, 450.0, 700.0, 1100.0, 50.0, 0.0])
        z = 450.0 + 900.0 * (lon + 70.9)
        self.tabla_celdas = pd.DataFrame({"celda": 8_000_000_000 + np.arange(12), "lat": lat, "lon": lon,
                                          "cod_comuna": com, "w_ghs": w})
        self.z_celdas = {"ambiental": z, "salud": z - 30.0}
        self.horas_validas = _horas_validas(h_todo, validos, self.codigos, range(2000, 2026))
        self.escenarios = {v: tendencias.escenarios_tf(self.horas_validas, v, U) for v in tendencias.VARIABLES_TF}
        hT, hTd, hU, hP = Hiper(50.0, 50.0, 0.2), Hiper(25.0, 0.0, 0.5), Hiper(100.0, 50.0, 0.2), Hiper(50.0, 150.0, 1.0)
        nucleo = {"T": hT, "Td": hTd, "u": hU, "v": hU, "p": hP}
        self.cfg_amb = {"A": {"prod": dict(nucleo)}, "B": {"prod": {k: Hiper(h.L_km * 2, h.lam, h.kappa)
                                                                     for k, h in nucleo.items()}},
                        "AB": {"prod": {k: (h, Hiper(25.0, 50.0, 0.5)) for k, h in nucleo.items()}},
                        "C": {"prod": {"T": 10.0, "Td": 1.0, "u": 100.0, "v": 100.0, "p": 10.0}}}
        self.cfg_salud = {"A": {"prod": {"T": hT, "Td": hTd}}, "B": {"prod": {"T": hT, "Td": hTd}},
                          "AB": {"prod": {"T": (hT, hTd), "Td": (hTd, hT)}}, "C": {"prod": {"T": 10.0, "Td": 1.0}},
                          "C_est": {"prod": {"T": 10.0}}}

    @staticmethod
    def fondo_en(h, lat, z) -> dict:
        """Un fondo analítico (hora × punto), sin tendencia."""
        h = np.asarray(h)
        dia = (h / 24.0) % 365.25
        ciclo = 5.0 * np.cos(2 * np.pi * (dia - 15.0) / 365.25) + 4.0 * np.cos(2 * np.pi * ((h % 24) - 19.0) / 24.0)
        T = 15.0 - 6.5 * np.asarray(z)[None, :] / 1000.0 + ciclo[:, None] + 0.5 * (np.asarray(lat)[None, :] + 33.0)
        dep = 5.0 + 2.0 * np.cos(2 * np.pi * ((h % 24) - 19.0) / 24.0)
        u = np.broadcast_to((1.5 + 0.5 * np.sin(2 * np.pi * (h % 24) / 24.0))[:, None], T.shape).copy()
        v = np.broadcast_to((-0.5 + 0.3 * np.cos(2 * np.pi * (h % 24) / 24.0))[:, None], T.shape).copy()
        p = np.broadcast_to(numerico.p_std(np.asarray(z))[None, :], T.shape) + 0.5 * np.cos(2 * np.pi * dia / 365.25)[:, None]
        return {"T_F": T, "Td_F": T - dep[:, None], "p_F": p, "u_F": u, "v_F": v}

    @staticmethod
    def _clima(h, F, amp, j) -> dict:
        T = F["T_F"][:, j]
        return {"T": _clima_mes_hora(h, T)[0], "T_menos_Td": _clima_mes_hora(h, T - F["Td_F"][:, j])[0],
                "rapidez": _clima_mes_hora(h, np.hypot(F["u_F"][:, j], F["v_F"][:, j]))[0],
                "amp": _clima_mes_hora(h, amp[:, 0])[0]}

    def celdas(self, uso: str) -> tendencias.CeldasTF:
        t = self.tabla_celdas
        z = self.z_celdas[uso]
        h = np.arange(_h("2010-01-01T00"), _h("2011-01-01T00"), dtype=np.int64)
        F = self.fondo_en(h, t["lat"].to_numpy(), z)
        amp = fondo_era5l.amplitud_dia_utc(F["T_F"], h)
        clima = {v: np.stack([self._clima(h, F, amp[:, [i]], i)[v] for i in range(len(t))]) for v in
                 candidatos.ESTADO_C}
        return tendencias.celdas_tf(t, z, estaticos=_estaticos(t["celda"], t["lat"], t["lon"], z, t["cod_comuna"]),
                                    clima_estado=clima)

    def fondo(self, celdas: tendencias.CeldasTF):
        def f(hh, idx):
            return self.fondo_en(hh, celdas.lat[idx], celdas.z[idx])
        return f


_MINI_CACHE = None


def _mini() -> _Mini:
    global _MINI_CACHE
    if _MINI_CACHE is None:
        _MINI_CACHE = _Mini()
    return _MINI_CACHE


class PruebasPorUso(unittest.TestCase):
    """MC-04 (TF por candidato × uso × variable), las filas en ``decision`` y la paridad con ``candidatos``."""

    @classmethod
    def setUpClass(cls):
        cls.m = _mini()
        cls.U = cls.m.U
        cls.horas = np.arange(_h("2003-01-01T00"), _h("2026-01-01T00"), dtype=np.int64)
        cls.pasadas, cls.res = {}, {}
        for uso, cfg in (("ambiental", cls.m.cfg_amb), ("salud", cls.m.cfg_salud)):
            celdas = cls.m.celdas(uso)
            variables = tendencias.VARIABLES_TF if uso == "ambiental" else ("T", "Td")
            p = tendencias.PasadaTF(cls.m.datos, celdas, cls.m.escenarios, cfg, cls.U, variables=variables)
            cls.pasadas[uso] = (p, celdas)
            cls.res[uso] = tendencias.resultados_tf(p.correr(cls.horas, cls.m.fondo(celdas)), cls.U)
        cls.por_uso = tendencias.tf_por_uso(cls.res["ambiental"], cls.res["salud"])
        cls.tf = tendencias.filas_tf(cls.por_uso, cls.m.escenarios)

    def test_redes_de_la_red_chica(self):
        """La red chica: 10 históricas (desde 2005) y la red constante de r2003_2025 (21 de 23 años ≥ 80 %)."""
        for v in tendencias.VARIABLES_TF:
            e = self.m.escenarios[v]
            self.assertEqual((e.regla, e.n_red, len(e.historica)), ("r2003_2025", 10, 10), v)
            self.assertEqual(e.historica, frozenset(self.m.codigos[:10]))

    def test_tf_por_candidato_uso_y_variable_mc04(self):
        """MC-04 y MC-55: ambiental A, B, AB, C × T, Td, rapidez, p; agudo A, B, AB, C × T, Td; crónico A, B, AB, C_est
        × T, con las filas de A, B y AB iguales a las del agudo (se calcula una vez). En ``tipos.ESQUEMA_TF``."""
        tf = self.tf
        tipos.validar_esquema(tf, tipos.ESQUEMA_TF, nombre="tf")
        self.assertEqual(len(tf), (16 + 8 + 4) * 2)
        for uso in ("ambiental", "agudo", "cronico"):
            sub = tf[tf["uso"] == uso]
            self.assertEqual(sorted(set(sub["candidato"])), sorted(tendencias.CANDIDATOS_USO[uso]), uso)
            self.assertEqual(sorted(set(sub["variable"])), sorted(tendencias.VARIABLES_USO[uso]), uso)
        self.assertNotIn("C", set(tf.loc[tf["uso"] == "cronico", "candidato"]))
        self.assertNotIn("C_est", set(tf.loc[tf["uso"] != "cronico", "candidato"]))
        cols = ["media_pond", "p95_pond", "resultado", "regla_red", "n_red"]
        for cand in ("A", "B", "AB"):
            for prueba in ("TF1", "TF2"):
                ag = tf[(tf["uso"] == "agudo") & (tf["candidato"] == cand) & (tf["variable"] == "T") &
                        (tf["prueba"] == prueba)][cols].reset_index(drop=True)
                cr = tf[(tf["uso"] == "cronico") & (tf["candidato"] == cand) & (tf["variable"] == "T") &
                        (tf["prueba"] == prueba)][cols].reset_index(drop=True)
                pd.testing.assert_frame_equal(ag, cr)
        cero = tf[tf["candidato"].isin(["A", "C", "C_est"])]
        self.assertTrue(bool((cero[["media_pond", "p95_pond"]] <= constantes.valor("TF_CERO_TOL")).all().all()))
        self.assertTrue(bool((tf["regla_red"] == "r2003_2025").all()) and bool((tf["n_red"] == 10).all()))
        for v, nombre in tendencias.COTAS_TF.items():
            t1m, t1p, t2m, t2p = constantes.valor(nombre)
            for prueba, (cm, cp) in (("TF1", (t1m, t1p)), ("TF2", (t2m, t2p))):
                sub = tf[(tf["variable"] == v) & (tf["prueba"] == prueba)]
                self.assertTrue(bool((sub["cota_media"] == cm).all() and (sub["cota_p95"] == cp).all()), (v, prueba))
        # Lo ambiental y lo agudo usan otra z de celda: no tienen por qué coincidir (B en T).
        b_amb = tf[(tf["uso"] == "ambiental") & (tf["candidato"] == "B") & (tf["variable"] == "T")]["media_pond"]
        self.assertTrue(np.isfinite(b_amb.to_numpy()).all())

    def test_filas_reales_pasan_por_la_decision(self):
        """Las filas reales entran a ``decision.compuertas`` y ``decidir_combinacion`` en cada (uso, grupo), y la
        compuerta TF dice lo mismo que ``resultado`` (DEC-5)."""
        U = self.U
        hechos = set()
        for caso in sintetico.CASOS_METRICAS:
            if caso == "soporte":
                continue
            d = sintetico.tablas_metricas(caso)
            clave = (d["uso"], d["grupo"])
            if clave in hechos or d["e0_excluidos"]:
                continue
            hechos.add(clave)
            tf = self.tf[self.tf["uso"] == d["uso"]].reset_index(drop=True)
            entradas = tipos.EntradasDecision(tipos.Uso(d["uso"]), tipos.Grupo(d["grupo"]), d["validacion"], tf,
                                              d["replicas"], {})
            with self.subTest(uso=d["uso"], grupo=d["grupo"]):
                tabla = decision.compuertas(d["uso"], d["grupo"], entradas, U)
                de_tf = tabla[tabla["compuerta"] == "TF"]
                variables = decision.VARIABLES[(tipos.Uso(d["uso"]), tipos.Grupo(d["grupo"]))].TF
                for f in de_tf.itertuples():
                    fila = tf[(tf["candidato"] == f.candidato) & (tf["variable"] == f.variable) &
                              (tf["prueba"] == f.ambito)]
                    self.assertEqual(len(fila), 1)
                    self.assertEqual(bool(f.pasa), fila["resultado"].iloc[0] == "pasa")
                self.assertEqual(set(de_tf["variable"]), set(variables))
                r = decision.decidir_combinacion(d["uso"], d["grupo"], entradas, umbrales=U)
                self.assertTrue(all(v.value == "r2003_2025" for v in r.red_tf2.values()))
        self.assertEqual(hechos, set(decision.VARIABLES))

    def test_tf2_no_evaluable_en_todas_las_filas(self):
        """EMC1-2 (D4): con < 10 estaciones en las tres reglas, TF2 «no_evaluable» para todos los candidatos, red
        «ninguna» y n_red < 10; TF1 se calcula igual; ``decision`` deja fuera a B y AB con «TF2 no evaluable»."""
        U = self.U
        # La primera estación sin horas desde 2010: sigue en la red histórica y sale de la constante (9 < 10).
        hv = {y: t.assign(horas=np.where((t["codigo"] == self.m.codigos[0]) & (y >= 2010), 0, t["horas"]))
              for y, t in self.m.horas_validas.items()}
        esc = {v: tendencias.escenarios_tf(hv, v, U) for v in tendencias.VARIABLES_TF}
        self.assertTrue(all(e.regla == "ninguna" and e.n_red < 10 for e in esc.values()))
        self.assertTrue(all(e.historica == self.m.escenarios[v].historica for v, e in esc.items()))
        p, celdas = self.pasadas["salud"]
        p2 = tendencias.PasadaTF(self.m.datos, celdas, esc, self.m.cfg_salud, U, variables=("T", "Td"))
        self.assertEqual(p2.anios(), tuple(range(2015, 2025)))         # sin TF2, sólo los años de TF1
        res = tendencias.resultados_tf(p2.correr(self.horas, self.m.fondo(celdas)), U)
        tf = tendencias.filas_tf(tendencias.tf_por_uso(salud=res), esc)
        tf2 = tf[tf["prueba"] == "TF2"]
        self.assertTrue(bool((tf2["resultado"] == "no_evaluable").all()))
        self.assertTrue(bool((tf2["regla_red"] == "ninguna").all()) and bool((tf2["n_red"] < 10).all()))
        self.assertTrue(tf2["media_pond"].isna().all() and tf2["p95_pond"].isna().all())
        self.assertFalse(bool((tf[tf["prueba"] == "TF1"]["resultado"] == "no_evaluable").any()))
        # TF1 no cambia con la red de TF2.
        for k in (("A", "prod", "T"), ("B", "prod", "Td")):
            self.assertEqual(res[k]["TF1"], self.res["salud"][k]["TF1"])
        d = sintetico.tablas_metricas("agudo_nivel")
        entradas = tipos.EntradasDecision(tipos.Uso.AGUDO, tipos.Grupo.T_TD, d["validacion"],
                                          tf[tf["uso"] == "agudo"].reset_index(drop=True), d["replicas"], {})
        r = decision.decidir_combinacion("agudo", "T_Td", entradas, umbrales=U)
        for c in ("B", "AB"):
            self.assertIn("TF2 no evaluable", r.motivos.get(c, ()))
        self.assertIn("TF2 no evaluable", r.notas)

    def test_paridad_con_candidatos(self):
        """TEN-13 y TEN-14: A, B y AB son, bit a bit, ``correccion_a``, ``correccion_b`` y ``correccion_ab`` de
        ``candidatos`` con la lista de vecinos de todas las estaciones; C y C_est, ``predecir_c`` (≤ 10⁻⁹ K)."""
        U = self.U
        p, celdas = self.pasadas["salud"]
        fondo = self.m.fondo(celdas)
        entrenamiento = {c: self.m.infos[c] for c in self.m.codigos}
        clima_T = self.m.datos.climatologias[self.m.datos.climatologias["variable"] == "T"]
        for mes in ("2016-03", "2019-12", "2024-02"):
            h = np.arange(_h(f"{mes}-01T00"), _h(str(np.datetime64(mes, "M") + 1) + "-01T00"), dtype=np.int64)
            with self.subTest(mes=mes):
                hA = self.m.cfg_salud["A"]["prod"]["T"]
                vec = candidatos.vecinos(celdas.puntos(), entrenamiento, hA, U)
                np.testing.assert_array_equal(p.correccion_mes(h, fondo, "A", "prod", "T"),
                                              candidatos.correccion_a(vec, clima_T, h))
                Q = candidatos.matriz_q(self.m.datos, self.m.codigos, "B", "T", h, U)
                np.testing.assert_array_equal(p.correccion_mes(h, fondo, "B", "prod", "T"),
                                              candidatos.correccion_b(vec, Q, np.isfinite(Q)))
                ha, hq = self.m.cfg_salud["AB"]["prod"]["T"]
                Qa = candidatos.matriz_q(self.m.datos, self.m.codigos, "AB", "T", h, U)
                vec_a = candidatos.vecinos(celdas.puntos(), entrenamiento, ha, U)
                vec_q = candidatos.vecinos(celdas.puntos(), entrenamiento, hq, U)
                np.testing.assert_array_equal(p.correccion_mes(h, fondo, "AB", "prod", "T"),
                                              candidatos.correccion_ab(vec_a, vec_q, clima_T, Qa, np.isfinite(Qa), h))
                F = fondo(h, np.arange(celdas.n))
                amp = fondo_era5l.amplitud_dia_utc(F["T_F"], h)
                for cand, clave in (("C", "C"), ("C_est", "C_est")):
                    R = p.correccion_mes(h, fondo, cand, "prod", "T")
                    modelo = candidatos.ajustar_c(self.m.datos.filas_c[clave]["T"], self.m.codigos, 10.0)
                    for i in range(celdas.n):
                        if cand == "C":
                            estado = {"T": F["T_F"][:, i], "T_menos_Td": F["T_F"][:, i] - F["Td_F"][:, i],
                                      "rapidez": np.hypot(F["u_F"][:, i], F["v_F"][:, i]), "amp": amp[:, i]}
                        else:
                            estado = {v: celdas.clima_estado[v][i] for v in candidatos.ESTADO_C}
                        esperado = candidatos.predecir_c(modelo, celdas.estaticos.iloc[[i]], h, estado)
                        self.assertTrue(np.isfinite(esperado).all())
                        np.testing.assert_allclose(R[:, i], esperado, rtol=0, atol=1e-9)
                    self.assertGreater(float(np.abs(R).max()), 0.0)
        # La red del escenario sí cambia B (sólo las disponibles) y no cambia A (TEN-4).
        h = np.arange(_h("2016-03-01T00"), _h("2016-04-01T00"), dtype=np.int64)
        red = frozenset(self.m.codigos[:5])
        hB = self.m.cfg_salud["B"]["prod"]["T"]
        vec = candidatos.vecinos(celdas.puntos(), entrenamiento, hB, U)
        Q = candidatos.matriz_q(self.m.datos, self.m.codigos, "B", "T", h, U)
        disp = np.isfinite(Q) & np.isin(np.array(self.m.codigos), list(red))[None, :]
        np.testing.assert_array_equal(p.correccion_mes(h, fondo, "B", "prod", "T", red=red),
                                      candidatos.correccion_b(vec, Q, disp))
        np.testing.assert_array_equal(p.correccion_mes(h, fondo, "A", "prod", "T", red=red),
                                      p.correccion_mes(h, fondo, "A", "prod", "T"))

    def test_dia_sin_datos_y_estacion_excluida(self):
        """H6: una estación con un día sin datos en un mes sigue disponible el resto del mes (la red efectiva cuenta las
        estaciones con algún q en el mes; paridad con ``correccion_b``); una estación excluida no entra al entrenamiento
        de B ni de C."""
        U = self.U
        _, celdas = self.pasadas["salud"]
        fondo = self.m.fondo(celdas)
        cfg = {"B": self.m.cfg_salud["B"], "C": self.m.cfg_salud["C"]}
        hB = self.m.cfg_salud["B"]["prod"]["T"]
        h = np.arange(_h("2016-03-01T00"), _h("2016-04-01T00"), dtype=np.int64)
        # Un día sin datos (2016-03-10, UTC) en la estación 4: ni sus reportes ni sus horas interpolables.
        c4 = self.m.codigos[3]
        d0 = _h("2016-03-10T00")
        df = self.m.datos.residuos[c4]
        hueco = df[~((df["h"] >= d0 - 1) & (df["h"] < d0 + 25))].reset_index(drop=True)
        datos = dataclasses.replace(self.m.datos, residuos={**self.m.datos.residuos, c4: hueco})
        p = tendencias.PasadaTF(datos, celdas, self.m.escenarios, cfg, U, variables=("T",), pruebas=("TF1",))
        Q = candidatos.matriz_q(datos, self.m.codigos, "B", "T", h, U)
        j = self.m.codigos.index(c4)
        en_dia = (h >= d0) & (h < d0 + 24)
        self.assertTrue(np.isnan(Q[en_dia, j]).all() and np.isfinite(Q[~en_dia, j]).any())
        vec = candidatos.vecinos(celdas.puntos(), {c: self.m.infos[c] for c in self.m.codigos}, hB, U)
        np.testing.assert_array_equal(p.correccion_mes(h, fondo, "B", "prod", "T"),
                                      candidatos.correccion_b(vec, Q, np.isfinite(Q)))
        # Una estación excluida (K3) no entra: ni a los vecinos de B ni a las sumas de C.
        c6 = self.m.codigos[5]
        infos = {**self.m.infos, c6: dataclasses.replace(self.m.infos[c6], excluida=True, motivo="k3")}
        datos_x = dataclasses.replace(self.m.datos, estaciones=infos)
        px = tendencias.PasadaTF(datos_x, celdas, self.m.escenarios, cfg, U, variables=("T",), pruebas=("TF1",))
        resto = [c for c in self.m.codigos if c != c6]
        self.assertEqual(px.codigos, tuple(resto))
        vec_x = candidatos.vecinos(celdas.puntos(), {c: infos[c] for c in resto}, hB, U)
        Qx = candidatos.matriz_q(datos_x, resto, "B", "T", h, U)
        Rx = px.correccion_mes(h, fondo, "B", "prod", "T")
        np.testing.assert_array_equal(Rx, candidatos.correccion_b(vec_x, Qx, np.isfinite(Qx)))
        self.assertFalse(np.array_equal(Rx, self.pasadas["salud"][0].correccion_mes(h, fondo, "B", "prod", "T")))
        modelo = candidatos.ajustar_c(self.m.datos.filas_c["C"]["T"], resto, 10.0)
        F = fondo(h, np.arange(celdas.n))
        amp = fondo_era5l.amplitud_dia_utc(F["T_F"], h)
        Rc = px.correccion_mes(h, fondo, "C", "prod", "T")
        estado = {"T": F["T_F"][:, 0], "T_menos_Td": F["T_F"][:, 0] - F["Td_F"][:, 0],
                  "rapidez": np.hypot(F["u_F"][:, 0], F["v_F"][:, 0]), "amp": amp[:, 0]}
        np.testing.assert_allclose(Rc[:, 0], candidatos.predecir_c(modelo, celdas.estaticos.iloc[[0]], h, estado),
                                   rtol=0, atol=1e-9)

    def test_reproducible_por_meses_y_lotes(self):
        """MC-37 y TEN-22: la misma pasada da lo mismo bit a bit; los meses calculados en otro orden y sumados en el
        suyo dan lo mismo; con lotes de 3 celdas, las medias coinciden (≤ 10⁻¹²)."""
        U = self.U
        p, celdas = self.pasadas["salud"]
        fondo = self.m.fondo(celdas)
        horas = np.arange(_h("2015-01-01T00"), _h("2025-01-01T00"), dtype=np.int64)
        cfg = {"B": self.m.cfg_salud["B"], "C": self.m.cfg_salud["C"]}
        p1 = tendencias.PasadaTF(self.m.datos, celdas, self.m.escenarios, cfg, U, variables=("T", "Td"),
                                 pruebas=("TF1",))
        meses = p1.meses(horas)
        sumas = [p1.sumas_mes(hm, fondo) for hm in meses]
        al_reves = [p1.sumas_mes(hm, fondo) for hm in reversed(meses)][::-1]
        a, b = p1.acumular(sumas), p1.acumular(al_reves)
        c = p1.correr(horas, fondo)
        for k in a.medias:
            np.testing.assert_array_equal(a.medias[k].media, b.medias[k].media)
            np.testing.assert_array_equal(a.medias[k].media, c.medias[k].media)
        p3 = tendencias.PasadaTF(self.m.datos, celdas, self.m.escenarios, cfg, U, variables=("T", "Td"),
                                 pruebas=("TF1",), lote_puntos=3)
        self.assertEqual(len(p3.lotes), 4)
        d = p3.correr(horas, fondo)
        self.assertEqual(set(d.medias), set(a.medias))
        for k in a.medias:
            np.testing.assert_allclose(d.medias[k].media, a.medias[k].media, rtol=1e-12, atol=0)

    def test_celdas_sin_comuna_o_sin_poblacion_no_entran(self):
        """TEN-6: las celdas con cod_comuna ≤ 0 o w_ghs ≤ 0 no entran; el peso de una comuna es su Σ w_ghs (MC-48)."""
        celdas = self.m.celdas("salud")
        self.assertEqual(celdas.n, 10)
        p, _ = self.pasadas["salud"]
        t = self.m.tabla_celdas
        t = t[(t["w_ghs"] > 0) & (t["cod_comuna"] > 0)]
        esperado = t.groupby("cod_comuna")["w_ghs"].sum()
        np.testing.assert_array_equal(p.comunas, esperado.index.to_numpy())
        np.testing.assert_allclose(p.pesos_comuna, esperado.to_numpy(), rtol=1e-15)
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.CeldasTF(ids=np.array([1, 2]), lat=np.zeros(2), lon=np.zeros(2), z=np.zeros(2),
                                cod_comuna=np.array([13101, 0]), w_ghs=np.ones(2))


# ---------------------------------------------------------------------------
# Unidades de la prueba (§5.7)
# ---------------------------------------------------------------------------
def _horas_anio(codigos_horas: dict, anios) -> dict:
    """{año: {código: horas}} con las mismas horas cada año (``codigos_horas``: código → función año → horas)."""
    return {y: {c: int(f(y)) for c, f in codigos_horas.items()} for y in anios}


def _medias(media: np.ndarray, anios, comunas=(1, 2, 3)) -> tendencias.MediasComunaAnio:
    return tendencias.MediasComunaAnio(comunas=np.array(comunas), anios=np.array(list(anios)),
                                       media=np.asarray(media, dtype=np.float64))


class PruebasTF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()

    def test_red_historica_2000_horas_en_2000_2009(self):
        """TEN-2: ≥ 2.000 horas válidas sumadas en 2000-2009 (el borde entra); las horas de 2010 no cuentan."""
        anios = range(2000, 2026)
        hv = _horas_anio({"000001": lambda y: 200 if y <= 2009 else 0, "000002": lambda y: 199 if y <= 2009 else 8000,
                          "000003": lambda y: 2000 if y == 2009 else 0}, anios)
        self.assertEqual(tendencias.red_historica(hv, "T", self.U), frozenset({"000001", "000003"}))
        hv_df = {y: pd.DataFrame({"codigo": list(d), "horas": list(d.values())}) for y, d in hv.items()}
        self.assertEqual(tendencias.red_historica(hv_df, "T", self.U), frozenset({"000001", "000003"}))
        del hv[2005]
        with self.assertRaises(tendencias.ErrorTendencias):               # TEN-1: un año que falta no es 0
            tendencias.red_historica(hv, "T", self.U)

    def test_red_constante_tres_reglas_y_ninguna(self):
        """§5.7 y EMC1-2: r2000_2025 (≥ 50 % de las horas UTC del año, MC-47, en ≥ 22 de 26), r2003_2025 (≥ 80 % de
        23 años: 19), r2010_2025 (≥ 80 % de 16: 13) o «ninguna» con < 10, en ese orden."""
        U = self.U
        anios = range(2000, 2026)
        medio = tendencias.horas_del_anio

        def red(n_estaciones, primer_anio, horas=lambda y: medio(y) // 2):
            return {f"{100000 + k:06d}": (lambda y, a=primer_anio: horas(y) if y >= a else 0)
                    for k in range(n_estaciones)}
        # 10 estaciones con 22 años (2004-2025) a exactamente el 50 % (también en los bisiestos): r2000_2025.
        hv = _horas_anio(red(10, 2004), anios)
        self.assertEqual(tendencias.red_constante(hv, "T", U), (frozenset(hv[2025]), "r2000_2025"))
        # Una hora menos que el 50 % en un año bisiesto deja ese año fuera: 21 años → r2003_2025 (21 de 23).
        hv = _horas_anio(red(10, 2004, lambda y: medio(y) // 2 - (1 if y == 2008 else 0)), anios)
        self.assertEqual(tendencias.red_constante(hv, "T", U)[1], "r2003_2025")
        # r2003_2025: 19 de 23 años entran (desde 2007); 18 no (desde 2008), y entonces rige r2010_2025 (16 de 16).
        hv = _horas_anio(red(10, 2007), anios)
        self.assertEqual(tendencias.red_constante(hv, "T", U)[1], "r2003_2025")
        hv = _horas_anio(red(10, 2008), anios)
        self.assertEqual(tendencias.red_constante(hv, "T", U)[1], "r2010_2025")
        # r2010_2025: 13 de 16 entran (desde 2013); 12 no (desde 2014) → «ninguna», con la red de r2010_2025 (vacía).
        hv = _horas_anio(red(10, 2013), anios)
        self.assertEqual(tendencias.red_constante(hv, "T", U)[1], "r2010_2025")
        hv = _horas_anio(red(10, 2014), anios)
        self.assertEqual(tendencias.red_constante(hv, "T", U), (frozenset(), "ninguna"))
        # Con 9 estaciones en todas las reglas: «ninguna» y la red de r2010_2025 (9 < 10), cuyo tamaño es n_red.
        hv = _horas_anio(red(9, 2000), anios)
        r, regla = tendencias.red_constante(hv, "T", U)
        self.assertEqual((regla, len(r)), ("ninguna", 9))
        e = tendencias.escenarios_tf(hv, "T", U)
        self.assertFalse(e.evaluable)
        self.assertEqual(e.anios("constante"), ())
        self.assertEqual(e.anios("completo"), tuple(range(2015, 2025)))
        # 3 h de 24 (sinópticas): nunca ≥ 50 % (MC-47).
        hv = _horas_anio(red(12, 2000, lambda y: medio(y) // 8), anios)
        self.assertEqual(tendencias.red_constante(hv, "T", U)[1], "ninguna")
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.red_constante(_horas_anio(red(1, 2000, lambda y: medio(y) + 1), anios), "T", U)

    def test_escenarios_anios_y_redes(self):
        """TEN-4: «cambio» = histórica en 2015-2019 y todas en 2020-2024; «completo» = todas; «constante» en los años
        de su regla; sin TF1, no hay «cambio»."""
        e = tendencias.EscenariosTF("T", historica=frozenset({"000001"}), constante=frozenset({"000002"}),
                                    regla="r2010_2025")
        self.assertEqual(e.anios("cambio"), tuple(range(2015, 2025)))
        self.assertEqual(e.anios("constante"), tuple(range(2010, 2026)))
        self.assertEqual(e.anios("completo"), tuple(range(2010, 2026)))
        self.assertEqual(e.anios("cambio", ("TF2",)), ())
        self.assertEqual(e.anios("completo", ("TF1",)), tuple(range(2015, 2025)))
        self.assertEqual(e.red("cambio", 2017), frozenset({"000001"}))
        self.assertIsNone(e.red("cambio", 2020))
        self.assertIsNone(e.red("completo", 2001))
        self.assertEqual(e.red("constante", 2012), frozenset({"000002"}))
        self.assertEqual(tendencias.anios_regla("r2000_2025"), (2000, 2025))
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.anios_regla("ninguna")

    def test_media_y_p95_ponderados_mc48(self):
        """MC-48: el P95 es el menor valor cuyo peso acumulado alcanza 0,95, sin interpolar; la media, ponderada."""
        x = np.array([0.30, 0.10, 0.20, 0.40])
        w = np.array([4.0, 90.0, 1.0, 5.0])                    # ordenados: 0,1 (90), 0,2 (91), 0,3 (95) y 0,4 (100)
        media, p95 = tendencias.media_p95_ponderados(x, w)
        self.assertAlmostEqual(media, float(np.dot(x, w) / w.sum()), places=15)
        self.assertEqual(p95, 0.30)                            # el peso acumulado alcanza 95 justo en 0,3
        self.assertEqual(tendencias.media_p95_ponderados(x, np.array([4.0, 90.0, 1.0, 5.000001]))[1], 0.40)
        self.assertEqual(tendencias.media_p95_ponderados(np.array([2.0]), np.array([3.0])), (2.0, 2.0))
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.media_p95_ponderados(np.array([NAN]), np.array([1.0]))

    def test_medias_comunales_por_lotes(self):
        """TEN-6: la media comunal de un año es Σ w·x / Σ w sobre las celda-horas finitas; un lote es de un solo año."""
        rng = np.random.default_rng(0)
        h = np.arange(_h("2017-03-01T00"), _h("2017-04-01T00"), dtype=np.int64)
        x = rng.normal(size=(h.size, 6))
        x[3, 1] = NAN
        w = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        com = np.array([13102, 13101, 13102, 13105, 13101, 13105])
        s = tendencias.medias_comuna_anio(x, h, w, com)
        orden = np.array([13101, 13102, 13105])
        for k, c in enumerate(orden):
            m = com == c
            ok = np.isfinite(x[:, m])
            esperado = np.sum(np.where(ok, x[:, m], 0.0) * w[m]) / np.sum(ok * w[m])
            self.assertAlmostEqual(s[0, k] / s[1, k], esperado, places=12)
        s2 = tendencias.medias_comuna_anio(x, h, w, com, orden=np.array([13100, 13101, 13102, 13105]))
        np.testing.assert_array_equal(s2[:, 1:], s)
        self.assertEqual(tuple(s2[:, 0]), (0.0, 0.0))
        h2 = np.arange(_h("2017-12-31T20"), _h("2018-01-01T04"), dtype=np.int64)
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.medias_comuna_anio(np.zeros((h2.size, 6)), h2, w, com)
        acc = tendencias.AcumuladorComunas(orden)
        acc.sumar("k", 2017, s)
        acc.sumar("k", 2017, s)
        np.testing.assert_allclose(acc.medias("k").media[:, 0], s[0] / s[1], rtol=1e-15)

    def test_tf1_y_tf2_con_medias_conocidas(self):
        """TEN-7 a TEN-9: Δ_c de TF1 y Δτ_c de TF2 (por década) con medias anuales conocidas, sus cotas y su resultado."""
        U = self.U
        anios = np.arange(2010, 2026)
        base = np.tile(10.0 + 0.0 * anios, (3, 1))
        completo = _medias(base, anios)
        cambio_m = base.copy()
        cambio_m[0, (anios >= 2015) & (anios <= 2019)] -= 0.2          # comuna 1: Δ = +0,2
        cambio_m[2, (anios >= 2015) & (anios <= 2019)] += 0.04         # comuna 3: Δ = −0,04
        cambio = _medias(cambio_m, anios)
        np.testing.assert_allclose(tendencias.delta_tf1(cambio, completo), [0.2, 0.0, -0.04], atol=1e-12)
        pesos = {1: 1.0, 2: 10.0, 3: 89.0}
        r = tendencias.tf1(cambio, completo, pesos, U, "T")
        self.assertAlmostEqual(r["media_pond"], (0.2 * 1 + 0.04 * 89) / 100, places=12)
        self.assertAlmostEqual(r["p95_pond"], 0.04, places=12)       # acumulado: 0 (10), 0,04 (99), 0,2 (100)
        t1m, t1p, t2m, t2p = constantes.valor("TF_COTAS_T")
        self.assertEqual((r["cota_media"], r["cota_p95"], r["resultado"]), (t1m, t1p, "pasa"))
        self.assertEqual(tendencias.tf1(cambio, completo, {1: 50.0, 2: 1.0, 3: 49.0}, U, "T")["resultado"], "falla")
        # TF2: una tendencia de 0,03 K por año (0,3 por década) en la comuna 2 de la red constante.
        const = base.copy()
        const[1] += 0.03 * (anios - 2010)
        r2 = tendencias.tf2(_medias(const, anios), completo, pesos, U, "T", "r2010_2025")
        np.testing.assert_allclose(tendencias.delta_tf2(_medias(const, anios), completo, anios), [0, 0.3, 0],
                                   atol=1e-12)
        self.assertAlmostEqual(r2["media_pond"], 0.3 * 10 / 100, places=12)
        self.assertAlmostEqual(r2["p95_pond"], 0.3, places=12)       # acumulado: 0 (1), 0 (90), 0,3 (100)
        self.assertEqual((r2["cota_media"], r2["cota_p95"], r2["regla"], r2["resultado"]), (t2m, t2p, "r2010_2025",
                                                                                          "falla"))
        r2b = tendencias.tf2(_medias(const, anios), completo, {1: 1.0, 2: 4.0, 3: 95.0}, U, "T", "r2010_2025")
        self.assertEqual((r2b["p95_pond"], r2b["resultado"]), (0.0, "pasa"))
        # Sólo los años de la regla: con r2000_2025 sin medias antes de 2010, la pendiente usa 2010-2025 (TEN-8).
        self.assertAlmostEqual(tendencias.tf2(_medias(const, anios), completo, pesos, U, "T",
                                              "r2000_2025")["media_pond"], r2["media_pond"], places=12)
        ne = tendencias.tf2(None, None, pesos, U, "Td", "ninguna")
        self.assertEqual(ne["resultado"], "no_evaluable")
        self.assertTrue(math.isnan(ne["media_pond"]))
        self.assertEqual((ne["cota_media"], ne["cota_p95"]), constantes.valor("TF_COTAS_TD")[2:])
        # Una comuna sin años en un período queda fuera y se cuenta (TEN-7).
        hueco = cambio_m.copy()
        hueco[1, (anios >= 2020) & (anios <= 2024)] = NAN
        r3 = tendencias.tf1(_medias(hueco, anios), completo, pesos, U, "T")
        self.assertEqual((r3["n_comunas"], r3["n_comunas_sin_dato"]), (2, 1))

    def test_borde_de_pasa_en_la_media_y_el_p95(self):
        """H2 (TEN-9): |Δ| igual a la cota pasa y el float64 siguiente (``np.nextafter``) falla, en la media y en el P95
        (DEC-5: «media ≤ cota y P95 ≤ cota»)."""
        U = self.U
        t1m, t1p, _, _ = constantes.valor("TF_COTAS_T")
        anios = (2015, 2020)                    # un año por período: la media de los dos es exacta

        def tf1_con(deltas, pesos):
            n = len(deltas)
            cambio = _medias(np.column_stack([np.zeros(n), np.asarray(deltas, dtype=float)]), anios, range(1, n + 1))
            completo = _medias(np.zeros((n, 2)), anios, range(1, n + 1))
            return tendencias.tf1(cambio, completo, dict(zip(range(1, n + 1), pesos)), U, "T")
        r = tf1_con([t1m], [1.0])                                   # media = P95 = cota de la media (≤ cota del P95)
        self.assertEqual((r["media_pond"], r["resultado"]), (t1m, "pasa"))
        r = tf1_con([np.nextafter(t1m, np.inf)], [1.0])
        self.assertGreater(r["media_pond"], t1m)
        self.assertEqual(r["resultado"], "falla")
        r = tf1_con([t1p, 0.0], [1.0, 9.0])                         # P95 = cota del P95 y media = cota/10
        self.assertEqual((r["p95_pond"], r["resultado"]), (t1p, "pasa"))
        self.assertLess(r["media_pond"], t1m)
        r = tf1_con([np.nextafter(t1p, np.inf), 0.0], [1.0, 9.0])
        self.assertGreater(r["p95_pond"], t1p)
        self.assertLess(r["media_pond"], t1m)
        self.assertEqual(r["resultado"], "falla")

    def test_cero_por_construccion_es_error_de_codigo(self):
        """TEN-10 (§5.7): en A, C y C_est un valor > 10⁻⁶ es un error de código y lanza; el borde no; B y AB no."""
        tol = constantes.valor("TF_CERO_TOL")
        borde = {"prueba": "TF1", "variable": "T", "media_pond": tol, "p95_pond": tol, "max_abs": tol,
                 "resultado": "pasa"}
        for c in ("A", "C", "C_est"):
            tendencias.comprobar_cero(c, borde)
            for clave in ("media_pond", "p95_pond", "max_abs"):
                with self.assertRaises(tendencias.ErrorTendencias):
                    tendencias.comprobar_cero(c, {**borde, clave: np.nextafter(tol, 1.0)})
            with self.assertRaises(tendencias.ErrorTendencias):                    # sin el máximo no se da por bueno
                tendencias.comprobar_cero(c, {k: v for k, v in borde.items() if k != "max_abs"})
        tendencias.comprobar_cero("B", {**borde, "media_pond": 1.0, "p95_pond": 2.0, "resultado": "falla"})
        tendencias.comprobar_cero("A", {**borde, "media_pond": NAN, "p95_pond": NAN, "resultado": "no_evaluable"})
        # En una pasada: si A cambiara entre escenarios, resultados_tf lo detecta.
        anios = np.arange(2015, 2025)
        base = np.full((3, anios.size), 5.0)
        malo = base.copy()
        malo[0, :5] += 1e-3
        medias = tendencias.MediasTF(comunas=np.array([1, 2, 3]), pesos_comuna=np.ones(3), tareas=(("A", "x", "T"),),
                                     escenarios={"T": tendencias.EscenariosTF("T", frozenset(), frozenset(),
                                                                              "ninguna")},
                                     pruebas=("TF1", "TF2"),
                                     medias={("A", "x", "T", "cambio"): _medias(malo, anios),
                                             ("A", "x", "T", "completo"): _medias(base, anios)})
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.resultados_tf(medias, self.U)
        self.assertEqual(tendencias.resultados_tf(medias, self.U, comprobar=False)[("A", "x", "T")]["TF1"]["resultado"],
                         "pasa")
        # TEN-10: un solo valor > 10⁻⁶ en una comuna chica, con la media y el P95 bajo 10⁻⁶, también es error.
        chico = base.copy()
        chico[0, :5] -= 2e-6
        medias = dataclasses.replace(medias, pesos_comuna=np.array([1e-3, 1.0, 1.0]),
                                     medias={("A", "x", "T", "cambio"): _medias(chico, anios),
                                             ("A", "x", "T", "completo"): _medias(base, anios)})
        r = tendencias.resultados_tf(medias, self.U, comprobar=False)[("A", "x", "T")]["TF1"]
        self.assertLessEqual(max(r["media_pond"], r["p95_pond"]), tol)
        self.assertGreater(r["max_abs"], tol)
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.resultados_tf(medias, self.U)

    def test_producto_igual_a_fondo_era5l(self):
        """TEN-5 (A20): el producto de T, Td y p es, bit a bit, el de ``fondo_era5l.producto_desde``; la rapidez es
        √(u² + v²) de su u y su v."""
        rng = np.random.default_rng(1)
        F = {c: rng.normal(size=(5, 4)) for c in fondo_era5l.CAMPOS_F}
        F["p_F"] = 800 + 10 * F["p_F"]
        R = {v: rng.normal(size=(5, 4)) * (1e-3 if v == "p" else 1) for v in tendencias.VARIABLES_PRODUCTO}
        P = fondo_era5l.producto_desde(F, {f"R_{v}": R[v] for v in R})
        for v in ("T", "Td", "p"):
            np.testing.assert_array_equal(tendencias.producto_tf(v, F, R), P[v])
        np.testing.assert_array_equal(tendencias.producto_tf("rapidez", F, R), np.hypot(P["u"], P["v"]))

    def test_constantes_de_uso_iguales_a_decision(self):
        """MC-04 y DEC-1: los candidatos y las variables de TF de cada uso son los de ``decision``."""
        for uso, cands in tendencias.CANDIDATOS_USO.items():
            self.assertEqual(cands, tuple(decision.CANDIDATOS_USO[tipos.Uso(uso)]), uso)
            tf = sorted({v for (u, _), vs in decision.VARIABLES.items() if u.value == uso for v in vs.TF})
            self.assertEqual(sorted(tendencias.VARIABLES_USO[uso]), tf, uso)
        self.assertEqual(tendencias.CERO_POR_CONSTRUCCION, tuple(decision.CERO_POR_CONSTRUCCION))
        self.assertEqual(tendencias.CON_DERIVA, tuple(decision.CON_DERIVA))


# ---------------------------------------------------------------------------
# S16: TF de contaminantes (Anexo B)
# ---------------------------------------------------------------------------
def _celdas_contaminantes() -> pd.DataFrame:
    """Comuna 13101 con 120 celdas (60 de w = 9 y 60 de w = 1), 13102 con 30, 13103 con 50, 13104 con 70; más 5 sin
    comuna y 3 sin población (no entran)."""
    filas = []
    k = 0
    for com, ws in ((13101, [9.0] * 60 + [1.0] * 60), (13102, [3.0] * 30), (13103, [2.0] * 50),
                    (13104, list(np.linspace(1, 20, 70))), (0, [5.0] * 5), (13102, [0.0] * 3)):
        for w in ws:
            filas.append((9_000_000_000 + k, com, w))
            k += 1
    return pd.DataFrame(filas, columns=["celda", "cod_comuna", "w_ghs"])


def _meteo(artefacto: float = 0.0, *, solo_comuna=None, ganador: str = "A"):
    """Columnas ``mc_*`` sintéticas con el ganador A (corrección fija por celda) o C (que además cambia con el estado del
    día); ninguna de las dos depende del escenario. Con ``artefacto``, «cambio» en 2015-2019 pierde ese tanto de
    corrección en mc_t2m (como B con la red histórica)."""
    def meteo(escenario, celdas, dias):
        d = np.asarray(dias, dtype=float)[:, None]
        c = (np.asarray(celdas) % 1000).astype(float)[None, :]
        ciclo = 6.0 * np.cos(2 * np.pi * (d - 15.0) / 365.25)
        correccion = 0.7 + 0.01 * c if ganador == "A" else 0.3 + 0.05 * ciclo + 0.002 * c
        t2m = 288.0 + ciclo + 0.01 * c + correccion
        if artefacto and escenario == "cambio":
            anio = tendencias._anio_de_dia(np.asarray(dias, dtype=np.int64))[:, None]
            afecta = np.ones_like(c, bool) if solo_comuna is None else np.isin(np.asarray(celdas)[None, :], solo_comuna)
            t2m = t2m - artefacto * ((anio >= 2015) & (anio <= 2019)) * afecta
        return {"mc_t2m": t2m, "mc_rh": 60.0 + 10.0 * np.sin(2 * np.pi * d / 365.25) + 0 * c,
                "mc_wind": 2.0 + 0.001 * c + 0 * d}
    return meteo


def _fabrica(meteo):
    """Fábrica falsa: una función conocida de las columnas mc_* (como la de v2, con el modelo como coeficientes)."""
    def fabrica(modelo, variante, escenario, celdas, dias):
        m = meteo(escenario, celdas, dias)
        return (modelo["b0"] + modelo["b_t"] * (m["mc_t2m"] - 273.15) + modelo["b_rh"] * m["mc_rh"]
                + modelo["b_w"] * m["mc_wind"])
    return fabrica


MODELO_FALSO = {"b0": 20.0, "b_t": 0.5, "b_rh": 0.05, "b_w": -1.0}


class PruebasS16Tendencias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.tabla = _celdas_contaminantes()
        cls.muestra = tendencias.muestra_tf_contaminantes(cls.tabla, cls.tabla["w_ghs"].to_numpy(), cls.U)

    def test_s16_muestra_tf_contaminantes(self):
        """Anexo B y TEN-19: hasta 50 celdas por comuna (todas si son ≤ 50), con probabilidad ∝ w_ghs, la semilla de
        MC-44 por comuna (no depende del orden ni de las demás comunas), sin las celdas sin comuna o sin población."""
        m = self.muestra
        self.assertEqual(m.dtype, tendencias.DTYPE_MUESTRA)
        n = {int(c): int((m["cod_comuna"] == c).sum()) for c in np.unique(m["cod_comuna"])}
        self.assertEqual(n, {13101: 50, 13102: 30, 13103: 50, 13104: 50})
        self.assertNotIn(0, n)
        self.assertTrue((m["w_ghs"] > 0).all())
        pesadas = int((m["w_ghs"][m["cod_comuna"] == 13101] == 9.0).sum())
        self.assertGreater(pesadas, 35)              # al azar sin peso serían ≈ 25 de 50
        t = self.tabla
        self.assertEqual(float(m["peso_comuna"][m["cod_comuna"] == 13101][0]),
                         float(t.loc[t["cod_comuna"] == 13101, "w_ghs"].sum()))
        rng = np.random.default_rng(3)
        mezclada = t.iloc[rng.permutation(len(t))].reset_index(drop=True)
        np.testing.assert_array_equal(
            tendencias.muestra_tf_contaminantes(mezclada, mezclada["w_ghs"].to_numpy(), self.U), m)
        sin_13102 = t[t["cod_comuna"] != 13102].reset_index(drop=True)
        otra = tendencias.muestra_tf_contaminantes(sin_13102, sin_13102["w_ghs"].to_numpy(), self.U)
        np.testing.assert_array_equal(otra[otra["cod_comuna"] == 13101], m[m["cod_comuna"] == 13101])
        # H3: la muestra es la de un sorteo hecho aquí por otro camino (SeedSequence de MC-44 con la etiqueta
        # «tf_contaminantes/<cod_comuna>», NUM-6, y choice sin reposición sobre las celdas en orden).
        self.assertEqual(self.U.a("SEMILLA"), 20261023)
        for c in (13101, 13104):
            sub = t[(t["cod_comuna"] == c) & (t["w_ghs"] > 0)].sort_values("celda")
            huella = int.from_bytes(hashlib.sha256(f"tf_contaminantes/{c}".encode("utf-8")).digest(), "big")
            rng_ind = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261023, huella])))
            w = sub["w_ghs"].to_numpy()
            k = rng_ind.choice(len(sub), size=50, replace=False, p=w / w.sum())
            np.testing.assert_array_equal(m["celda"][m["cod_comuna"] == c], np.sort(sub["celda"].to_numpy()[k]))
        d = np.arange(0, 4000)
        np.testing.assert_array_equal(tendencias.dias_tf_contaminantes(d, self.U),
                                      d % self.U.a("SEL_MOD") == self.U.a("SEL_RESTO"))
        self.assertEqual((self.U.a("SEL_MOD"), self.U.a("SEL_RESTO"), self.U.a("M6_CELDAS_COMUNA")), (11, 3, 50))

    def _media_nacional(self, fabrica, escenario: str = "completo") -> float:
        """La media nacional ponderada 2015-2024 de un escenario, calculada aquí por otro camino."""
        m = self.muestra
        d = np.arange(tendencias._d2000_de_fecha(2015), tendencias._d2000_de_fecha(2025))
        d = d[d % 11 == 3]
        P = fabrica(MODELO_FALSO, "I", escenario, m["celda"], d)
        anio = tendencias._anio_de_dia(d)
        por_comuna = []
        for c in np.unique(m["cod_comuna"]):
            sel = m["cod_comuna"] == c
            anuales = [np.sum(P[anio == y][:, sel] * m["w_ghs"][sel]) / (np.sum(anio == y) * m["w_ghs"][sel].sum())
                       for y in range(2015, 2025)]
            por_comuna.append((float(m["peso_comuna"][sel][0]), float(np.mean(anuales))))
        W = np.array([x[0] for x in por_comuna])
        return float(np.dot(W, [x[1] for x in por_comuna]) / W.sum())

    def test_s16_tf_contaminantes_cero_con_a_y_c(self):
        """Fábrica falsa con un ganador A o C: la predicción no cambia entre escenarios y la TF es 0 por construcción;
        las cotas son el 1 % y el 3 % de la media nacional ponderada 2015-2024 del escenario completo."""
        for ganador in ("A", "C"):
            fabrica = _fabrica(_meteo(ganador=ganador))
            for variante in ("I", "D"):
                with self.subTest(ganador=ganador, variante=variante):
                    r = tendencias.tf_contaminantes(fabrica, MODELO_FALSO, variante, self.muestra, self.U)
                    self.assertEqual((r["resultado"], r["media_pond"], r["p95_pond"]), ("pasa", 0.0, 0.0))
                    nacional = self._media_nacional(fabrica)
                    self.assertAlmostEqual(r["media_nacional"], nacional, delta=1e-9 * nacional)
                    self.assertAlmostEqual(r["cota_media"], self.U.frac("M6_TF_MEDIA_PCT") * r["media_nacional"],
                                           places=12)
                    self.assertAlmostEqual(r["cota_p95"], self.U.frac("M6_TF_P95_PCT") * r["media_nacional"],
                                           places=12)
                    self.assertEqual(r["n_comunas"], 4)
            v = tendencias.tf_contaminantes(fabrica, MODELO_FALSO, "I", self.muestra, self.U, verificacion_un_mes=True)
            self.assertEqual((v["resultado"], v["verificacion_un_mes"], v["mes"], v["dif_max"]),
                             ("pasa", True, "2015-01", 0.0))

    def test_s16_tf_contaminantes_distinto_de_cero_con_artefacto(self):
        """Con un artefacto sembrado («cambio» sin 1 K de corrección en 2015-2019), la TF es distinta de 0 y falla
        (0,5 µg/m³ frente al 1 % de ≈ 29 µg/m³); la verificación de un mes lo detecta como error de código."""
        fabrica = _fabrica(_meteo(1.0))
        r = tendencias.tf_contaminantes(fabrica, MODELO_FALSO, "D", self.muestra, self.U)
        self.assertGreater(r["media_pond"], 0.0)
        self.assertAlmostEqual(r["media_pond"], 0.5, places=9)
        self.assertEqual(r["resultado"], "falla")
        # H5: la media nacional de las cotas es la del escenario «completo», no la de «cambio».
        nacional, de_cambio = self._media_nacional(fabrica, "completo"), self._media_nacional(fabrica, "cambio")
        self.assertAlmostEqual(r["media_nacional"], nacional, delta=1e-9 * nacional)
        self.assertGreater(abs(r["media_nacional"] - de_cambio), 0.1)
        self.assertAlmostEqual(r["cota_media"], self.U.frac("M6_TF_MEDIA_PCT") * nacional, delta=1e-9)
        with self.assertRaises(tendencias.ErrorTendencias):
            tendencias.tf_contaminantes(fabrica, MODELO_FALSO, "I", self.muestra, self.U, verificacion_un_mes=True)
        # Un artefacto sólo en una comuna mueve el P95 ponderado según su peso (MC-48).
        una = self.muestra["celda"][self.muestra["cod_comuna"] == 13103]
        r1 = tendencias.tf_contaminantes(_fabrica(_meteo(0.2, solo_comuna=una)), MODELO_FALSO, "D", self.muestra,
                                         self.U)
        W = {int(c): float(self.muestra["peso_comuna"][self.muestra["cod_comuna"] == c][0])
             for c in np.unique(self.muestra["cod_comuna"])}
        total = sum(W.values())
        self.assertAlmostEqual(r1["media_pond"], 0.1 * W[13103] / total, places=9)
        esperado = 0.0 if (total - W[13103]) / total >= 0.95 else 0.1      # 13103 pesa 100 de 1.525 (6,6 %)
        self.assertAlmostEqual(r1["p95_pond"], esperado, places=9)
        self.assertEqual(esperado, 0.1)

    def test_s16_tolerancia_de_la_verificacion_de_un_mes(self):
        """H6 (TEN-21): en la verificación de un mes, una diferencia de 2·10⁻⁶ entre escenarios es un error de código y
        una de 5·10⁻⁷ pasa (la tolerancia es ``TF_CERO_TOL``)."""
        self.assertEqual(constantes.valor("TF_CERO_TOL"), 1e-06)
        with self.assertRaises(tendencias.ErrorTendencias):          # 4·10⁻⁶ K en mc_t2m → 2·10⁻⁶ en la predicción
            tendencias.tf_contaminantes(_fabrica(_meteo(4e-6)), MODELO_FALSO, "I", self.muestra, self.U,
                                        verificacion_un_mes=True)
        v = tendencias.tf_contaminantes(_fabrica(_meteo(1e-6)), MODELO_FALSO, "I", self.muestra, self.U,
                                        verificacion_un_mes=True)
        self.assertEqual(v["resultado"], "pasa")
        self.assertAlmostEqual(v["dif_max"], 5e-7, delta=1e-10)

    def test_s16_resultados_en_ramas_m6(self):
        """DEC-14: los resultados entran a ``decision.ramas_m6``; con ganadores A o C, la de I es la verificación de
        un mes; si D falla su TF, gana I por la rama 2."""
        U = self.U
        d = sintetico.tablas_m6("rama1_D")
        condiciones = {p: {s: decision.condiciones_anexo_b(d["comparacion"], p, s, U) for s in sintetico.SENTIDOS_M6}
                       for p in sintetico.CONTAMINANTES_M6}
        ganadores = {"T_Td": "A", "u_v": "C", "p": "A"}
        i = tendencias.tf_contaminantes(_fabrica(_meteo()), MODELO_FALSO, "I", self.muestra, U,
                                        verificacion_un_mes=True)["resultado"]
        for artefacto, rama, variante in ((0.0, 1, "D"), (1.0, 2, "I")):
            dd = tendencias.tf_contaminantes(_fabrica(_meteo(artefacto)), MODELO_FALSO, "D", self.muestra,
                                             U)["resultado"]
            tf = {p: {"I": i, "D": dd} for p in sintetico.CONTAMINANTES_M6}
            r = decision.ramas_m6(condiciones, tf, ganadores)
            self.assertEqual({p: int(x) for p, x in r.rama.items()}, {p: rama for p in sintetico.CONTAMINANTES_M6})
            self.assertEqual({p: str(x) for p, x in r.variante.items() if p != "O3"},
                             {p: variante for p in sintetico.CONTAMINANTES_M6})


if __name__ == "__main__":
    unittest.main()
