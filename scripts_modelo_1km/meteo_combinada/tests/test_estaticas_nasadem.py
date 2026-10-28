"""Pruebas de estaticas_nasadem.py (§2.5, §3 y §4.6).

Dueño: I8 (ola 2). Las que llevan «sNN» son la prueba NN de §9 del texto (S3: K1, K3 con un DEM con máscara
administrativa, la alineación de los píxeles-punto con las celdas y la pendiente con cos φ). Correr desde
scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos, en carpetas temporales: las teselas NASADEM y GHS-POP salen de ``sintetico`` (GeoTIFF int16 de
1/3.600° y GeoTIFF float32 de 100 m en Mollweide, SIN-9 y SIN-10) y las tablas de la grilla se arman aquí con ids
propios. Para probar por separado cada exigencia de ``leer_tesela`` (NAS-3), una tesela de ``sintetico`` se retoca con
rasterio («r+») en la misma carpeta temporal, como hace ``test_sinca_meteo`` con sus archivos sintéticos. Ninguna prueba
abre DMC, la meteorología SINCA real, NASADEM real ni GHS-POP real. Del reloj sólo se lee, por AST y con su huella de AP
``1da0236`` (la clausura fijada, FIJ-1; antes ``4b50b0d``), el código de ``tablas.interpretar_coordenada`` y el rango de
§3.3 de ``constantes`` (la copia de NAS-1).
La equivalencia de los motivos con POL-5 se compara con ``politicas._estado_coordenadas`` (NAS-12), hasta que el
enumerado único de motivos esté en ``tipos``.
Los valores esperados salen de caminos propios: la regla escrita en la prueba (bordes en múltiplos de 72 pasos de la
red, planos con pendiente conocida, máscaras que cortan la celda), haversine punto por punto para los discos y
``rasterio.transform.rowcol`` para los píxeles GHS.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import estaticas_nasadem as EN  # noqa: E402
from meteo_combinada import fijados, numerico, tipos, umbrales  # noqa: E402
from meteo_combinada import sintetico as S  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_RELOJ = _RAIZ / "reloj_dmc"
P = 3600                                   # puntos de la red por grado (1/3.600°)
KM_POR_GRADO = math.pi * 6371 / 180        # MC-59
M_POR_PASO = 6371000 * math.pi / 180 / P   # Δy de la red, en m

_U = None


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


def _red(grados: float) -> int:
    return int(round(grados * P))


def _I(la):
    return np.rint(np.asarray(la) * P)


def _tesela(carpeta, nombre, funcion_z, *, norte, oeste, filas, columnas, mascara=None):
    ruta = S.tesela_nasadem(Path(carpeta) / nombre, funcion_z, mascara=mascara, oeste=oeste, norte=norte,
                            filas=filas, columnas=columnas)
    return EN.leer_tesela(ruta, hashlib.sha256(ruta.read_bytes()).hexdigest())


def _ghs(carpeta, nombre, funcion_pob, **kw):
    ruta = S.tesela_ghs(Path(carpeta) / nombre, funcion_pob, **kw)
    return ruta, EN.leer_ghs(ruta, hashlib.sha256(ruta.read_bytes()).hexdigest())


def _grilla(centros, *, cod=None, macro=None, aoi=None):
    """celdas, estaticas y estaticas_lulc de unas celdas dadas por su centro, con ids propios (no deducibles)."""
    n = len(centros)
    ids = np.arange(70001, 70001 + n, dtype=np.int64)[::-1].copy()
    cod = list(cod) if cod is not None else [13101] * n
    macro = list(macro) if macro is not None else ["centro"] * n
    aoi = list(aoi) if aoi is not None else ["continente"] * n
    celdas = pd.DataFrame({
        "celda": ids, "lat": [c[0] for c in centros], "lon": [c[1] for c in centros],
        "cod_comuna": np.asarray(cod, dtype=np.int32), "aoi_id": pd.array(aoi, dtype="string"),
        "macrozona": pd.array(macro, dtype="string"),
        "macrozona_cod": np.asarray([S.MACROZONA_CODIGO[m] for m in macro], dtype=np.int8)})
    estaticas = pd.DataFrame({"celda": ids, "dist_costa_km": np.linspace(0.5, 40.0, n).astype(np.float32)})
    partes = []
    for anio, base in ((2015, 0.1), (2020, 0.3)):
        d = {"celda": ids, "anio": np.full(n, anio, np.int16)}
        d.update({c: np.full(n, base + q / 100, np.float32) for q, c in enumerate(tipos.LULC)})
        partes.append(pd.DataFrame(d))
    return celdas, estaticas, pd.concat(partes, ignore_index=True)


def _fila(est, celda_id):
    return est[est["celda"] == celda_id].iloc[0]


class _UmbralTPI:
    """Los umbrales de M0 con la fracción de C_TPI_PCT cambiada por una calculada en la prueba: sólo sirve para probar
    el borde «< 50 %» y el conteo exacto de los puntos del disco (NAS-9). No es un umbral del texto."""

    def __init__(self, U, fraccion: float):
        self._U, self._f = U, float(fraccion)

    def a(self, clave):
        return self._U.a(clave)

    def frac(self, clave):
        return self._f if clave == "C_TPI_PCT" else self._U.frac(clave)


# ---------------------------------------------------------------------------------------------------------------
class PruebasS3(unittest.TestCase):
    def test_s03_k1_decimales_segundos_y_minutos(self):
        """K1: ρ con d decimales, con segundos y sólo minutos; rige la precisión más gruesa (MC-59, NAS-2)."""
        U = _umbrales()
        r2 = math.sqrt(2)
        dos_decimales = 0.005 * KM_POR_GRADO * r2           # 0,786 km
        minutos = 0.5 / 60 * KM_POR_GRADO * r2              # 1,310 km
        casos = [
            ("-33.45", "-70.65", dos_decimales),
            ("−33,45", "-70,65", dos_decimales),                 # signo U+2212 y coma decimal
            ("-33.4500", "-70.65", dos_decimales),               # 4 y 2 decimales: la más gruesa
            ("33°27' S", "70°39' W", minutos),
            ("33°27'12\" S", "70°39' W", minutos),             # segundos y sólo minutos: la más gruesa
            ("33°27.5' S", "70°39.25′ W", minutos),             # minutos con decimales: 0,5′ (NAS-2)
            ("-33°27'", "-70.65", minutos),
        ]
        for lat, lon, esperado in casos:
            with self.subTest(lat=lat, lon=lon):
                self.assertAlmostEqual(EN.rho_km(lat, lon, U), esperado, places=12)
        # con segundos, 0,5″ = 0,022 km → recorte a 0,1 km
        self.assertEqual(EN.rho_km("33°27'12\" S", "70°39'05\" W", U), 0.1)
        self.assertEqual(EN.rho_km("33 27 12.5 S", "70 39 05 W", U), 0.1)
        for malo in ("abc", "", None, "33.5°27' S", "+33°27' S"):
            with self.subTest(malo=malo):
                self.assertTrue(math.isnan(EN.rho_km(malo, "-70.65", U)))
        self.assertAlmostEqual(EN.interpretar_coordenada("33°27' S", "lat"), -(33 + 27 / 60), places=12)
        self.assertAlmostEqual(EN.interpretar_coordenada("−70,65", "lon"), -70.65, places=12)
        self.assertEqual(EN.interpretar_coordenada("33.45", "lat"), 33.45)      # nunca se invierte un signo

    def test_s03_k1_recortes_en_0_1_y_2_km(self):
        """ρ = mín(máx(ρ; 0,1 km); 2 km), con √2 y sin cos φ (MC-59)."""
        U = _umbrales()
        self.assertEqual((U.a("RHO_MIN_KM"), U.a("RHO_MAX_KM")), (0.1, 2))
        self.assertEqual(EN.rho_km("-33.456", "-70.651", U), 0.1)       # 0,079 km
        self.assertEqual(EN.rho_km("-33.4", "-70.6", U), 2.0)           # 7,9 km
        self.assertEqual(EN.rho_km("-33", "-70", U), 2.0)               # 79 km
        # sin cos φ: lo mismo a −20° y a −50°, y con √2
        a20, a50 = EN.rho_km("-20.00", "-70.00", U), EN.rho_km("-50.00", "-70.00", U)
        self.assertEqual(a20, a50)
        self.assertAlmostEqual(a50, 0.005 * KM_POR_GRADO * math.sqrt(2), places=12)
        self.assertGreater(a50 / (0.005 * KM_POR_GRADO), 1.4)

    def test_s03_k3_pasa_y_falla_con_dem_con_mascara(self):
        """K3 con un DEM sintético con máscara administrativa: dato a ≤ ρ y |Δz| ≤ 50 m, inclusivos (NAS-10)."""
        U = _umbrales()
        self.assertEqual(U.a("K3_DZ_M"), 50)
        lat, lon = -33.45, -70.65
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "k3.tif", lambda la, lo: np.full(la.shape, 1000.0), mascara=lambda la, lo: lo < -70.66,
                        norte=-33.43, oeste=-70.69, filas=144, columnas=144)
        filas, cols = np.nonzero(t.dato)
        d = numerico.haversine_km(lat, lon, (t.i_norte - filas) / P, (t.j_oeste + cols) / P)
        d_min = float(d.min())
        self.assertTrue(0.8 < d_min < 1.0, d_min)               # la máscara deja el dato a ≈ 0,93 km al oeste
        # ρ = d_min exacto (la misma haversine sobre los mismos puntos de la red): «a ≤ ρ» es inclusiva
        self.assertEqual(EN.k3(lat, lon, 1000.0, d_min, [t], U), (True, 1000.0))
        self.assertEqual(EN.k3(lat, lon, 1000.0, d_min + 1e-9, [t], U), (True, 1000.0))
        pasa, z_s = EN.k3(lat, lon, 1000.0, d_min - 1e-9, [t], U)
        self.assertFalse(pasa)
        self.assertTrue(math.isnan(z_s))
        self.assertEqual(EN.k3(lat, lon, 1050.0, 2.0, [t], U), (True, 1050.0))      # |Δz| = 50: pasa
        self.assertEqual(EN.k3(lat, lon, 949.0, 2.0, [t], U)[0], False)             # |Δz| = 51: no
        self.assertEqual(EN.k3(lat, lon, 1050.5, 2.0, [t], U)[0], False)
        self.assertEqual(EN.k3(lat, lon, 1000.0, 2.0, [], U)[0], False)             # sin NASADEM: no pasa
        # La tesela está a ≤ ρ aunque su dato no lo esté: K3 sí se prueba, y falla (NAS-10); sin tesela no (D37)
        self.assertTrue(EN.hay_tesela_a_rho(lat, lon, d_min - 1e-9, [t]))
        self.assertFalse(EN.hay_tesela_a_rho(lat, lon, 2.0, []))
        with self.assertRaises(ValueError):
            EN.k3(lat, lon, 1000.0, math.nan, [t], U)

    def test_s03_k3_sin_z_cat_da_z_s_nasadem_y_qfe_sin_regla(self):
        """Sin z_cat legible: coordenadas confirmadas y z_s NASADEM bilineal; ``z_s_fuente`` = «nasadem», con la que
        ``politicas`` deja QFE sin regla (A7). Sin bilineal posible, la estación queda fuera (NAS-11)."""
        U = _umbrales()
        norte, oeste = -33.43, -70.67
        i0, j0 = _red(norte), _red(oeste)

        def plano(la, lo):
            return 1000.0 + 3.0 * (np.rint(np.asarray(lo) * P) - j0) + 2.0 * (_I(la) - i0)

        lat_txt, lon_txt = "-33.4500694", "-70.6498889"
        lat, lon = float(lat_txt), float(lon_txt)
        esperado = 1000.0 + 3.0 * (lon * P - j0) + 2.0 * (lat * P - i0)     # la bilineal reproduce un plano
        j_vecino = math.floor(lon * P) + 1
        # una estación con segundos enteros cae justo sobre un punto de la red (I_g, J_g)
        lat_g = EN.interpretar_coordenada("33°27'00\" S", "lat")
        lon_g = EN.interpretar_coordenada("70°39'00\" W", "lon")
        i_g, j_g = _red(lat_g), _red(lon_g)
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "plano.tif", plano, norte=norte, oeste=oeste, filas=144, columnas=144)
            t_hueco = _tesela(tmp, "hueco.tif", plano, norte=norte, oeste=oeste, filas=144, columnas=144,
                              mascara=lambda la, lo: np.rint(np.asarray(lo) * P) != j_vecino)
            # sin dato en la fila al norte y en la columna al este del punto: los puntos de peso 0 de la bilineal
            t_borde = _tesela(tmp, "borde.tif", plano, norte=norte, oeste=oeste, filas=144, columnas=144,
                              mascara=lambda la, lo: (_I(la) != i_g + 1) & (np.rint(np.asarray(lo) * P) != j_g + 1))
        pasa, z_s = EN.k3(lat, lon, math.nan, 0.5, [t], U)
        self.assertTrue(pasa)
        self.assertAlmostEqual(z_s, esperado, places=6)
        self.assertEqual(EN.k3(i0 / P - 0.01, j0 / P + 0.01, None, 0.5, [t], U), (True, 1000.0 + 3 * 36 - 2 * 36))
        pasa, z_s = EN.k3(lat, lon, math.nan, 0.5, [t_hueco], U)
        self.assertTrue(pasa)
        self.assertTrue(math.isnan(z_s))
        # un punto con peso 0 no necesita dato (NAS-11): sobre el punto, y sobre la fila entre dos columnas
        self.assertEqual(EN.k3(lat_g, lon_g, math.nan, 0.5, [t_borde], U),
                         (True, 1000.0 + 3.0 * (j_g - j0) + 2.0 * (i_g - i0)))
        lon_f = -70.6501111                                         # entre J_g − 1 y J_g, sobre la fila I_g
        pasa, z_s = EN.k3(lat_g, lon_f, math.nan, 0.5, [t_borde], U)
        self.assertTrue(pasa)
        self.assertAlmostEqual(z_s, 1000.0 + 3.0 * (lon_f * P - j0) + 2.0 * (i_g - i0), places=6)
        self.assertTrue(math.isnan(EN.k3(lat_g + 0.5 / P, lon_g, math.nan, 0.5, [t_borde], U)[1]))   # ahí sí pesa
        celdas, _, _ = _grilla([(-33.455, -70.645)])
        catalogo = pd.DataFrame({"codigo": ["330001"], "nombre": ["Sin altitud"], "lat_txt": [lat_txt],
                                 "lon_txt": [lon_txt], "alt_txt": ["s/i"]})
        mz = fijados.macrozona_region(_AP)
        info = EN.info_estaciones(catalogo, celdas, [t], U, macrozona_region=mz, conjuntos={})["330001"]
        self.assertEqual((info.k3_pasa, info.z_s_fuente, info.excluida, info.motivo), (True, "nasadem", False, None))
        self.assertTrue(math.isnan(info.z_cat))
        self.assertAlmostEqual(info.z_s, esperado, places=6)
        info = EN.info_estaciones(catalogo, celdas, [t_hueco], U, macrozona_region=mz, conjuntos={})["330001"]
        self.assertEqual((info.k3_pasa, info.z_s_fuente, info.excluida, info.motivo),
                         (True, "nasadem", True, EN.MOTIVO_SIN_Z_S))

    def test_s03_pixeles_punto_en_celdas_bordes_oeste_y_sur_cerrados(self):
        """Un punto de la red sobre el borde sur u oeste es de esa celda; sobre el norte o el este, de la vecina.

        La altitud vale 1.000 en las filas de la red múltiplos de 72 pasos y 1 en las columnas múltiplos de 72: cada
        celda de 36 × 36 recibe la fila o la columna sólo si es su borde sur u oeste (y no si es su borde norte o
        este)."""
        U = _umbrales()

        def z(la, lo):
            return (1000.0 * (np.mod(_I(la), 72) == 0) + 1.0 * (np.mod(np.rint(np.asarray(lo) * P), 72) == 0))

        centros = [(-33.455, -70.655), (-33.455, -70.645), (-33.445, -70.655), (-33.445, -70.645)]
        celdas, estaticas, lulc = _grilla(centros)
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "bordes.tif", z, norte=-33.44, oeste=-70.66, filas=73, columnas=73)
        self.assertEqual((t.i_norte, t.i_sur, t.j_oeste, t.j_este), (-120384, -120456, -254376, -254304))
        est = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc, U)
        esperado = {(-33.455, -70.655): 36 * 1000 + 36, (-33.455, -70.645): 36 * 1000,
                    (-33.445, -70.655): 36, (-33.445, -70.645): 0}
        for (la, lo), suma in esperado.items():
            fila = est[(celdas["lat"] == la) & (celdas["lon"] == lo)].iloc[0]
            with self.subTest(celda=(la, lo)):
                self.assertEqual(fila["z_media"], suma / 1296)
                self.assertEqual(fila["frac_dato"], 1.0)
        # celda_de_puntos con la misma regla
        puntos = [(-33.45, -70.66, (-3345, -7066)), (-33.44, -70.65, (-3344, -7065)),
                  (-33.4500001, -70.6600001, (-3346, -7067)), (-33.4499999, -70.6599999, (-3345, -7066)),
                  (-33.445, -70.645, (-3345, -7065))]
        k = EN.celda_de_puntos([p[0] for p in puntos], [p[1] for p in puntos])
        self.assertEqual([tuple(int(x) for x in fila) for fila in k], [p[2] for p in puntos])
        with self.assertRaises(ValueError):
            EN.celda_de_puntos([math.nan], [-70.6])

    def test_s03_pendiente_con_cos_phi_en_menos20_y_menos50(self):
        """Plano de pendiente conocida en −20° y −50°: z = 1.000 + 10·ΔJ + 5·ΔI (m por paso de la red), con
        Δx = Δy·cos φ de cada fila (NAS-7)."""
        U = _umbrales()
        for lat_c in (-20.005, -50.005):
            with self.subTest(lat=lat_c):
                lon_c = -70.005
                norte, oeste = lat_c + 0.015, lon_c - 0.015
                i0, j0 = _red(norte), _red(oeste)

                def plano(la, lo, i0=i0, j0=j0):
                    return 1000.0 + 10.0 * (np.rint(np.asarray(lo) * P) - j0) + 5.0 * (_I(la) - i0)

                celdas, estaticas, lulc = _grilla([(lat_c, lon_c)])
                with tempfile.TemporaryDirectory() as tmp:
                    t = _tesela(tmp, "plano.tif", plano, norte=norte, oeste=oeste, filas=109, columnas=109)
                est = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc, U)
                k = round(lat_c * 100 - 0.5)
                filas_i = np.arange(36 * k, 36 * k + 36)
                dx = M_POR_PASO * np.cos(np.radians(filas_i / P))
                esperado = float(np.mean(np.degrees(np.arctan(np.hypot(10.0 / dx, 5.0 / M_POR_PASO)))))
                self.assertAlmostEqual(float(est["pendiente_deg"].iloc[0]), esperado, places=9)
                sin_cos = math.degrees(math.atan(math.hypot(10.0 / M_POR_PASO, 5.0 / M_POR_PASO)))
                if lat_c < -40:
                    self.assertGreater(abs(esperado - sin_cos), 5.0)      # sin cos φ se notaría

    def test_s03_celda_cortada_por_la_mascara_administrativa(self):
        """Celda de costa o de frontera: la máscara administrativa del descargador la corta (S3, «un DEM sintético con
        máscara administrativa»). z_media es la media de los puntos con dato y frac_dato su fracción (NAS-6). La
        pendiente es NaN en los puntos sin dato y en los vecinos de la máscara («nunca diferencias de un lado»), y la
        de la celda es la media de las definidas (NAS-7). La altitud poblada ignora la población GHS que cae sobre la
        parte sin dato (NAS-8). Las declaraciones cuentan cada caso, y ``ghs`` vacío es un error.

        Los esperados salen de un camino propio: punto por punto, con el plano y la máscara escritos aquí, y los píxeles
        GHS con pyproj y ``rasterio.transform.rowcol`` sobre el archivo."""
        U = _umbrales()
        lat_c, lon_c = -33.445, -70.645
        k, m = round(lat_c * 100 - 0.5), round(lon_c * 100 - 0.5)
        i_s, j_o = 36 * k, 36 * m                       # fila sur y columna oeste de la celda, en la red

        def plano_ij(ii, jj):                           # 10 m por columna y 5 m por fila de la red
            return 1000 + 10 * (jj - j_o) + 5 * (ii - i_s)

        def con_dato_ij(ii, jj):                        # escalera: de 12 a 29 columnas con dato por fila de la celda
            return (jj - j_o) < 12 + (ii - i_s) // 2

        lejana = (-33.505, lon_c)                       # sin tesela NASADEM y fuera de la tesela GHS
        celdas, estaticas, lulc = _grilla([(lat_c, lon_c), lejana])
        id_c, id_l = int(celdas["celda"].iloc[0]), int(celdas["celda"].iloc[1])
        puntos = [(ii, jj) for ii in range(i_s, i_s + 36) for jj in range(j_o, j_o + 36)]
        con = [(ii, jj) for ii, jj in puntos if con_dato_ij(ii, jj)]
        vecinos = ((1, 0), (-1, 0), (0, 1), (0, -1))
        definidos = [(ii, jj) for ii, jj in con if all(con_dato_ij(ii + a, jj + b) for a, b in vecinos)]
        self.assertTrue(0 < len(definidos) < len(con) < 1296)
        with tempfile.TemporaryDirectory() as tmp:
            # la celda y un punto más de cada lado (los vecinos de la pendiente)
            t = _tesela(tmp, "costa.tif", lambda la, lo: plano_ij(_I(la), _I(lo)).astype(np.float64),
                        mascara=lambda la, lo: con_dato_ij(_I(la), _I(lo)), norte=(i_s + 36) / P,
                        oeste=(j_o - 1) / P, filas=38, columnas=38)
            ruta_g, g = _ghs(tmp, "rampa.tif", lambda la, lo: 1.0 + 1000.0 * (la + 33.47) + 300.0 * (lo + 70.66),
                             lat_centro=lat_c, lon_centro=lon_c, filas=40, columnas=40)
            import rasterio
            from pyproj import Transformer
            from rasterio.transform import rowcol
            II, JJ = np.array([p[0] for p in puntos]), np.array([p[1] for p in puntos])
            x, y = Transformer.from_crs("EPSG:4326", "ESRI:54009", always_xy=True).transform(JJ / P, II / P)
            with rasterio.open(ruta_g) as ds:
                fila, col = rowcol(ds.transform, x, y)
                v = ds.read(1)[np.asarray(fila), np.asarray(col)].astype(np.float64)
        est = EN.estaticos_celdas(celdas, [t], [g], estaticas, lulc, U)
        a = _fila(est, id_c)
        # NAS-6: la media de los puntos con dato, no la suma sobre 1.296
        self.assertEqual(a["frac_dato"], len(con) / 1296)
        self.assertEqual(a["z_media"], sum(plano_ij(ii, jj) for ii, jj in con) / len(con))
        # NAS-7: NaN en cada punto sin dato o con un vecino sin dato; la media de las definidas
        z_v, d_v = EN._ventana([t], i_s + 36, i_s - 1, j_o - 1, j_o + 36)
        p_v = EN._pendientes(z_v, d_v, i_s + 36)
        definida = set(definidos)
        distintas = [(ii, jj) for ii, jj in puntos
                     if math.isfinite(p_v[i_s + 36 - ii, jj - j_o + 1]) != ((ii, jj) in definida)]
        self.assertEqual(distintas, [])

        def pendiente(ii):
            dx = M_POR_PASO * math.cos(math.radians(ii / P))
            return math.degrees(math.atan(math.hypot(10.0 / dx, 5.0 / M_POR_PASO)))

        self.assertAlmostEqual(float(a["pendiente_deg"]), sum(pendiente(ii) for ii, _ in definidos) / len(definidos),
                               places=9)
        # NAS-8: sólo pesan los puntos con dato, aunque la parte sin dato tenga población
        w = np.where(v > 0, v, 0.0)
        conjunto_con = set(con)
        con_mask = np.array([p in conjunto_con for p in puntos])
        self.assertGreater(float(w[~con_mask].min()), 0.0)
        zz = np.array([plano_ij(ii, jj) for ii, jj in puntos], dtype=np.float64)
        self.assertAlmostEqual(float(a["z_poblada"]), float(np.sum((w * zz)[con_mask]) / np.sum(w[con_mask])), places=9)
        self.assertFalse(bool(a["z_poblada_es_media"]))
        b = _fila(est, id_l)
        self.assertTrue(math.isnan(b["z_media"]) and math.isnan(b["z_poblada"]) and bool(b["z_poblada_es_media"]))
        self.assertEqual(b["frac_dato"], 0.0)
        # las declaraciones (la tesela no alcanza a cubrir la mitad de ningún disco)
        self.assertEqual(est.attrs["declaraciones"], {
            "ghs_legible": True, "teselas_ghs": 1, "huellas_ghs": (g.sha256,), "celdas": 2,
            "celdas_sin_dato_nasadem": 1, "celdas_con_media_en_vez_de_poblada": 1, "celdas_fuera_de_ghs": 1,
            "celdas_tpi1_truncado": 2, "celdas_tpi5_truncado": 2})
        repetida = EN.estaticos_celdas(celdas, [t], (g, g), estaticas, lulc, U)
        self.assertEqual((repetida.attrs["declaraciones"]["teselas_ghs"], float(_fila(repetida, id_c)["z_poblada"])),
                         (1, float(a["z_poblada"])))
        sin = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc, U).attrs["declaraciones"]
        self.assertEqual((sin["ghs_legible"], sin["teselas_ghs"], sin["huellas_ghs"], sin["celdas_fuera_de_ghs"],
                          sin["celdas_con_media_en_vez_de_poblada"]), (False, 0, (), 2, 2))
        with self.assertRaises(ValueError):                    # [] no es «ninguna tesela legible»: eso es None
            EN.estaticos_celdas(celdas, [t], [], estaticas, lulc, U)
        with self.assertRaises(TypeError):
            EN.estaticos_celdas(celdas, [t], [t], estaticas, lulc, U)


# ---------------------------------------------------------------------------------------------------------------
class PruebasEstaticos(unittest.TestCase):
    def test_altitud_poblada_y_media_sin_poblacion(self):
        """§3: z ponderada por GHS-POP 2020 (el píxel de 100 m que contiene cada punto); sin población, la media; sin
        teselas legibles, la media y se declara (NAS-8)."""
        U = _umbrales()
        lat_a, lat_b, lon_c = -33.445, -33.455, -70.645
        i_a = _red(lat_a)
        celdas, estaticas, lulc = _grilla([(lat_a, lon_c), (lat_b, lon_c)])
        id_a, id_b = int(celdas["celda"].iloc[0]), int(celdas["celda"].iloc[1])
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "dem.tif", lambda la, lo: np.where(_I(la) > i_a, 2000.0, 1000.0),
                        norte=-120384 / P, oeste=-254341 / P, filas=74, columnas=38)
            _, g = _ghs(tmp, "ghs.tif", lambda la, lo: np.where(la > lat_a + 0.003, 50.0, 0.0), lat_centro=-33.45,
                        lon_centro=lon_c, filas=40, columnas=40)
            ruta_rampa, g_rampa = _ghs(tmp, S.nombre_tesela_ghs(12, 13) + ".zip",
                                       lambda la, lo: 1.0 + 1000.0 * (la + 33.47) + 300.0 * (lo + 70.66),
                                       lat_centro=-33.45, lon_centro=lon_c, filas=40, columnas=40)
            est = EN.estaticos_celdas(celdas, [t], [g], estaticas, lulc, U)
            a, b = _fila(est, id_a), _fila(est, id_b)
            self.assertEqual(a["z_media"], (17 * 2000 + 19 * 1000) / 36)
            self.assertEqual((a["z_poblada"], bool(a["z_poblada_es_media"])), (2000.0, False))
            self.assertEqual((b["z_media"], b["z_poblada"], bool(b["z_poblada_es_media"])), (1000.0, 1000.0, True))
            self.assertTrue(est.attrs["declaraciones"]["ghs_legible"])
            # sin teselas GHS legibles: la media en todas, y se declara
            sin = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc, U)
            self.assertTrue(sin["z_poblada_es_media"].all())
            np.testing.assert_array_equal(sin["z_poblada"].to_numpy(), sin["z_media"].to_numpy())
            self.assertFalse(sin.attrs["declaraciones"]["ghs_legible"])
            # pesos que varían, por un camino propio (pyproj y rasterio.transform.rowcol sobre el archivo)
            est = EN.estaticos_celdas(celdas, [t], [g_rampa], estaticas, lulc, U)
            import rasterio
            from pyproj import Transformer
            from rasterio.transform import rowcol
            k, m = round(lat_a * 100 - 0.5), round(lon_c * 100 - 0.5)
            II, JJ = np.meshgrid(np.arange(36 * k, 36 * k + 36), np.arange(36 * m, 36 * m + 36), indexing="ij")
            x, y = Transformer.from_crs("EPSG:4326", "ESRI:54009", always_xy=True).transform(JJ / P, II / P)
            with rasterio.open(f"/vsizip/{ruta_rampa}/{S.nombre_tesela_ghs(12, 13)}.tif") as ds:
                fila, col = rowcol(ds.transform, x.ravel(), y.ravel())
                v = ds.read(1)[np.asarray(fila), np.asarray(col)].astype(np.float64)
            w = np.where(v > 0, v, 0.0)
            zz = np.where(II.ravel() > i_a, 2000.0, 1000.0)
            self.assertAlmostEqual(float(_fila(est, id_a)["z_poblada"]), float(np.sum(w * zz) / np.sum(w)), places=9)
            # dos teselas GHS que cubren los mismos puntos de la celda deben valer lo mismo en ellos (NAS-8)
            kw = dict(lon_centro=lon_c, filas=20, columnas=20)
            _, g10 = _ghs(tmp, "g10.tif", lambda la, lo: np.full(la.shape, 10.0), lat_centro=lat_a, **kw)
            _, g10_sur = _ghs(tmp, "g10_sur.tif", lambda la, lo: np.full(la.shape, 10.0), lat_centro=lat_a - 0.004,
                              **kw)
            _, g20_sur = _ghs(tmp, "g20_sur.tif", lambda la, lo: np.full(la.shape, 20.0), lat_centro=lat_a - 0.004,
                              **kw)
            juntas = EN.estaticos_celdas(celdas, [t], [g10, g10_sur], estaticas, lulc, U)
            self.assertEqual(juntas.attrs["declaraciones"]["teselas_ghs"], 2)
            self.assertFalse(bool(_fila(juntas, id_a)["z_poblada_es_media"]))
            for orden in ([g10, g20_sur], [g20_sur, g10]):
                with self.assertRaisesRegex(ValueError, "dos teselas GHS"):
                    EN.estaticos_celdas(celdas, [t], orden, estaticas, lulc, U)

    def test_tpi_truncado_con_menos_de_la_mitad_de_dato(self):
        """§4.6: TPI = z_media − media del disco (radio 1 y 5 km, haversine) con la parte con dato; con < 50 % de dato,
        ``tpi_truncado`` y TPI = 0 tras estandarizar (NAS-9)."""
        U = _umbrales()
        lat_c, lon_c = -33.445, -70.645
        i_c, j_c = _red(lat_c), _red(lon_c)
        k, m = -3345, -7065
        alto, ancho = 72, 90                    # la tesela: ±72 filas y ±90 columnas alrededor del centro

        def z(la, lo):
            ii, jj = _I(la), np.rint(np.asarray(lo) * P)
            en_celda = (ii >= 36 * k) & (ii <= 36 * k + 35) & (jj >= 36 * m) & (jj <= 36 * m + 35)
            return np.where(en_celda, 1000.0, 900.0)

        celdas, estaticas, lulc = _grilla([(lat_c, lon_c)])
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "tpi.tif", z, norte=(i_c + alto) / P, oeste=(j_c - ancho) / P, filas=2 * alto + 1,
                        columnas=2 * ancho + 1)
        est = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc, U).iloc[0]
        self.assertEqual(est["z_media"], 1000.0)
        fracciones = {}
        for nombre, r in (("tpi1", 1.0), ("tpi5", 5.0)):
            di, dj = np.arange(-170, 171), np.arange(-215, 216)
            II, JJ = i_c + di[:, None], j_c + dj[None, :]
            en_disco = numerico.haversine_km(lat_c, lon_c, II / P, JJ / P) <= r
            con_dato = (np.abs(II - i_c) <= alto) & (np.abs(JJ - j_c) <= ancho)
            self.assertFalse(en_disco[0].any() or en_disco[-1].any() or en_disco[:, 0].any() or en_disco[:, -1].any())
            zz = z(II / P, JJ / P)
            media = float(zz[en_disco & con_dato].mean())
            frac = float((en_disco & con_dato).sum() / en_disco.sum())
            fracciones[nombre] = frac
            with self.subTest(tpi=nombre):
                self.assertAlmostEqual(float(est[nombre]), 1000.0 - media, places=9)
                self.assertEqual(bool(est[f"{nombre}_truncado"]), frac < U.frac("C_TPI_PCT"))
        # El borde: con el umbral igual a la fracción no se trunca («< 50 %») y con el siguiente doble sí. Así se
        # prueba también que el disco tiene exactamente los puntos a ≤ r del centro de la celda (haversine, NAS-9):
        # un disco centrado en otra latitud, o con otro conteo, cambia la fracción.
        for nombre, frac in fracciones.items():
            with self.subTest(borde=nombre):
                justo = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc, _UmbralTPI(U, frac)).iloc[0]
                self.assertFalse(bool(justo[f"{nombre}_truncado"]))
                arriba = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc,
                                             _UmbralTPI(U, np.nextafter(frac, np.inf))).iloc[0]
                self.assertTrue(bool(arriba[f"{nombre}_truncado"]))
        self.assertFalse(bool(est["tpi1_truncado"]))
        self.assertTrue(bool(est["tpi5_truncado"]))
        self.assertGreater(float(est["tpi1"]), 0.0)
        np.testing.assert_array_equal(EN.estandarizar_tpi([est["tpi1"], est["tpi5"]], [False, True], 10.0, 4.0),
                                      [(float(est["tpi1"]) - 10.0) / 4.0, 0.0])
        with self.assertRaises(ValueError):
            EN.estandarizar_tpi([1.0], [False], 0.0, 0.0)
        # D33: el TPI truncado no entra a la media ni al desvío (sí lo calculado con la parte con dato, que se guarda)
        self.assertEqual(EN.tpi_entra_a_estandarizar(est[["tpi1", "tpi5"]].to_numpy(dtype=np.float64),
                                                     est[["tpi1_truncado", "tpi5_truncado"]].to_numpy(dtype=bool)).tolist(),
                         [True, False])
        self.assertTrue(math.isfinite(float(est["tpi5"])))

    def test_info_estaciones_con_el_esquema(self):
        """``tipos.ESQUEMA_ESTACIONES_MC``: identidad, textos, K1, K3, z_s, celda, macrozona de la celda (TIP-11) y
        exclusiones (A8, NAS-12)."""
        U = _umbrales()
        centros, cod, macro, aoi = [], [], [], []
        for la in (-33.435, -33.445, -33.455):
            for lo in (-70.665, -70.655, -70.645):
                if (la, lo) == (-33.435, -70.645):
                    continue                                  # fuera de la grilla
                centros.append((la, lo))
                if (la, lo) == (-33.455, -70.665):
                    cod.append(0), macro.append("centro"), aoi.append("continente")         # sin comuna, heredada
                elif (la, lo) == (-33.435, -70.665):
                    cod.append(5104), macro.append("insular"), aoi.append("juan_fernandez")
                else:
                    cod.append(13101), macro.append("centro"), aoi.append("continente")
        celdas, _, _ = _grilla(centros, cod=cod, macro=macro, aoi=aoi)
        catalogo = pd.DataFrame({
            "codigo": ["330017", "330010", "330011", "330012", "330013", "330014", "330015", "330016"],
            "nombre": ["Fuera de rango", "Buena", "K3 falla", "Sin altitud", "Ilegible", "Sin comuna", "Isla",
                       "Fuera de la grilla"],
            "lat_txt": ["33.4452", "-33.4452", "-33.4448", "-33.4447", "abc", "-33.4551", "-33.4352", "-33.4352"],
            "lon_txt": ["-70.6451", "-70.6451", "-70.6553", "-70.6447", "-70.65", "-70.6649", "-70.6651",
                        "-70.6449"],
            "alt_txt": ["520", "520", "800", None, "520", "520", "520,0", "520"],
            "tipo": [None, "Sinóptica", None, None, None, None, None, None],
            "propietario": [None, "DMC", None, None, None, None, None, None],
            "omm": [None, "85574", None, None, None, None, None, None]})
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "plano.tif", lambda la, lo: np.full(la.shape, 520.0), norte=-33.428, oeste=-70.672,
                        filas=130, columnas=130)
        mz = fijados.macrozona_region(_AP)
        infos = EN.info_estaciones(catalogo, celdas, [t], U, macrozona_region=mz,
                                   conjuntos={"330010": tipos.Conjunto.V, "330011": "V2"})
        self.assertEqual(list(infos), sorted(catalogo["codigo"]))
        id_de = {c: int(i) for c, i in zip(centros, celdas["celda"])}
        b = infos["330010"]
        self.assertEqual((b.conjunto, b.macrozona, b.grupo, b.omm, b.tipo, b.propietario),
                         ("V", "centro", "G330010", True, "Sinóptica", "DMC"))
        self.assertEqual((b.k3_pasa, b.z_s, b.z_s_fuente, b.celda, b.excluida, b.motivo),
                         (True, 520.0, "catalogo", id_de[(-33.445, -70.645)], False, None))
        self.assertEqual((b.lat, b.lon, b.z_cat, b.rho_km), (-33.4452, -70.6451, 520.0, 0.1))
        e, n = numerico.utm19s(b.lat, b.lon)
        self.assertEqual((b.utm_e, b.utm_n), (float(e), float(n)))
        self.assertEqual((b.bloque, b.pix0, b.pix3, b.respaldo_16km, b.sin_fondo), ("", -1, -1, False, True))
        self.assertTrue(math.isnan(b.w0))
        c = infos["330011"]
        self.assertEqual((c.conjunto, c.k3_pasa, c.excluida, c.motivo, c.omm), ("V2", False, True, EN.MOTIVO_K3, False))
        self.assertTrue(math.isnan(c.z_s))
        d = infos["330012"]
        self.assertEqual((d.conjunto, d.k3_pasa, d.z_s, d.z_s_fuente, d.excluida), ("N", True, 520.0, "nasadem", False))
        f = infos["330013"]
        self.assertEqual((f.excluida, f.motivo, f.celda, f.macrozona, f.k3_pasa),
                         (True, EN.MOTIVO_COORDENADAS_ILEGIBLES, None, None, False))
        self.assertTrue(math.isnan(f.lat) and math.isnan(f.rho_km) and math.isnan(f.utm_e))
        g = infos["330014"]
        self.assertEqual((g.celda, g.macrozona, g.excluida), (id_de[(-33.455, -70.665)], None, False))     # D9
        h = infos["330015"]
        self.assertEqual((h.celda, h.macrozona, h.excluida, h.z_cat), (id_de[(-33.435, -70.665)], None, False,
                                                                       520.0))   # D16
        i = infos["330016"]
        self.assertEqual((i.celda, i.macrozona, i.excluida), (None, None, False))
        j = infos["330017"]
        self.assertEqual((j.lat, j.excluida, j.motivo, j.celda), (33.4452, True, EN.MOTIVO_FUERA_DE_RANGO, None))
        # D34 (NAS-17): fuera de la grilla es la que entra y no tiene celda; una excluida sin celda no lo es
        self.assertEqual({c for c, x in infos.items() if EN.fuera_de_la_grilla(x)}, {"330016"})
        self.assertFalse(EN.fuera_de_la_grilla(f) or EN.fuera_de_la_grilla(j) or EN.fuera_de_la_grilla(b))
        tabla = EN.tabla_estaciones(infos)
        tipos.validar_esquema(tabla, tipos.ESQUEMA_ESTACIONES_MC, nombre="estaciones")
        self.assertEqual(tabla.attrs["esquema"], tipos.ESQUEMA_ESTACIONES_MC.version)
        self.assertEqual(list(tabla["codigo"]), sorted(infos))
        self.assertEqual(int(tabla["celda"].isna().sum()), 3)
        self.assertEqual(int(tabla["omm"].sum()), 1)
        # NAS-18: conteos, en enteros de Python, de cada motivo (también los que no aparecen), fuera de la grilla y
        # sin macrozona (Ilegible, Sin comuna, Isla, Fuera de la grilla y Fuera de rango)
        por_motivo = dict.fromkeys([*EN.MOTIVOS, tipos.MotivoExclusion.SIN_FONDO.value], 0)
        por_motivo.update({EN.MOTIVO_COORDENADAS_ILEGIBLES: 1, EN.MOTIVO_FUERA_DE_RANGO: 1, EN.MOTIVO_K3: 1})
        esperadas = {"estaciones": 8, "excluidas": 3, "por_motivo": por_motivo, "sin_nasadem_con_fondo": 0,
                     "fuera_de_la_grilla": 1, "sin_macrozona": 5}
        self.assertEqual(tabla.attrs["declaraciones"], esperadas)
        self.assertEqual(EN.declaraciones_estaciones(infos), esperadas)
        hechas = tabla.attrs["declaraciones"]
        self.assertTrue(all(type(v) is int for k, v in hechas.items() if k != "por_motivo"))
        self.assertTrue(all(type(v) is int for v in hechas["por_motivo"].values()))
        vacia = EN.tabla_estaciones({})
        self.assertEqual(len(vacia), 0)
        self.assertEqual((vacia.attrs["declaraciones"]["estaciones"], vacia.attrs["esquema"]),
                         (0, tipos.ESQUEMA_ESTACIONES_MC.version))
        # catálogo sin OMM: None (MC-62)
        sin_omm = EN.info_estaciones(catalogo.drop(columns=["omm"]), celdas, [t], U, macrozona_region=mz,
                                     conjuntos={})
        self.assertIsNone(sin_omm["330010"].omm)
        # La columna presente sin ningún indicativo es como no traerla (NAS-12). Es lo que da
        # reloj_dmc.extraccion.leer_catalogo_dmc sin el campo: siempre trae «omm» («string») y conserva los «».
        n = len(catalogo)
        for vacia in ([None] * n, [""] * n, ["  "] * (n - 1) + [None], ["s/n"] * n, ["s/n", "-", "", None] * 2):
            with self.subTest(omm=vacia):
                cat = catalogo.assign(omm=pd.array(vacia, dtype="string"))
                otras = EN.info_estaciones(cat, celdas, [t], U, macrozona_region=mz, conjuntos={})
                self.assertEqual({i.omm for i in otras.values()}, {None})
                self.assertTrue(EN.tabla_estaciones(otras)["omm"].isna().all())
        # con algún indicativo: verdadero sólo con alguna cifra («s/n» y «-» no lo son)
        textos = ["s/n", " 85574 ", "", None, "-", "s/n", "85586", " "]
        mezcla = EN.info_estaciones(catalogo.assign(omm=pd.array(textos, dtype="string")), celdas, [t], U,
                                    macrozona_region=mz, conjuntos={})
        self.assertEqual({c: mezcla[c].omm for c in mezcla},
                         {c: c in ("330010", "330015") for c in catalogo["codigo"]})
        # Motivos y POL-5: sin coordenadas confirmadas antes de K4 si y sólo si el motivo es de los que Q2 cuenta como
        # «K3 deja sin coordenadas» (NAS-12, D36); y la equivalencia de etiquetas de hoy, hasta el enumerado único.
        # «sin_nasadem» (D37) se prueba en PruebasCoberturaNASADEM, con sus dos etiquetas.
        from meteo_combinada import politicas
        equivalencia = {None: None, EN.MOTIVO_SIN_Z_S: None, EN.MOTIVO_K3: politicas.MOTIVO_K3,
                        EN.MOTIVO_FUERA_DE_RANGO: politicas.MOTIVO_K3,
                        EN.MOTIVO_COORDENADAS_ILEGIBLES: politicas.MOTIVO_SIN_COORDENADAS}
        self.assertEqual(set(equivalencia) - {None}, set(EN.MOTIVOS) - {EN.MOTIVO_SIN_NASADEM})
        self.assertEqual({i.motivo for i in infos.values()} - {None},
                         {EN.MOTIVO_K3, EN.MOTIVO_FUERA_DE_RANGO, EN.MOTIVO_COORDENADAS_ILEGIBLES})
        for codigo, info in infos.items():
            with self.subTest(codigo=codigo):
                confirmadas, motivo = politicas._estado_coordenadas(info, frozenset())
                self.assertEqual(confirmadas, info.motivo not in EN.MOTIVOS_SIN_COORDENADAS_K3)
                self.assertEqual(motivo, equivalencia[info.motivo])
        # una macrozona desconocida en la grilla detiene
        rara = celdas.copy()
        rara["macrozona"] = pd.array(["otra"] + list(rara["macrozona"][1:]), dtype="string")
        with self.assertRaises(ValueError):
            EN.info_estaciones(catalogo, rara, [t], U, macrozona_region=mz, conjuntos={})
        with self.assertRaises(ValueError):
            EN.info_estaciones(pd.concat([catalogo, catalogo.iloc[:1]]), celdas, [t], U, macrozona_region=mz,
                               conjuntos={})


# ---------------------------------------------------------------------------------------------------------------
def _distancia_km(lat1, lon1, lat2, lon2):
    """Haversine con R = 6.371 km escrita aquí (camino propio, MC-60), para lo que no está en un borde exacto."""
    p1, p2 = math.radians(lat1), np.radians(np.asarray(lat2, dtype=np.float64))
    dl = np.radians(np.asarray(lon2, dtype=np.float64) - lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(np.minimum(a, 1.0)))


def _recorte(tesela, ventana):
    """La parte de una tesela dentro de una ventana de ``ventana_k3``, como TeselaDEM en memoria (NAS-16)."""
    n, s = min(_red(ventana["lat_norte"]), tesela.i_norte), max(_red(ventana["lat_sur"]), tesela.i_sur)
    o, e = max(_red(ventana["lon_oeste"]), tesela.j_oeste), min(_red(ventana["lon_este"]), tesela.j_este)
    f, c = slice(tesela.i_norte - n, tesela.i_norte - s + 1), slice(o - tesela.j_oeste, e - tesela.j_oeste + 1)
    return EN.TeselaDEM(nombre=f"recorte de {tesela.nombre}", sha256=tesela.sha256, i_norte=n, j_oeste=o,
                        z=tesela.z[f, c].copy(), dato=tesela.dato[f, c].copy())


class PruebasCoberturaNASADEM(unittest.TestCase):
    """D37 (NAS-16), D33 (NAS-9) y las declaraciones de NAS-18."""

    def test_d37_sin_tesela_a_rho_no_hay_prueba_k3(self):
        """D37: sin ninguna tesela a ≤ ρ no hay prueba K3. La estación queda fuera con «sin_nasadem», con z_cat y sin
        él; sale del numerador y del denominador de Q2 y se cuenta aparte. Una tesela a ≤ ρ sin dato sí es prueba K3:
        falla con z_cat y deja sin z_s sin él (D31). Las coordenadas fuera de rango van antes."""
        U = _umbrales()
        celdas, _, _ = _grilla([(-33.445, -70.645), (-33.305, -70.795)])
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "plano.tif", lambda la, lo: np.full(la.shape, 520.0), norte=-33.428, oeste=-70.672,
                        filas=130, columnas=130)
            vacia = _tesela(tmp, "vacia.tif", lambda la, lo: np.full(la.shape, 520.0), mascara=lambda la, lo: la > 0,
                            norte=-33.30, oeste=-70.80, filas=40, columnas=40)
        self.assertFalse(vacia.dato.any())
        catalogo = pd.DataFrame({
            "codigo": ["330020", "330021", "330022", "330023", "330024", "330025", "330026"],
            "nombre": ["Antártica", "Antártica sin altitud", "Al este de la tesela", "Tesela sin dato",
                       "Tesela sin dato, sin altitud", "Buena", "Fuera de rango"],
            "lat_txt": ["-62.19", "-62.19", "-33.4450", "-33.3050", "-33.3050", "-33.4452", "-16.50"],
            "lon_txt": ["-58.98", "-58.98", "-70.6330", "-70.7950", "-70.7950", "-70.6451", "-70.00"],
            "alt_txt": ["45", None, "520", "520", "s/i", "520", "520"]})
        mz = fijados.macrozona_region(_AP)
        infos = EN.info_estaciones(catalogo, celdas, [t, vacia], U, macrozona_region=mz, conjuntos={})
        self.assertEqual({c: (i.motivo, i.excluida, i.k3_pasa, i.z_s_fuente) for c, i in infos.items()}, {
            "330020": (EN.MOTIVO_SIN_NASADEM, True, False, "catalogo"),
            "330021": (EN.MOTIVO_SIN_NASADEM, True, True, "nasadem"),
            "330022": (EN.MOTIVO_SIN_NASADEM, True, False, "catalogo"),
            "330023": (EN.MOTIVO_K3, True, False, "catalogo"),
            "330024": (EN.MOTIVO_SIN_Z_S, True, True, "nasadem"),
            "330025": (None, False, True, "catalogo"),
            "330026": (EN.MOTIVO_FUERA_DE_RANGO, True, False, "catalogo")})
        self.assertTrue(all(math.isnan(infos[c].z_s) for c in ("330020", "330021", "330022", "330023", "330024")))
        # «Al este»: el punto de la tesela más cercano está a más de ρ (0,1 km), por un camino propio
        ii, jj = np.indices(t.z.shape)
        lejos = _distancia_km(-33.445, -70.633, (t.i_norte - ii) / P, (t.j_oeste + jj) / P).min()
        self.assertEqual(infos["330022"].rho_km, 0.1)
        self.assertTrue(0.2 < lejos < 0.4, lejos)
        # k3 sola da la regla literal (sin tesela es como sin dato); lo de D37 lo decide hay_tesela_a_rho
        rho_a = infos["330020"].rho_km
        self.assertEqual(EN.k3(-62.19, -58.98, 45.0, rho_a, [t, vacia], U)[0], False)
        pasa, z_s = EN.k3(-62.19, -58.98, math.nan, rho_a, [t, vacia], U)
        self.assertTrue(pasa and math.isnan(z_s))
        self.assertFalse(EN.hay_tesela_a_rho(-62.19, -58.98, rho_a, [t, vacia]))
        self.assertFalse(EN.hay_tesela_a_rho(-33.445, -70.633, 0.1, [t, vacia]))
        self.assertTrue(EN.hay_tesela_a_rho(-33.305, -70.795, 0.1, [vacia]))
        # la Antártica no tiene celda ni macrozona (D9), y no es «fuera de la grilla»: está excluida (NAS-17)
        a = infos["330020"]
        self.assertEqual((a.celda, a.macrozona, EN.fuera_de_la_grilla(a)), (None, None, False))
        # Q2 (D36 y D37): «sin_nasadem» no está en el numerador y sale también del denominador
        self.assertNotIn(EN.MOTIVO_SIN_NASADEM, EN.MOTIVOS_SIN_COORDENADAS_K3)
        self.assertEqual(EN.MOTIVOS_FUERA_DE_Q2, frozenset({EN.MOTIVO_SIN_NASADEM}))
        self.assertEqual(EN.MOTIVOS_SIN_COORDENADAS_K3, tipos.MOTIVOS_SIN_COORDENADAS_K3)
        self.assertEqual({c for c, i in infos.items() if i.motivo not in EN.MOTIVOS_FUERA_DE_Q2},
                         {"330023", "330024", "330025", "330026"})
        self.assertEqual({c for c, i in infos.items() if i.motivo in EN.MOTIVOS_SIN_COORDENADAS_K3},
                         {"330023", "330026"})
        # POL-5: con z_cat, «k3» y sin confirmar; sin z_cat, confirmadas (§2.5). Cambia la etiqueta, no Q2 (NAS-12)
        from meteo_combinada import politicas
        self.assertEqual(politicas._estado_coordenadas(infos["330020"], frozenset()), (False, politicas.MOTIVO_K3))
        self.assertEqual(politicas._estado_coordenadas(infos["330021"], frozenset()), (True, None))
        # se cuentan aparte (NAS-18), también las que el operador encontrara con fondo
        d = EN.tabla_estaciones(infos).attrs["declaraciones"]
        self.assertEqual((d["por_motivo"][EN.MOTIVO_SIN_NASADEM], d["sin_nasadem_con_fondo"], d["excluidas"]),
                         (3, 0, 6))
        con_fondo = dict(infos, **{"330022": dataclasses.replace(infos["330022"], sin_fondo=False)})
        self.assertEqual(EN.declaraciones_estaciones(con_fondo)["sin_nasadem_con_fondo"], 1)
        buena = infos["330025"]
        for rara in (dataclasses.replace(buena, excluida=True, motivo="otro"),
                     dataclasses.replace(buena, excluida=True, motivo=None),
                     dataclasses.replace(buena, excluida=False, motivo=EN.MOTIVO_K3)):
            with self.subTest(motivo=rara.motivo, excluida=rara.excluida), self.assertRaises(ValueError):
                EN.declaraciones_estaciones({"330025": rara})
        with self.assertRaises(TypeError):
            EN.info_estaciones(catalogo, celdas, [t, "vacia.tif"], U, macrozona_region=mz, conjuntos={})

    def test_d37_tesela_a_rho_inclusiva_y_ventana_k3(self):
        """NAS-16: «a ≤ ρ» de la tesela es inclusiva y mira su huella, con dato o sin él; ``ventana_k3`` contiene los
        puntos de la red a ≤ ρ y los de la bilineal, y las teselas recortadas a esas ventanas dan lo mismo."""
        U = _umbrales()
        lat, lon = -33.45, -70.65
        with tempfile.TemporaryDirectory() as tmp:
            se = _tesela(tmp, "sureste.tif", lambda la, lo: np.full(la.shape, 800.0),
                         mascara=lambda la, lo: lo > -70.62, norte=-33.46, oeste=-70.635, filas=60, columnas=80)
            grande = _tesela(tmp, "grande.tif",
                             lambda la, lo: 900.0 + 3000.0 * (la + 33.45) + 2000.0 * (lo + 70.65),
                             norte=-33.40, oeste=-70.72, filas=200, columnas=260)
        ii, jj = np.indices(se.z.shape)
        d = numerico.haversine_km(lat, lon, (se.i_norte - ii.ravel()) / P, (se.j_oeste + jj.ravel()) / P)
        d_min = float(d.min())
        self.assertTrue(1.0 < d_min < 2.0, d_min)
        self.assertFalse(se.dato.ravel()[int(np.argmin(d))])          # el punto más cercano no tiene dato
        self.assertTrue(EN.hay_tesela_a_rho(lat, lon, d_min, [se]))
        self.assertFalse(EN.hay_tesela_a_rho(lat, lon, d_min - 1e-9, [se]))
        pasa, z_s = EN.k3(lat, lon, 800.0, d_min, [se], U)                 # hay prueba, y falla (NAS-10)
        self.assertFalse(pasa)
        self.assertTrue(math.isnan(z_s))
        with self.assertRaises(ValueError):
            EN.hay_tesela_a_rho(lat, lon, 0.0, [se])
        # los cuatro lados de la huella: al norte, al sur, al este y al oeste de la tesela, cerca del medio del lado
        medio_i, medio_j = (se.i_norte + se.i_sur) / 2 / P, (se.j_oeste + se.j_este) / 2 / P
        for lado, (la, lo) in {"norte": (se.i_norte / P + 0.004, medio_j), "sur": (se.i_sur / P - 0.004, medio_j),
                               "este": (medio_i, se.j_este / P + 0.005), "oeste": (medio_i, se.j_oeste / P - 0.005)
                               }.items():
            with self.subTest(lado=lado):
                d_lado = float(numerico.haversine_km(la, lo, (se.i_norte - ii.ravel()) / P,
                                                     (se.j_oeste + jj.ravel()) / P).min())
                self.assertTrue(0.3 < d_lado < 0.6, d_lado)
                self.assertTrue(EN.hay_tesela_a_rho(la, lo, d_lado, [se]))
                self.assertFalse(EN.hay_tesela_a_rho(la, lo, d_lado - 1e-9, [se]))
        # ventana_k3 contiene los puntos de la red a ≤ ρ (haversine propia, con holgura) y los de la bilineal
        for la, lo, rho in ((-33.45, -70.65, 2.0), (-62.19, -58.98, 2.0), (-20.0, -70.1, 0.1),
                            (-55.9, -67.3, 0.7861)):
            with self.subTest(lat=la, rho=rho):
                v = EN.ventana_k3(la, lo, rho)
                II, JJ = np.meshgrid(np.arange(_red(la) - 200, _red(la) + 201),
                                     np.arange(_red(lo) - 400, _red(lo) + 401), indexing="ij")
                cerca = _distancia_km(la, lo, II / P, JJ / P) <= rho * (1 + 1e-9)
                self.assertTrue(cerca.any())
                self.assertFalse(cerca[0].any() or cerca[-1].any() or cerca[:, 0].any() or cerca[:, -1].any())
                self.assertLessEqual(int(II[cerca].max()), _red(v["lat_norte"]))
                self.assertGreaterEqual(int(II[cerca].min()), _red(v["lat_sur"]))
                self.assertLessEqual(int(JJ[cerca].max()), _red(v["lon_este"]))
                self.assertGreaterEqual(int(JJ[cerca].min()), _red(v["lon_oeste"]))
                i0, j0 = math.floor(la * P), math.floor(lo * P)
                self.assertTrue(_red(v["lat_sur"]) <= i0 and i0 + 1 <= _red(v["lat_norte"]))
                self.assertTrue(_red(v["lon_oeste"]) <= j0 and j0 + 1 <= _red(v["lon_este"]))
        # Las teselas recortadas a las ventanas de las estaciones dan las mismas InfoEstacion (NAS-16): con z_cat
        # dentro, sin z_cat junto al borde este y una sin tesela a ≤ ρ
        catalogo = pd.DataFrame({"codigo": ["330030", "330031", "330032", "330033"],
                                 "nombre": ["Dentro", "Gruesa", "Sin altitud", "Lejos"],
                                 "lat_txt": ["-33.4300", "-33.43", "-33.4471", "-33.4300"],
                                 "lon_txt": ["-70.6800", "-70.68", "-70.6489", "-70.6200"],
                                 "alt_txt": ["900", "900", None, "900"]})
        celdas, _, _ = _grilla([(-33.425, -70.675)])                    # la celda de «Dentro» y de «Gruesa»
        mz = fijados.macrozona_region(_AP)
        completas =EN.info_estaciones(catalogo, celdas, [grande], U, macrozona_region=mz, conjuntos={})
        recortes = []
        for fila in catalogo.itertuples():
            la, lo = EN.interpretar_coordenada(fila.lat_txt, "lat"), EN.interpretar_coordenada(fila.lon_txt, "lon")
            v = EN.ventana_k3(la, lo, EN.rho_km(fila.lat_txt, fila.lon_txt, U))
            if EN.hay_tesela_a_rho(la, lo, EN.rho_km(fila.lat_txt, fila.lon_txt, U), [grande]):
                recortes.append(_recorte(grande, v))
        self.assertEqual(len(recortes), 3)
        recortadas = EN.info_estaciones(catalogo, celdas, recortes, U, macrozona_region=mz, conjuntos={})
        pd.testing.assert_frame_equal(EN.tabla_estaciones(completas), EN.tabla_estaciones(recortadas),
                                      check_exact=True)
        self.assertEqual({c: i.motivo for c, i in completas.items()},
                         {"330030": None, "330031": None, "330032": None, "330033": EN.MOTIVO_SIN_NASADEM})
        self.assertEqual(completas["330031"].rho_km, 0.005 * KM_POR_GRADO * math.sqrt(2))
        self.assertTrue(math.isfinite(completas["330032"].z_s))
        self.assertEqual(completas["330030"].celda, int(celdas["celda"].iloc[0]))

    def test_d33_tpi_truncado_fuera_de_la_media_y_el_desvio(self):
        """D33: entran a la media y al desvío los TPI finitos y no truncados; el truncado vale 0 después (NAS-9)."""
        tpi = np.array([1.0, np.nan, 2.0, 3.0, -4.0])
        truncado = np.array([False, False, True, False, True])
        self.assertEqual(EN.tpi_entra_a_estandarizar(tpi, truncado).tolist(), [True, False, False, True, False])
        entra = EN.tpi_entra_a_estandarizar(tpi, truncado)
        media, desvio = float(tpi[entra].mean()), float(tpi[entra].std())
        self.assertEqual((media, desvio), (2.0, 1.0))
        np.testing.assert_array_equal(EN.estandarizar_tpi(tpi, truncado, media, desvio), [-1.0, np.nan, 0.0, 1.0, 0.0])
        with self.assertRaises(TypeError):                     # la columna booleana, no 0 y 1
            EN.tpi_entra_a_estandarizar([1.0], [0])
        with self.assertRaises(TypeError):
            EN.estandarizar_tpi([1.0], [1], 0.0, 1.0)
        with self.assertRaises(ValueError):
            EN.tpi_entra_a_estandarizar([1.0, 2.0], [False])


# ---------------------------------------------------------------------------------------------------------------
class PruebasLecturaYRed(unittest.TestCase):
    def test_lectura_de_textos_como_reloj(self):
        """NAS-1: ``interpretar_coordenada`` y el rango de RELOJ §3.3 son los del reloj (por AST, con su huella)."""
        from reloj_dmc import fijados as fijados_reloj
        nombres = ["_NUMERO", "_DECIMAL", "_SEXAGESIMAL", "_LETRAS", "_numero", "interpretar_coordenada"]
        espacio = fijados_reloj.extraer_por_ast(_RELOJ / "tablas.py", fijados.HUELLAS_RELOJ["tablas"],
                                                nombres, {"re": re})
        reloj = espacio["interpretar_coordenada"]
        textos = ["-33.45", "−33,45", " -33.4500 ", "+33.45", "33.45", "33°27' S", "33°27′12″ S", "33 27 12 S",
                  "33°27'12.5\" S", "33°27.5' S", "33.5°27' S", "33°27.5'12\" S", "-33°27'S", "+33°27'S", "33°61' S",
                  "70°39'W", "70°39'E", "70°39' N", "abc", "", "   ", None, "520", "520,5", "s/n", "-0.0", "33 S"]
        for texto in textos:
            for eje in ("lat", "lon", "alt"):
                with self.subTest(texto=texto, eje=eje):
                    self.assertEqual(EN.interpretar_coordenada(texto, eje), reloj(texto, eje))
        with self.assertRaises(ValueError):
            EN.interpretar_coordenada("1", "z")
        fuente = (_RELOJ / "constantes.py").read_bytes()
        self.assertEqual(hashlib.sha256(fuente).hexdigest(), fijados.HUELLAS_RELOJ["constantes"])
        valores = {}
        for nodo in ast.walk(ast.parse(fuente.decode("utf-8"))):
            if (isinstance(nodo, ast.Call) and getattr(nodo.func, "id", None) == "ConstanteTexto" and nodo.args
                    and isinstance(nodo.args[0], ast.Constant) and nodo.args[0].value in ("COORD_LAT", "COORD_LON")):
                valores[nodo.args[0].value] = ast.literal_eval(nodo.args[1])
        self.assertEqual(valores, {"COORD_LAT": EN.COORD_LAT_RELOJ, "COORD_LON": EN.COORD_LON_RELOJ})
        self.assertTrue(EN.coordenadas_en_rango(-17.0, -55.0) and EN.coordenadas_en_rango(-90.0, -110.0))
        self.assertFalse(EN.coordenadas_en_rango(-16.99, -70.0) or EN.coordenadas_en_rango(-33.0, -54.9))
        self.assertFalse(EN.coordenadas_en_rango(None, -70.0) or EN.coordenadas_en_rango(math.nan, -70.0))

    def test_leer_tesela_exige_huella_y_formato(self):
        """NAS-3: sha256 de los bytes leídos, formato del descargador y centros en la red."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.tesela_nasadem(Path(tmp) / "t.tif", lambda la, lo: np.full(la.shape, 7.0),
                                    mascara=lambda la, lo: _I(lo) < _red(-70.69), oeste=-70.70, norte=-33.40, filas=10,
                                    columnas=40)
            sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
            t = EN.leer_tesela(ruta, sha)
            self.assertEqual((t.nombre, t.sha256, t.i_norte, t.j_oeste), ("t.tif", sha, _red(-33.40), _red(-70.70)))
            self.assertEqual((t.z.dtype, t.z.shape, t.tile_id, t.aoi_id), (np.int16, (10, 40), "s34w071", "continente"))
            self.assertEqual(int(t.dato[0].sum()), 36)
            with self.assertRaises(ValueError):
                EN.leer_tesela(ruta, "0" * 64)
            with self.assertRaises(ValueError):
                EN.leer_tesela(ruta, sha.upper())
            ruta_g = S.tesela_ghs(Path(tmp) / "g.tif", lambda la, lo: np.full(la.shape, 3.0), filas=5, columnas=5)
            with self.assertRaises(ValueError):                 # no es NASADEM
                EN.leer_tesela(ruta_g, hashlib.sha256(ruta_g.read_bytes()).hexdigest())
            g = EN.leer_ghs(ruta_g, hashlib.sha256(ruta_g.read_bytes()).hexdigest())
            self.assertEqual((g.paso_m, g.pob.shape, g.nodata), (100.0, (5, 5), -200.0))
            with self.assertRaises(ValueError):                 # no es GHS
                EN.leer_ghs(ruta, sha)
            # Cada exigencia de NAS-3 por separado: una tesela de sintetico, retocada en la carpeta temporal con
            # rasterio («r+»), en lo que se prueba y en nada más. El control reescribe la etiqueta con su mismo valor.
            import rasterio
            from rasterio.transform import Affine

            def retocada(nombre, cambio):
                otra = S.tesela_nasadem(Path(tmp) / f"{nombre}.tif", lambda la, lo: np.full(la.shape, 7.0),
                                        oeste=-70.70, norte=-33.40, filas=10, columnas=12)
                with rasterio.open(otra, "r+") as ds:
                    cambio(ds)
                return otra, hashlib.sha256(otra.read_bytes()).hexdigest()

            def corrida(ds, d_lon, d_lat):
                a = ds.transform
                ds.transform = Affine(a.a, 0.0, a.c + d_lon * a.a, 0.0, a.e, a.f + d_lat * a.e)

            control = EN.leer_tesela(*retocada("control", lambda ds: ds.update_tags(producto=EN.PRODUCTO_NASADEM)))
            self.assertEqual((control.i_norte, control.j_oeste, int(control.dato.sum())), (_red(-33.40), _red(-70.70),
                                                                                           120))
            casos = {
                "producto": (lambda ds: ds.update_tags(producto="SRTMGL1_HGT"), "etiquetas"),
                "unidades": (lambda ds: ds.update_tags(vertical_units="feet"), "etiquetas"),
                "medio_paso_lon": (lambda ds: corrida(ds, 0.5, 0.0), "no cae en la red"),
                "medio_paso_lat": (lambda ds: corrida(ds, 0.0, 0.5), "no cae en la red"),
            }
            for nombre, (cambio, mensaje) in casos.items():
                with self.subTest(caso=nombre), self.assertRaisesRegex(ValueError, mensaje):
                    EN.leer_tesela(*retocada(nombre, cambio))

    def test_teselas_que_se_solapan(self):
        """NAS-4: un punto con dato en dos teselas debe valer lo mismo; sin tesela, no hay dato."""
        U = _umbrales()
        with tempfile.TemporaryDirectory() as tmp:
            a = _tesela(tmp, "a.tif", lambda la, lo: np.full(la.shape, 500.0), norte=-33.44, oeste=-70.66, filas=37,
                        columnas=37)
            b = _tesela(tmp, "b.tif", lambda la, lo: np.full(la.shape, 500.0), norte=-33.44, oeste=-70.65, filas=37,
                        columnas=37)
            c = _tesela(tmp, "c.tif", lambda la, lo: np.full(la.shape, 600.0), norte=-33.44, oeste=-70.65, filas=37,
                        columnas=37)
            # b con la máscara administrativa: sin dato en su mitad oeste, que es la que comparte con la celda de a
            b_mascara = _tesela(tmp, "b_mascara.tif", lambda la, lo: np.full(la.shape, 500.0), norte=-33.44,
                                oeste=-70.65, filas=37, columnas=37, mascara=lambda la, lo: _I(lo) >= _red(-70.645))
            a_mascara = _tesela(tmp, "a_mascara.tif", lambda la, lo: np.full(la.shape, 500.0), norte=-33.44,
                                oeste=-70.66, filas=37, columnas=37, mascara=lambda la, lo: _I(lo) < _red(-70.655))
        celdas, estaticas, lulc = _grilla([(-33.445, -70.655), (-33.445, -70.645)])
        est = EN.estaticos_celdas(celdas, [a, b], None, estaticas, lulc, U)
        self.assertEqual(list(est["z_media"]), [500.0, 500.0])
        self.assertEqual(list(est["frac_dato"]), [1.0, 1.0])
        with self.assertRaises(ValueError):                    # comparten la columna −70,65 con valores distintos
            EN.estaticos_celdas(celdas, [a, c], None, estaticas, lulc, U)
        solo_a = EN.estaticos_celdas(celdas, [a], None, estaticas, lulc, U)
        self.assertEqual(float(solo_a["frac_dato"].iloc[1]), 1 / 36)       # sólo la columna del borde oeste
        self.assertEqual(float(solo_a["z_media"].iloc[1]), 500.0)          # la media de esa columna, no sobre 1.296
        # Un punto sin dato en una tesela no pisa el dato de otra, en cualquier orden (NAS-4): las teselas con
        # máscaras distintas se completan. La columna compartida (−70,65) tiene dato sólo en a o sólo en b.
        ordenes = {(a, b_mascara): [1.0, 19 / 36], (b_mascara, a): [1.0, 19 / 36], (a_mascara, b): [18 / 36, 1.0],
                   (b, a_mascara): [18 / 36, 1.0], (a_mascara, b_mascara, a, b): [1.0, 1.0]}
        for orden, frac in ordenes.items():
            with self.subTest(orden=[x.nombre for x in orden]):
                junta = EN.estaticos_celdas(celdas, list(orden), None, estaticas, lulc, U)
                self.assertEqual(list(junta["z_media"]), [500.0, 500.0])
                self.assertEqual(list(junta["frac_dato"]), frac)
        mitades = EN.estaticos_celdas(celdas, [a_mascara, b_mascara], None, estaticas, lulc, U)
        self.assertEqual(list(mitades["frac_dato"]), [18 / 36, 18 / 36])
        self.assertEqual(list(mitades["z_media"]), [500.0, 500.0])
        sin_nada = EN.estaticos_celdas(celdas, [], None, estaticas, lulc, U)
        self.assertTrue(sin_nada["z_media"].isna().all() and (sin_nada["frac_dato"] == 0).all())
        self.assertEqual(sin_nada.attrs["declaraciones"]["celdas_sin_dato_nasadem"], 2)

    def test_nasadem_en_pixeles_con_los_bordes_de_3(self):
        """A9 y NAS-13: la huella [oeste, este) × [sur, norte) del píxel ERA5-Land, con bordes oeste y sur cerrados."""
        cat = S.catalogo_pixeles(-33.4, -70.6, 1, 1)
        oeste, sur = float(cat["cell_west"].iloc[0]), float(cat["cell_south"].iloc[0])
        este, norte = float(cat["cell_east"].iloc[0]), float(cat["cell_north"].iloc[0])
        i_s, i_n, j_o, j_e = _red(sur), _red(norte), _red(oeste), _red(este)

        def z(la, lo):
            ii, jj = _I(la), np.rint(np.asarray(lo) * P)
            return 1000.0 * (ii == i_s) + 7.0 * (ii == i_n) + 3.0 * (jj == j_o) + 5.0 * (jj == j_e)

        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "huella.tif", z, norte=norte, oeste=oeste, filas=i_n - i_s + 1, columnas=j_e - j_o + 1)
            media_oeste = _tesela(tmp, "mitad.tif", z, norte=norte, oeste=oeste, filas=i_n - i_s + 1,
                                  columnas=j_e - j_o + 1, mascara=lambda la, lo: _I(lo) < _red(-70.6))
        res = EN.nasadem_en_pixeles(cat, [t])
        self.assertEqual(list(res.columns), ["pixel_id", "z_nasadem", "frac_nasadem"])
        self.assertEqual(int(res["pixel_id"].iloc[0]), int(cat["pixel_id"].iloc[0]))
        self.assertEqual(float(res["z_nasadem"].iloc[0]), (360 * 1000 + 360 * 3) / 360 ** 2)
        self.assertEqual(float(res["frac_nasadem"].iloc[0]), 1.0)
        mitad = EN.nasadem_en_pixeles(cat, [media_oeste])
        self.assertEqual(float(mitad["frac_nasadem"].iloc[0]), 0.5)
        vacio = EN.nasadem_en_pixeles(cat, [])
        self.assertTrue(math.isnan(float(vacio["z_nasadem"].iloc[0])) and float(vacio["frac_nasadem"].iloc[0]) == 0)


class PruebasEstaticosResto(unittest.TestCase):
    def test_otros_estaticos_y_tablas_faltantes(self):
        """NAS-14: log(1 + distancia a la costa), cobertura del suelo de 2015, lat, macrozona_cod y cod_comuna de la
        grilla; una celda que falta en una tabla detiene."""
        U = _umbrales()
        self.assertEqual(U.a("C_ANIO_LULC"), 2015)
        celdas, estaticas, lulc = _grilla([(-33.445, -70.655), (-33.445, -70.645)], cod=[13101, 0],
                                          macro=["centro", "sin_region"])
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "a.tif", lambda la, lo: np.full(la.shape, 500.0), norte=-33.44, oeste=-70.66, filas=37,
                        columnas=73)
        est = EN.estaticos_celdas(celdas, [t], None, estaticas, lulc, U)
        tipos.validar_esquema(est, tipos.ESQUEMA_ESTATICAS_CELDA, nombre="estaticos")
        self.assertEqual(est.attrs["esquema"], tipos.ESQUEMA_ESTATICAS_CELDA.version)
        np.testing.assert_array_equal(est["celda"].to_numpy(), celdas["celda"].to_numpy())
        np.testing.assert_allclose(est["log_dist_costa"], np.log1p(estaticas["dist_costa_km"].astype(np.float64)),
                                   rtol=0, atol=1e-12)
        for q, c in enumerate(tipos.LULC):
            self.assertEqual(float(est[c].iloc[0]), float(np.float32(0.1 + q / 100)))       # 2015, no 2020
        self.assertEqual(list(est["lat"]), [-33.445, -33.445])
        self.assertEqual(list(est["macrozona_cod"]), [2, 5])
        self.assertEqual(list(est["cod_comuna"]), [13101, 0])
        with self.assertRaises(ValueError):
            EN.estaticos_celdas(celdas, [t], None, estaticas.iloc[:1], lulc, U)
        with self.assertRaises(ValueError):
            EN.estaticos_celdas(celdas, [t], None, estaticas, lulc[lulc["anio"] == 2020], U)
        corrida = celdas.copy()
        corrida["lat"] = corrida["lat"] + 0.001                 # centro que no es k/100 + 0,005
        with self.assertRaises(ValueError):
            EN.estaticos_celdas(corrida, [t], None, estaticas, lulc, U)

    def test_resultado_no_depende_del_lote(self):
        """NAS-15: las celdas juntas, de a una o en otro orden dan lo mismo, bit a bit; ``ventana_necesaria`` cubre
        lo que se usa."""
        U = _umbrales()
        centros = [(-33.445 - 0.01 * a, -70.655 + 0.01 * b) for a in range(3) for b in range(3)]
        celdas, estaticas, lulc = _grilla(centros)
        v = EN.ventana_necesaria(celdas)
        norte, oeste = v["lat_norte"], v["lon_oeste"]
        filas, columnas = _red(norte) - _red(v["lat_sur"]) + 1, _red(v["lon_este"]) - _red(oeste) + 1
        with tempfile.TemporaryDirectory() as tmp:
            t = _tesela(tmp, "relieve.tif",
                        lambda la, lo: 800.0 + 400.0 * np.sin(la * 300.0) * np.cos(lo * 250.0) + 2000.0 * (lo + 70.7),
                        mascara=lambda la, lo: (la + 33.47) ** 2 + (lo + 70.64) ** 2 > 0.0001, norte=norte,
                        oeste=oeste, filas=filas, columnas=columnas)
            _, g = _ghs(tmp, "ghs.tif", lambda la, lo: 5.0 + 100.0 * np.abs(np.sin(la * 900.0)), lat_centro=-33.455,
                        lon_centro=-70.645, filas=60, columnas=60)
        juntas = EN.estaticos_celdas(celdas, [t], [g], estaticas, lulc, U)
        orden = np.arange(len(celdas))[::-1]
        al_reves = EN.estaticos_celdas(celdas.iloc[orden].reset_index(drop=True), [t], [g],
                                       estaticas, lulc, U).iloc[orden].reset_index(drop=True)
        de_a_una = pd.concat([EN.estaticos_celdas(celdas.iloc[[q]], [t], [g], estaticas, lulc, U)
                              for q in range(len(celdas))], ignore_index=True)
        for otra in (al_reves, de_a_una):
            pd.testing.assert_frame_equal(juntas, otra, check_exact=True)
        self.assertTrue(juntas["tpi5_truncado"].eq(False).all())       # la tesela cubre los discos de 5 km
        self.assertGreater(juntas["pendiente_deg"].min(), 0.0)


if __name__ == "__main__":
    unittest.main()
