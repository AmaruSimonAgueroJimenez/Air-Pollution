"""Pruebas de fondo_era5l.py (§2.6, §3 y §4.1): S5 (la parte del fondo), S11, S12 (la parte del fondo) y S13; y las
decisiones delegadas D27 (el píxel de la lluvia de RR06), D28 (la amplitud) y D29 (el operador sobre las
climatologías, con T − Td recortado hora a hora).

Dueño: I7 (ola 2; D27-D29 en la ola 3). Las que llevan «sNN» son la prueba NN de §9 del texto. Correr desde
scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos (``sintetico``), en carpetas temporales: ninguna prueba abre DMC, ERA5L real, la meteorología
SINCA real, NASADEM real ni GHS-POP real. S11 y S12 pasan por el descargador, el adaptador y ``dmc_features`` fijados
(sólo se leen como código, con su huella) con el cliente falso de ``sintetico``; si falta un archivo o cambió de
huella, la prueba se omite con el motivo y no se da por aprobada. Los umbrales son los anclados en M0
(``umbrales.cargar_m0``). La detención de M2a por la alineación es de I20 (``test_orquestacion``). Los casos del
lector que el escritor sintético no fabrica (otro calendario, otra hora en el origen del eje, ``pixel_id`` enmascarado,
z escrito en (longitud, latitud)) cambian una sola variable, en memoria, de un NetCDF de ``sintetico`` (``_conjunto``):
no se escribe ningún otro archivo.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import inspect  # noqa: E402
import math  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import constantes, fondo_era5l, numerico, tipos, umbrales  # noqa: E402
from meteo_combinada import sintetico as S  # noqa: E402

F = fondo_era5l
_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
K = constantes.valor("KELVIN")
G = constantes.valor("GRAVEDAD")
R_SECO = constantes.valor("R_SECO")
EPS, COMP = constantes.valor("Q_ESPECIFICA")
V_10KT = 10 * 1852 / 3600                       # S11: 10 kt en m/s (5,1444…)
# §3: «del 2000-01-01 a su último dato (hoy 2026-09-15 23:00 UTC)»: un ejemplo de la última hora de los manifiestos.
ULTIMA_E5L = np.datetime64("2026-09-15T23", "h")
_U = None


def setUpModule():
    F._netcdf4()        # netCDF4 con su aviso conocido de ABI silenciado, antes de que sintetico lo importe


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


def _h(t) -> np.ndarray:
    """Horas desde 2000-01-01T00Z de unos tiempos datetime64 (UTC ingenuo)."""
    return (np.asarray(t, dtype="datetime64[h]") - np.datetime64("2000-01-01T00", "h")).astype(np.int64)


def _base(T: int, P: int, **cambios) -> dict:
    campos = {"t2m": np.full((T, P), 290.0), "d2m": np.full((T, P), 280.0), "sp": np.full((T, P), 95000.0),
              "u10": np.full((T, P), 1.0), "v10": np.full((T, P), -1.0), "tp": np.zeros((T, P))}
    campos.update(cambios)
    return campos


def _mes(carpeta, nombre, campos, tiempos, cat, **kw):
    ruta = S.mes_era5_netcdf(Path(carpeta) / nombre, campos, tiempos, cat.pixel_id, **kw)
    return F.leer_mes(ruta)


def _z_tabla(cat, z) -> pd.DataFrame:
    return pd.DataFrame({"pixel_id": cat.pixel_id.to_numpy(np.int64), "z_e5l": np.asarray(z, dtype=np.float64)})


def _h1(t) -> int:
    """La h (int) de un instante."""
    return int(_h(np.datetime64(t, "h")))


class _Variable:
    """Una variable de un NetCDF de ``sintetico`` como la ve el lector (dimensiones, atributos y valores), para
    cambiarle una sola cosa en memoria, sin escribir otro archivo."""

    def __init__(self, valores, dimensiones, **atributos):
        self._valores = valores
        self.dimensions = tuple(dimensiones)
        for nombre, valor in atributos.items():
            setattr(self, nombre, valor)

    def __getitem__(self, clave):
        return self._valores[clave]


def _conjunto(ruta, nombres, **cambios) -> types.SimpleNamespace:
    """Las variables ``nombres`` de un NetCDF de ``sintetico``, leídas en memoria, con ``cambios`` (nombre →
    ``_Variable``): lo que ``_mes_del_conjunto`` y ``_geopotencial_del_conjunto`` reciben de netCDF4."""
    netCDF4 = F._netcdf4()
    ds = netCDF4.Dataset(str(ruta), mode="r")
    try:
        variables = {n: _Variable(ds.variables[n][:], ds.variables[n].dimensions,
                                  **{a: ds.variables[n].getncattr(a) for a in ds.variables[n].ncattrs()})
                     for n in nombres}
    finally:
        ds.close()
    variables.update(cambios)
    return types.SimpleNamespace(variables=variables)


def _distancia_respaldo(lat, lon, lat_v, lon_v) -> float:
    """La distancia con la misma llamada que ``_respaldo`` (un punto contra un arreglo de candidatos)."""
    return float(numerico.haversine_km(np.float64(lat), np.float64(lon), np.array([lat_v]), np.array([lon_v]))[0])


def _punto_a_distancia_exacta(lat_v, lon_v, d_km, *, intentos=4000):
    """Un punto al sur de (lat_v, lon_v), entre 0,1° y 0,2° de latitud, cuya distancia por haversine (la cuenta de
    ``_respaldo``) da exactamente ``d_km`` en float64; None si no aparece. Se busca en longitudes que avanzan de a
    10⁻⁴° y, en cada una, la latitud por bisección y en los float vecinos."""
    for k in range(intentos):
        lon = lon_v + k * 1e-4
        a, b = lat_v - 0.1, lat_v - 0.2              # a más cerca, b más lejos
        for _ in range(64):
            m = (a + b) / 2
            if _distancia_respaldo(m, lon, lat_v, lon_v) <= d_km:
                a = m
            else:
                b = m
        x = a
        for _ in range(4):
            x = np.nextafter(x, np.inf)
        for _ in range(9):
            if _distancia_respaldo(x, lon, lat_v, lon_v) == d_km:
                return float(x), float(lon)
            x = np.nextafter(x, -np.inf)
    return None


def _verdad_T(la, lo, z, hh, gamma):
    """La T «verdadera» de S5 (°C): lineal en latitud, longitud y altura (con Γ), más un ciclo en la hora."""
    return 20 + 2 * (la + 33) - 3 * (lo + 71) + gamma * z / 1000 + 0.1 * hh


def _verdad_u(la, lo, hh):
    return 2 + 5 * (la + 33) + 7 * (lo + 71) + 0.05 * hh


def _verdad_v(la, lo, hh):
    return -1 - 4 * (la + 33) + 3 * (lo + 71) - 0.02 * hh


def _fondo_independiente(mes, cat, z_pix, lat, lon, z, gamma):
    """Camino propio de §4.1 (bucles y ``math``): bilineal en latitud y longitud sobre la rejilla regular del
    catálogo, Γ, hipsometría con T̄ y conservación de q; sin renormalización (todos los vecinos válidos)."""
    lat_n = cat.latitude.max()
    lon_o = cat.longitude.min()
    a = (lat_n - lat) / 0.1
    b = (lon - lon_o) / 0.1
    a0, b0 = int(math.floor(a + 1e-12)), int(math.floor(b + 1e-12))
    da, db = a - a0, b - b0
    pid = {(round(float(r.latitude), 6), round(float(r.longitude), 6)): int(r.pixel_id) for r in cat.itertuples()}
    col = {int(p): k for k, p in enumerate(mes.pixel_id)}
    vecinos = []
    for (x, y, w) in ((0, 0, (1 - da) * (1 - db)), (0, 1, (1 - da) * db), (1, 0, da * (1 - db)), (1, 1, da * db)):
        if w > 0:
            p = pid[(round(lat_n - 0.1 * (a0 + x), 6), round(lon_o + 0.1 * (b0 + y), 6))]
            vecinos.append((col[p], w, z - z_pix[p]))
    nt = len(mes.tiempos)
    salida = {c: np.zeros(nt) for c in ("T_F", "Td_F", "p_F", "u_F", "v_F")}
    for t in range(nt):
        acum = dict.fromkeys(salida, 0.0)
        suma_w = 0.0
        for c, w, dz in vecinos:
            t2m, d2m, sp = (float(mes.datos[v][t, c]) for v in ("t2m", "d2m", "sp"))
            ti = t2m - K
            tx = ti + gamma * dz / 1000.0
            tmed = (ti + tx) / 2 + K
            px = sp / 100.0 * math.exp(-G * dz / (R_SECO * tmed))
            e = 6.112 * math.exp(17.625 * (d2m - K) / (243.04 + d2m - K))
            q = EPS * e / (sp / 100.0 - COMP * e)
            ex = q * px / (EPS + COMP * q)
            lg = math.log(ex / 6.112)
            tdx = 243.04 * lg / (17.625 - lg)
            acum["T_F"] += w * tx
            acum["Td_F"] += w * tdx
            acum["p_F"] += w * px
            acum["u_F"] += w * float(mes.datos["u10"][t, c])
            acum["v_F"] += w * float(mes.datos["v10"][t, c])
            suma_w += w
        for nombre in salida:
            salida[nombre][t] = acum[nombre] / suma_w
        salida["Td_F"][t] = min(salida["Td_F"][t], salida["T_F"][t])
    return salida


# ---------------------------------------------------------------------------------------------------------------
# S5: fondo exacto
# ---------------------------------------------------------------------------------------------------------------
class PruebasS5(unittest.TestCase):
    """S5, la parte del fondo: con campos lineales en altura el fondo reproduce los valores exactos (bilineal, Γ,
    hipsometría y conservación de q), con estaciones arriba y abajo del píxel, z en metros y QFE con p_std(z_s)."""

    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.gamma = float(cls.U.a("GAMMA_K_KM"))
        cls.cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        a = np.round((-33.0 - cls.cat.latitude.to_numpy()) / 0.1).astype(int)
        b = np.round((cls.cat.longitude.to_numpy() + 71.0) / 0.1).astype(int)
        cls.z_pix = 300.0 + 200.0 * a + 100.0 * b                       # de 300 a 1.000 m
        cls.z_map = {int(p): float(z) for p, z in zip(cls.cat.pixel_id, cls.z_pix)}
        cls.t = S.horas_del_mes(2019, 9)[:48]
        T, P = len(cls.t), len(cls.cat)
        hora = (_h(cls.t) % 24)[:, None]
        lat = cls.cat.latitude.to_numpy()[None, :]
        lon = cls.cat.longitude.to_numpy()[None, :]
        campos = {"t2m": _verdad_T(lat, lon, cls.z_pix[None, :], hora, cls.gamma) + K,
                  "d2m": _verdad_T(lat, lon, cls.z_pix[None, :], hora, cls.gamma) + K - 8.0 - 0.5 * (lon + 71),
                  "sp": numerico.p_std(cls.z_pix)[None, :] * 100.0 + 300.0 * np.sin(hora / 4.0) + 0 * lat,
                  "u10": _verdad_u(lat, lon, hora), "v10": _verdad_v(lat, lon, hora), "tp": np.zeros((T, P))}
        cls.tmp = tempfile.TemporaryDirectory()
        cls.mes = _mes(cls.tmp.name, "lineal.nc", campos, cls.t, cls.cat)
        cls.hora = hora[:, 0]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _fondo(self, lat, lon, z):
        op = F.operador(lat, lon, z, self.cat, self.cat.pixel_id, _z_tabla(self.cat, self.z_pix), self.U)
        return op, F.campos_fondo(self.mes, op, self.U)

    def test_s05_fondo_exacto_con_campos_lineales(self):
        """Bilineal, Γ, hipsometría y conservación de q reproducen el valor exacto; en los centros de los píxeles,
        con z = z_E5L, el fondo es ERA5-Land tal cual (bit a bit)."""
        lat = np.array([-33.03, -33.17, -33.12, -33.05])
        lon = np.array([-70.94, -70.76, -70.83, -70.71])
        z = np.array([250.0, 1500.0, 700.0, 3000.0])
        op, fondo = self._fondo(lat, lon, z)
        self.assertTrue((np.asarray(op.pix) >= 0).all())
        # Campos lineales: el valor exacto (salvo el float32 del archivo).
        esperado_T = _verdad_T(lat[None, :], lon[None, :], z[None, :], self.hora[:, None], self.gamma)
        np.testing.assert_allclose(fondo["T_F"], esperado_T, atol=1e-4)
        np.testing.assert_allclose(fondo["u_F"], _verdad_u(lat[None, :], lon[None, :], self.hora[:, None]), atol=1e-5)
        np.testing.assert_allclose(fondo["v_F"], _verdad_v(lat[None, :], lon[None, :], self.hora[:, None]), atol=1e-5)
        # Hipsometría y q: el camino propio, desde los mismos float32 del archivo.
        for k in range(len(lat)):
            propio = _fondo_independiente(self.mes, self.cat, self.z_map, lat[k], lon[k], z[k], self.gamma)
            for c in ("T_F", "Td_F", "p_F", "u_F", "v_F"):
                np.testing.assert_allclose(fondo[c][:, k], propio[c], rtol=1e-11, atol=1e-9, err_msg=c)
        # En los centros, con z = z_E5L: ERA5-Land tal cual.
        op, centro = self._fondo(self.cat.latitude.to_numpy(), self.cat.longitude.to_numpy(), self.z_pix)
        self.assertTrue((np.asarray(op.pix)[:, 1:] == -1).all())
        self.assertTrue((np.asarray(op.w)[:, 0] == 1.0).all())
        datos = {v: self.mes.datos[v].astype(np.float64) for v in ("t2m", "d2m", "sp", "u10", "v10")}
        self.assertTrue(np.array_equal(centro["T_F"], datos["t2m"] - K))
        self.assertTrue(np.array_equal(centro["p_F"], datos["sp"] / 100.0))
        self.assertTrue(np.array_equal(centro["Td_F"], np.minimum(datos["d2m"] - K, datos["t2m"] - K)))
        self.assertTrue(np.array_equal(centro["u_F"], datos["u10"]))
        self.assertTrue(np.array_equal(centro["v_F"], datos["v10"]))
        self.assertFalse(centro["renormalizada"].any())
        # El operador de los píxeles (por pixel_id, A10) da lo mismo, bit a bit.
        pid = self.cat.pixel_id.to_numpy(np.int64)
        op_pix = F.operador_pixeles(pid, self.cat, pid, _z_tabla(self.cat, self.z_pix))
        for campo in ("pix", "w", "dz", "respaldo"):
            np.testing.assert_array_equal(getattr(op_pix, campo), getattr(op, campo), err_msg=campo)
        en_pixeles = F.campos_fondo(self.mes, op_pix, self.U)
        for c in (*F.CAMPOS_F, "renormalizada"):
            self.assertTrue(np.array_equal(en_pixeles[c], centro[c]), c)

    def test_s05_estaciones_arriba_y_abajo_del_pixel(self):
        """En el centro de un píxel, con z_s arriba y abajo de z_E5L (en metros): T cambia en Γ·Δz exacto, p sigue la
        hipsometría con T̄, q se conserva (Td baja ≈ 1,8 K/km) y Td_F ≤ T_F."""
        p = 5
        lat0, lon0, zp = float(self.cat.latitude[p]), float(self.cat.longitude[p]), float(self.z_pix[p])
        dz = np.array([-1000.0, -250.0, 0.0, 250.0, 1000.0])
        op, fondo = self._fondo(np.full(5, lat0), np.full(5, lon0), zp + dz)
        np.testing.assert_array_equal(np.asarray(op.dz)[:, 0], dz)                 # z en metros, z_x − z_i
        t_i = self.mes.datos["t2m"][:, p].astype(np.float64) - K
        for k in range(5):
            np.testing.assert_allclose(fondo["T_F"][:, k] - t_i, self.gamma * dz[k] / 1000, atol=1e-12)
        np.testing.assert_allclose(fondo["T_F"][:, 4] - fondo["T_F"][:, 2], -6.5, atol=1e-9)
        np.testing.assert_allclose(fondo["T_F"][:, 0] - fondo["T_F"][:, 2], 6.5, atol=1e-9)
        self.assertTrue((np.diff(fondo["p_F"], axis=1) < 0).all())                  # más arriba, menos presión
        sp = self.mes.datos["sp"][:, p].astype(np.float64) / 100.0
        for k in range(5):
            t_media = (t_i + fondo["T_F"][:, k]) / 2 + K
            np.testing.assert_allclose(fondo["p_F"][:, k], sp * np.exp(-G * dz[k] / (R_SECO * t_media)), rtol=1e-14)
        e_i = numerico.magnus_agua(self.mes.datos["d2m"][:, p].astype(np.float64) - K)
        q_i = EPS * e_i / (sp - COMP * e_i)
        for k in range(5):
            e_x = numerico.magnus_agua(fondo["Td_F"][:, k])
            q_x = EPS * e_x / (fondo["p_F"][:, k] - COMP * e_x)
            np.testing.assert_allclose(q_x, q_i, rtol=1e-12)
        caida = (fondo["Td_F"][:, 2] - fondo["Td_F"][:, 4])            # por km hacia arriba
        self.assertTrue(((caida > 1.4) & (caida < 2.2)).all(), caida[:3])
        self.assertTrue((fondo["Td_F"] <= fondo["T_F"]).all())
        # Un punto entre cuatro píxeles, arriba de todos y abajo de todos: Γ sobre la z del punto.
        op, f2 = self._fondo(np.array([-33.07, -33.07]), np.array([-70.86, -70.86]), np.array([0.0, 4000.0]))
        np.testing.assert_allclose(f2["T_F"][:, 1] - f2["T_F"][:, 0], self.gamma * 4.0, atol=1e-9)
        self.assertTrue((np.asarray(op.dz)[0] > 0).sum() == 0 and (np.asarray(op.dz)[1] > 0).all())

    def test_s05_regla_de_qfe_con_p_std_de_z_s(self):
        """QFE se compara con el fondo llevado a la misma z_s (en metros) con que se escribe la regla de QFE,
        p_std(z_s) − 80 ≤ QFE ≤ p_std(z_s) + 50 (§2.3): con un barómetro perfecto (QFE = p_F) la hora cae dentro de
        la regla y r_p = ln(QFE/p_F) = 0, también arriba y abajo de los píxeles; si z_s se diera en km, la estación de
        3.000 m quedaría fuera de la regla."""
        bajo, alto = self.U.a("QQFE_BAJO"), self.U.a("QQFE_ALTO")
        lat = np.array([-33.0, -33.1, -33.04, -33.16, -33.12, -33.08])
        lon = np.array([-71.0, -70.8, -70.93, -70.77, -70.88, -70.74])
        z_s = np.array([0.0, 1500.0, 2200.0, 3000.0, 4000.0, 600.0])
        op, fondo = self._fondo(lat, lon, z_s)
        p_std = numerico.p_std(z_s)[None, :]
        self.assertTrue(((fondo["p_F"] >= p_std + bajo) & (fondo["p_F"] <= p_std + alto)).all())
        qfe = fondo["p_F"].astype(np.float32).astype(np.float64)
        nan = np.full(qfe.shape, np.nan)
        r = F.residuos({"T": nan, "Td": nan, "u": nan, "v": nan, "QFE": qfe}, fondo)
        self.assertTrue(np.array_equal(r["r_p"], np.zeros(qfe.shape)))
        self.assertTrue(np.isnan(r["r_T"]).all())
        _, en_km = self._fondo(lat[3:4], lon[3:4], z_s[3:4] / 1000.0)
        self.assertTrue((en_km["p_F"][:, 0] > numerico.p_std(z_s[3]) + alto).all())


# ---------------------------------------------------------------------------------------------------------------
# S11 y S12: por el descargador, el adaptador y cargar_dmc fijados
# ---------------------------------------------------------------------------------------------------------------
def _codigo_fijado(prueba_o_clase):
    """El descargador, el adaptador y dmc_features (por ruta y huella); SkipTest si falta alguno."""
    from meteo_combinada import fijados
    for ruta, sha in ((_AP / fijados.RUTA_DESCARGADOR, fijados.SHA_DESCARGADOR),
                      (_AP / fijados.RUTA_ADAPTADOR, fijados.SHA_ADAPTADOR),
                      (_AP / fijados.RUTA_DMC_FEATURES, fijados.SHA_DMC_FEATURES)):
        if not ruta.is_file() or hashlib.sha256(ruta.read_bytes()).hexdigest() != sha:
            raise unittest.SkipTest(f"{ruta.name} falta o cambió de huella; la prueba no se da por aprobada")
    return fijados.cargar_descargador(_AP), fijados.cargar_adaptador(_AP), fijados.cargar_dmc_features(_AP)


def _politica(codigo: str, minutos: int, lat: float, lon: float, variables) -> dict:
    """Una política de lectura mínima (§2.5) con reloj F(c): mediciones instantáneas y calidad documentada."""
    desde, hasta = "2019-09-01T00:00:00", "2019-09-30T23:00:00"
    base = {"verified": True, "source": "prueba sintetica", "valid_from": desde, "valid_to": hasta}
    rangos = {"Ts": ("degC", -39.0, 50.0), "wind_speed_instant": ("m/s", 0.0, 50.0),
              "wind_direction_instant": ("degree", 0, 360)}
    calidad = {v: {**base, "unit": rangos[v][0], "method": "documented_numeric_checks", "accepted_source_codes": [],
                   "allow_unknown_source_qc": True, "minimum": rangos[v][1], "maximum": rangos[v][2]}
               for v in variables}
    return {"station_code": codigo, "valid_from": desde, "valid_to": hasta,
            "clock": {**base, "timestamp_semantics": "instantaneous", "fixed_offset_minutes": int(minutos)},
            "coordinates": {**base, "latitude": lat, "longitude": lon},
            "measurements": {v: {**base, "statistic": "instantaneous", "interval_minutes": 0} for v in variables},
            "quality": calidad}


def _serie(larga: pd.DataFrame, variable: str) -> tuple[np.ndarray, np.ndarray]:
    """(h UTC, valor) de las filas usables de una variable de la tabla larga de cargar_dmc, en orden de h."""
    filas = larga[(larga.variable == variable) & larga.usable.astype(bool)]
    utc = pd.DatetimeIndex(filas.timestamp_utc).tz_convert("UTC").tz_localize(None)
    h = _h(utc.to_numpy().astype("datetime64[h]"))
    orden = np.argsort(h)
    return h[orden], filas.value.to_numpy(np.float64)[orden]


def _fondo_estacion(mes, cat, lat, lon, z, U):
    op = F.operador([lat], [lon], [z], cat, cat.pixel_id, _z_tabla(cat, np.full(len(cat), z)), U)
    fondo = F.campos_fondo(mes, op, U)
    return F.tabla_puntos(mes.tiempos, {c: fondo[c][:, 0] for c in F.CAMPOS_F})


_DIRECCIONES = (270.0, 360.0, 90.0, 180.0)
# «Hacia» de ERA5-Land para el viento que viene de cada dirección DMC: (u10, v10) en unidades de la rapidez.
_HACIA = {270.0: (1.0, 0.0), 360.0: (0.0, -1.0), 90.0: (-1.0, 0.0), 180.0: (0.0, 1.0)}


class PruebasS11(unittest.TestCase):
    """S11: viento y signo, por el adaptador real (DD y FF en nudos de la hoja DMC sintética)."""

    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        descargador, cls.adaptador, cls.dmc = _codigo_fijado(cls)
        cls.cat = S.catalogo_pixeles(-33.0, -71.0, 3, 3)
        cls.lat, cls.lon, cls.z = -33.1, -70.9, 520.0
        u = np.arange(np.datetime64("2019-09-02T00"), np.datetime64("2019-09-06T00"), np.timedelta64(1, "h"))
        dd = np.array([_DIRECCIONES[k % 4] for k in range(len(u))])
        cls.dd = dd
        est = S.estacion_sintetica("900011", cls.lat, cls.lon, cls.z, u.astype("datetime64[ns]"),
                                   Ts=np.full(len(u), 15.0), wind_direction_instant=dd,
                                   wind_speed_instant=np.full(len(u), 10.0))
        cls.tmp = tempfile.TemporaryDirectory()
        dmc = S.fabricar_descarga([est], Path(cls.tmp.name) / "dmc", descargador, "2019-09-01", "2019-09-30")
        (manifiesto,) = S.manifiestos_de(dmc)["900011"]
        politica = _politica("900011", 0, cls.lat, cls.lon, ("Ts", "wind_speed_instant", "wind_direction_instant"))
        cls.larga, _ = cls.dmc.cargar_dmc([manifiesto], [politica], adapter_sha256=S.SHA_ADAPTADOR)
        cls.h_u, cls.wind_u = _serie(cls.larga, "wind_u")
        cls.h_v, cls.wind_v = _serie(cls.larga, "wind_v")
        # ERA5-Land con el mismo viento, en la convención «hacia».
        t = S.horas_del_mes(2019, 9)
        ht = _h(t)
        u10, v10 = np.zeros(len(t)), np.zeros(len(t))
        pos = np.searchsorted(ht, _h(u))
        for k, d in enumerate(dd):
            u10[pos[k]], v10[pos[k]] = V_10KT * _HACIA[d][0], V_10KT * _HACIA[d][1]
        P = len(cls.cat)
        campos = _base(len(t), P, u10=np.repeat(u10[:, None], P, axis=1), v10=np.repeat(v10[:, None], P, axis=1))
        cls.mes = _mes(cls.tmp.name, "viento.nc", campos, t, cls.cat)
        cls.fondo = _fondo_estacion(cls.mes, cls.cat, cls.lat, cls.lon, cls.z, cls.U)
        cls.horas = _h(u)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_s11_dd_270_con_10_kt_da_u_mas_5_144(self):
        """DD 270 con 10 kt → u = +5,144 m/s y v ≈ 0, por el adaptador real."""
        self.assertTrue(np.array_equal(self.h_u, self.horas) and np.array_equal(self.h_v, self.horas))
        oeste = self.dd == 270.0
        self.assertTrue(oeste.any())
        np.testing.assert_allclose(self.wind_u[oeste], V_10KT, rtol=0, atol=1e-12)
        self.assertEqual(round(float(self.wind_u[oeste][0]), 3), 5.144)
        self.assertTrue((np.abs(self.wind_v[oeste]) < 1e-9).all())

    def test_s11_dd_360_da_v_negativo(self):
        """DD 360 → v < 0 (viento del norte: hacia el sur), u ≈ 0."""
        norte = self.dd == 360.0
        self.assertTrue(norte.any())
        self.assertTrue((self.wind_v[norte] < 0).all())
        np.testing.assert_allclose(self.wind_v[norte], -V_10KT, atol=1e-12)
        self.assertTrue((np.abs(self.wind_u[norte]) < 1e-9).all())

    def test_s11_desde_y_hacia_dan_residuo_cero(self):
        """La DMC «desde» (el adaptador da u = −vel·sen(dd)) y la ERA5-Land «hacia» dan residuo 0 con el mismo
        viento; si ERA5-Land se leyera con la convención «desde», el residuo sería el doble del viento."""
        f = F.en_horas(self.fondo, self.horas)
        nan = np.full(len(self.horas), np.nan)
        r = F.residuos({"T": nan, "Td": nan, "u": self.wind_u, "v": self.wind_v, "QFE": nan}, f)
        self.assertLess(float(np.max(np.abs(r["r_u"]))), 1e-6)
        self.assertLess(float(np.max(np.abs(r["r_v"]))), 1e-6)
        al_reves = {**f, "u_F": -f["u_F"], "v_F": -f["v_F"]}
        r2 = F.residuos({"T": nan, "Td": nan, "u": self.wind_u, "v": self.wind_v, "QFE": nan}, al_reves)
        np.testing.assert_allclose(np.hypot(r2["r_u"], r2["r_v"]), 2 * V_10KT, rtol=1e-6)


class PruebasS12(unittest.TestCase):
    """S12, la parte del fondo: ERA5-Land con un ciclo diario marcado y etiquetas DMC fabricadas por un camino propio
    (L = u + c, como RELOJ §8) con reglas −240 y −180 dan residuo 0; un error de ±1 h, no; una hora que no es HH:00
    se rechaza."""

    def test_s12_ciclo_diario_y_reglas_menos240_y_menos180_dan_residuo_cero(self):
        U = _umbrales()
        descargador, _, dmc_features = _codigo_fijado(self)
        cat = S.catalogo_pixeles(-33.0, -71.0, 3, 3)
        lat, lon, z = -33.1, -70.9, 520.0
        t = S.horas_del_mes(2019, 9)
        ht = _h(t)
        verdad = np.round(12.0 + 8.0 * np.sin(2 * np.pi * ((ht % 24) - 9) / 24) + 0.3 * ((ht // 24) % 7), 1)
        P = len(cat)
        campos = _base(len(t), P, t2m=np.repeat((verdad + K)[:, None], P, axis=1),
                       d2m=np.repeat((verdad + K - 6.0)[:, None], P, axis=1))
        u = np.arange(np.datetime64("2019-09-02T00"), np.datetime64("2019-09-08T00"), np.timedelta64(1, "h"))
        hu = _h(u)
        Ts = verdad[np.searchsorted(ht, hu)]
        relojes = {"900021": -240, "900022": -180}
        estaciones = [S.estacion_sintetica(c, lat, lon, z, S.etiquetas_desde_utc(u.astype("datetime64[ns]"), m),
                                           Ts=Ts) for c, m in relojes.items()]
        with tempfile.TemporaryDirectory() as tmp:
            mes = _mes(tmp, "ciclo.nc", campos, t, cat)
            fondo = _fondo_estacion(mes, cat, lat, lon, z, U)
            dmc = S.fabricar_descarga(estaciones, Path(tmp) / "dmc", descargador, "2019-09-01", "2019-09-30")
            manifiestos = S.manifiestos_de(dmc)
            for codigo, minutos in relojes.items():
                (manifiesto,) = manifiestos[codigo]
                for error_h in (0, -1, 1):
                    with self.subTest(codigo=codigo, reloj=minutos, error_h=error_h):
                        politica = _politica(codigo, minutos + 60 * error_h, lat, lon, ("Ts",))
                        larga, _ = dmc_features.cargar_dmc([manifiesto], [politica], adapter_sha256=S.SHA_ADAPTADOR)
                        h_obs, ts = _serie(larga, "Ts")
                        self.assertEqual(len(h_obs), len(hu))
                        nan = np.full(len(h_obs), np.nan)
                        r = F.residuos({"T": ts, "Td": nan, "u": nan, "v": nan, "QFE": nan},
                                       F.en_horas(fondo, h_obs))
                        if error_h == 0:
                            self.assertTrue(np.array_equal(h_obs, hu))
                            self.assertLess(float(np.max(np.abs(r["r_T"]))), 1e-3)
                        else:
                            self.assertTrue(np.array_equal(h_obs, hu - error_h))
                            self.assertGreater(float(np.mean(np.abs(r["r_T"]))), 0.5)
                            self.assertGreater(float(np.max(np.abs(r["r_T"]))), 1.5)

    def test_s12_hora_que_no_es_hh00_se_rechaza(self):
        """El lector propio rechaza una hora que no es HH:00 (``MesNativo.indice_tiempo`` la redondearía hacia
        abajo), una hora repetida y horas de dos meses."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        casos = {"no_hh00": np.array(["2019-01-01T00:00", "2019-01-01T01:30"], dtype="datetime64[s]"),
                 "repetida": np.array(["2019-01-01T00:00", "2019-01-01T00:00"], dtype="datetime64[s]"),
                 "dos_meses": np.array(["2019-01-31T23:00", "2019-02-01T00:00"], dtype="datetime64[s]")}
        with tempfile.TemporaryDirectory() as tmp:
            for nombre, tiempos in casos.items():
                with self.subTest(caso=nombre):
                    ruta = S.mes_era5_netcdf(Path(tmp) / f"{nombre}.nc", _base(2, 2), tiempos, cat.pixel_id)
                    with self.assertRaises(F.ErrorFondo) as ctx:
                        F.leer_mes(ruta)
                    if nombre == "no_hh00":
                        self.assertIn("HH:00", str(ctx.exception))
            bueno = S.mes_era5_netcdf(Path(tmp) / "bueno.nc", _base(2, 2),
                                      np.array(["2019-01-01T00:00", "2019-01-01T01:00"], dtype="datetime64[s]"),
                                      cat.pixel_id)
            mes = F.leer_mes(bueno)
            self.assertEqual(list(mes.tiempos), list(_h(np.array(["2019-01-01T00", "2019-01-01T01"],
                                                                 dtype="datetime64[h]"))))
            self.assertEqual(mes.tiempos.dtype, np.int32)
            self.assertFalse(mes.completo_hasta(_h1(ULTIMA_E5L)))


# ---------------------------------------------------------------------------------------------------------------
# S13: unidades de ERA5-Land, lluvia y geopotencial
# ---------------------------------------------------------------------------------------------------------------
class PruebasS13(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.cat = S.catalogo_pixeles(-33.0, -71.0, 2, 2)
        cls.tmp = tempfile.TemporaryDirectory()
        # Un acumulado tp continuo de enero a marzo (como ERA5-Land: el de las 00 UTC del día 1 es el paso 24 del
        # día anterior, que está en el mes anterior), partido después en sus tres archivos mensuales.
        t_todo = np.concatenate([S.horas_del_mes(2019, m) for m in (1, 2, 3)])
        ht = _h(t_todo)
        lluvia = np.where(ht % 5 == 0, 0.0004, 0.0) + np.where(ht % 7 == 0, 0.0011, 0.0)
        lluvia = np.repeat(lluvia[:, None], len(cls.cat), axis=1) * np.arange(1, len(cls.cat) + 1)[None, :]
        tp = S.tp_acumulado(t_todo, lluvia)
        mes_de = t_todo.astype("datetime64[M]").astype(int) % 12 + 1
        cls.lluvia, cls.meses = {}, {}
        for mes in (1, 2, 3):
            k = mes_de == mes
            cls.lluvia[mes] = lluvia[k]
            cls.meses[mes] = _mes(cls.tmp.name, f"2019{mes:02d}.nc", _base(int(k.sum()), len(cls.cat), tp=tp[k]),
                                  t_todo[k], cls.cat)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _malo(self, unidades):
        t = S.horas_del_mes(2019, 4)[:24]
        return _mes(self.tmp.name, f"{unidades}.nc", _base(24, len(self.cat)), t, self.cat, unidades=unidades)

    def test_s13_t2m_en_celsius_aborta(self):
        """t2m en °C (el atributo sigue diciendo K): la mediana cae fuera de [200, 330] K y se aborta."""
        F.comprobar_unidades(self._malo("nativas"), self.U)
        with self.assertRaises(F.ErrorUnidades) as ctx:
            F.comprobar_unidades(self._malo("t2m_celsius"), self.U)
        self.assertIn("t2m", str(ctx.exception))
        self.assertTrue(issubclass(F.ErrorUnidades, RuntimeError) and not issubclass(F.ErrorUnidades, ValueError))

    def test_s13_sp_en_hpa_aborta(self):
        """sp en hPa: fuera de [40.000, 110.000] Pa; u10 o v10 de mediana ≥ 30 m/s, también."""
        with self.assertRaises(F.ErrorUnidades) as ctx:
            F.comprobar_unidades(self._malo("sp_hpa"), self.U)
        self.assertIn("sp", str(ctx.exception))
        t = S.horas_del_mes(2019, 4)[:24]
        mes = _mes(self.tmp.name, "viento_malo.nc", _base(24, len(self.cat), u10=np.full((24, 4), 30.0)), t, self.cat)
        with self.assertRaises(F.ErrorUnidades):
            F.comprobar_unidades(mes, self.U)

    def test_s13_d2m_v10_y_los_bordes_de_los_rangos(self):
        """§4.1: «mediana de t2m y d2m en [200, 330] K, de sp en [40.000, 110.000] Pa y |mediana| de u10 y v10
        < 30 m/s». d2m en °C y v10 de ±30 m/s abortan, cada uno con su nombre; las medianas en 200, 330, 40.000 y
        110.000 pasan (bordes incluidos), y apenas fuera, no."""
        t = S.horas_del_mes(2019, 4)[:24]
        P = len(self.cat)

        def mes(nombre, **campos):
            return _mes(self.tmp.name, f"{nombre}.nc", _base(24, P, **{v: np.full((24, P), x) for v, x in
                                                                       campos.items()}), t, self.cat)

        malos = {"d2m_celsius": ({"d2m": 280.0 - K}, "d2m"), "v10_30": ({"v10": 30.0}, "v10"),
                 "v10_menos_30": ({"v10": -30.0}, "v10"), "t2m_sobre_330": ({"t2m": 330.01}, "t2m"),
                 "d2m_bajo_200": ({"d2m": 199.99}, "d2m"), "sp_bajo": ({"sp": 39999.0}, "sp"),
                 "sp_alto": ({"sp": 110001.0}, "sp")}
        for nombre, (campos, variable) in malos.items():
            with self.subTest(caso=nombre):
                with self.assertRaises(F.ErrorUnidades) as ctx:
                    F.comprobar_unidades(mes(nombre, **campos), self.U)
                self.assertEqual(str(ctx.exception).split(" en ")[-1], f"['{variable}']")
        buenos = {"bordes_bajos": {"t2m": 200.0, "d2m": 200.0, "sp": 40000.0, "u10": -29.99, "v10": 29.99},
                  "bordes_altos": {"t2m": 330.0, "d2m": 330.0, "sp": 110000.0, "u10": 29.99, "v10": -29.99}}
        for nombre, campos in buenos.items():
            with self.subTest(caso=nombre):
                F.comprobar_unidades(mes(nombre, **campos), self.U)

    def test_s13_tp_de_m_a_mm(self):
        """La lluvia horaria del acumulado tp (m, desde las 00 UTC) sale en mm."""
        mm = F.incrementos_tp([self.meses[1]])
        esperado = self.lluvia[1] * 1000.0
        self.assertTrue(np.isnan(mm[0]).all())                      # 00 UTC del 1 de enero: sin la hora previa
        np.testing.assert_allclose(mm[1:], esperado[1:], atol=1e-4)
        self.assertGreater(float(np.nanmax(mm)), 1.0)               # en mm, no en m

    def test_s13_primer_incremento_nan_solo_y_no_con_meses_contiguos(self):
        """Serie continua (§2.6): el primer incremento de febrero es NaN si se lee solo, y no con enero; con un mes
        de por medio que falta (enero y marzo), el primero de marzo vuelve a ser NaN."""
        solo = F.incrementos_tp([self.meses[2]])
        self.assertTrue(np.isnan(solo[0]).all())
        np.testing.assert_allclose(solo[1:], self.lluvia[2][1:] * 1000.0, atol=1e-4)
        juntos = F.incrementos_tp([self.meses[1], self.meses[2]])
        n1 = len(self.meses[1].tiempos)
        self.assertTrue(np.isfinite(juntos[n1]).all())
        np.testing.assert_allclose(juntos[n1:], self.lluvia[2] * 1000.0, atol=1e-4)
        np.testing.assert_array_equal(F.horas_de([self.meses[1], self.meses[2]])[n1:], self.meses[2].tiempos)
        salteado = F.incrementos_tp([self.meses[1], self.meses[3]])
        self.assertTrue(np.isnan(salteado[n1]).all())
        with self.assertRaises(F.ErrorFondo):
            F.incrementos_tp([self.meses[2], self.meses[1]])

    def test_s13_acumulado_que_baja_da_cero_y_meses_con_los_mismos_pixeles(self):
        """Como ``meteo_civil_v3.lluvia_horaria`` (§2.6, FON-11), el incremento se recorta en 0: un acumulado que baja
        un poco dentro del día da 0, no un negativo. Los meses de la serie continua traen los mismos píxeles en el
        mismo orden; si no, ``ErrorFondo``."""
        t = S.horas_del_mes(2019, 4)[:6]                          # 00 a 05 UTC del 1 de abril
        P = len(self.cat)
        tp = np.repeat(np.array([0.0005, 0.001, 0.002, 0.002, 0.003, 0.004])[:, None], P, axis=1)
        tp[:, 0] = [0.0005, 0.001, 0.002, 0.0019, 0.003, 0.003]   # baja a las 03 UTC y se queda a las 05 UTC
        mm = F.incrementos_tp([_mes(self.tmp.name, "baja.nc", _base(6, P, tp=tp), t, self.cat)])
        self.assertTrue(np.isnan(mm[0]).all())
        self.assertEqual(float(mm[3, 0]), 0.0)
        self.assertEqual(float(mm[5, 0]), 0.0)
        self.assertTrue((mm[1:] >= 0).all())
        np.testing.assert_allclose(mm[1:, 0], [1.0, 1.0, 0.0, 1.1, 0.0], atol=1e-4)
        np.testing.assert_allclose(mm[1:, 1], [1.0, 1.0, 0.0, 1.0, 1.0], atol=1e-4)
        # Mismos píxeles, otro orden; o el mismo número de píxeles, otros.
        pid = self.cat.pixel_id.to_numpy(np.int64)
        enero, febrero = S.horas_del_mes(2019, 1)[-3:], S.horas_del_mes(2019, 2)[:3]
        primero = F.leer_mes(S.mes_era5_netcdf(Path(self.tmp.name) / "orden_1.nc", _base(3, P), enero, pid))
        for nombre, otros in (("al_reves", pid[::-1]), ("otros", np.r_[pid[:-1], pid[-1] + 1])):
            with self.subTest(caso=nombre):
                segundo = F.leer_mes(S.mes_era5_netcdf(Path(self.tmp.name) / f"orden_{nombre}.nc", _base(3, P),
                                                       febrero, otros))
                with self.assertRaises(F.ErrorFondo):
                    F.incrementos_tp([primero, segundo])
        igual = F.leer_mes(S.mes_era5_netcdf(Path(self.tmp.name) / "orden_igual.nc", _base(3, P), febrero, pid))
        self.assertEqual(F.incrementos_tp([primero, igual]).shape, (6, P))

    def test_s13_ventanas_rr06_que_cruzan_un_mes(self):
        """RR06 rotulado a las 02 UTC del 1 de febrero suma 21-02 UTC: con sólo febrero falta enero (NaN); con el
        mes anterior, da la suma de las 6 horas."""
        h_fin = np.array([_h(np.datetime64("2019-02-01T02"))[()], _h(np.datetime64("2019-02-10T12"))[()]])
        solo = F.sumas_rr06(F.incrementos_tp([self.meses[2]]), h_fin, h=F.horas_de([self.meses[2]]))
        self.assertTrue(np.isnan(solo[0]).all())
        meses = [self.meses[1], self.meses[2]]
        juntos = F.sumas_rr06(F.incrementos_tp(meses), h_fin, h=F.horas_de(meses))
        h_todo = np.concatenate([_h(S.horas_del_mes(2019, 1)), _h(S.horas_del_mes(2019, 2))])
        lluvia = np.concatenate([self.lluvia[1], self.lluvia[2]]) * 1000.0
        for k, fin in enumerate(h_fin):
            ventana = (h_todo > fin - 6) & (h_todo <= fin)
            self.assertEqual(int(ventana.sum()), 6)
            np.testing.assert_allclose(juntos[k], lluvia[ventana].sum(axis=0), atol=1e-4)
        np.testing.assert_allclose(solo[1], juntos[1], atol=0)

    def test_s13_geopotencial_corrido_un_pixel_no_alinea(self):
        """z_E5L desde el NetCDF crudo coincide con el parquet derivado; con la grilla corrida una fila, no
        (MC-38): ``comprobar_alineacion`` lanza ``ErrorAlineacion`` (la detención de M2a es de I20)."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        z = np.linspace(100.0, 1200.0, len(cat))
        nasadem = pd.DataFrame({"pixel_id": cat.pixel_id.to_numpy(np.int64), "z_nasadem": z + 3.0,
                                "frac_nasadem": np.ones(len(cat))})
        sp = pd.Series(numerico.p_std(z), index=cat.pixel_id.to_numpy(np.int64))
        for corrimiento, alinea in ((0, True), (1, False), (-1, False)):
            with self.subTest(corrimiento=corrimiento):
                r = S.geopotencial_sintetico(Path(self.tmp.name) / f"geo{corrimiento}", cat, z,
                                             corrimiento_filas=corrimiento)
                geo = F.leer_geopotencial(r["geopotencial"])
                tabla = F.z_e5l(geo, cat, nasadem, sp, self.U, validos=cat.pixel_id)
                self.assertTrue((tabla.caso == "geopotencial").all())
                parquet = pd.read_parquet(r["altitud"])
                if alinea:
                    F.comprobar_alineacion(tabla, parquet)
                    self.assertTrue(np.array_equal(tabla.z_e5l.to_numpy(), parquet.z_m.to_numpy()))
                else:
                    with self.assertRaises(F.ErrorAlineacion):
                        F.comprobar_alineacion(tabla, parquet)
        with self.assertRaises(F.ErrorAlineacion):
            F.comprobar_alineacion(tabla.iloc[1:], parquet)
        with self.assertRaises(F.ErrorFondo):
            F.leer_geopotencial(r["geopotencial"], sha256="0" * 64)

    def test_s13_alineacion_a_0_001_m_y_nan_como_diferencia(self):
        """MC-38: «|z_E5L − z_parquet| ≤ 0,001 m» en todos los píxeles: 0,0009 m alinea y 0,0011 m (en un solo píxel,
        hacia arriba o hacia abajo) no. FON-5: un NaN cuenta como diferencia, también si está en los dos."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        z = np.linspace(100.0, 1200.0, len(cat))
        r = S.geopotencial_sintetico(Path(self.tmp.name) / "geo_tolerancia", cat, z)
        tabla = F.z_e5l(F.leer_geopotencial(r["geopotencial"]), cat,
                        pd.DataFrame({"pixel_id": cat.pixel_id.to_numpy(np.int64), "z_nasadem": z,
                                      "frac_nasadem": np.ones(len(cat))}),
                        pd.Series(numerico.p_std(z), index=cat.pixel_id.to_numpy(np.int64)), self.U,
                        validos=cat.pixel_id)
        parquet = pd.read_parquet(r["altitud"])

        def con(dz=0.0, k=None, nan_z=False, nan_parquet=False):
            p, t = parquet.copy(), tabla.copy()
            filas = slice(None) if k is None else [k]
            p.loc[p.index[filas], "z_m"] = p.z_m.to_numpy()[filas] + dz
            if nan_parquet:
                p.loc[p.index[filas], "z_m"] = np.nan
            if nan_z:
                t.loc[t.index[filas], "z_e5l"] = np.nan
            return t, p

        for dz in (0.0009, -0.0009):
            with self.subTest(dz=dz):
                F.comprobar_alineacion(*con(dz))
        casos = (("mas_0_0011", {"dz": 0.0011}), ("menos_0_0011", {"dz": -0.0011}),
                 ("un_pixel", {"dz": 0.0011, "k": 5}), ("nan_en_los_dos", {"k": 3, "nan_z": True, "nan_parquet": True}),
                 ("nan_en_z", {"k": 3, "nan_z": True}), ("nan_en_parquet", {"k": 3, "nan_parquet": True}))
        for nombre, cambio in casos:
            with self.subTest(caso=nombre):
                with self.assertRaises(F.ErrorAlineacion) as ctx:
                    F.comprobar_alineacion(*con(**cambio))
                n = len(cat) if "k" not in cambio else 1
                self.assertIn(f"en {n} píxeles de {len(cat)}", str(ctx.exception))


# ---------------------------------------------------------------------------------------------------------------
# Operador, píxeles válidos y demás piezas del fondo
# ---------------------------------------------------------------------------------------------------------------
class PruebasFondo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()

    def test_vecino_a_16_km_y_renormalizacion(self):
        """Vecinos sin dato se descartan y se renormaliza (también hora a hora, MC-39); sin ninguno, el centro válido
        más cercano a ≤ 16 km por haversine, con empate por menor pixel_id (MC-60); más lejos, sin fondo. La rejilla
        cruza el meridiano 0, para probar la longitud módulo 360."""
        cat = S.catalogo_pixeles(-33.0, -0.2, 3, 5)                    # lon −0,2 … 0,2; lat −33,0 … −33,2
        pid = {(round(float(r.latitude), 1), round(float(r.longitude), 1)): int(r.pixel_id) for r in cat.itertuples()}
        invalidos = {pid[(-33.1, 0.0)], pid[(-33.0, 0.1)]}
        validos = np.array([p for p in cat.pixel_id if int(p) not in invalidos], dtype=np.int64)
        z = _z_tabla(cat, np.full(len(cat), 100.0))
        lat = np.array([-33.04, -33.1, -33.05, -50.0])
        lon = np.array([0.03, 0.0, -0.05, 0.0])
        op = F.operador(lat, lon, np.full(4, 100.0), cat, validos, z, self.U, ids=np.array(["a", "b", "c", "d"]))
        pix, w = np.asarray(op.pix), np.asarray(op.w)
        # a: entre (−33,0; 0,0), (−33,0; 0,1) [no válido], (−33,1; 0,0) [no válido] y (−33,1; 0,1).
        di, dj = 0.4, 0.3
        bruto = np.array([(1 - di) * (1 - dj), (1 - di) * dj, di * (1 - dj), di * dj])
        usados = np.array([True, False, False, True])
        np.testing.assert_array_equal(pix[0], [pid[(-33.0, 0.0)], -1, -1, pid[(-33.1, 0.1)]])
        np.testing.assert_allclose(w[0], np.where(usados, bruto, 0) / bruto[usados].sum(), atol=1e-12)
        self.assertFalse(op.respaldo[0])
        # b: en el centro de un píxel no válido; los de ±0,1° de longitud están a la misma distancia (9,3 km):
        # gana el menor pixel_id (el de 0,1°, j = 1, frente al de −0,1°, j = 3.599).
        self.assertTrue(op.respaldo[1])
        self.assertEqual(int(pix[1, 0]), pid[(-33.1, 0.1)])
        self.assertLess(pid[(-33.1, 0.1)], pid[(-33.1, -0.1)])
        self.assertEqual(list(pix[1, 1:]), [-1, -1, -1])
        self.assertEqual(float(w[1, 0]), 1.0)
        # c: cruza el meridiano: (−33,0; −0,1), (−33,0; 0,0), (−33,1; −0,1) y (−33,1; 0,0) [no válido].
        np.testing.assert_array_equal(pix[2, :3], [pid[(-33.0, -0.1)], pid[(-33.0, 0.0)], pid[(-33.1, -0.1)]])
        self.assertEqual(int(pix[2, 3]), -1)
        np.testing.assert_allclose(w[2, :3], [1 / 3, 1 / 3, 1 / 3], atol=1e-12)
        # d: lejos de todo: sin fondo.
        self.assertTrue((pix[3] == -1).all() and not op.respaldo[3])
        tabla = F.columnas_operador(op)
        self.assertEqual(list(tabla.columns), ["id", *F.COLUMNAS_OPERADOR])
        self.assertEqual(list(tabla.sin_fondo), [False, False, False, True])
        self.assertEqual(list(tabla.respaldo_16km), [False, True, False, False])
        rehecho = F.operador_desde_columnas(op.ids, op.z, tabla, z)
        for campo in ("pix", "w", "dz", "respaldo"):
            np.testing.assert_array_equal(getattr(rehecho, campo), getattr(op, campo))
        # Un píxel válido a más de 16 km no sirve de respaldo.
        solo_lejos = np.array([pid[(-33.1, 0.2)]], dtype=np.int64)          # a 18,7 km de (−33,1; 0,0)
        op2 = F.operador([-33.1], [0.0], [100.0], cat, solo_lejos, z, self.U)
        self.assertTrue((np.asarray(op2.pix) == -1).all())
        # Hora a hora: un vecino válido sin dato en una hora se descarta en esa hora y se marca.
        t = S.horas_del_mes(2019, 9)[:6]
        P = len(cat)
        t2m = np.full((6, P), 290.0) + np.arange(P)[None, :]
        u10 = np.full((6, P), 1.0) + 0.5 * np.arange(P)[None, :] + 0.01 * np.arange(6)[:, None]
        v10 = np.full((6, P), -2.0) + 0.25 * np.arange(P)[None, :] - 0.02 * np.arange(6)[:, None]
        col = {int(p): k for k, p in enumerate(cat.pixel_id)}
        t2m[2, col[pid[(-33.1, 0.1)]]] = np.nan
        with tempfile.TemporaryDirectory() as tmp:
            mes = _mes(tmp, "hueco.nc", _base(6, P, t2m=t2m, u10=u10, v10=v10), t, cat)
        fondo = F.campos_fondo(mes, op, self.U)
        datos = mes.datos["t2m"].astype(np.float64) - K
        c0, c3 = col[pid[(-33.0, 0.0)]], col[pid[(-33.1, 0.1)]]
        a0, a3 = datos[:, c0], datos[:, c3]
        esperado = (w[0, 0] * a0 + w[0, 3] * a3) / (w[0, 0] + w[0, 3])
        np.testing.assert_allclose(np.delete(fondo["T_F"][:, 0], 2), np.delete(esperado, 2), atol=1e-12)
        self.assertAlmostEqual(float(fondo["T_F"][2, 0]), float(a0[2]), places=12)
        self.assertEqual(list(fondo["renormalizada"][:, 0]), [False, False, True, False, False, False])
        # FON-7: u y v se renormalizan con sus propias entradas (u10, v10), no con t2m: en la hora del hueco de t2m
        # siguen con el bilineal completo, sin perder el vecino.
        for c, var in (("u_F", "u10"), ("v_F", "v10")):
            x = mes.datos[var].astype(np.float64)
            completo = (w[0, 0] * x[:, c0] + w[0, 3] * x[:, c3]) / (w[0, 0] + w[0, 3])
            np.testing.assert_allclose(fondo[c][:, 0], completo, rtol=0, atol=1e-12, err_msg=c)
            self.assertGreater(abs(float(fondo[c][2, 0]) - float(x[2, c0])), 0.1, c)
        self.assertTrue(np.isnan(fondo["T_F"][:, 3]).all() and np.isnan(fondo["u_F"][:, 3]).all())
        self.assertFalse(fondo["renormalizada"][:, 3].any())

    def _columna_con_un_valido(self):
        """Una columna de píxeles en −71,0° (−33,0 … −33,3) con sólo el de −33,0 válido: un punto entre −33,1 y
        −33,2 no tiene vecinos bilineales válidos y busca el respaldo en ese píxel."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 4, 1)
        pid = {round(float(r.latitude), 1): int(r.pixel_id) for r in cat.itertuples()}
        return cat, pid[-33.0], _z_tabla(cat, np.full(len(cat), 100.0))

    def test_respaldo_con_radio_de_16_km_y_no_15(self):
        """§4.1: «el centro válido más cercano a ≤ 16 km» y «Un solo radio, 16 km, para estaciones, celdas y píxeles
        (RELOJ usa 15 km sólo para elegir su píxel)»: un punto con su píxel válido a ≈ 15,5 km tiene respaldo; uno
        apenas por encima de 16 km queda sin fondo."""
        cat, valido, z = self._columna_con_un_valido()
        km_por_grado = math.pi * 6371.0 / 180.0
        lat = np.array([-33.0 - 15.5 / km_por_grado, -33.0 - 16.02 / km_por_grado])
        lon = np.full(2, -71.0)
        d = [_distancia_respaldo(la, lo, -33.0, -71.0) for la, lo in zip(lat, lon)]
        self.assertTrue(15.0 < d[0] < 16.0 < d[1] < 16.05, d)
        op = F.operador(lat, lon, np.full(2, 100.0), cat, [valido], z, self.U)
        self.assertEqual(list(op.respaldo), [True, False])
        self.assertEqual(list(np.asarray(op.pix)[:, 0]), [valido, -1])
        self.assertTrue((np.asarray(op.pix)[:, 1:] == -1).all())
        self.assertEqual(list(F.columnas_operador(op).sin_fondo), [False, True])

    def test_respaldo_a_16_km_exactos_por_haversine(self):
        """El borde se incluye («≤ 16 km», FON-6): un punto cuya distancia por haversine (R = 6.371 km, MC-60) da
        exactamente 16,0 km en float64 tiene respaldo."""
        cat, valido, z = self._columna_con_un_valido()
        punto = _punto_a_distancia_exacta(-33.0, -71.0, 16.0)
        if punto is None:
            self.skipTest("no apareció un punto a 16,0 km exactos en float64; la prueba no se da por aprobada")
        lat, lon = punto
        self.assertEqual(_distancia_respaldo(lat, lon, -33.0, -71.0), 16.0)
        op = F.operador([lat], [lon], [100.0], cat, [valido], z, self.U)
        self.assertTrue(op.respaldo[0])
        self.assertEqual(int(np.asarray(op.pix)[0, 0]), valido)
        # El mismo punto, corrido un float hacia el sur (> 16 km), ya no tiene fondo.
        afuera = float(np.nextafter(np.nextafter(lat, -np.inf), -np.inf))
        self.assertGreater(_distancia_respaldo(afuera, lon, -33.0, -71.0), 16.0)
        self.assertFalse(F.operador([afuera], [lon], [100.0], cat, [valido], z, self.U).respaldo[0])

    def test_lotes_de_puntos_dan_lo_mismo_bit_a_bit(self):
        """El operador y los campos de un punto no dependen de qué otros puntos van en el lote (MC-37, S9): partir
        los puntos en lotes da lo mismo, bit a bit."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        rng = np.random.default_rng(3)
        n = 12
        lat, lon = rng.uniform(-33.2, -33.0, n), rng.uniform(-71.0, -70.7, n)
        z = rng.uniform(0, 3000, n)
        z_pix = _z_tabla(cat, rng.uniform(200, 1500, len(cat)))
        t = S.horas_del_mes(2019, 9)[:24]
        P = len(cat)
        campos = _base(24, P, t2m=rng.normal(290, 3, (24, P)), d2m=rng.normal(280, 3, (24, P)),
                       sp=rng.normal(90000, 500, (24, P)), u10=rng.normal(0, 3, (24, P)), v10=rng.normal(0, 3, (24, P)))
        with tempfile.TemporaryDirectory() as tmp:
            mes = _mes(tmp, "lotes.nc", campos, t, cat)
        todo = F.campos_fondo(mes, F.operador(lat, lon, z, cat, cat.pixel_id, z_pix, self.U), self.U)
        for lote in (slice(0, 5), slice(5, 6), slice(6, n)):
            parte = F.campos_fondo(mes, F.operador(lat[lote], lon[lote], z[lote], cat, cat.pixel_id, z_pix, self.U),
                                   self.U)
            for c in (*F.CAMPOS_F, "renormalizada"):
                self.assertTrue(np.array_equal(parte[c], todo[c][:, lote], equal_nan=c != "renormalizada"), c)

    def test_pixeles_validos_tres_meses(self):
        """t2m y sp finitos en algún momento de 200001, 201307 y 202507; la intersección (FON-3)."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 2, 3)
        P = len(cat)
        meses = {}
        with tempfile.TemporaryDirectory() as tmp:
            for ym in (200001, 201307, 202507):
                t = S.horas_del_mes(ym // 100, ym % 100)[:24]
                campos = _base(24, P)
                if ym == 201307:
                    campos["t2m"][:, 0] = np.nan                       # píxel 0: sin t2m en 201307
                if ym == 202507:
                    campos["sp"][:, 1] = np.nan                        # píxel 1: sin sp en 202507
                campos["t2m"][1:, 2] = np.nan                          # píxel 2: un solo valor finito basta
                meses[str(ym)] = _mes(tmp, f"{ym}.nc", campos, t, cat)
            validos = F.pixeles_validos(meses)
            np.testing.assert_array_equal(validos, np.sort(cat.pixel_id.to_numpy(np.int64)[2:]))
            self.assertEqual(validos.dtype, np.int64)
            with self.assertRaises(F.ErrorFondo):
                F.pixeles_validos({k: v for k, v in meses.items() if k != "202507"})
            with self.assertRaises(F.ErrorFondo):
                F.pixeles_validos({"200001": meses["201307"], "201307": meses["200001"], "202507": meses["202507"]})
        self.assertEqual(F._MESES_VALIDEZ, (200001, 201307, 202507))

    def test_residuos_y_producto_desde(self):
        """r = obs − F (r_p = ln(QFE/p_F)) en float32 → float64 (FON-8), y el producto F + R los invierte; Td sale
        con mín(·, T) y p = p_F·exp(R_p)."""
        rng = np.random.default_rng(7)
        n = 50
        fondo = {"T_F": rng.normal(15, 5, n), "Td_F": rng.normal(5, 5, n), "p_F": rng.normal(950, 30, n),
                 "u_F": rng.normal(0, 3, n), "v_F": rng.normal(0, 3, n), "amp_TF": np.full(n, 9.0)}
        obs = {"T": rng.normal(15, 5, n), "Td": rng.normal(5, 5, n), "u": rng.normal(0, 3, n),
               "v": rng.normal(0, 3, n), "QFE": rng.normal(950, 30, n)}
        obs["T"][0] = np.nan
        obs["QFE"][1] = -1.0
        r = F.residuos(obs, fondo)
        self.assertEqual(sorted(r), sorted(F.CLAVES_RESIDUOS))
        f4 = {c: np.asarray(v, np.float64).astype(np.float32).astype(np.float64) for c, v in fondo.items()}
        o4 = {c: np.asarray(v, np.float64).astype(np.float32).astype(np.float64) for c, v in obs.items()}
        self.assertTrue(np.array_equal(r["r_T"], o4["T"] - f4["T_F"], equal_nan=True))
        self.assertTrue(np.isnan(r["r_T"][0]) and np.isnan(r["r_p"][1]))
        np.testing.assert_allclose(r["r_p"][2:], np.log(o4["QFE"][2:] / f4["p_F"][2:]), rtol=1e-15)
        R = {"R_T": r["r_T"], "R_Td": r["r_Td"], "R_u": r["r_u"], "R_v": r["r_v"], "R_p": r["r_p"]}
        prod = F.producto_desde(f4, R)
        np.testing.assert_allclose(prod["T"][1:], o4["T"][1:], atol=1e-12)
        np.testing.assert_allclose(prod["u"], o4["u"], atol=1e-12)
        np.testing.assert_allclose(prod["p"][2:], o4["QFE"][2:], rtol=1e-12)
        np.testing.assert_allclose(prod["Td"][1:], np.minimum(o4["Td"][1:], prod["T"][1:]), atol=1e-12)
        self.assertTrue((prod["Td"][1:] <= prod["T"][1:]).all())
        with self.assertRaises(F.ErrorFondo):
            F.residuos({k: v for k, v in obs.items() if k != "QFE"}, fondo)
        with self.assertRaises(F.ErrorFondo):
            F.producto_desde(fondo, {k: v for k, v in R.items() if k != "R_p"})

    def test_tabla_puntos_y_en_horas(self):
        """El fondo en una estación (A1): ``ESQUEMA_PUNTOS_E5L`` en float32, igual armado mes a mes o de una vez;
        ``en_horas`` (A2) da float64 en las horas pedidas y NaN donde la tabla no tiene la hora."""
        U = self.U
        cat = S.catalogo_pixeles(-33.0, -71.0, 2, 2)
        z = _z_tabla(cat, [400.0, 450.0, 500.0, 550.0])
        op = F.operador([-33.04], [-70.93], [800.0], cat, cat.pixel_id, z, U)
        with tempfile.TemporaryDirectory() as tmp:
            meses = []
            for m in (1, 2):
                t = S.horas_del_mes(2019, m)
                ht = _h(t)
                t2m = 290.0 + 6 * np.sin(2 * np.pi * (ht % 24) / 24)[:, None] + np.arange(4)[None, :] * 0.5
                meses.append(_mes(tmp, f"{m}.nc", _base(len(t), 4, t2m=t2m), t, cat))
        partes = []
        for mes in meses:
            fondo = F.campos_fondo(mes, op, U)
            partes.append(F.tabla_puntos(mes.tiempos, {c: fondo[c][:, 0] for c in F.CAMPOS_F}))
        por_mes = pd.concat(partes, ignore_index=True)
        h = F.horas_de(meses)
        fondos = [F.campos_fondo(m, op, U) for m in meses]
        de_una = F.tabla_puntos(h, {c: np.concatenate([f[c][:, 0] for f in fondos]) for c in F.CAMPOS_F})
        pd.testing.assert_frame_equal(por_mes, de_una)
        tipos.validar_esquema(de_una, tipos.ESQUEMA_PUNTOS_E5L, nombre="puntos")
        self.assertEqual(de_una.attrs["esquema"], tipos.ESQUEMA_PUNTOS_E5L.version)
        self.assertAlmostEqual(float(de_una.amp_TF.iloc[0]), 12.0, places=3)
        pedidas = np.array([h[5], h[0] - 1, h[-1], h[-1] + 10, h[700]])
        en = F.en_horas(de_una, pedidas)
        self.assertEqual(sorted(en), sorted(F.COLUMNAS_PUNTOS[1:]))
        self.assertTrue(np.isnan(en["T_F"][1]) and np.isnan(en["p_F"][3]))
        self.assertEqual(en["T_F"].dtype, np.float64)
        self.assertEqual(float(en["T_F"][0]), float(np.float32(fondos[0]["T_F"][5, 0])))
        self.assertEqual(float(en["Td_F"][4]), float(de_una.Td_F.iloc[700]))
        with self.assertRaises(F.ErrorFondo):
            F.tabla_puntos(h[::-1], {c: np.zeros(len(h)) for c in F.CAMPOS_F})
        with self.assertRaises(F.ErrorFondo):
            F.en_horas(de_una.astype({"T_F": "float64"}), pedidas)

    def test_amplitud_dia_utc(self):
        """Máximo menos mínimo de las 24 horas del día UTC; NaN si al día le falta una hora o trae un NaN (FON-10)."""
        h = np.arange(48 + 23, dtype=np.int64)                 # dos días completos y uno de 23 horas
        T = np.column_stack([np.sin(2 * np.pi * h / 24) * 5 + h / 24, np.ones(len(h))])
        T[30, 1] = np.nan
        amp = F.amplitud_dia_utc(T, h)
        dia0 = T[:24, 0]
        np.testing.assert_allclose(amp[:24, 0], dia0.max() - dia0.min())
        self.assertTrue(np.isnan(amp[48:, 0]).all())
        self.assertEqual(float(amp[0, 1]), 0.0)
        self.assertTrue(np.isnan(amp[24:48, 1]).all())
        with self.assertRaises(F.ErrorFondo):
            F.amplitud_dia_utc(T, h.astype(float))

    def test_z_e5l_tres_casos_y_aviso_de_50_m(self):
        """Geopotencial; si falta, NASADEM con ≥ 95 % de la huella; si no, la hipsométrica de sp̄; el aviso
        |z_NASADEM − z_hipso| > 50 m; ``valido``; un píxel válido sin ningún caso detiene (FON-4)."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 2, 3)
        ids = cat.pixel_id.to_numpy(np.int64)
        z = np.array([100.0, 200.0, 300.0, 400.0, 500.0, 600.0])
        with tempfile.TemporaryDirectory() as tmp:
            r = S.geopotencial_sintetico(Path(tmp) / "g", cat, z)
            geo = F.leer_geopotencial(r["geopotencial"])
        zg = np.array(geo.z)
        quitar = [1, 2, 3, 4]
        i0, j0 = int(cat.lat_index_global.min()), int(cat.lon_index_global.min())
        for k in quitar:
            zg[int(cat.lat_index_global[k]) - i0, int(cat.lon_index_global[k]) - j0] = np.nan
        geo = F.Geopotencial(lat=geo.lat, lon=geo.lon, z=zg, sha256=geo.sha256)
        nasadem = pd.DataFrame({"pixel_id": ids, "z_nasadem": z + 10.0,
                                "frac_nasadem": [1.0, 0.96, 0.95, 0.5, 0.2, 1.0]})
        sp = pd.Series(numerico.p_std(z + np.array([0, 0, 0, 0, 80.0, 0])), index=ids)
        tabla = F.z_e5l(geo, cat, nasadem, sp, self.U, validos=ids[[0, 1, 2, 3, 4]])
        tipos.validar_esquema(tabla, tipos.ESQUEMA_ZE5L, nombre="z_e5l")
        self.assertEqual(list(tabla.caso), ["geopotencial", "nasadem", "nasadem", "hipsometrica", "hipsometrica",
                                            "geopotencial"])
        z_hip = numerico.z_hipsometrica(sp.to_numpy())
        np.testing.assert_allclose(tabla.z_e5l, [z[0], z[1] + 10, z[2] + 10, z_hip[3], z_hip[4], z[5]], atol=1e-3)
        np.testing.assert_allclose(tabla.z_hipso, z_hip)
        self.assertEqual(list(tabla.valido), [True, True, True, True, True, False])
        self.assertEqual(list(tabla.dif_mayor_50m), [False, False, False, False, True, False])
        np.testing.assert_allclose(tabla.z_e5l[0], np.float32(z[0] * G) / G)
        sin_sp = sp.copy()
        sin_sp.iloc[3] = np.nan
        with self.assertRaises(F.ErrorFondo):
            F.z_e5l(geo, cat, nasadem, sin_sp, self.U, validos=ids)
        tabla2 = F.z_e5l(geo, cat, nasadem, sin_sp, self.U, validos=ids[[0, 5]])
        self.assertTrue(pd.isna(tabla2.caso.iloc[3]) and np.isnan(tabla2.z_e5l.iloc[3]))
        with self.assertRaises(F.ErrorFondo):
            F.operador([-33.05], [-70.95], [0.0], cat, ids, tabla2, self.U)

    def test_z_e5l_nasadem_sin_media_y_aviso_en_50_m_exactos(self):
        """Caso 2 de §4.1: «la media NASADEM de la huella de la celda, cuando ≥ 95 % de la celda tiene dato»: con
        ``frac_nasadem`` = 1 pero sin media finita, el píxel pasa a la hipsométrica (no detiene M2a). El aviso es
        «|z_NASADEM − z_hipsométrica| > 50 m»: con 50 m exactos (arriba o abajo) no se marca; con 50,01 m, sí."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 4)
        ids = cat.pixel_id.to_numpy(np.int64)
        with tempfile.TemporaryDirectory() as tmp:
            r = S.geopotencial_sintetico(Path(tmp) / "g", cat, np.full(len(cat), 700.0))
            geo = F.leer_geopotencial(r["geopotencial"])
        geo = F.Geopotencial(lat=geo.lat, lon=geo.lon, z=np.full(np.shape(geo.z), np.nan), sha256=geo.sha256)
        sp = pd.Series(numerico.p_std(np.array([700.0, 700.0, 650.0, 720.0])), index=ids)
        z_hip = numerico.z_hipsometrica(sp.to_numpy())
        z_nas = np.array([np.nan, z_hip[1] + 50.0, z_hip[2] - 50.0, z_hip[3] + 50.01])
        self.assertEqual([abs(z_nas[k] - z_hip[k]) for k in (1, 2)], [50.0, 50.0])     # 50 m exactos en float64
        nasadem = pd.DataFrame({"pixel_id": ids, "z_nasadem": z_nas, "frac_nasadem": [1.0, 0.5, 0.5, 0.5]})
        tabla = F.z_e5l(geo, cat, nasadem, sp, self.U, validos=ids)
        self.assertEqual(list(tabla.caso), ["hipsometrica"] * 4)
        np.testing.assert_array_equal(tabla.z_e5l.to_numpy(), z_hip)
        self.assertEqual(list(tabla.dif_mayor_50m), [False, False, False, True])
        self.assertTrue(tabla.valido.all())

    def test_climatologias_del_estado_y_sp_medio(self):
        """Por píxel, mes y hora UTC: T, T − Td, rapidez y la media de las amplitudes diarias, con los meses de
        2000-2025; sp̄ en hPa; un mes de 2026 no suma y uno repetido es un error (FON-13). Los ciclos de 2019 y 2020
        van en contrafase, así que D28 (P17: la media de las amplitudes diarias, 8 K) se distingue de la amplitud del
        ciclo medio (2 K)."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        acum = F.acumulador_estado(cat.pixel_id)
        with tempfile.TemporaryDirectory() as tmp:
            meses = []
            for anio, m, dias in ((2019, 1, 2), (2020, 1, 2), (2019, 2, 1), (2026, 1, 1)):
                t = S.horas_del_mes(anio, m)[:24 * dias]
                ht = _h(t)
                amplitud = np.where(anio == 2019, 6.0, -10.0)          # 2020: 10 K, con el máximo 12 h después
                t2m = 285.0 + amplitud / 2 * np.sin(2 * np.pi * (ht % 24) / 24)[:, None] + np.array([[0.0, 2.0]])
                campos = _base(len(t), 2, t2m=t2m, d2m=t2m - 4.0, u10=np.full((len(t), 2), 3.0),
                               v10=np.full((len(t), 2), 4.0), sp=np.full((len(t), 2), 90000.0 + 1000 * (anio - 2019)))
                meses.append(_mes(tmp, f"{anio}{m}.nc", campos, t, cat))
        for mes in meses:
            F.climatologias_estado(acum, mes)
        with self.assertRaises(F.ErrorFondo):
            F.climatologias_estado(acum, meses[0])
        self.assertEqual(acum.meses, {201901, 202001, 201902})
        tabla = F.tabla_clima_estado(acum)
        tipos.validar_esquema(tabla, tipos.ESQUEMA_CLIMA_ESTADO, nombre="clima")
        self.assertEqual(len(tabla), 2 * 12 * 24)
        ene = tabla[(tabla.pixel_id == int(np.sort(cat.pixel_id)[0])) & (tabla.mes == 1)]
        self.assertEqual(list(ene.hora), list(range(24)))
        h6 = ene[ene.hora == 6].iloc[0]
        self.assertAlmostEqual(float(h6["T"]), 285.0 - K + (3.0 - 5.0) / 2, places=4)
        self.assertAlmostEqual(float(h6["T_menos_Td"]), 4.0, places=4)
        self.assertAlmostEqual(float(h6["rapidez"]), 5.0, places=5)
        # La media de las amplitudes diarias, (6 + 10)/2 = 8 K, en cada hora y píxel; no la del ciclo medio (2 K).
        enero = tabla[tabla.mes == 1]
        np.testing.assert_allclose(enero.amp.to_numpy(np.float64), 8.0, atol=1e-3)
        ciclo = ene["T"].to_numpy(np.float64)
        self.assertAlmostEqual(float(ciclo.max() - ciclo.min()), 2.0, places=3)
        self.assertTrue(tabla[tabla.mes == 3][["T", "T_menos_Td", "rapidez", "amp"]].isna().all().all())
        sp = F.sp_medio_hpa(acum)
        horas = np.array([48, 48, 24])
        np.testing.assert_allclose(sp.to_numpy(), np.full(2, (900.0 * 48 + 910.0 * 48 + 900.0 * 24) / horas.sum()),
                                   rtol=1e-12)

    def test_leer_mes_exige_la_huella_y_las_variables(self):
        """La sha256 es la de los bytes leídos y, si se da, debe coincidir; faltan variables → ErrorFondo."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        t = S.horas_del_mes(2019, 9)[:3]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.mes_era5_netcdf(Path(tmp) / "m.nc", _base(3, 2), t, cat.pixel_id)
            sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
            mes = F.leer_mes(ruta, sha256=sha)
            self.assertEqual(mes.sha256, sha)
            self.assertEqual(sorted(mes.datos), sorted(F.VARIABLES_E5L))
            self.assertTrue(all(v.dtype == np.float32 for v in mes.datos.values()))
            with self.assertRaises(F.ErrorFondo):
                F.leer_mes(ruta, sha256="0" * 64)
            incompleto = S.mes_era5_netcdf(Path(tmp) / "i.nc", {"t2m": np.full((3, 2), 290.0)}, t, cat.pixel_id)
            with self.assertRaises(F.ErrorFondo):
                F.leer_mes(incompleto)
            completo = S.mes_era5_netcdf(Path(tmp) / "c.nc", _base(720, 2), S.horas_del_mes(2019, 9), cat.pixel_id)
            self.assertTrue(F.leer_mes(completo).completo_hasta(_h1(ULTIMA_E5L)))
            self.assertEqual(F.leer_mes(completo).yyyymm, 201909)

    def test_completo_hasta_la_ultima_hora_con_dato(self):
        """§3: «del 2000-01-01 a su último dato (hoy 2026-09-15 23:00 UTC)». El último mes, cortado el día 15 a las
        23 UTC, está completo hasta esa hora (no se pierde ni detiene M2a); no lo está con un hueco, sin su primera
        hora, con una hora después del último dato ni si se le exige el mes calendario entero. Un mes anterior se
        exige entero, y uno posterior al último dato no está completo (FON-1)."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        ultima = _h1(ULTIMA_E5L)
        sep = S.horas_del_mes(2026, 9)
        cortado = sep[: 15 * 24]
        with tempfile.TemporaryDirectory() as tmp:
            def mes(nombre, t):
                return _mes(tmp, f"{nombre}.nc", _base(len(t), 2), t, cat)

            ultimo = mes("202609", cortado)
            self.assertEqual(int(ultimo.tiempos[-1]), ultima)
            self.assertTrue(ultimo.completo_hasta(ultima))
            self.assertTrue(ultimo.completo_hasta(np.int64(ultima)))
            self.assertFalse(ultimo.completo_hasta(_h1("2026-09-30T23")))      # el mes calendario entero
            self.assertFalse(ultimo.completo_hasta(ultima - 1))                # una hora después del último dato
            self.assertFalse(mes("hueco", np.delete(cortado, 200)).completo_hasta(ultima))
            self.assertFalse(mes("sin_primera", cortado[1:]).completo_hasta(ultima))
            self.assertTrue(mes("201909", S.horas_del_mes(2019, 9)).completo_hasta(ultima))
            self.assertFalse(mes("201909_corto", S.horas_del_mes(2019, 9)[:-1]).completo_hasta(ultima))
            self.assertTrue(mes("202608", S.horas_del_mes(2026, 8)).completo_hasta(ultima))
            self.assertFalse(mes("202610", S.horas_del_mes(2026, 10)[:24]).completo_hasta(ultima))
            for malo in (float(ultima), True, str(ultima), ULTIMA_E5L):
                with self.subTest(h_ultima=repr(malo)):
                    with self.assertRaises(F.ErrorFondo):
                        ultimo.completo_hasta(malo)
        self.assertFalse(hasattr(F.MesE5L, "completo"))          # no hay una completitud por mes calendario

    def test_lector_calendario_y_hora_del_origen_del_eje(self):
        """FON-1: el eje «<unidad> since <fecha> [hora]» con calendario gregoriano (o sin él); otro calendario
        («noleap», «360_day»…) se rechaza, y la hora del origen cuenta: «hours since 2019-09-01 06:00:00» con 0, 1 y 2
        son las 06, 07 y 08 UTC, no las 00, 01 y 02 (§3: «Horario UTC exacto (HH:00)», S12)."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        t = S.horas_del_mes(2019, 9)[6:9]
        esperado = _h(t.astype("datetime64[h]"))
        nombres = ("time", "pixel_id", *F.VARIABLES_E5L)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.mes_era5_netcdf(Path(tmp) / "eje.nc", _base(3, 2), t, cat.pixel_id)
            base = _conjunto(ruta, nombres)
            tiempo = base.variables["time"]
            self.assertTrue(np.array_equal(F._mes_del_conjunto(base, "0" * 64, "eje.nc").tiempos, esperado))

            def con_eje(valores, unidades, **atributos):
                eje = _Variable(np.asarray(valores), ("time",), units=unidades, **atributos)
                return F._mes_del_conjunto(_conjunto(ruta, nombres, time=eje), "0" * 64, "eje.nc")

            for calendario in ("noleap", "365_day", "360_day", "all_leap", "julian"):
                with self.subTest(calendario=calendario):
                    with self.assertRaises(F.ErrorFondo) as ctx:
                        con_eje(tiempo[:], tiempo.units, calendar=calendario)
                    self.assertIn("calendario", str(ctx.exception))
            for calendario in ("standard", "gregorian", "proleptic_gregorian"):
                with self.subTest(calendario=calendario):
                    self.assertTrue(np.array_equal(con_eje(tiempo[:], tiempo.units, calendar=calendario).tiempos,
                                                   esperado))
            self.assertTrue(np.array_equal(con_eje(tiempo[:], tiempo.units).tiempos, esperado))   # sin calendario
            for unidades, valores in (("hours since 2019-09-01 06:00:00", [0, 1, 2]),
                                      ("hours since 2019-09-01T06:00", [0, 1, 2]),
                                      ("minutes since 2019-09-01 05:30:00 UTC", [30, 90, 150]),
                                      ("seconds since 2019-09-01 05:59:59", [1, 3601, 7201]),
                                      ("hours since 2019-08-31 23:00:00", [7.0, 8.0, 9.0])):
                with self.subTest(unidades=unidades):
                    mes = con_eje(valores, unidades, calendar="proleptic_gregorian")
                    self.assertTrue(np.array_equal(mes.tiempos, esperado))
                    self.assertEqual(mes.yyyymm, 201909)
            with self.assertRaises(F.ErrorFondo):
                con_eje([0, 1, 2], "days since 2019-09-01", calendar="proleptic_gregorian")
            with self.assertRaises(F.ErrorFondo):
                con_eje([0.0, 1.5, 2.0], "hours since 2019-09-01 06:00:00", calendar="proleptic_gregorian")

    def test_lector_pixel_id_repetido_o_enmascarado(self):
        """FON-1: ``pixel_id`` sin repetir y sin enmascarar; si no, ``ErrorFondo``."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        pid = cat.pixel_id.to_numpy(np.int64)
        t = S.horas_del_mes(2019, 9)[:3]
        with tempfile.TemporaryDirectory() as tmp:
            repetido = S.mes_era5_netcdf(Path(tmp) / "repetido.nc", _base(3, 2), t, [pid[0], pid[0]])
            with self.assertRaises(F.ErrorFondo) as ctx:
                F.leer_mes(repetido)
            self.assertIn("pixel_id", str(ctx.exception))
            ruta = S.mes_era5_netcdf(Path(tmp) / "bueno.nc", _base(3, 2), t, pid)
            self.assertTrue(np.array_equal(F.leer_mes(ruta).pixel_id, pid))
            nombres = ("time", "pixel_id", *F.VARIABLES_E5L)
            enmascarado = _Variable(np.ma.masked_array(pid, mask=[False, True]), ("pixel",))
            with self.assertRaises(F.ErrorFondo):
                F._mes_del_conjunto(_conjunto(ruta, nombres, pixel_id=enmascarado), "0" * 64, "bueno.nc")

    def test_geopotencial_centros_float32_antes_de_normalizar_longitud(self):
        """Los centros CDS en float32 se reconocen en su precisión original, incluso 256,2° (desvío > 10⁻⁵°).
        En ambas convenciones de longitud conservan exactamente z y la alineación con el derivado sintético."""
        cat = S.catalogo_pixeles(-32.1, -103.8, 3, 4)
        ids = cat.pixel_id.to_numpy(np.int64)
        z = 100.0 + 37.0 * np.arange(len(cat))
        nasadem = pd.DataFrame({"pixel_id": ids, "z_nasadem": z, "frac_nasadem": np.ones(len(cat))})
        sp = pd.Series(numerico.p_std(z), index=ids)
        with tempfile.TemporaryDirectory() as tmp:
            r = S.geopotencial_sintetico(Path(tmp) / "g", cat, z)
            geo = F.leer_geopotencial(r["geopotencial"])
            base = _conjunto(r["geopotencial"], ("z", "latitude", "longitude"))
            parquet = pd.read_parquet(r["altitud"])
        directo = F.z_e5l(geo, cat, nasadem, sp, self.U, validos=ids)
        for convencion in ("0..360", "-180..180"):
            with self.subTest(convencion=convencion):
                lon = geo.lon % 360 if convencion == "0..360" else geo.lon
                crudo_lon = lon.astype(np.float32)
                if convencion == "0..360":
                    self.assertGreater(float(np.max(np.abs(crudo_lon.astype(np.float64) - lon))), 1e-5)
                variables = {**base.variables,
                             "latitude": _Variable(geo.lat.astype(np.float32), ("latitude",)),
                             "longitude": _Variable(crudo_lon, ("longitude",))}
                lat, lon, zz = F._geopotencial_del_conjunto(types.SimpleNamespace(variables=variables), "g.nc")
                desde_f4 = F.z_e5l(F.Geopotencial(lat=lat, lon=lon, z=zz, sha256=geo.sha256), cat, nasadem, sp,
                                   self.U, validos=ids)
                pd.testing.assert_frame_equal(desde_f4, directo)
                F.comprobar_alineacion(desde_f4, parquet)
                np.testing.assert_array_equal(zz, geo.z)

    def test_geopotencial_float32_fuera_del_centro_rechazado(self):
        """No basta con redondear: un float vecino al del centro, aun bajo 10⁻⁵°, y un corrimiento real fallan."""
        cat = S.catalogo_pixeles(-32.1, -103.8, 2, 3)
        with tempfile.TemporaryDirectory() as tmp:
            r = S.geopotencial_sintetico(Path(tmp) / "g", cat, np.arange(len(cat)) + 100.0)
            geo = F.leer_geopotencial(r["geopotencial"])
            base = _conjunto(r["geopotencial"], ("z", "latitude", "longitude"))
        for nombre, eje in (("latitude", geo.lat), ("longitude", geo.lon), ("longitude", geo.lon % 360)):
            for modo in ("vecino_menos", "vecino_mas", "corrido"):
                with self.subTest(eje=nombre, origen=float(eje[0]), modo=modo):
                    crudo = eje.astype(np.float32)
                    if modo == "corrido":
                        crudo[0] += np.float32(0.001)
                    else:
                        direccion = np.float32(-np.inf if modo == "vecino_menos" else np.inf)
                        crudo[0] = np.nextafter(crudo[0], direccion)
                    variables = {**base.variables, nombre: _Variable(crudo, (nombre,))}
                    with self.assertRaises(F.ErrorFondo):
                        lat, lon, zz = F._geopotencial_del_conjunto(types.SimpleNamespace(variables=variables), "g.nc")
                        F._z_geopotencial(F.Geopotencial(lat=lat, lon=lon, z=zz, sha256=geo.sha256), F._catalogo(cat))

    def test_geopotencial_float64_conserva_holgura_y_no_promueve_float32(self):
        """Un eje float64 conserva 10⁻⁵°: no se lo convierte a float32 para aparentar igualdad con un centro."""
        cat = S.catalogo_pixeles(-32.1, -103.8, 2, 3)
        with tempfile.TemporaryDirectory() as tmp:
            r = S.geopotencial_sintetico(Path(tmp) / "g", cat, np.arange(len(cat)) + 100.0)
            geo = F.leer_geopotencial(r["geopotencial"])
            base = _conjunto(r["geopotencial"], ("z", "latitude", "longitude"))
        for desvio in (0.0, 9e-6, -9e-6, 1.1e-5, -1.1e-5, 0.001):
            for nombre, eje in (("latitude", geo.lat), ("longitude", geo.lon % 360)):
                with self.subTest(desvio=desvio, eje=nombre):
                    crudo = eje.copy()
                    crudo[0] += desvio
                    variables = {**base.variables, nombre: _Variable(crudo, (nombre,))}
                    if abs(desvio) <= 1e-5:
                        lat, lon, zz = F._geopotencial_del_conjunto(types.SimpleNamespace(variables=variables), "g.nc")
                        valores = F._z_geopotencial(F.Geopotencial(lat=lat, lon=lon, z=zz, sha256=geo.sha256),
                                                    F._catalogo(cat))
                        self.assertTrue(np.isfinite(valores).all())
                    else:
                        with self.assertRaises(F.ErrorFondo):
                            lat, lon, zz = F._geopotencial_del_conjunto(types.SimpleNamespace(variables=variables), "g.nc")
                            F._z_geopotencial(F.Geopotencial(lat=lat, lon=lon, z=zz, sha256=geo.sha256), F._catalogo(cat))
        variables = {**base.variables, "longitude": _Variable((geo.lon % 360).astype(np.float32).astype(np.float64),
                                                              ("longitude",))}
        with self.assertRaises(F.ErrorFondo):
            lat, lon, zz = F._geopotencial_del_conjunto(types.SimpleNamespace(variables=variables), "g.nc")
            F._z_geopotencial(F.Geopotencial(lat=lat, lon=lon, z=zz, sha256=geo.sha256), F._catalogo(cat))

    def test_geopotencial_centros_repetidos_no_finitos_o_enmascarados(self):
        """La normalización no admite centros repetidos, NaN, infinitos ni coordenadas enmascaradas."""
        cat = S.catalogo_pixeles(-32.1, -103.8, 2, 3)
        with tempfile.TemporaryDirectory() as tmp:
            r = S.geopotencial_sintetico(Path(tmp) / "g", cat, np.arange(len(cat)) + 100.0)
            geo = F.leer_geopotencial(r["geopotencial"])
            base = _conjunto(r["geopotencial"], ("z", "latitude", "longitude"))
        for dtype in (np.float32, np.float64):
            for nombre, eje in (("latitude", geo.lat), ("longitude", geo.lon % 360)):
                for modo in ("repetido", "nan", "inf", "menos_inf", "enmascarado"):
                    with self.subTest(tipo=dtype, eje=nombre, modo=modo):
                        crudo = eje.astype(dtype)
                        if modo == "enmascarado":
                            crudo = np.ma.array(crudo, mask=np.arange(len(crudo)) == 0)
                        else:
                            crudo[0] = {"repetido": crudo[1], "nan": np.nan, "inf": np.inf,
                                        "menos_inf": -np.inf}[modo]
                        variables = {**base.variables, nombre: _Variable(crudo, (nombre,))}
                        with self.assertRaises(F.ErrorFondo):
                            lat, lon, zz = F._geopotencial_del_conjunto(types.SimpleNamespace(variables=variables), "g.nc")
                            F._z_geopotencial(F.Geopotencial(lat=lat, lon=lon, z=zz, sha256=geo.sha256), F._catalogo(cat))

    def test_geopotencial_con_dimensiones_longitud_latitud(self):
        """Un z escrito (…, longitude, latitude) se transpone: da la misma rejilla y el mismo z_E5L que el escrito
        (…, latitude, longitude), con una rejilla de 3 × 4 y con una cuadrada de 3 × 3."""
        for filas, columnas in ((3, 4), (3, 3)):
            with self.subTest(rejilla=(filas, columnas)):
                cat = S.catalogo_pixeles(-33.0, -71.0, filas, columnas)
                ids = cat.pixel_id.to_numpy(np.int64)
                z = 100.0 + 37.0 * np.arange(len(cat))
                with tempfile.TemporaryDirectory() as tmp:
                    r = S.geopotencial_sintetico(Path(tmp) / "g", cat, z)
                    geo = F.leer_geopotencial(r["geopotencial"])
                    base = _conjunto(r["geopotencial"], ("z", "latitude", "longitude"))
                zt = base.variables["z"]
                transpuesto = _Variable(np.ma.asarray(zt[:]).transpose(0, 2, 1),
                                        ("valid_time", "longitude", "latitude"), units=zt.units)
                lat, lon, zz = F._geopotencial_del_conjunto(
                    types.SimpleNamespace(variables={**base.variables, "z": transpuesto}), "g.nc")
                np.testing.assert_array_equal(lat, geo.lat)
                np.testing.assert_array_equal(lon, geo.lon)
                np.testing.assert_array_equal(zz, geo.z)
                nasadem = pd.DataFrame({"pixel_id": ids, "z_nasadem": z, "frac_nasadem": np.ones(len(cat))})
                sp = pd.Series(numerico.p_std(z), index=ids)
                directo = F.z_e5l(geo, cat, nasadem, sp, self.U, validos=ids)
                desde_t = F.z_e5l(F.Geopotencial(lat=lat, lon=lon, z=zz, sha256=geo.sha256), cat, nasadem, sp, self.U,
                                  validos=ids)
                pd.testing.assert_frame_equal(desde_t, directo)
                np.testing.assert_allclose(directo.z_e5l, z, atol=1e-3)
                if filas != columnas:
                    # Los valores en (longitud, latitud) rotulados (latitud, longitud): la forma no calza.
                    mal_rotulado = _Variable(np.ma.asarray(zt[:]).transpose(0, 2, 1),
                                             ("valid_time", "latitude", "longitude"), units=zt.units)
                    with self.assertRaises(F.ErrorFondo):
                        F._geopotencial_del_conjunto(
                            types.SimpleNamespace(variables={**base.variables, "z": mal_rotulado}), "g.nc")

    def test_operador_de_pixeles_con_el_catalogo_corrido_dentro_de_la_holgura(self):
        """§3: en los píxeles válidos, con z = z_E5L, «el fondo es ERA5-Land tal cual y sólo se suma la corrección».
        Con las coordenadas del catálogo corridas dentro de la holgura de la grilla (10⁻⁷° y −3·10⁻⁶°, que
        ``_catalogo`` acepta), ``operador_pixeles`` (por pixel_id, A10) sigue dando un vecino de peso 1 y dz = 0, y
        el fondo es t2m − 273,15, sp/100, mín(d2m, t2m) − 273,15, u10 y v10, bit a bit, sin renormalizar."""
        U = self.U
        cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        ids = cat.pixel_id.to_numpy(np.int64)
        corrido = cat.copy()
        corrido["latitude"] = corrido["latitude"] + 1e-7
        corrido["longitude"] = corrido["longitude"] - 3e-6
        rng = np.random.default_rng(11)
        z_pix = _z_tabla(cat, rng.uniform(200, 1500, len(cat)))
        P = len(cat)
        campos = _base(24, P, t2m=rng.normal(290, 3, (24, P)), d2m=rng.normal(280, 3, (24, P)),
                       sp=rng.normal(90000, 500, (24, P)), u10=rng.normal(0, 3, (24, P)), v10=rng.normal(0, 3, (24, P)))
        with tempfile.TemporaryDirectory() as tmp:
            mes = _mes(tmp, "pixeles.nc", campos, S.horas_del_mes(2019, 9)[:24], cat)
        pedidos = ids[[5, 0, 11, 5]]
        op = F.operador_pixeles(pedidos, corrido, ids, z_pix)
        pix = np.asarray(op.pix)
        np.testing.assert_array_equal(pix[:, 0], pedidos)
        self.assertTrue((pix[:, 1:] == -1).all())
        np.testing.assert_array_equal(np.asarray(op.w), np.c_[np.ones(4), np.zeros((4, 3))])
        np.testing.assert_array_equal(np.asarray(op.dz)[:, 0], np.zeros(4))
        self.assertTrue(np.isnan(np.asarray(op.dz)[:, 1:]).all())
        np.testing.assert_array_equal(op.ids, pedidos)
        np.testing.assert_array_equal(op.z, z_pix.z_e5l.to_numpy()[[5, 0, 11, 5]])
        self.assertFalse(np.asarray(op.respaldo).any())
        fondo = F.campos_fondo(mes, op, U)
        col = [int(np.flatnonzero(np.asarray(mes.pixel_id) == p)[0]) for p in pedidos]
        d = {v: mes.datos[v][:, col].astype(np.float64) for v in ("t2m", "d2m", "sp", "u10", "v10")}
        self.assertTrue(np.array_equal(fondo["T_F"], d["t2m"] - K))
        self.assertTrue(np.array_equal(fondo["p_F"], d["sp"] / 100.0))
        self.assertTrue(np.array_equal(fondo["Td_F"], np.minimum(d["d2m"] - K, d["t2m"] - K)))
        self.assertTrue(np.array_equal(fondo["u_F"], d["u10"]) and np.array_equal(fondo["v_F"], d["v10"]))
        self.assertFalse(fondo["renormalizada"].any())
        # Con el catálogo sin correr, lo mismo; fuera de la holgura, el catálogo no sirve.
        for c in ("pix", "w", "dz", "z"):
            np.testing.assert_array_equal(getattr(F.operador_pixeles(pedidos, cat, ids, z_pix), c), getattr(op, c))
        lejos = cat.copy()
        lejos["latitude"] = lejos["latitude"] + 2e-5
        with self.assertRaises(F.ErrorFondo):
            F.operador_pixeles(pedidos, lejos, ids, z_pix)
        # Sólo píxeles válidos, del catálogo, con z_E5L finita y con pixel_id enteros.
        sin_z = z_pix.copy()
        sin_z.loc[0, "z_e5l"] = np.nan
        ajeno = ids.max() + 1
        con_ajeno = pd.concat([z_pix, pd.DataFrame({"pixel_id": [ajeno], "z_e5l": [500.0]})], ignore_index=True)
        for nombre, args in (("no_valido", (pedidos, cat, ids[ids != pedidos[0]], z_pix)),
                             ("fuera_del_catalogo", (np.array([ajeno]), cat, ids, z_pix)),
                             ("valido_fuera_del_catalogo", (np.array([ajeno]), cat, np.r_[ids, ajeno], con_ajeno)),
                             ("sin_z", (ids[:1], cat, ids, sin_z)),
                             ("no_enteros", (pedidos.astype(float), cat, ids, z_pix))):
            with self.subTest(caso=nombre):
                with self.assertRaises(F.ErrorFondo):
                    F.operador_pixeles(*args)

    def test_operador_lleva_el_indice_al_entero_en_latitudes_norte(self):
        """FON-6: en 64,1° la cuenta (90 − lat)/0,1 da 259,00000000000006 en float64; sin llevarla al entero, el
        centro del píxel tendría un segundo vecino de peso ≈ 6·10⁻¹⁴. Llevada al entero, un vecino de peso 1."""
        cat = S.catalogo_pixeles(64.1, -71.0, 2, 2)
        self.assertNotEqual((90.0 - 64.1) * 10, round((90.0 - 64.1) * 10))
        arriba = cat[np.isclose(cat.latitude, 64.1)]
        op = F.operador(arriba.latitude.to_numpy(), arriba.longitude.to_numpy(), np.full(len(arriba), 100.0), cat,
                        cat.pixel_id, _z_tabla(cat, np.full(len(cat), 100.0)), self.U)
        np.testing.assert_array_equal(np.asarray(op.pix)[:, 0], arriba.pixel_id.to_numpy())
        self.assertTrue((np.asarray(op.pix)[:, 1:] == -1).all())
        self.assertTrue((np.asarray(op.w)[:, 0] == 1.0).all())

    def test_todo_error_es_error_fondo(self):
        """FON-2 (MC-57): ningún error de este módulo es un ``ValueError`` ni un ``TypeError``, que el paso 1 de §2.1
        captura como «no normalizable». Toda función pública pasa por ``_errores_de_fondo``; una tabla de fondo mal
        armada o desalineada en ``residuos`` o ``en_horas`` (lo que consume el control de calidad) es ``ErrorFondo``,
        también cuando el error nace en numpy, pandas o ``tipos``."""
        self.assertFalse(issubclass(F.ErrorFondo, (ValueError, TypeError)))
        publicas = [n for n, f in inspect.getmembers(F, inspect.isfunction)
                    if f.__module__ == F.__name__ and not n.startswith("_")]
        self.assertGreaterEqual(len(publicas), 20)
        self.assertEqual([n for n in publicas if not hasattr(getattr(F, n), "__wrapped__")], [])
        self.assertTrue(hasattr(F.MesE5L.completo_hasta, "__wrapped__"))
        n = 4
        fondo = {c: np.zeros(n) for c in F.CAMPOS_F}
        obs = {c: np.zeros(n) for c in F.CLAVES_OBS}
        tabla = F.tabla_puntos(np.arange(n, dtype=np.int64), fondo)
        casos = {
            "residuos_desalineados": lambda: F.residuos({**obs, "T": np.zeros(n + 1)}, fondo),
            "residuos_sin_qfe": lambda: F.residuos({k: v for k, v in obs.items() if k != "QFE"}, fondo),
            "residuos_con_texto": lambda: F.residuos({**obs, "T": np.array(["a"] * n)}, fondo),
            "en_horas_esquema": lambda: F.en_horas(tabla.astype({"T_F": "float64"}), np.arange(n)),
            "en_horas_sin_columna": lambda: F.en_horas(tabla.drop(columns="p_F"), np.arange(n)),
            "en_horas_horas_reales": lambda: F.en_horas(tabla, np.arange(n, dtype=float)),
            "producto_desalineado": lambda: F.producto_desde(fondo, {c: np.zeros(n + 1) for c in F.CLAVES_R}),
            "tabla_puntos_forma": lambda: F.tabla_puntos(np.arange(n), {c: np.zeros(n + 1) for c in F.CAMPOS_F}),
            "sumas_rr06_forma": lambda: F.sumas_rr06(np.zeros((n, 2)), np.arange(2), h=np.arange(n + 1)),
            "amplitud_forma": lambda: F.amplitud_dia_utc(np.zeros(n), np.arange(n + 1)),
            "horas_de_vacio": lambda: F.horas_de([]),
            "operador_largos": lambda: F.operador([0.0], [0.0, 1.0], [0.0], None, [], {}, self.U),
            "operador_z_pix": lambda: F.operador([-33.0], [-71.0], [0.0], S.catalogo_pixeles(-33.0, -71.0, 1, 1),
                                                 [], [1.0], self.U),
            "pixeles_validos_claves": lambda: F.pixeles_validos({"200001": None}),
            "pixel_de_lluvia_columnas": lambda: F.pixel_de_lluvia([1], pd.DataFrame({"celda": [1]})),
            "pixel_de_lluvia_celda_real": lambda: F.pixel_de_lluvia(
                [1.5], pd.DataFrame({"celda": [1], "era5land_pixel": [7]})),
            "lluvia_rr06_forma": lambda: F.lluvia_rr06(np.zeros((n, 2)), np.arange(2), np.zeros(2, dtype=np.int64),
                                                       h=np.arange(n), pixel_ids=np.arange(3)),
            "lluvia_rr06_pixel_real": lambda: F.lluvia_rr06(np.zeros((n, 2)), np.arange(2), np.zeros(2),
                                                            h=np.arange(n), pixel_ids=np.arange(2)),
            "clima_en_puntos_esquema": lambda: F.clima_en_puntos(pd.DataFrame({"pixel_id": [1]}), None, self.U),
            "clima_en_horas_forma": lambda: F.clima_en_horas({v: np.zeros((1, 12)) for v in F.VARIABLES_CLIMA},
                                                             np.arange(n)),
        }
        for nombre, llamada in casos.items():
            with self.subTest(caso=nombre):
                with self.assertRaises(F.ErrorFondo) as ctx:
                    llamada()
                self.assertNotIsInstance(ctx.exception, (ValueError, TypeError))


# ---------------------------------------------------------------------------------------------------------------
# D27 y D29 (decisiones delegadas de la ola 2): la lluvia de RR06 y el operador sobre las climatologías. D28 está en
# PruebasFondo.test_climatologias_del_estado_y_sp_medio.
# ---------------------------------------------------------------------------------------------------------------
_TIPOS_ENLACE = ["propio", "vecino_valido", "sin_enlace"]      # construir_grilla.enlazar_pixel_valido


def _enlaces_reales(enlaces: pd.DataFrame) -> pd.DataFrame:
    """Los enlaces de ``sintetico.grilla`` con el tipo de enlace de la grilla real («propio», «vecino_valido» o
    «sin_enlace»; el sintético escribe «contiene»)."""
    salida = enlaces.copy()
    salida["era5land_enlace"] = pd.Categorical(["propio"] * len(salida), categories=_TIPOS_ENLACE)
    return salida


class PruebasD27(unittest.TestCase):
    """D27 (P16): la lluvia de una estación en RR06 es la del píxel que ``enlaces_productos.parquet`` enlaza a su
    celda; sin enlace, no se compara y se cuenta (§2.6, FON-12). Grilla y meses de ``sintetico`` (los meses en una
    carpeta temporal; la grilla, en memoria)."""

    @classmethod
    def setUpClass(cls):
        g = S.grilla(400, 4)                                  # 20 × 20 celdas de 0,01° desde (−33,30; −70,80)
        cls.enlaces = _enlaces_reales(g["enlaces_productos"])
        cls.cat = S.catalogo_pixeles(-33.3, -70.8, 3, 3)      # los 9 píxeles que cubren la grilla
        cls.tmp = tempfile.TemporaryDirectory()
        t_todo = np.concatenate([S.horas_del_mes(2019, m) for m in (1, 2)])
        cls.h_todo = _h(t_todo)
        P = len(cls.cat)
        base = (np.where(cls.h_todo % 5 == 0, 0.0004, 0.0) + np.where(cls.h_todo % 7 == 0, 0.0011, 0.0)
                + np.where(cls.h_todo % 11 == 0, 0.0002, 0.0))
        cls.lluvia = base[:, None] * np.arange(1, P + 1)[None, :]          # m por hora, distinta en cada píxel
        tp = S.tp_acumulado(t_todo, cls.lluvia)
        enero = t_todo.astype("datetime64[M]") == np.datetime64("2019-01", "M")
        cls.meses = [_mes(cls.tmp.name, f"{nombre}.nc", _base(int(k.sum()), P, tp=tp[k]), t_todo[k], cls.cat)
                     for nombre, k in (("201901", enero), ("201902", ~enero))]
        cls.h = F.horas_de(cls.meses)
        cls.tp = F.incrementos_tp(cls.meses)
        cls.ids = np.asarray(cls.meses[0].pixel_id, dtype=np.int64)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _con(self, fila, pixel, tipo) -> pd.DataFrame:
        enl = self.enlaces.copy()
        enl.loc[enl.index[fila], "era5land_pixel"] = pixel
        enl.loc[enl.index[fila], "era5land_enlace"] = tipo
        return enl

    def test_d27_el_pixel_enlazado_a_la_celda(self):
        """``pixel_de_lluvia`` da el ``era5land_pixel`` de la celda de cada estación, también cuando no es el píxel
        más cercano («vecino_valido»): la geometría no cuenta. −1 sin celda (D34) o con la celda «sin_enlace». Una
        tabla mal armada o una celda que no está en ella es un ``ErrorFondo`` (FON-12)."""
        enl = self.enlaces
        self.assertTrue(set(enl.era5land_pixel) <= set(self.ids))
        self.assertGreater(enl.era5land_pixel.nunique(), 4)
        c = enl.celda.to_numpy(np.int64)
        otro = int(next(p for p in self.ids if p != int(enl.era5land_pixel.iloc[1])))
        enl = self._con(1, otro, "vecino_valido")
        enl.loc[enl.index[2], "era5land_pixel"] = -1
        enl.loc[enl.index[2], "era5land_enlace"] = "sin_enlace"
        self.assertEqual(str(enl.era5land_pixel.dtype), "int64")
        celdas = pd.array([c[0], c[1], c[2], None, c[3]], dtype="Int64")     # como la columna ``celda`` (Int64)
        pix = F.pixel_de_lluvia(celdas, enl)
        self.assertEqual(pix.dtype, np.int64)
        np.testing.assert_array_equal(pix, [int(enl.era5land_pixel.iloc[0]), otro, -1, -1,
                                            int(enl.era5land_pixel.iloc[3])])
        np.testing.assert_array_equal(F.pixel_de_lluvia(celdas, enl.drop(columns="era5land_enlace")), pix)
        np.testing.assert_array_equal(F.pixel_de_lluvia(pd.Series(celdas), enl), pix)
        np.testing.assert_array_equal(F.pixel_de_lluvia([int(c[0]), np.nan], enl),
                                      [int(enl.era5land_pixel.iloc[0]), -1])
        self.assertEqual(len(F.pixel_de_lluvia([], enl)), 0)
        nulo_tipo = enl.copy()
        nulo_tipo["era5land_enlace"] = nulo_tipo.era5land_enlace.astype("string")
        nulo_tipo.loc[nulo_tipo.index[0], "era5land_enlace"] = pd.NA
        nulo_pixel = enl.copy()
        nulo_pixel["era5land_pixel"] = nulo_pixel.era5land_pixel.astype("Int64")
        nulo_pixel.loc[nulo_pixel.index[0], "era5land_pixel"] = pd.NA
        malos = {
            "celda_fuera_de_la_tabla": (pd.array([int(c.max()) + 1], dtype="Int64"), enl),
            "sin_enlace_con_pixel": ([c[0]], self._con(0, int(enl.era5land_pixel.iloc[0]), "sin_enlace")),
            "menos_1_sin_sin_enlace": ([c[0]], self._con(0, -1, "propio")),
            "tipo_nulo": ([c[0]], nulo_tipo),
            "pixel_nulo": ([c[0]], nulo_pixel),
            "pixel_real": ([c[0]], enl.astype({"era5land_pixel": "float64"})),
            "pixel_menor_que_menos_1": ([c[0]], self._con(2, -2, "sin_enlace")),
            "celda_repetida": ([c[0]], pd.concat([enl, enl.iloc[:1]], ignore_index=True)),
            "sin_era5land_pixel": ([c[0]], enl.drop(columns="era5land_pixel")),
            "celda_no_entera": ([1.5], enl),
        }
        for nombre, (celdas_mal, tabla) in malos.items():
            with self.subTest(caso=nombre):
                with self.assertRaises(F.ErrorFondo):
                    F.pixel_de_lluvia(celdas_mal, tabla)

    def test_d27_suma_de_6_h_en_el_pixel_enlazado_y_sin_enlace_se_cuenta(self):
        """Cada reporte suma las 6 horas que terminan en su rótulo en el píxel de su estación: la cuenta de
        ``sumas_rr06`` en esa columna, bit a bit, y la lluvia sintética dentro de 10⁻⁴ mm. La ventana que cruza el
        cambio de mes suma con el mes anterior; la del 1 de enero a las 03 UTC, sin diciembre, es NaN pero no «sin
        enlace». Los reportes sin enlace dan NaN y ``sin_enlace``, que es lo que se cuenta."""
        enl = self._con(2, -1, "sin_enlace")
        c = enl.celda.to_numpy(np.int64)
        pix_est = F.pixel_de_lluvia(pd.array([c[0], c[399], c[2], None], dtype="Int64"), enl)
        self.assertEqual(list(pix_est[2:]), [-1, -1])
        self.assertNotEqual(int(pix_est[0]), int(pix_est[1]))
        rotulos = np.array([_h1("2019-01-01T03"), _h1("2019-02-01T02"), _h1("2019-02-10T12"), _h1("2019-01-20T18")])
        h_fin = np.tile(rotulos, len(pix_est))
        pixel = np.repeat(pix_est, len(rotulos))
        suma, sin = F.lluvia_rr06(self.tp, h_fin, pixel, h=self.h, pixel_ids=self.ids)
        self.assertEqual((suma.dtype, sin.dtype), (np.dtype(np.float64), np.dtype(bool)))
        np.testing.assert_array_equal(sin, pixel == -1)
        self.assertEqual(int(sin.sum()), 8)                    # los reportes que no se comparan, para contarlos
        self.assertTrue(np.isnan(suma[sin]).all())
        todas = F.sumas_rr06(self.tp, rotulos, h=self.h)
        for k, p in enumerate(pix_est[:2]):
            col = int(np.flatnonzero(self.ids == p)[0])
            propia = suma[k * len(rotulos):(k + 1) * len(rotulos)]
            self.assertTrue(np.array_equal(propia, todas[:, col], equal_nan=True))
            self.assertTrue(np.isnan(propia[0]) and not sin[k * len(rotulos)])     # NaN por la ventana, no el enlace
            for j, fin in enumerate(rotulos[1:], start=1):
                ventana = (self.h_todo > fin - 6) & (self.h_todo <= fin)
                self.assertEqual(int(ventana.sum()), 6)
                self.assertAlmostEqual(float(propia[j]), float(self.lluvia[ventana, col].sum() * 1000.0), delta=1e-4)
        # La lluvia sigue al enlace de cada estación: con otro píxel, otra suma.
        self.assertGreater(abs(float(suma[1]) - float(suma[len(rotulos) + 1])), 0.1)
        malos = {
            "pixel_fuera_de_los_meses": {"pixel": np.array([int(self.ids.max()) + 1])},
            "pixel_menor_que_menos_1": {"pixel": np.array([-2])},
            "pixel_real": {"pixel": np.array([float(self.ids[0])])},
            "un_pixel_por_reporte": {"pixel": self.ids[:2]},
            "pixel_ids_repetidos": {"pixel_ids": np.r_[self.ids[:-1], self.ids[0]]},
            "tp_sin_su_columna": {"pixel_ids": self.ids[:-1]},
            "h_desordenadas": {"h": self.h[::-1]},
        }
        for nombre, cambio in malos.items():
            a = {"pixel": self.ids[:1], "pixel_ids": self.ids, "h": self.h, **cambio}
            with self.subTest(caso=nombre):
                with self.assertRaises(F.ErrorFondo):
                    F.lluvia_rr06(self.tp, rotulos[1:2], a["pixel"], h=a["h"], pixel_ids=a["pixel_ids"])


def _campos_clima(la, lo, z, mes, hora, gamma) -> dict:
    """Climatologías lineales en latitud y longitud (T, además, con Γ·z): el bilineal las reproduce exactas."""
    return {"T": 20 + 2 * (la + 33) - 3 * (lo + 71) + gamma * z / 1000 + 0.1 * hora + 0.5 * mes,
            "T_menos_Td": 5 + 1.5 * (la + 33) + 2 * (lo + 71) + 0.05 * hora + 0.1 * mes,
            "rapidez": 3 + 4 * (la + 33) + 6 * (lo + 71) + 0.01 * mes + 0.02 * hora,
            "amp": 10 - 3 * (la + 33) + 5 * (lo + 71) + 0.02 * mes - 0.01 * hora}


def _tabla_clima(cat, z_pix, gamma, semilla=5) -> pd.DataFrame:
    """``ESQUEMA_CLIMA_ESTADO`` de los píxeles de ``cat`` con ``_campos_clima`` en el centro y la z_E5L de cada uno,
    con las filas en un orden cualquiera."""
    P, celdas = len(cat), 12 * 24
    pid = np.repeat(cat.pixel_id.to_numpy(np.int64), celdas)
    mes = np.tile(np.repeat(np.arange(1, 13), 24), P)
    hora = np.tile(np.arange(24), 12 * P)
    la, lo = (np.repeat(cat[c].to_numpy(np.float64), celdas) for c in ("latitude", "longitude"))
    z = np.repeat(np.asarray(z_pix, dtype=np.float64), celdas)
    datos = {"pixel_id": pid, "mes": mes.astype(np.int8), "hora": hora.astype(np.int8)}
    datos.update({v: x.astype(np.float32) for v, x in _campos_clima(la, lo, z, mes, hora, gamma).items()})
    tabla = pd.DataFrame(datos, columns=list(tipos.ESQUEMA_CLIMA_ESTADO))
    return tabla.sample(frac=1, random_state=semilla).reset_index(drop=True)


def _cubo(tabla, ids) -> dict:
    """Los valores de la tabla (float32 → float64) como punto × mes × hora, en el orden de ``ids``."""
    t = tabla.set_index(["pixel_id", "mes", "hora"]).sort_index()
    return {v: np.stack([t.loc[int(p), v].to_numpy(np.float32).astype(np.float64).reshape(12, 24) for p in ids])
            for v in F.VARIABLES_CLIMA}


class PruebasD29(unittest.TestCase):
    """D29 (P18 y FON-P3): el operador sobre las climatologías (T con los pesos bilineales y Γ; T − Td, rapidez y
    amplitud con los pesos bilineales solos) y T − Td con el recorte hora a hora, máx(t2m − d2m, 0), que es lo que C
    ve en T_F − Td_F (§4.1, §4.7; FON-13, FON-14)."""

    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls.gamma = float(cls.U.a("GAMMA_K_KM"))
        cls.cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        a = np.round((-33.0 - cls.cat.latitude.to_numpy()) / 0.1).astype(int)
        b = np.round((cls.cat.longitude.to_numpy() + 71.0) / 0.1).astype(int)
        cls.z_pix = 300.0 + 200.0 * a + 100.0 * b                       # de 300 a 1.000 m
        cls.z = _z_tabla(cls.cat, cls.z_pix)
        cls.tabla = _tabla_clima(cls.cat, cls.z_pix, cls.gamma)
        # Puntos dentro de la rejilla, arriba y abajo de sus píxeles; el último, en un centro.
        cls.lat = np.array([-33.04, -33.15, -33.11, -33.0])
        cls.lon = np.array([-70.93, -70.78, -70.85, -70.9])
        cls.zp = np.array([1500.0, 100.0, 640.0, 900.0])
        cls.op = F.operador(cls.lat, cls.lon, cls.zp, cls.cat, cls.cat.pixel_id, cls.z, cls.U)
        cls.cp = F.clima_en_puntos(cls.tabla, cls.op, cls.U)

    def test_d29_t_menos_td_recortado_hora_a_hora(self):
        """FON-13: T − Td es la media de máx(t2m − d2m, 0) de cada hora. Con d2m > t2m en las horas 0-11 de 2019
        (−2 K) y +4 K en 2020, la hora 6 da 2 K (sin recorte, o recortando la media, daría 1 K); en las horas 12-23
        (+1 y +4 K) da 2,5 K. Una hora con d2m NaN no suma (no es 0): 8/3 K y no 2 K. Es la media por hora de
        T_F − Td_F del fondo en el píxel (``operador_pixeles``), y ``clima_en_puntos`` la devuelve tal cual."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        ids = cat.pixel_id.to_numpy(np.int64)
        self.assertTrue((np.diff(ids) > 0).all())
        acum = F.acumulador_estado(ids)
        meses = []
        with tempfile.TemporaryDirectory() as tmp:
            for anio in (2019, 2020):
                t = S.horas_del_mes(anio, 1)[:48]
                hh = _h(t) % 24
                t2m = 285.0 + 3.0 * np.sin(2 * np.pi * hh / 24)[:, None] + np.array([[0.0, 2.0]])
                dif = np.where(hh < 12, -2.0, 1.0) if anio == 2019 else np.full(len(t), 4.0)
                d2m = t2m - dif[:, None]
                if anio == 2019:
                    d2m[6, 0] = np.nan                                  # 2019-01-01 06 UTC, píxel 0
                meses.append(_mes(tmp, f"{anio}.nc", _base(len(t), 2, t2m=t2m, d2m=d2m), t, cat))
        for mes in meses:
            F.climatologias_estado(acum, mes)
        tabla = F.tabla_clima_estado(acum)

        def valor(k, hora, v="T_menos_Td"):
            fila = tabla[(tabla.pixel_id == ids[k]) & (tabla.mes == 1) & (tabla.hora == hora)]
            return float(fila[v].iloc[0])

        self.assertAlmostEqual(valor(1, 6), 2.0, places=5)
        self.assertAlmostEqual(valor(1, 18), 2.5, places=5)
        self.assertAlmostEqual(valor(0, 6), 8.0 / 3.0, places=5)
        self.assertAlmostEqual(valor(0, 7), 2.0, places=5)
        self.assertAlmostEqual(valor(0, 6, "T"), 285.0 + 3.0 - K, places=4)     # t2m sigue sumando sus 4 horas
        enero = tabla[tabla.mes == 1]
        self.assertTrue((enero.T_menos_Td.to_numpy(np.float64) >= 0).all())
        # Lo que C ve en T_F − Td_F, en el píxel y hora a hora (Td_F := mín(Td_F, T_F)), promediado por hora UTC.
        op = F.operador_pixeles(ids, cat, ids, _z_tabla(cat, [500.0, 600.0]))
        dif, horas = [], []
        for mes in meses:
            f = F.campos_fondo(mes, op, self.U)
            dif.append(f["T_F"] - f["Td_F"])
            horas.append(np.asarray(mes.tiempos, dtype=np.int64) % 24)
        D, H = np.vstack(dif), np.concatenate(horas)
        self.assertTrue((D[np.isfinite(D)] >= 0).all())
        for k in range(2):
            for hora in range(24):
                x = D[H == hora, k]
                self.assertAlmostEqual(valor(k, hora), float(x[np.isfinite(x)].mean()), delta=1e-5)
        cp = F.clima_en_puntos(tabla, op, self.U)
        esperado = _cubo(tabla, ids)
        for v in F.VARIABLES_CLIMA:
            self.assertTrue(np.array_equal(cp[v], esperado[v], equal_nan=True), v)
        self.assertTrue(np.isnan(cp["T_menos_Td"][:, 1:]).all())          # sin febrero a diciembre: NaN
        self.assertFalse(cp["renormalizada"].any())

    def test_d29_t_con_gamma_y_las_demas_con_los_pesos_solos(self):
        """Con climatologías lineales en latitud y longitud (y T con Γ·z_i), el operador da en cada punto, mes y hora
        T = la lineal + Γ·z_x/1000 y T − Td, rapidez y amplitud = las lineales, sin ningún término de altura, con
        puntos 1.200 m arriba y 900 m abajo de sus píxeles."""
        m = np.arange(1, 13)[None, :, None]
        hh = np.arange(24)[None, None, :]
        esperado = _campos_clima(self.lat[:, None, None], self.lon[:, None, None], self.zp[:, None, None], m, hh,
                                 self.gamma)
        dz = np.asarray(self.op.dz)
        self.assertGreater(np.nanmax(np.abs(dz)), 800.0)
        for v in F.VARIABLES_CLIMA:
            self.assertEqual(self.cp[v].shape, (4, 12, 24), v)
            self.assertEqual(self.cp[v].dtype, np.float64, v)
            np.testing.assert_allclose(self.cp[v], esperado[v], rtol=0, atol=2e-5, err_msg=v)
        self.assertFalse(self.cp["renormalizada"].any())
        # Con Γ en T − Td (o sin Γ en T) el error sería de varios K.
        self.assertGreater(float(np.abs(self.gamma * dz[0, 0] / 1000)), 1.0)

    def test_d29_en_los_pixeles_es_la_tabla_tal_cual_y_por_lotes_lo_mismo(self):
        """Con ``operador_pixeles`` (peso 1, dz = 0) da la tabla, bit a bit (§3: «allí el fondo es ERA5-Land tal
        cual»); el orden de las filas de la tabla no importa, y partir los puntos en lotes da lo mismo."""
        ids = self.cat.pixel_id.to_numpy(np.int64)
        pedidos = ids[[5, 0, 11, 5]]
        cp = F.clima_en_puntos(self.tabla, F.operador_pixeles(pedidos, self.cat, ids, self.z), self.U)
        esperado = _cubo(self.tabla, pedidos)
        for v in F.VARIABLES_CLIMA:
            self.assertTrue(np.array_equal(cp[v], esperado[v]), v)
        ordenada = self.tabla.sort_values(["pixel_id", "mes", "hora"]).reset_index(drop=True)
        for v in (*F.VARIABLES_CLIMA, "renormalizada"):
            self.assertTrue(np.array_equal(F.clima_en_puntos(ordenada, self.op, self.U)[v], self.cp[v]), v)
        for lote in (slice(0, 1), slice(1, 3), slice(3, 4)):
            op = F.operador(self.lat[lote], self.lon[lote], self.zp[lote], self.cat, ids, self.z, self.U)
            parte = F.clima_en_puntos(self.tabla, op, self.U)
            for v in (*F.VARIABLES_CLIMA, "renormalizada"):
                self.assertTrue(np.array_equal(parte[v], self.cp[v][lote]), v)

    def test_d29_renormalizacion_sin_z_y_respaldo(self):
        """Un vecino sin valor en un mes y hora se descarta y se renormaliza, sólo en esa variable, y se marca
        (MC-39, como hora a hora); sin ningún vecino, NaN. Un punto sin z tiene T NaN y lo demás igual (no depende de
        z). El respaldo a ≤ 16 km lleva peso 1 y Γ en T."""
        op, cp = self.op, self.cp
        pix, w, dz = np.asarray(op.pix), np.asarray(op.w), np.asarray(op.dz)
        self.assertTrue((pix[0] >= 0).all() and (pix[1] >= 0).all())
        t2 = self.tabla.copy()
        quitar_T = (t2.pixel_id == pix[0, 0]) & (t2.mes == 7) & (t2.hora == 5)
        t2.loc[quitar_T, "T"] = np.float32(np.nan)
        quitar_r = t2.pixel_id.isin(pix[1]) & (t2.mes == 3) & (t2.hora == 0)
        t2.loc[quitar_r, "rapidez"] = np.float32(np.nan)
        cp2 = F.clima_en_puntos(t2, op, self.U)
        cubo = _cubo(self.tabla, ids=[int(p) for p in pix[0]])
        resto = [k for k in range(4) if k != 0]
        num = sum(w[0, k] * (cubo["T"][k, 6, 5] + self.gamma * dz[0, k] / 1000) for k in resto)
        self.assertAlmostEqual(float(cp2["T"][0, 6, 5]), num / sum(w[0, k] for k in resto), places=10)
        self.assertGreater(abs(float(cp2["T"][0, 6, 5]) - float(cp["T"][0, 6, 5])), 1e-3)
        self.assertEqual([tuple(x) for x in np.argwhere(cp2["renormalizada"][0])], [(6, 5)])
        self.assertTrue(np.isnan(cp2["rapidez"][1, 2, 0]) and np.isfinite(cp2["T"][1, 2, 0]))
        self.assertFalse(cp2["renormalizada"][1, 2, 0])
        fuera = np.ones((12, 24), dtype=bool)
        fuera[6, 5] = False
        self.assertTrue(np.array_equal(cp2["T"][0][fuera], cp["T"][0][fuera]))
        for v in ("T_menos_Td", "amp"):
            self.assertTrue(np.array_equal(cp2[v], cp[v]), v)
        # Sin z: T NaN; lo demás, igual bit a bit (mismos pesos).
        sin_z = F.clima_en_puntos(self.tabla, F.operador(self.lat[:1], self.lon[:1], [np.nan], self.cat,
                                                          self.cat.pixel_id, self.z, self.U), self.U)
        self.assertTrue(np.isnan(sin_z["T"]).all())
        for v in ("T_menos_Td", "rapidez", "amp"):
            self.assertTrue(np.array_equal(sin_z[v][0], cp[v][0]), v)
        self.assertFalse(sin_z["renormalizada"].any())
        # Respaldo: ninguna esquina válida; el centro válido de (−33,0; −70,9) a ≈ 14,6 km, con peso 1 y dz.
        ids = self.cat.pixel_id.to_numpy(np.int64)
        valido = int(ids[(np.isclose(self.cat.latitude, -33.0)) & (np.isclose(self.cat.longitude, -70.9))][0])
        op_r = F.operador([-33.13], [-70.92], [1200.0], self.cat, [valido], self.z, self.U)
        self.assertTrue(op_r.respaldo[0])
        cr = F.clima_en_puntos(self.tabla, op_r, self.U)
        cubo_v = _cubo(self.tabla, [valido])
        dz_r = float(np.asarray(op_r.dz)[0, 0])
        self.assertEqual(dz_r, 1200.0 - self.z_map_de(valido))
        self.assertTrue(np.array_equal(cr["T"][0], cubo_v["T"][0] + self.gamma * dz_r / 1000))
        for v in ("T_menos_Td", "rapidez", "amp"):
            self.assertTrue(np.array_equal(cr[v][0], cubo_v[v][0]), v)

    def z_map_de(self, pixel) -> float:
        return float(self.z_pix[int(np.flatnonzero(self.cat.pixel_id.to_numpy(np.int64) == pixel)[0])])

    def test_d29_clima_en_horas(self):
        """``clima_en_horas`` toma, para cada h, el mes (1-12) y la hora UTC: 2019-01-31 23 UTC → (enero, 23);
        2019-02-01 00 UTC → (febrero, 0); 2020-12-31 23 UTC → (diciembre, 23); 2021-07-15 05 UTC → (julio, 5)."""
        h = np.array([_h1("2019-01-31T23"), _h1("2019-02-01T00"), _h1("2020-12-31T23"), _h1("2021-07-15T05")])
        ch = F.clima_en_horas(self.cp, h)
        self.assertEqual(sorted(ch), sorted(F.VARIABLES_CLIMA))
        for v in F.VARIABLES_CLIMA:
            self.assertEqual(ch[v].shape, (4, 4))
            for k, (m, hora) in enumerate(((0, 23), (1, 0), (11, 23), (6, 5))):
                self.assertTrue(np.array_equal(ch[v][k], self.cp[v][:, m, hora]), (v, k))
        self.assertEqual(F.clima_en_horas(self.cp, np.array([], dtype=np.int64))["T"].shape, (0, 4))
        with self.assertRaises(F.ErrorFondo):
            F.clima_en_horas(self.cp, h.astype(float))
        with self.assertRaises(F.ErrorFondo):
            F.clima_en_horas({v: x for v, x in self.cp.items() if v != "amp"}, h)

    def test_d29_tabla_mal_armada_es_error_fondo(self):
        """FON-14: cada píxel con sus 12 × 24 filas exactas y sin repetir, el esquema exacto, mes 1-12 y hora 0-23, y
        todo vecino del operador en la tabla; si no, ``ErrorFondo``. Un mes o una hora fuera de rango en el primer o
        el último píxel no repite ninguna fila (no hay con quién chocar): lo ataja la regla del rango, no la de las
        repetidas, y sin ella el cubo de ese píxel quedaría corrido en silencio."""
        t = self.tabla
        vecino = int(np.asarray(self.op.pix)[0, 0])
        primero, ultimo = int(t.pixel_id.min()), int(t.pixel_id.max())

        def con(pixel, mes, hora, columna, valor):
            otra = t.copy()
            otra.loc[(otra.pixel_id == pixel) & (otra.mes == mes) & (otra.hora == hora), columna] = np.int8(valor)
            return otra

        movida = t.copy()
        movida.loc[movida.index[0], "hora"] = np.int8((int(movida.hora.iloc[0]) + 1) % 24)
        malas = {
            "sin_un_vecino": (t[t.pixel_id != vecino], "no están en la tabla"),
            "fila_repetida": (pd.concat([t, t.iloc[:1]], ignore_index=True), "repetidas"),
            "sin_una_fila": (t.iloc[1:], "12 × 24 filas"),
            "fila_movida": (movida, "repetidas"),
            "mes_13_en_el_ultimo": (con(ultimo, 12, 0, "mes", 13), "mes fuera"),
            "hora_24_en_el_ultimo": (con(ultimo, 12, 23, "hora", 24), "mes fuera"),
            "mes_0_en_el_primero": (con(primero, 1, 0, "mes", 0), "mes fuera"),
            "hora_menos_1_en_el_primero": (con(primero, 1, 0, "hora", -1), "mes fuera"),
            "mes_13_en_todos": (t.assign(mes=np.where(t.mes == 12, 13, t.mes).astype(np.int8)), "mes fuera"),
            "float64": (t.astype({"T": "float64"}), "tipos distintos"),
            "sin_columna": (t.drop(columns="amp"), "columnas"),
        }
        for nombre, (tabla, motivo) in malas.items():
            with self.subTest(caso=nombre):
                with self.assertRaises(F.ErrorFondo) as ctx:
                    F.clima_en_puntos(tabla, self.op, self.U)
                self.assertIn(motivo, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
