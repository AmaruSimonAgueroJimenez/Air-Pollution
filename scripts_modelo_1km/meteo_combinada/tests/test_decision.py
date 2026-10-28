"""Pruebas de decision.py (§6 y Anexo B): S7 (la regla) y S16 (las ramas), más los registros.

Dueño: I10 (olas 2 y 3). Las que llevan «sNN» son la prueba NN de §9 del texto. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos: las tablas de ``sintetico.tablas_metricas`` y ``sintetico.tablas_m6`` (en memoria), con
cambios hechos aquí a mano; ninguna prueba abre DMC, la meteorología SINCA real, NASADEM real ni GHS-POP real. Los
umbrales son los anclados en M0 (``umbrales.cargar_m0``: el texto y el JSON de APH, con sus huellas).

Las tablas de ``sintetico.tablas_metricas`` entran tal como salen (acuerdo A11), sin rodeos: los de la ola 2
(``_con_particiones``, que sumaba las filas de macrozona de P1 y P2, y ``_e1_vacio_valido``, que arreglaba la TF de C
en «e1_vacio») y el de D43 (la rapidez por macrozona en «uv») se borraron cuando I5 entregó esas tablas (SIN-22).
``test_s07_tablas_metricas_tal_cual`` corre cada caso tal como sale y compara todo su esperado; si un cambio de
``sintetico`` deja de calzar, lista el desajuste (``_desajustes_i5``), comprueba que ``decision`` lo rechace por esa
razón y se omite con el motivo: no se da por aprobada.
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import ceguera, constantes, decision, sintetico as S, tipos, umbrales  # noqa: E402
from meteo_combinada.tipos import ReglaRedConstante, Rama, Variante  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_U = None


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


class _UFalso:
    """Umbrales con algunos ids cambiados: para ver que la regla los lee de ``U`` y no los tiene escritos."""

    def __init__(self, base, **cambios):
        self.base, self.cambios = base, cambios

    def a(self, ident):
        return self.cambios.get(ident, self.base.a(ident))


# ---------------------------------------------------------------------------------------------------------------
# Ayudas: casos de sintetico y cambios a mano
# ---------------------------------------------------------------------------------------------------------------
def _entradas(d, *, validacion=None, tf=None, replicas=None, motivos=None):
    """Las tablas de un caso de ``sintetico.tablas_metricas``, con las que se cambien a mano (acuerdo A11, TIP-12)."""
    return tipos.EntradasDecision(tipos.Uso(d["uso"]), tipos.Grupo(d["grupo"]),
                                  d["validacion"] if validacion is None else validacion,
                                  d["tf"] if tf is None else tf,
                                  d["replicas"] if replicas is None else replicas,
                                  d["e0_excluidos"] if motivos is None else motivos)


def _con_metricas(val: pd.DataFrame, cambios: dict, *, estrato="nacional", particion="agregado") -> pd.DataFrame:
    """{(candidato, variable, columna): valor} en las filas del estrato y la partición (en una macrozona, la única)."""
    v = val.copy()
    for (cand, var, col), x in cambios.items():
        m = ((v.candidato == cand) & (v.variable == var) & (v.estrato == estrato)
             & (v.particion == particion)).to_numpy(dtype=bool)
        assert m.sum() == 1, (cand, var, col, estrato, particion)
        v.loc[m, col] = x
    return v


def _con_macrozona(val: pd.DataFrame, variable: str, S_z: dict, *, n_estaciones=12, publicable=True,
                   macrozona="centro", particiones=("P1", "P2", "agregado")) -> pd.DataFrame:
    """Filas de macrozona hechas a mano, {candidato: S_c,z}, en las particiones pedidas (lo agudo y lo crónico)."""
    base = val[((val.estrato == "nacional") & (val.particion == "agregado")).to_numpy(dtype=bool)].iloc[0]
    filas = []
    for p in particiones:
        for cand, s in S_z.items():
            f = base.to_dict()
            f.update({"variable": variable, "candidato": cand, "particion": p, "S": s, "CD": np.nan, "EX": np.nan,
                      "nivel": np.nan, "anomalia": np.nan, "estrato": "macrozona", "valor_estrato": macrozona,
                      "n_evaluaciones": 2 * n_estaciones, "n_estaciones": n_estaciones, "publicable": publicable})
            filas.append(f)
    nuevas = pd.DataFrame(filas, columns=list(val.columns))
    salida = pd.concat([val, nuevas], ignore_index=True).astype(dict(tipos.ESQUEMA_VALIDACION_PUB))
    tipos.validar_esquema(salida, tipos.ESQUEMA_VALIDACION_PUB, nombre="validacion")
    return salida


def _agudo_base() -> tuple[dict, pd.DataFrame]:
    """«agudo_nivel» con el nivel de AB de vuelta a la base (1,05): todas las compuertas pasan y gana AB."""
    d = S.tablas_metricas("agudo_nivel")
    return d, _con_metricas(d["validacion"], {("AB", "temp_media", "nivel"): 1.05})


def _cronica_mz(d) -> pd.DataFrame:
    """La macrozona «centro» de un caso crónico con 12 estaciones (MZ rige) y S_z de A y C_est que pasan:
    mín sobre E0 (sin AB) = 0,30 (B) y cota 1,15·0,30 = 0,345."""
    cambios = {(c, "T", "n_estaciones"): 12 for c in ("A", "B", "AB", "C_est")}
    cambios.update({("A", "T", "S"): 0.33, ("C_est", "T", "S"): 0.34})
    return _con_metricas(d["validacion"], cambios, estrato="macrozona")


def _con_tf(tf: pd.DataFrame, cambios: dict) -> pd.DataFrame:
    """{(candidato, variable, prueba): {columna: valor}}."""
    t = tf.copy()
    for (cand, var, prueba), campos in cambios.items():
        m = ((t.candidato == cand) & (t.variable == var) & (t.prueba == prueba)).to_numpy(dtype=bool)
        assert m.sum() == 1, (cand, var, prueba)
        for col, x in campos.items():
            t.loc[m, col] = x
    return t


def _solo(replicas: pd.DataFrame, candidatos) -> pd.DataFrame:
    return replicas[replicas.candidato.isin(list(candidatos)).to_numpy(dtype=bool)].reset_index(drop=True)


_NO_EVALUABLE = {"media_pond": float("nan"), "p95_pond": float("nan"), "resultado": "no_evaluable",
                 "regla_red": "ninguna", "n_red": 7}


def _fallidas(tabla: pd.DataFrame) -> dict[str, set[str]]:
    """Candidato → compuertas que falla, desde la tabla de ``compuertas``."""
    salida: dict[str, set[str]] = {}
    for f in tabla[~tabla.pasa.to_numpy(dtype=bool)].itertuples():
        salida.setdefault(f.candidato, set()).add(f.compuerta)
    return salida


def _sin_tf_de_b(d) -> pd.DataFrame:
    """La TF1 de B en T de los casos crónicos, de vuelta a «pasa» (media y P95 de B en la base: cota/5)."""
    return _con_tf(d["tf"], {("B", "T", "TF1"): {"media_pond": 0.01, "p95_pond": 0.03, "resultado": "pasa"}})


def _condiciones(d, U) -> dict:
    return {p: {s: decision.condiciones_anexo_b(d["comparacion"], p, s, U) for s in S.SENTIDOS_M6}
            for p in S.CONTAMINANTES_M6}


def _ambientales(t_td="ganador_claro", u_v="uv", p="p_sin_ex", **cambios) -> dict:
    """Entradas ambientales de los tres grupos: por omisión, (T, Td) gana AB, (u, v) gana A y p gana B."""
    salida = {}
    for g, caso in (("T_Td", t_td), ("u_v", u_v), ("p", p)):
        d = S.tablas_metricas(caso)
        salida[g] = _entradas(d, **cambios.get(g, {}))
    return salida


# Sumandos y factores de §6.1 (y del Anexo A, «Compuertas»), escritos aquí aparte de la regla (DEC-1).
_VALORES_TEXTO = {"CD_MULT": 1.10, "CD_T": 0.05, "CD_HR": 0.5, "CD_P": 0.05, "EX_T": 0.25, "EX_TD": 0.40,
                  "EX_HR": 2.0, "EX_FF": 0.30, "MZ_MULT": 1.15, "MZ_MIN_EST": 10, "NIVEL_MULT": 1.15}
_CD_SUMANDO = {"T": "CD_T", "HR": "CD_HR", "rapidez": "CD_T", "p": "CD_P"}            # «+ 0,05 K o m/s, + 0,5…»
_EX_SUMANDO = {"T": "EX_T", "temp_media": "EX_T", "Td": "EX_TD", "hr_media": "EX_HR", "rapidez": "EX_FF"}
_COLUMNA = {"CD": "CD", "EX": "EX", "MZ": "S", "nivel": "nivel", "anomalia": "anomalia"}


def _cota(U, compuerta: str, variable: str, minimo: float) -> float:
    """La cota de §6.1 con el mínimo sobre E0, en el mismo orden de operaciones que el texto."""
    if compuerta == "CD":
        return U.a("CD_MULT") * minimo + U.a(_CD_SUMANDO[variable])
    if compuerta == "EX":
        return minimo + U.a(_EX_SUMANDO[variable])
    if compuerta == "MZ":
        return U.a("MZ_MULT") * minimo
    return U.a("NIVEL_MULT") * minimo                                          # nivel (agudo) y anomalía (crónico)


def _ambientales_sin_b_ab() -> dict:
    """Entradas ambientales en que gana A en los tres grupos: en (T, Td) y en p, B y AB fuera de E0 por deriva; en
    (u, v), B y AB fuera por EX y CD."""
    salida = {}
    for g, caso in (("T_Td", "ganador_claro"), ("u_v", "uv"), ("p", "p_sin_ex")):
        d = S.tablas_metricas(caso)
        if g == "u_v":
            salida[g] = _entradas(d)
        else:
            salida[g] = _entradas(d, motivos={"B": ("deriva",), "AB": ("deriva",)},
                                  replicas=_solo(d["replicas"], ("A", "C")))
    return salida


def _ic_a_mano(dif, pct):
    """Percentil sin interpolar (la menor x con F(x) ≥ q), con q = (1 − pct/100)/2 y su complemento."""
    x = sorted(dif)
    n = len(x)
    a = round((1 - pct / 100) / 2, 12)
    return x[math.ceil(n * a) - 1], x[math.ceil(n * (1 - a)) - 1]


# Orden fijo de §6.2, paso 3, escrito aquí aparte de la regla.
_ORDEN = {"A": 0, "AB": 1, "B": 2, "C": 3, "C_est": 3}


def _conjunto_a_mano(r) -> tuple[str, ...]:
    """El conjunto en que la decisión eligió (§6.2 y Anexo B, rama 3), leído del registro: con la nota del ganador
    restringido, A y C; con la regla crónica, A y C_est de E1 o, si ninguno está, de E0; si no, E1 o, vacío, los de E0
    sin TF fallida (paso 4)."""
    e0, e1 = list(r.e0), list(r.e1)
    if "I restringido por TF de contaminantes" in r.notas:
        e0, e1 = [c for c in e0 if c in ("A", "C")], [c for c in e1 if c in ("A", "C")]
    if "regla crónica" in r.notas:
        return tuple([c for c in e1 if c in ("A", "C_est")] or [c for c in e0 if c in ("A", "C_est")])
    sin_tf = [c for c in e0 if not {"TF", "TF2 no evaluable"} & set(r.motivos.get(c, ()))]
    return tuple(e1 or sin_tf)


def _ic_d46(replicas: pd.DataFrame, conjunto, c: str, pct) -> tuple[float, float]:
    """D46 (MC-34): el intervalo de ΔS_c con el ganador de cada réplica, el de menor S de réplica en ``conjunto`` con el
    orden fijo, y ΔS_c,r = S_c,r − S_ganador_r,r."""
    rep = replicas.pivot(index="replica", columns="candidato", values="S")
    dif = []
    for _, fila in rep.iterrows():
        g = min(conjunto, key=lambda x: (fila[x], _ORDEN[x]))
        dif.append(float(fila[c]) - float(fila[g]))
    return _ic_a_mano(dif, pct)


def _replicas_a_mano(S: dict) -> pd.DataFrame:
    """{candidato: [S de cada réplica]} en ``ESQUEMA_REPLICAS``."""
    filas = [{"replica": r, "candidato": c, "S": float(s)} for c, ss in S.items() for r, s in enumerate(ss)]
    salida = pd.DataFrame(filas, columns=list(tipos.ESQUEMA_REPLICAS)).astype(dict(tipos.ESQUEMA_REPLICAS))
    tipos.validar_esquema(salida, tipos.ESQUEMA_REPLICAS, nombre="replicas")
    return salida


def _desajustes_i5(d) -> dict[str, str | None]:
    """Lo que le falta a un caso de ``tablas_metricas``, tal como sale, para calzar con ``decision`` (A11): {desajuste:
    texto del ValueError que provoca, o None si no la detiene}. Cada uno es un pedido a I5 por medio del coordinador."""
    val, tf, e = d["validacion"], d["tf"], d["esperado"]
    salida: dict[str, str | None] = {}
    mz = val[(val.estrato == "macrozona").to_numpy(dtype=bool)]
    por_clave: dict[tuple, set] = {}
    for v, z, c, p in zip(mz.variable, mz.valor_estrato, mz.candidato, mz.particion):
        por_clave.setdefault((v, z, c), set()).add(p)
    if any(ps != {"P1", "P2", "agregado"} for ps in por_clave.values()):
        salida["macrozonas sin sus filas de P1 y P2 (MC-61, DEC-4)"] = "faltan las filas"
    if d["grupo"] == "u_v" and ({z for v, z, _ in por_clave if v == "uv"}
                                != {z for v, z, _ in por_clave if v == "rapidez"}):
        salida["sin filas de macrozona en la rapidez (D43, DEC-20)"] = "DEC-20"
    cero = tf[tf.candidato.isin(["A", "C", "C_est"]).to_numpy(dtype=bool)]
    tol = constantes.valor("TF_CERO_TOL")
    if ((cero.media_pond > tol) | (cero.p95_pond > tol)).to_numpy(dtype=bool).any():      # NaN > tol es False
        salida["TF de A, C o C_est > 10⁻⁶, que §5.7 hace error de código"] = "error de código"
    if not e["e1"] and "regla sin ganador" not in e["notas"]:
        salida["con E1 vacío, el esperado no trae la nota «regla sin ganador» (DEC-10)"] = None
    return salida


# ---------------------------------------------------------------------------------------------------------------
# S7: la regla
# ---------------------------------------------------------------------------------------------------------------
class PruebasS7(unittest.TestCase):
    def setUp(self):
        self.U = _umbrales()

    def _decidir(self, d, entradas=None, U=None):
        return decision.decidir_combinacion(d["uso"], d["grupo"], entradas or _entradas(d), umbrales=U or self.U)

    def test_s07_cada_compuerta(self):
        """TF, CD, EX, MZ, nivel y anomalía, con los mínimos sobre E0: en cada caso de sintetico, las compuertas que
        falla cada candidato, E0, E1, el ganador y el S del grupo son los esperados (calculados aparte con el Anexo
        A); cada caso aísla una compuerta en una variable."""
        for caso in S.CASOS_METRICAS:
            if caso == "soporte":                                    # es de la regla de soporte (I14)
                continue
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                e = d["esperado"]
                tabla = decision.compuertas(d["uso"], d["grupo"], _entradas(d), self.U)
                self.assertEqual(_fallidas(tabla), {c: set(s) for c, s in e["fallas"].items()})
                r = self._decidir(d)
                self.assertEqual((r.e0, r.e1, r.ganador, r.notas), (e["e0"], e["e1"], e["ganador"], e["notas"]))
                self.assertEqual(r.S, e["S"])          # misma fórmula: igualdad exacta en float64
                self.assertEqual(set(tabla.candidato), set(e["e0"]))   # sólo los de E0 pasan por las compuertas

        # Qué compuerta y qué variable falla en cada caso aislado (§6.1, «Variables a las que se aplican»).
        aislados = {"compuerta_cd": ("AB", "CD", "T"), "falla_cd_hr": ("AB", "CD", "HR"),
                    "falla_ex_td": ("AB", "EX", "Td"), "falla_mz_hr": ("AB", "MZ", "HR"),
                    "falla_tf_td": ("AB", "TF", "Td"), "tf2_falla": ("AB", "TF", "T"),
                    "agudo_nivel": ("AB", "nivel", "temp_media"), "falla_ex_hr_media": ("AB", "EX", "hr_media"),
                    "falla_mz_agudo": ("AB", "MZ", "temp_media"), "falla_mz_cronica": ("B", "MZ", "T")}
        for caso, (cand, comp, var) in aislados.items():
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                t = decision.compuertas(d["uso"], d["grupo"], _entradas(d), self.U)
                fallas = t[~t.pasa.to_numpy(dtype=bool)]
                self.assertEqual(list(zip(fallas.candidato, fallas.compuerta, fallas.variable)), [(cand, comp, var)])
        t = decision.compuertas("ambiental", "u_v", _entradas(S.tablas_metricas("uv")), self.U)
        f = t[~t.pasa.to_numpy(dtype=bool)]
        self.assertEqual(sorted(zip(f.candidato, f.compuerta, f.variable)), [("AB", "CD", "rapidez"),
                                                                            ("B", "EX", "rapidez")])
        self.assertEqual(set(t[t.compuerta == "MZ"].variable), {"uv", "rapidez"})                  # D43
        d = S.tablas_metricas("cronica_mixta")
        t = decision.compuertas("cronico", "T_Td", _entradas(d), self.U)
        self.assertEqual(set(t[(t.compuerta == "anomalia") & ~t.pasa].candidato), {"C_est"})
        self.assertEqual(set(t.variable[t.compuerta == "CD"]), {"T"})              # lo crónico: sólo T
        self.assertEqual(set(t.variable[t.compuerta == "TF"]), {"T"})              # MC-04

        # p: no hay EX de la presión; el EX de 9,9 de B no cuenta.
        t = decision.compuertas("ambiental", "p", _entradas(S.tablas_metricas("p_sin_ex")), self.U)
        self.assertNotIn("EX", set(t.compuerta))

        # Mínimos sobre E0: B, fuera de E0 por deriva, con un CD bajísimo no hace fallar a nadie.
        d = S.tablas_metricas("deriva")
        val = _con_metricas(d["validacion"], {("B", "T", "CD"): 0.05})
        r = self._decidir(d, _entradas(d, validacion=val))
        self.assertEqual((r.e1, r.ganador), (("A", "AB", "C"), "AB"))
        nac = val[((val.estrato == "nacional") & (val.particion == "agregado") & (val.variable == "T"))
                  .to_numpy(dtype=bool)]
        self.assertLess(1.10 * float(nac.CD.min()) + 0.05, float(nac.CD.max()))    # con el mínimo de todos, fallarían

        # El borde exacto pasa («≤»), en float64 y con los valores de U; el siguiente float falla.
        d = S.tablas_metricas("ganador_claro")
        borde = self.U.a("CD_MULT") * 0.30 + self.U.a("CD_T")
        for valor, falla in ((borde, False), (np.nextafter(borde, np.inf), True)):
            val = _con_metricas(d["validacion"], {("AB", "T", "CD"): float(valor)})
            t = decision.compuertas("ambiental", "T_Td", _entradas(d, validacion=val), self.U)
            self.assertEqual("AB" in _fallidas(t), falla, valor)

        # MZ: no rige con < 10 estaciones, ni en un estrato no publicable, ni en una «macrozona» que no lo es (D9).
        for caso, motivo in (("mz_no_aplica", "pocas_estaciones"), ("mz_no_publicable", "no_publicable"),
                             ("mz_no_publicable_p2", "no_publicable")):                    # MC-61: falla en P2
            d = S.tablas_metricas(caso)
            t = decision.compuertas("ambiental", "T_Td", _entradas(d), self.U)
            mz = t[t.compuerta == "MZ"]
            self.assertFalse(mz.aplica.any())
            self.assertEqual(set(mz.motivo), {motivo})
        d = S.tablas_metricas("ganador_claro")
        val = d["validacion"].copy()
        val.loc[(val.estrato == "macrozona").to_numpy(dtype=bool), "valor_estrato"] = "sin_region"
        val = _con_metricas(val, {("AB", "T", "S"): 9.9}, estrato="macrozona")
        t = decision.compuertas("ambiental", "T_Td", _entradas(d, validacion=val), self.U)
        self.assertEqual(set(t[t.compuerta == "MZ"].motivo), {"sin_macrozona"})
        self.assertEqual(_fallidas(t), {})

        # La regla lee los umbrales de U (no los tiene escritos): con CD_MULT = 1,5, AB ya no falla CD.
        d = S.tablas_metricas("compuerta_cd")
        t = decision.compuertas("ambiental", "T_Td", _entradas(d), _UFalso(self.U, CD_MULT=1.5))
        self.assertEqual(_fallidas(t), {})
        t = decision.compuertas("ambiental", "T_Td", _entradas(S.tablas_metricas("falla_mz_hr")),
                                _UFalso(self.U, MZ_MIN_EST=13))
        self.assertEqual(_fallidas(t), {})

        # La tabla de compuertas.
        t = decision.compuertas("ambiental", "T_Td", _entradas(S.tablas_metricas("ganador_claro")), self.U)
        self.assertEqual({c: str(t[c].dtype) for c in t.columns}, dict(decision.COLUMNAS_COMPUERTAS))
        self.assertEqual(t.attrs["esquema"], decision.VERSION_COMPUERTAS)

    def _filas_fallidas(self, d, val, **kw) -> set:
        t = decision.compuertas(d["uso"], d["grupo"], _entradas(d, validacion=val, **kw), self.U)
        f = t[~t.pasa.to_numpy(dtype=bool)]
        return set(zip(f.candidato, f.compuerta, f.variable))

    def test_s07_bordes_y_sumandos_de_cada_compuerta(self):
        """§6.1 y Anexo A: en cada compuerta relativa y en cada variable, el borde exacto pasa y el float siguiente
        falla, con la cota escrita aquí aparte de la regla (sumando y factor del texto, mínimo sobre E0). Así queda fijo
        cada sumando (0,40 K en Td, 0,5 puntos en HR, 0,30 m/s en la rapidez…), no sólo que «hay» una cota."""
        for ident, valor in _VALORES_TEXTO.items():
            self.assertEqual(self.U.a(ident), valor, ident)
        g, uv, p = (S.tablas_metricas(c) for c in ("ganador_claro", "uv", "p_sin_ex"))
        agu, val_agu = _agudo_base()
        val_agu = _con_macrozona(val_agu, "temp_media", {"A": 0.80, "B": 0.75, "AB": 0.72, "C": 0.82})
        val_agu = _con_macrozona(val_agu, "hr_media", {"A": 5.0, "B": 4.8, "AB": 4.6, "C": 5.2})
        cro = S.tablas_metricas("cronica")
        bases = {"amb": (g, g["validacion"], {}), "uv": (uv, uv["validacion"], {}),
                 "p": (p, p["validacion"], {}), "agu": (agu, val_agu, {}),
                 "cro": (cro, _cronica_mz(cro), {"tf": _sin_tf_de_b(cro)})}
        casos = [("amb", "CD", "T", "C"), ("amb", "CD", "HR", "C"), ("amb", "EX", "T", "C"), ("amb", "EX", "Td", "C"),
                 ("amb", "MZ", "T", "C"), ("amb", "MZ", "HR", "C"),
                 ("uv", "CD", "rapidez", "C"), ("uv", "EX", "rapidez", "C"), ("uv", "MZ", "uv", "C"),
                 ("uv", "MZ", "rapidez", "C"),                                                    # D43
                 ("p", "CD", "p", "C"), ("p", "MZ", "p", "C"),
                 ("agu", "CD", "T", "C"), ("agu", "CD", "HR", "C"), ("agu", "EX", "temp_media", "C"),
                 ("agu", "EX", "hr_media", "C"), ("agu", "nivel", "temp_media", "C"), ("agu", "nivel", "hr_media", "C"),
                 ("agu", "MZ", "temp_media", "C"), ("agu", "MZ", "hr_media", "C"),
                 ("cro", "CD", "T", "C_est"), ("cro", "EX", "temp_media", "C_est"), ("cro", "anomalia", "T", "C_est"),
                 ("cro", "MZ", "T", "C_est")]
        cubiertas = set()
        for base, comp, var, cand in casos:
            d, val, kw = bases[base]
            with self.subTest(base=base, compuerta=comp, variable=var):
                previas = self._filas_fallidas(d, val, **kw)
                estrato = "macrozona" if comp == "MZ" else "nacional"
                columna = _COLUMNA[comp]
                e0 = [c for c in d["candidatos"] if c not in d["e0_excluidos"]]
                filas = val[((val.estrato == estrato) & (val.particion == "agregado") & (val.variable == var)
                             & val.candidato.isin(e0)).to_numpy(dtype=bool)]
                minimo = float(filas[columna].min())
                self.assertLess(minimo, float(filas[columna][filas.candidato == cand].iloc[0]))   # no es el mínimo
                cota = _cota(self.U, comp, var, minimo)
                for valor, falla in ((cota, False), (float(np.nextafter(cota, np.inf)), True)):
                    v = _con_metricas(val, {(cand, var, columna): valor}, estrato=estrato)
                    fallidas = self._filas_fallidas(d, v, **kw)
                    self.assertEqual((cand, comp, var) in fallidas, falla, valor)
                    self.assertEqual(fallidas - {(cand, comp, var)}, previas)
                cubiertas.add((d["uso"], d["grupo"], comp, var))
        # Cubren todas las compuertas relativas de VARIABLES (§6.1).
        esperadas = {(u.value, g_.value, comp, var) for (u, g_), vg in decision.VARIABLES.items()
                     for comp, campo in (("CD", "CD"), ("EX", "EX"), ("MZ", "MZ"), ("nivel", "nivel"),
                                         ("anomalia", "anomalia")) for var in getattr(vg, campo)}
        self.assertEqual(cubiertas, esperadas)

        # Entre las dos cotas posibles (con el sumando de otra variable fallarían).
        self.assertEqual(self._filas_fallidas(g, _con_metricas(g["validacion"], {("AB", "HR", "CD"): 3.5})), set())
        self.assertEqual(self._filas_fallidas(g, _con_metricas(g["validacion"], {("AB", "Td", "EX"): 1.15})), set())
        self.assertNotIn(("C", "EX", "rapidez"),
                         self._filas_fallidas(uv, _con_metricas(bases["uv"][1], {("C", "rapidez", "EX"): 0.58})))

        # MZ rige con 10 estaciones exactas («≥ 10») y no con 9.
        d = S.tablas_metricas("falla_mz_hr")
        for n, fallas in ((10, {("AB", "MZ", "HR")}), (9, set())):
            val = _con_metricas(d["validacion"], {(c, v, "n_estaciones"): n for c in ("A", "B", "AB", "C")
                                                  for v in ("T", "HR")}, estrato="macrozona")
            with self.subTest(n_estaciones=n):
                self.assertEqual(self._filas_fallidas(d, val), fallas)
                t = decision.compuertas("ambiental", "T_Td", _entradas(d, validacion=val), self.U)
                self.assertEqual(bool(t[t.compuerta == "MZ"].aplica.all()), n == 10)

    def test_s07_minimos_sobre_e0(self):
        """§6.2, paso 2: «Los mínimos de las compuertas relativas se toman sobre E0», también en EX, MZ, nivel y
        anomalía: un candidato fuera de E0 con un valor bajísimo no hace fallar a nadie; dentro de E0, sí."""
        f = S.tablas_metricas("finitud")                                  # AB fuera de E0 por finitud
        for cambios, estrato in (({("AB", "T", "S"): 0.90}, "macrozona"),   # cota 1,15·1,10 = 1,265 (con AB, 1,035)
                                 ({("AB", "T", "EX"): 0.10}, "nacional")):  # cota 0,50 + 0,25 (con AB, 0,35)
            with self.subTest(cambios=cambios):
                val = _con_metricas(f["validacion"], cambios, estrato=estrato)
                self.assertEqual(self._filas_fallidas(f, val), set())
                con_ab = self._filas_fallidas(f, val, motivos={})
                self.assertTrue({c for c, _, _ in con_ab} == {"A", "B", "C"}, con_ab)
        agu, val = _agudo_base()                                          # B fuera de E0 por deriva
        val = _con_metricas(val, {("B", "temp_media", "nivel"): 0.50})
        self.assertEqual(self._filas_fallidas(agu, val, motivos={"B": ("deriva",)}), set())
        self.assertIn(("A", "nivel", "temp_media"), self._filas_fallidas(agu, val))
        cro = S.tablas_metricas("cronica")                                # AB fuera de E0 por deriva
        val = _con_metricas(cro["validacion"], {("AB", "T", "anomalia"): 0.05})
        self.assertEqual(self._filas_fallidas(cro, val, tf=_sin_tf_de_b(cro)), set())
        self.assertIn(("A", "anomalia", "T"), self._filas_fallidas(cro, val, tf=_sin_tf_de_b(cro), motivos={}))

    def test_s07_mz_por_particion(self):
        """MC-61 y §0.4.4: una macrozona que no es publicable en P1 o en P2 no entra a MZ aunque el agregado lo sea;
        sin sus filas de P1 y P2 no se decide; las nacionales de P1 y P2 son descriptivas (DEC-2, DEC-4)."""
        d = S.tablas_metricas("falla_mz_hr")
        base = d["validacion"]                                       # sintetico trae P1, P2 y el agregado (SIN-22)
        cands = ("A", "B", "AB", "C")
        self.assertEqual(self._filas_fallidas(d, base), {("AB", "MZ", "HR")})
        es_mz = (base.estrato == "macrozona").to_numpy(dtype=bool)
        for p in ("P1", "P2"):
            with self.subTest(particion=p):
                val = _con_metricas(base, {(c, "HR", "publicable"): False for c in cands}, estrato="macrozona",
                                    particion=p)
                t = decision.compuertas("ambiental", "T_Td", _entradas(d, validacion=val), self.U)
                mz = t[(t.compuerta == "MZ") & (t.variable == "HR")]
                self.assertFalse(mz.aplica.any())
                self.assertEqual(set(mz.motivo), {"no_publicable"})
                self.assertEqual(_fallidas(t), {})
                r = decision.decidir_combinacion("ambiental", "T_Td", _entradas(d, validacion=val), umbrales=self.U)
                self.assertEqual((r.e1, r.ganador), (("A", "B", "AB", "C"), "AB"))
        malos = {
            "publicable de P1 distinto entre candidatos": _con_metricas(base, {("A", "HR", "publicable"): False},
                                                                        estrato="macrozona", particion="P1"),
            "sin P1 ni P2": base[~(es_mz & base.particion.isin(["P1", "P2"]).to_numpy(dtype=bool))]
            .reset_index(drop=True),
            "sin P2": base[~(es_mz & (base.particion == "P2").to_numpy(dtype=bool))].reset_index(drop=True),
            "sin el agregado": base[~(es_mz & (base.particion == "agregado").to_numpy(dtype=bool))]
            .reset_index(drop=True),
        }
        for nombre, val in malos.items():
            with self.subTest(caso=nombre), self.assertRaises(ValueError):
                decision.compuertas("ambiental", "T_Td", _entradas(d, validacion=val), self.U)
        # Las nacionales de P1 y P2 no se leen: un S de 99 en P1 y en P2 no cambia nada.
        val = base
        for p in ("P1", "P2"):
            val = _con_metricas(val, {("AB", v, "S"): 99.0 for v in ("T", "HR")}, particion=p)
        r0 = decision.decidir_combinacion("ambiental", "T_Td", _entradas(d, validacion=base), umbrales=self.U)
        r1 = decision.decidir_combinacion("ambiental", "T_Td", _entradas(d, validacion=val), umbrales=self.U)
        self.assertEqual(r1, r0)

    def test_s07_mz_en_lo_agudo_y_en_lo_cronico(self):
        """§6.1: MZ también en lo agudo (en ``temp_media`` y ``hr_media``) y en lo crónico (en T), con una macrozona de
        ≥ 10 estaciones en que un candidato falla; una fila de macrozona en otra variable es un error (DEC-2)."""
        agu = S.tablas_metricas("falla_mz_agudo")                           # 0,95 > 1,15·0,75 (mín sobre E0: B)
        self.assertEqual(self._filas_fallidas(agu, agu["validacion"]), {("AB", "MZ", "temp_media")})
        r = self._decidir(agu)
        self.assertEqual((r.e1, r.ganador, r.motivos), (("A", "B", "C"), "B", {"AB": ("MZ",)}))
        t = decision.compuertas("agudo", "T_Td", _entradas(agu), self.U)
        self.assertEqual(set(t[t.compuerta == "MZ"].variable), {"temp_media", "hr_media"})
        self.assertTrue(t[t.compuerta == "MZ"].aplica.all())
        # La sonda del revisor: filas de macrozona de lo agudo en T y HR (variables de CD, no de MZ) → error.
        agu, val = _agudo_base()
        for var in ("T", "HR"):
            val = _con_macrozona(val, var, {"A": 1.0, "B": 1.0, "AB": 99.0, "C": 1.0})
        with self.assertRaises(ValueError):
            self._decidir(agu, _entradas(agu, validacion=val))

        # Crónico: 12 estaciones; B falla MZ (0,50 > 1,15·0,33) y AB, la deriva → regla crónica, gana A.
        cro = S.tablas_metricas("cronica")
        val = _con_metricas(_cronica_mz(cro), {("B", "T", "S"): 0.50}, estrato="macrozona")
        entradas = _entradas(cro, validacion=val, tf=_sin_tf_de_b(cro))
        self.assertEqual(self._filas_fallidas(cro, val, tf=_sin_tf_de_b(cro)), {("B", "MZ", "T")})
        r = self._decidir(cro, entradas)
        self.assertEqual((r.e1, r.ganador, r.notas), (("A", "C_est"), "A", ("regla crónica",)))
        self.assertEqual(r.motivos, {"B": ("MZ",), "AB": ("deriva",)})
        self.assertEqual(self._decidir(cro, _entradas(cro, validacion=_cronica_mz(cro), tf=_sin_tf_de_b(cro))).ganador,
                         "B")                                                # sin la falla de MZ gana B
        # El caso de sintetico: B falla MZ (0,50 > 1,15·0,32) y AB sigue en E1, así no rige la regla crónica.
        fmc = S.tablas_metricas("falla_mz_cronica")
        r = self._decidir(fmc)
        self.assertEqual((r.e1, r.ganador, r.notas, r.motivos), (("A", "AB", "C_est"), "AB", (), {"B": ("MZ",)}))
        # En lo crónico MZ va sólo en T; en lo ambiental, no en Td.
        for d, var in ((cro, "temp_media"), (S.tablas_metricas("ganador_claro"), "Td")):
            with self.subTest(uso=d["uso"], variable=var), self.assertRaises(ValueError):
                val = _con_macrozona(d["validacion"], var, {c: 1.0 for c in d["candidatos"]}, macrozona="sur")
                decision.compuertas(d["uso"], d["grupo"], _entradas(d, validacion=val), self.U)

    def test_s07_mz_en_uv_vectorial_y_en_la_rapidez(self):
        """D43 (P33): en (u, v), MZ va en el RMSE vectorial y en la rapidez, y un candidato debe pasar en las dos (§6.1:
        «CD y MZ, a las del puntaje del grupo: … la rapidez en (u, v)»). DEC-20: si las variables de MZ de un grupo no
        traen las mismas macrozonas, la regla no se decide."""
        uv = S.tablas_metricas("uv")
        base = uv["validacion"]
        cands = ("A", "B", "AB", "C")
        previas = {("AB", "CD", "rapidez"), ("B", "EX", "rapidez")}
        self.assertEqual(self._filas_fallidas(uv, base), previas)
        r = self._decidir(uv)
        self.assertEqual((r.e1, r.ganador), (("A", "C"), "A"))
        t = decision.compuertas("ambiental", "u_v", _entradas(uv), self.U)
        mz = t[t.compuerta == "MZ"]
        self.assertEqual(sorted(set(zip(mz.variable, mz.ambito))), [("rapidez", "centro"), ("uv", "centro")])
        self.assertTrue(mz.aplica.all())

        # «falla_mz_rapidez» de sintetico: A falla MZ sólo en la rapidez (1,00 > 1,15·0,82), sale de E1 y gana C. Con
        # MZ sólo en «uv» ganaría A.
        f = S.tablas_metricas("falla_mz_rapidez")
        self.assertEqual(self._filas_fallidas(f, f["validacion"]), previas | {("A", "MZ", "rapidez")})
        r = self._decidir(f)
        self.assertEqual((r.e1, r.ganador, r.motivos["A"]), (("C",), "C", ("MZ",)))
        # El borde: con el S_z de A en la rapidez justo en la cota pasa, y gana A otra vez.
        cota = self.U.a("MZ_MULT") * 0.82
        val = _con_metricas(base, {("A", "rapidez", "S"): cota}, estrato="macrozona")
        self.assertEqual(self._filas_fallidas(uv, val), previas)
        val = _con_metricas(base, {("A", "rapidez", "S"): float(np.nextafter(cota, np.inf))}, estrato="macrozona")
        self.assertEqual(self._filas_fallidas(uv, val), previas | {("A", "MZ", "rapidez")})
        # Y sólo en «uv»: falla igual, por la otra variable.
        val = _con_metricas(base, {("A", "uv", "S"): 2.5}, estrato="macrozona")
        self.assertEqual(self._filas_fallidas(uv, val), previas | {("A", "MZ", "uv")})
        # Con 9 estaciones en la rapidez, MZ no rige allí, pero sí en «uv».
        val = _con_metricas(base, {**{(c, "rapidez", "n_estaciones"): 9 for c in cands}, ("A", "rapidez", "S"): 2.5},
                            estrato="macrozona")
        t = decision.compuertas("ambiental", "u_v", _entradas(uv, validacion=val), self.U)
        mz = t[t.compuerta == "MZ"].set_index(["variable", "candidato"])
        self.assertFalse(mz.loc["rapidez"].aplica.any())
        self.assertTrue(mz.loc["uv"].aplica.all())
        self.assertEqual(_fallidas(t), {"AB": {"CD"}, "B": {"EX"}})

        # DEC-20: «uv» con macrozonas y la rapidez sin ellas (como las tablas de antes de D43), la rapidez con una de
        # más, o la rapidez sin «uv»: error.
        sur = _con_macrozona(base, "rapidez", {c: 1.0 for c in cands}, macrozona="sur")
        sin_uv = base[~((base.estrato == "macrozona") & (base.variable == "uv")).to_numpy(dtype=bool)]
        sin_rapidez = base[~((base.estrato == "macrozona") & (base.variable == "rapidez")).to_numpy(dtype=bool)]
        for nombre, v in (("sin la rapidez", sin_rapidez.reset_index(drop=True)), ("sur sólo en la rapidez", sur),
                          ("la rapidez sin «uv»", sin_uv.reset_index(drop=True))):
            with self.subTest(caso=nombre), self.assertRaisesRegex(ValueError, "DEC-20"):
                decision.compuertas("ambiental", "u_v", _entradas(uv, validacion=v), self.U)
        # También en (T, Td): HR sin sus filas de macrozona.
        g = S.tablas_metricas("ganador_claro")
        sin_hr = g["validacion"][~((g["validacion"].estrato == "macrozona")
                                   & (g["validacion"].variable == "HR")).to_numpy(dtype=bool)]
        with self.assertRaisesRegex(ValueError, "DEC-20"):
            decision.compuertas("ambiental", "T_Td", _entradas(g, validacion=sin_hr.reset_index(drop=True)), self.U)
        # Sin ninguna fila de macrozona en el grupo, MZ no rige (DEC-20; exigir las cinco es un pedido).
        nac = base[(base.estrato == "nacional").to_numpy(dtype=bool)].reset_index(drop=True)
        t = decision.compuertas("ambiental", "u_v", _entradas(uv, validacion=nac), self.U)
        self.assertNotIn("MZ", set(t.compuerta))
        self.assertEqual(self._decidir(uv, _entradas(uv, validacion=nac)).ganador, "A")

    def test_s07_macrozonas_lista_cerrada(self):
        """DEC-19 (D9, D16): una macrozona desconocida es un error; «sin_region» e «insular» no rigen en MZ; la lista
        es la de ``_comun_modelo.MACROZONA_CODIGO`` (por AST, con su huella) menos ``MACROZONAS_NINGUNA``."""
        d = S.tablas_metricas("falla_mz_hr")
        for nombre, motivo in (("foo", None), ("sin_region", "sin_macrozona"), ("insular", "sin_macrozona")):
            val = d["validacion"].copy()
            val.loc[(val.estrato == "macrozona").to_numpy(dtype=bool), "valor_estrato"] = nombre
            with self.subTest(macrozona=nombre):
                if motivo is None:
                    with self.assertRaises(ValueError):
                        decision.compuertas("ambiental", "T_Td", _entradas(d, validacion=val), self.U)
                    continue
                t = decision.compuertas("ambiental", "T_Td", _entradas(d, validacion=val), self.U)
                self.assertEqual(set(t[t.compuerta == "MZ"].motivo), {motivo})
                self.assertEqual(_fallidas(t), {})
        for nombre in decision.MACROZONAS:
            val = d["validacion"].copy()
            val.loc[(val.estrato == "macrozona").to_numpy(dtype=bool), "valor_estrato"] = nombre
            with self.subTest(macrozona=nombre):
                self.assertEqual(self._filas_fallidas(d, val), {("AB", "MZ", "HR")})
        from meteo_combinada import fijados
        if not (_AP / fijados.RUTA_COMUN_MODELO).is_file():
            self.skipTest("falta _comun_modelo.py; la comparación de la lista no se da por aprobada")
        self.assertEqual(set(decision.MACROZONAS), set(fijados.macrozona_codigo(_AP)) - tipos.MACROZONAS_NINGUNA)
        self.assertEqual(len(decision.MACROZONAS), len(set(decision.MACROZONAS)))

    def test_s07_entradas_invalidas(self):
        """La regla no se decide con entradas incompletas o incoherentes: ValueError o TypeError (DEC-2 a DEC-6)."""
        d = S.tablas_metricas("ganador_claro")
        casos = {
            "métrica de E0 no finita": _entradas(d, validacion=_con_metricas(d["validacion"],
                                                                            {("A", "T", "CD"): float("nan")})),
            "métrica negativa": _entradas(d, validacion=_con_metricas(d["validacion"], {("A", "Td", "EX"): -0.1})),
            "fila nacional no publicable": _entradas(d, validacion=_con_metricas(d["validacion"],
                                                                                {("C", "T", "publicable"): False})),
            "n_estaciones distinto entre candidatos": _entradas(d, validacion=_con_metricas(
                d["validacion"], {("C", "T", "n_estaciones"): 11}, estrato="macrozona")),
            "deriva en A": _entradas(d, motivos={"A": ("deriva",)}),
            "motivo desconocido": _entradas(d, motivos={"B": ("CD",)}),
            "E0 vacío": _entradas(d, motivos={c: ("finitud",) for c in ("A", "B", "AB", "C")},
                                  replicas=_solo(d["replicas"], ())),
            "réplicas sin un candidato de E0": _entradas(d, replicas=_solo(d["replicas"], ("A", "B", "AB"))),
            "réplicas con uno fuera de E0": _entradas(d, motivos={"C": ("finitud",)}),
            "cotas de TF distintas de §5.7": _entradas(d, tf=_con_tf(d["tf"], {("B", "T", "TF1"): {"cota_media": 0.06}})),
            "resultado de TF que no calza": _entradas(d, tf=_con_tf(d["tf"], {("B", "T", "TF1"): {"resultado": "falla"}})),
            "TF de A > 10⁻⁶ (error de código)": _entradas(d, tf=_con_tf(d["tf"], {("A", "Td", "TF2"): {
                "media_pond": 1e-5, "p95_pond": 1e-5}})),
            "TF1 no evaluable": _entradas(d, tf=_con_tf(d["tf"], {(c, "T", "TF1"): dict(_NO_EVALUABLE)
                                                                  for c in ("A", "B", "AB", "C")})),
            "falta una fila de TF de E0": _entradas(d, tf=d["tf"][~((d["tf"].candidato == "AB")
                                                                     & (d["tf"].prueba == "TF1")).to_numpy(dtype=bool)]
                                                    .reset_index(drop=True)),
        }
        for nombre, entradas in casos.items():
            with self.subTest(caso=nombre):
                with self.assertRaises((ValueError, TypeError)):
                    decision.decidir_combinacion("ambiental", "T_Td", entradas, umbrales=self.U)
        val = d["validacion"].copy()
        val["candidato"] = val["candidato"].replace({"C": "C_est"})
        with self.assertRaises(ValueError):                         # C_est no es candidato ambiental (§6.1)
            decision.decidir_combinacion("ambiental", "T_Td", _entradas(d, validacion=val), umbrales=self.U)
        with self.assertRaises(ValueError):                         # las entradas son de otro (uso, grupo)
            decision.decidir_combinacion("agudo", "T_Td", _entradas(d), umbrales=self.U)
        with self.assertRaises(ValueError):                         # lo agudo no decide (u, v)
            decision.compuertas("agudo", "u_v", tipos.EntradasDecision(tipos.Uso.AGUDO, tipos.Grupo.U_V, d["validacion"],
                                                                      d["tf"], d["replicas"], {}), self.U)
        with self.assertRaises(TypeError):
            decision.decidir_combinacion("ambiental", "T_Td", {"validacion": d["validacion"]}, umbrales=self.U)

        # §5.7: «un valor > 10⁻⁶ es un error de código»; el borde exacto no lo es.
        self.assertEqual(constantes.valor("TF_CERO_TOL"), 1e-6)
        for valor, error in ((1e-6, False), (float(np.nextafter(1e-6, 1.0)), True)):
            for columnas in ({"media_pond": valor, "p95_pond": 0.0}, {"media_pond": 0.0, "p95_pond": valor}):
                with self.subTest(valor=valor, columnas=list(columnas)):
                    entradas = _entradas(d, tf=_con_tf(d["tf"], {("A", "Td", "TF2"): columnas}))
                    if error:
                        with self.assertRaises(ValueError):
                            decision.decidir_combinacion("ambiental", "T_Td", entradas, umbrales=self.U)
                    else:
                        r = decision.decidir_combinacion("ambiental", "T_Td", entradas, umbrales=self.U)
                        self.assertEqual(r.ganador, "AB")

    def test_s07_e1_vacio(self):
        """E1 vacío: el de menor S entre los de E0 que pasan TF (A siempre la pasa), con la nota «regla sin ganador»."""
        # «e1_vacio» de sintetico (SIN-22): A sale por CD en T, B por EX en T, AB por TF y C por CD en HR
        # (4,0 > 1,10·3,0 + 0,5). AB tiene el menor S y falla TF: el paso 4 elige B, no AB.
        d = S.tablas_metricas("e1_vacio")
        t = decision.compuertas("ambiental", "T_Td", _entradas(d), self.U)
        self.assertEqual(_fallidas(t), {"A": {"CD"}, "B": {"EX"}, "AB": {"TF"}, "C": {"CD"}})
        r = self._decidir(d)
        self.assertEqual(min(r.S, key=r.S.get), "AB")
        self.assertEqual((r.e1, r.ganador, r.notas), ((), "B", ("regla sin ganador",)))
        self.assertEqual(r.motivos, {"A": ("CD",), "B": ("EX",), "AB": ("TF",), "C": ("CD",)})

        # B falla además TF: gana A, que siempre la pasa (sin el filtro ganaría AB, y después B).
        tf = _con_tf(d["tf"], {("B", "Td", "TF1"): {"media_pond": 0.30, "p95_pond": 0.75, "resultado": "falla"}})
        r = self._decidir(d, _entradas(d, tf=tf))
        self.assertEqual((r.e1, r.ganador, r.notas), ((), "A", ("regla sin ganador",)))
        self.assertEqual(r.motivos["B"], ("TF", "EX"))

        # C (artefacto 0 por construcción) con TF1 fallida de 0,15 K: error de código (§5.7), no una compuerta.
        tf = _con_tf(d["tf"], {("C", "T", "TF1"): {"media_pond": 0.15, "p95_pond": 0.45, "resultado": "falla"}})
        with self.assertRaisesRegex(ValueError, "error de código"):
            self._decidir(d, _entradas(d, tf=tf))

        # Si nadie de E0 pasa TF (A y C fuera de E0), no hay ganador posible: error, no se decide a mano.
        g = S.tablas_metricas("ganador_claro")
        tf = _con_tf(g["tf"], {("B", "T", "TF1"): {"media_pond": 0.15, "p95_pond": 0.45, "resultado": "falla"},
                               ("AB", "T", "TF2"): {"media_pond": 0.15, "p95_pond": 0.45, "resultado": "falla"}})
        entradas = _entradas(g, tf=tf, motivos={"A": ("finitud",), "C": ("finitud",)},
                             replicas=_solo(g["replicas"], ("B", "AB")))
        with self.assertRaises(ValueError):
            decision.decidir_combinacion("ambiental", "T_Td", entradas, umbrales=self.U)

    def test_s07_regla_cronica_y_caso_mixto(self):
        """Paso 5 de §6.2 [M0, B8]: ni B ni AB en E1 y al menos uno falla TF o la deriva → compiten A y C_est (en E1,
        o en E0 si ninguno está); con los dos fuera sólo por otras compuertas rigen los pasos 3 y 4."""
        # B falla TF y AB, deriva; E1 = {A, C_est}.
        d = S.tablas_metricas("cronica")
        r = self._decidir(d)
        self.assertEqual((r.e1, r.ganador, r.notas), (("A", "C_est"), "A", ("regla crónica",)))
        self.assertEqual(r.motivos, {"B": ("TF",), "AB": ("deriva",)})

        # Caso mixto: B falla TF y AB queda fuera por CD; E1 vacío → entre A y C_est de E0 (el paso 4 daría AB).
        d = S.tablas_metricas("cronica_mixta")
        r = self._decidir(d)
        self.assertEqual((r.e1, r.ganador), ((), "C_est"))
        self.assertEqual(r.notas, ("regla crónica", "regla sin ganador"))           # DEC-10
        self.assertEqual(min((c for c in r.e0 if c != "B"), key=r.S.get), "AB")   # el paso 4 elegiría AB

        # Los dos fuera sólo por otras compuertas (B por EX, AB por CD): pasos 3 y 4, sin regla crónica.
        val = _con_metricas(d["validacion"], {("B", "temp_media", "EX"): 0.90})
        r = self._decidir(d, _entradas(d, validacion=val, tf=_sin_tf_de_b(d)))
        self.assertEqual(r.motivos["B"], ("EX",))
        self.assertEqual((r.e1, r.ganador, r.notas), ((), "B", ("regla sin ganador",)))

        # Mixto por la deriva: AB fuera de E0 por deriva y B fuera sólo por CD; dispara («basta uno»).
        val = _con_metricas(d["validacion"], {("B", "T", "CD"): 0.45})
        r = self._decidir(d, _entradas(d, validacion=val, tf=_sin_tf_de_b(d), motivos={"AB": ("deriva",)},
                                       replicas=_solo(d["replicas"], ("A", "B", "C_est"))))
        self.assertEqual((r.e1, r.ganador), ((), "C_est"))
        self.assertEqual(r.motivos["B"], ("CD",))
        self.assertIn("regla crónica", r.notas)

        # B en E1: no rige (aunque AB falló la deriva); gana B por el paso 3.
        c = S.tablas_metricas("cronica")
        r = self._decidir(c, _entradas(c, tf=_sin_tf_de_b(c)))
        self.assertEqual((r.ganador, r.notas), ("B", ()))

        # DEC-9: B fuera de E0 por finitud con su TF1 «falla» en la tabla cuenta como «falla TF».
        r = self._decidir(d, _entradas(d, motivos={"B": ("finitud",)},
                                       replicas=_solo(d["replicas"], ("A", "AB", "C_est"))))
        self.assertEqual((r.e1, r.ganador), ((), "C_est"))
        self.assertIn("regla crónica", r.notas)
        r = self._decidir(d, _entradas(d, tf=_sin_tf_de_b(d), motivos={"B": ("finitud",)},
                                       replicas=_solo(d["replicas"], ("A", "AB", "C_est"))))
        self.assertEqual((r.ganador, r.notas), ("AB", ("regla sin ganador",)))      # sin TF fallida: paso 4
        # Sin filas de TF de B (fuera de E0), B no cuenta como «falla TF».
        sin_b = d["tf"][(d["tf"].candidato != "B").to_numpy(dtype=bool)].reset_index(drop=True)
        r = self._decidir(d, _entradas(d, tf=sin_b, motivos={"B": ("finitud",)},
                                       replicas=_solo(d["replicas"], ("A", "AB", "C_est"))))
        self.assertEqual((r.ganador, r.notas), ("AB", ("regla sin ganador",)))
        # DEC-5 también fuera de E0: TF1 «no evaluable», un resultado que no calza o cotas que no son las de §5.7.
        fuera = {"motivos": {"B": ("finitud",)}, "replicas": _solo(d["replicas"], ("A", "AB", "C_est"))}
        for nombre, cambios in {"TF1 no evaluable": {"media_pond": float("nan"), "p95_pond": float("nan"),
                                                     "resultado": "no_evaluable"},
                                "«falla» dentro de las cotas": {"media_pond": 0.01, "p95_pond": 0.03},
                                "cotas distintas": {"cota_media": 0.06}}.items():
            with self.subTest(caso=nombre), self.assertRaises(ValueError):
                self._decidir(d, _entradas(d, tf=_con_tf(d["tf"], {("B", "T", "TF1"): cambios}), **fuera))
        # EMC1-2 fuera de E0: con B y AB fuera por finitud y TF2 «no evaluable» en T, rige la regla crónica (TF2 no
        # evaluable «cuenta como falla en E1 y en los pasos 4 y 5»).
        n = S.tablas_metricas("tf2_no_evaluable")
        r = self._decidir(n, _entradas(n, motivos={"B": ("finitud",), "AB": ("finitud",)},
                                       replicas=_solo(n["replicas"], ("A", "C_est"))))
        self.assertEqual((r.e0, r.e1, r.ganador), (("A", "C_est"), ("A", "C_est"), "C_est"))
        self.assertEqual(r.notas, ("regla crónica", "TF2 no evaluable"))

        # Con la regla y ni A ni C_est en E0: error.
        with self.assertRaises(ValueError):
            self._decidir(d, _entradas(d, motivos={"A": ("finitud",), "C_est": ("finitud",)},
                                       replicas=_solo(d["replicas"], ("B", "AB"))))

    def test_s07_tf2_no_evaluable_excluye_b_y_ab_y_dispara_la_regla_cronica(self):
        """EMC1-2: red constante con menos de 10 estaciones en las tres reglas; registro y regla crónica."""
        d = S.tablas_metricas("tf2_no_evaluable")
        tf2 = d["tf"][d["tf"].prueba == "TF2"]
        self.assertTrue(((tf2.regla_red == "ninguna") & (tf2.n_red < 10)).all())
        r = self._decidir(d)
        self.assertEqual(r.motivos, {"B": ("TF2 no evaluable",), "AB": ("TF2 no evaluable",)})
        self.assertEqual(r.red_tf2, {"T": ReglaRedConstante.NINGUNA})
        self.assertEqual((r.e1, r.ganador), (("A", "C_est"), "C_est"))
        self.assertEqual(r.notas, ("regla crónica", "TF2 no evaluable"))
        t = decision.compuertas("cronico", "T_Td", _entradas(d), self.U)
        tf2 = t[(t.compuerta == "TF") & (t.ambito == "TF2")].set_index("candidato")
        self.assertTrue(tf2.loc[["A", "C_est"], "pasa"].all())                     # A, C y C_est pasan TF2 en v
        self.assertFalse(tf2.loc[["B", "AB"], "pasa"].any())
        self.assertEqual(set(tf2.motivo), {"TF2 no evaluable"})
        tf1 = t[(t.compuerta == "TF") & (t.ambito == "TF1")]
        self.assertTrue(tf1.pasa.all() and (tf1.motivo == "").all())               # su TF1 se calcula igual

        # Ambiental (T, Td), TF2 no evaluable en Td: B y AB fuera en el grupo, gana A entre A y C.
        g = S.tablas_metricas("ganador_claro")
        tf = _con_tf(g["tf"], {(c, "Td", "TF2"): dict(_NO_EVALUABLE) for c in ("A", "B", "AB", "C")})
        r = self._decidir(g, _entradas(g, tf=tf))
        self.assertEqual((r.e1, r.ganador, r.notas), (("A", "C"), "A", ("TF2 no evaluable",)))
        self.assertEqual(r.red_tf2, {"T": ReglaRedConstante.R2000_2025, "Td": ReglaRedConstante.NINGUNA})
        # B además falla TF1 en T: los dos motivos.
        tf_b = _con_tf(tf, {("B", "T", "TF1"): {"media_pond": 0.15, "p95_pond": 0.45, "resultado": "falla"}})
        self.assertEqual(self._decidir(g, _entradas(g, tf=tf_b)).motivos["B"], ("TF", "TF2 no evaluable"))
        # TF2 no evaluable en una variable de otro grupo (la rapidez) no toca a (T, Td).
        extra = g["tf"][(g["tf"].variable == "T").to_numpy(dtype=bool)].copy()
        extra["variable"] = pd.array(["rapidez"] * len(extra), dtype="string")
        tf_r = _con_tf(pd.concat([g["tf"], extra], ignore_index=True),
                       {(c, "rapidez", "TF2"): dict(_NO_EVALUABLE) for c in ("A", "B", "AB", "C")})
        tipos.validar_esquema(tf_r, tipos.ESQUEMA_TF, nombre="tf")
        r = self._decidir(g, _entradas(g, tf=tf_r))
        self.assertEqual((r.ganador, r.notas, set(r.red_tf2)), ("AB", (), {"T", "Td"}))

        # Registros incoherentes: error.
        incoherentes = {
            "no evaluable con una red": {(c, "T", "TF2"): {"regla_red": "r2010_2025"} for c in ("A", "B", "AB", "C_est")},
            "no evaluable con 10 o más estaciones": {(c, "T", "TF2"): {"n_red": 12} for c in ("A", "B", "AB", "C_est")},
            "redes distintas entre candidatos": {("A", "T", "TF2"): {"regla_red": "r2003_2025"}},
            "redes de distinto tamaño entre candidatos (no evaluable)": {("A", "T", "TF2"): {"n_red": 8}},
        }
        for nombre, cambios in incoherentes.items():
            with self.subTest(caso=nombre), self.assertRaises(ValueError):
                self._decidir(d, _entradas(d, tf=_con_tf(d["tf"], cambios)))
        c = S.tablas_metricas("cronica")
        for nombre, cambios in {"no evaluable sólo en B": {("B", "T", "TF2"): dict(_NO_EVALUABLE)},
                                "evaluable con la red «ninguna»": {(x, "T", "TF2"): {"regla_red": "ninguna"}
                                                                  for x in ("A", "B", "AB", "C_est")},
                                "redes de distinto tamaño entre candidatos": {("A", "T", "TF2"): {"n_red": 40}},
                                "distinto tamaño en uno fuera de E0": {("AB", "T", "TF2"): {"n_red": 40}}}.items():
            with self.subTest(caso=nombre), self.assertRaises(ValueError):
                self._decidir(c, _entradas(c, tf=_con_tf(c["tf"], cambios)))
        with self.assertRaises(ValueError):                         # también en lo ambiental (ganador_claro)
            self._decidir(g, _entradas(g, tf=_con_tf(g["tf"], {("A", "T", "TF2"): {"n_red": 40}})))

    def test_s07_empates_exactos_y_determinismo(self):
        """Orden fijo A, AB, B, C (C_est en lo crónico); empate = igualdad en float64 (MC-63); el resultado no depende
        del orden de las filas."""
        r = self._decidir(S.tablas_metricas("empate"))
        self.assertEqual(r.S["A"], r.S["AB"])
        self.assertEqual(r.ganador, "A")
        p = S.tablas_metricas("p_sin_ex")
        casos = {"AB frente a B": ({("AB", "p", "CD"): 0.21, ("B", "p", "S"): 0.85}, "AB"),
                 "B frente a C": ({("B", "p", "S"): 0.95, ("C", "p", "S"): 0.95}, "B"),
                 "A frente a C": ({("A", "p", "S"): 0.95, ("C", "p", "S"): 0.95, ("B", "p", "S"): 1.2}, "A")}
        for nombre, (cambios, ganador) in casos.items():
            with self.subTest(caso=nombre):
                r = self._decidir(p, _entradas(p, validacion=_con_metricas(p["validacion"], cambios)))
                self.assertEqual(r.ganador, ganador)
        c = S.tablas_metricas("cronica")
        val = _con_metricas(c["validacion"], {("C_est", "T", "S"): 0.30})
        r = self._decidir(c, _entradas(c, validacion=val, tf=_sin_tf_de_b(c)))
        self.assertEqual((r.S["B"], r.ganador), (r.S["C_est"], "B"))
        # Crónico, AB frente a B: E1 = {B, AB} con S_AB = S_B → AB (A, AB, B, C_est). A sale por EX y C_est por la
        # anomalía, como en «cronica_mixta»; B pasa TF y AB, CD.
        m = S.tablas_metricas("cronica_mixta")
        val = _con_metricas(m["validacion"], {("AB", "T", "CD"): 0.30, ("AB", "T", "S"): 0.30})
        r = self._decidir(m, _entradas(m, validacion=val, tf=_sin_tf_de_b(m)))
        self.assertEqual((r.e1, r.S["AB"], r.ganador, r.notas), (("B", "AB"), r.S["B"], "AB", ()))
        # Un ulp de diferencia no es empate: gana el menor aunque vaya después en el orden (en p, con un solo S; en
        # S_par un ulp de S_T puede perderse al sumar, y entonces sí es empate en float64).
        val = _con_metricas(p["validacion"], {("A", "p", "S"): float(np.nextafter(0.90, 1.0))})
        r = self._decidir(p, _entradas(p, validacion=val))
        self.assertLess(r.S["B"], r.S["A"])
        self.assertEqual(r.ganador, "B")

        # Determinismo: barajar las filas y el orden de motivos_e0 no cambia nada, ni el registro.
        rng = np.random.default_rng(20261026)
        for caso in ("ganador_claro", "cronica_mixta", "tf2_no_evaluable", "deriva", "uv"):
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                base = self._decidir(d)
                barajadas = _entradas(
                    d, validacion=d["validacion"].sample(frac=1.0, random_state=rng.integers(1 << 30)).reset_index(drop=True),
                    tf=d["tf"].sample(frac=1.0, random_state=rng.integers(1 << 30)).reset_index(drop=True),
                    replicas=d["replicas"].sample(frac=1.0, random_state=rng.integers(1 << 30)).reset_index(drop=True),
                    motivos=dict(reversed(list(d["e0_excluidos"].items()))))
                otra = self._decidir(d, barajadas)
                self.assertEqual(otra, base)
                self.assertEqual(self._decidir(d), base)
                hip = {(d["uso"], d["grupo"]): {}}
                self.assertEqual(json.dumps(decision.decision_json([otra], hip, {}), sort_keys=True),
                                 json.dumps(decision.decision_json([base], hip, {}), sort_keys=True))

    def test_s07_intervalo_de_delta_s_con_el_ganador_de_cada_replica(self):
        """§5.4 con MC-34 (D5) y D46: en cada réplica gana el de menor S de réplica dentro del conjunto en que eligió la
        decisión (E1, el paso 4 o el paso 5), con el mismo desempate, y ΔS_c,r = S_c,r − S_ganador_r,r. Las compuertas
        no se rehacen por réplica: uno fuera de ese conjunto con un S de réplica menor nunca gana una réplica."""
        nivel = constantes.valor("BOOT_IC_PCT")
        self.assertEqual(nivel, 95)
        n = 40

        # Paso 3: E1 = {A, B, AB, C} y gana AB; B gana las 10 primeras réplicas.
        g = S.tablas_metricas("ganador_claro")
        rep = _replicas_a_mano({"A": [1.20] * n, "B": [0.95] * 10 + [1.10] * 30, "AB": [1.00] * n, "C": [1.30] * n})
        r = self._decidir(g, _entradas(g, replicas=rep))
        self.assertEqual((r.e1, r.ganador), (("A", "B", "AB", "C"), "AB"))
        for c in r.e0:
            self.assertEqual(r.ic_delta_S[c], _ic_d46(rep, r.e1, c, nivel), c)
        # El del ganador ya no es [0, 0] (lo sería con el ganador fijo): 0 en 30 réplicas y 0,05 en 10.
        self.assertEqual(r.ic_delta_S["AB"], (0.0, 1.00 - 0.95))
        self.assertEqual(r.ic_delta_S["B"], (0.0, 1.10 - 1.00))     # con el ganador fijo, el extremo bajo sería −0,05
        self.assertEqual(r.delta_S["AB"], 0.0)                      # ΔS sigue con el ganador de la decisión

        # Paso 3 con uno fuera de E1: AB falla CD y tiene el menor S en todas las réplicas; no gana ninguna.
        cd = S.tablas_metricas("compuerta_cd")
        rep = _replicas_a_mano({"A": [1.20] * n, "B": [1.10] * n, "AB": [0.50] * n, "C": [1.30] * n})
        r = self._decidir(cd, _entradas(cd, replicas=rep))
        self.assertEqual((r.e1, r.ganador), (("A", "B", "C"), "B"))
        self.assertEqual(r.ic_delta_S["B"], (0.0, 0.0))
        self.assertEqual(r.ic_delta_S["AB"], (0.50 - 1.10, 0.50 - 1.10))
        self.assertEqual(r.ic_delta_S["A"], _ic_d46(rep, r.e1, "A", nivel))

        # Paso 4: E1 vacío; AB falla TF y tiene el menor S: el ganador de cada réplica sale de {A, B, C}.
        d = S.tablas_metricas("e1_vacio")
        rep = _replicas_a_mano({"A": [1.20] * n, "B": [1.00] * 20 + [1.25] * 20, "AB": [0.50] * n, "C": [1.30] * n})
        r = self._decidir(d, _entradas(d, replicas=rep))
        self.assertEqual((r.e1, r.ganador, _conjunto_a_mano(r)), ((), "B", ("A", "B", "C")))
        for c in r.e0:
            self.assertEqual(r.ic_delta_S[c], _ic_d46(rep, ("A", "B", "C"), c, nivel), c)
        self.assertEqual(r.ic_delta_S["AB"], (0.50 - 1.20, 0.50 - 1.00))  # nunca 0: AB no gana réplicas
        self.assertEqual(r.ic_delta_S["B"], (0.0, 1.25 - 1.20))

        # Paso 5: la regla crónica; compiten A y C_est de E1, y B (fuera por TF) tiene el menor S.
        c = S.tablas_metricas("cronica")
        rep = _replicas_a_mano({"A": [0.36] * 20 + [0.40] * 20, "B": [0.30] * n, "C_est": [0.38] * n})
        r = self._decidir(c, _entradas(c, replicas=rep))
        self.assertEqual((r.e1, r.ganador, r.notas), (("A", "C_est"), "A", ("regla crónica",)))
        for x in r.e0:
            self.assertEqual(r.ic_delta_S[x], _ic_d46(rep, ("A", "C_est"), x, nivel), x)
        self.assertEqual(r.ic_delta_S["A"], (0.0, 0.40 - 0.38))
        self.assertLess(r.ic_delta_S["B"][1], 0.0)

        # Con las réplicas de sintetico, en todos los casos de S7: el conjunto leído del registro (_conjunto_a_mano).
        for caso in S.CASOS_METRICAS:
            if caso == "soporte":
                continue
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                r = self._decidir(d)
                conjunto = _conjunto_a_mano(r)
                self.assertIn(r.ganador, conjunto)
                for x in r.e0:
                    self.assertEqual(r.ic_delta_S[x], _ic_d46(d["replicas"], conjunto, x, nivel), x)
                self.assertGreaterEqual(r.ic_delta_S[r.ganador][0], 0.0)

    def test_s07_tablas_metricas_tal_cual(self):
        """Acuerdo A11 (TIP-12): cada caso de ``sintetico.tablas_metricas``, tal como sale y sin ningún rodeo, calza con
        ``decision``: las compuertas que falla cada candidato, E0, E1, el ganador, las notas y el S del grupo del
        esperado. Si algún caso deja de calzar por un desajuste conocido (``_desajustes_i5``), debe fallar por esa
        razón (el texto del error) y la prueba se omite con la lista: no se da por aprobada mientras I5 no lo
        corrija. Cubre también lo que ``test_tipos`` sólo mira por esquema."""
        pendientes = {}
        casos = [c for c in S.CASOS_METRICAS if c != "soporte"]      # «soporte» es de la regla de soporte (I14)
        for caso in casos:
            d = S.tablas_metricas(caso)
            e = d["esperado"]
            desajustes = _desajustes_i5(d)
            with self.subTest(caso=caso, desajustes=tuple(desajustes)):
                errores = [p for p in desajustes.values() if p is not None]
                if errores:
                    with self.assertRaisesRegex(ValueError, "|".join(errores)):
                        decision.decidir_combinacion(d["uso"], d["grupo"], _entradas(d), umbrales=self.U)
                    pendientes[caso] = tuple(desajustes)
                    continue
                tabla = decision.compuertas(d["uso"], d["grupo"], _entradas(d), self.U)
                self.assertEqual(_fallidas(tabla), {c: set(s) for c, s in e["fallas"].items()})
                r = decision.decidir_combinacion(d["uso"], d["grupo"], _entradas(d), umbrales=self.U)
                self.assertEqual((r.e0, r.e1, r.ganador, r.S), (e["e0"], e["e1"], e["ganador"], e["S"]))
                if desajustes:                                       # sólo la nota de DEC-10
                    self.assertEqual(r.notas, tuple(n for n in decision.ORDEN_NOTAS
                                                    if n in (*e["notas"], "regla sin ganador")))
                    pendientes[caso] = tuple(desajustes)
                else:
                    self.assertEqual(r.notas, e["notas"])
        if pendientes:
            lista = "; ".join(f"{c} ({', '.join(x)})" for c, x in pendientes.items())
            self.skipTest(f"{len(pendientes)} de {len(casos)} casos de sintetico.tablas_metricas no calzan tal cual con "
                          f"decision (acuerdo A11), pendientes de I5: {lista}. La prueba no se da por aprobada")


# ---------------------------------------------------------------------------------------------------------------
# S16: Anexo B
# ---------------------------------------------------------------------------------------------------------------
class PruebasS16(unittest.TestCase):
    def setUp(self):
        self.U = _umbrales()
        self.amb = _ambientales()
        self.ganadores = {g: decision.decidir_combinacion("ambiental", g, e, umbrales=self.U).ganador
                          for g, e in self.amb.items()}

    def _ramas(self, caso, *, tf=None, ganadores=None, **kw):
        d = S.tablas_m6(caso)
        return decision.ramas_m6(_condiciones(d, self.U), tf or d["tf_contaminantes"], ganadores or self.ganadores,
                                 entradas_ambientales=kw.get("entradas", self.amb), umbrales=self.U)

    def test_s16_tres_ramas(self):
        """Las tres ramas del Anexo B en cada caso de sintetico (rama y variante esperadas, calculadas aparte)."""
        self.assertEqual(self.ganadores, {"T_Td": "AB", "u_v": "A", "p": "B"})
        for caso in S.CASOS_M6:
            with self.subTest(caso=caso):
                r = self._ramas(caso)
                e = S.tablas_m6(caso)["esperado"]
                self.assertEqual({p: int(x) for p, x in r.rama.items()}, e["rama"])
                self.assertEqual({k: v.value for k, v in r.variante.items()}, e["variante"])
                self.assertEqual(r.ganador_restringido is not None, e["restringido"])
                self.assertTrue(all(isinstance(x, Rama) for x in r.rama.values()))
        self.assertEqual(self._ramas("rama1_I").rama, {"pm25": Rama.UNO, "no2": Rama.UNO})
        self.assertEqual(self._ramas("rama3").rama["pm25"], Rama.TRES)
        # Rama 2 con D: ninguna supera, I falla su TF y D pasa la suya.
        r = self._ramas("rama2_ninguna", tf={"pm25": {"I": "falla", "D": "pasa"}, "no2": {"I": "pasa", "D": "pasa"}})
        self.assertEqual((r.rama["pm25"], r.variante["pm25"]), (Rama.DOS, Variante.D))
        self.assertEqual((r.rama["no2"], r.variante["no2"]), (Rama.DOS, Variante.I))
        # Rama 1 de D que no pasa su TF y con la de I fallida también: rama 3.
        r = self._ramas("rama1_D", tf={"pm25": {"I": "falla", "D": "falla"}, "no2": {"I": "pasa", "D": "pasa"}})
        self.assertEqual((r.rama["pm25"], r.variante["pm25"]), (Rama.TRES, Variante.I))
        self.assertEqual((r.rama["no2"], r.variante["no2"]), (Rama.UNO, Variante.D))
        # Las 7 condiciones: cada caso de una sola condición fallida deja a D sin superar en pm25.
        for caso in [c for c in S.CASOS_M6 if c.startswith("falla_c")]:
            with self.subTest(caso=caso):
                cond = decision.condiciones_anexo_b(S.tablas_m6(caso)["comparacion"], "pm25", "D_frente_a_I", self.U)
                self.assertEqual(len(cond), 7)
                self.assertEqual(cond.count(False), 1)
        # Condición 7 en puntos porcentuales (SIN-17): con 0,01 en vez de 1 punto, «c7_en_puntos» no pasaría.
        comp = S.tablas_m6("c7_en_puntos")["comparacion"]
        self.assertTrue(decision.condiciones_anexo_b(comp, "pm25", "D_frente_a_I", self.U)[6])
        self.assertFalse(decision.condiciones_anexo_b(comp, "pm25", "D_frente_a_I",
                                                      _UFalso(self.U, M6_NMB_PP=0.01))[6])

    def test_s16_simetria_a_lo_mas_una_supera(self):
        """Por la condición 1: a lo más una variante supera; las dos a la vez es un error; cada condición se exige en
        LRO y en BLQ-75 a la vez."""
        for caso in S.CASOS_M6:
            with self.subTest(caso=caso):
                cond = _condiciones(S.tablas_m6(caso), self.U)
                for pol in S.CONTAMINANTES_M6:
                    self.assertLessEqual(sum(all(cond[pol][s]) for s in S.SENTIDOS_M6), 1)
        todas = {p: {s: [True] * 7 for s in S.SENTIDOS_M6} for p in S.CONTAMINANTES_M6}
        with self.assertRaises(ValueError):
            decision.ramas_m6(todas, S.tablas_m6("rama1_I")["tf_contaminantes"], self.ganadores)
        # «solo_lro»: D cumple todo en LRO, pero no en BLQ-75 → no supera.
        cond = decision.condiciones_anexo_b(S.tablas_m6("solo_lro")["comparacion"], "pm25", "D_frente_a_I", self.U)
        self.assertFalse(all(cond))
        comp = S.tablas_m6("rama1_D")["comparacion"]
        sin_blq = comp[~((comp.contaminante == "pm25") & (comp.protocolo == "BLQ-75")).to_numpy(dtype=bool)]
        with self.assertRaises(ValueError):
            decision.condiciones_anexo_b(sin_blq.reset_index(drop=True), "pm25", "D_frente_a_I", self.U)
        with self.assertRaises(ValueError):                                       # el Anexo B no compara O3
            decision.condiciones_anexo_b(comp, "o3", "D_frente_a_I", self.U)
        incompletas = {p: {"I_frente_a_D": [False] * 7} for p in S.CONTAMINANTES_M6}
        with self.assertRaises(ValueError):                                       # los dos sentidos
            decision.ramas_m6(incompletas, S.tablas_m6("rama1_I")["tf_contaminantes"], self.ganadores)

    def test_s16_desempate_en_i(self):
        """Rama 2: ninguna supera y las dos pasan su TF → I. La TF de I se exige con un ganador B o AB; con A o C, su
        entrada es la verificación de un mes (Anexo B: «con A o C es 0 por construcción y se verifica en un mes»), que
        debe venir y decir «pasa» (DEC-14)."""
        r = self._ramas("rama2_ninguna")
        self.assertEqual({p: r.variante[p] for p in S.CONTAMINANTES_M6}, {"pm25": Variante.I, "no2": Variante.I})
        self.assertEqual(set(r.rama.values()), {Rama.DOS})
        amb = _ambientales_sin_b_ab()
        sin_b_ab = {g: decision.decidir_combinacion("ambiental", g, e, umbrales=self.U).ganador for g, e in amb.items()}
        self.assertEqual(sin_b_ab, {"T_Td": "A", "u_v": "A", "p": "A"})
        solo_d = {p: {"D": "pasa"} for p in S.CONTAMINANTES_M6}
        verificada = {p: {"I": "pasa", "D": "pasa"} for p in S.CONTAMINANTES_M6}
        r = self._ramas("rama2_ninguna", tf=verificada, ganadores=sin_b_ab, entradas=amb)
        self.assertEqual(r.variante["pm25"], Variante.I)
        r = self._ramas("rama1_D", tf={p: {"I": "pasa", "D": "falla"} for p in S.CONTAMINANTES_M6},
                        ganadores=sin_b_ab, entradas=amb)
        self.assertEqual((r.rama["pm25"], r.variante["pm25"]), (Rama.DOS, Variante.I))
        with self.assertRaises(ValueError):                                 # sin la verificación de un mes de I
            self._ramas("rama2_ninguna", tf=solo_d, ganadores=sin_b_ab, entradas=amb)
        with self.assertRaises(ValueError):                                 # «falla» de I con A o C: error de código
            self._ramas("rama2_ninguna", tf={p: {"I": "falla", "D": "pasa"} for p in S.CONTAMINANTES_M6},
                        ganadores=sin_b_ab, entradas=amb)
        with self.assertRaises(ValueError):                                 # con B o AB, la TF de I es obligatoria
            self._ramas("rama2_ninguna", tf=solo_d)
        with self.assertRaises(ValueError):                                 # la de D, siempre
            self._ramas("rama2_ninguna", tf={p: {"I": "pasa"} for p in S.CONTAMINANTES_M6})

    def test_s16_condicion_1_y_comparaciones_incompletas(self):
        """Condición 1: un IC que «excluye 0 a favor de c» (``ic_bajo`` = 0 no lo excluye); un IC invertido o un IC o
        un NMB no finito es un error (DEC-13)."""
        comp = S.tablas_m6("rama1_D")["comparacion"]

        def con(cambios, protocolo="LRO"):
            c = comp.copy()
            m = ((c.contaminante == "pm25") & (c.sentido == "D_frente_a_I") & (c.protocolo == protocolo)
                 ).to_numpy(dtype=bool)
            self.assertEqual(int(m.sum()), 1)
            for col, x in cambios.items():
                c.loc[m, col] = x
            return c

        def cond(c):
            return decision.condiciones_anexo_b(c, "pm25", "D_frente_a_I", self.U)

        self.assertEqual(cond(comp), [True] * 7)
        for protocolo in ("LRO", "BLQ-75"):
            with self.subTest(protocolo=protocolo):
                self.assertEqual(cond(con({"ic_bajo": 0.0}, protocolo)), [False] + [True] * 6)
                self.assertEqual(cond(con({"ic_bajo": float(np.nextafter(0.0, 1.0))}, protocolo)), [True] * 7)
        nan, inf = float("nan"), float("inf")
        for cambios in ({"ic_bajo": 0.03}, {"ic_alto": nan}, {"ic_bajo": nan}, {"ic_alto": inf}, {"ic_bajo": -inf},
                        {"nmb_c": nan}, {"nmb_otra": inf}):
            with self.subTest(cambios=cambios), self.assertRaises(ValueError):
                cond(con(cambios, "BLQ-75"))

    def test_s16_ganador_ambiental_contrastado_con_las_entradas(self):
        """DEC-16: con las entradas ambientales, ``ganador_ambiental`` debe ser, grupo por grupo, el que dan."""
        for ganadores in ({**self.ganadores, "u_v": "C"}, {**self.ganadores, "T_Td": "B"}):
            for caso in ("rama3", "rama1_D"):
                with self.subTest(ganadores=ganadores, caso=caso), self.assertRaises(ValueError):
                    self._ramas(caso, ganadores=ganadores)
        r = self._ramas("rama1_D", ganadores={**self.ganadores, "u_v": "C"}, entradas=None)   # sin entradas: no se
        self.assertEqual(r.rama["pm25"], Rama.UNO)                                          # contrasta (ramas 1 y 2)
        with self.assertRaises(ValueError):                                 # con entradas hacen falta los umbrales
            d = S.tablas_m6("rama1_D")
            decision.ramas_m6(_condiciones(d, self.U), d["tf_contaminantes"], self.ganadores,
                              entradas_ambientales=self.amb)

    def test_s16_regla_de_o3(self):
        """La elegida en PM2,5 y NO2 si coinciden; si difieren, I."""
        self.assertEqual(self._ramas("o3_difieren").variante["O3"], Variante.I)
        self.assertEqual(self._ramas("rama1_D").variante["O3"], Variante.D)
        self.assertEqual(self._ramas("rama1_I").variante["O3"], Variante.I)
        self.assertEqual(decision.variante_o3({"pm25": "D", "no2": "D"}), "D")
        self.assertEqual(decision.variante_o3({"pm25": "D", "no2": "I"}), "I")
        self.assertEqual(decision.variante_o3({"pm25": Variante.I, "no2": Variante.I}), "I")
        for malo in ({"pm25": "D"}, {"pm25": "D", "no2": "D", "o3": "D"}, {"pm25": "D", "no2": "X"}):
            with self.subTest(entrada=malo), self.assertRaises(ValueError):
                decision.variante_o3(malo)

    def test_s16_variante_por_contaminante(self):
        """Una variante por contaminante."""
        r = self._ramas("o3_difieren")
        self.assertEqual((r.variante["pm25"], r.variante["no2"]), (Variante.I, Variante.D))
        r = self._ramas("rama3")
        self.assertEqual((r.rama["pm25"], r.variante["pm25"]), (Rama.TRES, Variante.I))
        self.assertEqual((r.rama["no2"], r.variante["no2"]), (Rama.UNO, Variante.I))
        r = self._ramas("borde_c7")
        self.assertEqual({k: v.value for k, v in r.variante.items()}, {"pm25": "D", "no2": "D", "O3": "D"})

    def test_s16_ganador_restringido_para_todos_solo_grupos_con_b_o_ab(self):
        """Rama 3 en un contaminante: restringido para todos, rehaciendo sólo los grupos con B o AB (entre A y C de E0,
        con las compuertas de §6.2 y su paso 4)."""
        r = self._ramas("rama3")
        self.assertEqual(r.ganador_restringido, {"T_Td": "A", "u_v": "A", "p": "A"})
        self.assertEqual(r.notas, ("I restringido por TF de contaminantes",))
        self.assertEqual(r.rama["no2"], Rama.UNO)                  # no2 conserva su rama; el restringido vale igual
        dec = decision.decisiones_restringidas(self.amb, {"T_Td", "p"}, umbrales=self.U)
        originales = {g: decision.decidir_combinacion("ambiental", g, e, umbrales=self.U) for g, e in self.amb.items()}
        self.assertEqual(dec["u_v"], originales["u_v"])            # los grupos con A o C quedan igual
        for g in ("T_Td", "p"):
            with self.subTest(grupo=g):
                self.assertTrue(set(dec[g].e0) <= {"A", "C"} and set(dec[g].e1) <= set(dec[g].e0))
                self.assertIn("I restringido por TF de contaminantes", dec[g].notas)
                for c in ("B", "AB"):
                    self.assertIn("TF de contaminantes", dec[g].motivos[c])
                for c in dec[g].e0:                                 # DEC-15: el S de la decisión original
                    self.assertEqual(dec[g].S[c], originales[g].S[c])
                self.assertEqual(dec[g].delta_S[dec[g].ganador], 0.0)
                for c in dec[g].e0:                                 # D46: el ganador de cada réplica, entre A y C
                    self.assertEqual(dec[g].ic_delta_S[c],
                                     _ic_d46(self.amb[g].replicas, _conjunto_a_mano(dec[g]), c, 95), c)
        self.assertEqual(dec["p"].motivos["AB"], ("CD", "TF de contaminantes"))

        # D46 en la rama 3, con réplicas hechas a mano: AB tiene el menor S en todas y C gana 10 de 40 frente a A. El
        # ganador de cada réplica sale de {A, C} (no del E0 original, que lo daría siempre a AB, ni fijo en A).
        n = 40
        rep = _replicas_a_mano({"A": [1.15] * 30 + [1.30] * 10, "B": [1.08] * n, "AB": [1.00] * n, "C": [1.26] * n})
        amb = _ambientales(T_Td={"replicas": rep})
        d = decision.decisiones_restringidas(amb, {"T_Td", "p"}, umbrales=self.U)["T_Td"]
        self.assertEqual((d.e0, d.e1, d.ganador), (("A", "C"), ("A", "C"), "A"))
        self.assertEqual(d.ic_delta_S["A"], (0.0, 1.30 - 1.26))
        self.assertEqual(d.ic_delta_S["C"], _ic_d46(rep, ("A", "C"), "C", 95))
        self.assertEqual(d.ic_delta_S["C"][0], 0.0)
        o = decision.decidir_combinacion("ambiental", "T_Td", amb["T_Td"], umbrales=self.U)
        self.assertEqual(o.ic_delta_S["AB"], (0.0, 0.0))            # sin restringir, AB gana todas las réplicas

        # Entre A y C, gana el de menor S (aquí C, con S_par por debajo del de A y por encima de AB y B).
        val = _con_metricas(S.tablas_metricas("ganador_claro")["validacion"], {("C", "T", "S"): 1.15,
                                                                               ("C", "HR", "S"): 7.7})
        amb = _ambientales(T_Td={"validacion": val})
        self.assertEqual(decision.decidir_combinacion("ambiental", "T_Td", amb["T_Td"], umbrales=self.U).ganador, "AB")
        self.assertEqual(decision.ganador_restringido(amb, {"T_Td", "p"}, umbrales=self.U)["T_Td"], "C")
        # A y C fuera de E1 (A por CD y C por EX): el paso 4 entre A y C de E0, con «regla sin ganador».
        val = _con_metricas(S.tablas_metricas("ganador_claro")["validacion"], {("A", "T", "CD"): 0.45,
                                                                               ("C", "Td", "EX"): 1.5})
        amb = _ambientales(T_Td={"validacion": val})
        d = decision.decisiones_restringidas(amb, {"T_Td", "p"}, umbrales=self.U)["T_Td"]
        self.assertEqual((d.e1, d.ganador), ((), "A"))
        self.assertEqual(d.notas, ("regla sin ganador", "I restringido por TF de contaminantes"))

        with self.assertRaises(ValueError):                         # grupos_con_b_ab debe ser el de las entradas
            decision.ganador_restringido(self.amb, {"T_Td"}, umbrales=self.U)
        with self.assertRaises(ValueError):                         # rama 3 sin entradas
            d6 = S.tablas_m6("rama3")
            decision.ramas_m6(_condiciones(d6, self.U), d6["tf_contaminantes"], self.ganadores)
        with self.assertRaises(ValueError):                         # faltan grupos ambientales
            decision.ganador_restringido({"T_Td": self.amb["T_Td"]}, {"T_Td"}, umbrales=self.U)


# ---------------------------------------------------------------------------------------------------------------
# Registros
# ---------------------------------------------------------------------------------------------------------------
_HUELLAS = {"ERA5L/era5land_2024_01.nc": "a" * 64, "LOCAL/meteo_combinada/v1/validacion/puntajes.parquet":
            {"sha256": "b" * 64, "bytes": 1234}}


class PruebasDecision(unittest.TestCase):
    def setUp(self):
        self.U = _umbrales()

    def _decisiones(self):
        casos = (("ganador_claro",), ("uv",), ("p_sin_ex",), ("agudo_nivel",), ("tf2_no_evaluable",))
        salida = []
        for (caso,) in casos:
            d = S.tablas_metricas(caso)
            salida.append((d, decision.decidir_combinacion(d["uso"], d["grupo"], _entradas(d), umbrales=self.U)))
        return salida

    def test_decision_json_registro(self):
        """E0, E1, motivos, S, ΔS y su intervalo, red de TF2, notas y ganador; números de Python, orden fijo, huellas
        bajo «huellas» y sin vocabulario prohibido (D3, clase «métrica»)."""
        pares = self._decisiones()
        hip = {}
        for d, r in pares:
            hip[(d["uso"], d["grupo"])] = {r.ganador: {"T": tipos.Hiper(50.0, 150.0, 0.2),
                                                       "Td": tipos.Hiper(25.0, 50.0, 0.5)}}
        hip["cronico/T_Td"] = hip.pop(("cronico", "T_Td"))          # también «uso/grupo»
        registro = decision.decision_json([r for _, r in reversed(pares)], hip, _HUELLAS)
        json.dumps(registro, ensure_ascii=False, allow_nan=False, sort_keys=True)
        ceguera.vigilar_salida("decision.json", registro, clase="metrica")
        self.assertEqual(registro["esquema"], decision.ESQUEMA_DECISION)
        self.assertEqual([(x["uso"], x["grupo"]) for x in registro["decisiones"]],
                         [("ambiental", "T_Td"), ("ambiental", "u_v"), ("ambiental", "p"), ("agudo", "T_Td"),
                          ("cronico", "T_Td")])
        self.assertEqual(list(registro["huellas"]), sorted(_HUELLAS))
        por = {(x["uso"], x["grupo"]): x for x in registro["decisiones"]}
        for d, r in pares:
            with self.subTest(caso=d["caso"]):
                x = por[(d["uso"], d["grupo"])]
                self.assertEqual(set(x), {"uso", "grupo", "ganador", "e0", "e1", "motivos", "S", "delta_S",
                                          "ic_delta_S", "red_tf2", "notas", "hiperparametros"})
                self.assertEqual((x["ganador"], x["e0"], x["e1"]), (r.ganador, list(r.e0), list(r.e1)))
                self.assertEqual(x["S"], d["esperado"]["S"])
                self.assertEqual(x["delta_S"], {c: r.S[c] - r.S[r.ganador] for c in r.e0})
                for c in r.e0:                                      # D46: el ganador de cada réplica (MC-34)
                    self.assertEqual(tuple(x["ic_delta_S"][c]), _ic_d46(d["replicas"], _conjunto_a_mano(r), c, 95))
                self.assertGreaterEqual(x["ic_delta_S"][r.ganador][0], 0.0)
                self.assertEqual(x["notas"], list(d["esperado"]["notas"]))
                self.assertEqual(x["hiperparametros"][r.ganador]["T"], {"L_km": 50.0, "lam": 150.0, "kappa": 0.2})
        cro = por[("cronico", "T_Td")]
        self.assertEqual(cro["motivos"], {"B": ["TF2 no evaluable"], "AB": ["TF2 no evaluable"]})
        self.assertEqual(cro["red_tf2"], {"T": "ninguna"})
        self.assertEqual(por[("ambiental", "u_v")]["motivos"], {"B": ["EX"], "AB": ["CD"]})
        self.assertEqual(por[("ambiental", "u_v")]["red_tf2"], {"rapidez": "r2000_2025"})

        decisiones = [r for _, r in pares]
        malos = {
            "faltan hiperparámetros": (decisiones, {k: v for k, v in hip.items() if k != "cronico/T_Td"}, _HUELLAS),
            "hiperparámetros de más": (decisiones[:1], hip, _HUELLAS),
            "hiperparámetro no finito": (decisiones[:1], {("ambiental", "T_Td"): {"L_km": float("nan")}}, _HUELLAS),
            "ruta absoluta": (decisiones[:1], {("ambiental", "T_Td"): {}}, {"/" + "Users/x/a.nc": "a" * 64}),
            "huella que no es sha256": (decisiones[:1], {("ambiental", "T_Td"): {}}, {"ERA5L/a.nc": "abc"}),
            "decisión repetida": (decisiones[:1] * 2, {("ambiental", "T_Td"): {}}, {}),
        }
        for nombre, args in malos.items():
            with self.subTest(caso=nombre), self.assertRaises((ValueError, TypeError)):
                decision.decision_json(*args)
        roto = dataclasses.replace(decisiones[0], ganador="C_est")
        with self.assertRaises(ValueError):
            decision.decision_json([roto], {("ambiental", "T_Td"): {}}, {})

    def test_decision_m6_json(self):
        """``decision_m6.json`` (D14, clase «resumen»): quién supera, ramas, condiciones y variante por contaminante,
        la de O3, el ganador restringido y las notas."""
        amb = _ambientales()
        ganadores = {g: decision.decidir_combinacion("ambiental", g, e, umbrales=self.U).ganador for g, e in amb.items()}
        d6 = S.tablas_m6("rama3")
        r = decision.ramas_m6(_condiciones(d6, self.U), d6["tf_contaminantes"], ganadores, entradas_ambientales=amb,
                              umbrales=self.U)
        registro = decision.decision_m6_json(r, _HUELLAS)
        json.dumps(registro, ensure_ascii=False, allow_nan=False)
        ceguera.vigilar_salida("m6/decision_m6.json", registro, clase="resumen")
        self.assertEqual(registro["esquema"], decision.ESQUEMA_DECISION_M6)
        self.assertEqual(registro["rama"], {"pm25": 3, "no2": 1})
        self.assertEqual(registro["supera"], {"pm25": None, "no2": "I"})
        self.assertEqual(registro["variante"], {"pm25": "I", "no2": "I", "O3": "I"})
        self.assertEqual(registro["ganador_restringido"], {"T_Td": "A", "u_v": "A", "p": "A"})
        self.assertEqual(registro["notas"], ["I restringido por TF de contaminantes"])
        self.assertEqual(set(registro["condiciones"]["no2"]), {"I_frente_a_D", "D_frente_a_I"})
        self.assertEqual(registro["condiciones"]["no2"]["I_frente_a_D"], [True] * 7)
        r1 = decision.ramas_m6(_condiciones(S.tablas_m6("rama1_D"), self.U), S.tablas_m6("rama1_D")["tf_contaminantes"],
                               ganadores)
        self.assertIsNone(decision.decision_m6_json(r1, {})["ganador_restringido"])
        for roto in (dataclasses.replace(r, ganador_restringido=None),
                     dataclasses.replace(r1, ganador_restringido={"T_Td": "A", "u_v": "A", "p": "A"}),
                     dataclasses.replace(r, ganador_restringido={"T_Td": "B", "u_v": "A", "p": "A"})):
            with self.assertRaises(ValueError):
                decision.decision_m6_json(roto, {})


if __name__ == "__main__":
    unittest.main()
