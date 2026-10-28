"""Pruebas de tipos.py (enumerados, identificadores, esquemas y clases de datos; §2 del diseño).

Dueño: I0 (coordinador). Leen, sin escribir, el texto vigente v2.3 (la tabla de marcas de §2.4) con su sha256; si
falta, esas pruebas se omiten con el motivo y no se dan por aprobadas. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import re  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import tipos, umbrales  # noqa: E402
from meteo_combinada.tipos import Alcance, Marca, VariableDMC  # noqa: E402

_AP = _RAIZ.parent
_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
_CELDA = re.compile(r"(?<!\\)\|")


def _texto_vigente() -> str:
    ruta = _APH / umbrales.TEXTO_VIGENTE
    if not ruta.is_file():
        raise unittest.SkipTest(f"falta {ruta.name}; la prueba no se da por aprobada")
    datos = ruta.read_bytes()
    if hashlib.sha256(datos).hexdigest() != umbrales.SHA_TEXTO_VIGENTE:
        raise AssertionError(f"{ruta.name} no es el texto vigente v2.3")
    return datos.decode("utf-8")


def _tabla_de_marcas(texto: str) -> list[tuple[int, str, str]]:
    """(bit, marca, «¿Invalida?») de la tabla de §2.4."""
    a = texto.index("### 2.4 ")
    b = texto.index("### 2.5 ", a)
    filas = []
    for linea in texto[a:b].splitlines():
        celdas = [c.strip() for c in _CELDA.split(linea.strip())[1:-1]]
        if len(celdas) == 4 and celdas[0].isdigit():
            filas.append((int(celdas[0]), celdas[1], celdas[3]))
    return filas


# Palabras de la columna «¿Invalida?» → variables de la fuente.
_PALABRAS = {"Td": (VariableDMC.TD,), "HR": (VariableDMC.HR,), "QFE": (VariableDMC.QFE,), "QFF": (VariableDMC.QFF,),
             "viento": (VariableDMC.FF, VariableDMC.DD)}


class PruebasMarcas(unittest.TestCase):
    def test_marcas_como_en_la_tabla_de_2_4(self):
        """TIP-1: bits 0 a 22 en el orden del texto, con el nombre de la columna «Marca»."""
        filas = _tabla_de_marcas(_texto_vigente())
        self.assertEqual([b for b, _, _ in filas], list(range(len(Marca))))
        self.assertEqual(len(filas), len(tipos.NOMBRES_MARCAS))
        for bit, nombre, _ in filas:
            with self.subTest(bit=bit):
                self.assertEqual(Marca(bit).nombre_texto, nombre)
                self.assertEqual(Marca(bit).bit, 1 << bit)

    def test_invalidantes_como_en_la_tabla_de_2_4(self):
        """La columna «¿Invalida?»: «no»/«informa» → NO; «toda la fila» → FILA; «la variable» → VARIABLE; el
        centinela arrastra Td y HR (Ts) y QFF (QFE); las demás, las variables que nombra."""
        filas = _tabla_de_marcas(_texto_vigente())
        self.assertEqual(set(tipos.INVALIDANTES), set(Marca))
        for bit, nombre, celda in filas:
            inv = tipos.INVALIDANTES[Marca(bit)]
            with self.subTest(marca=nombre):
                if celda.startswith("no") or celda == "informa":
                    self.assertIs(inv.alcance, Alcance.NO)
                elif celda == "sí, toda la fila":
                    self.assertIs(inv.alcance, Alcance.FILA)
                elif celda == "sí, la variable":
                    self.assertIs(inv.alcance, Alcance.VARIABLE)
                    self.assertEqual(dict(inv.arrastra), {})
                elif celda.startswith("sí. Con Ts"):
                    self.assertIs(inv.alcance, Alcance.VARIABLE)
                    self.assertEqual({k: set(v) for k, v in inv.arrastra.items()},
                                     {"Ts": {"Td", "relative_humidity"}, "QFE": {"QFF"}})
                else:
                    self.assertIs(inv.alcance, Alcance.VARIABLES)
                    cabeza = celda.removeprefix("sí, ").split(":")[0]
                    cabeza = re.split(r" (?:del|antes|de esas)", cabeza)[0]
                    esperadas = {v.value for palabra in re.findall(r"\w+", cabeza) for v in _PALABRAS.get(palabra, ())}
                    self.assertTrue(esperadas, celda)
                    self.assertEqual(set(inv.variables), esperadas)

    def test_marcas_q1_son_las_invalidantes_de_los_bits_3_a_17(self):
        """TIP-2: los bits 3-17 menos los que no invalidan (8, 10 y 15)."""
        bits = [int(m) for m in tipos.MARCAS_Q1]
        self.assertEqual(bits, sorted(set(range(Marca.FUERA_DE_RANGO, Marca.AIRE_SECO_SOSTENIDO + 1))
                                      - {Marca.TD_RECORTADO, Marca.TD_DERIVADO, Marca.HR_RECORTADA}))

    def test_marcas_caben_en_uint32(self):
        self.assertLess(max(m.bit for m in Marca), 1 << 31)


class PruebasEnumerados(unittest.TestCase):
    def test_candidatos_sin_fondo_ni_sin_dmc(self):
        """§0.4.1 y §0.4.2: no existe un candidato «fondo» ni «sin DMC»."""
        self.assertEqual([c.value for c in tipos.Candidato], ["A", "B", "AB", "C", "C_est"])
        for c in tipos.Candidato:
            self.assertNotIn("fondo", c.value.lower())
            self.assertNotIn("sin", c.value.lower())

    def test_variables_de_la_fuente_y_sus_columnas(self):
        """EMC1-1 y EMC1-3: siete variables de la fuente; wind_u y wind_v no entran."""
        self.assertEqual(len(tipos.VARIABLES_FUENTE), 7)
        self.assertNotIn(VariableDMC.WIND_U, tipos.VARIABLES_FUENTE)
        self.assertEqual(set(tipos.COLUMNA_ANCHA), set(tipos.VARIABLES_FUENTE))
        self.assertEqual(set(tipos.COLUMNA_MARCAS), set(tipos.VARIABLES_FUENTE))
        for v in tipos.VARIABLES_FUENTE:
            self.assertIn(tipos.COLUMNA_ANCHA[v], tipos.ESQUEMA_QC_ESTACION)
            self.assertEqual(tipos.ESQUEMA_QC_ESTACION[tipos.COLUMNA_MARCAS[v]], "uint32")

    def test_viento_por_variable_de_la_fuente(self):
        """TIP-9: FF y DD con su propia columna de marcas."""
        self.assertNotEqual(tipos.COLUMNA_MARCAS[VariableDMC.FF], tipos.COLUMNA_MARCAS[VariableDMC.DD])
        self.assertEqual(len(set(tipos.COLUMNA_MARCAS.values())), len(tipos.VARIABLES_FUENTE))
        self.assertNotIn("marcas_viento", tipos.ESQUEMA_QC_ESTACION)

    def test_macrozona_sin_region_e_insular_son_ninguna(self):
        """TIP-8 (D9) y TIP-11 (D16): «sin_region», «insular» y None no son macrozonas; las demás pasan igual."""
        self.assertIsNone(tipos.macrozona_o_ninguna(None))
        self.assertIsNone(tipos.macrozona_o_ninguna("sin_region"))
        self.assertIsNone(tipos.macrozona_o_ninguna("insular"))
        self.assertEqual(tipos.MACROZONAS_NINGUNA, {tipos.MACROZONA_SIN_REGION, tipos.MACROZONA_INSULAR})
        for nombre in ("norte_grande", "norte_chico", "centro", "sur", "austral"):
            self.assertEqual(tipos.macrozona_o_ninguna(nombre), nombre)

    def test_macrozonas_ninguna_son_codigos_de_comun_modelo(self):
        """TIP-11: «sin_region» e «insular» son las dos macrozonas de MACROZONA_CODIGO (por AST, con su huella) que
        ninguna región con comuna da; las demás son las de MACROZONA_REGION."""
        from meteo_combinada import fijados
        if not (_AP / fijados.RUTA_COMUN_MODELO).is_file():
            self.skipTest("falta _comun_modelo.py; la prueba no se da por aprobada")
        codigo = fijados.macrozona_codigo(_AP)
        region = fijados.macrozona_region(_AP)
        self.assertTrue(tipos.MACROZONAS_NINGUNA <= set(codigo))
        self.assertEqual(set(codigo) - tipos.MACROZONAS_NINGUNA,
                         {m for r, m in region.items() if r != 0})

    def test_macrozona_de_celda(self):
        """TIP-11 (D9, D16, D20): la macrozona sale de la columna «macrozona» de la celda y de su cod_comuna, no de la
        región: Juan Fernández (región 5, macrozona «insular») no es «centro»; una celda con cod_comuna 0 o −1, cuya
        macrozona se heredó de la región vecina, no tiene macrozona; sin celda, tampoco."""
        import numpy as np
        import pandas as pd
        self.assertEqual(tipos.macrozona_de_celda("centro", 13101), "centro")
        self.assertEqual(tipos.macrozona_de_celda("centro", np.int32(13101)), "centro")
        self.assertEqual(tipos.macrozona_de_celda("sur", 8101.0), "sur")
        self.assertIsNone(tipos.macrozona_de_celda("insular", 5104))            # Juan Fernández
        self.assertIsNone(tipos.macrozona_de_celda("insular", -1))              # celda generada de Rapa Nui
        self.assertIsNone(tipos.macrozona_de_celda("centro", 0))                # D9: heredada por vecino
        self.assertIsNone(tipos.macrozona_de_celda("centro", -1))               # D20: el −1 como el 0
        self.assertIsNone(tipos.macrozona_de_celda("sin_region", 0))
        for sin_celda in (None, pd.NA, float("nan")):
            self.assertIsNone(tipos.macrozona_de_celda("centro", sin_celda))
        with self.assertRaises(TypeError):
            tipos.macrozona_de_celda("centro", "13101")
        with self.assertRaises(TypeError):
            tipos.macrozona_de_celda("centro", True)
        with self.assertRaises(ValueError):
            tipos.macrozona_de_celda("centro", 13101.5)

    def test_validacion_publicada_cuenta_estaciones(self):
        """TIP-10: MZ exige ≥ 10 estaciones evaluables (§6.1); cada estación da dos evaluaciones."""
        cols = list(tipos.ESQUEMA_VALIDACION_PUB)
        self.assertEqual(cols[cols.index("n_evaluaciones") + 1], "n_estaciones")
        self.assertEqual(tipos.ESQUEMA_VALIDACION_PUB["n_estaciones"], "int32")

    def test_red_constante_ninguna(self):
        """TIP-6 (EMC1-2): la red «ninguna» con TF2 no evaluable."""
        self.assertEqual(tipos.ReglaRedConstante.NINGUNA.value, "ninguna")

    def test_rama_y_origenes(self):
        self.assertEqual([int(r) for r in tipos.Rama], [1, 2, 3])
        for origen in (tipos.OrigenTd, tipos.OrigenHR, tipos.OrigenViento):
            self.assertEqual(origen.SIN_VALOR, -1)
            self.assertTrue(all(-128 <= int(o) <= 127 for o in origen))     # caben en int8


class PruebasOla2(unittest.TestCase):
    """Cambios del coordinador al cerrar la ola 2 (TIP-13 a TIP-16). Los módulos de la ola 2 conservan sus copias de
    los nombres hasta que su dueño los tome de aquí: estas pruebas exigen que sean iguales."""

    def test_errata_confirmada_es_un_objeto(self):
        """TIP-13: ruta, sha256 y commit; None por omisión; congelada."""
        self.assertEqual([f.name for f in dataclasses.fields(tipos.ErrataConfirmada)], ["ruta", "sha256", "commit"])
        campos = {f.name: f for f in dataclasses.fields(tipos.RegistroReloj)}
        self.assertIsNone(campos["errata_confirmada"].default)
        errata = tipos.ErrataConfirmada(ruta="APH/x.md", sha256="0" * 64, commit="1" * 40)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            errata.commit = "2" * 40  # type: ignore[misc]

    def test_errata_de_politicas_es_el_objeto_de_tipos(self):
        """TIP-13: politicas arma el ErrataConfirmada desde el objeto del registro (POL-1)."""
        from meteo_combinada import politicas
        errata = {"ruta": "APH/auditoria/20261101/meteo_combinada/errata.md", "sha256": "a" * 64, "commit": "b" * 40}
        self.assertEqual(politicas._texto_errata(errata), tipos.ErrataConfirmada(**errata))
        self.assertIsNone(politicas._texto_errata(None))

    def test_motivos_de_exclusion(self):
        """TIP-14: los de estaticas_nasadem (NAS-12, NAS-16) más «sin_fondo» (A8), en su orden de precedencia; los que
        cuentan en el numerador de Q2 (D36) y los que salen del numerador y del denominador (D37), disjuntos."""
        from meteo_combinada import estaticas_nasadem
        self.assertEqual([m.value for m in tipos.MotivoExclusion],
                         [*estaticas_nasadem.MOTIVOS, tipos.MotivoExclusion.SIN_FONDO.value])
        self.assertEqual(tipos.MOTIVOS_SIN_COORDENADAS_K3, estaticas_nasadem.MOTIVOS_SIN_COORDENADAS_K3)
        self.assertEqual(tipos.MOTIVOS_FUERA_DE_Q2, estaticas_nasadem.MOTIVOS_FUERA_DE_Q2)
        self.assertEqual(tipos.MotivoExclusion.SIN_NASADEM.value, estaticas_nasadem.MOTIVO_SIN_NASADEM)
        self.assertEqual(tipos.MOTIVOS_FUERA_DE_Q2, {tipos.MotivoExclusion.SIN_NASADEM.value})
        self.assertTrue(tipos.MOTIVOS_FUERA_DE_Q2.isdisjoint(tipos.MOTIVOS_SIN_COORDENADAS_K3))
        self.assertEqual(tipos.MOTIVOS_SIN_COORDENADAS_K3,
                         {tipos.MotivoExclusion.COORDENADAS_ILEGIBLES.value,
                          tipos.MotivoExclusion.COORDENADAS_FUERA_DE_RANGO.value, tipos.MotivoExclusion.K3.value})
        for fuera in (tipos.MotivoExclusion.SIN_Z_S, tipos.MotivoExclusion.SIN_FONDO):
            self.assertNotIn(fuera.value, tipos.MOTIVOS_SIN_COORDENADAS_K3 | tipos.MOTIVOS_FUERA_DE_Q2)

    def test_rotulos_de_la_decision(self):
        """TIP-15: los rótulos que lee decision y que fabrica sintetico (SIN-14) son los de tipos."""
        from meteo_combinada import decision, sintetico
        usados = {v for vg in decision.VARIABLES.values() for campo in dataclasses.fields(vg)
                  for v in getattr(vg, campo.name)}
        self.assertEqual(usados, {v.value for v in tipos.VariableMetrica})
        self.assertEqual((decision.ESTRATO_NACIONAL, decision.ESTRATO_MACROZONA),
                         (tipos.Estrato.NACIONAL.value, tipos.Estrato.MACROZONA.value))
        self.assertEqual(decision.MACROZONAS, tipos.MACROZONAS)
        self.assertEqual((decision.CONTAMINANTES_M6, decision.CLAVE_O3), (tipos.CONTAMINANTES_M6, tipos.CLAVE_O3))
        self.assertEqual((decision.ESQUEMA_DECISION, decision.ESQUEMA_DECISION_M6),
                         (tipos.VERSION_DECISION, tipos.VERSION_DECISION_M6))
        variables, estratos = set(), set()
        for caso in sintetico.CASOS_METRICAS:
            tablas = sintetico.tablas_metricas(caso)
            if "validacion" in tablas:
                variables |= set(tablas["validacion"]["variable"]) | set(tablas["tf"]["variable"])
                estratos |= set(tablas["validacion"]["estrato"])
        self.assertLessEqual(variables, {v.value for v in tipos.VariableMetrica})
        self.assertLessEqual(estratos, {e.value for e in tipos.Estrato})
        self.assertTrue(set(tipos.MACROZONAS).isdisjoint(tipos.MACROZONAS_NINGUNA))

    def test_macrozonas_son_las_de_comun_modelo(self):
        """TIP-15: MACROZONAS = MACROZONA_CODIGO (por AST, con su huella) menos MACROZONAS_NINGUNA, en su orden."""
        from meteo_combinada import fijados
        if not (_AP / fijados.RUTA_COMUN_MODELO).is_file():
            self.skipTest("falta _comun_modelo.py; la prueba no se da por aprobada")
        codigo = fijados.macrozona_codigo(_AP)
        orden = sorted((c for m, c in codigo.items() if m not in tipos.MACROZONAS_NINGUNA))
        por_codigo = {c: m for m, c in codigo.items()}
        self.assertEqual(tipos.MACROZONAS, tuple(por_codigo[c] for c in orden))

    def test_sinca_hora_sin_columnas_nuevas(self):
        """TIP-16: el conteo de R7 y el reloj van en el registro, no en ESQUEMA_SINCA_HORA."""
        self.assertEqual(list(tipos.ESQUEMA_SINCA_HORA), ["estacion", "h", "variable", "valor", "valido", "serie"])


class PruebasCierreOla2(unittest.TestCase):
    """Cambios del coordinador al aplicar D20-D50 (TIP-17 y TIP-18; TIP-11 y TIP-14 revisadas)."""

    def test_macrozona_cod_es_la_de_comun_modelo(self):
        """TIP-18: MACROZONA_COD es MACROZONA_CODIGO de _comun_modelo (por AST, con su huella), código por código."""
        from meteo_combinada import fijados
        if not (_AP / fijados.RUTA_COMUN_MODELO).is_file():
            self.skipTest("falta _comun_modelo.py; la prueba no se da por aprobada")
        self.assertEqual(dict(tipos.MACROZONA_COD), fijados.macrozona_codigo(_AP))
        self.assertEqual(set(tipos.MACROZONA_COD) - set(tipos.MACROZONAS), set(tipos.MACROZONAS_NINGUNA))

    def test_indicadoras_macrozona(self):
        """TIP-18 (D22 (a)): una indicadora por macrozona, desde el código de la grilla; «sin_region» e «insular» van
        en 0; un código desconocido o que no es entero es un error. Una celda con cod_comuna 0 lleva las de la
        macrozona heredada, aunque macrozona_de_celda la deje sin macrozona para los conteos (TIP-11)."""
        import numpy as np
        for i, m in enumerate(tipos.MACROZONAS):
            esperado = tuple(int(j == i) for j in range(len(tipos.MACROZONAS)))
            self.assertEqual(tipos.indicadoras_macrozona(tipos.MACROZONA_COD[m]), esperado, m)
            self.assertEqual(tipos.indicadoras_macrozona(np.int8(tipos.MACROZONA_COD[m])), esperado, m)
        ceros = (0,) * len(tipos.MACROZONAS)
        for m in tipos.MACROZONAS_NINGUNA:
            self.assertEqual(tipos.indicadoras_macrozona(tipos.MACROZONA_COD[m]), ceros, m)
        centro = tipos.MACROZONA_COD["centro"]
        self.assertIsNone(tipos.macrozona_de_celda("centro", 0))
        self.assertEqual(sum(tipos.indicadoras_macrozona(centro)), 1)
        for malo in (True, "2", None, float("nan")):
            with self.subTest(malo=malo), self.assertRaises(TypeError):
                tipos.indicadoras_macrozona(malo)
        for malo in (len(tipos.MACROZONA_COD), -1, 2.5):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                tipos.indicadoras_macrozona(malo)

    def test_estado_en_datos_competencia(self):
        """TIP-17 (acuerdo A14): DatosCompetencia lleva el estado de C (ESQUEMA_PUNTOS_E5L) y el de C_est (las
        climatologías del operador, D29) por estación; las variables son las de ESQUEMA_CLIMA_ESTADO y las de
        fondo_era5l.clima_en_puntos, en el mismo orden."""
        from meteo_combinada import fondo_era5l
        self.assertEqual([f.name for f in dataclasses.fields(tipos.DatosCompetencia)],
                         ["residuos", "climatologias", "tramos", "filas_c", "estaticos", "estaciones", "pliegues",
                          "puntos_e5l", "clima_estado"])
        self.assertEqual(tipos.VARIABLES_CLIMA_ESTADO, fondo_era5l.VARIABLES_CLIMA)
        self.assertEqual(list(tipos.ESQUEMA_CLIMA_ESTADO),
                         ["pixel_id", "mes", "hora", *tipos.VARIABLES_CLIMA_ESTADO])


class PruebasOla3(unittest.TestCase):
    """TIP-19 a TIP-24 (cierre de la ola 3): lo que I12, I13 e I14 pidieron pasar a ``tipos``. Los módulos conservan
    sus copias hasta que sus dueños vuelvan; estas pruebas exigen que sean iguales a las de ``tipos``."""

    def test_esquemas_de_la_ola_3_son_los_de_sus_modulos(self):
        """TIP-21: columnas, orden, tipos y versión iguales a los de ``qc_dmc_meteo``, ``candidatos`` y
        ``validacion``."""
        from meteo_combinada import candidatos, qc_dmc_meteo, validacion
        pares = (("conteos", qc_dmc_meteo.COLUMNAS_CONTEO, None, tipos.ESQUEMA_CONTEOS_QC),
                 ("prediccion", candidatos.COLUMNAS_PREDICCION, None, tipos.ESQUEMA_PREDICCION),
                 ("soporte", validacion.COLUMNAS_SOPORTE, validacion.VERSION_SOPORTE, tipos.ESQUEMA_SOPORTE_PUB),
                 ("descriptivos", validacion.COLUMNAS_DESCRIPTIVOS, validacion.VERSION_DESCRIPTIVOS,
                  tipos.ESQUEMA_DESCRIPTIVOS_PUB),
                 ("sinca", validacion.COLUMNAS_SINCA, validacion.VERSION_SINCA, tipos.ESQUEMA_SINCA_PUB))
        for nombre, columnas, version, esquema in pares:
            with self.subTest(esquema=nombre):
                self.assertEqual(list(dict(columnas).items()), list(esquema.items()))
                if version is not None:
                    self.assertEqual(version, esquema.version)
        publicados = (tipos.ESQUEMA_SOPORTE_PUB, tipos.ESQUEMA_DESCRIPTIVOS_PUB, tipos.ESQUEMA_SINCA_PUB)
        self.assertTrue(all(tipos.ESQUEMAS[e.nombre] is e for e in publicados))
        self.assertEqual(set(tipos.ESQUEMAS_EN_MEMORIA), {"conteos_qc", "prediccion"})
        self.assertFalse(set(tipos.ESQUEMAS_EN_MEMORIA) & set(tipos.ESQUEMAS))
        self.assertIs(tipos.ESQUEMAS[tipos.ESQUEMA_ESTATICAS_CELDA_C.nombre], tipos.ESQUEMA_ESTATICAS_CELDA_C)   # ola 4
        for esquema in (*tipos.ESQUEMAS_EN_MEMORIA.values(), tipos.ESQUEMA_ESTATICAS_CELDA_C):
            tipos.validar_esquema(tipos.tabla_vacia(esquema), esquema, nombre=esquema.nombre)

    def test_estaticos_de_c_con_z_e5l(self):
        """TIP-22 (PED-2): los estáticos de C son los de ``estaticas_nasadem`` más ``z_e5l`` en f8, al final; es la
        columna que ``candidatos`` exige."""
        from meteo_combinada import candidatos
        self.assertEqual(candidatos.COLUMNA_Z_E5L, tipos.COLUMNA_Z_E5L)
        self.assertEqual(list(tipos.ESQUEMA_ESTATICAS_CELDA_C.items()),
                         [*tipos.ESQUEMA_ESTATICAS_CELDA.items(), (tipos.COLUMNA_Z_E5L, "float64")])

    def test_esquemas_de_la_ola_3_y_la_guarda_de_s7(self):
        """TIP-21 y TIP-22 frente a ``ceguera`` (D3, CEG-10): los tres publicados pasan como métrica; los estáticos de C
        sólo como insumo (como ``ze5l``); la predicción no pasa en ninguna clase con vocabulario (R, §0.4.3)."""
        from meteo_combinada import ceguera
        for esquema in (tipos.ESQUEMA_SOPORTE_PUB, tipos.ESQUEMA_DESCRIPTIVOS_PUB, tipos.ESQUEMA_SINCA_PUB):
            ceguera.vigilar_salida(f"{esquema.nombre}.parquet", tipos.tabla_vacia(esquema), clase="metrica")
        estaticos = tipos.tabla_vacia(tipos.ESQUEMA_ESTATICAS_CELDA_C)
        ceguera.vigilar_salida("estaticas/celdas.parquet", estaticos, clase="insumo")
        with self.assertRaises(ceguera.SalidaProhibida):
            ceguera.vigilar_salida("estaticas_celda_c.parquet", estaticos, clase="metrica")
        prediccion = tipos.tabla_vacia(tipos.ESQUEMA_PREDICCION)
        for clase in ceguera.CLASES_CON_VOCABULARIO:
            with self.subTest(clase=clase), self.assertRaises(ceguera.SalidaProhibida):
                ceguera.vigilar_salida("prediccion.parquet", prediccion, clase=clase)

    def test_estratos_descriptivos(self):
        """TIP-19 (VAL-17): los rótulos de ``estrato`` y el valor de «omm» son los de ``validacion``, en su orden; la
        decisión sigue leyendo sólo «nacional» y «macrozona»."""
        from meteo_combinada import decision, validacion
        self.assertEqual(tuple(e.value for e in tipos.Estrato), validacion.ESTRATOS)
        self.assertEqual(tipos.VALOR_ESTRATO_OMM, validacion.VALOR_OMM)
        self.assertEqual((decision.ESTRATO_NACIONAL, decision.ESTRATO_MACROZONA),
                         (tipos.Estrato.NACIONAL.value, tipos.Estrato.MACROZONA.value))

    def test_fuera_de_la_grilla_igual_en_sus_copias(self):
        """TIP-20 (D34): ``tipos.fuera_de_la_grilla`` es el predicado de ``estaticas_nasadem`` y el de las copias de
        ``candidatos`` y ``validacion``, en las cuatro combinaciones de excluida y celda."""
        from meteo_combinada import candidatos, estaticas_nasadem, validacion
        nan = float("nan")
        base = tipos.InfoEstacion(
            codigo="330001", nombre="E", conjunto="V", macrozona="centro", grupo="G330001", omm=None, tipo=None,
            propietario=None, lat_txt="-33.4", lon_txt="-70.6", alt_txt="500", lat=-33.4, lon=-70.6, z_cat=500.0,
            rho_km=0.1, k3_pasa=True, z_s=500.0, z_s_fuente="catalogo", celda=None, utm_e=nan, utm_n=nan, bloque="",
            pix0=-1, pix1=-1, pix2=-1, pix3=-1, w0=nan, w1=nan, w2=nan, w3=nan, respaldo_16km=False, sin_fondo=False,
            excluida=False, motivo=None)
        copias = (estaticas_nasadem.fuera_de_la_grilla, candidatos._fuera_de_la_grilla,
                  validacion._fuera_de_la_grilla)
        for excluida in (False, True):
            for celda in (None, 81001):
                info = dataclasses.replace(base, excluida=excluida, celda=celda)
                esperado = (not excluida) and celda is None
                with self.subTest(excluida=excluida, celda=celda):
                    self.assertIs(tipos.fuera_de_la_grilla(info), esperado)
                    self.assertEqual([bool(f(info)) for f in copias], [esperado] * len(copias))

    def test_vecinos_y_sumas_de_c(self):
        """TIP-23 (PED-1, PED-4): ``VecinosNucleo`` trae los campos de ``candidatos.VecinosEntrenamiento``, en su
        orden, y ``tipos.SumasC`` los de ``candidatos.SumasC``."""
        from meteo_combinada import candidatos
        self.assertEqual([f.name for f in dataclasses.fields(tipos.VecinosNucleo)],
                         [f.name for f in dataclasses.fields(candidatos.VecinosEntrenamiento)])
        self.assertTrue(issubclass(candidatos.VecinosEntrenamiento, tipos.VecinosNucleo))
        self.assertEqual([f.name for f in dataclasses.fields(tipos.SumasC)],
                         [f.name for f in dataclasses.fields(candidatos.SumasC)])


class PruebasEsquemas(unittest.TestCase):
    def test_cada_esquema_construye_su_tabla_vacia(self):
        """Cada tipo es un tipo válido de pandas; la tabla vacía valida contra su esquema y lleva su versión."""
        versiones = [e.version for e in tipos.ESQUEMAS.values()]
        self.assertEqual(len(versiones), len(set(versiones)))
        for nombre, esquema in tipos.ESQUEMAS.items():
            with self.subTest(esquema=nombre):
                self.assertEqual(esquema.nombre, nombre)
                df = tipos.tabla_vacia(esquema)
                tipos.validar_esquema(df, esquema, nombre=nombre)
                self.assertEqual(df.attrs["esquema"], esquema.version)

    def test_validar_esquema_rechaza(self):
        e = tipos.ESQUEMA_ZE5L
        df = tipos.tabla_vacia(e)
        with self.assertRaises(ValueError):
            tipos.validar_esquema(df[list(reversed(df.columns))], e, nombre="orden")
        with self.assertRaises(ValueError):
            tipos.validar_esquema(df.drop(columns=["caso"]), e, nombre="falta")
        with self.assertRaises(ValueError):
            tipos.validar_esquema(df.astype({"z_e5l": "float32"}), e, nombre="tipo")

    def test_esquema_inmutable(self):
        with self.assertRaises(AttributeError):
            tipos.ESQUEMA_TF.version = "x"
        with self.assertRaises(TypeError):
            tipos.ESQUEMA_TF._columnas["nueva"] = "int8"

    def test_laterales_i_9_y_d_14_columnas(self):
        """§7.1 y MC-28: I con 9 mc_*; D con 9 fe_* y 5 dmc_R_*: 14 columnas, más las dos claves."""
        claves = ["estacion", "ts_utc"]
        self.assertEqual(list(tipos.ESQUEMA_LATERAL_I)[:2], claves)
        self.assertEqual(list(tipos.ESQUEMA_LATERAL_D)[:2], claves)
        self.assertEqual(len(tipos.ESQUEMA_LATERAL_I) - 2, 9)
        self.assertEqual(len(tipos.ESQUEMA_LATERAL_D) - 2, 14)
        self.assertEqual(set(tipos.UNIDADES_EL), set(tipos.SUFIJOS_EL))
        self.assertEqual(tuple(tipos.UNIDADES_R_D), tipos.COLUMNAS_R_D)

    def test_entradas_decision_son_las_tablas_de_tablas_metricas(self):
        """TIP-12: EntradasDecision lleva validación, TF, réplicas y motivos de E0, las tablas que fabrica
        sintetico.tablas_metricas para S7, cada una con su esquema."""
        from meteo_combinada import sintetico
        self.assertEqual([f.name for f in dataclasses.fields(tipos.EntradasDecision)],
                         ["uso", "grupo", "validacion", "tf", "replicas", "motivos_e0"])
        caso = sintetico.tablas_metricas("ganador_claro")
        entradas = tipos.EntradasDecision(tipos.Uso(caso["uso"]), tipos.Grupo(caso["grupo"]), caso["validacion"],
                                          caso["tf"], caso["replicas"], caso["e0_excluidos"])
        tipos.validar_esquema(entradas.validacion, tipos.ESQUEMA_VALIDACION_PUB, nombre="validacion")
        tipos.validar_esquema(entradas.tf, tipos.ESQUEMA_TF, nombre="tf")
        tipos.validar_esquema(entradas.replicas, tipos.ESQUEMA_REPLICAS, nombre="replicas")
        self.assertEqual(set(entradas.validacion["candidato"]), set(caso["candidatos"]))
        self.assertTrue(set(entradas.validacion["grupo"]) == {entradas.grupo.value})

    def test_info_estacion_es_la_fila_del_esquema(self):
        """InfoEstacion: los mismos campos que ESQUEMA_ESTACIONES_MC, en el mismo orden."""
        self.assertEqual([f.name for f in dataclasses.fields(tipos.InfoEstacion)], list(tipos.ESQUEMA_ESTACIONES_MC))

    def test_meteo_diaria_lleva_la_version_de_meteo_civil_v3(self):
        self.assertEqual(tipos.ESQUEMA_METEO_DIARIA.version, "meteo-diaria-v3/1")

    def test_estaticas_con_las_siete_lulc(self):
        self.assertEqual(len(tipos.LULC), 7)
        self.assertTrue(set(tipos.LULC) <= set(tipos.ESQUEMA_ESTATICAS_CELDA))


class PruebasIdentificadores(unittest.TestCase):
    def test_identificadores_de_2_1(self):
        self.assertEqual(tipos.id_grupo(["330030", "330020"]), "G330020")
        self.assertEqual(tipos.id_tramo("1.2", 3), "1.2/3")
        self.assertEqual(tipos.id_bloque(4, 83), "4_83")
        self.assertEqual(tipos.id_pliegue_p1(0), "P1-0")
        self.assertEqual(tipos.id_interno(tipos.id_pliegue_p2("4_83"), 2), "P2-4_83/i2")
        for texto in ("P1-0", "P2-4_83", "P2-4_83/i2"):
            self.assertIsNotNone(tipos.PATRON_PLIEGUE.fullmatch(texto), texto)
        self.assertIsNotNone(tipos.PATRON_TRAMO.fullmatch("1.2/3"))
        for malo in ([], ["33002"], [330020]):
            with self.assertRaises(ValueError):
                tipos.id_grupo(malo)
        for k in (0, True, 1.0):
            with self.assertRaises(ValueError):
                tipos.id_tramo("1.2", k)
        with self.assertRaises(ValueError):
            tipos.id_tramo("0.1", 1)
        with self.assertRaises(ValueError):
            tipos.id_pliegue_p2("4-83")

    def test_pliegue_ordenado_y_disjunto(self):
        p = tipos.Pliegue("P1-0", tipos.Particion.P1, ("330020",), ("330030", "330040"), ("330021",))
        self.assertEqual(p.externo, None)
        with self.assertRaises(ValueError):
            tipos.Pliegue("P1-0", tipos.Particion.P1, ("330030", "330020"), ())
        with self.assertRaises(ValueError):
            tipos.Pliegue("P1-0", tipos.Particion.P1, ("330020",), ("330020",))
        with self.assertRaises(ValueError):
            tipos.Pliegue("P1-0", tipos.Particion.P1, ("330020",), ("330030",), ("330030",))


if __name__ == "__main__":
    unittest.main()
