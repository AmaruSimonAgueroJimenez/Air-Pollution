"""Pruebas de tipos.py (enumerados, identificadores y esquemas).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import tipos  # noqa: E402
from reloj_dmc.tipos import ClaseH, Familia, Hipotesis, Linea  # noqa: E402

# Esquemas que vivían en red y en salidas hasta la ola 4b (los módulos de origen conservan alias).
ESQUEMAS_DE_RED = ("ESQUEMA_MUESTRA_A3", "ESQUEMA_MUESTRA_A5", "ESQUEMA_CALIBRACION", "ESQUEMA_GDUP")
ESQUEMAS_DE_SALIDAS = ("ESQUEMA_EVIDENCIA_PARTE", "ESQUEMA_EVIDENCIA_ANIO", "ESQUEMA_NO_NORMALIZABLES",
                       "ESQUEMA_CALIBRACION_CSV")


class PruebasTipos(unittest.TestCase):
    def test_hipotesis_ids_ida_y_vuelta(self):
        """F(0), F(-4), F(+1), C(Santiago), C(Pacific/Easter), Cv(Santiago)."""
        for ident in ("F(0)", "F(-3)", "F(-4)", "F(+1)", "F(-6)", "C(Santiago)", "C(Coyhaique)", "C(Punta_Arenas)",
                      "C(Pacific/Easter)", "Cv(Santiago)", "Cv(Pacific/Easter)"):
            with self.subTest(ident=ident):
                self.assertEqual(Hipotesis.desde_id(ident).id, ident)
        self.assertEqual(Hipotesis("F", 0, None).id, "F(0)")
        self.assertEqual(Hipotesis("F", -4, None).id, "F(-4)")
        self.assertEqual(Hipotesis("C", None, "Pacific/Easter").id, "C(Pacific/Easter)")
        self.assertEqual(Hipotesis.desde_id("Cv(Santiago)"), Hipotesis("Cv", None, "America/Santiago"))
        self.assertTrue(Hipotesis.desde_id("F(-3)").es_fija)
        self.assertFalse(Hipotesis.desde_id("C(Santiago)").es_fija)
        for malo in ("F(4)", "F(+0)", "F(-0)", "F(-04)", "F(-4.0)", "F()", "C()", "c(Santiago)", "C(America/Santiago)",
                     "Cv(Lima)", "F(-4) ", "Z(Santiago)"):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                Hipotesis.desde_id(malo)
        for args in (("F", None, None), ("F", -4, "America/Santiago"), ("F", True, None), ("F", -4.0, None),
                     ("C", -4, "America/Santiago"), ("C", None, None), ("X", None, None)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Hipotesis(*args)

    def test_p04_america_easter_da_error(self):
        """«America/Easter» no existe: desde_id y el constructor de C fallan."""
        with self.assertRaises(ValueError):
            Hipotesis.desde_id("C(America/Easter)")
        with self.assertRaises(ValueError):
            Hipotesis.desde_id("C(Easter)")
        with self.assertRaises(ValueError):
            Hipotesis("C", None, "America/Easter")
        with self.assertRaises(ValueError):
            Hipotesis("Cv", None, "America/Easter")
        self.assertEqual(Hipotesis("C", None, "Pacific/Easter").id, "C(Pacific/Easter)")
        self.assertNotIn("America/Easter", tipos.ZONAS)

    def test_orden_canonico_e_id_de_clase(self):
        """«F(-3)|C(Santiago)»; un miembro → su propio id."""
        h = Hipotesis.desde_id
        self.assertEqual(ClaseH(miembros=(h("C(Santiago)"), h("F(-3)")), desfases={"R0": -3}).id, "F(-3)|C(Santiago)")
        self.assertEqual(ClaseH(miembros=(h("F(-4)"),), desfases={}).id, "F(-4)")
        self.assertEqual(ClaseH(miembros=(h("C(Santiago)"), h("C(Coyhaique)")), desfases={}).id,
                         "C(Santiago)|C(Coyhaique)")
        self.assertEqual(ClaseH(miembros=(h("C(Santiago)"), h("F(-3)")), desfases={}).ids_miembros,
                         frozenset({"F(-3)", "C(Santiago)"}))
        with self.assertRaises(ValueError):
            ClaseH(miembros=(), desfases={}).id
        # §2.1 del diseño: F por desfase descendente (las de fuera de P en su lugar), luego C según ZONAS, al final Cv.
        desordenadas = ["Cv(Santiago)", "C(Pacific/Easter)", "F(-6)", "C(Santiago)", "F(-3)", "F(+1)", "F(0)",
                        "C(Punta_Arenas)", "F(-5)", "C(Coyhaique)", "F(-4)"]
        self.assertEqual(sorted(desordenadas, key=lambda i: h(i).orden()),
                         ["F(+1)", "F(0)", "F(-3)", "F(-4)", "F(-5)", "F(-6)", "C(Santiago)", "C(Coyhaique)",
                          "C(Punta_Arenas)", "C(Pacific/Easter)", "Cv(Santiago)"])
        self.assertEqual(tipos.interseccion_de_clases(frozenset({"F(-3)", "C(Santiago)"}), frozenset({"C(Santiago)"})),
                         frozenset({"C(Santiago)"}))

    def test_esquemas_columnas_y_tipos(self):
        """validar_esquema exige columnas, orden y tipos exactos."""
        esquemas = {n: v for n, v in vars(tipos).items() if n.startswith("ESQUEMA_")}
        self.assertGreaterEqual(set(esquemas), set(ESQUEMAS_DE_RED) | set(ESQUEMAS_DE_SALIDAS))
        for nombre, esquema in esquemas.items():
            with self.subTest(esquema=nombre):
                vacia = tipos.tabla_vacia(esquema)
                self.assertEqual(len(vacia), 0)
                tipos.validar_esquema(vacia, esquema, nombre=nombre)
        e = tipos.ESQUEMA_HORAS
        bien = pd.DataFrame({"codigo": ["330020"], "anio": [2019], "mes": [1], "horas_ts_o_qfe": [24]}).astype(e)
        tipos.validar_esquema(bien, e, nombre="horas")
        with self.assertRaisesRegex(ValueError, "columnas"):
            tipos.validar_esquema(bien[["anio", "codigo", "mes", "horas_ts_o_qfe"]], e, nombre="orden")
        with self.assertRaisesRegex(ValueError, "columnas"):
            tipos.validar_esquema(bien.drop(columns=["mes"]), e, nombre="falta")
        with self.assertRaisesRegex(ValueError, "columnas"):
            tipos.validar_esquema(bien.assign(extra=1), e, nombre="sobra")
        with self.assertRaisesRegex(ValueError, "tipos"):
            tipos.validar_esquema(bien.astype({"anio": "int32"}), e, nombre="tipo")
        with self.assertRaisesRegex(ValueError, "tipos"):
            tipos.validar_esquema(bien.astype({"codigo": "object"}), e, nombre="texto sin string")

    def test_esquemas_de_red_y_salidas_viven_en_tipos(self):
        """Ola 4b: los esquemas propios de red y de salidas están en tipos; los módulos de origen conservan
        alias (los mismos objetos), y su contenido es el de la ola 4a."""
        from reloj_dmc import red, salidas
        for nombre in ESQUEMAS_DE_RED:
            with self.subTest(esquema=nombre):
                self.assertIs(getattr(red, nombre), getattr(tipos, nombre))
        for nombre in ESQUEMAS_DE_SALIDAS:
            with self.subTest(esquema=nombre):
                self.assertIs(getattr(salidas, nombre), getattr(tipos, nombre))
        self.assertEqual(tipos.ESQUEMA_CALIBRACION_CSV, {**tipos.ESQUEMA_CALIBRACION, "fuera": "boolean"})
        self.assertEqual(list(tipos.ESQUEMA_MUESTRA_A3), ["codigo", "anio", "regimen", "macrozona", "c_f_cont",
                                                          "c_s2_cont", "D"])
        parte = tipos.ESQUEMA_EVIDENCIA_PARTE
        self.assertEqual(len(parte), 83)
        self.assertEqual(list(parte)[:5], ["codigo", "anio", "mes", "parte", "regimen"])
        self.assertEqual(list(parte)[-4:], ["estados", "lineas_reloj_anomalo", "discordante", "lineas_discordantes"])
        self.assertEqual((parte["e2_n_rr"], parte["e2_valida"], parte["e3_c_hat_ts"], parte["e4_K_hr"]),
                         ("Int32", "boolean", "Int8", "Int8"))
        self.assertEqual(len(tipos.ESQUEMA_EVIDENCIA_ANIO), 29)
        self.assertEqual((salidas.VARIABLES_E3, salidas.VARIABLES_E4), (("Ts", "QFE"), ("Ts", "QFE", "HR")))

    def test_propiedades_de_lineas(self):
        """Familias y Q de §4.0; E3t no excluye; guardas y marcas no apoyan."""
        L, P = Linea, tipos.LINEAS
        self.assertEqual(set(P), set(Linea))
        familias = {Familia.REGISTRO: {L.E1A, L.E1B, L.E1C, L.E2}, Familia.TERMICA: {L.E3T},
                    Familia.PRESION_REANALISIS: {L.E3P}, Familia.PRESION_MAREA: {L.E4P}, Familia.EXTERNA: {L.E6},
                    Familia.DOCUMENTAL: {L.E5}, Familia.GUARDA: {L.E3D, L.P7, L.TP, L.E4T, L.G_VERSION},
                    Familia.MARCA: {L.G_HR, L.G_VIENTO}}
        for familia, lineas in familias.items():
            self.assertEqual({x for x, p in P.items() if p.familia == familia}, lineas, familia)
        self.assertEqual({x for x, p in P.items() if p.cuantitativa}, {L.E3P, L.E4P, L.E6})   # E3t sólo en modo completo
        self.assertEqual({x for x, p in P.items() if not p.no_termica}, {L.E3T})
        self.assertFalse(P[L.E3T].excluye)
        self.assertEqual({x for x, p in P.items() if p.excluye}, {L.E1A, L.E1B, L.E1C, L.E2, L.E3P, L.E4P, L.E6})
        apoyo = set(tipos.LINEAS_DE_APOYO)
        self.assertFalse(apoyo & (familias[Familia.GUARDA] | familias[Familia.MARCA] | {L.E5}))
        self.assertEqual(set(tipos.GUARDAS_DE_DECISION), {L.E3D, L.P7, L.TP, L.E4T})
        self.assertEqual(set(tipos.LINEAS_DE_COBERTURA), {L.E2, L.E3P, L.E4P, L.E6})
        self.assertEqual(str(L.TP), "T-P")


if __name__ == "__main__":
    unittest.main()
