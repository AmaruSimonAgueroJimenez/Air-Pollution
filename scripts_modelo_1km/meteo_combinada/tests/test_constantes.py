"""Pruebas de constantes.py (anexo A2, repeticiones del Anexo A, exclusiones y lectura de números; §4.4 del diseño).

Dueño: I2 (ola 1). Leen, sin escribir, el texto vigente v2.4 y los archivos de M0 de APH con su sha256; si falta uno,
se omiten con el motivo y no se dan por aprobadas. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import constantes, umbrales  # noqa: E402

_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
_VIGENTE = _APH / umbrales.TEXTO_VIGENTE
# Lo que la regla de este módulo lee y la del reloj no: notación científica y fracciones (se declara: en eso se aparta).
_APARTE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹½¼¾⅓⅔]|\de[−+-]?\d")

# Las once definiciones que fijó el coordinador en la ola 0 para numerico (nombre → valor): no cambian.
DEFINICIONES_OLA_0 = {
    "MAGNUS_AGUA": (6.112, 17.625, 243.04), "MAGNUS_HIELO": (6.112, 22.46, 272.62),
    "P_STD": (1013.25, 2.25577e-05, 5.25588), "HIPSOMETRICA": (44330.8, 1013.25, 0.190263), "R_SECO": 287.05,
    "GRAVEDAD": 9.80665, "Q_ESPECIFICA": (0.622, 0.378), "Z_IMPLICITA": (29.27, 273.15, 0.0065), "KELVIN": 273.15,
    "NUDO_MS": (1852, 3600), "R_TIERRA_KM": 6371,
}


class _ConTexto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _VIGENTE.is_file():
            raise unittest.SkipTest(f"falta {_VIGENTE.name}; la prueba no se da por aprobada")
        cls.bytes_texto = _VIGENTE.read_bytes()
        if hashlib.sha256(cls.bytes_texto).hexdigest() != umbrales.SHA_TEXTO_VIGENTE:
            raise AssertionError(f"{_VIGENTE.name} no es el texto vigente v2.4")
        cls.texto = cls.bytes_texto.decode("utf-8")


class PruebasConstantes(_ConTexto):
    def test_carga_es_referencia_diagnostica_no_umbral_operativo(self):
        c = constantes.POR_NOMBRE["COSTO_CARGA_MAX"]
        self.assertEqual((c.valor, c.clase), (2, "definicion"))
        self.assertEqual(c.fragmento, "referencia diagnóstica histórica: carga < 2")
        self.assertIn(c.fragmento, self.texto)
        self.assertIn("[EMC4-1]", self.texto)

    def test_fragmentos_en_su_seccion(self):
        """Cada fragmento (A2, definiciones, repeticiones y exclusiones) está tal cual en su sección del v2.4 y sus
        números calzan con el valor, con sus ajenos y sus negativos."""
        self.assertEqual(constantes.verificar_contra_texto(self.texto), [])

    def test_verificacion_detecta_desvios(self):
        """Un número cambiado en el texto, un valor cambiado o un ajeno mal declarado hacen fallar la verificación."""
        texto = self.texto.replace("en más de 15 % en esta red", "en más de 16 % en esta red")
        self.assertTrue(any("SINCA_AVISO_PCT" in p for p in constantes.verificar_contra_texto(texto)))
        c = constantes.POR_NOMBRE["E0_FINITO_PCT"]
        for malo in (dataclasses.replace(c, valor=98), dataclasses.replace(c, ajenos=(1,)),
                     dataclasses.replace(c, seccion="§6.1"), dataclasses.replace(c, seccion="Anexo A"),
                     dataclasses.replace(c, seccion="§11"), dataclasses.replace(c, clase="otra")):
            otras = tuple(malo if x.nombre == c.nombre else x for x in constantes.CONSTANTES)
            with self.subTest(malo=malo), mock.patch.object(constantes, "CONSTANTES", otras):
                self.assertTrue(constantes.verificar_contra_texto(self.texto))
        p = constantes.POR_NOMBRE["P_STD"]
        sin_negativo = tuple(dataclasses.replace(p, negativos=()) if x.nombre == "P_STD" else x
                             for x in constantes.CONSTANTES)
        with mock.patch.object(constantes, "CONSTANTES", sin_negativo):
            self.assertTrue(any("P_STD" in m for m in constantes.verificar_contra_texto(self.texto)))
        duplicada = constantes.CONSTANTES + (constantes.CONSTANTES[0],)
        with mock.patch.object(constantes, "CONSTANTES", duplicada):
            self.assertTrue(any("repetido" in m for m in constantes.verificar_contra_texto(self.texto)))

    def test_completitud(self):
        """Ningún número de §2-§9 ni del Anexo B queda sin constante, repetición del Anexo A ni exclusión; un número
        nuevo en el cuerpo, o una entrada que falta, se detectan."""
        self.assertEqual(constantes.completitud(self.texto), [])
        nuevo = self.texto.replace("- **Evaluable:** ≥ 2.000 horas", "- **Evaluable:** ≥ 2.000 horas (y 37 días)")
        self.assertEqual(len(constantes.completitud(nuevo)), 2)          # el 37, y el 2.000 cuyo fragmento se rompió
        en_anexo_b = self.texto.replace("hasta 50 celdas por comuna", "hasta 50 celdas por comuna (o 41)")
        self.assertTrue(any("'41'" in p for p in constantes.completitud(en_anexo_b)))
        en_10 = self.texto.replace("## 10. Anclaje", "## 10. Anclaje (con 41 compuertas)")
        self.assertTrue(any("'41'" in p for p in constantes.completitud(en_10)))       # §10 es del cuerpo (CON-1)
        en_0 = self.texto.replace("en más del 50 % de sus horas de prueba", "en más del 41 % de sus horas de prueba")
        self.assertTrue(constantes.completitud(en_0))                                   # §0.4 también
        en_1 = self.texto.replace("579 estaciones, 87.190", "579 estaciones (41 más), 87.190")
        self.assertTrue(constantes.completitud(en_1))                                   # §1, con sus exclusiones
        for fuera in (self.texto.replace("*Earth and Space Science*, 7.", "*Earth and Space Science*, 7 y 41."),
                      self.texto.replace("Ts −40,0; QFE 500,0 (tolerancia 0,05)", "Ts −40,0; QFE 500,0 (tolerancia 0,06)")):
            self.assertNotEqual(fuera, self.texto)
            self.assertEqual(constantes.completitud(fuera), [])   # Referencias y Anexo A no son del A2
        for lista, nombre, cual in (("CONSTANTES", "nombre", "SINCA_AVISO_PCT"),
                                    ("REPETICIONES", "fragmento", "Dos reportes son consecutivos si distan ≤ 3 h"),
                                    ("NO_NORMATIVOS", "fragmento", "TROPOMI planean ≈ 276 GB")):
            sin = tuple(x for x in getattr(constantes, lista) if getattr(x, nombre) != cual)
            self.assertEqual(len(sin), len(getattr(constantes, lista)) - 1)
            with self.subTest(lista=lista), mock.patch.object(constantes, lista, sin):
                self.assertEqual(len(constantes.completitud(self.texto)), 1)

    def test_ajeno_sin_cubrir_se_detecta(self):
        """CON-3: un ajeno que no repite el propio valor necesita otra entrada (aquí, el 1 de «[1 − (sp̄/» de la
        hipsométrica, y el 2 de «z_cat/2», que es Z_IMPLICITA_DIVISOR)."""
        sin = tuple(x for x in constantes.NO_NORMATIVOS if x.fragmento != "[1 − (sp̄/")
        with mock.patch.object(constantes, "NO_NORMATIVOS", sin):
            problemas = constantes.completitud(self.texto)
        self.assertEqual(len(problemas), 1)
        self.assertIn("'1'", problemas[0])
        sin = tuple(x for x in constantes.CONSTANTES if x.nombre != "Z_IMPLICITA_DIVISOR")
        with mock.patch.object(constantes, "CONSTANTES", sin):
            problemas = constantes.completitud(self.texto)
        self.assertEqual(len(problemas), 1)
        self.assertIn("'2'", problemas[0])

    def test_paridad_de_numeros_con_el_reloj(self):
        """numeros_del_fragmento es la regla de reloj_dmc.constantes en los fragmentos de este texto sin notación
        científica ni fracciones; en esas dos cosas se aparta, a propósito: lee «·10⁻⁵», «10⁻⁶», «1e-9» y «½»."""
        from reloj_dmc import constantes as rc
        fragmentos = [x.fragmento for x in constantes.CONSTANTES + constantes.REPETICIONES + constantes.NO_NORMATIVOS]
        iguales = [f for f in fragmentos if not _APARTE.search(f)]
        self.assertGreater(len(iguales), 330)
        for f in iguales:
            with self.subTest(fragmento=f):
                self.assertEqual(constantes.numeros_del_fragmento(f), rc.numeros_del_fragmento(f))
        distintos = [f for f in fragmentos if _APARTE.search(f)
                     and constantes.numeros_del_fragmento(f) != rc.numeros_del_fragmento(f)]
        self.assertTrue(distintos)
        self.assertTrue(all(_APARTE.search(f) for f in distintos))
        self.assertEqual(constantes.numeros_del_fragmento("k(x,s) = exp(−½ (d_ef/L)²)"), [-0.5])
        self.assertEqual(rc.numeros_del_fragmento("k(x,s) = exp(−½ (d_ef/L)²)"), [])
        self.assertEqual(constantes.numeros_del_fragmento("π = ½ π^mon + ½ π^pob y ¼, ¾, ⅓ o ⅔"),
                         [0.5, 0.5, 0.25, 0.75, 1 / 3, 2 / 3])
        f = constantes.numeros_del_fragmento
        self.assertEqual(f("p_std(z) = 1.013,25 · (1 − 2,25577·10⁻⁵ · z)^5,25588"), [1013.25, 1, -2.25577e-05, 5.25588])
        self.assertEqual(f("un valor > 10⁻⁶ es un error"), [1e-06])
        self.assertEqual(f("dentro de 1e-9, en un año"), [1e-09])
        self.assertEqual(f("con d decimales, 0,5·10⁻ᵈ grados"), [0.5, 10])
        self.assertEqual(f("≈ 2,0·10¹¹ celda-horas"), [2e11])
        self.assertEqual(f("σ² y 2² y t2m y A1"), [])

    def test_anexo_a2(self):
        """anexo_a2.json: id, valor, sección, fragmento y clase de cada constante, con el sha256 del texto; se niega con
        otra huella o con un texto que no calza."""
        sha = hashlib.sha256(self.bytes_texto).hexdigest()
        a2 = constantes.anexo_a2(self.texto, sha)
        self.assertEqual(a2["schema"], constantes.ESQUEMA_ANEXO_A2)
        self.assertEqual(a2["texto_sha256"], umbrales.SHA_TEXTO_VIGENTE)
        ids = [c["id"] for c in a2["constantes"]]
        self.assertEqual(ids, [c.nombre for c in constantes.CONSTANTES])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({c["clase"] for c in a2["constantes"]}, set(constantes.CLASES))
        for c in a2["constantes"]:
            self.assertIn(c["fragmento"], self.texto)
        self.assertEqual(len(a2["repeticiones_del_anexo_a"]), len(constantes.REPETICIONES))
        self.assertEqual(len(a2["no_normativos"]), len(constantes.NO_NORMATIVOS))
        datos = json.dumps(a2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        self.assertEqual(json.loads(datos), a2)
        self.assertNotIn(chr(64), datos)
        self.assertNotIn("/" + "Users" + "/", datos)
        p_std = next(c for c in a2["constantes"] if c["id"] == "P_STD")
        self.assertEqual((p_std["ajenos"], p_std["negativos"], p_std["no_leidos"]), ([1], [1], []))
        c_per = next(c for c in a2["constantes"] if c["id"] == "C_PERIODOS")
        self.assertEqual([x["literal"] for x in c_per["no_leidos"]], ["2πh", "4πh", "2π", "4π"])
        self.assertTrue(all({"ajenos", "negativos", "no_leidos"} <= set(c) for c in a2["constantes"]))
        self.assertTrue(all({"ajenos", "negativos", "no_leidos"} <= set(c) for c in a2["repeticiones_del_anexo_a"]))
        with self.assertRaises(ValueError):
            constantes.anexo_a2(self.texto, "0" * 64)
        otro = self.texto.replace("en más de 15 % en esta red", "en más de 16 % en esta red")
        with self.assertRaises(ValueError):
            constantes.anexo_a2(otro, hashlib.sha256(otro.encode("utf-8")).hexdigest())

    def test_lo_que_pide_el_diseno_esta_en_el_a2(self):
        """§4.4 del diseño: los ejemplos de lo que entra al A2 están, con su valor."""
        v = constantes.valor
        esperados = {"TF_COTAS_T": (0.05, 0.15, 0.05, 0.15), "TF_COTAS_TD": (0.1, 0.25, 0.1, 0.25),
                     "TF_COTAS_RAPIDEZ": (0.05, 0.15, 0.05, 0.15), "TF_COTAS_P": (0.1, 0.3, 0.1, 0.3),
                     "TF1_RED_HISTORICA": (2000, 2000, 2009), "TF2_RED_R2000_2025": (50, 22, 26, 2000, 2025),
                     "TF2_RED_MIN_ESTACIONES": 10, "TF2_RED_R2003_2025": (80, 2003, 2025),
                     "TF2_RED_R2010_2025": (80, 2010, 2025), "TF1_ESCENARIO_CAMBIO": (2015, 2019, 2020, 2024),
                     "TF1_ESCENARIO_COMPLETO": (2015, 2024), "TF_CERO_TOL": 1e-06, "DERIVA_K_DECADA": 0.3,
                     "DERIVA_ANIO": 2010, "S6_RED": (20, 2000, 2009, 120, 2010, 2024), "S6_SESGO_K": -1.5,
                     "PIXEL_MESES_VALIDEZ": (200001, 201307, 202507), "E5L_T_K": (200, 330),
                     "E5L_SP_PA": (40000, 110000), "E5L_UV_MS": 30, "ESTRATO_ALTITUD_M": (500, 2000),
                     "ESTRATO_PERIODOS": (2000, 2009, 2010, 2026), "ANOMALIA_PERIODO": (2010, 2023),
                     "CD_MIN_VALORES": 10, "EX_CUANTILES_AGUDO": (5, 10, 90, 95), "E0_FINITO_PCT": 99,
                     "SINCA_AVISO_PCT": 15, "REPRES_CORRELACION_MIN": 0.8, "REPRES_COCIENTE": (0.5, 2),
                     "S1_RACHA_HR100_NO_H": 20, "S1_RACHA_HR100_SI_H": 50, "S4_TRASLADOS_M": (15, 5),
                     "S4_BAROMETRO_HPA": 1.5, "S5_RMSE_A_K": 0.3, "S5_SALTO_A_K": 0.2, "S14_TOLERANCIA": 1e-09,
                     "S15_EXTREMOS": (470, 1085, -60, 50, 60), "M6_CONDICIONES": 7, "M6_SIGMA2": "½·σ²",
                     "SECO_MIN_REPORTES": 3, "ERRATA_MUESTRA": (20, 20), "NUCLEO_MEDIO": 0.5, "S_PAR_PESO": 0.5,
                     "PI_AMBIENTAL": (0.5, 0.5), "GHS_RESOLUCION_M": 100, "GHS_PRODUCTO": "GHS-POP R2023A",
                     "AGUDO_NUDOS_COMUNAS": 343, "EX_CUANTILES_AMBIENTAL": (95, 5), "EX_CUANTIL_RAPIDEZ": 95,
                     "EX_CUANTILES_DESCRIPTIVOS": (95, 5), "EX_ACIERTO_CUANTIL": 95, "K1_RAIZ_DE": 2,
                     "C_PERIODOS": ((1, 24), (2, 24), (1, 365.25), (2, 365.25)), "Z_IMPLICITA_DIVISOR": 2,
                     "TF1_DELTA_C": "[media 2020-24 − media 2015-19]_cambio − [lo mismo]_completo",
                     "A_SEGUNDO_AJUSTE": 1, "S14_ANIOS": 1, "M6_TF_VERIFICACION_MESES": 1, "M6_TF_LOTE_MESES": 1}
        for nombre, esperado in esperados.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(v(nombre), esperado)
                self.assertIs(type(v(nombre)), type(esperado))
        with self.assertRaises(KeyError):
            v("NO_EXISTE")

    def test_definiciones_de_la_ola_0_no_cambian(self):
        """Los nombres y valores que usa numerico (ola 0, coordinador) siguen iguales."""
        for nombre, esperado in DEFINICIONES_OLA_0.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(constantes.valor(nombre), esperado)
                self.assertEqual(constantes.POR_NOMBRE[nombre].clase, "definicion")

    def test_secciones_del_texto(self):
        """«### n.m », «## n. » y «## Anexo B.»: cada sección desde su encabezado hasta el siguiente de su nivel."""
        a, b = constantes.tramo_de_seccion(self.texto, "§2.4")
        self.assertTrue(self.texto[a:b].startswith("### 2.4 "))
        self.assertTrue(self.texto[b:].startswith("### 2.5 "))
        a, b = constantes.tramo_de_seccion(self.texto, "§9")
        self.assertTrue(self.texto[a:b].startswith("## 9. "))
        self.assertTrue(self.texto[b:].startswith("## 10. "))
        a, b = constantes.tramo_de_seccion(self.texto, "Anexo B")
        self.assertTrue(self.texto[b:].startswith("## Referencias"))
        a, b = constantes.tramo_de_seccion(self.texto, "§2")
        self.assertTrue(self.texto[b:].startswith("## 3. "))
        a, b = constantes.tramo_de_seccion(self.texto, "§0.4")
        self.assertTrue(self.texto[a:b].startswith("### 0.4 "))
        a, b = constantes.tramo_de_seccion(self.texto, "§10")
        self.assertTrue(self.texto[b:].startswith("## Anexo A."))
        for desconocida in ("§11", "§2.9", "Anexo Z", "2.4"):
            self.assertIsNone(constantes.tramo_de_seccion(self.texto, desconocida))
        self.assertEqual(constantes.SECCIONES_NORMATIVAS, tuple(f"§{n}" for n in range(11)) + ("Anexo B",))

    def test_lo_que_la_regla_no_lee(self):
        """CON-11 y CON-13: «3L», «Q95», «2πh», «una vez más», «en un año» y «en un mes» están declarados en una
        entrada; cambiarlos se detecta, y una cifra pegada nueva sin declarar falla la completitud."""
        cambios = [("si d_ef ≤ 3L y s", "si d_ef ≤ 4L y s"), ("|sesgo del Q95 del", "|sesgo del Q90 del"),
                   ("sobre su propio Q95)", "sobre su propio Q90)"), ("y se ajusta\n  una vez más", "y se ajusta\n  dos veces más"),
                   ("dentro de 1e-9, en un año", "dentro de 1e-9, en dos años"), ("se verifica en un mes", "se verifica en dos meses"),
                   ("Por lotes de un mes", "Por lotes de dos meses"), ("de 4πh/24", "de 6πh/24"),
                   ("| TF1: media / P95 |", "| TF1: media / P90 |")]
        for viejo, nuevo in cambios:
            self.assertEqual(self.texto.count(viejo), 1, viejo)
            otro = self.texto.replace(viejo, nuevo)
            with self.subTest(cambio=nuevo):
                self.assertTrue(constantes.verificar_contra_texto(otro) + constantes.completitud(otro))
        nuevo = self.texto.replace("Rejilla de 75 km en UTM 19S", "Rejilla de 75 km en UTM 19S, cada 5L")
        self.assertTrue(any("'5L'" in p for p in constantes.completitud(nuevo)))
        self.assertEqual([constantes.valor_de_literal(x) for x in ("3L", "Q05", "P95", "2πh", "4π", "19S", "una vez más",
                                                                     "en un año", "R2023A", "texto")],
                         [3, 5, 95, 1, 2, 19, 1, 1, 2023, None])
        c = constantes.POR_NOMBRE["EX_CUANTIL_RAPIDEZ"]
        for malo in (dataclasses.replace(c, valor=90), dataclasses.replace(c, pegados=(("Q90", 0),)),
                     dataclasses.replace(c, pegados=(("Q95", 3),)), dataclasses.replace(c, pegados=())):
            otras = tuple(malo if x.nombre == c.nombre else x for x in constantes.CONSTANTES)
            with self.subTest(malo=malo.pegados), mock.patch.object(constantes, "CONSTANTES", otras):
                self.assertTrue(constantes.verificar_contra_texto(self.texto) + constantes.completitud(self.texto))

    def test_mascaras_no_ocultan_unidades(self):
        """CON-14: una máscara no oculta un número con unidad («la marca 14 y 9 h» deja ver el 9; «marca 14 h» falla)."""
        lista = self.texto.replace("salvo la marca 14.", "salvo la marca 14 y 9 h.")
        self.assertTrue(any("'9'" in p for p in constantes.completitud(lista)))
        pegada = self.texto.replace("salvo la marca 14.", "salvo la marca 14 h.")
        self.assertTrue(any("seguida de una unidad" in p for p in constantes.completitud(pegada)))
        self.assertEqual(constantes._enmascarados_con_unidad(self.texto, constantes._regiones(self.texto)), [])


class PruebasRepeticiones(_ConTexto):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.U = umbrales.cargar_m0(_APH)

    def test_repeticiones_coinciden_con_el_anexo_a(self):
        """Cada frase del cuerpo que repite un umbral del Anexo A vale lo mismo que su id (y existe el id)."""
        self.assertEqual(constantes.verificar_repeticiones(self.U.valores), [])
        for c in constantes.REPETICIONES:
            for ref in c.repite:
                nombre = re.sub(r"\[\d+\]$", "", ref)
                self.assertTrue(nombre in self.U.valores or nombre in constantes.POR_NOMBRE, ref)
        otros = dict(self.U.valores)
        otros["CONSECUTIVO_H"] = 4
        self.assertTrue(any("CONSECUTIVO_H" in p for p in constantes.verificar_repeticiones(otros)))
        del otros["CONSECUTIVO_H"]
        self.assertTrue(constantes.verificar_repeticiones(otros))

    def test_pesos_ambientales_literales_del_anexo_a(self):
        """CON-12: los ½ de π en lo ambiental son literales en la fila «Pesos» del Anexo A; PI_AMBIENTAL los repite."""
        filas = json.loads((_APH / umbrales.JSON_M0).read_text(encoding="utf-8"))["anexo_a"]
        (pesos,) = [f["texto"] for f in filas if f["grupo"] == "Pesos"]
        self.assertIn("ambiental ½ monitores + ½ población", pesos)
        self.assertEqual(constantes.valor("PI_AMBIENTAL"), (constantes.FRACCIONES["½"],) * 2)

    def test_cuerpo_0_4_y_10(self):
        """CON-1: SOPORTE_PCT se repite en §0.4.4 y SEMILLA en §10; ERRATA_MUESTRA es del A2."""
        secciones = {(c.seccion, c.repite) for c in constantes.REPETICIONES}
        self.assertIn(("§0.4", ("SOPORTE_PCT",)), secciones)
        self.assertIn(("§10", ("SEMILLA",)), secciones)
        self.assertEqual(constantes.POR_NOMBRE["ERRATA_MUESTRA"].seccion, "§10")

    def test_armonicos_procesos_y_magnus(self):
        """CON-10: los períodos 24/k de A_ARMONICOS_K son los del Anexo A; CON-8: PROCESOS es la opción D2 de M0."""
        k = constantes.valor("A_ARMONICOS_K")
        self.assertEqual(tuple(24 // x for x in k), (self.U.a("A_P1_H"), self.U.a("A_P2_H"), self.U.a("A_P3_H")))
        self.assertEqual(constantes.valor("PROCESOS"), self.U.opciones_m0["D2"])
        self.assertNotEqual(constantes.valor("MAGNUS_EL_FEATURES"), constantes.valor("MAGNUS_AGUA")[1:])

    def test_ningun_valor_del_a2_es_del_anexo_a_por_su_frase(self):
        """Una constante del A2 no repite una fila del Anexo A: si la frase repite un umbral, va a REPETICIONES."""
        filas = " ".join(f["texto"] for f in json.loads((_APH / umbrales.JSON_M0).read_text(encoding="utf-8"))["anexo_a"])
        for c in constantes.CONSTANTES:
            with self.subTest(constante=c.nombre):
                self.assertNotIn(c.fragmento, filas)


if __name__ == "__main__":
    unittest.main()
