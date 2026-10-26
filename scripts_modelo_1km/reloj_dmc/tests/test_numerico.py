"""Pruebas de numerico.py (semilla, remuestreo y utilidades).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
Cada cálculo se contrasta con un caso conocido o con una fórmula escrita aquí por un camino propio.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import math  # noqa: E402
import unittest  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402
from fractions import Fraction  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import numerico  # noqa: E402,F401

SEMILLA_BASE = 20261022
VENTANA = tuple(range(-9, 10))


def _etiquetas_horarias(desde: datetime, hasta: datetime, saltar=()) -> np.ndarray:
    """Etiquetas horarias ingenuas en [desde, hasta), sin las fechas de ``saltar``."""
    salida, t = [], desde
    while t < hasta:
        if t.date() not in saltar:
            salida.append(t)
        t += timedelta(hours=1)
    return np.array(salida, dtype="datetime64[ns]")


class PruebasRemuestreo(unittest.TestCase):
    def test_p07_misma_semilla_mismas_replicas(self):
        """La semilla de §4.0 reproduce las mismas 200 réplicas."""
        etiquetas = _etiquetas_horarias(datetime(2019, 9, 8), datetime(2019, 10, 1),
                                        saltar={date(2019, 9, 14), date(2019, 9, 15)})
        bloques = numerico.bloques_de_dias(etiquetas, date(2019, 9, 8), 5)
        s = numerico.semilla(SEMILLA_BASE, "330020", 2019, "2019-09-2", "QFE")
        rep_1 = numerico.replicas_por_bloques(bloques, 200, numerico.generador(s))
        rep_2 = numerico.replicas_por_bloques(bloques, 200, numerico.generador(s))
        self.assertEqual(len(rep_1), 200)
        for a, b in zip(rep_1, rep_2):
            np.testing.assert_array_equal(a, b)

        # Reconstrucción independiente de la secuencia documentada: Generator(PCG64(semilla)),
        # rng.integers(0, B, size=B) por réplica sobre los bloques no vacíos ordenados, y las filas de
        # cada bloque sorteado en su orden.
        no_vacios = sorted(set(bloques.tolist()))
        filas = {b: [i for i, x in enumerate(bloques.tolist()) if x == b] for b in no_vacios}
        rng = np.random.Generator(np.random.PCG64(s))
        for replica in rep_1:
            sorteo = rng.integers(0, len(no_vacios), size=len(no_vacios))
            esperado = [i for k in sorteo for i in filas[no_vacios[k]]]
            self.assertEqual(replica.tolist(), esperado)

        # Otra unidad da otra semilla y otras réplicas.
        s_otra = numerico.semilla(SEMILLA_BASE, "330020", 2019, "2019-09-1", "QFE")
        self.assertNotEqual(s, s_otra)
        rep_otra = numerico.replicas_por_bloques(bloques, 200, numerico.generador(s_otra))
        self.assertTrue(any(not np.array_equal(a, b) for a, b in zip(rep_1, rep_otra)))

        # Fijación del flujo de PCG64 del intérprete fijado (numpy 2.2.6): si una versión nueva de numpy
        # cambiara la secuencia, las réplicas dejarían de ser reproducibles y esta prueba lo detecta.
        rng = numerico.generador(5606866727109337681)
        self.assertEqual(rng.integers(0, 7, size=7).tolist(), [6, 5, 1, 0, 2, 5, 2])
        self.assertEqual(rng.integers(0, 7, size=7).tolist(), [1, 3, 1, 0, 4, 6, 3])

        # Sin bloques: réplicas vacías.
        vacias = numerico.replicas_por_bloques(np.array([], dtype=np.int64), 3, numerico.generador(s))
        self.assertEqual([len(v) for v in vacias], [0, 0, 0])

    def test_p07_bloques_desde_el_primer_dia_de_la_unidad(self):
        """Bloques de 5 días desde el primer día calendario de la unidad."""
        # Parte 2019-09-2: empieza el 8 de septiembre (día del cambio); los datos, el 10.
        etiquetas = np.array(["2019-09-10T00:00", "2019-09-12T23:00", "2019-09-13T00:00",
                              "2019-09-17T23:00", "2019-09-18T05:00"], dtype="datetime64[ns]")
        bloques = numerico.bloques_de_dias(etiquetas, date(2019, 9, 8), 5)
        # Desde el 8: [8-12] → 0, [13-17] → 1, [18-22] → 2. Contando desde el primer dato (10), el 13
        # caería en el bloque 0 y el 18 en el 1.
        self.assertEqual(bloques.tolist(), [0, 0, 1, 1, 2])
        self.assertEqual(numerico.bloques_de_dias(etiquetas, date(2019, 9, 10), 5).tolist(), [0, 0, 0, 1, 1])

        # Año-régimen R0, no contiguo: se cuenta desde el 1 de enero (R-42).
        fechas = np.array([date(2019, 1, 1), date(2019, 1, 6), date(2019, 4, 6), date(2019, 9, 8),
                           date(2019, 9, 9)], dtype="datetime64[D]")
        bloques_r0 = numerico.bloques_de_dias(fechas, date(2019, 1, 1), 5)
        dias = [(date(2019, 1, 1) - date(2019, 1, 1)).days, 5, (date(2019, 4, 6) - date(2019, 1, 1)).days,
                (date(2019, 9, 8) - date(2019, 1, 1)).days, (date(2019, 9, 9) - date(2019, 1, 1)).days]
        self.assertEqual(bloques_r0.tolist(), [d // 5 for d in dias])
        self.assertEqual(len(set(bloques_r0.tolist())), 4)        # bloques no vacíos

        # El remuestreo sortea sólo entre bloques no vacíos y repone tantos como haya.
        for replica in numerico.replicas_por_bloques(bloques_r0, 50, numerico.generador(1)):
            sorteados = bloques_r0[replica]
            self.assertTrue(set(sorteados.tolist()) <= set(bloques_r0.tolist()))
            cambios = 1 + int(np.count_nonzero(np.diff(replica) != 1))
            self.assertLessEqual(cambios, 4)
            self.assertEqual(sum(1 for b in sorteados.tolist() if b == 50) % 2, 0)  # el bloque 50 va entero

        # Una fecha anterior al primer día es un error del llamador.
        with self.assertRaises(ValueError):
            numerico.bloques_de_dias(fechas, date(2019, 1, 2), 5)

    def test_semilla_formula_literal(self):
        """int.from_bytes(sha256('20261022|330020|2019|2019-09-2|QFE').digest()[:8], 'big')."""
        literal = int.from_bytes(hashlib.sha256(b"20261022|330020|2019|2019-09-2|QFE").digest()[:8], "big")
        self.assertEqual(literal, 5606866727109337681)
        self.assertEqual(numerico.semilla(SEMILLA_BASE, "330020", 2019, "2019-09-2", "QFE"), literal)
        literal_r0 = int.from_bytes(hashlib.sha256(b"20261022|330020|2019|R0|Ts").digest()[:8], "big")
        self.assertEqual(numerico.semilla(SEMILLA_BASE, "330020", 2019, "R0", "Ts"), literal_r0)
        literal_v = int.from_bytes(hashlib.sha256(b"20261022|330020|2019|V-af1b0e1b|QFE").digest()[:8], "big")
        self.assertEqual(numerico.semilla(SEMILLA_BASE, "330020", 2019, "V-af1b0e1b", "QFE"), literal_v)
        for args in ((SEMILLA_BASE, "330020", 2019, "2019-09-2", "qfe"),     # variable (R-13)
                     (SEMILLA_BASE, "330020", 2019, "2019-09", "QFE"),       # parte sin n
                     (SEMILLA_BASE, "330020", 2019, "2018-09-1", "QFE"),     # parte de otro año
                     (SEMILLA_BASE, "330020", 2019, "R2", "QFE"),
                     (float(SEMILLA_BASE), "330020", 2019, "R0", "QFE"),     # «20261022.0» cambiaría la cadena
                     (SEMILLA_BASE, "33|0020", 2019, "R0", "QFE")):
            with self.assertRaises(ValueError, msg=str(args)):
                numerico.semilla(*args)
        rng = numerico.generador(literal)
        self.assertIsInstance(rng, np.random.Generator)
        self.assertIsInstance(rng.bit_generator, np.random.PCG64)


class PruebasCorrelacion(unittest.TestCase):
    def test_pearson_doble_precision(self):
        """Sin redondeo; NaN con varianza nula."""
        x = [1, 2, 3, 4, 5]
        y = [Fraction("2.0"), Fraction("4.1"), Fraction("5.9"), Fraction("8.3"), Fraction("9.7")]
        mx, my = Fraction(sum(x), 5), sum(y) / 5
        sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
        sxx = sum((a - mx) ** 2 for a in x)
        syy = sum((b - my) ** 2 for b in y)
        exacto = float(sxy) / math.sqrt(float(sxx * syy))
        r = numerico.pearson(np.array(x, float), np.array([float(v) for v in y]))
        self.assertIsInstance(r, float)
        self.assertAlmostEqual(r, exacto, delta=4e-16)
        self.assertNotEqual(r, round(r, 6))                      # no se redondea

        rng = np.random.default_rng(7)
        a, b = rng.normal(size=500), rng.normal(size=500)
        b = 0.3 * a + b
        self.assertAlmostEqual(numerico.pearson(a, b), float(np.corrcoef(a, b)[0, 1]), delta=1e-14)

        self.assertTrue(math.isnan(numerico.pearson(np.full(10, 0.1), a[:10])))   # media inexacta, varianza 0
        self.assertTrue(math.isnan(numerico.pearson(a[:10], np.full(10, 3.0))))
        self.assertTrue(math.isnan(numerico.pearson(a[:2], b[:2])))               # n < 3
        with self.assertRaises(ValueError):
            numerico.pearson(a[:5], b[:6])

        # r(c) por desfase: los 19 valores son idénticos, bit a bit, a pearson fila por fila.
        dx = rng.normal(size=(19, 731))
        dy = 0.5 * dx[5] + rng.normal(size=731)
        dx[3] = 1.25                                             # una fila constante → NaN
        r_c = numerico.correlaciones_por_desfase(dy, dx)
        self.assertEqual(r_c.shape, (19,))
        for i in range(19):
            if i == 3:
                self.assertTrue(math.isnan(r_c[i]))
            else:
                self.assertEqual(r_c[i], numerico.pearson(dx[i], dy))
        self.assertEqual(numerico.maximo_estricto(r_c, VENTANA), VENTANA[5])

    def test_maximo_con_empate_exacto_es_none(self):
        """Un empate exacto deja ĉ indefinido."""
        r = 0.9 - 0.01 * (np.array(VENTANA) + 4.0) ** 2
        self.assertEqual(numerico.maximo_estricto(r, VENTANA), -4)
        empate = r.copy()
        empate[VENTANA.index(0)] = empate[VENTANA.index(-4)]
        self.assertIsNone(numerico.maximo_estricto(empate, VENTANA))
        self.assertIsNone(numerico.maximo_estricto(np.full(19, np.nan), VENTANA))
        con_nan = r.copy()
        con_nan[VENTANA.index(2)] = np.nan
        self.assertEqual(numerico.maximo_estricto(con_nan, VENTANA), -4)
        # Un empate exacto aparece cuando dos desfases ven la misma serie (p. ej., un eje repetido).
        rng = np.random.default_rng(3)
        dx = rng.normal(size=(19, 400))
        dx[VENTANA.index(8)] = dx[VENTANA.index(-4)]
        dy = dx[VENTANA.index(-4)] + 0.1 * rng.normal(size=400)
        self.assertIsNone(numerico.maximo_estricto(numerico.correlaciones_por_desfase(dy, dx), VENTANA))
        with self.assertRaises(ValueError):
            numerico.maximo_estricto(r[:18], VENTANA)

    def test_interpolacion_parabolica_y_limite_8(self):
        """ĉ_cont sólo si |ĉ| ≤ 8."""
        c = np.array(VENTANA, dtype=float)
        for c0, c_hat, esperado in ((-3.3, -3, -3.3), (0.2, 0, 0.2), (7.8, 8, 7.8), (-7.6, -8, -7.6),
                                    (8.7, 9, None), (-8.6, -9, None)):
            r = 0.9 - 0.01 * (c - c0) ** 2                        # una parábola exacta se recupera exacta
            self.assertEqual(numerico.maximo_estricto(r, VENTANA), c_hat)
            cont = numerico.interpolar_parabola(r, c_hat, VENTANA)
            if esperado is None:
                self.assertIsNone(cont)
            else:
                self.assertAlmostEqual(cont, esperado, delta=1e-12)
        # La fórmula, con valores no parabólicos: ĉ + (0,5 − 0,7)/(2(0,5 − 1,6 + 0,7)) = ĉ + 0,25.
        r = np.zeros(19)
        r[VENTANA.index(-5):VENTANA.index(-3) + 1] = [0.5, 0.8, 0.7]
        self.assertAlmostEqual(numerico.interpolar_parabola(r, -4, VENTANA), -3.75, delta=1e-12)
        self.assertIsNone(numerico.interpolar_parabola(r, None, VENTANA))

    def test_ventana_y_bytes_de_semilla_sin_literales(self):
        """La ventana sale de U.f("E3_VENTANA") y es la misma que usa lineas_fisicas; sin ventana, error.
        Los bytes de la semilla salen de constantes.SEMILLA_BYTES."""
        from reloj_dmc import constantes, lineas_fisicas

        class _U:
            def __init__(self, ancho):
                self.ancho, self.pedidos = ancho, []

            def f(self, ident):
                self.pedidos.append(ident)
                return self.ancho

        U = _U(9)
        self.assertEqual(numerico.desfases_ventana(U), VENTANA)
        self.assertEqual(U.pedidos, ["E3_VENTANA"])
        self.assertEqual(numerico.desfases_ventana(_U(5)), tuple(range(-5, 6)))
        self.assertEqual(lineas_fisicas.ventana(_U(7)), numerico.desfases_ventana(_U(7)))
        self.assertFalse(hasattr(numerico, "DESFASES_VENTANA"))
        with self.assertRaises(TypeError):
            numerico.maximo_estricto(np.zeros(19))                 # la ventana es un argumento obligatorio
        self.assertEqual(numerico._SEMILLA_BYTES, constantes.valor("SEMILLA_BYTES"))

    def test_alias_12h(self):
        """es_alias_12(8, -4) es True; es_alias_12(-8, -4) es False (ver R-01)."""
        # R-01 (diseño §7.1): con c = L − u (§2.1) y la definición de §4.3.1 (ĉ ≡ c_H mód 12, ĉ ≠ c_H),
        # el alias de 12 h de F(−4) en la ventana [−9, 9] es +8, no −8 como escribe la prueba 11 de §8.
        # Se prueba la definición; la redacción de la prueba 11 se corrige por enmienda.
        self.assertTrue(numerico.es_alias_12(8, -4))
        self.assertFalse(numerico.es_alias_12(-8, -4))
        self.assertTrue(numerico.es_alias_12(-8, 4))             # −8 es el alias de +4
        self.assertFalse(numerico.es_alias_12(-4, -4))           # ĉ = c_H no es alias
        alias_en_ventana = {c_h: {c for c in VENTANA if numerico.es_alias_12(c, c_h)}
                            for c_h in (0, -3, -4, -5, -6)}
        self.assertEqual(alias_en_ventana, {0: set(), -3: {9}, -4: {8}, -5: {7}, -6: {6}})
        self.assertTrue(numerico.es_alias_12(np.int8(9), np.int64(-3)))


class PruebasArmonicos(unittest.TestCase):
    @staticmethod
    def _senal(t, A1, phi1, A2, psi2, A3=0.0, phi3=0.0):
        return (A1 * np.cos(2 * np.pi * (t - phi1) / 24) + A2 * np.cos(2 * np.pi * 2 * (t - psi2) / 24)
                + A3 * np.cos(2 * np.pi * 3 * (t - phi3) / 24))

    def test_ajuste_armonico_fases_conocidas(self):
        """φ1 y ψ2 de una señal sintética exacta; EE × 2."""
        t = np.tile(np.arange(24.0), 30) + 0.37                  # hora solar desplazada, diseño balanceado
        for phi1, psi2 in ((14.5, 9.75), (23.8, 11.9), (0.2, 0.1)):
            a = self._senal(t, 2.0, phi1, 1.16, psi2, 0.3, 5.0)
            ajuste = numerico.ajuste_armonico(t, a, 3, 2.0)
            self.assertEqual((ajuste.K, ajuste.n), (3, len(t)))
            self.assertAlmostEqual(ajuste.phi1, phi1, delta=1e-9)
            self.assertAlmostEqual(ajuste.psi2, psi2, delta=1e-9)
            np.testing.assert_allclose(ajuste.amplitudes, (2.0, 1.16, 0.3), atol=1e-9)
            self.assertTrue(0 <= ajuste.phi1 < 24 and 0 <= ajuste.psi2 < 12)

        # Paso de 3 h: 8 horas distintas, K = mín(3, ⌊7/2⌋) = 3, recuperación exacta.
        t3 = np.tile(np.arange(0.0, 24.0, 3.0), 40)
        self.assertEqual(numerico.K_de_n_h(8, 3), 3)
        ajuste = numerico.ajuste_armonico(t3, self._senal(t3, 1.5, 15.2, 0.9, 9.75, 0.4, 2.0), 3, 2.0)
        self.assertAlmostEqual(ajuste.phi1, 15.2, delta=1e-9)
        self.assertAlmostEqual(ajuste.psi2, 9.75, delta=1e-9)

        # EE: con ruido conocido, EE(A_k) ≈ σ·√(2/n) en un diseño balanceado; el factor multiplica.
        rng = np.random.default_rng(11)
        sigma = 0.5
        a = self._senal(t, 2.0, 14.5, 1.16, 9.75) + sigma * rng.normal(size=len(t))
        uno = numerico.ajuste_armonico(t, a, 3, 1.0)
        dos = numerico.ajuste_armonico(t, a, 3, 2.0)
        np.testing.assert_allclose(dos.ee_amplitudes, 2 * np.array(uno.ee_amplitudes), rtol=1e-15)
        np.testing.assert_allclose(uno.ee_amplitudes, sigma * math.sqrt(2 / len(t)), rtol=0.15)
        np.testing.assert_allclose(uno.ee_amplitudes, uno.ee_amplitudes[0], rtol=1e-9)
        # EE independiente: σ̂ de los residuos y Var = σ̂²·2/n (diseño balanceado, XᵀX = n/2·I).
        X = np.column_stack([f(2 * np.pi * k * t / 24) for k in (1, 2, 3) for f in (np.cos, np.sin)])
        res = a - X @ np.linalg.lstsq(X, a, rcond=None)[0]
        sigma_hat = math.sqrt(float(res @ res) / (len(t) - 6))
        np.testing.assert_allclose(uno.ee_amplitudes, sigma_hat * math.sqrt(2 / len(t)), rtol=1e-9)

        self.assertIsNone(numerico.ajuste_armonico(t, a, 1, 2.0).psi2)
        with self.assertRaises(ValueError):                      # una sola hora: rango incompleto
            numerico.ajuste_armonico(np.full(50, 6.0), rng.normal(size=50), 1, 2.0)
        self.assertEqual([numerico.K_de_n_h(n, 3) for n in (24, 8, 7, 6, 4, 3, 2, 1, 0)],
                         [3, 3, 3, 2, 1, 1, 0, 0, 0])            # paso de 6 h → n_h = 4 → K = 1

    def test_quitar_armonico_24(self):
        """El residuo no tiene componente de 24 h."""
        rng = np.random.default_rng(5)
        t = np.tile(np.arange(24.0), 20)
        doce = 0.8 * np.cos(2 * np.pi * 2 * (t - 9.75) / 24)
        y = 1010.0 + 1.5 * np.cos(2 * np.pi * (t - 4.0) / 24) + doce + 0.2 * rng.normal(size=len(t))
        y[[7, 100, 333]] = np.nan
        residuo = numerico.quitar_armonico_24(t, y)
        self.assertTrue(np.array_equal(np.isnan(residuo), np.isnan(y)))
        ok = np.isfinite(residuo)
        X = np.column_stack([np.ones(ok.sum()), np.cos(2 * np.pi * t[ok] / 24), np.sin(2 * np.pi * t[ok] / 24)])
        np.testing.assert_allclose(X.T @ residuo[ok], 0.0, atol=1e-8)   # ortogonal a 1, cos y sen de 24 h
        X12 = np.column_stack([np.cos(4 * np.pi * t[ok] / 24), np.sin(4 * np.pi * t[ok] / 24)])
        amplitud_12 = float(np.hypot(*np.linalg.lstsq(X12, residuo[ok], rcond=None)[0]))
        self.assertAlmostEqual(amplitud_12, 0.8, delta=0.03)     # el armónico de 12 h queda

        # Sin ruido ni 12 h, el residuo es nulo; con paso de 12 h (diseño de rango incompleto), también.
        puro = 5.0 + 2.0 * np.cos(2 * np.pi * (t - 3.0) / 24)
        np.testing.assert_allclose(numerico.quitar_armonico_24(t, puro), 0.0, atol=1e-9)
        t12 = np.tile([0.0, 12.0], 30)
        np.testing.assert_allclose(numerico.quitar_armonico_24(t12, 5.0 + 2.0 * np.cos(2 * np.pi * t12 / 24)),
                                   0.0, atol=1e-9)
        # Horas absolutas (eje UTC desde 2000) dan lo mismo que la hora del día.
        np.testing.assert_allclose(numerico.quitar_armonico_24(t + 24 * 9000, y), residuo, atol=1e-8,
                                   equal_nan=True)

    def test_p13_ecuacion_del_tiempo_tabulada(self):
        """Spencer a ±1 min de valores tabulados."""
        # Extremos y ceros de la ecuación del tiempo (hora aparente − hora media), como los dan los
        # almanaques: −14 min 15 s el 11 feb, +3 min 41 s el 14 may, −6 min 30 s el 26 jul y
        # +16 min 25 s el 3 nov; ceros cerca del 15 abr, 13 jun, 1 sep y 25 dic (año 2019).
        tabulados = {date(2019, 2, 11): -(14 + 15 / 60), date(2019, 5, 14): 3 + 41 / 60,
                     date(2019, 7, 26): -6.5, date(2019, 11, 3): 16 + 25 / 60, date(2019, 4, 15): 0.0,
                     date(2019, 6, 13): 0.0, date(2019, 9, 1): 0.0, date(2019, 12, 25): 0.0}
        n = np.array([d.timetuple().tm_yday for d in tabulados])
        eot = numerico.ecuacion_del_tiempo_min(n)
        np.testing.assert_allclose(eot, list(tabulados.values()), atol=1.0)

        # Fórmula literal de §4.4, escrita aquí aparte.
        B = 2 * math.pi * (45 - 1) / 365
        literal = 229.18 * (0.000075 + 0.001868 * math.cos(B) - 0.032077 * math.sin(B)
                            - 0.014615 * math.cos(2 * B) - 0.040849 * math.sin(2 * B))
        self.assertAlmostEqual(float(numerico.ecuacion_del_tiempo_min(45)), literal, delta=1e-12)

        # Todo el año 2019 contra un algoritmo independiente de mayor precisión: la fórmula de Smart que
        # da Meeus (Astronomical Algorithms, cap. 28), a las 12 UTC de cada día.
        dias = np.arange(1, 366)
        jd = 2451544.5 + (date(2019, 1, 1) - date(2000, 1, 1)).days + (dias - 1) + 0.5
        T = (jd - 2451545.0) / 36525
        L0 = np.deg2rad(np.mod(280.46646 + T * (36000.76983 + 0.0003032 * T), 360))
        M = np.deg2rad(357.52911 + T * (35999.05029 - 0.0001537 * T))
        e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
        eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
        eps = np.deg2rad(eps0 + 0.00256 * np.cos(np.deg2rad(125.04 - 1934.136 * T)))
        yy = np.tan(eps / 2) ** 2
        E = (yy * np.sin(2 * L0) - 2 * e * np.sin(M) + 4 * e * yy * np.sin(M) * np.cos(2 * L0)
             - 0.5 * yy ** 2 * np.sin(4 * L0) - 1.25 * e ** 2 * np.sin(2 * M))
        meeus_min = 4 * np.rad2deg(E)
        np.testing.assert_allclose(meeus_min[n - 1], list(tabulados.values()), atol=0.15)  # el oráculo calza
        self.assertLessEqual(float(np.max(np.abs(numerico.ecuacion_del_tiempo_min(dias) - meeus_min))), 1.0)

    def test_hora_solar(self):
        """t0(L) = (hora decimal + λ/15 + EoT/60) mód 24, con n = día del año de la fecha de L."""
        def eot(n):
            B = 2 * math.pi * (n - 1) / 365
            return 229.18 * (0.000075 + 0.001868 * math.cos(B) - 0.032077 * math.sin(B)
                             - 0.014615 * math.cos(2 * B) - 0.040849 * math.sin(2 * B))
        etiquetas = np.array(["2019-01-01T12:00", "2019-01-01T02:00", "2019-07-15T12:30",
                              "2020-12-31T00:00", "2019-12-31T23:00"], dtype="datetime64[ns]")
        lon = -70.65
        esperado = [(12 + lon / 15 + eot(1) / 60) % 24, (2 + lon / 15 + eot(1) / 60) % 24,
                    (12.5 + lon / 15 + eot(196) / 60) % 24, (0 + lon / 15 + eot(366) / 60) % 24,
                    (23 + lon / 15 + eot(365) / 60) % 24]
        self.assertEqual(numerico.GRADOS_POR_HORA, 15.0)
        t0 = numerico.hora_solar(etiquetas, lon)
        np.testing.assert_allclose(t0, esperado, atol=1e-12)
        self.assertTrue(((t0 >= 0) & (t0 < 24)).all())
        # Con objetos datetime ingenuos da lo mismo.
        np.testing.assert_allclose(numerico.hora_solar(np.array([datetime(2019, 1, 1, 12)], dtype=object), lon),
                                   t0[:1], atol=1e-12)

    def test_circulares_y_envolturas(self):
        """[−6, 6), [−0,5; 0,5), media circular de período 1 h."""
        self.assertEqual(numerico.envolver(6.0, -6, 12), -6.0)
        self.assertEqual(numerico.envolver(-6.0, -6, 12), -6.0)
        self.assertAlmostEqual(numerico.envolver(5.999, -6, 12), 5.999, delta=1e-12)
        self.assertAlmostEqual(numerico.envolver(18.5, -6, 12), -5.5, delta=1e-12)
        self.assertEqual(numerico.envolver(0.5, -0.5, 1), -0.5)
        self.assertAlmostEqual(numerico.envolver(-0.7, -0.5, 1), 0.3, delta=1e-12)
        self.assertEqual(numerico.envolver(-1e-18, 0.0, 24.0), 0.0)   # borde por redondeo
        arr = numerico.envolver(np.array([-6.0, 0.0, 6.0, 13.0]), -6, 12)
        np.testing.assert_allclose(arr, [-6.0, 0.0, -6.0, 1.0])

        self.assertEqual(numerico.distancia_circular(23.0, 1.0, 24.0), 2.0)
        self.assertAlmostEqual(numerico.distancia_circular(0.2, 11.9, 12.0), 0.3, delta=1e-12)
        self.assertEqual(numerico.distancia_circular(3.0, 9.0, 12.0), 6.0)
        # E4p con F(−4): ψ2 = 5,75 h → ψ2 − c_H = 9,75 → δ = 0; con ψ2 = 1,75 → δ = 4.
        np.testing.assert_allclose(numerico.distancia_circular(np.array([5.75, 1.75]) + 4, 9.75, 12.0), [0.0, 4.0])

        self.assertAlmostEqual(numerico.media_circular(np.array([0.1, 0.2, 0.3]), 1.0), 0.2, delta=1e-12)
        self.assertEqual(numerico.media_circular(np.array([0.45, -0.45]), 1.0), -0.5)  # 0,5 → −0,5
        self.assertAlmostEqual(numerico.media_circular(np.array([0.4, 0.6]), 1.0), -0.5, delta=1e-12)
        self.assertAlmostEqual(numerico.media_circular(np.array([11.0, 1.0]), 12.0), 0.0, delta=1e-12)
        self.assertAlmostEqual(numerico.media_circular(np.array([-0.2, -0.3, 0.9]), 1.0), -0.2, delta=1e-12)
        self.assertTrue(math.isnan(numerico.media_circular(np.array([0.0, 0.5]), 1.0)))   # resultante nula
        self.assertTrue(math.isnan(numerico.media_circular(np.array([]), 1.0)))

        # Distancias: 1° de meridiano = 2πR/360; y contra haversine escrita aparte.
        self.assertAlmostEqual(float(numerico.distancia_km(-33.0, -70.0, np.array([-34.0]), np.array([-70.0]))[0]),
                               2 * math.pi * 6371.0088 / 360, delta=1e-9)
        rng = np.random.default_rng(2)
        lat2, lon2 = rng.uniform(-56, -17, 200), rng.uniform(-110, -66, 200)
        lat1, lon1 = -33.45, -70.66
        p1, l1, p2, l2 = map(np.deg2rad, (lat1, lon1, lat2, lon2))
        hav = 2 * 6371.0088 * np.arcsin(np.sqrt(np.sin((p2 - p1) / 2) ** 2
                                                + np.cos(p1) * np.cos(p2) * np.sin((l2 - l1) / 2) ** 2))
        np.testing.assert_allclose(numerico.distancia_km(lat1, lon1, lat2, lon2), hav, atol=1e-6)
        self.assertEqual(float(numerico.distancia_km(lat1, lon1, np.array([lat1]), np.array([lon1]))[0]), 0.0)

    def test_z_pixel_y_redondeo_hacia_cero(self):
        """z_pix de 1.013,25 hPa = 0 m; 0,5 → 0 y −0,5 → 0."""
        self.assertEqual(numerico.z_pixel(1013.25), 0.0)
        # Atmósfera estándar internacional: 898,76 hPa a 1.000 m y 500 hPa a unos 5.574 m.
        self.assertAlmostEqual(numerico.z_pixel(898.76), 1000.0, delta=1.0)
        self.assertAlmostEqual(numerico.z_pixel(500.0), 5574.0, delta=2.0)
        casos = {0.5: 0, -0.5: 0, 1.5: 1, -1.5: -1, 2.5: 2, -2.5: -2, 0.6: 1, -0.6: -1, 0.4: 0, -0.4: 0,
                 3.0: 3, -2.0: -2, 0.0: 0, 1.4999: 1, -1.5001: -2}
        for x, esperado in casos.items():
            resultado = numerico.redondear_empate_hacia_cero(x)
            self.assertEqual(resultado, esperado, msg=str(x))
            self.assertIs(type(resultado), int)
        with self.assertRaises(ValueError):
            numerico.redondear_empate_hacia_cero(float("nan"))


if __name__ == "__main__":
    unittest.main()
