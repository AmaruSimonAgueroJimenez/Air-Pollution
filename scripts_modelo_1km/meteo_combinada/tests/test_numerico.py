"""Pruebas de numerico.py (§2.3-§5): Magnus, presión, distancias, proyecciones y estadísticos.

Dueño: I3 (ola 1). Casos conocidos, sintéticos. La paridad de Magnus con ``meteo_civil_v3`` lee su fuente por AST
(código de APH con su huella; nada se importa ni se ejecuta salvo esa función); si falta, se omite con el motivo.
Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import math  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import constantes, numerico  # noqa: E402

_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
_METEO_CIVIL = _APH / "scripts_riesgo_agudo/v3_next/meteo_civil_v3.py"
_SHA_METEO_CIVIL = "483f63a634252fa383ae8a0abb3fd0e1472a73b67c8b36c1b2534a231f627bba"
SEMILLA = 20261023      # la del Anexo A; sólo como entrada de las pruebas


class PruebasHumedad(unittest.TestCase):
    def test_magnus_agua_hielo_e_inversa(self):
        """§2.4: e_s y e_i en 0 °C valen 6,112 hPa; Td = Magnus⁻¹ invierte e_s; HR(T, T) = 100."""
        self.assertEqual(float(numerico.magnus_agua(0.0)), 6.112)
        self.assertEqual(float(numerico.magnus_hielo(0.0)), 6.112)
        t = np.linspace(-45.0, 45.0, 181)
        self.assertTrue(np.allclose(numerico.td_desde_e(numerico.magnus_agua(t)), t, rtol=0, atol=1e-10))
        esperado = 6.112 * np.exp(17.625 * 20.0 / (243.04 + 20.0))
        self.assertAlmostEqual(float(numerico.magnus_agua(20.0)), esperado, places=12)
        esperado = 6.112 * np.exp(22.46 * -15.0 / (272.62 - 15.0))
        self.assertAlmostEqual(float(numerico.magnus_hielo(-15.0)), esperado, places=12)
        self.assertTrue(np.allclose(numerico.hr_desde(t, t), 100.0, rtol=0, atol=1e-10))
        td = t - 7.5
        self.assertTrue(np.allclose(numerico.td_desde_hr(numerico.hr_desde(t, td), t), td, rtol=0, atol=1e-9))

    def test_hr_sobre_hielo_respecto_del_agua_mc25(self):
        """MC-25 (NUM-1): «sobre hielo» lee Td como punto de escarcha y la HR es respecto del agua; sin recorte."""
        t, td = -10.0, -12.0
        self.assertAlmostEqual(float(numerico.hr_desde(t, td, hielo=True)),
                               100 * float(numerico.magnus_hielo(td)) / float(numerico.magnus_agua(t)), places=12)
        # Bajo 0 °C, e_i < e_s a la misma temperatura: leído como punto de escarcha, el mismo Td da menos HR.
        self.assertLess(float(numerico.hr_desde(t, td, hielo=True)), float(numerico.hr_desde(t, td)))
        self.assertGreater(float(numerico.hr_desde(10.0, 11.0)), 100.0)          # no recorta

    def test_paridad_de_magnus_con_meteo_civil_v3(self):
        """La HR de numerico, recortada en [0, 100], es la de ``meteo_civil_v3.humedad_relativa`` (17,625 y 243,04)."""
        if not _METEO_CIVIL.is_file():
            self.skipTest("falta meteo_civil_v3.py de APH; la prueba no se da por aprobada")
        from reloj_dmc import fijados as fijados_reloj
        extraido = fijados_reloj.extraer_por_ast(_METEO_CIVIL, _SHA_METEO_CIVIL,
                                                 ("MAGNUS_A", "MAGNUS_B", "humedad_relativa"), {"np": np})
        self.assertEqual((extraido["MAGNUS_A"], extraido["MAGNUS_B"]), constantes.valor("MAGNUS_AGUA")[1:])
        rng = np.random.default_rng(0)
        t = rng.uniform(-30, 40, 2000)
        td = t - rng.uniform(-2, 25, 2000)
        ref = extraido["humedad_relativa"](t, td)
        self.assertTrue(np.allclose(np.clip(numerico.hr_desde(t, td), 0, 100), ref, rtol=1e-13, atol=0))


class PruebasPresion(unittest.TestCase):
    def test_p_std_hipsometrica_y_presion_a_altitud(self):
        """§2.3 y §4.1: p_std(0) = 1.013,25; la hipsométrica es casi la inversa; p′ con 9,80665 y 287,05."""
        self.assertEqual(float(numerico.p_std(0.0)), 1013.25)
        self.assertAlmostEqual(float(numerico.p_std(1000.0)), 1013.25 * (1 - 2.25577e-5 * 1000.0) ** 5.25588, places=10)
        self.assertAlmostEqual(float(numerico.p_std(1000.0)), 898.75, delta=0.01)       # atmósfera estándar
        self.assertEqual(float(numerico.z_hipsometrica(1013.25)), 0.0)
        z = np.array([0.0, 500.0, 2000.0, 4465.0, 5000.0])
        self.assertTrue(np.allclose(numerico.z_hipsometrica(numerico.p_std(z)), z, rtol=0, atol=0.5))
        # §2.3: el centinela QFE 500,0 queda bajo p_std(z) − 80 hasta ≈ 4.465 m.
        self.assertLess(500.0, float(numerico.p_std(4400.0)) - 80)
        self.assertGreater(500.0, float(numerico.p_std(4500.0)) - 80)
        self.assertEqual(float(numerico.presion_a_altitud(850.0, 280.0, 0.0)), 850.0)
        esperado = 850.0 * math.exp(-9.80665 * 150.0 / (287.05 * 280.0))
        self.assertAlmostEqual(float(numerico.presion_a_altitud(850.0, 280.0, 150.0)), esperado, places=10)
        # Bajar y subir lo mismo con la misma T̄ vuelve al valor.
        p = numerico.presion_a_altitud(numerico.presion_a_altitud(850.0, 275.0, 300.0), 275.0, -300.0)
        self.assertAlmostEqual(float(p), 850.0, places=10)


class PruebasGeometria(unittest.TestCase):
    def test_haversine_utm_y_mollweide(self):
        """MC-60: R = 6.371 km; UTM 19S (EPSG:32719) y Mollweide (ESRI:54009, NUM-8)."""
        self.assertAlmostEqual(float(numerico.haversine_km(-33.0, -70.0, -34.0, -70.0)), math.pi * 6371 / 180, places=9)
        self.assertEqual(float(numerico.haversine_km(-33.0, -70.0, -33.0, -70.0)), 0.0)
        a = numerico.haversine_km(-33.0, -70.0, -20.0, -68.5)
        b = numerico.haversine_km(-20.0, -68.5, -33.0, -70.0)
        self.assertEqual(float(a), float(b))
        d = numerico.haversine_km(np.array([-33.0, -40.0])[:, None], np.array([-70.0, -72.0])[:, None],
                                  np.array([-33.0, -35.0, -50.0])[None, :], np.array([-70.0, -71.0, -73.0])[None, :])
        self.assertEqual(d.shape, (2, 3))
        # En el meridiano central de la zona 19 (−69°), E = 500.000 m; en el ecuador, N = 10.000.000 m (falso norte).
        e, n = numerico.utm19s(np.array([-33.45, 0.0]), np.array([-69.0, -69.0]))
        self.assertAlmostEqual(float(e[0]), 500000.0, places=4)
        self.assertAlmostEqual(float(n[1]), 10000000.0, places=4)
        self.assertTrue(float(e[0]) > float(numerico.utm19s(-33.45, -69.5)[0]))
        x, y = numerico.mollweide(np.array([0.0, 90.0, -90.0]), np.array([0.0, 0.0, 0.0]))
        self.assertAlmostEqual(float(x[0]), 0.0, places=6)
        self.assertAlmostEqual(float(y[1]), 6378137.0 * math.sqrt(2), places=1)
        self.assertAlmostEqual(float(y[2]), -6378137.0 * math.sqrt(2), places=1)


class PruebasEstadisticos(unittest.TestCase):
    def test_mediana_mad(self):
        """NUM-2: MAD sin escalar, sólo con los finitos."""
        self.assertEqual(numerico.mediana_mad([1, 2, 3, 4, 100]), (3.0, 1.0))
        self.assertEqual(numerico.mediana_mad([1, np.nan, 3, np.inf]), (2.0, 1.0))
        med, mad = numerico.mediana_mad([])
        self.assertTrue(math.isnan(med) and math.isnan(mad))

    def test_cuantil_ponderado_sin_interpolar_mc48(self):
        """MC-48: el menor valor cuyo peso acumulado alcanza q."""
        x, w = [4.0, 1.0, 3.0, 2.0], [1.0, 1.0, 1.0, 1.0]
        self.assertEqual(numerico.cuantil_ponderado(x, w, 0.5), 2.0)
        self.assertEqual(numerico.cuantil_ponderado(x, w, 0.95), 4.0)
        self.assertEqual(numerico.cuantil_ponderado(x, w, 0.75), 3.0)       # alcanza justo 3 de 4
        self.assertEqual(numerico.cuantil_ponderado([1.0, 2.0, 3.0], [0.0, 5.0, 0.0], 0.0), 2.0)
        self.assertEqual(numerico.cuantil_ponderado([1.0, 2.0, 3.0], [1.0, 1.0, 18.0], 0.95), 3.0)
        self.assertEqual(numerico.cuantil_ponderado([1.0, 2.0, 3.0], [18.0, 1.0, 1.0], 0.9), 1.0)
        valores = list(range(1, 21))
        self.assertEqual(numerico.cuantil_ponderado(valores, [1.0] * 20, 0.95), 19.0)
        for malo in (([1.0, np.nan], [1.0, 1.0], 0.5), ([1.0, 2.0], [1.0, -1.0], 0.5), ([1.0], [0.0], 0.5),
                     ([1.0, 2.0], [1.0], 0.5), ([1.0], [1.0], 1.5)):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                numerico.cuantil_ponderado(*malo)

    def test_armonico_recortado_recupera_y_recorta(self):
        """§4.3 (NUM-4): sin ruido recupera los coeficientes; con valores atípicos en las dos colas, el recorte del
        10 % y el segundo ajuste también."""
        h = np.tile(np.arange(24), 10).astype(float)
        coefs = np.array([1.5, 0.8, -0.4, 0.3, 0.2, -0.1, 0.05])
        r = numerico.valor_armonico(coefs, h)
        self.assertTrue(np.allclose(numerico.armonico_recortado(h, r, 3, 0.1), coefs, rtol=0, atol=1e-10))
        sucio = r.copy()
        sucio[[3, 40, 77, 120, 151, 200]] += 50.0
        sucio[[10, 55, 90, 133, 170, 230]] -= 50.0
        sin_recorte = numerico.armonico_recortado(h, sucio, 3, 0.0)
        self.assertFalse(np.allclose(sin_recorte, coefs, atol=1e-3))
        self.assertTrue(np.allclose(numerico.armonico_recortado(h, sucio, 3, 0.1), coefs, rtol=0, atol=1e-9))
        self.assertEqual(numerico.armonico_recortado(h, r, 2, 0.1).shape, (5,))
        for malo in ((h, r, 0, 0.1), (h, r, 2, 0.5), (h, r[:-1], 2, 0.1), (h[:3], r[:3], 2, 0.1)):
            with self.subTest(n=len(malo[0]), k=malo[2]), self.assertRaises(ValueError):
                numerico.armonico_recortado(*malo)

    def test_armonico_con_rango_deficiente_falla_h21(self):
        """H21 (NUM-4): menos horas distintas que coeficientes es un error explícito (DisenoDeficiente), en el primer
        ajuste y también cuando el recorte se lleva horas UTC enteras antes del segundo."""
        h = np.repeat([0.0, 8.0, 16.0], 30)
        r = np.cos(2 * np.pi * h / 24)
        with self.assertRaises(numerico.DisenoDeficiente):
            numerico.armonico_recortado(h, r, 2, 0.1)               # 3 horas distintas, 5 coeficientes
        self.assertTrue(issubclass(numerico.DisenoDeficiente, ValueError))
        # 12 horas distintas para k = 3 (7 coeficientes): 6 con 20 valores y 6 con un par ±100. El recorte del 10 %
        # (13 por cola) se lleva los 12 extremos, y quedan 6 horas distintas.
        rng = np.random.default_rng(3)
        llenas, pares = [0, 4, 8, 12, 16, 20], [2, 6, 10, 14, 18, 22]
        h = np.concatenate([np.repeat(llenas, 20), np.repeat(pares, 2)]).astype(float)
        r = np.concatenate([rng.normal(scale=0.01, size=120), np.tile([100.0, -100.0], 6)])
        numerico.armonico_recortado(h, r, 3, 0.0)                    # sin recorte, el primer ajuste tiene rango
        with self.assertRaisesRegex(numerico.DisenoDeficiente, "segundo"):
            numerico.armonico_recortado(h, r, 3, 0.1)

    def test_ridge_ponderado(self):
        """NUM-9: α = 0 es mínimos cuadrados; con α grande las pendientes van a 0 y la constante sin penalizar queda
        en la media."""
        rng = np.random.default_rng(1)
        x = rng.normal(size=(200, 3))
        x -= x.mean(axis=0)
        X = np.column_stack([np.ones(200), x])
        y = 2.0 + np.matmul(x, np.array([1.0, -0.5, 0.25])) + rng.normal(scale=0.1, size=200)
        w = rng.uniform(0.5, 2.0, 200)
        xtx, xty = np.matmul(X.T, w[:, None] * X), np.matmul(X.T, w * y)
        mco = np.linalg.solve(xtx, xty)
        self.assertTrue(np.allclose(numerico.ridge_ponderado(xtx, xty, 0.0), mco))
        fuerte = numerico.ridge_ponderado(xtx, xty, 1e12, sin_penalizar=1)
        self.assertAlmostEqual(float(fuerte[0]), float(np.sum(w * y) / np.sum(w)), places=6)
        self.assertTrue(np.all(np.abs(fuerte[1:]) < 1e-6))
        todo = numerico.ridge_ponderado(xtx, xty, 1e12)
        self.assertTrue(np.all(np.abs(todo) < 1e-6))
        with self.assertRaises(ValueError):
            numerico.ridge_ponderado(xtx, xty, -1.0)

    def test_hueco_circular_mc27(self):
        """MC-27: cada 3 h da 3; cada 5 h, 5; sobre la duración del día civil (23 h) también."""
        self.assertEqual(numerico.hueco_circular_max(range(0, 24, 3), 24), 3)
        self.assertEqual(numerico.hueco_circular_max(range(0, 24, 5), 24), 5)
        self.assertEqual(numerico.hueco_circular_max([23, 1], 24), 22)
        self.assertEqual(numerico.hueco_circular_max([1, 23], 24), 22)
        self.assertEqual(numerico.hueco_circular_max([24, 0, 25], 24), 23)
        self.assertEqual(numerico.hueco_circular_max([5], 24), 24)
        self.assertEqual(numerico.hueco_circular_max([], 24), 24)
        self.assertEqual(numerico.hueco_circular_max(range(0, 23, 3), 23), 3)
        self.assertEqual(numerico.hueco_circular_max(range(8, 20), 24), 13)       # aeródromo diurno
        with self.assertRaises(ValueError):
            numerico.hueco_circular_max([1], 0)

    def test_hueco_circular_rechaza_horas_no_enteras_h21(self):
        """H21 (NUM-5): una hora no entera no se trunca ([0; 4,9] daría 20); un flotante entero sí vale."""
        self.assertEqual(numerico.hueco_circular_max(np.array([0.0, 3.0]), 24), 21)
        for malo in ([0, 4.9], [0.5], [np.nan, 3], [True, False], ["3"]):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                numerico.hueco_circular_max(malo, 24)


class PruebasAzar(unittest.TestCase):
    def test_generador_por_subsecuencia_mc44(self):
        """MC-44 (NUM-6): la huella es el sha256 de la etiqueta «a/b»; mismo resultado sea cual sea el orden de las
        llamadas, y etiquetas distintas dan secuencias distintas."""
        huella = int.from_bytes(hashlib.sha256("internos/P2-4_83".encode("utf-8")).digest(), "big")
        esperado = np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEMILLA, huella]))).random(5)
        self.assertTrue(np.array_equal(numerico.generador(SEMILLA, "internos", "P2-4_83").random(5), esperado))
        self.assertTrue(np.array_equal(numerico.generador(SEMILLA, "internos/P2-4_83").random(5), esperado))
        a = numerico.generador(SEMILLA, "P1")
        b = numerico.generador(SEMILLA, "remuestreo")
        primero_a, primero_b = a.random(3), b.random(3)
        self.assertTrue(np.array_equal(numerico.generador(SEMILLA, "remuestreo").random(3), primero_b))
        self.assertTrue(np.array_equal(numerico.generador(SEMILLA, "P1").random(3), primero_a))
        self.assertFalse(np.array_equal(primero_a, primero_b))
        self.assertFalse(np.array_equal(numerico.generador(SEMILLA + 1, "P1").random(3), primero_a))
        for malo in ((SEMILLA,), (-1, "P1"), (True, "P1"), (SEMILLA, 3)):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                numerico.generador(*malo)

    def test_remuestreo_bloques(self):
        """NUM-7: réplicas × bloques, con reposición, de los ids ordenados, con la etiqueta «remuestreo»."""
        ids = ["4_83", "5_83", "4_84", "10_90", "5_83"]
        r = numerico.remuestreo_bloques(ids, 7, SEMILLA)
        self.assertEqual(r.shape, (7, 4))
        self.assertTrue(set(r.ravel()) <= set(ids))
        self.assertTrue(np.array_equal(r, numerico.remuestreo_bloques(list(reversed(ids)), 7, SEMILLA)))
        ordenados = np.array(sorted(set(ids)), dtype=object)
        esperado = ordenados[numerico.generador(SEMILLA, "remuestreo").integers(0, 4, size=(7, 4))]
        self.assertTrue(np.array_equal(r, esperado))
        muchos = numerico.remuestreo_bloques(ids, 500, SEMILLA)
        self.assertTrue(any(len(set(fila)) < 4 for fila in muchos))       # hay repeticiones: con reposición
        with self.assertRaises(ValueError):
            numerico.remuestreo_bloques([], 3, SEMILLA)
        with self.assertRaises(ValueError):
            numerico.remuestreo_bloques(ids, 0, SEMILLA)


if __name__ == "__main__":
    unittest.main()
