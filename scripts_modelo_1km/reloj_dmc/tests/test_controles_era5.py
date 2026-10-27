"""Pruebas de controles_era5.py (C3, §8.E).

A ciegas y sin datos reales: ninguna prueba abre la DMC, ERA5-Land real ni /Volumes. Las series ERA5-Land
son sintéticas, con fases conocidas, en memoria o en NetCDF con la forma real (time × pixel, float32, sin
``units``) dentro de carpetas temporales. Las fases 4 a 10 de §5.2 (orquestacion.evaluar_red) se simulan
casi siempre con una ``evaluar_red`` falsa; ``PruebasRedReal`` corre la de verdad sobre una estación de
prueba, con el adaptador fijado, para la ida y vuelta (se omite si falta el código fijado en AP). Si faltan
los umbrales anclados en C0, la prueba se omite con el motivo. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import copy  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zoneinfo  # noqa: E402
from dataclasses import replace  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest import mock  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import controles_era5 as C3  # noqa: E402
from reloj_dmc import decision, entorno, extraccion, fijados, numerico, politica, umbrales  # noqa: E402
from reloj_dmc.guardas import MARCA_DESFASE_TERMICO_LOCAL  # noqa: E402
from reloj_dmc.tipos import (ESQUEMA_EXTRACTO_HORA, ESQUEMA_GUARDAS, ESQUEMA_MARCAS, ESQUEMA_MES,  # noqa: E402
                             DecisionAnio, MotivoAnio, Veredicto, tabla_vacia, validar_esquema)

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_CACHE = {}
SEMILLA_TEXTO = 20261022                       # §8.E y Anexo B (la prueba la compara con U.f("SEMILLA"))
MACROZONA_REGION = {5: "costa", 13: "centro", 11: "austral", 12: "austral"}
ANIOS = range(2008, 2027)
UNA_HORA = np.timedelta64(1, "h")


def setUpModule():
    zoneinfo.reset_tzpath(to=[])               # §9 y §8.A.2: sólo el paquete tzdata del intérprete
    zoneinfo.ZoneInfo.clear_cache()


def _control_ok(m):
    return extraccion.ControlMesEra5(m, "ab" * 32, True, 280.0, 95000.0, True)


# Controles de mes de una extracción completa y sin anomalías (A1 limpio, lectura C3-16).
CONTROLES_OK = {m: _control_ok(m) for m in extraccion.MESES_ERA5}


class _AdaptadorFalso:
    """Lo que usa la ida y vuelta de meteorologia_v2 (_confirmado y _utc) para reglas de desfase fijo, que son
    las que emite §7.2. Las pruebas con la red falsa no tienen el código fijado; PruebasRedReal usa el real."""
    llamadas = 0

    def _confirmado(self, regla, momento):
        type(self).llamadas += 1
        desde, hasta = (datetime.fromisoformat(regla[k]) for k in ("valid_from", "valid_to"))
        return regla.get("verified") is True and desde <= momento <= hasta

    def _utc(self, momento, regla):
        return momento.replace(tzinfo=timezone(timedelta(minutes=regla["fixed_offset_minutes"]))).astimezone(timezone.utc)


ADAPTADOR = _AdaptadorFalso()


def _regla(codigo, desde, hasta, minutos):
    """Una entrada de politicas_reloj de §7.2 (sólo lo que lee la ida y vuelta)."""
    texto = {"valid_from": desde.isoformat(), "valid_to": hasta.isoformat()}
    return {"station_code": codigo, **texto,
            "clock": {"verified": True, "source": "prueba", **texto, "timestamp_semantics": "instantaneous",
                      "fixed_offset_minutes": minutos}}


def _umbrales():
    if "U" not in _CACHE:
        try:
            _CACHE["U"] = umbrales.cargar_c0(_APH)
        except (OSError, umbrales.ErrorUmbrales) as e:
            raise unittest.SkipTest(f"sin los umbrales anclados en C0: {e}")
    return _CACHE["U"]


# --- Catálogo de píxeles sintético (0,1°, como el real) ----------------------------------------
def _pid(lat, lon):
    """pixel_id = lat_index_global·3600 + lon_index_global (atributo de los mensuales reales)."""
    return int(round((90 - lat) * 10)) * 3600 + int(round((lon % 360) * 10))


def _catalogo():
    """Bloque norte (32 × 20, mar en lon ≤ −72,2; región 5 al oeste de −71,45 y 13 al este) y bloque sur
    (6 × 11 a 52° S, mar en lon ≤ −71,4; región 12). Devuelve (catálogo, válidos)."""
    filas, validos = [], set()
    bloques = [([round(-33.0 - 0.1 * i, 1) for i in range(32)], [round(-72.4 + 0.1 * j, 1) for j in range(20)],
                lambda lon: lon <= -72.15, lambda lon: 5101 if lon <= -71.45 else 13101),
               ([round(-52.0 - 0.1 * i, 1) for i in range(6)], [round(-71.5 + 0.1 * j, 1) for j in range(11)],
                lambda lon: lon <= -71.35, lambda lon: 12101)]
    for lats, lons, es_mar, comuna in bloques:
        for lat in lats:
            for lon in lons:
                p = _pid(lat, lon)
                filas.append({"pixel_id": p, "latitude": lat, "longitude": lon, "cell_west": lon - 0.05,
                              "cell_south": lat - 0.05, "cell_east": lon + 0.05, "cell_north": lat + 0.05,
                              "cod_comuna": comuna(lon), "territorio": "continental",
                              "lat_index_global": p // 3600, "lon_index_global": p % 3600})
                if not es_mar(lon):
                    validos.add(p)
    cat = pd.DataFrame(filas).sort_values("pixel_id").reset_index(drop=True)
    return cat, validos


CAT, VALIDOS = _catalogo()
COORDS = {int(p): (float(la), float(lo)) for p, la, lo in zip(CAT.pixel_id, CAT.latitude, CAT.longitude)}


class _SerieAnalitica:
    """tipos.SerieEra5 analítica: t2m y sp con ciclo diario en hora solar, distintas por píxel."""
    t0 = extraccion.T0_ERA5
    n_horas = extraccion.N_HORAS_ERA5

    def __init__(self, coords):
        self.coords = coords

    def tiene(self, pixel_id):
        return int(pixel_id) in self.coords

    def valores(self, pixel_id, variable, u):
        lat, lon = self.coords[int(pixel_id)]
        u = np.asarray(u).astype("datetime64[h]")
        k = ((u - self.t0) // UNA_HORA).astype(np.float64)
        tsol = (u - u.astype("datetime64[D]")).astype(np.int64) + lon / 15.0
        if variable == "t2m":
            x = 12.0 + 6.0 * np.cos(2 * np.pi * (tsol - 15.0) / 24) + 2.0 * np.sin(2 * np.pi * k / 127.0) \
                + 0.01 * (int(pixel_id) % 7)
        elif variable == "sp":
            x = self.media(pixel_id, "sp") + 0.9 * np.cos(4 * np.pi * (tsol - 9.75) / 24) \
                + 3.0 * np.sin(2 * np.pi * k / 98.0)
        else:
            x = np.zeros(len(u))
        return np.where((u >= self.t0) & (u <= extraccion.ULTIMA_HORA_ERA5), x, np.nan)

    def media(self, pixel_id, variable):
        return 950.0 - 0.5 * (int(pixel_id) % 11) if variable == "sp" else 12.0


def _decision(codigo, anio, veredicto, clase=None):
    return DecisionAnio(codigo=codigo, anio=int(anio), P=(), clases=(), excluidas={}, K=(),
                        veredicto=Veredicto(veredicto), clase_confirmada=clase)


def _clase_del_anio(reloj, anio):
    """En 2015 C(Santiago) ≡ F(−3) (§2.3): la clase confirmada es la fusionada."""
    if anio == 2015 and reloj in ("F(-3)", "C(Santiago)"):
        return "F(-3)|C(Santiago)"
    return reloj


def _decisiones_correctas(unidades):
    return [_decision(u.codigo, a, "confirmado", _clase_del_anio(u.reloj, a)) for u in unidades for a in ANIOS]


class _RedFalsa:
    """Simula orquestacion.evaluar_red: guarda los argumentos, construye ``inspeccionar`` entradas y devuelve
    las decisiones, evidencias y política que se le den (la ciencia de las fases 4-10 no se prueba aquí).
    Como la real (ORQ-9), sólo arma la política si recibe ``huellas``; por omisión, sin reglas."""

    def __init__(self, decisiones=None, evidencias=None, inspeccionar=1, politica=None):
        self.decisiones = decisiones or (lambda codigos: [])
        self.evidencias = evidencias or (lambda codigos: [])
        self.politica = politica or (lambda vistas: {"politicas_reloj": []})
        self.inspeccionar = inspeccionar
        self.llamadas = []

    def __call__(self, entradas, serie, tablas_, umbrales_, opciones, *, avance=None, huellas=None):
        vistas, iterador = [], iter(entradas())          # la fábrica es perezosa: sólo se arman las que se piden
        for _ in range(self.inspeccionar):
            vistas.append(next(iterador))
        self.llamadas.append(SimpleNamespace(entradas=vistas, serie=serie, tablas=tablas_, umbrales=umbrales_,
                                             opciones=opciones, huellas=huellas))
        return SimpleNamespace(decisiones=self.decisiones(vistas), evidencias=self.evidencias(vistas),
                               politica=None if huellas is None else self.politica(vistas))


# --- ERA5-Land sintético de fases conocidas ---------------------------------------------------
def _horas_del_mes(yyyymm):
    mes = np.datetime64(f"{yyyymm[:4]}-{yyyymm[4:]}", "M")
    return np.arange(mes.astype("datetime64[h]"), (mes + 1).astype("datetime64[h]"), UNA_HORA)


def _campos_de_fase(t, pixel_ids, psi2, phi1, rng, a2=1.0, a1=6.0):
    """t2m (K) y sp (Pa) float32 con S2 de amplitud ``a2`` hPa y máximo en ψ2 h solares y ciclo térmico con
    máximo en φ1; la hora solar sale de numerico.hora_solar (camino ajeno a controles_era5)."""
    n_t, n_p = len(t), len(pixel_ids)
    t2m, sp = np.full((n_t, n_p), np.nan), np.full((n_t, n_p), np.nan)
    k = ((t - extraccion.T0_ERA5) // UNA_HORA).astype(np.float64)
    for c, p in enumerate(pixel_ids):
        lat, lon = COORDS[int(p)]
        t0 = numerico.hora_solar(t, lon)
        sinoptico = 1.0 * np.sin(2 * np.pi * k / 101.0 + c)
        sp[:, c] = 100.0 * (950.0 + a2 * np.cos(4 * np.pi * (t0 - psi2[c]) / 24) + 0.5 * np.cos(2 * np.pi * (t0 - 7) / 24)
                            + sinoptico + 0.3 * rng.standard_normal(n_t))
        t2m[:, c] = 288.0 + a1 * np.cos(2 * np.pi * (t0 - phi1[c]) / 24) + 0.5 * sinoptico \
            + 0.4 * rng.standard_normal(n_t)
    return {"t2m": t2m.astype(np.float32), "sp": sp.astype(np.float32),
            "u10": np.zeros((n_t, n_p), np.float32), "v10": np.zeros((n_t, n_p), np.float32)}


def _lecturas(meses, pixel_ids, psi2, phi1, semilla=7, **kw):
    """(AAAAMM, (tiempos, pixel_id, valores, control)) como extraccion.leer_mes_era5land, en memoria."""
    rng = np.random.default_rng(semilla)
    for m in meses:
        t = _horas_del_mes(m)
        valores = _campos_de_fase(t, pixel_ids, psi2, phi1, rng, **kw)
        control = extraccion.ControlMesEra5(m, "ab" * 32, True, float(np.nanmedian(valores["t2m"])),
                                            float(np.nanmedian(valores["sp"])), True)
        yield m, (t, np.asarray(pixel_ids, dtype=np.int64), valores, control)


def _escribir_nc(ruta, t, pixel_ids, campos):
    netCDF4 = extraccion._netcdf4()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ds = netCDF4.Dataset(ruta, "w", format="NETCDF4")
    try:
        ds.createDimension("time", len(t))
        ds.createDimension("pixel", len(pixel_ids))
        tv = ds.createVariable("time", "i8", ("time",))
        tv.units = "seconds since 1970-01-01 00:00:00 UTC"
        tv.calendar = "proleptic_gregorian"
        tv[:] = (t.astype("datetime64[s]") - np.datetime64("1970-01-01T00:00:00", "s")).astype(np.int64)
        ds.createVariable("pixel_id", "i8", ("pixel",))[:] = np.asarray(pixel_ids, dtype=np.int64)
        for nombre in ("t2m", "sp", "u10", "v10"):
            v = ds.createVariable(nombre, "f4", ("time", "pixel"), zlib=True, fill_value=np.float32(np.nan))
            v[:] = campos[nombre]
    finally:
        ds.close()


def _mes_nc(raiz_era5l, yyyymm, semilla=11):
    """Mensual con todos los píxeles del catálogo; los no válidos, sin dato (NaN)."""
    ids = CAT.pixel_id.to_numpy(dtype=np.int64)
    t = _horas_del_mes(yyyymm)
    n = len(ids)
    campos = _campos_de_fase(t, ids, np.full(n, 9.75), np.full(n, 14.5), np.random.default_rng(semilla))
    sin_dato = ~np.isin(ids, np.array(sorted(VALIDOS)))
    for v in campos.values():
        v[:, sin_dato] = np.nan
    ruta = extraccion.ruta_mes_era5(raiz_era5l, yyyymm)
    _escribir_nc(ruta, t, ids, campos)
    return ruta


# ===========================================================================
class PruebasC3a(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.pixeles = C3.pixeles_c3a(CAT, VALIDOS, MACROZONA_REGION)

    def _correr(self, psi2, phi1, pixeles=None, meses=("201501", "201502"), **kw):
        pixeles = self.pixeles if pixeles is None else pixeles
        ids = pixeles.pixel_id.to_numpy()
        return C3._c3a_desde_meses(_lecturas(meses, ids, psi2, phi1, **kw), pixeles, self.U)

    def test_c3a_muestra_y_macrozonas(self):
        """Píxeles válidos con |lat| ≤ 50°, por pixel_id, con la macrozona de §3.3 (región del centro)."""
        p = self.pixeles
        self.assertTrue(set(p.pixel_id) <= VALIDOS)
        self.assertTrue((p.latitude.abs() <= 50).all())
        self.assertEqual(list(p.pixel_id), sorted(p.pixel_id))
        self.assertEqual(len(p), 32 * 17)                     # el bloque sur (52° S) queda fuera
        self.assertEqual(set(p.macrozona), {"costa", "centro"})
        self.assertEqual(int((p.macrozona == "costa").sum()), 32 * 7)
        self.assertEqual(C3.meses_c3a()[0], "201501")
        self.assertEqual(C3.meses_c3a()[-1], "202412")
        self.assertEqual(len(C3.meses_c3a()), 120)

    def test_ajuste_acumulado_igual_al_directo(self):
        """Las ecuaciones normales acumuladas dan el ajuste de numerico.ajuste_armonico (EE × 2, φ1, ψ2)."""
        rng = np.random.default_rng(3)
        t = np.sort(rng.uniform(0, 24 * 60, 3000))
        a = 0.8 * np.cos(4 * np.pi * (t - 9.6) / 24) + 2.0 * np.cos(2 * np.pi * (t - 14.2) / 24) \
            + 0.3 * np.cos(6 * np.pi * (t - 3.0) / 24) + 0.4 * rng.standard_normal(len(t))
        directo = numerico.ajuste_armonico(t, a, 3, 2.0)
        normales = C3._Normales(1, 6)
        for parte in np.array_split(np.arange(len(t)), 4):               # en trozos, como mes a mes
            X = C3._diseno(t[parte][:, None], 3)
            normales.sumar(np.array([0]), X, a[parte][:, None])
        acumulado = C3.ajuste_desde_normales(normales.XtX[0], normales.Xty[0], normales.yty[0], normales.n[0], 3, 2.0)
        self.assertEqual(acumulado.n, directo.n)
        np.testing.assert_allclose(acumulado.amplitudes, directo.amplitudes, rtol=1e-9)
        np.testing.assert_allclose(acumulado.ee_amplitudes, directo.ee_amplitudes, rtol=1e-6)
        self.assertAlmostEqual(acumulado.phi1, directo.phi1, places=9)
        self.assertAlmostEqual(acumulado.psi2, directo.psi2, places=9)
        self.assertIsNone(C3.ajuste_desde_normales(np.zeros((6, 6)), np.zeros(6), 0.0, 6, 3, 2.0))

    def test_hora_solar_y_anomalia_diaria(self):
        """t0 coincide con numerico.hora_solar; los días UTC con < 20 valores no dan anomalía."""
        t = _horas_del_mes("201507")
        lon = np.array([-70.6, -72.1, -109.4])
        t0 = C3._hora_solar_utc(t, lon)
        for c, l in enumerate(lon):
            np.testing.assert_allclose(t0[:, c], numerico.hora_solar(t, l), atol=1e-12)
        x = np.tile(np.arange(len(t), dtype=float)[:, None], (1, 2))
        x[:5, 1] = np.nan                                        # el día 1 de la columna 1 queda con 19 valores
        a = C3._anomalias_dia_utc(x, t.astype("datetime64[D]"), 20)
        self.assertTrue(np.isnan(a[:24, 1]).all())
        np.testing.assert_allclose(a[:24, 0], np.arange(24) - 11.5)
        np.testing.assert_allclose(a[24:48, 1], np.arange(24) - 11.5)

    def test_c3a_psi2_y_phi1_con_serie_sintetica(self):
        """Mediana de ψ2 a ≤ 0,30 h de 9,75 h; φ1 en [12,5; 16]."""
        n = len(self.pixeles)
        rng = np.random.default_rng(5)
        psi2 = 9.75 + 0.1 * rng.uniform(-1, 1, n)
        phi1 = np.full(n, 14.5)
        tabla, detalle, motivos = self._correr(psi2, phi1)
        self.assertEqual(motivos, [])
        np.testing.assert_allclose(tabla.psi2_h, psi2, atol=0.1)          # σ(ψ2) ≈ 0,02 h con este ruido
        np.testing.assert_allclose(tabla.phi1_h, phi1, atol=0.05)
        self.assertTrue(tabla.entra_psi2.all())
        crit = detalle["criterios"]
        self.assertTrue(crit["pasa"])
        self.assertLessEqual(crit["pais"]["distancia_h"], self.U.f("C3A_PSI2_TOL_H"))
        self.assertEqual(crit["pais"]["n"], n)
        self.assertTrue(crit["macrozonas"]["costa"]["evaluada"] and crit["macrozonas"]["costa"]["pasa"])
        self.assertAlmostEqual(crit["phi1"]["mediana_h"], 14.5, places=1)
        self.assertEqual(detalle["meses"], ["201501", "201502"])

        # Corrimientos: ψ2 a 0,5 h de la constante falla en el país; φ1 fuera de [12,5; 16] también.
        _, d_psi, m_psi = self._correr(np.full(n, 10.25), phi1)
        self.assertFalse(d_psi["criterios"]["pais"]["pasa"])
        self.assertAlmostEqual(d_psi["criterios"]["pais"]["distancia_h"], 0.5, places=1)
        self.assertTrue(m_psi)
        _, d_phi, _ = self._correr(psi2, np.full(n, 11.0))
        self.assertTrue(d_phi["criterios"]["pais"]["pasa"])
        self.assertFalse(d_phi["criterios"]["phi1"]["pasa"])
        self.assertFalse(d_phi["criterios"]["pasa"])
        # Envoltura circular: ψ2 cerca de 0 h (= 12 h) dista 2,25 h de 9,75, no 9,75 h.
        _, d_cero, _ = self._correr(np.full(n, 0.0), phi1, meses=("201501",))
        self.assertAlmostEqual(d_cero["criterios"]["pais"]["distancia_h"], 2.25, places=1)

    def test_c3a_macrozona_con_30_pixeles(self):
        """Una macrozona con ≥ 30 píxeles fuera de tolerancia hace fallar C3a; con < 30 no se evalúa."""
        p = self.pixeles
        costa = (p.macrozona == "costa").to_numpy()
        psi2 = np.where(costa, 10.5, 9.75)
        phi1 = np.full(len(p), 14.5)
        _, detalle, motivos = self._correr(psi2, phi1, meses=("201501",))
        crit = detalle["criterios"]
        self.assertTrue(crit["pais"]["pasa"])                     # 224 de 544 corridos: la mediana nacional pasa
        self.assertEqual(crit["macrozonas_que_fallan"], ["costa"])
        self.assertFalse(crit["pasa"])
        self.assertTrue(any("costa" in m for m in motivos))
        # Con sólo 29 píxeles de la costa, esa macrozona no se evalúa y C3a pasa.
        reducida = pd.concat([p[~costa], p[costa].iloc[:29]]).sort_values("pixel_id").reset_index(drop=True)
        costa_r = (reducida.macrozona == "costa").to_numpy()
        _, det_r, mot_r = self._correr(np.where(costa_r, 10.5, 9.75), np.full(len(reducida), 14.5),
                                       pixeles=reducida, meses=("201501",))
        self.assertFalse(det_r["criterios"]["macrozonas"]["costa"]["evaluada"])
        self.assertIsNone(det_r["criterios"]["macrozonas"]["costa"]["pasa"])
        self.assertTrue(det_r["criterios"]["pasa"])
        self.assertEqual(mot_r, [])

    def test_c3a_a2_ee_y_eje(self):
        """Sin S2 (A2/EE < 3) no hay mediana de ψ2 y C3a falla; un mes con eje anómalo o ausente, también."""
        n = len(self.pixeles)
        tabla, detalle, _ = self._correr(np.full(n, 9.75), np.full(n, 14.5), meses=("201501",), a2=0.0)
        self.assertFalse(tabla.entra_psi2.any())
        self.assertEqual(detalle["criterios"]["pais"]["n"], 0)
        self.assertFalse(detalle["criterios"]["pasa"])
        lecturas = list(_lecturas(("201501", "201502"), self.pixeles.pixel_id.to_numpy(), np.full(n, 9.75),
                                  np.full(n, 14.5)))
        m, (t, pid, valores, control) = lecturas[1]
        malo = extraccion.ControlMesEra5(m, control.sha256, False, control.mediana_t2m_K, control.mediana_sp_Pa, True)
        _, det, motivos = C3._c3a_desde_meses([lecturas[0], (m, (t, pid, valores, malo)), ("201503", None)],
                                              self.pixeles, self.U)
        self.assertTrue(det["criterios"]["pasa"])                 # la marea y φ1 están bien …
        self.assertEqual(det["meses_eje_anomalo"], ["201502"])    # … pero el eje y el mes ausente hacen fallar
        self.assertEqual(det["meses_ausentes"], ["201503"])
        self.assertEqual(len(motivos), 2)
        # Un mes ilegible (lectura C3-4) también hace fallar, con el tipo del error y sin su texto.
        _, det, motivos = C3._c3a_desde_meses([lecturas[0], ("201502", C3._MesIlegible("OSError"))], self.pixeles,
                                              self.U)
        self.assertEqual(det["meses_ilegibles"], {"201502": "OSError"})
        self.assertEqual(motivos, ["meses ilegibles (A1): 201502 (OSError)"])

    def test_mes_ilegible_hace_fallar_c3a_sin_abortar(self):
        """Un mensual con bytes que no son NetCDF: c3a no lanza (netCDF4 da OSError); anota el mes y no pasa.
        medias_sp_hpa, en cambio, lanza ErrorC3 con el mes (lectura C3-14)."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "ERA5L"
            _mes_nc(raiz, "201501")
            malo = extraccion.ruta_mes_era5(raiz, "201502")
            malo.write_bytes(b"esto no es un NetCDF")
            with self.assertRaises(OSError):                     # lo que hacía abortar a C3a
                extraccion.leer_mes_era5land(malo)
            r = C3.c3a(raiz, CAT, VALIDOS, MACROZONA_REGION, self.U, meses=("201501", "201502", "201503"))
            self.assertFalse(r.pasa)
            self.assertEqual(r.detalle["meses_ilegibles"], {"201502": "OSError"})
            self.assertEqual(r.detalle["meses_ausentes"], ["201503"])
            self.assertIn("meses ilegibles (A1): 201502 (OSError)", r.detalle["motivos"])
            self.assertTrue(r.detalle["criterios"]["pais"]["pasa"])      # el mes legible sí se ajustó
            self.assertNotIn(tmp, json.dumps(r.detalle, default=str))   # sin rutas en el detalle
            medias, ausentes, ilegibles = C3._medias_sp(raiz, VALIDOS, ("201501", "201502", "201503"), C3._nada)
            self.assertEqual((ausentes, ilegibles), (["201503"], {"201502": "OSError"}))
            self.assertEqual(set(medias), VALIDOS)
            with self.assertRaises(C3.ErrorC3):
                C3.medias_sp_hpa(raiz, VALIDOS, meses=("201501", "201502"))
            self.assertEqual(C3.medias_sp_hpa(raiz, VALIDOS, meses=("201501", "201503")), medias)

    def test_c3a_no_reemplaza_la_constante(self):
        """Si falla, informa; nunca toma la fase de ERA5-Land."""
        U = self.U
        huella = U.huella()
        constante = U.f("E4P_S2_FASE_H")
        self.assertEqual(constante, 9.75)
        n = len(self.pixeles)
        tabla, detalle, motivos = self._correr(np.full(n, 10.5), np.full(n, 14.5), meses=("201501",))
        crit = detalle["criterios"]
        self.assertFalse(crit["pasa"])
        self.assertTrue(motivos)
        # Informa la mediana de ERA5-Land, pero la referencia sigue siendo la constante del texto.
        self.assertAlmostEqual(crit["pais"]["mediana_psi2_h"], 10.5, places=1)
        self.assertAlmostEqual(crit["pais"]["distancia_h"], 0.75, places=1)
        self.assertEqual(crit["s2_fase_vigente_h"], constante)
        self.assertEqual(detalle["s2_fase_vigente_h"], constante)
        self.assertIs(detalle["constante_reemplazada"], False)
        self.assertIn("enmienda", detalle["si_falla"])
        # Nada cambió: ni los umbrales ni el criterio vuelto a aplicar sobre la misma tabla.
        self.assertEqual(U.huella(), huella)
        self.assertEqual(U.f("E4P_S2_FASE_H"), constante)
        self.assertFalse(C3.criterios_c3a(tabla, U)["pasa"])
        # Por construcción: el módulo nunca ajusta umbrales ni escribe la constante; sólo la lee con U.f.
        arbol = ast.parse(Path(C3.__file__).read_text(encoding="utf-8"))
        constantes_s2, leidas_con_f = set(), set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and nodo.value == "E4P_S2_FASE_H":
                constantes_s2.add(id(nodo))
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
                self.assertNotIn(nodo.func.attr, ("ajustado", "_replace"), "controles_era5 no ajusta umbrales")
                if (nodo.func.attr == "f" and nodo.args and isinstance(nodo.args[0], ast.Constant)
                        and nodo.args[0].value == "E4P_S2_FASE_H"):
                    leidas_con_f.add(id(nodo.args[0]))
            if isinstance(nodo, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                for o in objetivos:
                    self.assertFalse(isinstance(o, ast.Attribute) and o.attr in ("fijos", "ajustables", "pasos"))
        self.assertTrue(constantes_s2)
        self.assertEqual(constantes_s2, leidas_con_f)          # el id sólo aparece como U.f("E4P_S2_FASE_H")

    def test_c3a_meses_del_texto(self):
        """c3a con meses distintos de 2015-01 … 2024-12 (sólo en pruebas) nunca pasa."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "ERA5L"
            _mes_nc(raiz, "201501")
            r = C3.c3a(raiz, CAT, VALIDOS, MACROZONA_REGION, self.U, meses=("201501",))
        self.assertEqual(r.control, "C3a")
        self.assertFalse(r.pasa)
        self.assertFalse(r.detalle["meses_del_texto"])
        self.assertTrue(r.detalle["criterios"]["pais"]["pasa"])
        self.assertIn("2015-01 a 2024-12", r.detalle["motivos"][0])


# ===========================================================================
class PruebasMuestras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()

    def test_c3b_muestra_con_semilla(self):
        """24 + 6 píxeles, orden de llamadas fijado."""
        U = self.U
        self.assertEqual(U.f("SEMILLA"), SEMILLA_TEXTO)
        m = C3.muestra_c3b(CAT, VALIDOS, U)
        self.assertEqual(len(m), 30)
        self.assertEqual(len(set(m)), 30)
        self.assertTrue(set(m) <= VALIDOS)
        lat = {p: COORDS[p][0] for p in COORDS}
        self.assertTrue(all(abs(lat[p]) <= 50 for p in m[:24]))
        self.assertTrue(all(lat[p] < -50 for p in m[24:]))
        # Camino independiente: un generador, primero 24 del norte y luego 6 del sur, sobre ids ordenados.
        norte = np.array(sorted(p for p in VALIDOS if abs(lat[p]) <= 50), dtype=np.int64)
        sur = np.array(sorted(p for p in VALIDOS if lat[p] < -50), dtype=np.int64)
        rng = np.random.Generator(np.random.PCG64(SEMILLA_TEXTO))
        esperado = [int(x) for x in rng.choice(norte, 24, replace=False)] + \
                   [int(x) for x in rng.choice(sur, 6, replace=False)]
        self.assertEqual(m, esperado)
        rng = np.random.Generator(np.random.PCG64(SEMILLA_TEXTO))
        al_reves = [int(x) for x in rng.choice(sur, 6, replace=False)]
        self.assertNotEqual(m[24:], al_reves)                     # otro orden de llamadas da otra muestra
        # Ni el orden de las filas ni las repeticiones cambian la muestra.
        self.assertEqual(C3.muestra_c3b(CAT.sample(frac=1.0, random_state=4), VALIDOS, U), m)
        self.assertEqual(C3.muestra_c3b(CAT, set(VALIDOS), U), m)
        # Sin 6 píxeles válidos al sur de 50° S no hay muestra.
        solo_norte = {p for p in VALIDOS if lat[p] > -50}
        with self.assertRaises(C3.ErrorC3):
            C3.muestra_c3b(CAT, solo_norte | set(list(sur)[:5]), U)

    def test_c3b_plan_y_fuentes(self):
        """120 unidades píxel × reloj; la fuente es el píxel válido más cercano (≠ el elegido)."""
        plan = C3.plan_c3b(CAT, VALIDOS, self.U)
        self.assertEqual(len(plan), 120)
        self.assertEqual(len({u.codigo for u in plan}), 120)
        self.assertTrue(all(len(u.codigo) == 6 and u.codigo.isdigit() for u in plan))
        self.assertEqual([u.reloj for u in plan[:4]], ["F(0)", "F(-3)", "F(-4)", "C(Santiago)"])
        self.assertEqual(sum(u.zona == "norte" for u in plan), 96)
        for u in plan:
            self.assertEqual(u.enlazado, u.sitio)
            self.assertNotEqual(u.fuente, u.sitio)
            self.assertIn(u.fuente, VALIDOS)
            lat0, lon0 = COORDS[u.sitio]
            otros = sorted(p for p in VALIDOS if p != u.sitio)
            d = numerico.distancia_km(lat0, lon0, np.array([COORDS[p][0] for p in otros]),
                                      np.array([COORDS[p][1] for p in otros]))
            self.assertAlmostEqual(float(d.min()), float(numerico.distancia_km(
                lat0, lon0, np.array([COORDS[u.fuente][0]]), np.array([COORDS[u.fuente][1]]))[0]), places=9)
            self.assertTrue(u.ruido and u.con_qfe)

    def test_vecinos_catalogo(self):
        """8 contiguos por índice global presentes en el catálogo; sin las columnas, desde pixel_id."""
        centro, esquina, borde = _pid(-33.5, -71.0), _pid(-33.0, -72.4), _pid(-33.0, -71.0)
        self.assertEqual(len(C3.vecinos_catalogo(CAT, centro)), 8)
        self.assertEqual(len(C3.vecinos_catalogo(CAT, esquina)), 3)
        self.assertEqual(len(C3.vecinos_catalogo(CAT, borde)), 5)
        esperado = sorted(_pid(round(-33.5 + a, 1), round(-71.0 + b, 1))
                          for a in (-0.1, 0, 0.1) for b in (-0.1, 0, 0.1) if (a, b) != (0, 0))
        self.assertEqual(list(C3.vecinos_catalogo(CAT, centro)), esperado)
        sin_indices = CAT.drop(columns=["lat_index_global", "lon_index_global"])
        for p in (centro, esquina, borde):
            self.assertEqual(C3.vecinos_catalogo(sin_indices, p), C3.vecinos_catalogo(CAT, p))
        with self.assertRaises(KeyError):
            C3.vecinos_catalogo(CAT, _pid(-40.0, -70.0))
        # Índices que no calzan con los centros (otra convención): se detiene en vez de dar vecinos falsos.
        corrido = CAT.assign(lat_index_global=CAT.lat_index_global + 1)
        with self.assertRaises(C3.ErrorC3):
            C3.vecinos_catalogo(corrido, centro)
        renumerado = sin_indices.assign(pixel_id=np.arange(len(sin_indices)))
        with self.assertRaises(C3.ErrorC3):
            C3.vecinos_catalogo(renumerado, 5)

    def test_c3c_pares_costeros(self):
        """10-15 km, |Δz| ≤ 1.000 m, sin la exclusión costera."""
        U = self.U
        z = {p: 100.0 + 10.0 * (p % 13) for p in VALIDOS}
        parejas = C3.parejas_c3c(CAT, VALIDOS, z, U)
        costeros = {p for p in VALIDOS if any(q not in VALIDOS for q in C3.vecinos_catalogo(CAT, p))}
        interiores = VALIDOS - costeros
        self.assertEqual(costeros, {p for p in VALIDOS if COORDS[p] in {(la, -72.1) for la in np.round(
            -33.0 - 0.1 * np.arange(32), 1)} | {(la, -71.3) for la in np.round(-52.0 - 0.1 * np.arange(6), 1)}})
        self.assertEqual(set(parejas), costeros)                 # todos tienen un interior en diagonal
        for c, (i, d) in parejas.items():
            self.assertIn(i, interiores)
            self.assertTrue(10.0 <= d <= 15.0)
            # El más cercano entre los interiores a 10-15 km con |Δz| ≤ 1.000 m (empate: menor pixel_id).
            cand = sorted(interiores)
            dd = numerico.distancia_km(*COORDS[c], np.array([COORDS[p][0] for p in cand]),
                                       np.array([COORDS[p][1] for p in cand]))
            ok = [(float(x), p) for x, p in zip(dd, cand) if 10 <= x <= 15 and abs(z[p] - z[c]) <= 1000]
            self.assertEqual(i, min(ok)[1])
        # Un desnivel de más de 1.000 m saca al candidato; sin otro, el costero queda sin pareja.
        c0, (i0, _) = sorted(parejas.items())[0]
        z_alto = dict(z)
        z_alto[i0] = z[c0] + 1000.5
        nuevas = C3.parejas_c3c(CAT, VALIDOS, z_alto, U)
        self.assertNotEqual(nuevas.get(c0, (None,))[0], i0)
        # Muestra: un generador con la semilla, una llamada sobre los costeros con pareja, ordenados.
        pares = C3.muestra_c3c(CAT, VALIDOS, z, U)
        self.assertEqual(len(pares), 30)
        rng = np.random.Generator(np.random.PCG64(SEMILLA_TEXTO))
        elegidos = [int(x) for x in rng.choice(np.array(sorted(parejas), dtype=np.int64), 30, replace=False)]
        self.assertEqual(pares, [(c, parejas[c][0]) for c in elegidos])
        # Con menos de 30 costeros con pareja, C3c no tiene muestra.
        with self.assertRaises(C3.ErrorC3):
            C3.muestra_c3c(CAT, VALIDOS, {p: v for p, v in z.items() if p in interiores or p in elegidos[:5]}, U)


# ===========================================================================
class PruebasC3b(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.plan = C3.plan_c3b(CAT, VALIDOS, cls.U)

    def test_c3b_unidad_recupera(self):
        """≥ 80 % de los años con el reloj verdadero y ninguno con otro."""
        U = self.U
        rec = C3.recupera_unidad
        anios = list(ANIOS)                                                     # 19 años
        conf = [_decision("930000", a, "confirmado", "F(-4)") for a in anios]
        insuf = [_decision("930000", a, "insuficiente") for a in anios]
        self.assertTrue(rec(conf[:16] + insuf[16:], "F(-4)", U)["recupera"])    # 16/19 = 0,84
        r = rec(conf[:15] + insuf[15:], "F(-4)", U)                              # 15/19 = 0,79
        self.assertFalse(r["recupera"])
        self.assertAlmostEqual(r["frac_verdadero"], 15 / 19)
        self.assertTrue(rec(conf[:4] + insuf[4:5], "F(-4)", U)["recupera"])      # 4/5 = 0,80: el borde entra
        otro = conf[:18] + [_decision("930000", 2026, "confirmado", "F(-3)")]
        r = rec(otro, "F(-4)", U)
        self.assertFalse(r["recupera"])
        self.assertEqual((r["n_confirmados_otro"], r["anios_otro"]), (1, [2026]))
        self.assertEqual((r["n_confirmaciones_erroneas"], r["anios_erroneos"], r["n_erroneas_retiradas"]),
                         (1, [2026], 0))
        # Los años sin datos no cuentan; ninguno con datos no recupera.
        sin = [_decision("930000", a, "sin_datos") for a in anios[16:]]
        self.assertEqual(rec(conf[:16] + sin, "F(-4)", U)["n_anios"], 16)
        self.assertFalse(rec([], "F(-4)", U)["recupera"])
        self.assertFalse(rec(sin, "F(-4)", U)["recupera"])
        # 2015: la clase fusionada F(−3)|C(Santiago) cuenta para ambos; «sin_confirmar» cuenta como año.
        civil = [_decision("930003", a, "confirmado", _clase_del_anio("C(Santiago)", a)) for a in anios]
        self.assertTrue(rec(civil, "C(Santiago)", U)["recupera"])
        self.assertEqual(rec(civil, "F(-3)", U)["n_confirmados_verdadero"], 1)
        self.assertFalse(rec(civil, "F(-3)", U)["recupera"])
        r = rec(civil[:15] + [_decision("930003", a, "sin_confirmar") for a in anios[15:]], "C(Santiago)", U)
        self.assertEqual((r["n_anios"], r["recupera"]), (19, False))

    def test_confirmacion_erronea_borrada_por_5_3_cuenta_como_erronea(self):
        """Lectura C3-12, con decision.rachas real: reloj verdadero F(0); 2026 confirmado F(−3) en el paso 9 de
        §5.1. §5.3 lo deja sin confirmar (cambio sin respaldo) y conserva su clase: sigue siendo una
        confirmación errónea y la unidad no recupera, aunque 18 de 19 años queden con F(0)."""
        U = self.U
        pasos = [_decision("930000", a, "confirmado", "F(0)") for a in range(2008, 2026)]
        pasos.append(_decision("930000", 2026, "confirmado", "F(-3)"))
        finales = decision.rachas(pasos, tabla_vacia(ESQUEMA_MES), frozenset(), U).decisiones
        ultimo = finales[-1]
        self.assertEqual((ultimo.veredicto, ultimo.motivo, ultimo.clase_confirmada),
                         (Veredicto.SIN_CONFIRMAR, MotivoAnio.CAMBIO_SIN_RESPALDO, "F(-3)"))
        r = C3.recupera_unidad(finales, "F(0)", U)
        self.assertEqual(r["n_confirmados_verdadero"], 18)
        self.assertEqual(r["n_confirmados_otro"], 0)                    # con los finales no se ve …
        self.assertEqual((r["n_confirmaciones_erroneas"], r["n_erroneas_retiradas"], r["anios_erroneos"]),
                         (1, 1, [2026]))                                # … pero el paso 9 sí
        self.assertGreaterEqual(r["frac_verdadero"], U.frac("C3B_UNIDAD_PCT"))
        self.assertFalse(r["recupera"])
        self.assertTrue(C3.es_confirmacion_erronea(ultimo, "F(0)"))
        self.assertFalse(C3.es_confirmacion_erronea(finales[0], "F(0)"))
        self.assertFalse(C3.es_confirmacion_erronea(_decision("930000", 2010, "insuficiente"), "F(0)"))
        fila = C3.tabla_anios(finales, [SimpleNamespace(codigo="930000", reloj="F(0)")]).iloc[-1]
        self.assertEqual((bool(fila.confirmado_otro), bool(fila.confirmacion_erronea)), (False, True))

    def test_errores_esporadicos_ocultos_no_dejan_pasar_c3b(self):
        """Cinco unidades del norte con un año de otro reloj que §5.3 borra (decision.rachas real): cuatro
        A → B → A (estación inestable) y una con el último año (cambio sin respaldo). Con los veredictos
        finales no habría ninguna confirmación errónea y recuperarían 92 de 96 (≥ 95 %): C3b pasaría. Con las
        del paso 9 de §5.1, son cinco confirmaciones erróneas y C3b no pasa."""
        U = self.U
        plan = self.plan
        norte = [u for u in plan if u.zona == "norte"]
        otro = {"F(0)": "F(-3)", "F(-3)": "F(0)", "F(-4)": "F(0)", "C(Santiago)": "F(0)"}
        sucias = {u.codigo: (2012 if k < 4 else 2026) for k, u in enumerate(norte[:5])}
        decisiones = []
        for u in plan:
            pasos = [_decision(u.codigo, a, "confirmado",
                               otro[u.reloj] if sucias.get(u.codigo) == a else _clase_del_anio(u.reloj, a))
                     for a in ANIOS]
            decisiones += decision.rachas(pasos, tabla_vacia(ESQUEMA_MES), frozenset(), U).decisiones
        tabla = C3.tabla_unidades(decisiones, plan, U)
        crit = C3.criterios_c3b(tabla, U)
        self.assertEqual(crit["confirmaciones_erroneas_finales"], 0)
        self.assertEqual(crit["confirmaciones_erroneas"], 5)
        self.assertEqual(crit["confirmaciones_erroneas_retiradas"], 5)
        self.assertEqual(crit["recuperan_norte"], 91)                   # las 5 sucias no recuperan
        self.assertFalse(crit["pasa"])
        # Sin las confirmaciones del paso 9 (la lectura anterior), el mismo caso pasaba.
        vieja = tabla.assign(n_confirmaciones_erroneas=tabla["n_confirmados_otro"],
                             recupera=(tabla["frac_verdadero"] >= U.frac("C3B_UNIDAD_PCT"))
                             & (tabla["n_confirmados_otro"] == 0) & (tabla["n_anios"] > 0))
        self.assertEqual(int(vieja[vieja.zona == "norte"]["recupera"].sum()), 92)
        self.assertTrue(C3.criterios_c3b(vieja, U)["pasa"])

    def test_c3b_criterios(self):
        """Sin errores en las 120; ≥ 95 % del norte; las 6 F(0) del sur recuperan (las otras pueden no)."""
        U = self.U
        plan = self.plan
        decisiones = _decisiones_correctas(plan)
        tabla = C3.tabla_unidades(decisiones, plan, U)
        self.assertEqual(len(tabla), 120)
        self.assertTrue(C3.criterios_c3b(tabla, U)["pasa"])

        def con(cambios):
            d = [x for x in decisiones if (x.codigo, x.anio) not in cambios] + list(cambios.values())
            return C3.criterios_c3b(C3.tabla_unidades(d, plan, U), U)

        norte = [u for u in plan if u.zona == "norte"]
        sur = [u for u in plan if u.zona == "sur"]
        flojos = {(u.codigo, a): _decision(u.codigo, a, "insuficiente") for u in norte[:4] for a in range(2008, 2014)}
        self.assertTrue(con(flojos)["pasa"])                                     # 92/96 = 0,958
        flojos.update({(norte[4].codigo, a): _decision(norte[4].codigo, a, "insuficiente") for a in range(2008, 2014)})
        r = con(flojos)
        self.assertEqual(r["recuperan_norte"], 91)                               # 91/96 = 0,948
        self.assertFalse(r["pasa"])
        sur_civil = [u for u in sur if u.reloj != "F(0)"]
        insuf_sur = {(u.codigo, a): _decision(u.codigo, a, "insuficiente") for u in sur_civil for a in ANIOS}
        r = con(insuf_sur)
        self.assertTrue(r["pasa"])                                               # F(−3), F(−4) y C pueden fallar
        self.assertEqual(r["recuperan_sur_otros"], 0)
        u0 = next(u for u in sur if u.reloj == "F(0)")
        self.assertFalse(con({(u0.codigo, a): _decision(u0.codigo, a, "insuficiente") for a in ANIOS})["pasa"])
        u1 = sur_civil[0]
        r = con({(u1.codigo, 2020): _decision(u1.codigo, 2020, "confirmado", "F(0)")})
        self.assertEqual(r["confirmaciones_erroneas"], 1)                        # un error en el sur basta
        self.assertFalse(r["pasa"])
        r = C3.criterios_c3b(C3.tabla_unidades(decisiones[:-19], plan, U), U)    # una unidad sin años
        self.assertFalse(r["pasa"])
        with self.assertRaises(C3.ErrorC3):
            C3.tabla_unidades(decisiones + [_decision("999999", 2020, "insuficiente")], plan, U)

    def test_c3b_estaciones_de_prueba_y_red(self):
        """La red recibe LINEAS_C3B con la exclusión costera; las estaciones llevan la serie del píxel fuente
        con ruido de 0,3, sin RR06, etiquetas completas en los relojes fijos y sin h0 en C(Santiago)."""
        U = self.U
        from reloj_dmc import orquestacion
        serie = _SerieAnalitica(COORDS)
        red = _RedFalsa(decisiones=lambda vistas: _decisiones_correctas(self.plan), inspeccionar=4)
        r = C3.c3b(Path("/nada/ERA5L"), CAT, VALIDOS, U, macrozona_region=MACROZONA_REGION, serie=serie,
                   controles_era5=CONTROLES_OK, evaluar_red=red, tablas_calendario=object(), adaptador=ADAPTADOR)
        self.assertTrue(r.pasa, r.detalle["motivos"])
        self.assertEqual(r.control, "C3b")
        self.assertEqual(len(r.tabla), 120)
        self.assertEqual(len(r.detalle["tablas"]["anios"]), 120 * 19)
        self.assertEqual((r.detalle["meses_era5_anomalos"], r.detalle["meses_era5_sin_control"]), ([], []))
        self.assertEqual(len(red.llamadas), 1)
        llamada = red.llamadas[0]
        self.assertIs(llamada.serie, serie)
        self.assertEqual(llamada.opciones.lineas_activas, orquestacion.LINEAS_C3B)
        self.assertTrue(llamada.opciones.aplicar_exclusion_costera)
        self.assertIsInstance(llamada.huellas, politica.HuellasPolitica)     # la red emite la política (C3-15)
        self.assertEqual(r.detalle["ida_y_vuelta"]["comprobada"], True)
        entradas = llamada.entradas
        self.assertEqual([e.info.codigo for e in entradas], [u.codigo for u in self.plan[:4]])
        u0 = self.plan[0]
        for e in entradas:
            validar_esquema(e.extracto, ESQUEMA_EXTRACTO_HORA, nombre="extracto C3b")
            validar_esquema(e.meses, ESQUEMA_MES, nombre="meses C3b")
            info = e.info
            self.assertEqual((info.pixel_id, info.costera), (u0.sitio, False))
            self.assertEqual((info.lat, info.lon), COORDS[u0.sitio])
            self.assertAlmostEqual(info.alt_m, numerico.z_pixel(serie.media(u0.fuente, "sp")), places=5)
            self.assertAlmostEqual(info.z_pix, numerico.z_pixel(serie.media(u0.sitio, "sp")), places=9)
            self.assertFalse(e.extracto[["rr", "tx", "tn", "observador"]].any().any())
            self.assertEqual(int(e.extracto.anio.min()), 2008)
            self.assertEqual(int(e.extracto.anio.max()), 2026)
            self.assertTrue(e.extracto.L.is_monotonic_increasing and not e.extracto.L.duplicated().any())
        # Ruido de 0,3 °C y 0,3 hPa sobre la serie del píxel fuente (F(0): L = u).
        f0 = entradas[0].extracto.set_index("L")
        u = f0.index.to_numpy(dtype="datetime64[h]")
        for col, var in (("ts", "t2m"), ("qfe", "sp")):
            dif = f0[col].to_numpy() - serie.valores(u0.fuente, var, u)
            self.assertAlmostEqual(float(np.nanstd(dif)), 0.3, delta=0.02)
            self.assertAlmostEqual(float(np.nanmean(dif)), 0.0, delta=0.02)
        # Etiquetas: completas en los relojes fijos; en C(Santiago), exactamente las de la zona (sin h0).
        horas_2008 = pd.date_range("2008-01-01", "2008-12-31 23:00", freq="h")
        for e in entradas[:3]:
            L = pd.DatetimeIndex(e.extracto.L[e.extracto.anio == 2008])
            self.assertEqual(len(L), len(horas_2008))
            self.assertTrue((L == horas_2008).all())
        santiago = ZoneInfo("America/Santiago")
        u_utc = [datetime(2007, 12, 31, tzinfo=timezone.utc) + timedelta(hours=k) for k in range(24 * 370)]
        civiles = sorted({x.astimezone(santiago).replace(tzinfo=None) for x in u_utc}
                         & set(horas_2008.to_pydatetime()))
        L_c = list(pd.DatetimeIndex(entradas[3].extracto.L[entradas[3].extracto.anio == 2008]).to_pydatetime())
        self.assertEqual(L_c, civiles)
        self.assertNotIn(datetime(2008, 10, 12, 0), L_c)                          # adelanto de 2008: h0 no existe
        self.assertEqual(len(L_c), len(horas_2008) - 1)

    def test_c3b_era5_anomalo_no_corre_la_red(self):
        """Sin serie, extrae los 30 elegidos y sus fuentes; con un mes anómalo (A1) falla sin correr la red."""
        U = self.U
        serie = _SerieAnalitica(COORDS)
        llamadas = []

        def extraer(raiz, pixel_ids, destino, **kw):
            llamadas.append((pixel_ids, destino, kw))
            ok = extraccion.ControlMesEra5("200001", "ab" * 32, True, 280.0, 95000.0, True)
            malo = extraccion.ControlMesEra5("200002", "ab" * 32, False, 280.0, 95000.0, True)
            return serie, {"200001": ok, "200002": malo}

        red = _RedFalsa()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C3.extraccion, "extraer_era5land", extraer):
            r = C3.c3b(Path(tmp) / "ERA5L", CAT, VALIDOS, U, macrozona_region=MACROZONA_REGION,
                       destino=Path(tmp) / "c3b", evaluar_red=red, tablas_calendario=object(), adaptador=ADAPTADOR)
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["meses_era5_anomalos"], ["200002"])
        self.assertEqual(len(r.detalle["meses_era5_sin_control"]), len(extraccion.MESES_ERA5) - 2)
        self.assertEqual(red.llamadas, [])
        pixel_ids, destino, kw = llamadas[0]
        self.assertEqual(set(pixel_ids), {u.sitio for u in self.plan} | {u.fuente for u in self.plan})
        self.assertEqual(destino.name, "c3b")
        self.assertEqual(kw["validos"], VALIDOS)
        with self.assertRaises(ValueError):                        # sin serie ni destino no hay dónde extraer
            C3.c3b(Path("/nada"), CAT, VALIDOS, U, macrozona_region=MACROZONA_REGION, evaluar_red=red)

        # Una extracción que no se puede hacer (un mes ilegible la detiene) deja C3b sin pasar, sin abortar.
        def ilegible(*_a, **_k):
            raise OSError("NetCDF: Unknown file format")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(C3.extraccion, "extraer_era5land", ilegible):
            r = C3.c3b(Path(tmp) / "ERA5L", CAT, VALIDOS, U, macrozona_region=MACROZONA_REGION,
                       destino=Path(tmp) / "c3b", evaluar_red=red, tablas_calendario=object(), adaptador=ADAPTADOR)
        self.assertFalse(r.pasa)
        self.assertIn("OSError", r.detalle["motivos"][0])
        self.assertEqual(red.llamadas, [])

    def test_c3b_con_serie_y_sin_controles_no_pasa_sin_A1(self):
        """Lectura C3-16: con una serie ya extraída, los controles de mes son obligatorios; un mes sin control
        cuenta como A1 y la red no corre."""
        U = self.U
        serie = _SerieAnalitica(COORDS)
        red = _RedFalsa(decisiones=lambda vistas: _decisiones_correctas(self.plan))
        comunes = dict(macrozona_region=MACROZONA_REGION, serie=serie, evaluar_red=red, tablas_calendario=object(),
                       adaptador=ADAPTADOR)
        with self.assertRaises(ValueError):
            C3.c3b(Path("/nada"), CAT, VALIDOS, U, **comunes)
        with self.assertRaises(ValueError):
            C3.c3c(Path("/nada"), CAT, VALIDOS, U, z_pix={p: 100.0 for p in VALIDOS}, **comunes)
        parciales = {m: c for m, c in CONTROLES_OK.items() if m != "201907"}
        r = C3.c3b(Path("/nada"), CAT, VALIDOS, U, controles_era5=parciales, **comunes)
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["meses_era5_sin_control"], ["201907"])
        self.assertTrue(any("sin control" in m for m in r.detalle["motivos"]))
        self.assertEqual(red.llamadas, [])
        self.assertEqual(C3.meses_era5_sin_control(parciales), ["201907"])
        self.assertEqual(C3.meses_era5_sin_control(CONTROLES_OK), [])

    def test_c3b_emite_politica_y_comprueba_ida_y_vuelta(self):
        """Lectura C3-15 (§8, reglas comunes): la red recibe huellas y emite la política; una regla que no
        devuelve el u que generó la etiqueta hace fallar C3b; sin política (A5 alto) o sin adaptador, C3b
        no pasa (sin adaptador, ni siquiera corre la red)."""
        U = self.U
        serie = _SerieAnalitica(COORDS)
        u0 = self.plan[0]                                               # F(0): u = L
        buena = lambda vistas: {"politicas_reloj": [_regla(u0.codigo, datetime(2010, 1, 1), datetime(2010, 1, 31, 23),
                                                           0)]}
        mala = lambda vistas: {"politicas_reloj": [_regla(u0.codigo, datetime(2010, 1, 1), datetime(2010, 1, 31, 23),
                                                          -180)]}

        def correr(**kw):
            red = _RedFalsa(decisiones=lambda vistas: _decisiones_correctas(self.plan), **kw)
            argumentos = dict(macrozona_region=MACROZONA_REGION, serie=serie, controles_era5=CONTROLES_OK,
                              evaluar_red=red, tablas_calendario=object(), adaptador=ADAPTADOR)
            return C3.c3b(Path("/nada"), CAT, VALIDOS, U, **argumentos), red

        _AdaptadorFalso.llamadas = 0
        r, red = correr(politica=buena)
        self.assertTrue(r.pasa, r.detalle["motivos"])
        ida = r.detalle["ida_y_vuelta"]
        self.assertEqual((ida["comprobada"], ida["reglas"], ida["estaciones_con_reglas"], ida["fallas"]),
                         (True, 1, 1, []))
        self.assertGreaterEqual(_AdaptadorFalso.llamadas, 31 * 24)    # cada etiqueta de enero de 2010
        self.assertEqual(red.llamadas[0].huellas.adaptador_sha256, fijados.SHA_ADAPTADOR)
        r, _ = correr(politica=mala)
        self.assertFalse(r.pasa)
        self.assertTrue(r.detalle["ida_y_vuelta"]["fallas"])
        self.assertTrue(r.detalle["criterios"]["pasa"])               # las decisiones están bien …
        self.assertTrue(any("ida y vuelta" in m for m in r.detalle["motivos"]))   # … pero la política no
        r, _ = correr(politica=lambda vistas: None)                   # A5 alto: no hay política
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["ida_y_vuelta"]["politica_emitida"], False)
        self.assertIn(C3.MOTIVO_SIN_POLITICA, r.detalle["motivos"])
        red = _RedFalsa(decisiones=lambda vistas: _decisiones_correctas(self.plan))
        r = C3.c3b(Path("/nada"), CAT, VALIDOS, U, macrozona_region=MACROZONA_REGION, serie=serie,
                   controles_era5=CONTROLES_OK, evaluar_red=red, tablas_calendario=object())
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["motivos"], [C3.MOTIVO_SIN_ADAPTADOR])
        self.assertEqual(red.llamadas, [])
        # Las huellas de la política en memoria son sha256 válidos (politica.politica las valida).
        h = C3.huellas_c3("C3b")
        self.assertEqual((h.commit_ap, h.protocolo_sha256), ("0" * 40, umbrales.SHA_PROTOCOLO_C0))
        politica._validar_huellas(h)
        self.assertNotEqual(C3.huellas_c3("C3c").informe_sha256, h.informe_sha256)


# ===========================================================================
def _guardas_tp(codigo, anio, resultado):
    filas = [{"codigo": codigo, "anio": anio, "guarda": "T-P", "H": "F(0)", "unidad": r, "resultado": resultado,
              "detalle": ""} for r in ("R0", "R1")]
    filas.append({"codigo": codigo, "anio": anio, "guarda": "T-P", "H": "F(-3)", "unidad": "R0", "resultado": "falla",
                  "detalle": ""})                                  # bajo otra H no cuenta
    filas.append({"codigo": codigo, "anio": anio, "guarda": "E3d", "H": "F(0)", "unidad": str(anio),
                  "resultado": "falla", "detalle": ""})            # otra guarda no cuenta
    return filas


def _evidencia(codigo, resultados_tp, delta=0.4):
    """Evidencia mínima (sólo lo que lee C3c): T-P y la marca de δt bajo F(0) por año."""
    guardas = [f for anio, res in resultados_tp.items() for f in _guardas_tp(codigo, anio, res)]
    marcas = [{"codigo": codigo, "anio": anio, "marca": MARCA_DESFASE_TERMICO_LOCAL, "H": "F(0)",
               "valor": (delta if res != "no_evaluable" else None)} for anio, res in resultados_tp.items()]
    g = pd.DataFrame(guardas, columns=list(ESQUEMA_GUARDAS)).astype(ESQUEMA_GUARDAS)
    m = pd.DataFrame(marcas, columns=list(ESQUEMA_MARCAS)).astype(ESQUEMA_MARCAS)
    return SimpleNamespace(info=SimpleNamespace(codigo=codigo), guardas=g, marcas=m)


class PruebasC3c(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.z = {p: 100.0 + 10.0 * (p % 13) for p in VALIDOS}
        cls.pares = C3.muestra_c3c(CAT, VALIDOS, cls.z, cls.U)
        cls.planes = C3.plan_c3c(cls.pares)

    def _red(self, tp_por_par=None, otro_solo_ts=False, inspeccionar=0):
        planes = self.planes
        tp_por_par = tp_por_par or {}

        def decisiones(vistas):
            variante = C3.VARIANTES_C3C[len(red.llamadas) - 1]
            if variante == "Ts":
                salida = [_decision(u.codigo, a, "insuficiente") for u in planes["Ts"] for a in ANIOS]
                if otro_solo_ts:
                    salida[0] = _decision(planes["Ts"][0].codigo, 2008, "confirmado", "F(-3)")
                return salida
            return [_decision(u.codigo, a, "confirmado", "F(0)") for u in planes["Ts+QFE"] for a in ANIOS]

        def evidencias(vistas):
            variante = C3.VARIANTES_C3C[len(red.llamadas) - 1]
            return [_evidencia(u.codigo, tp_por_par.get(k, {a: "pasa" for a in (2010, 2011)}) if variante == "Ts+QFE"
                               else {a: "no_evaluable" for a in (2010, 2011)})
                    for k, u in enumerate(planes[variante])]

        red = _RedFalsa(decisiones, evidencias, inspeccionar)
        return red

    def _c3c(self, red, **kw):
        argumentos = dict(macrozona_region=MACROZONA_REGION, z_pix=self.z, serie=_SerieAnalitica(COORDS),
                          controles_era5=CONTROLES_OK, evaluar_red=red, tablas_calendario=object(), adaptador=ADAPTADOR)
        argumentos.update(kw)
        return C3.c3c(Path("/nada/ERA5L"), CAT, VALIDOS, self.U, **argumentos)

    def test_c3c_red_y_estaciones(self):
        """Dos redes (sólo Ts; Ts y QFE) sin la exclusión costera; la estación lleva la serie del costero en
        UTC, sin ruido, y se enlaza al interior (costera)."""
        from reloj_dmc import orquestacion
        red = self._red(inspeccionar=1)
        r = self._c3c(red)
        self.assertTrue(r.pasa, r.detalle["motivos"])
        self.assertEqual(len(red.llamadas), 2)
        serie = red.llamadas[0].serie
        for llamada, variante in zip(red.llamadas, ("Ts", "Ts+QFE")):
            self.assertFalse(llamada.opciones.aplicar_exclusion_costera)
            self.assertEqual(llamada.opciones.lineas_activas, orquestacion.LINEAS_C3B)
            e = llamada.entradas[0]
            costero, interior = self.pares[0]
            self.assertEqual(e.info.codigo, self.planes[variante][0].codigo)
            self.assertEqual((e.info.pixel_id, e.info.costera), (interior, True))
            self.assertEqual((e.info.lat, e.info.lon), COORDS[costero])
            validar_esquema(e.extracto, ESQUEMA_EXTRACTO_HORA, nombre="extracto C3c")
            ex = e.extracto.set_index("L")
            u = ex.index.to_numpy(dtype="datetime64[h]")                            # F(0): L = u
            np.testing.assert_allclose(ex.ts.to_numpy(), np.round(serie.valores(costero, "t2m", u), 1), atol=1e-9)
            if variante == "Ts":
                self.assertTrue(ex.qfe.isna().all())
            else:
                np.testing.assert_allclose(ex.qfe.to_numpy(), np.round(serie.valores(costero, "sp", u), 1), atol=1e-9)
            self.assertEqual(len(ex), len(pd.date_range("2008-01-01", "2026-09-15 23:00", freq="h")))
        self.assertEqual(len(r.tabla), 60)
        self.assertEqual(r.detalle["criterios"]["pares_tp_evaluable"], 30)
        self.assertEqual(r.detalle["delta_t"]["n"], 60)
        self.assertEqual(set(r.detalle["tablas"]["delta_t"].columns), {"codigo", "variante", "anio", "tp", "delta_t_h"})
        self.assertEqual([list(p) for p in self.pares], r.detalle["pares"])

    def test_c3c_criterios(self):
        """Ninguna confirmación errónea; con sólo Ts, ninguna distinta de F(0); T-P sin fallar en ≥ 95 %."""
        self.assertTrue(self._c3c(self._red({0: {2010: "falla", 2011: "pasa"}})).pasa)        # 29/30
        r = self._c3c(self._red({0: {2010: "falla"}, 1: {2011: "falla"}}))                       # 28/30
        self.assertFalse(r.pasa)
        self.assertAlmostEqual(r.detalle["criterios"]["frac_tp_sin_fallar"], 28 / 30)
        # Los pares sin T-P evaluable salen del denominador: 19/20 = 0,95 pasa (borde incluido).
        sin_tp = {k: {2010: "no_evaluable", 2011: "no_evaluable"} for k in range(2, 12)}
        r = self._c3c(self._red({0: {2010: "falla"}, **sin_tp}))
        self.assertEqual(r.detalle["criterios"]["pares_tp_evaluable"], 20)
        self.assertTrue(r.pasa)
        # Sin ningún par evaluable el criterio no se cumple.
        todos = {k: {2010: "no_evaluable"} for k in range(30)}
        r = self._c3c(self._red(todos))
        self.assertFalse(r.pasa)
        self.assertIsNone(r.detalle["criterios"]["frac_tp_sin_fallar"])
        # Con sólo Ts, una confirmación de F(−3) es errónea y hace fallar C3c.
        r = self._c3c(self._red(otro_solo_ts=True))
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["criterios"]["confirmaciones_no_f0_solo_ts"], 1)
        self.assertEqual(r.detalle["criterios"]["confirmaciones_erroneas"], 1)

    def test_c3c_cuenta_las_confirmaciones_que_borra_5_3(self):
        """Lectura C3-12 también en C3c: con sólo Ts, una confirmación de F(−3) que §5.3 dejó sin confirmar
        (conserva su clase) es una confirmación distinta de F(0)."""
        planes = self.planes
        red = self._red()
        base = red.decisiones

        def decisiones(vistas):
            salida = base(vistas)
            if C3.VARIANTES_C3C[len(red.llamadas) - 1] == "Ts":
                salida[0] = replace(_decision(planes["Ts"][0].codigo, 2008, "sin_confirmar", "F(-3)"),
                                    motivo=MotivoAnio.INESTABLE)
            return salida

        red.decisiones = decisiones
        r = self._c3c(red)
        self.assertFalse(r.pasa)
        crit = r.detalle["criterios"]
        self.assertEqual((crit["confirmaciones_no_f0_solo_ts"], crit["confirmaciones_erroneas"],
                          crit["confirmaciones_erroneas_finales"], crit["confirmaciones_erroneas_retiradas"]),
                         (1, 1, 0, 1))

    def test_c3c_sin_decisiones_no_pasa(self):
        """«Se corre la decisión» (lectura C3-11): sin estación-años evaluados, o con QFE y sin ninguna fila de
        T-P, C3c no pasa aunque T-P no falle en ningún par."""
        planes = self.planes
        red = self._red()
        red.decisiones = lambda vistas: []
        r = self._c3c(red)
        self.assertFalse(r.pasa)
        crit = r.detalle["criterios"]
        self.assertFalse(crit["completo"])
        self.assertEqual(crit["estaciones_sin_anios"], 60)
        self.assertTrue(crit["tp_ok"])                                  # T-P pasa en los 30 pares …
        self.assertTrue(any("30 pares" in m for m in r.detalle["motivos"]))   # … pero no se decidió nada
        # Con decisiones, pero una estación con QFE sin ninguna fila de T-P en su evidencia.
        red = self._red()
        evidencias = red.evidencias

        def sin_tp(vistas):
            salida = evidencias(vistas)
            if C3.VARIANTES_C3C[len(red.llamadas) - 1] == "Ts+QFE":
                salida[0] = SimpleNamespace(info=salida[0].info, guardas=salida[0].guardas.iloc[:0],
                                            marcas=salida[0].marcas.iloc[:0])
            return salida

        red.evidencias = sin_tp
        r = self._c3c(red)
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["criterios"]["estaciones_qfe_sin_tp"], 1)
        self.assertEqual(r.tabla.loc[r.tabla.codigo == planes["Ts+QFE"][0].codigo, "tp_anios_con_guarda"].item(), 0)
        self.assertTrue(r.detalle["criterios"]["tp_ok"])                # 29 de 29 evaluables sin fallar

    def test_c3c_ida_y_vuelta_en_cada_red(self):
        """Lectura C3-15: cada una de las dos redes emite su política y pasa la ida y vuelta; una regla mala en
        la red con QFE basta para que C3c no pase."""
        planes = self.planes
        red = self._red()
        u = planes["Ts+QFE"][0]

        def mala(vistas):
            if C3.VARIANTES_C3C[len(red.llamadas) - 1] != "Ts+QFE":
                return {"politicas_reloj": []}
            return {"politicas_reloj": [_regla(u.codigo, datetime(2011, 3, 1), datetime(2011, 3, 31, 23), -240)]}

        red.politica = mala
        r = self._c3c(red)
        self.assertFalse(r.pasa)
        self.assertTrue(r.detalle["criterios"]["pasa"])
        ida = r.detalle["ida_y_vuelta"]
        self.assertEqual(set(ida), {"Ts", "Ts+QFE"})
        self.assertEqual((ida["Ts"]["pasa"], ida["Ts+QFE"]["pasa"]), (True, False))
        self.assertTrue(any(m.startswith("Ts+QFE: la ida y vuelta falla") for m in r.detalle["motivos"]))
        self.assertTrue(all(isinstance(ll.huellas, politica.HuellasPolitica) for ll in red.llamadas))
        red = self._red()
        r = self._c3c(red, adaptador=None)
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["motivos"], [C3.MOTIVO_SIN_ADAPTADOR])
        self.assertEqual(red.llamadas, [])

    def test_c3c_sin_muestra(self):
        """Con menos de 30 costeros con pareja, C3c no pasa y no corre ninguna red."""
        red = self._red()
        r = C3.c3c(Path("/nada"), CAT, VALIDOS, self.U, macrozona_region=MACROZONA_REGION,
                   z_pix={p: 0.0 for p in list(VALIDOS)[:10]}, serie=_SerieAnalitica(COORDS),
                   controles_era5=CONTROLES_OK, evaluar_red=red, tablas_calendario=object(), adaptador=ADAPTADOR)
        self.assertFalse(r.pasa)
        self.assertIn("30", r.detalle["motivos"][0])
        self.assertEqual(red.llamadas, [])


# ===========================================================================
_REGISTRO = {"activo": False, "prohibidas": (), "abiertos": []}
_EVENTOS_DE_RUTA = ("open", "os.listdir", "os.scandir", "glob.glob", "shutil.copyfile", "shutil.copytree")


def _gancho(evento, args):
    """Gancho de auditoría: registra cada ruta abierta o listada y falla si cae bajo una carpeta prohibida."""
    if not _REGISTRO["activo"] or evento not in _EVENTOS_DE_RUTA or not args:
        return
    ruta = args[0]
    if not isinstance(ruta, (str, bytes, os.PathLike)):
        return
    texto = os.path.normpath(os.path.abspath(os.fsdecode(ruta)))
    _REGISTRO["abiertos"].append(texto)
    for prohibida in _REGISTRO["prohibidas"]:
        if texto == prohibida or texto.startswith(prohibida + os.sep):
            raise PermissionError(f"C3 tocó una carpeta prohibida: {evento} {texto}")


def _instalar_gancho():
    if not _CACHE.get("gancho"):
        sys.addaudithook(_gancho)          # no se puede quitar: queda inerte con «activo» en False
        _CACHE["gancho"] = True


class PruebasCeguera(unittest.TestCase):
    def test_c3_no_abre_la_dmc(self):
        """Registro de open: nada bajo DMC."""
        U = _umbrales()
        _instalar_gancho()
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(Path(tmp))
            dmc = rutas.dmc
            for nombre, contenido in (("progreso.json", "{}"), ("catalogo_nacional.json.gz", "x"),
                                      ("estaciones/330020/2020-01.manifest.json", "{}"),
                                      ("metadata/estaciones.json", "{}"), (".meteo_download.lock", "")):
                (dmc / nombre).parent.mkdir(parents=True, exist_ok=True)
                (dmc / nombre).write_text(contenido, encoding="utf-8")
            for m in ("200001", "201307", "202507", "201501", "201502"):
                _mes_nc(rutas.era5l, m)
            prohibidas = (os.path.normpath(str(dmc)), os.path.normpath("/Volumes"))
            red_b = _RedFalsa(decisiones=lambda v: [], inspeccionar=1)
            red_c = _RedFalsa(decisiones=lambda v: [], inspeccionar=1)
            _REGISTRO.update(activo=True, prohibidas=prohibidas, abiertos=[])
            try:
                # El registro falla de verdad si algo toca la DMC.
                with self.assertRaises(PermissionError):
                    open(dmc / "progreso.json", "rb").close()
                with self.assertRaises(PermissionError):
                    os.listdir(dmc)
                _REGISTRO["abiertos"].clear()
                validos = extraccion.pixeles_validos(rutas.era5l, U)
                ra = C3.c3a(rutas.era5l, CAT, validos, MACROZONA_REGION, U, meses=("201501", "201502"))
                medias = C3.medias_sp_hpa(rutas.era5l, validos, meses=("201501", "201502"))
                serie = _SerieAnalitica(COORDS)
                rb = C3.c3b(rutas.era5l, CAT, validos, U, macrozona_region=MACROZONA_REGION, serie=serie,
                            controles_era5=CONTROLES_OK, evaluar_red=red_b, tablas_calendario=object(),
                            adaptador=ADAPTADOR)
                rc = C3.c3c(rutas.era5l, CAT, validos, U, macrozona_region=MACROZONA_REGION,
                            z_pix=C3.z_pix_de(medias), serie=serie, controles_era5=CONTROLES_OK, evaluar_red=red_c,
                            tablas_calendario=object(), adaptador=ADAPTADOR)
                directo = rutas.local / "pruebas_c3_directo"
                huellas = C3.escribir_c3([ra, rb, rc], directo)
                # El conductor completo (la extracción se simula: su memmap sería de ~225 MB).
                extracciones = []

                def extraer(raiz, pixel_ids, destino, **kw):
                    extracciones.append((Path(raiz), list(pixel_ids), Path(destino)))
                    ok = {m: extraccion.ControlMesEra5(m, "ab" * 32, True, 280.0, 95000.0, True)
                          for m in extraccion.MESES_ERA5}
                    return serie, ok

                red_d = _RedFalsa(decisiones=lambda v: [], inspeccionar=1)
                with mock.patch.object(C3.extraccion, "extraer_era5land", extraer):
                    resultados, huellas_d = C3.correr_c3(rutas, CAT, validos, MACROZONA_REGION, U, evaluar_red=red_d,
                                                         tablas_calendario=object(), adaptador=ADAPTADOR)
                listado_d = sorted(os.listdir(C3.carpeta_c3(rutas)))
                shas_d = {n: entorno.sha256_archivo(C3.carpeta_c3(rutas) / n) for n in listado_d}
                # Un mes ilegible (lectura C3-14): no aborta; la extracción no se intenta y C3b y C3c no pasan.
                extraccion.ruta_mes_era5(rutas.era5l, "200002").write_bytes(b"no es un NetCDF")
                extracciones_antes, red_e = len(extracciones), _RedFalsa(decisiones=lambda v: [], inspeccionar=1)
                with mock.patch.object(C3.extraccion, "extraer_era5land", extraer):
                    con_ilegible, huellas_e = C3.correr_c3(rutas, CAT, validos, MACROZONA_REGION, U,
                                                           evaluar_red=red_e, tablas_calendario=object(),
                                                           adaptador=ADAPTADOR)
            finally:
                _REGISTRO["activo"] = False
            self.assertEqual(len(extracciones), extracciones_antes)
            self.assertEqual(red_e.llamadas, [])
            for r in con_ilegible[1:]:
                self.assertFalse(r.pasa)
                self.assertEqual(r.detalle["motivos"], ["meses ilegibles (A1): 200002 (OSError)"])
            self.assertEqual(sorted(os.listdir(C3.carpeta_c3(rutas))), sorted(huellas_e))
            self.assertNotIn("C3c_delta_t.csv", huellas_e)              # lo de la corrida anterior se borró
            abiertos = list(_REGISTRO["abiertos"])
            self.assertEqual([r.control for r in resultados], ["C3a", "C3b", "C3c"])
            self.assertEqual(len(extracciones), 1)                       # una sola extracción para C3b y C3c
            raiz, pixel_ids, destino = extracciones[0]
            self.assertEqual(raiz, rutas.era5l)
            self.assertEqual(destino, rutas.corridas / "c3_extractos")
            self.assertTrue(set(pixel_ids) <= VALIDOS)
            self.assertEqual(len(pixel_ids), len(set(pixel_ids)))
            self.assertEqual(len(red_d.llamadas), 3)                     # C3b y las dos variantes de C3c
            self.assertEqual(resultados[1].detalle["meses_era5_anomalos"], [])
            self.assertTrue(resultados[0].detalle["meses_del_texto"])
            self.assertIn("meses ausentes", " ".join(resultados[0].detalle["motivos"]))   # sólo hay 2 de 120
            self.assertEqual(validos, VALIDOS)
            self.assertTrue(ra.detalle["criterios"]["pais"]["pasa"])
            self.assertEqual(len(red_b.llamadas[0].entradas), 1)
            self.assertEqual(len(red_c.llamadas), 2)
            era5 = os.path.normpath(str(rutas.era5l))
            self.assertTrue(any(a.startswith(era5 + os.sep) and a.endswith(".nc") for a in abiertos))
            for prohibida in prohibidas:
                self.assertFalse([a for a in abiertos if a == prohibida or a.startswith(prohibida + os.sep)])
            carpeta = C3.carpeta_c3(rutas)
            self.assertTrue(str(carpeta).endswith(os.path.join("modelado_1km", "verificacion_reloj_dmc", "v1", "c3")))
            self.assertEqual(sorted(os.listdir(directo)), sorted(huellas))
            for nombre, sha in huellas.items():
                self.assertEqual(entorno.sha256_archivo(directo / nombre), sha)
            self.assertEqual((listado_d, shas_d), (sorted(huellas_d), huellas_d))    # la primera corrida de correr_c3
            for nombre, sha in huellas_e.items():
                self.assertEqual(entorno.sha256_archivo(carpeta / nombre), sha)
            self.assertIn("C3c_delta_t.csv", huellas_d)
            # La DMC quedó intacta.
            self.assertEqual((dmc / "progreso.json").read_text(encoding="utf-8"), "{}")


class PruebasSalida(unittest.TestCase):
    def _resultado(self, detalle=None):
        tabla = pd.DataFrame({"pixel_id": [1, 2], "psi2_h": [9.7, np.nan]})
        detalle = detalle or {"motivos": [], "x": np.float64(np.nan), "n": np.int64(3), "s": {1, 2},
                              "tablas": {"anios": pd.DataFrame({"a": [1]})}}
        return C3.ResultadoC3("C3a", False, detalle, tabla)

    def test_escribir_c3_con_sha256(self):
        """C3a.json (canónico, sin NaN), C3a.csv, C3a_anios.csv y sha256.json, sólo en la carpeta dada."""
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp) / "c3"
            huellas = C3.escribir_c3([self._resultado()], carpeta)
            self.assertEqual(set(huellas), {"C3a.json", "C3a.csv", "C3a_anios.csv", "sha256.json"})
            self.assertEqual(sorted(os.listdir(carpeta)), sorted(huellas))
            for nombre, sha in huellas.items():
                self.assertEqual(entorno.sha256_archivo(carpeta / nombre), sha)
            lista = json.loads((carpeta / "sha256.json").read_text(encoding="utf-8"))
            self.assertEqual(lista["archivos"], {k: v for k, v in huellas.items() if k != "sha256.json"})
            cuerpo = json.loads((carpeta / "C3a.json").read_text(encoding="utf-8"))
            self.assertEqual(cuerpo["detalle"], {"motivos": [], "x": None, "n": 3, "s": [1, 2]})
            self.assertIs(cuerpo["pasa"], False)
            # Privacidad: un detalle con «/Users/» o «@» no se escribe (y no queda nada a medias).
            otra = Path(tmp) / "otra"
            with self.assertRaises(ValueError):
                C3.escribir_c3([self._resultado({"ruta": "/Users/alguien/x"})], otra)
            with self.assertRaises(ValueError):
                C3.escribir_c3([self._resultado({"correo": "a@b"})], otra)
            with self.assertRaises(TypeError):
                C3.escribir_c3([self._resultado({"ruta": Path(tmp)})], otra)
            self.assertFalse(otra.exists())
        with self.assertRaises(PermissionError):                  # nunca bajo /Volumes (sin tocar el disco)
            C3.escribir_c3([self._resultado()], Path("/Volumes/NoExiste/c3"))

    def test_escribir_c3_no_deja_archivos_viejos(self):
        """Lectura C3-13: tras dos escrituras seguidas, la carpeta tiene sólo lo de la segunda (y lo ajeno a C3,
        intacto); sha256.json lista exactamente los archivos C3 que hay."""
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp) / "c3"
            primera = C3.escribir_c3([self._resultado(),
                                      C3.ResultadoC3("C3b", True, {"tablas": {"anios": pd.DataFrame({"a": [1]})}},
                                                     pd.DataFrame({"x": [1]}))], carpeta)
            self.assertIn("C3b_anios.csv", primera)
            (carpeta / "notas.txt").write_text("ajeno", encoding="utf-8")
            (carpeta / "C3b.json.part").write_bytes(b"resto")          # no calza con la salida de C3: queda
            segunda = C3.escribir_c3([self._resultado({"motivos": ["otra"]})], carpeta)
            self.assertEqual(set(segunda), {"C3a.json", "C3a.csv", "sha256.json"})
            self.assertEqual(sorted(os.listdir(carpeta)), sorted(set(segunda) | {"notas.txt", "C3b.json.part"}))
            lista = json.loads((carpeta / "sha256.json").read_text(encoding="utf-8"))["archivos"]
            self.assertEqual(sorted(lista), ["C3a.csv", "C3a.json"])
            self.assertEqual(sorted(p.name for p in carpeta.iterdir() if C3._PATRON_SALIDA_C3.fullmatch(p.name)),
                             sorted(lista))
            for nombre, sha in segunda.items():
                self.assertEqual(entorno.sha256_archivo(carpeta / nombre), sha)
            # Si la escritura se corta a mitad, no queda un sha256.json que la dé por coherente.
            with mock.patch.object(C3.entorno, "escribir_atomico", side_effect=OSError("disco lleno")):
                with self.assertRaises(OSError):
                    C3.escribir_c3([self._resultado()], carpeta)
            self.assertFalse((carpeta / "sha256.json").exists())


# ===========================================================================
class PruebasRedReal(unittest.TestCase):
    """La evaluar_red real (fases 4 a 10) sobre una estación de prueba de C3b, con el adaptador fijado: la
    política emitida pasa la ida y vuelta de §8 y la unidad recupera sin confirmaciones erróneas. Tarda
    ~8-10 s. Se omite si falta el código fijado en AP (no se da por aprobada)."""

    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        if not (_AP / fijados.RUTA_ADAPTADOR).is_file():
            raise unittest.SkipTest(f"falta el código fijado {fijados.RUTA_ADAPTADOR}; no se da por aprobada")
        from reloj_dmc import tablas
        cls.adaptador = fijados.cargar_adaptador(_AP)
        cls.calendario = tablas.cargar_tablas()

    def test_c3b_con_la_red_real_y_el_adaptador_fijado(self):
        U = self.U
        plan = C3.plan_c3b(CAT, VALIDOS, U)
        civil = [u for u in plan if u.reloj == "C(Santiago)"][:1]        # el reloj de reglas más enredadas
        corridas = []

        def red_real(*args, **kw):
            corridas.append((kw, C3._orquestacion().evaluar_red(*args, **kw)))
            return corridas[-1][1]

        serie = _SerieAnalitica(COORDS)
        with mock.patch.object(C3, "plan_c3b", return_value=civil):
            r = C3.c3b(Path("/nada"), CAT, VALIDOS, U, macrozona_region=MACROZONA_REGION, serie=serie,
                       controles_era5=CONTROLES_OK, tablas_calendario=self.calendario, evaluar_red=red_real,
                       adaptador=self.adaptador)
        (kw, resultado), = corridas
        self.assertIsInstance(kw["huellas"], politica.HuellasPolitica)
        self.assertIsNotNone(resultado.politica)
        ida = r.detalle["ida_y_vuelta"]
        self.assertTrue(ida["comprobada"])
        self.assertEqual(ida["fallas"], [])
        self.assertEqual(ida["estaciones_con_reglas"], 1)
        self.assertGreater(ida["reglas"], 30)                           # un tramo por régimen de hora civil
        fila = r.tabla.iloc[0]
        self.assertEqual(int(fila.n_confirmaciones_erroneas), 0)
        self.assertTrue(bool(fila.recupera), r.detalle["tablas"]["anios"])
        self.assertFalse(r.pasa)                                        # una sola unidad: no es C3b completo
        self.assertEqual(r.detalle["motivos"][0], "la red no evaluó las 120 unidades")
        # La misma política con un tramo corrido una hora falla la ida y vuelta (con el adaptador real).
        u = civil[0]
        info = C3.infos_de_prueba(civil, CAT, {p: serie.media(p, "sp") for p in (u.sitio, u.fuente)},
                                  MACROZONA_REGION, U)
        caso = C3.caso_de_prueba(u, info[u.codigo], CAT)
        self.assertEqual(C3.ida_y_vuelta(resultado.politica, [caso], self.adaptador)["fallas"], [])
        mala = copy.deepcopy(resultado.politica)
        mala["politicas_reloj"][0]["clock"]["fixed_offset_minutes"] -= 60
        self.assertTrue(C3.ida_y_vuelta(mala, [caso], self.adaptador)["fallas"])



# Las tres celdas de la fila 1399 de catalogo_pixeles.parquet de ERA5L (49,9° S), con sus valores tal como están
# guardados; el centro (5039262) es la estación de prueba de C3b donde se vio la errata E-1 de la Enmienda 5.
_CAT_1399 = pd.DataFrame({
    "pixel_id": np.array([5039261, 5039262, 5039263], dtype=np.int64),
    "lat_index_global": [1399, 1399, 1399], "lon_index_global": [2861, 2862, 2863],
    "latitude": [-49.9, -49.9, -49.9], "longitude": [-73.9, -73.8, -73.7],
    "cell_west": [-73.95, -73.85, -73.75], "cell_east": [-73.85, -73.75, -73.65],
    "cell_south": [-49.95, -49.95, -49.95], "cell_north": [-49.85, -49.85, -49.85],
    "cod_comuna": [12401, 12401, 12401], "asignacion_comuna": ["centro"] * 3,
    "territorio": ["continental"] * 3, "aoi_id": ["continente"] * 3})


def _catalogo_empate_c3c():
    """Dos filas (49,8° y 49,9° S) × nueve columnas (71,0° a 70,2° O); sin dato en (−49,8; −70,6). El costero
    (−49,9; −70,6) tiene dos interiores a 10-15 km, al oeste y al este, a la misma distancia geométrica; en coma
    flotante el este sale 8·10⁻¹³ km más cerca."""
    filas, validos = [], set()
    for lat in (-49.8, -49.9):
        for j in range(9):
            lon = round(-71.0 + 0.1 * j, 1)
            p = _pid(lat, lon)
            filas.append({"pixel_id": p, "latitude": lat, "longitude": lon, "cell_west": lon - 0.05,
                          "cell_south": lat - 0.05, "cell_east": lon + 0.05, "cell_north": lat + 0.05,
                          "cod_comuna": 12101, "territorio": "continental",
                          "lat_index_global": p // 3600, "lon_index_global": p % 3600})
            if (lat, lon) != (-49.8, -70.6):
                validos.add(p)
    return pd.DataFrame(filas).sort_values("pixel_id").reset_index(drop=True), validos


class PruebasEnmienda5Empate(unittest.TestCase):
    """ERR-1 (errata E-1 de la Enmienda 5) en C3b (lectura C3-6) y C3c (lectura C3-9)."""

    def test_err1_estacion_de_prueba_c3b_empate_este_oeste_menor_pixel_id(self):
        """C3-6: «el píxel válido más cercano al elegido (distinto de él; empate, menor pixel_id)». Para 5039262
        (49,9° S, la unidad que no recuperaba F(0)) el oeste y el este empatan: decide 5039261. El código anterior
        a la errata daba 5039263."""
        elegido = C3.pixel_valido_mas_cercano(_CAT_1399, {5039261, 5039262, 5039263}, 5039262)
        self.assertEqual(elegido, 5039261)

    def test_err1_pareja_c3c_empate_menor_pixel_id(self):
        """C3-9: «Pareja: el interior más cercano (empate, menor pixel_id)». El código anterior a la errata daba el
        interior del este, de pixel_id mayor."""
        cat, validos = _catalogo_empate_c3c()
        costero, oeste, este = _pid(-49.9, -70.6), _pid(-49.9, -70.8), _pid(-49.9, -70.4)
        d = numerico.distancia_km(-49.9, -70.6, np.array([-49.9, -49.9]), np.array([-70.8, -70.4]))
        self.assertTrue(10.0 <= d[0] <= 15.0 and d[0] != d[1] and abs(d[0] - d[1]) < 1e-9)
        self.assertLess(oeste, este)
        parejas = C3.parejas_c3c(cat, validos, {p: 100.0 for p in validos}, _umbrales())
        self.assertIn(costero, parejas)
        self.assertEqual(parejas[costero][0], oeste)
        self.assertAlmostEqual(parejas[costero][1], float(d[0]), places=9)



class _RedConControles(_RedFalsa):
    """_RedFalsa que además trae los controles de red, como orquestacion.ResultadoRed."""

    def __call__(self, *args, **kwargs):
        r = super().__call__(*args, **kwargs)
        r.controles = {
            "A3": {"pais": {"n": 444, "falla": False}, "macrozonas": {"norte_chico": {"n": 444, "mediana_D": -0.329,
                                                                                       "falla": True}},
                   "falla_pais": False, "fallan_macrozonas": ["norte_chico"], "rige": "pais",
                   "fallan_macrozonas_sin_consecuencia": ["norte_chico"]},
            "A5": {"alto": False, "m": float("nan")},
            "calibracion_e3t": {"modos": {"norte_chico": "completo"}, "por_macrozona": {"norte_chico": {"n": 40}},
                                "umbrales": {"min_estacion_anios": 30.0}},
            "A4": {"restringe_e3t": False}}
        return r


class PruebasEnmienda5Controles(unittest.TestCase):
    """Enmienda 5, E5-1 (lecturas C3-8 y C3-17)."""

    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.plan = C3.plan_c3b(CAT, VALIDOS, cls.U)

    def test_e5_1_c3b_a3_solo_en_el_pais_y_controles_en_el_json(self):
        """La red de C3b recibe ``a3_solo_pais=True``; C3b.json guarda A3, A5 y la calibración de E3t."""
        red = _RedConControles(decisiones=lambda vistas: _decisiones_correctas(self.plan))
        r = C3.c3b(Path("/nada/ERA5L"), CAT, VALIDOS, self.U, macrozona_region=MACROZONA_REGION,
                   serie=_SerieAnalitica(COORDS), controles_era5=CONTROLES_OK, evaluar_red=red,
                   tablas_calendario=object(), adaptador=ADAPTADOR)
        self.assertTrue(red.llamadas[0].opciones.a3_solo_pais)
        self.assertTrue(red.llamadas[0].opciones.aplicar_exclusion_costera)
        cr = r.detalle["controles_red"]
        self.assertEqual(set(cr), {"A3", "A5", "calibracion_e3t"})
        self.assertEqual(cr["A3"]["rige"], "pais")
        self.assertEqual(cr["calibracion_e3t"]["modos"], {"norte_chico": "completo"})
        with tempfile.TemporaryDirectory() as tmp:
            C3.escribir_c3([r], Path(tmp))
            escrito = json.loads((Path(tmp) / "C3b.json").read_text(encoding="utf-8"))
        self.assertEqual(escrito["detalle"]["controles_red"]["A3"]["fallan_macrozonas_sin_consecuencia"],
                         ["norte_chico"])
        self.assertIsNone(escrito["detalle"]["controles_red"]["A5"]["m"])          # sin NaN en el JSON
        # Una red que no trae controles (las pruebas que la simulan) deja la clave vacía.
        sin = C3.c3b(Path("/nada/ERA5L"), CAT, VALIDOS, self.U, macrozona_region=MACROZONA_REGION,
                     serie=_SerieAnalitica(COORDS), controles_era5=CONTROLES_OK,
                     evaluar_red=_RedFalsa(decisiones=lambda vistas: _decisiones_correctas(self.plan)),
                     tablas_calendario=object(), adaptador=ADAPTADOR)
        self.assertEqual(sin.detalle["controles_red"], {})

    def test_e5_1_c3c_no_usa_la_opcion(self):
        """C3c no cambia: sus dos redes llevan A3 como en §5.4 y van sin la exclusión costera."""
        z = {p: 100.0 + 10.0 * (p % 13) for p in VALIDOS}
        red = _RedFalsa()
        C3.c3c(Path("/nada/ERA5L"), CAT, VALIDOS, self.U, macrozona_region=MACROZONA_REGION, z_pix=z,
               serie=_SerieAnalitica(COORDS), controles_era5=CONTROLES_OK, evaluar_red=red, tablas_calendario=object(),
               adaptador=ADAPTADOR)
        self.assertEqual(len(red.llamadas), 2)
        for llamada in red.llamadas:
            self.assertFalse(llamada.opciones.a3_solo_pais)
            self.assertFalse(llamada.opciones.aplicar_exclusion_costera)

    def test_e5_lecturas_de_c3(self):
        """E5-1 y la errata E-1 en las lecturas del módulo: C3-6, C3-8, C3-9, C3-17 y ERR-1."""
        doc = " ".join(C3.__doc__.split())
        c3_8 = doc.split("- C3-8 ")[1].split("- C3-9.")[0]
        self.assertIn("[Enmienda 5, E5-1]", c3_8)
        self.assertIn("A3 rige sólo con su resultado en el país", c3_8)
        for lectura in ("- C3-6.", "- C3-9."):
            self.assertIn("con la tolerancia de ERR-1", doc.split(lectura)[1][:400], lectura)
        self.assertIn("- C3-17 [Enmienda 5, E5-1]", doc)
        self.assertIn("- ERR-1 [errata E-1 de la Enmienda 5]", doc)


if __name__ == "__main__":
    unittest.main()
