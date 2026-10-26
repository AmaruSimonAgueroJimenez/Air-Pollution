"""Pruebas de estados.py (álgebra de estados).

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

from reloj_dmc import estados  # noqa: E402,F401
from reloj_dmc.tipos import ESQUEMA_ESTADOS, Estado, Linea, Nivel, Regla  # noqa: E402

C, I, D, S = Estado.COMPATIBLE, Estado.INCOMPATIBLE, Estado.DUDOSA, Estado.SIN_INFORMACION
P_CONTINENTAL = ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")
PARTES_2019 = [f"2019-{m:02d}-1" for m in range(1, 13)]


def _tabla(filas_por_unidad, *, linea=Linea.E2, regla=Regla.UNICA, anio=2019):
    """filas_por_unidad: lista de (nivel, unidad, {H: estado}, reloj_anomalo)."""
    marcos = [estados.filas_estado("330020", anio, linea, nivel, unidad, por_h, regla=regla,
                                   reloj_anomalo=anomala)
              for nivel, unidad, por_h, anomala in filas_por_unidad]
    return pd.concat(marcos, ignore_index=True)


def _base(cambios_parte=None, cambios_regimen=None, anomalas=(), regimen_anomalo=(), anio=2019):
    """Una estación UTC: F(0) compatible en todo; las demás incompatibles en los regímenes."""
    cambios_parte = cambios_parte or {}
    cambios_regimen = cambios_regimen or {}
    filas = []
    for parte in [p.replace("2019", str(anio), 1) for p in PARTES_2019]:
        por_h = {"F(0)": C, "F(-3)": C, "F(-4)": S, "C(Santiago)": S}
        por_h.update(cambios_parte.get(parte, {}))
        filas.append((Nivel.PARTE, parte, por_h, parte in anomalas))
    for regimen in ("R0", "R1"):
        por_h = {"F(0)": C, "F(-3)": C, "F(-4)": I, "C(Santiago)": I}
        por_h.update(cambios_regimen.get(regimen, {}))
        filas.append((Nivel.REGIMEN, regimen, por_h, regimen in regimen_anomalo))
    return _tabla(filas, anio=anio)


def _anual(salida, anio=2019):
    a = salida[(salida["nivel"] == "anio") & (salida["anio"] == anio)]
    return {h: (e, bool(an), m) for h, e, an, m in zip(a["H"], a["estado"], a["reloj_anomalo"], a["motivo"])}


def _discordantes(salida):
    d = salida[salida["discordante"]]
    return set(zip(d["unidad"], d["H"]))


class PruebasEstados(unittest.TestCase):
    def assertEsquema(self, df):
        self.assertEqual(list(df.columns), list(ESQUEMA_ESTADOS))
        self.assertEqual({c: str(t) for c, t in df.dtypes.items()}, dict(ESQUEMA_ESTADOS))

    def test_filas_estado_esquema(self):
        """Una fila por H, con las columnas, el orden y los tipos de ESQUEMA_ESTADOS."""
        df = estados.filas_estado("330020", 2019, Linea.E3P, Nivel.PARTE, "2019-09-2",
                                  {"F(0)": C, "F(-4)": "incompatible"}, regla=Regla.GRUESA,
                                  reloj_anomalo=True, motivo=None)
        self.assertEsquema(df)
        self.assertEqual(df["H"].tolist(), ["F(0)", "F(-4)"])
        self.assertEqual(df["estado"].tolist(), ["compatible", "incompatible"])
        self.assertEqual(df["linea"].tolist(), ["E3p", "E3p"])
        self.assertEqual(df["regla"].tolist(), ["gruesa", "gruesa"])
        self.assertTrue(df["reloj_anomalo"].all())
        self.assertFalse(df["discordante"].any())
        self.assertTrue(df["motivo"].isna().all())
        self.assertEsquema(estados.filas_estado("330020", 2019, Linea.E2, Nivel.PARTE, "2019-09-2", {}))
        with self.assertRaises(ValueError):                       # las líneas evalúan hipótesis, no clases
            estados.filas_estado("330020", 2019, Linea.E2, Nivel.PARTE, "2019-09-2", {"F(-3)|C(Santiago)": C})
        with self.assertRaises(ValueError):
            estados.filas_estado("330020", 2019, Linea.E2, Nivel.PARTE, "2019-09-2", {"F(0)": "anomalo"})

    def test_una_parte_discordante_dos_incompatible(self):
        """§4.0: una parte incompatible es discordante; dos dan incompatible."""
        # Una sola parte incompatible con F(0): el año no cambia; esa parte es discordante para F(0).
        entrada = _base(cambios_parte={"2019-05-1": {"F(0)": I}})
        copia = entrada.copy(deep=True)
        salida = estados.anual_por_partes(entrada, linea=Linea.E2)
        pd.testing.assert_frame_equal(entrada, copia)             # la entrada no se toca
        self.assertEsquema(salida)
        anual = _anual(salida)
        self.assertEqual(list(anual), list(P_CONTINENTAL))
        self.assertEqual(anual["F(0)"][0], "sin_informacion")    # la compatibilidad la decide la línea
        self.assertTrue(pd.isna(anual["F(0)"][2]))
        self.assertEqual(anual["F(-4)"][:2], ("incompatible", False))   # por año-régimen
        self.assertEqual(anual["F(-4)"][2], "incompatible en R0,R1")
        self.assertEqual(_discordantes(salida), {("2019-05-1", "F(0)")})
        self.assertEqual(len(salida), len(entrada) + len(P_CONTINENTAL))
        a = salida[salida["nivel"] == "anio"]
        self.assertEqual(set(a["unidad"]), {"2019"})
        self.assertFalse(a["discordante"].any())

        # Dos partes incompatibles con F(0): incompatible en el año, sin partes discordantes.
        salida = estados.anual_por_partes(_base(cambios_parte={"2019-05-1": {"F(0)": I},
                                                               "2019-06-1": {"F(0)": I}}), linea=Linea.E2)
        self.assertEqual(_anual(salida)["F(0)"][0], "incompatible")
        self.assertEqual(_anual(salida)["F(0)"][2], "incompatible en 2 partes")
        self.assertEqual(_discordantes(salida), set())

        # Por año-régimen basta uno solo, aunque ninguna parte lo sea.
        salida = estados.anual_por_partes(_base(cambios_regimen={"R1": {"F(-3)": I}}), linea=Linea.E2)
        self.assertEqual(_anual(salida)["F(-3)"][:2], ("incompatible", False))
        self.assertEqual(_anual(salida)["F(0)"][0], "sin_informacion")

        # Dos años a la vez: cada uno con su fila anual.
        dos = pd.concat([_base(cambios_parte={"2019-05-1": {"F(0)": I}}),
                         _base(cambios_parte={"2020-05-1": {"F(0)": I}, "2020-07-1": {"F(0)": I}}, anio=2020)],
                        ignore_index=True)
        salida = estados.anual_por_partes(dos, linea=Linea.E2)
        self.assertEqual(_anual(salida, 2019)["F(0)"][0], "sin_informacion")
        self.assertEqual(_anual(salida, 2020)["F(0)"][0], "incompatible")
        self.assertEqual(_discordantes(salida), {("2019-05-1", "F(0)")})

    def test_anomalo_por_regimen_o_dos_partes(self):
        """§4.0: anómalo en un año-régimen o en ≥ 2 partes."""
        # Una sola parte anómala: el año no es anómalo; la parte es discordante (en toda H).
        salida = estados.anual_por_partes(_base(anomalas={"2019-03-1"}), linea=Linea.E2)
        self.assertFalse(any(v[1] for v in _anual(salida).values()))
        self.assertEqual(_discordantes(salida), {("2019-03-1", h) for h in P_CONTINENTAL})

        # Dos partes anómalas: el año es anómalo; ninguna es discordante.
        salida = estados.anual_por_partes(_base(anomalas={"2019-03-1", "2019-08-1"}), linea=Linea.E2)
        self.assertTrue(all(v[1] for v in _anual(salida).values()))
        self.assertEqual(_discordantes(salida), set())

        # Un año-régimen anómalo basta.
        salida = estados.anual_por_partes(_base(regimen_anomalo={"R0"}), linea=Linea.E2)
        self.assertTrue(all(v[1] for v in _anual(salida).values()))

        # Lectura propuesta: una parte incompatible y otra anómala se cuentan por separado; las dos
        # quedan discordantes y el año no es incompatible ni anómalo.
        salida = estados.anual_por_partes(_base(cambios_parte={"2019-05-1": {"F(0)": I}},
                                                anomalas={"2019-09-1"}), linea=Linea.E2)
        self.assertEqual(_anual(salida)["F(0)"][:2], ("sin_informacion", False))
        self.assertEqual(_discordantes(salida),
                         {("2019-05-1", "F(0)")} | {("2019-09-1", h) for h in P_CONTINENTAL})

        # E6: meses y la evaluación del año. Dos meses incompatibles con F(−3) la excluyen; la fila
        # anual conserva el estado de la evaluación del año y la reemplaza (no se repite).
        filas = [(Nivel.MES, f"2019-{m:02d}", {"F(0)": C, "F(-3)": I if m in (2, 9) else C}, False)
                 for m in range(1, 13)]
        filas.append((Nivel.ANIO, "2019", {"F(0)": C, "F(-3)": S}, False))
        salida = estados.anual_por_partes(_tabla(filas, linea=Linea.E6), linea=Linea.E6)
        anual = _anual(salida)
        self.assertEqual(anual["F(0)"][0], "compatible")
        self.assertEqual(anual["F(-3)"][:2], ("incompatible", False))
        self.assertEqual(anual["F(-3)"][2], "incompatible en 2 meses")
        self.assertEqual(int((salida["nivel"] == "anio").sum()), 2)
        self.assertEqual(_discordantes(salida), set())

        # Errores de implementación que la función rechaza.
        with self.assertRaises(ValueError):                       # otra línea
            estados.anual_por_partes(_base(), linea=Linea.E3P)
        with self.assertRaises(ValueError):                       # otra regla
            estados.anual_por_partes(_base(), linea=Linea.E2, regla=Regla.GRUESA)
        incoherente = _base()
        incoherente.loc[0, "reloj_anomalo"] = True                # señal de unidad distinta según H
        with self.assertRaises(ValueError):
            estados.anual_por_partes(incoherente, linea=Linea.E2)
        with self.assertRaises(ValueError):                       # filas repetidas
            estados.anual_por_partes(pd.concat([_base(), _base()], ignore_index=True), linea=Linea.E2)
        vacia = estados.anual_por_partes(_base().iloc[0:0], linea=Linea.E2)
        self.assertTrue(vacia.empty)
        self.assertEsquema(vacia)

    def test_combinar_subevaluaciones(self):
        """incompatible > compatible > dudosa > sin_informacion."""
        self.assertEqual(estados.combinar([]), S)
        self.assertEqual(estados.combinar([S, D]), D)
        self.assertEqual(estados.combinar([D, C, S]), C)
        self.assertEqual(estados.combinar([C, I, D]), I)
        self.assertEqual(estados.combinar(iter(["sin_informacion", "compatible"])), C)
        self.assertEqual(estados.combinar([S, S]), S)
        with self.assertRaises(ValueError):
            estados.combinar([C, "otro"])

    def test_estado_de_clase_exige_acuerdo(self):
        """Miembros con estados distintos lanzan ErrorFusion."""
        self.assertEqual(estados.estado_de_clase({"F(-3)": I, "C(Santiago)": I}), I)
        self.assertEqual(estados.estado_de_clase({"F(0)": "dudosa"}), D)
        with self.assertRaises(estados.ErrorFusion):
            estados.estado_de_clase({"F(-3)": C, "C(Santiago)": I})
        with self.assertRaises(estados.ErrorFusion):              # dudosa ≠ sin información
            estados.estado_de_clase({"F(-3)": D, "C(Santiago)": S})
        with self.assertRaises(estados.ErrorFusion):
            estados.estado_de_clase({})
        self.assertTrue(estados.es_informativo(C) and estados.es_informativo(I))
        self.assertFalse(estados.es_informativo(D) or estados.es_informativo(S))


if __name__ == "__main__":
    unittest.main()
