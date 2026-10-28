"""Pruebas de validacion.py (§5): S7 (soporte) y S12 (CD), las métricas de §5.2-§5.8, los pesos y S de §5.3, el
remuestreo de §5.4, los estratos y la réplica con N de §5.5 y la red SINCA de §5.6.

Dueño: I14 (ola 3). Las que llevan «sNN» son la prueba NN de §9 del texto. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos: series y tablas hechas aquí o por ``sintetico`` (en memoria o en
``tempfile.TemporaryDirectory``); ninguna prueba abre DMC, la meteorología SINCA real, NASADEM real, ERA5L real ni
GHS-POP real. Los umbrales son los anclados en M0 (``umbrales.cargar_m0``: el texto y el JSON de APH, con sus huellas).
``decision`` (ola 2) se usa tal cual para comprobar que lo que sale de aquí entra a la regla (acuerdo A11); ``entorno``
se importa para fijar la base de zonas en la del paquete tzdata (VAL-3).

Mutaciones (en memoria, sin tocar el disco; para la revisión). Primera entrega: 40 cambios de la regla en
``validacion``, 38 detectados. Allí se dio por equivalente «≥» en vez de «>» en el aviso SINCA, con un motivo falso: el
borde sí se arma en coma flotante (1 + 15/100 es 1,15 exacto en float64, y 1,15 · 2 también), y ahora lo fija
``test_aviso_sinca_borde_exacto``. La revisión halló 14 más sin detectar (M01-M08, M12, M15, M16, M22, M23 y M26); todas
se detectan ahora. M22 (la réplica con N sin quitar las excluidas) era equivalente con la entrada esperada, porque
``particiones.bloques_remuestreo`` deja fuera las excluidas (PAR-1); ahora ``remuestreo`` rechaza el bloque de una
excluida y la réplica con N lo deja fuera, y ``test_replica_con_n_sortea_los_bloques_de_todas_las_n`` la ve. Las 17
mutaciones de lo nuevo de esta ronda (macrozonas, E0, bloques de N y descriptivos) también se detectan. Sobrevive una,
equivalente: el orden de las operaciones de S_par (multiplicar por ½ es exacto en binario).
"""
import sys

sys.dont_write_bytecode = True

import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zoneinfo  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import entorno  # noqa: E402,F401  (fija la base de zonas: VAL-3)
from meteo_combinada import ceguera, constantes, decision, numerico, tipos, umbrales  # noqa: E402
from meteo_combinada import sinca_meteo as SM, sintetico as S  # noqa: E402
from meteo_combinada import validacion as V  # noqa: E402
from meteo_combinada.tipos import Grupo, Uso  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
_U = None
_NAN = float("nan")
_ZONA = tipos.ZONA_CIVIL


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


def _h_de(fecha: str) -> int:
    """Horas desde 2000-01-01T00:00Z de una fecha y hora UTC."""
    return int((pd.Timestamp(fecha) - pd.Timestamp("2000-01-01")) / pd.Timedelta(hours=1))


# ---------------------------------------------------------------------------------------------------------------
# Estaciones y evaluaciones sintéticas
# ---------------------------------------------------------------------------------------------------------------
_PLANTILLA = tipos.InfoEstacion(
    codigo="330001", nombre="Estación sintética", conjunto="V", macrozona="centro", grupo="G330001", omm=None,
    tipo=None, propietario=None, lat_txt="-33.40", lon_txt="-70.60", alt_txt="500", lat=-33.4, lon=-70.6, z_cat=500.0,
    rho_km=0.1, k3_pasa=True, z_s=500.0, z_s_fuente="catalogo", celda=1, utm_e=0.0, utm_n=0.0, bloque="4_83",
    pix0=0, pix1=1, pix2=2, pix3=3, w0=0.25, w1=0.25, w2=0.25, w3=0.25, respaldo_16km=False, sin_fondo=False,
    excluida=False, motivo=None)


def _info(codigo: str, **cambios) -> tipos.InfoEstacion:
    return dataclasses.replace(_PLANTILLA, codigo=codigo, grupo="G" + codigo, **cambios)


def _red(n_centro=12, n_sur=3, n_sin=1, *, conjunto=None) -> dict[str, tipos.InfoEstacion]:
    """Estaciones: n_centro en «centro», n_sur en «sur» y n_sin sin macrozona; un bloque de P2 por estación de cada
    macrozona (las del sur comparten los de las primeras del centro)."""
    infos = {}
    k = 0
    for macro, n in (("centro", n_centro), ("sur", n_sur), (None, n_sin)):
        for i in range(n):
            k += 1
            codigo = f"{330000 + k:06d}"
            infos[codigo] = _info(codigo, macrozona=macro, bloque=f"{4 + i}_{83 if macro else 70}",
                                  z_s=float(300 + 400 * i), conjunto=(conjunto or {}).get(codigo, "V"),
                                  lat=-33.0 - 0.1 * k, lon=-70.5 - 0.05 * k)
    return infos


_MULT = {"A": 1.2, "B": 1.1, "AB": 1.0, "C": 1.15, "C_est": 1.15}
_RUIDO = 0.03          # ruido relativo por evaluación y candidato: así S_par cambia de una réplica a otra


def _evaluaciones(uso, grupo, infos, *, semilla=0, mult=None, frac=None, mult_de=None) -> pd.DataFrame:
    """ESQUEMA_EVALUACIONES de un (uso, grupo): por estación, P1 y P2, cada variable de METRICAS y cada candidato.
    Las métricas de S, nivel y anomalía valen base·mult del candidato·(1 ± 3 %), con una base distinta en P1 y en P2;
    CD y EX son iguales en todos (las compuertas pasan). ``frac(codigo, particion, candidato)`` da la fracción sin
    soporte (0,1 por omisión)."""
    uso, grupo = Uso(uso), Grupo(grupo)
    rng = np.random.default_rng(semilla)
    filas = []
    for codigo in sorted(infos):
        info = infos[codigo]
        if info.excluida:
            continue
        m_est = (mult_de or {}).get(codigo, mult or _MULT)
        for particion, pliegue in (("P1", f"P1-{int(codigo) % 10}"), ("P2", f"P2-{info.bloque}")):
            base = {c: float(rng.uniform(0.5, 1.5)) for c in V.COLUMNAS_METRICA}
            for v, metricas in V.METRICAS[(uso, grupo)].items():
                cols = set(metricas.values())
                for cand in V.CANDIDATOS_USO[uso]:
                    m = dict.fromkeys(V.COLUMNAS_METRICA, _NAN)
                    for c in cols:
                        m[c] = (base[c] if c in ("cd", "ex")
                                else base[c] * m_est[cand] * float(rng.uniform(1 - _RUIDO, 1 + _RUIDO)))
                    if "mse_h" in cols:
                        m["mae_h"], m["sesgo_h"] = math.sqrt(m["mse_h"]), 0.1
                    filas.append({"codigo": codigo, "particion": particion, "pliegue": pliegue, "candidato": cand,
                                  "uso": uso.value, "variable": v, "n_horas": 5000, "n_dias": 1000, "n_anios": 5,
                                  **m, "frac_sin_soporte": frac(codigo, particion, cand) if frac else 0.1})
    esquema = tipos.ESQUEMA_EVALUACIONES
    return pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))


def _bandas(evaluaciones, *, semilla=1, fija=None) -> dict:
    rng = np.random.default_rng(semilla)
    salida = {}
    for c, p in sorted(set(zip(evaluaciones["codigo"], evaluaciones["particion"]))):
        for k in V.CLAVES_HORAS:
            salida[(c, p, k)] = int(fija if fija is not None else rng.integers(0, 4))
    return salida


_PI = (0.4, 0.3, 0.2, 0.1)


def _pis(pi=_PI) -> dict:
    return {k: pi for k in V.CLAVES_HORAS}


# Casos de tablas_metricas con la TF de cada (uso, grupo), sin TF fallidas.
_TF_DE = {(Uso.AMBIENTAL, Grupo.T_TD): "ganador_claro", (Uso.AMBIENTAL, Grupo.U_V): "uv",
          (Uso.AMBIENTAL, Grupo.P): "p_sin_ex", (Uso.AGUDO, Grupo.T_TD): "agudo_nivel",
          (Uso.CRONICO, Grupo.T_TD): "falla_mz_cronica"}


def _fila_pub(tabla, *, variable, candidato, particion, estrato="nacional", valor=""):
    m = ((tabla.variable == variable) & (tabla.candidato == candidato) & (tabla.particion == particion)
         & (tabla.estrato == estrato) & (tabla.valor_estrato == valor)).to_numpy(dtype=bool)
    assert m.sum() == 1, (variable, candidato, particion, estrato, valor, int(m.sum()))
    return tabla[m].iloc[0]


# ---------------------------------------------------------------------------------------------------------------
# S7: la regla de soporte bloquea un estrato
# ---------------------------------------------------------------------------------------------------------------
class PruebasS7Validacion(unittest.TestCase):
    def setUp(self):
        self.U = _umbrales()

    def test_s07_soporte_bloquea_un_estrato(self):
        """§0.4.4 y §5.5: un estrato sin soporte en > 50 % no se publica (sólo su fracción); los demás, sí."""
        d = S.tablas_metricas("soporte")
        self.assertEqual(self.U.frac("SOPORTE_PCT"), d["esperado"]["umbral_sin_soporte"])
        ev = d["evaluaciones"]
        infos = {c: _info(c, macrozona=x["macrozona"], conjunto=x["conjunto"]) for c, x in d["infos"].items()}
        banda = _bandas(ev, fija=0)
        kw = dict(uso="ambiental", grupo="T_Td", banda=banda, pi=_pis((1.0, 0.0, 0.0, 0.0)))
        tabla = V.estratos(ev, infos, self.U, **kw)
        soporte = V.fracciones_sin_soporte(ev, infos, self.U, **kw)
        for estrato, valor in d["esperado"]["no_publicables"]:
            filas = tabla[(tabla.estrato == estrato) & (tabla.valor_estrato == valor) & (tabla.variable == "T")]
            self.assertEqual(len(filas), 4 * 3)
            self.assertFalse(filas.publicable.any())
            self.assertTrue(filas[list(V.COLUMNAS_PUB)].isna().all().all(), "un estrato sin soporte no publica S")
            sop = soporte[(soporte.estrato == estrato) & (soporte.valor_estrato == valor) & (soporte.variable == "T")
                          & (soporte.particion == "agregado")]
            self.assertEqual(dict(zip(sop.candidato, sop.frac_sin_soporte.round(12))),
                             {"A": 0.8, "B": 0.8, "AB": 0.8, "C": 0.1})
        for estrato, valor in d["esperado"]["publicables"]:
            filas = tabla[(tabla.estrato == estrato) & (tabla.valor_estrato == valor) & (tabla.variable == "T")]
            self.assertTrue(filas.publicable.all())
            self.assertTrue(np.isfinite(filas["S"]).all())
            self.assertFalse(((soporte.estrato == estrato) & (soporte.valor_estrato == valor)
                              & (soporte.variable == "T")).any(), "de un estrato publicado no sale la fracción")
        nacional = tabla[(tabla.estrato == "nacional") & (tabla.variable == "T")]
        self.assertTrue(nacional.publicable.all() and np.isfinite(nacional["S"]).all())

    def test_s07_el_estrato_se_evalua_por_particion_mc61(self):
        """MC-61 (TIP-15): publicable por partición; sin soporte en P2 el estrato no se publica en ninguna; el nacional
        siempre se publica; la compuerta MZ queda «no_publicable» en ``decision``."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)

        def frac(codigo, particion, cand):
            return {"P1": 0.2, "P2": 0.7}[particion] if cand == "A" else 0.1

        ev = _evaluaciones("ambiental", "T_Td", infos, frac=frac)
        kw = dict(uso="ambiental", grupo="T_Td", banda=_bandas(ev), pi=_pis())
        tabla = V.estratos(ev, infos, self.U, **kw)
        for v in ("T", "HR"):
            for cand in V.CANDIDATOS_USO[Uso.AMBIENTAL]:
                pub = {p: bool(_fila_pub(tabla, variable=v, candidato=cand, particion=p, estrato="macrozona",
                                         valor="centro").publicable) for p in V.PARTICIONES}
                self.assertEqual(pub, {"P1": True, "P2": False, "agregado": True})     # 0,2, 0,7 y 0,45
                for p in V.PARTICIONES:
                    fila = _fila_pub(tabla, variable=v, candidato=cand, particion=p, estrato="macrozona",
                                     valor="centro")
                    self.assertTrue(math.isnan(fila.S))
                    self.assertEqual((fila.n_estaciones, fila.n_evaluaciones), (12, 24 if p == "agregado" else 12))
                nac = _fila_pub(tabla, variable=v, candidato=cand, particion="P2")
                self.assertTrue(nac.publicable and math.isfinite(nac.S), "MC-61: el nacional siempre se publica")
        d = S.tablas_metricas("ganador_claro")
        ent = tipos.EntradasDecision(Uso.AMBIENTAL, Grupo.T_TD, tabla, d["tf"],
                                     V.remuestreo(ev, {c: i.bloque for c, i in infos.items()}, self.U, infos=infos,
                                                  e0=("A", "B", "AB", "C"), **kw), {})
        mz = decision.compuertas(Uso.AMBIENTAL, Grupo.T_TD, ent, self.U)
        mz = mz[(mz.compuerta == "MZ") & (mz.ambito == "centro")]
        self.assertEqual(set(mz.motivo), {"no_publicable"})
        self.assertFalse(mz.aplica.any())

    def test_s07_salidas_pasan_la_guarda(self):
        """S7 (MC-02, D3): lo que publica este módulo pasa la guarda de su clase: ningún rótulo del fondo ni del
        residuo, ni «sin_dmc», ni «R_»."""
        infos = _red()
        ev = _evaluaciones("ambiental", "u_v", infos)
        kw = dict(uso="ambiental", grupo="u_v", banda=_bandas(ev), pi=_pis())
        salidas = {"validacion/puntajes.parquet": V.estratos(ev, infos, self.U, **kw),
                   "validacion/soporte.parquet": V.fracciones_sin_soporte(ev, infos, self.U, **kw),
                   "validacion/bandas.parquet": V.tabla_bandas(ev, infos, self.U, uso="ambiental", grupo="u_v",
                                                              banda=kw["banda"], pi_pob=_pis(), pi_mon=_pis()),
                   "validacion/evaluaciones.parquet": ev}
        filas = [f for c, p, cand, v in zip(ev.codigo, ev.particion, ev.candidato, ev.variable)
                 for f in V.filas_descriptivas({"descriptivos": dict.fromkeys(V.descriptivos_de("ambiental", v), 0.5)},
                                               codigo=c, particion=p, candidato=cand, uso="ambiental", variable=v)]
        salidas["validacion/descriptivos.parquet"] = V.tabla_descriptivos(ev, filas, infos, self.U, **kw)
        self.assertGreater(len(salidas["validacion/descriptivos.parquet"]), 0)
        sinca = _caso_sinca(self.U, {"A": 0.3, "B": 0.2, "AB": 0.1, "C": 0.4}, ganador="AB")
        salidas["validacion/sinca.parquet"] = sinca["metricas"]
        salidas["validacion/sinca_aviso.json"] = {"aviso": sinca["aviso"], "declaraciones": sinca["declaraciones"]}
        for nombre, contenido in salidas.items():
            with self.subTest(nombre=nombre):
                clase = ceguera.clase_de_ruta(nombre) or "metrica"
                ceguera.vigilar_salida(nombre, contenido, clase=clase)
                self.assertIn(clase, ceguera.CLASES_CON_VOCABULARIO)
        with self.assertRaises(ceguera.SalidaProhibida):
            ceguera.vigilar_salida("validacion/puntajes.parquet", salidas["validacion/puntajes.parquet"].assign(
                candidato="fondo"), clase="metrica")


# ---------------------------------------------------------------------------------------------------------------
# S12: un error de ±1 h del reloj aparece en CD
# ---------------------------------------------------------------------------------------------------------------
def _verdad_t(h) -> np.ndarray:
    """T con un ciclo diario marcado (6 K, máximo a las 19 UTC) y un ciclo anual lento."""
    h = np.asarray(h, dtype=np.float64)
    return 15.0 + 6.0 * np.cos(2 * np.pi * (h - 19) / 24) + 4.0 * np.cos(2 * np.pi * h / (24 * 365.25))


class PruebasS12Validacion(unittest.TestCase):
    def setUp(self):
        self.U = _umbrales()

    def test_s12_error_de_una_hora_aparece_en_cd(self):
        """§9, S12: con el reloj correcto CD = 0 (un sesgo constante no es ciclo); con etiquetas corridas ±1 h, CD es
        el de un ciclo de 6 K desfasado una hora, A·√2·sen(π/24) ≈ 1,11 K, muy sobre el sumando de la compuerta."""
        h = np.arange(_h_de("2019-01-01"), _h_de("2021-01-01"), dtype=np.int64)
        producto = _verdad_t(h)
        bien = V.ciclo_diario(h, producto, _verdad_t(h) - 0.3, self.U)
        self.assertLess(bien, 1e-9)
        esperado = 6.0 * math.sqrt(2) * math.sin(math.pi / 24)
        for corrimiento in (-1, 1):
            with self.subTest(corrimiento=corrimiento):
                obs = _verdad_t(h + corrimiento)            # la observación de u es la de u ± 1 (reloj errado)
                cd = V.ciclo_diario(h, producto, obs, self.U)
                self.assertAlmostEqual(cd, esperado, delta=esperado * 1e-3)
                self.assertGreater(cd, 10 * self.U.a("CD_T"))
                m = V.evaluacion(h, producto, obs, uso="ambiental", variable="T", umbrales=self.U)
                self.assertEqual(m["cd"], cd)

    def test_cd_resta_la_media_de_cada_mes(self):
        """§5.2 («esa diferencia menos su media del mes, sobre (m, h)»; VAL-6): un sesgo constante dentro de cada mes
        UTC y distinto entre meses no es ciclo (CD = 0); un ciclo diario de amplitud a_m distinta en cada mes da
        CD = √(Σ_m a_m² / 24), la media de a_m² cos² sobre las 12 × 24 celdas."""
        h = np.arange(_h_de("2019-01-01"), _h_de("2020-01-01"), dtype=np.int64)
        mes = (np.datetime64("2000-01-01T00", "h") + h).astype("datetime64[M]").astype(np.int64) % 12
        obs = _verdad_t(h)
        sesgo_mes = np.linspace(-1.0, 1.2, 12)
        self.assertLess(V.ciclo_diario(h, obs + sesgo_mes[mes], obs, self.U), 1e-9)
        amplitud = 0.2 + 0.1 * np.arange(12)
        ciclo = amplitud[mes] * np.cos(2 * np.pi * (h - 19) / 24)
        cd = V.ciclo_diario(h, obs + sesgo_mes[mes] + ciclo, obs, self.U)
        self.assertAlmostEqual(cd, math.sqrt(float(np.sum(amplitud ** 2)) / 24), places=12)


# ---------------------------------------------------------------------------------------------------------------
# §5.2, §5.8: métricas de una evaluación
# ---------------------------------------------------------------------------------------------------------------
class PruebasValidacion(unittest.TestCase):
    def setUp(self):
        self.U = _umbrales()

    # --- §5.2, horarias -----------------------------------------------------------------------------------------
    def test_metricas_horarias_viento_vectorial(self):
        """RMSE vectorial y sesgo de la rapidez; sólo las horas emparejadas (VAL-2)."""
        pred = np.array([[1.0, 0.0], [0.0, 2.0], [3.0, 4.0], [1.0, 1.0]])
        obs = np.array([[0.0, 0.0], [0.0, 1.0], [0.0, 4.0], [np.nan, 1.0]])
        m = V.metricas_horarias(pred, obs, "uv")
        self.assertEqual(m["n_horas"], 3)
        self.assertAlmostEqual(m["mse"], 11 / 3, places=15)
        self.assertAlmostEqual(m["rmse"], math.sqrt(11 / 3), places=15)
        self.assertAlmostEqual(m["mae"], 5 / 3, places=15)
        self.assertAlmostEqual(m["sesgo"], 1.0, places=15)
        self.assertEqual(V.metricas_horarias((pred[:, 0], pred[:, 1]), (obs[:, 0], obs[:, 1]), "uv"), m)
        with self.assertRaises(ValueError):
            V.metricas_horarias(pred[:, 0], obs[:, 0], "uv")
        with self.assertRaises(ValueError):
            V.metricas_horarias(pred[:, 0], obs[:, 0], "temp_media")

    def test_metricas_horarias_escalares(self):
        m = V.metricas_horarias([1.0, 2.0, 4.0, np.nan], [0.0, 3.0, 1.0, 2.0], "T")
        self.assertEqual(m["n_horas"], 3)
        self.assertAlmostEqual(m["mse"], (1 + 1 + 9) / 3, places=15)
        self.assertAlmostEqual(m["mae"], 5 / 3, places=15)
        self.assertAlmostEqual(m["sesgo"], 1.0, places=15)
        self.assertEqual(V.metricas_horarias([np.nan], [1.0], "p")["n_horas"], 0)

    def test_dia_valido_8h_y_hueco_4h(self):
        """§5.2 y MC-27: ≥ 8 horas válidas y hueco circular ≤ 4 h, sobre la duración del día civil (23, 24 o 25 h)."""
        rango = np.arange(_h_de("2024-03-01"), _h_de("2024-10-01"), dtype=np.int64)
        dia, pos, dur = V.dia_civil(rango, _ZONA)
        primera = {int(d): int(rango[np.flatnonzero(dia == d)[0]]) for d in np.unique(dia)}

        def d2000(fecha):
            return int((pd.Timestamp(fecha) - pd.Timestamp("2000-01-01")).days)

        casos = {"2024-03-10": ((0, 3, 6, 9, 12, 15, 18, 21), True), "2024-03-11": ((0, 1, 2, 3, 4, 5, 6, 7), False),
                 "2024-03-12": ((0, 3, 6, 9, 12, 15, 18), False), "2024-03-13": ((0, 2, 4, 8, 12, 16, 20, 22), True),
                 "2024-03-14": ((0, 2, 4, 9, 12, 16, 20, 22), False),
                 "2024-04-06": ((0, 3, 6, 9, 12, 15, 18, 21, 24), True),       # 25 h: hueco de vuelta 1
                 "2024-09-08": ((0, 3, 6, 9, 12, 15, 18, 21), True)}           # 23 h: hueco de vuelta 2
        h = np.array([primera[d2000(f)] + p for f, (ps, _) in casos.items() for p in ps], dtype=np.int64)
        tabla = V.dias_validos(h, np.ones(h.size, dtype=bool), _ZONA, self.U).set_index("dia")
        self.assertEqual(int(tabla.loc[d2000("2024-04-06"), "duracion"]), 25)
        self.assertEqual(int(tabla.loc[d2000("2024-09-08"), "duracion"]), 23)
        self.assertEqual(int(tabla.loc[d2000("2024-03-10"), "duracion"]), 24)
        for f, (ps, valido) in casos.items():
            with self.subTest(dia=f):
                fila = tabla.loc[d2000(f)]
                self.assertEqual(bool(fila.valido), valido)
                self.assertEqual(int(fila.hueco), numerico.hueco_circular_max(ps, int(fila.duracion)))
        # paridad con numerico.hueco_circular_max en días al azar
        rng = np.random.default_rng(7)
        elegidas = rango[rng.random(rango.size) < 0.35]
        t = V.dias_validos(elegidas, np.ones(elegidas.size, dtype=bool), _ZONA, self.U)
        d_el, p_el, dur_el = V.dia_civil(elegidas, _ZONA)
        for fila in t.itertuples():
            m = d_el == fila.dia
            self.assertEqual(fila.hueco, numerico.hueco_circular_max(p_el[m], int(dur_el[m][0])))
            self.assertEqual(fila.n_horas, int(m.sum()))
        with self.assertRaises(ValueError):
            V.dias_validos(np.array([1, 1]), np.array([True, True]), _ZONA, self.U)

    def test_zona_exige_la_base_de_tzdata(self):
        """VAL-3: con otra base de zonas en TZPATH, el día civil no se calcula."""
        try:
            zoneinfo.reset_tzpath()
            if not zoneinfo.TZPATH:
                self.skipTest("el intérprete no trae una TZPATH del sistema")
            with self.assertRaises(RuntimeError):
                V._zona_iana(_ZONA)
        finally:
            zoneinfo.reset_tzpath(to=[])
            zoneinfo.ZoneInfo.clear_cache()
        self.assertEqual(zoneinfo.TZPATH, ())

    def test_medias_diarias_en_las_horas_emparejadas(self):
        """VAL-3: la media del día del producto en las mismas horas que la observación."""
        h0 = _h_de("2023-06-01T04")                     # medianoche civil (UTC−4 en invierno)
        h = np.arange(h0, h0 + 24, dtype=np.int64)
        obs = np.where(np.arange(24) % 2 == 0, 10.0, np.nan)
        pred = np.arange(24, dtype=np.float64)
        d = V.medias_diarias(h, pred, obs, _ZONA, self.U)
        self.assertEqual(len(d), 1)
        self.assertEqual(d.loc[0, "pred_media"], float(np.mean(np.arange(0, 24, 2))))
        self.assertEqual((d.loc[0, "pred_max"], d.loc[0, "pred_min"]), (22.0, 0.0))
        self.assertEqual((int(d.loc[0, "anio"]), int(d.loc[0, "mes"]), int(d.loc[0, "n_horas"])), (2023, 6, 12))

    def test_dia_y_evaluabilidad_en_las_horas_emparejadas(self):
        """VAL-2 y VAL-3: el día válido y la evaluabilidad se miden en las horas emparejadas (observación válida y
        producto finito), no en las observadas. Un día con 8 horas observadas, una sin producto, no es válido aunque las
        7 emparejadas dejen un hueco ≤ 4 h; 2.000 horas observadas con 1.999 emparejadas no son evaluables."""
        h0 = _h_de("2023-06-01T04")                     # medianoche civil (UTC−4 en invierno)
        emparejadas = (0, 4, 8, 12, 15, 18, 21)         # sólo falla el número de horas
        self.assertEqual(len(emparejadas), self.U.a("DIA_MIN_H") - 1)
        self.assertLessEqual(numerico.hueco_circular_max(emparejadas, 24), self.U.a("DIA_HUECO_H"))
        h = h0 + np.array(sorted((*emparejadas, 2)), dtype=np.int64)
        obs = np.full(h.size, 10.0)
        pred = np.where(h == h0 + 2, np.nan, 11.0)
        self.assertEqual(len(V.medias_diarias(h, pred, obs, _ZONA, self.U)), 0)
        self.assertEqual(len(V.medias_diarias(h, np.full(h.size, 11.0), obs, _ZONA, self.U)), 1)
        n = self.U.a("MIN_HORAS")
        h = np.arange(_h_de("2015-01-01T04"), _h_de("2015-01-01T04") + n, dtype=np.int64)
        obs = _verdad_t(h)
        pred = obs + 0.5
        self.assertIsNotNone(V.evaluacion(h, pred, obs, uso="ambiental", variable="T", umbrales=self.U))
        pred[n // 2] = np.nan
        self.assertIsNone(V.evaluacion(h, pred, obs, uso="ambiental", variable="T", umbrales=self.U))

    def test_bordes_de_los_minimos_del_anexo_a(self):
        """Anexo A («Mínimos: 2.000 h; …; estrato agudo con ≥ 10 días; año con ≥ 300 días; ≥ 3 años») y §5.3 (π con las
        estaciones de ≥ 2.000 horas): cada mínimo, en su valor exacto, entra; uno menos, no."""
        # evaluable con MIN_HORAS horas emparejadas exactas (VAL-2)
        n = self.U.a("MIN_HORAS")
        h = np.arange(_h_de("2015-01-01T04"), _h_de("2015-01-01T04") + n, dtype=np.int64)
        obs = _verdad_t(h)
        m = V.evaluacion(h, obs + 0.5, obs, uso="ambiental", variable="T", umbrales=self.U)
        self.assertEqual(m["n_horas"], n)
        self.assertIsNone(V.evaluacion(h[1:], obs[1:] + 0.5, obs[1:], uso="ambiental", variable="T", umbrales=self.U))
        # estrato agudo con AGUDO_MIN_DIAS días exactos (VAL-4)
        k = self.U.a("AGUDO_MIN_DIAS")
        rng = np.random.default_rng(4)
        o = rng.normal(15, 3, 2 * k - 1)
        p = o + rng.normal(0, 0.5, o.size)
        diario = pd.DataFrame({"anio": 2020, "mes": [1] * k + [2] * (k - 1), "pred_media": p, "obs_media": o})
        e = slice(0, k)
        esperado = float(np.mean(((p[e] - p[e].mean()) - (o[e] - o[e].mean())) ** 2))
        self.assertAlmostEqual(V.desviacion_estrato(diario, self.U), esperado, places=14)
        self.assertAlmostEqual(V.desviacion_estrato(diario.iloc[:k], self.U), esperado, places=14)
        self.assertTrue(math.isnan(V.desviacion_estrato(diario.iloc[1:k], self.U)))
        # año válido con ANIO_MIN_DIAS días exactos (VAL-5)
        k = self.U.a("ANIO_MIN_DIAS")
        diario = pd.DataFrame({"anio": [2020] * k + [2021] * (k - 1), "mes": 1, "pred_media": 1.25,
                               "obs_media": 1.0})
        self.assertEqual(V.anios_validos(diario, self.U), {2020: 0.25})
        # nivel neto con MIN_ANIOS años exactos (VAL-5)
        k = self.U.a("MIN_ANIOS")
        infos = {c: _info(c) for c in ("330001", "330002", "330003")}
        anios = range(2010, 2010 + k)
        anuales = {}
        filas = []
        for i, c in enumerate(infos):
            for cand in V.CANDIDATOS_USO[Uso.CRONICO]:
                anuales[(c, "P1", cand)] = {y: 0.1 * (i + 1) + 0.01 * (y - 2010) for y in anios[: k - (i == 2)]}
                filas.append(V.fila_evaluacion(
                    {"n_horas": 5000, "n_dias": 2000, "n_anios": len(anuales[(c, "P1", cand)]),
                     **dict.fromkeys(V.COLUMNAS_METRICA, _NAN)},
                    codigo=c, particion="P1", pliegue="P1-1", candidato=cand, uso="cronico", variable="T",
                    frac_sin_soporte=_NAN if cand == "C_est" else 0.1))
        out = V.completar_cronico(V.tabla_evaluaciones(filas), anuales, infos, self.U).set_index(["codigo",
                                                                                                    "candidato"])
        for cand in V.CANDIDATOS_USO[Uso.CRONICO]:
            media = {y: (anuales[("330001", "P1", cand)][y] + anuales[("330002", "P1", cand)][y]) / 2 for y in anios}
            for c in ("330001", "330002"):
                self.assertAlmostEqual(out.loc[(c, cand), "mse_anual_neto"], float(np.mean(
                    [(anuales[(c, "P1", cand)][y] - media[y]) ** 2 for y in anios])), places=14)
            self.assertTrue(math.isnan(out.loc[("330003", cand), "mse_anual_neto"]))
        # π con las estaciones de MIN_HORAS horas exactas (VAL-9)
        n = self.U.a("MIN_HORAS")
        est = pd.DataFrame({"codigo": ["330001", "330002"], "lat": [-33.0, -34.0], "lon": [-70.0, -70.0]})
        celdas = pd.DataFrame([{"anio": y, "lat": la, "lon": -70.0, "w_ghs": 1.0} for y in range(2000, 2026)
                               for la in (-33.0, -34.0)])
        for horas, esperado in ((n, [1.0, 0.0, 0.0, 0.0]), (n - 1, [0.5, 0.0, 0.0, 0.5])):
            with self.subTest(horas=horas):
                por_anio = {y: est.assign(horas=[n, horas]) for y in range(2000, 2026)}
                self.assertEqual(list(V.pi_poblacion(celdas, por_anio, "T", self.U).values()), esperado)

    def test_desviacion_estrato_y_nivel(self):
        """§5.2, agudo (VAL-4): estratos de año × mes con ≥ 10 días; el nivel es el MSE de las medias diarias."""
        rng = np.random.default_rng(3)
        obs = rng.normal(15, 3, 21)
        pred = obs + np.r_[np.full(12, 0.7), np.full(9, -0.4)] + rng.normal(0, 0.2, 21)
        diario = pd.DataFrame({"anio": [2020] * 21, "mes": [1] * 12 + [2] * 9, "pred_media": pred, "obs_media": obs})
        e = slice(0, 12)
        dp, do = pred[e] - pred[e].mean(), obs[e] - obs[e].mean()
        self.assertAlmostEqual(V.desviacion_estrato(diario, self.U), float(np.mean((dp - do) ** 2)), places=14)
        self.assertAlmostEqual(V.nivel_diario(diario), float(np.mean((pred - obs) ** 2)), places=14)
        self.assertTrue(math.isnan(V.desviacion_estrato(diario.iloc[12:], self.U)))

    def test_anual_neto_y_anomalia(self):
        """§5.2, crónico (VAL-5): error neto de macrozona × año y anomalía interanual 2010-2023 con ≥ 5 años."""
        eps = {2009: 0.5, 2010: 0.2, 2011: 0.4, 2012: 0.1, 2013: 0.3, 2014: 0.6}
        medias = {y: 0.25 for y in eps}
        self.assertAlmostEqual(V.anual_neto(eps, medias), float(np.mean([(e - 0.25) ** 2 for e in eps.values()])),
                               places=15)
        with self.assertRaises(ValueError):
            V.anual_neto(eps, {2010: 0.0})
        a = V.anomalias(eps, self.U)
        dentro = [eps[y] for y in range(2010, 2015)]
        self.assertEqual(sorted(a), list(range(2010, 2015)))
        self.assertAlmostEqual(a[2011], 0.4 - float(np.mean(dentro)), places=15)
        m_a = {y: 0.01 for y in a}
        self.assertAlmostEqual(V.anomalia_interanual(eps, m_a, self.U),
                               float(np.mean([(a[y] - 0.01) ** 2 for y in a])), places=15)
        self.assertIsNone(V.anomalias({2010: 0.1, 2011: 0.2, 2012: 0.3, 2013: 0.4}, self.U))
        self.assertTrue(math.isnan(V.anomalia_interanual({2010: 0.1}, {}, self.U)))

    def test_completar_cronico_d22b_y_p1_p2_juntas(self):
        """D22 (b): sin macrozona no entra al nivel neto ni a la anomalía, y se cuenta; la media de macrozona × año va
        sobre las evaluaciones de P1 y P2 del mismo candidato (VAL-5, VAL-P1)."""
        infos = {"330001": _info("330001"), "330002": _info("330002"), "330003": _info("330003", macrozona=None),
                 "330004": _info("330004", macrozona="sur")}
        anios = range(2010, 2016)
        rng = np.random.default_rng(11)
        filas, anuales = [], {}
        for c in infos:
            for p, pl in (("P1", "P1-1"), ("P2", "P2-4_83")):
                for cand in V.CANDIDATOS_USO[Uso.CRONICO]:
                    eps = {y: float(rng.normal(0.2, 0.3)) for y in anios}
                    if c == "330004":
                        eps = {2010: 0.1, 2011: 0.2}                        # < 3 años: no evaluable para el neto
                    anuales[(c, p, cand)] = eps
                    filas.append(V.fila_evaluacion(
                        {"n_horas": 5000, "n_dias": 2000, "n_anios": len(eps),
                         **dict.fromkeys(V.COLUMNAS_METRICA, _NAN), "cd": 0.3},
                        codigo=c, particion=p, pliegue=pl, candidato=cand, uso="cronico", variable="T",
                        frac_sin_soporte=_NAN if cand == "C_est" else 0.1))
        ev = V.tabla_evaluaciones(filas)
        out = V.completar_cronico(ev, anuales, infos, self.U)
        self.assertEqual(out.attrs["declaraciones"]["cronico_sin_macrozona_estaciones"], 1)
        sin = out[out.codigo == "330003"]
        self.assertTrue(sin[["mse_anual_neto", "mse_anomalia"]].isna().all().all())
        self.assertTrue(out[out.codigo == "330004"]["mse_anual_neto"].isna().all())
        for cand in V.CANDIDATOS_USO[Uso.CRONICO]:
            claves = [(c, p, cand) for c in ("330001", "330002") for p in ("P1", "P2")]
            media = {y: float(np.mean([anuales[k][y] for k in claves])) for y in anios}
            for k in claves:
                fila = out[(out.codigo == k[0]) & (out.particion == k[1]) & (out.candidato == cand)].iloc[0]
                self.assertAlmostEqual(fila.mse_anual_neto, float(np.mean([(anuales[k][y] - media[y]) ** 2
                                                                           for y in anios])), places=14)
                self.assertTrue(math.isfinite(fila.mse_anomalia))
        with self.assertRaises(ValueError):
            V.completar_cronico(out, anuales, infos, self.U)

    def test_extremos_ambiental_agudo_y_rapidez(self):
        """§5.8 (VAL-7): (|b_calor| + |b_frío|)/2, |sesgo del Q95| de la rapidez y la media en 5, 10, 90 y 95."""
        rng = np.random.default_rng(5)
        n = self.U.a("EX_MIN_DIAS")
        o = pd.DataFrame({"media": rng.normal(15, 4, n), "maximo": rng.normal(22, 4, n), "minimo": rng.normal(8, 4, n)})
        p = pd.DataFrame({"media": o.media + 0.3, "maximo": o.maximo + 1.0, "minimo": o.minimo - 2.0})
        self.assertAlmostEqual(V.extremos(p, o, "ambiental", "T", self.U), 1.5, places=12)
        self.assertAlmostEqual(V.extremos(p, o, "ambiental", "Td", self.U), 1.5, places=12)
        self.assertAlmostEqual(V.extremos(p, o, "ambiental", "rapidez", self.U), 1.0, places=12)
        self.assertAlmostEqual(V.extremos(p, o, "agudo", "temp_media", self.U), 0.3, places=12)
        self.assertAlmostEqual(V.extremos(p, o, "agudo", "hr_media", self.U), 0.3, places=12)
        self.assertAlmostEqual(V.extremos(p, o, "cronico", "temp_media", self.U), 0.3, places=12)
        self.assertTrue(math.isnan(V.extremos(p.iloc[1:], o.iloc[1:], "ambiental", "T", self.U)))
        for uso, v in (("ambiental", "p"), ("ambiental", "HR"), ("cronico", "hr_media"), ("agudo", "T")):
            with self.assertRaises(ValueError):
                V.extremos(p, o, uso, v, self.U)
        d = V.extremos_descriptivos(p.maximo, o.maximo, self.U)
        self.assertAlmostEqual(d["sesgo_sobre_q_alto"], 1.0, places=12)
        self.assertEqual(d["acierto"], 1.0)
        # VAL-7: cuantil empírico sin interpolar. Con x = 0…n−1, Q95 es el valor de orden ⌈0,95·n⌉ (854 con n = 900),
        # no 854,05 como con la interpolación lineal.
        x = np.arange(n, dtype=np.float64)
        lineal = pd.DataFrame({"media": x, "maximo": x, "minimo": x})
        doble = pd.DataFrame({"media": 2 * x, "maximo": 2 * x, "minimo": 2 * x})
        self.assertEqual(V.extremos(doble, lineal, "ambiental", "rapidez", self.U), float(math.ceil(0.95 * n) - 1))

    def test_extremos_descriptivos_sobre_es_estricto(self):
        """§5.8, descriptivos (VAL-7): «sobre el Q95» y «bajo el Q05» son estrictos. Con la observación 0…n−1, el día
        del Q95 mismo (y el del Q05) no entra al sesgo condicional, aunque su error sea 100 (o −50); el acierto es la
        fracción de los días sobre el Q95 observado en que el producto pasa su propio Q95."""
        n = self.U.a("EX_MIN_DIAS")
        q_alto, q_bajo = constantes.valor("EX_CUANTILES_DESCRIPTIVOS")
        self.assertEqual(constantes.valor("EX_ACIERTO_CUANTIL"), q_alto)

        def de_orden(x, q):                              # cuantil empírico sin interpolar: el valor de orden ⌈q·n⌉
            return float(np.sort(x)[-(-q * x.size // 100) - 1])

        o = np.arange(n, dtype=np.float64)
        qa, qb = de_orden(o, q_alto), de_orden(o, q_bajo)
        p = o.copy()
        p[o > qa] += 1.0
        p[o == qa] += 100.0
        p[o < qb] -= 2.0
        p[o == qb] -= 50.0
        d = V.extremos_descriptivos(p, o, self.U)
        self.assertEqual(d["sesgo_sobre_q_alto"], 1.0)
        self.assertEqual(d["sesgo_bajo_q_bajo"], -2.0)
        sobre = o > qa
        self.assertEqual(d["acierto"], float(np.mean(p[sobre] > de_orden(p, q_alto))))
        self.assertTrue(0 < d["acierto"] < 1)
        # Serie de cada descriptivo (VAL-7, VAL-P8): el máximo diario da +1 y acierto 1; el mínimo, invertido, da −2x en
        # la cola baja (media −2·media(x < Q05)) y acierto 0; la media diaria, +3.
        diario_o = pd.DataFrame({"media": o, "maximo": o, "minimo": o})
        diario_p = pd.DataFrame({"media": o + 3.0, "maximo": o + 1.0, "minimo": -o})
        bajo_min = float(np.mean(-2 * o[o < qb]))
        for uso, v, esperado in ((Uso.AMBIENTAL, "T", (1.0, bajo_min, 1.0)), (Uso.AMBIENTAL, "Td", (1.0, bajo_min, 1.0)),
                                 (Uso.AMBIENTAL, "rapidez", (1.0, 1.0, 1.0)), (Uso.AGUDO, "temp_media", (3.0, 3.0, 1.0)),
                                 (Uso.CRONICO, "temp_media", (3.0, 3.0, 1.0))):
            with self.subTest(uso=uso.value, variable=v):
                d = V._descriptivos_extremos(diario_p, diario_o, uso, v, self.U)
                self.assertEqual((d["sesgo_sobre_q_alto"], d["sesgo_bajo_q_bajo"], d["acierto"]), esperado)

    def test_cociente_de_amplitudes(self):
        """§5.2 («El cociente de amplitudes se informa aparte»; VAL-6): media por mes de la amplitud del ciclo medio del
        producto, dividida por la misma media de la observación (no la media de los cocientes); NaN sin ciclo
        observado. ``evaluacion`` lo devuelve en sus descriptivos."""
        h = np.arange(_h_de("2019-01-01"), _h_de("2020-01-01"), dtype=np.int64)
        mes = (np.datetime64("2000-01-01T00", "h") + h).astype("datetime64[M]").astype(np.int64) % 12
        coseno = np.cos(2 * np.pi * (h - 19) / 24)
        a = 1.0 + 0.5 * np.arange(12)                       # amplitud observada de cada mes
        c = 3.0 + np.where(np.arange(12) < 6, 2.0, -1.5)   # la del producto: no es proporcional
        obs = 10.0 + a[mes] * coseno
        pred = 12.0 + c[mes] * coseno
        esperado = float(np.mean(c) / np.mean(a))
        self.assertNotAlmostEqual(esperado, float(np.mean(c / a)), places=3)
        self.assertAlmostEqual(V.cociente_amplitudes(h, pred, obs, self.U), esperado, places=12)
        self.assertAlmostEqual(V.cociente_amplitudes(h, obs, pred, self.U), 1 / esperado, places=12)
        self.assertTrue(math.isnan(V.cociente_amplitudes(h, pred, np.full(h.size, 10.0), self.U)))
        m = V.evaluacion(h, pred, obs, uso="ambiental", variable="T", umbrales=self.U)
        self.assertEqual(m["descriptivos"]["cociente_amplitudes"], V.cociente_amplitudes(h, pred, obs, self.U))

    def test_descriptivos_de_cada_evaluacion(self):
        """VAL-21 y VAL-7: ``evaluacion`` trae los descriptivos de ``descriptivos_de`` (cociente donde hay CD; sesgo
        condicional y acierto donde hay EX; Tmáx y Tmín en ``temp_media`` del agudo), cada uno en su serie diaria. Con
        el error 0,5 + 0,3·c + 0,1·c² (c = el coseno del ciclo diario, 1 en el máximo y −1 en el mínimo) el error del
        máximo diario es 0,9, el del mínimo 0,3 y el de la media 0,55: T y Td dan 0,9 sobre el Q95 (en los máximos) y
        0,3 bajo el Q05 (en los mínimos); la rapidez, 0,9 en los dos (el máximo diario); las medias diarias, 0,55; y
        Tmáx-Tmín del agudo, (0,9 + 0,3)/2. ``filas_descriptivas`` los pone en filas y exige todos. Las horas empiezan
        en la medianoche civil (UTC−3 todo 2015): un día de 23 horas en la cola cálida movería la media de c²."""
        h = np.arange(_h_de("2015-01-01T03"), _h_de("2018-01-01T03"), dtype=np.int64)
        obs = _verdad_t(h)
        c = np.cos(2 * np.pi * (h - 19) / 24)
        pred = obs + 0.5 + 0.3 * c + 0.1 * c ** 2
        maximo, minimo, media = 0.9, 0.3, 0.55
        por_serie = {"ambiental": (maximo, minimo), "rapidez": (maximo, maximo), "diaria": (media, media)}
        cociente = (2 * 6.3) / (2 * 6.0)                    # amplitud del ciclo medio: 6,3·2 frente a 6·2 (aprox.)
        nombres = {("ambiental", "T"): ("cociente_amplitudes", "sesgo_sobre_q_alto", "sesgo_bajo_q_bajo", "acierto"),
                   ("ambiental", "Td"): ("sesgo_sobre_q_alto", "sesgo_bajo_q_bajo", "acierto"),
                   ("ambiental", "HR"): ("cociente_amplitudes",), ("ambiental", "p"): ("cociente_amplitudes",),
                   ("ambiental", "rapidez"): ("cociente_amplitudes", "sesgo_sobre_q_alto", "sesgo_bajo_q_bajo",
                                              "acierto"),
                   ("ambiental", "uv"): (), ("agudo", "T"): ("cociente_amplitudes",),
                   ("agudo", "temp_media"): ("sesgo_sobre_q_alto", "sesgo_bajo_q_bajo", "acierto", "ex_tmax_tmin"),
                   ("agudo", "hr_media"): ("sesgo_sobre_q_alto", "sesgo_bajo_q_bajo", "acierto"),
                   ("cronico", "T"): ("cociente_amplitudes",),
                   ("cronico", "temp_media"): ("sesgo_sobre_q_alto", "sesgo_bajo_q_bajo", "acierto")}
        for (uso, v), ns in nombres.items():
            with self.subTest(uso=uso, variable=v):
                self.assertEqual(V.descriptivos_de(uso, v), ns)
                if v == "uv":
                    m = V.evaluacion(h, (pred, pred), (obs, obs), uso=uso, variable=v, umbrales=self.U)
                else:
                    m = V.evaluacion(h, pred, obs, uso=uso, variable=v, umbrales=self.U)
                self.assertEqual(tuple(m["descriptivos"]), ns)
                serie = ("rapidez" if v == "rapidez" else "ambiental") if uso == "ambiental" else "diaria"
                esperado = {"sesgo_sobre_q_alto": por_serie[serie][0], "sesgo_bajo_q_bajo": por_serie[serie][1],
                            "acierto": 1.0, "ex_tmax_tmin": (maximo + minimo) / 2}
                for nombre in ns:
                    if nombre == "cociente_amplitudes":     # el ciclo anual mueve la amplitud en milésimas
                        self.assertAlmostEqual(m["descriptivos"][nombre], cociente, places=3)
                    else:
                        self.assertAlmostEqual(m["descriptivos"][nombre], esperado[nombre], places=10, msg=nombre)
                filas = V.filas_descriptivas(m, codigo="330001", particion="P1", candidato="A", uso=uso, variable=v)
                self.assertEqual([f["descriptivo"] for f in filas], list(ns))
        with self.assertRaises(ValueError):
            V.filas_descriptivas({"descriptivos": {}}, codigo="330001", particion="P1", candidato="A", uso="agudo",
                                 variable="temp_media")
        with self.assertRaises(ValueError):
            V.descriptivos_de("cronico", "HR")

    def test_evaluacion_completa(self):
        """``evaluacion`` → ``fila_evaluacion`` → ``tabla_evaluaciones``: con un sesgo constante de 0,5, MSE 0,25, CD 0,
        EX 0,5, nivel 0,25 y desviación dentro del estrato 0; < 2.000 horas no es evaluable."""
        h = np.arange(_h_de("2015-01-01T04"), _h_de("2018-01-01T04"), dtype=np.int64)
        obs = _verdad_t(h)
        pred = obs + 0.5
        filas = []
        esperado = {("ambiental", "T"): {"mse_h": 0.25, "sesgo_h": 0.5, "cd": 0.0, "ex": 0.5},
                    ("agudo", "temp_media"): {"mse_dia": 0.25, "mse_estrato": 0.0, "ex": 0.5},
                    ("cronico", "T"): {"mse_h": 0.25, "cd": 0.0}}
        for (uso, v), cols in esperado.items():
            m = V.evaluacion(h, pred, obs, uso=uso, variable=v, umbrales=self.U)
            for c, x in cols.items():
                self.assertAlmostEqual(m[c], x, places=10, msg=(uso, v, c))
            self.assertEqual(m["n_horas"], h.size)
            self.assertGreaterEqual(m["n_dias"], self.U.a("EX_MIN_DIAS"))
            if (uso, v) == ("cronico", "T"):
                self.assertEqual(sorted(m["anuales"]), [2015, 2016, 2017])
                self.assertTrue(all(abs(e - 0.5) < 1e-12 for e in m["anuales"].values()))
            filas.append(V.fila_evaluacion(m, codigo="330001", particion="P1", pliegue="P1-3", candidato="A",
                                           uso=uso, variable=v, frac_sin_soporte=0.0))
        tabla = V.tabla_evaluaciones(filas)
        tipos.validar_esquema(tabla, tipos.ESQUEMA_EVALUACIONES, nombre="evaluaciones")
        self.assertIsNone(V.evaluacion(h[:1999], pred[:1999], obs[:1999], uso="ambiental", variable="T",
                                       umbrales=self.U))
        with self.assertRaises(ValueError):
            V.tabla_evaluaciones(filas + filas[:1])
        with self.assertRaises(ValueError):
            V.fila_evaluacion(m, codigo="330001", particion="P1", pliegue="P2-4_83", candidato="A", uso="cronico",
                              variable="T", frac_sin_soporte=0.0)
        with self.assertRaises(ValueError):
            V.evaluacion(h, pred, obs, uso="cronico", variable="HR", umbrales=self.U)

    # --- §5.3 ---------------------------------------------------------------------------------------------------
    def test_bandas_bordes_inclusivos(self):
        """VAL-8: [0, 10], (10, 25], (25, 50] y > 50 km; sin estación de entrenamiento, la última."""
        self.assertEqual(V.rotulos_bandas(self.U), ("0-10", "10-25", "25-50", ">50"))
        d = [0, 10, 10.000001, 25, 25.5, 50, 50.1, math.inf]
        self.assertEqual(V.bandas(d, self.U).tolist(), [0, 0, 1, 1, 2, 2, 3, 3])
        with self.assertRaises(ValueError):
            V.bandas([np.nan], self.U)

    def test_bandas_de_pliegues(self):
        """VAL-8: la banda de cada evaluación desde ``particiones`` y las horas válidas de su variable."""
        infos = {"330001": _info("330001", lat=-33.0, lon=-70.0), "330002": _info("330002", lat=-33.1, lon=-70.0),
                 "330003": _info("330003", lat=-34.0, lon=-70.0)}
        pl = [tipos.Pliegue("P1-0", tipos.Particion.P1, ("330001",), ("330002", "330003")),
              tipos.Pliegue("P1-0/i0", tipos.Particion.P1, ("330002",), ("330003",), externo="P1-0")]
        horas = {"T": {"330002": 5000, "330003": 5000}, "viento": {"330002": 10, "330003": 5000}}
        b = V.bandas_de_pliegues(pl, infos, horas, self.U)
        self.assertEqual(b, {("330001", "P1", "T"): 1, ("330001", "P1", "viento"): 3})
        with self.assertRaises(ValueError):
            V.bandas_de_pliegues(pl, infos, {"rapidez": {}}, self.U)

    def test_puntaje_con_bandas_unidas(self):
        """Una banda con < 10 evaluaciones se une con la contigua más cercana a 0 (la de 0-10 km, con la de 10-25)."""
        rng = np.random.default_rng(2)
        pi = np.array([0.4, 0.3, 0.2, 0.1])

        def s_de(x, b, grupos):
            return math.sqrt(sum(pi[g].sum() * x[np.isin(b, g)].mean() for g in grupos))

        for cuentas, grupos in (((3, 12, 12, 12), ([0, 1], [2], [3])), ((12, 5, 6, 12), ([0, 1, 2], [3])),
                                ((12, 12, 12, 2), ([0], [1], [2, 3])), ((2, 2, 2, 2), ([0, 1, 2, 3],)),
                                ((0, 12, 0, 12), ([0, 1, 2], [3]))):
            with self.subTest(cuentas=cuentas):
                b = np.repeat(np.arange(4), cuentas)
                x = rng.uniform(0.5, 2.0, b.size)
                self.assertAlmostEqual(V.puntaje(x, b, pi, self.U), s_de(x, b, grupos), places=14)
        self.assertTrue(math.isnan(V.puntaje([], [], pi, self.U)))
        with self.assertRaises(ValueError):
            V.puntaje([np.nan], [0], pi, self.U)
        with self.assertRaises(ValueError):
            V.puntaje([1.0], [0], (0.5, 0.5, 0.5, 0.5), self.U)

    def test_cd_y_ex_se_agregan_con_el_cuadrado_mc29(self):
        """CD = √(Σ π_b media_b(CD_e²)), y lo mismo con EX (MC-29); el nivel y la anomalía como S (VAL-10)."""
        infos = _red(n_centro=40, n_sur=0, n_sin=0)
        for uso, v, col_pub, col in (("ambiental", "T", "CD", "cd"), ("ambiental", "Td", "EX", "ex"),
                                     ("agudo", "temp_media", "nivel", "mse_dia"),
                                     ("cronico", "T", "anomalia", "mse_anomalia")):
            with self.subTest(uso=uso, columna=col_pub):
                ev = _evaluaciones(uso, "T_Td", infos)
                banda = _bandas(ev)
                tabla = V.estratos(ev, infos, self.U, uso=uso, grupo="T_Td", banda=banda, pi=_pis())
                sel = ev[(ev.variable == v) & (ev.candidato == "A")]
                b = np.array([banda[(c, p, V.HORAS_DE[v])] for c, p in zip(sel.codigo, sel.particion)])
                x = sel[col].to_numpy()
                y = x ** 2 if col_pub in ("CD", "EX") else x
                fila = _fila_pub(tabla, variable=v, candidato="A", particion="agregado")
                self.assertAlmostEqual(fila[col_pub], V.puntaje(y, b, _PI, self.U), places=14)
                self.assertAlmostEqual(fila[col_pub], math.sqrt(sum(
                    _PI[k] * y[b == k].mean() for k in range(4))), places=12)

    def test_puntaje_par_calza_con_decision(self):
        """Acuerdo A11: ``puntaje_par`` da, bit a bit, el S del grupo de ``decision._s_del_grupo`` en todos los casos
        de ``sintetico.tablas_metricas``."""
        vistos = 0
        for caso in S.CASOS_METRICAS:
            if caso == "soporte":
                continue
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                uso, grupo = Uso(d["uso"]), Grupo(d["grupo"])
                ent = tipos.EntradasDecision(uso, grupo, d["validacion"], d["tf"], d["replicas"], d["e0_excluidos"])
                prep = decision._preparar(uso, grupo, ent)
                vs = decision.VARIABLES[(uso, grupo)].S
                por = [{c: prep.nacional[(v, c)]["S"] for c in prep.e0} for v in vs]
                mio = V.puntaje_par(por[0], por[1] if len(por) == 2 else None, prep.e0)
                self.assertEqual(mio, decision._s_del_grupo(prep))
                self.assertEqual(mio, d["esperado"]["S"])
                vistos += 1
        self.assertGreaterEqual(vistos, 20)
        with self.assertRaises(ValueError):
            V.puntaje_par({"A": 0.0, "B": 1.0}, {"A": 1.0, "B": 1.0}, ("A", "B"))
        with self.assertRaises(ValueError):
            V.puntaje_par({"A": 1.0}, {"A": 1.0}, ("A", "B"))

    def test_parametros_iguales_a_decision(self):
        """VAL-1: candidatos por uso, variables de S, CD, EX, MZ, nivel y anomalía, como ``decision`` (DEC-1)."""
        self.assertEqual(dict(V.CANDIDATOS_USO), dict(decision.CANDIDATOS_USO))
        self.assertEqual(set(V.METRICAS), set(decision.VARIABLES))
        for clave, vg in decision.VARIABLES.items():
            with self.subTest(clave=clave):
                self.assertEqual(V.S_DEL_GRUPO[clave], vg.S)
                self.assertEqual(V.VARIABLES_MZ[clave], vg.MZ)
                for col, variables in (("S", vg.S), ("CD", vg.CD), ("EX", vg.EX), ("nivel", vg.nivel),
                                       ("anomalia", vg.anomalia)):
                    publicadas = {v for v, m in V.METRICAS[clave].items() if col in m}
                    self.assertLessEqual(set(variables), publicadas, col)
                    if col != "S":
                        self.assertEqual(set(variables), publicadas, col)
        self.assertEqual(V.MACROZONAS, tipos.MACROZONAS)
        self.assertEqual((V.ESTRATO_NACIONAL, V.ESTRATO_MACROZONA), (decision.ESTRATO_NACIONAL,
                                                                     decision.ESTRATO_MACROZONA))
        self.assertEqual(V.PARTICIONES, decision.PARTICIONES)
        todas = {v for m in V.METRICAS.values() for v in m}
        self.assertLessEqual(todas, {v.value for v in tipos.VariableMetrica})

    def test_claves_de_horas_son_las_de_la_tabla_ancha(self):
        prefijo = "valido_"
        self.assertEqual(V.CLAVES_HORAS, tuple(c[len(prefijo):] for c in tipos.ESQUEMA_QC_ESTACION
                                               if c.startswith(prefijo)))
        self.assertEqual(set(V.HORAS_DE), {v.value for v in tipos.VariableMetrica})

    def test_pi_poblacion(self):
        """§5.3, π^pob (VAL-9): 2000-2025, cada celda con w_ghs > 0 a la estación más cercana con ≥ 2.000 horas."""
        anios = range(2000, 2026)
        est = pd.DataFrame({"codigo": ["330001", "330002"], "lat": [-33.0, -34.0], "lon": [-70.0, -70.0]})
        celdas = pd.DataFrame({"lat": [-33.05, -33.3, -33.6, -34.0, -35.0], "lon": [-70.0] * 5,
                               "w": [1.0, 2.0, 3.0, 4.0, 0.0]})
        filas, por_anio = [], {}
        for y in anios:
            por_anio[y] = est.assign(horas=[5000, 5000 if y >= 2010 else 100])
            for c in celdas.itertuples():
                filas.append({"anio": y, "lat": c.lat, "lon": c.lon, "w_ghs": c.w * (1 + (y - 2000) / 100)})
        tabla = pd.DataFrame(filas)
        pi = V.pi_poblacion(tabla, por_anio, "T", self.U)
        acum = np.zeros(4)
        for f in filas:
            if f["w_ghs"] <= 0:
                continue
            activas = est[por_anio[f["anio"]].horas.to_numpy() >= 2000]
            d = min(numerico.haversine_km(f["lat"], f["lon"], r.lat, r.lon) for r in activas.itertuples())
            acum[int(V.bandas([d], self.U)[0])] += f["w_ghs"]
        self.assertEqual(list(pi), list(V.rotulos_bandas(self.U)))
        np.testing.assert_allclose(list(pi.values()), acum / acum.sum(), rtol=0, atol=1e-14)
        with self.assertRaises(ValueError):
            V.pi_poblacion(tabla[tabla.anio != 2025], por_anio, "T", self.U)

    def test_pi_monitores_mc09(self):
        """§5.3, π^mon (MC-09, R21): un peso por monitor-año con datos de PM2,5 o NO2 en el panel que cita el
        manifiesto de la red 2, con sus coordenadas; el panel debe ser el citado."""
        with tempfile.TemporaryDirectory() as tmp:
            r = S.panel_y_pliegues(tmp)
            manifiesto = json.loads(Path(r["pliegues"]).read_text(encoding="utf-8"))
            paneles = {pol: {"tabla": pd.read_parquet(r[f"panel_{pol}"]),
                             "sha256": hashlib.sha256(Path(r[f"panel_{pol}"]).read_bytes()).hexdigest()}
                       for pol in tipos.CONTAMINANTES_M6}
        est = pd.DataFrame({"codigo": ["330001", "330002"], "lat": [-33.45, -36.8], "lon": [-70.65, -73.0],
                            "horas": [5000, 5000]})
        pi = V.pi_monitores(manifiesto, paneles, {2019: est}, "T", self.U)
        coord = {e["estacion"]: (e["lat"], e["lon"]) for e in manifiesto["estaciones"]}
        acum = np.zeros(4)
        for m, (la, lo) in sorted(coord.items()):        # 12 monitores-año: S012 sin NO2 pesa una vez
            d = min(numerico.haversine_km(la, lo, x.lat, x.lon) for x in est.itertuples())
            acum[int(V.bandas([d], self.U)[0])] += 1
        self.assertEqual(acum.sum(), 12)
        np.testing.assert_allclose(list(pi.values()), acum / 12, rtol=0, atol=1e-15)
        mal = {**paneles, "no2": {**paneles["no2"], "sha256": "0" * 64}}
        with self.assertRaises(ValueError):
            V.pi_monitores(manifiesto, mal, {2019: est}, "T", self.U)
        with self.assertRaises(ValueError):
            V.pi_monitores(manifiesto, paneles, {2018: est}, "T", self.U)
        amb = V.pi_uso("ambiental", _PI, (0.1, 0.2, 0.3, 0.4), umbrales=self.U)
        np.testing.assert_allclose(amb, [0.25, 0.25, 0.25, 0.25], atol=1e-15)
        np.testing.assert_array_equal(V.pi_uso("agudo", _PI, umbrales=self.U), _PI)
        with self.assertRaises(ValueError):
            V.pi_uso("ambiental", _PI, umbrales=self.U)

    # --- §5.5: estratos ------------------------------------------------------------------------------------------
    def test_estratos_rotulos_macrozonas_y_publicable(self):
        """TIP-15, A13, D43: rótulos de ``tipos``; las cinco macrozonas en cada variable de MZ (también la rapidez de
        (u, v)), en P1, P2 y el agregado, para todo candidato; vacías con n = 0, no publicables y S NaN; publicable y
        n_estaciones iguales para todos los candidatos; la estación sin macrozona sólo en lo nacional."""
        infos = _red()
        ev = _evaluaciones("ambiental", "u_v", infos)
        tabla = V.estratos(ev, infos, self.U, uso="ambiental", grupo="u_v", banda=_bandas(ev), pi=_pis())
        tipos.validar_esquema(tabla, tipos.ESQUEMA_VALIDACION_PUB, nombre="validacion")
        self.assertLessEqual(set(tabla.variable), {v.value for v in tipos.VariableMetrica})
        self.assertLessEqual(set(tabla.estrato), set(V.ESTRATOS))
        self.assertEqual(set(tabla.particion), set(V.PARTICIONES))
        claves = ["variable", "candidato", "particion", "estrato", "valor_estrato"]
        self.assertFalse(tabla.duplicated(claves).any())
        mz = tabla[tabla.estrato == "macrozona"]
        self.assertEqual(set(mz.variable), {"uv", "rapidez"})
        for v in ("uv", "rapidez"):
            for z in tipos.MACROZONAS:
                for cand in V.CANDIDATOS_USO[Uso.AMBIENTAL]:
                    for p in V.PARTICIONES:
                        fila = _fila_pub(tabla, variable=v, candidato=cand, particion=p, estrato="macrozona", valor=z)
                        if z == "centro":
                            self.assertTrue(fila.publicable and math.isfinite(fila.S))
                            self.assertEqual(fila.n_estaciones, 12)
                        elif z == "sur":
                            self.assertEqual(fila.n_estaciones, 3)
                        else:
                            self.assertEqual((fila.n_estaciones, fila.n_evaluaciones, bool(fila.publicable)),
                                             (0, 0, False))
                            self.assertTrue(math.isnan(fila.S))
        grupos = tabla.groupby(["variable", "particion", "estrato", "valor_estrato"])
        self.assertTrue((grupos["publicable"].nunique() == 1).all())
        self.assertTrue((grupos["n_estaciones"].nunique() == 1).all())
        self.assertEqual(tabla.attrs["declaraciones"]["sin_macrozona"], 1)
        nac = _fila_pub(tabla, variable="uv", candidato="A", particion="agregado")
        self.assertEqual(nac.n_estaciones, 16)
        no_formados = tabla.attrs["declaraciones"]["estratos_no_formados"]
        self.assertEqual(set(no_formados), {"periodo", "tipo", "propietario", "omm"})
        self.assertEqual(set(tabla.loc[tabla.estrato == "altitud", "valor_estrato"]), {"<500", "500-2000", ">2000"})

    def test_estratos_descriptivos_y_periodos(self):
        """VAL-17: tipo, propietario, OMM y período (con las evaluaciones de cada período)."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)
        altitudes = {0: 499.9, 1: 500.0, 2: 2000.0, 3: 2000.1}             # los bordes: [500, 2.000] es el del medio
        infos = {c: dataclasses.replace(i, tipo="sinoptica" if k % 2 else "climatologica",
                                        omm=(k % 3 == 0) or None, propietario="DMC", z_s=altitudes.get(k, 1000.0))
                 for k, (c, i) in enumerate(sorted(infos.items()))}
        ev = _evaluaciones("ambiental", "p", infos)
        periodos = {"2000-2009": _evaluaciones("ambiental", "p", infos, semilla=8),
                    "2010-2026": _evaluaciones("ambiental", "p", infos, semilla=9)}
        tabla = V.estratos(ev, infos, self.U, uso="ambiental", grupo="p", banda=_bandas(ev), pi=_pis(),
                           periodos=periodos)
        self.assertEqual(set(tabla.loc[tabla.estrato == "tipo", "valor_estrato"]), {"sinoptica", "climatologica"})
        self.assertEqual(set(tabla.loc[tabla.estrato == "omm", "valor_estrato"]), {V.VALOR_OMM})
        omm = _fila_pub(tabla, variable="p", candidato="A", particion="P1", estrato="omm", valor=V.VALOR_OMM)
        self.assertEqual(omm.n_estaciones, 4)
        alt = {z: _fila_pub(tabla, variable="p", candidato="A", particion="P1", estrato="altitud", valor=z).n_estaciones
               for z in ("<500", "500-2000", ">2000")}
        self.assertEqual(alt, {"<500": 1, "500-2000": 10, ">2000": 1})
        per = _fila_pub(tabla, variable="p", candidato="A", particion="agregado", estrato="periodo",
                        valor="2000-2009")
        sel = periodos["2000-2009"]
        self.assertEqual(per.n_evaluaciones, int(((sel.variable == "p") & (sel.candidato == "A")).sum()))
        self.assertEqual(tabla.attrs["declaraciones"]["estratos_no_formados"], ())
        with self.assertRaises(ValueError):
            V.estratos(ev, infos, self.U, uso="ambiental", grupo="p", banda=_bandas(ev), pi=_pis(),
                       periodos={"2010-2026": ev})

    def test_estratos_entran_a_decidir_combinacion(self):
        """Lo publicado y el remuestreo entran a ``decision.decidir_combinacion`` tal cual en los cinco (uso, grupo), y
        el ganador es el de menor S (AB, con las compuertas pasadas)."""
        infos = _red()
        bloques = {c: i.bloque for c, i in infos.items()}
        for (uso, grupo), caso in _TF_DE.items():
            with self.subTest(uso=uso.value, grupo=grupo.value):
                ev = _evaluaciones(uso, grupo, infos)
                kw = dict(uso=uso, grupo=grupo, banda=_bandas(ev), pi=_pis())
                tabla = V.estratos(ev, infos, self.U, **kw)
                rep = V.remuestreo(ev, bloques, self.U, infos=infos, e0=V.CANDIDATOS_USO[uso], **kw)
                ent = tipos.EntradasDecision(uso, grupo, tabla, S.tablas_metricas(caso)["tf"], rep, {})
                d = decision.decidir_combinacion(uso, grupo, ent, umbrales=self.U)
                self.assertEqual(d.ganador, "AB")
                self.assertEqual(d.e1, V.CANDIDATOS_USO[uso])
                mz = decision.compuertas(uso, grupo, ent, self.U)
                mz = mz[(mz.compuerta == "MZ") & mz.aplica]
                self.assertEqual(set(mz.ambito), {"centro"})          # 12 estaciones; «sur» tiene 3
                self.assertEqual(set(mz.variable), set(V.VARIABLES_MZ[(uso, grupo)]))

    def test_d34_fuera_de_la_grilla_y_estaciones_invalidas(self):
        """D34 (VAL-16): las evaluaciones de una estación fuera de la grilla se descartan y se cuentan; una excluida
        o desconocida es un error."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)
        fuera = sorted(infos)[0]
        ev = _evaluaciones("ambiental", "p", infos)
        infos_f = {**infos, fuera: dataclasses.replace(infos[fuera], celda=None, macrozona=None)}
        kw = dict(uso="ambiental", grupo="p", banda=_bandas(ev), pi=_pis())
        tabla = V.estratos(ev, infos_f, self.U, **kw)
        self.assertEqual(tabla.attrs["declaraciones"]["fuera_de_la_grilla"], 1)
        self.assertEqual(_fila_pub(tabla, variable="p", candidato="A", particion="agregado").n_estaciones, 11)
        excluida = {**infos, fuera: dataclasses.replace(infos[fuera], excluida=True, motivo="k3")}
        with self.assertRaises(ValueError):
            V.estratos(ev, excluida, self.U, **kw)
        with self.assertRaises(ValueError):
            V.estratos(ev, {c: i for c, i in infos.items() if c != fuera}, self.U, **kw)

    def test_macrozonas_que_no_son_macrozona(self):
        """VAL-16 (D9, D16): «sin_region» e «insular» cuentan como sin macrozona (sólo en lo nacional); un nombre que no
        es de ``tipos.MACROZONAS`` es un error. VAL-17 (pregunta VAL-P7): las variables sin filas de macrozona se
        declaran."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)
        c1, c2 = sorted(infos)[:2]
        raras = {**infos, c1: dataclasses.replace(infos[c1], macrozona="insular"),
                 c2: dataclasses.replace(infos[c2], macrozona="sin_region")}
        ev = _evaluaciones("ambiental", "T_Td", infos)
        kw = dict(uso="ambiental", grupo="T_Td", banda=_bandas(ev), pi=_pis())
        tabla = V.estratos(ev, raras, self.U, **kw)
        self.assertEqual(tabla.attrs["declaraciones"]["sin_macrozona"], 2)
        self.assertEqual(tabla.attrs["declaraciones"]["variables_sin_estrato_macrozona"], ("Td",))
        self.assertEqual(_fila_pub(tabla, variable="T", candidato="A", particion="agregado", estrato="macrozona",
                                   valor="centro").n_estaciones, 10)
        self.assertEqual(_fila_pub(tabla, variable="T", candidato="A", particion="agregado").n_estaciones, 12)
        self.assertLessEqual(set(tabla.loc[tabla.estrato == "macrozona", "valor_estrato"]), set(tipos.MACROZONAS))
        with self.assertRaises(ValueError):
            V.estratos(ev, {**infos, c1: dataclasses.replace(infos[c1], macrozona="atlantida")}, self.U, **kw)

    def test_las_mismas_evaluaciones_para_todos_los_candidatos(self):
        """VAL-15: cada candidato trae las mismas evaluaciones y las mismas métricas finitas."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)
        ev = _evaluaciones("ambiental", "p", infos)
        kw = dict(uso="ambiental", grupo="p", banda=_bandas(ev), pi=_pis())
        sin_una = ev.drop(index=ev.index[(ev.candidato == "C").to_numpy()][0])
        with self.assertRaises(ValueError):
            V.estratos(sin_una, infos, self.U, **kw)
        nan_en_una = ev.copy()
        nan_en_una.loc[nan_en_una.index[(nan_en_una.candidato == "B").to_numpy()][0], "cd"] = np.nan
        with self.assertRaises(ValueError):
            V.estratos(nan_en_una, infos, self.U, **kw)
        frac_mala = ev.copy()
        frac_mala.loc[frac_mala.index[(frac_mala.candidato == "A").to_numpy()][0], "frac_sin_soporte"] = np.nan
        with self.assertRaises(ValueError):
            V.estratos(frac_mala, infos, self.U, **kw)
        with self.assertRaises(ValueError):
            V.estratos(ev, infos, self.U, uso="agudo", grupo="p", banda=kw["banda"], pi=_pis())

    def test_fraccion_sin_soporte_por_horas(self):
        """VAL-13: la fracción del estrato es la de sus horas de prueba (media ponderada por ``n_horas``), no la media
        de las evaluaciones: 0,9 en 1.000 h y 0,2 en 3.000 h dan 0,375 (publicable), no 0,55."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)
        codigos = sorted(infos)

        def frac(codigo, particion, cand):
            return 0.9 if (cand == "B" and codigo in codigos[:6]) else 0.2

        ev = _evaluaciones("ambiental", "p", infos, frac=frac)
        ev.loc[ev.codigo.isin(codigos[:6]).to_numpy(), "n_horas"] = 1000
        ev.loc[ev.codigo.isin(codigos[6:]).to_numpy(), "n_horas"] = 3000
        kw = dict(uso="ambiental", grupo="p", banda=_bandas(ev), pi=_pis())
        tabla = V.estratos(ev, infos, self.U, **kw)
        fila = _fila_pub(tabla, variable="p", candidato="A", particion="agregado", estrato="macrozona", valor="centro")
        self.assertTrue(fila.publicable)
        ev.loc[ev.codigo.isin(codigos[:6]).to_numpy(), "n_horas"] = 3000
        ev.loc[ev.codigo.isin(codigos[6:]).to_numpy(), "n_horas"] = 1000
        tabla = V.estratos(ev, infos, self.U, **kw)
        fila = _fila_pub(tabla, variable="p", candidato="A", particion="agregado", estrato="macrozona", valor="centro")
        self.assertFalse(fila.publicable)                         # 0,725 > 0,5
        sop = V.fracciones_sin_soporte(ev, infos, self.U, **kw)
        b = sop[(sop.candidato == "B") & (sop.particion == "agregado") & (sop.valor_estrato == "centro")]
        self.assertAlmostEqual(float(b.frac_sin_soporte.iloc[0]), (0.9 * 3000 + 0.2 * 1000) / 4000, places=14)

    def test_publicable_borde(self):
        """§0.4.4 «en más del 50 %»: 0,5 exacto se publica; C no cuenta; faltar uno del núcleo es un error."""
        self.assertTrue(V.publicable({"A": 0.5, "B": 0.0, "AB": 0.5, "C": 1.0}, self.U))
        self.assertFalse(V.publicable({"A": 0.5, "B": 0.5000001, "AB": 0.0}, self.U))
        with self.assertRaises(ValueError):
            V.publicable({"A": 0.1, "B": 0.1}, self.U)
        with self.assertRaises(ValueError):
            V.publicable({"A": 0.1, "B": 0.1, "AB": 1.5}, self.U)

    def test_tabla_bandas(self):
        """§5.3, «Qué se publica»: π^mon (sólo ambiental), π^pob y la fracción sin soporte de cada candidato por
        banda (C y C_est sin fracción)."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)

        def frac(codigo, particion, cand):
            return 0.2 if particion == "P1" else 0.6

        for uso, grupo in ((Uso.AMBIENTAL, Grupo.P), (Uso.CRONICO, Grupo.T_TD)):
            ev = _evaluaciones(uso, grupo, infos, frac=frac)
            banda = _bandas(ev, fija=2)
            t = V.tabla_bandas(ev, infos, self.U, uso=uso, grupo=grupo, banda=banda, pi_pob=_pis(),
                               pi_mon=_pis((0.25, 0.25, 0.25, 0.25)))
            tipos.validar_esquema(t, tipos.ESQUEMA_BANDAS_PUB, nombre="bandas")
            f = t[(t.banda == "25-50") & (t.candidato == "A")]
            self.assertTrue(np.allclose(f.frac_sin_soporte, 0.4))
            self.assertTrue(t[t.banda == "0-10"].frac_sin_soporte.isna().all())
            self.assertTrue(t[t.candidato.isin(["C", "C_est"])].frac_sin_soporte.isna().all())
            if uso is Uso.AMBIENTAL:
                self.assertTrue((t.pi_mon == 0.25).all())
            else:
                self.assertTrue(t.pi_mon.isna().all())

    def test_tabla_descriptivos(self):
        """VAL-21: la tabla de descriptivos (nacional, P1, P2 y el agregado) con valores conocidos: los de nivel con
        Σ_b π_b · media_b(x) y Tmáx-Tmín, un EX, con √(Σ_b π_b · media_b(x²)); las mismas evaluaciones finitas para todos
        los candidatos; lo que no es una evaluación, falta o no es descriptivo del uso es un error."""
        infos = _red(n_centro=40, n_sur=0, n_sin=0)
        codigos = sorted(infos)
        ev = _evaluaciones("agudo", "T_Td", infos)
        banda = {(c, p, k): codigos.index(c) % 4 for c in codigos for p in ("P1", "P2") for k in V.CLAVES_HORAS}
        mult = {"A": 1.2, "B": 1.1, "AB": 1.0, "C": 1.15}
        filas = []
        valor = {}
        for (c, p, cand, v) in zip(ev.codigo, ev.particion, ev.candidato, ev.variable):
            m = {"descriptivos": {}}
            for j, nombre in enumerate(V.descriptivos_de("agudo", v)):
                x = (codigos.index(c) % 7 + 1) * 0.1 * (j + 1) * mult[cand] * (1.0 if p == "P1" else -0.5)
                m["descriptivos"][nombre] = valor[(c, p, cand, v, nombre)] = x
            filas += V.filas_descriptivas(m, codigo=c, particion=p, candidato=cand, uso="agudo", variable=v)
        kw = dict(uso="agudo", grupo="T_Td", banda=banda, pi=_pis())
        t = V.tabla_descriptivos(ev, filas, infos, self.U, **kw)
        self.assertEqual(list(t.columns), list(V.COLUMNAS_DESCRIPTIVOS))
        self.assertEqual(dict(t.dtypes.astype(str)), dict(V.COLUMNAS_DESCRIPTIVOS))
        self.assertEqual(set(t.variable), {"T", "HR", "temp_media", "hr_media"})
        self.assertFalse(t.duplicated(["variable", "candidato", "particion", "descriptivo"]).any())
        for fila in t.itertuples():
            ps = ("P1", "P2") if fila.particion == "agregado" else (fila.particion,)
            xs = {k: [valor[(c, p, fila.candidato, fila.variable, fila.descriptivo)] for c in codigos for p in ps
                      if codigos.index(c) % 4 == k] for k in range(4)}
            if fila.descriptivo == "ex_tmax_tmin":
                esperado = math.sqrt(sum(_PI[k] * float(np.mean(np.square(xs[k]))) for k in range(4)))
            else:
                esperado = sum(_PI[k] * float(np.mean(xs[k])) for k in range(4))
            self.assertAlmostEqual(fila.valor, esperado, places=13, msg=fila)
            self.assertEqual((fila.n_evaluaciones, fila.n_estaciones), (40 * len(ps), 40))
        with self.assertRaises(ValueError):
            V.tabla_descriptivos(ev, filas[1:], infos, self.U, **kw)
        self.assertEqual((filas[0]["variable"], filas[0]["descriptivo"]), ("T", "cociente_amplitudes"))
        ajena = {**filas[0], "descriptivo": "ex_tmax_tmin"}               # sólo de temp_media
        with self.assertRaises(ValueError):
            V.tabla_descriptivos(ev, filas + [ajena], infos, self.U, **kw)
        with self.assertRaises(ValueError):
            V.tabla_descriptivos(ev, filas + [{**filas[0], "codigo": "339999"}], infos, self.U, **kw)
        una_nan = [dict(f) for f in filas]
        i = next(i for i, f in enumerate(una_nan) if f["candidato"] == "B")
        una_nan[i]["valor"] = _NAN
        with self.assertRaises(ValueError):
            V.tabla_descriptivos(ev, una_nan, infos, self.U, **kw)
        for f in una_nan:                                # la misma evaluación sin el valor en todos: se cuenta aparte
            if all(f[k] == una_nan[i][k] for k in ("codigo", "particion", "variable", "descriptivo")):
                f["valor"] = _NAN
        t2 = V.tabla_descriptivos(ev, una_nan, infos, self.U, **kw)
        f2 = t2[(t2.variable == una_nan[i]["variable"]) & (t2.descriptivo == una_nan[i]["descriptivo"])
                & (t2.particion == "agregado")]
        self.assertEqual(set(f2.n_evaluaciones), {79})

    # --- §5.4 ---------------------------------------------------------------------------------------------------
    def test_remuestreo_por_bloques(self):
        """1.999 réplicas por bloque de P2 (MC-34): cada réplica toma todas las evaluaciones de P1 y P2 de las
        estaciones de los bloques que salen (con repetición), rehace la unión de bandas, S y S_par con los mínimos
        de la réplica sobre E0; reproducible."""
        infos = _red(n_centro=30)
        infos["339999"] = _info("339999", bloque="9_99")              # un bloque con estaciones y sin evaluaciones
        ev = _evaluaciones("ambiental", "T_Td", {c: i for c, i in infos.items() if c != "339999"})
        banda = _bandas(ev)
        bloques = {c: i.bloque for c, i in infos.items()}
        e0 = ("A", "B", "C")                                          # sin AB, el de menor S: los mínimos son de E0
        kw = dict(infos=infos, uso="ambiental", grupo="T_Td", banda=banda, pi=_pis(), e0=e0)
        rep = V.remuestreo(ev, bloques, self.U, **kw)
        tipos.validar_esquema(rep, tipos.ESQUEMA_REPLICAS, nombre="replicas")
        n = self.U.a("BOOT_REPLICAS")
        self.assertEqual(len(rep), n * len(e0))
        self.assertEqual(sorted(set(rep.replica)), list(range(n)))
        self.assertEqual(set(rep.candidato), set(e0))
        pd.testing.assert_frame_equal(rep, V.remuestreo(ev, bloques, self.U, **kw))
        ids = sorted(set(bloques.values()))
        sorteo = numerico.remuestreo_bloques(ids, n, self.U.a("SEMILLA"))
        self.assertGreater(rep[rep.candidato == "A"].S.std(), 0, "S_par debe cambiar de una réplica a otra")
        for r in (0, 1, 2, 3, n - 1):
            por_v = {}
            for v in ("T", "HR"):
                por_v[v] = {}
                for cand in e0:
                    sel = ev[(ev.variable == v) & (ev.candidato == cand)]
                    xs, bs = [], []
                    for b in sorteo[r]:
                        de_b = sel[sel.codigo.map(bloques) == b]
                        xs += list(de_b.mse_h)
                        bs += [banda[(c, p, V.HORAS_DE[v])] for c, p in zip(de_b.codigo, de_b.particion)]
                    por_v[v][cand] = V.puntaje(xs, np.array(bs, dtype=np.int64), _PI, self.U)
            esperado = V.puntaje_par(por_v["T"], por_v["HR"], e0)
            obtenido = rep[rep.replica == r].set_index("candidato").S
            for cand in e0:
                self.assertAlmostEqual(obtenido[cand], esperado[cand], places=12)
        with self.assertRaises(ValueError):
            V.remuestreo(ev, {c: b for c, b in bloques.items() if c != sorted(bloques)[0]}, self.U, **kw)

    def test_e0_se_comprueba_antes_de_usarlo(self):
        """VAL-12 y VAL-20: un candidato de E0 que no es del uso (C_est en lo ambiental), repetido o desconocido es un
        error en el remuestreo y en el aviso SINCA; no se descarta en silencio."""
        infos = _red(n_centro=12, n_sur=0, n_sin=0)
        ev = _evaluaciones("ambiental", "p", infos)
        bloques = {c: i.bloque for c, i in infos.items()}
        kw = dict(infos=infos, uso="ambiental", grupo="p", banda=_bandas(ev), pi=_pis())
        self.assertEqual(len(V.remuestreo(ev, bloques, self.U, e0=("C", "A"), **kw)), 2 * self.U.a("BOOT_REPLICAS"))
        puntajes = {("ambiental", c, lugar, "uv/mse_h"): 1.0 for c in ("A", "B", "AB", "C") for lugar in V.LUGARES}
        self.assertEqual(V._avisos_sinca(puntajes, {"ambiental/u_v": "A"}, {"ambiental/u_v": ("A", "B")})
                         ["ambiental/u_v"]["aviso"], False)
        for e0 in (("A", "B", "C_est"), ("A", "A", "B"), ("A", "X"), (), "AB"):
            with self.subTest(e0=e0):
                with self.assertRaises(ValueError):
                    V.remuestreo(ev, bloques, self.U, e0=e0, **kw)
                with self.assertRaises(ValueError):
                    V._avisos_sinca(puntajes, {"ambiental/u_v": "A"}, {"ambiental/u_v": e0})
        with self.assertRaises(ValueError):
            V._avisos_sinca(puntajes, {"ambiental/u_v": "A"}, {"ambiental/T_Td": ("A", "B")})

    # --- §5.5: réplica con N -------------------------------------------------------------------------------------
    def test_replica_con_n(self):
        """§5.5: la decisión con sólo las evaluaciones de N; descriptiva: dice si da el mismo ganador."""
        codigos = [f"{330000 + k:06d}" for k in range(1, 17)]
        conjunto = {c: ("N" if i < 12 else "V") for i, c in enumerate(codigos)}
        infos = _red(conjunto=conjunto)
        bloques = {c: i.bloque for c, i in infos.items()}
        caso_tf = S.tablas_metricas("ganador_claro")["tf"]

        def entradas(ev):
            return {("ambiental", "T_Td"): {"evaluaciones": ev, "banda": _bandas(ev), "pi": _pis(), "bloques": bloques,
                                            "tf": caso_tf, "motivos_e0": {}, "ganador": "AB"}}

        igual = V.replica_n(entradas(_evaluaciones("ambiental", "T_Td", infos)), infos, self.U,
                            decidir=decision.decidir_combinacion)
        self.assertEqual(igual["ambiental/T_Td"], {"ganador": "AB", "ganador_n": "AB", "mismo_ganador": True,
                                                   "n_estaciones_n": 12})
        mult_a = {"A": 1.0, "B": 1.1, "AB": 1.08, "C": 1.15}
        otro = _evaluaciones("ambiental", "T_Td", infos, mult_de={c: mult_a for c in codigos[:12]})
        distinto = V.replica_n(entradas(otro), infos, self.U, decidir=decision.decidir_combinacion)
        self.assertEqual((distinto["ambiental/T_Td"]["ganador_n"], distinto["ambiental/T_Td"]["mismo_ganador"]),
                         ("A", False))
        sin_n = {c: dataclasses.replace(i, conjunto="V") for c, i in infos.items()}
        nada = V.replica_n(entradas(_evaluaciones("ambiental", "T_Td", sin_n)), sin_n, self.U,
                           decidir=decision.decidir_combinacion)
        self.assertEqual(nada["ambiental/T_Td"]["motivo"], "no_decidible")

    def test_replica_con_n_sortea_los_bloques_de_todas_las_n(self):
        """VAL-18 (como VAL-12): el remuestreo de la réplica con N sortea los bloques de P2 de todas las estaciones N
        de ``bloques``, también los de las que no tienen evaluaciones, y no los de las estaciones de V."""
        codigos = [f"{330000 + k:06d}" for k in range(1, 17)]
        infos = _red(conjunto={c: ("N" if i < 12 else "V") for i, c in enumerate(codigos)})
        infos["339999"] = _info("339999", conjunto="N", bloque="9_99")      # N, con bloque propio y sin evaluaciones
        infos["339998"] = _info("339998", conjunto="N", bloque="9_98", excluida=True, motivo="k3")
        ev = _evaluaciones("ambiental", "T_Td", {c: i for c, i in infos.items() if c != "339999"})
        bloques = {c: i.bloque for c, i in infos.items()}               # con la excluida: la réplica la deja fuera
        vistas = []

        def decidir(uso, grupo, ent, *, umbrales):
            vistas.append(ent.replicas)
            return decision.decidir_combinacion(uso, grupo, ent, umbrales=umbrales)

        entrada = {"evaluaciones": ev, "banda": _bandas(ev), "pi": _pis(), "bloques": bloques,
                   "tf": S.tablas_metricas("ganador_claro")["tf"], "motivos_e0": {}, "ganador": "AB"}
        r = V.replica_n({("ambiental", "T_Td"): entrada}, infos, self.U, decidir=decidir)
        self.assertEqual(r["ambiental/T_Td"]["n_estaciones_n"], 12)
        self.assertEqual(len(vistas), 1)
        de_n = {c for c, i in infos.items() if i.conjunto == "N" and not i.excluida}
        ev_n = ev[ev.codigo.isin(sorted(de_n)).to_numpy(dtype=bool)].reset_index(drop=True)
        kw = dict(infos=infos, uso="ambiental", grupo="T_Td", banda=entrada["banda"], pi=_pis(),
                  e0=V.CANDIDATOS_USO[Uso.AMBIENTAL])
        pd.testing.assert_frame_equal(vistas[0], V.remuestreo(ev_n, {c: bloques[c] for c in sorted(de_n)}, self.U,
                                                              **kw))
        solo_evaluadas = V.remuestreo(ev_n, {c: bloques[c] for c in sorted(set(ev_n.codigo))}, self.U, **kw)
        self.assertFalse(vistas[0].equals(solo_evaluadas), "el bloque 9_99 debe cambiar el sorteo")
        with self.assertRaises(ValueError):                 # VAL-12: un bloque de una excluida es un error
            V.remuestreo(ev_n, {c: bloques[c] for c in sorted(de_n | {"339998"})}, self.U, **kw)
        with self.assertRaises(ValueError):                 # una estación N evaluada sin bloque no es «no_decidible»
            V.replica_n({("ambiental", "T_Td"): {**entrada, "bloques": {c: b for c, b in bloques.items()
                                                                        if c != codigos[0]}}},
                        infos, self.U, decidir=decidir)

    # --- §5.6: SINCA ---------------------------------------------------------------------------------------------
    def test_aviso_sinca_15(self):
        """§5.6: ganador peor que el segundo en más de 15 % en la red → aviso; en 14 %, no; en la celda o en el punto
        (VAL-20). Con el producto igual a la verdad la métrica es 0: la media SINCA de [u − 1, u] se compara con la del
        producto en u − 1 y u, y sólo las filas válidas (A12)."""
        sesgos = {"A": 0.2, "B": 0.3, "AB": 0.2, "C": 0.4}       # el menor de los demás es AB (0,2)
        r = _caso_sinca(self.U, {**sesgos, "A": 0.2 * 1.16}, ganador="A", sesgos_punto={**sesgos, "A": 0.2 * 1.14})
        aviso = r["aviso"]["ambiental/T_Td"]
        self.assertEqual((aviso["celda"], aviso["punto"], aviso["aviso"]), (True, False, True))
        r = _caso_sinca(self.U, {**sesgos, "A": 0.2 * 1.14}, ganador="A")
        self.assertEqual(r["aviso"]["ambiental/T_Td"]["aviso"], False)
        r = _caso_sinca(self.U, {"A": 0.0, "B": 0.3, "AB": 0.25, "C": 0.4}, ganador="AB")
        met = r["metricas"]
        cero = met[(met.candidato == "A") & (met.variable == "T") & (met.metrica == "mse_h") & (met.estrato == "red")
                   & (met.lugar == "celda")]
        self.assertLess(float(cero.valor.iloc[0]), 1e-9)
        self.assertEqual(int(cero.n_estaciones.iloc[0]), 3)
        b = met[(met.candidato == "B") & (met.variable == "HR") & (met.metrica == "mse_h") & (met.estrato == "red")
                & (met.lugar == "punto")]
        self.assertAlmostEqual(float(b.valor.iloc[0]), 0.3 * 10, places=9)
        terciles = met[(met.estrato == "tercil_tpi") & (met.variable == "T") & (met.metrica == "mse_h")]
        self.assertEqual(set(terciles.valor_estrato), {"1", "2", "3"})
        self.assertTrue((terciles.n_estaciones == 1).all())
        self.assertIn("ambiental/u_v", r["aviso"])
        self.assertNotIn("ambiental/p", r["aviso"])
        uv = met[(met.candidato == "C") & (met.variable == "uv") & (met.metrica == "mse_h") & (met.estrato == "red")]
        self.assertTrue(np.allclose(uv.valor, 0.4 * math.sqrt(2), atol=1e-9))
        cociente = met[(met.variable == "T") & (met.metrica == "cociente_amplitudes") & (met.estrato == "red")]
        self.assertEqual(len(cociente), 4 * 2)                  # VAL-21 en la red: un sesgo constante no cambia el ciclo
        self.assertTrue(np.allclose(cociente.valor, 1.0, atol=1e-9))

    def test_aviso_sinca_borde_exacto(self):
        """§5.6 «en más de 15 %» (VAL-20): el ganador en exactamente 1,15 veces el segundo no da aviso; el flotante
        siguiente, sí. 1 + 15/100 es 1,15 exacto en float64 y 1,15 · 2 también: el borde se arma. En (u, v) con el único
        S y en (T, Td) con S_par, en la celda y en el punto."""
        factor = 1 + constantes.valor("SINCA_AVISO_PCT") / 100
        self.assertEqual(factor, 1.15)
        borde = factor * 2.0
        self.assertEqual(borde / 2.0, factor)
        e0 = ("A", "B", "AB", "C")
        for s_a, aviso in ((borde, False), (float(np.nextafter(borde, np.inf)), True)):
            with self.subTest(s_ganador=s_a):
                uv = {("ambiental", c, lugar, "uv/mse_h"): {"A": s_a, "B": 2.0, "AB": 3.0, "C": 4.0}[c]
                      for c in e0 for lugar in V.LUGARES}
                r = V._avisos_sinca(uv, {"ambiental/u_v": "A"}, {"ambiental/u_v": e0})["ambiental/u_v"]
                self.assertEqual((r["celda"], r["punto"], r["aviso"]), (aviso, aviso, aviso))
                # S_par: con B el menor en T y en HR (2,0), S_par(B) = 1 y S_par(A) = ½ (s_a/2 + s_a/2) = s_a/2
                tt = {}
                for c in e0:
                    for lugar in V.LUGARES:
                        tt[("ambiental", c, lugar, "T/mse_h")] = {"A": s_a, "B": 2.0, "AB": 2.5, "C": 3.0}[c]
                        tt[("ambiental", c, lugar, "HR/mse_h")] = {"A": s_a, "B": 2.0, "AB": 2.5, "C": 3.0}[c]
                r = V._avisos_sinca(tt, {"ambiental/T_Td": "A"}, {"ambiental/T_Td": e0})["ambiental/T_Td"]
                self.assertEqual((r["celda"], r["punto"], r["aviso"]), (aviso, aviso, aviso))
                solo_punto = {**uv, **{("ambiental", c, "celda", "uv/mse_h"): 2.0 + e0.index(c) for c in e0}}
                r = V._avisos_sinca(solo_punto, {"ambiental/u_v": "A"}, {"ambiental/u_v": e0})["ambiental/u_v"]
                self.assertEqual((r["celda"], r["punto"], r["aviso"]), (False, aviso, aviso))

    def test_sinca_rapidez_es_la_media_de_las_rapideces(self):
        """VAL-19: la rapidez del producto frente a WSPD es la media de las rapideces en u − 1 y u, no la rapidez del
        vector medio; «uv» sí compara el vector medio."""
        h = np.array([10, 11], dtype=np.int64)
        prod = {"h": np.arange(8, 13, dtype=np.int64), "T": np.zeros(5), "HR": np.zeros(5),
                "u": np.array([0.0, 3.0, 0.0, 1.0, -1.0]), "v": np.array([0.0, 0.0, 4.0, 0.0, 0.0])}
        obs = {"WSPD": (h, np.array([2.0, 2.0])), "WDIR": (h, np.array([180.0, 180.0]))}
        h0, pred, _ = V._par_sinca(obs, prod, "rapidez")
        np.testing.assert_array_equal(h0, h - 1)
        np.testing.assert_allclose(pred, [3.5, 2.5], rtol=0, atol=1e-15)      # (3 + 4)/2 y (4 + 1)/2
        _, pred_uv, _ = V._par_sinca(obs, prod, "uv")
        np.testing.assert_allclose(pred_uv, [[1.5, 2.0], [0.5, 2.0]], rtol=0, atol=1e-15)

    def test_sinca_cronico_con_y_sin_macrozonas(self):
        """§5.6 en lo crónico (VAL-19, VAL-5): con ``macrozonas`` el nivel neto resta la media de macrozona × año de la
        red; «insular» (D16) no es macrozona y se cuenta aparte; un nombre ajeno o una estación sin macrozona dada es
        un error; sin ``macrozonas`` no se calcula y se declara. El aviso del 15 % de lo crónico usa ese S."""
        h = np.arange(_h_de("2015-01-01T03"), _h_de("2018-01-01T04"), dtype=np.int64)
        b = {"S01": 0.2, "S02": 0.6, "S03": 1.0}
        k = {"A": 1.2, "B": 1.5, "AB": 1.0, "C_est": 1.3}
        series, producto = _sinca_sintetica(h, tuple(b), ("TEMP",), "cronico",
                                            lambda cand, est, hh: {"T": k[cand] * b[est]})
        macro = {"S01": "centro", "S02": "centro", "S03": "insular"}
        e0 = {"cronico/T_Td": tuple(k)}
        tpi = dict.fromkeys(b, 0.0)
        r = V.validacion_sinca(series, producto, producto, tpi, self.U, ganadores={"cronico/T_Td": "AB"}, e0=e0,
                               macrozonas=macro)
        met = r["metricas"]
        self.assertEqual(r["declaraciones"]["cronico_sin_macrozona_estaciones"], 1)
        for cand in k:
            for lugar in V.LUGARES:
                fila = met[(met.candidato == cand) & (met.variable == "T") & (met.metrica == "mse_anual_neto")
                           & (met.estrato == "red") & (met.lugar == lugar)]
                # ε = k·b; centro: media 0,4·k; neto de S01 y S02 = (0,2·k)²; S = 0,2·k sobre 2 estaciones
                self.assertAlmostEqual(float(fila.valor.iloc[0]), 0.2 * k[cand], places=9)
                self.assertEqual(int(fila.n_estaciones.iloc[0]), 2)
        self.assertEqual(r["aviso"]["cronico/T_Td"]["aviso"], False)
        r = V.validacion_sinca(series, producto, producto, tpi, self.U, ganadores={"cronico/T_Td": "A"}, e0=e0,
                               macrozonas=macro)
        self.assertEqual(r["aviso"]["cronico/T_Td"], {"celda": True, "punto": True, "aviso": True, "ganador": "A"})
        sin = V.validacion_sinca(series, producto, producto, tpi, self.U, ganadores={"cronico/T_Td": "A"}, e0=e0)
        self.assertEqual(sin["declaraciones"]["cronico_sin_macrozonas"], 1)
        neto = sin["metricas"][sin["metricas"].metrica == "mse_anual_neto"]
        self.assertTrue(neto.valor.isna().all() and (neto.n_estaciones == 0).all())
        self.assertIsNone(sin["aviso"]["cronico/T_Td"]["aviso"])
        for malas in ({**macro, "S03": "atlantida"}, {"S01": "centro", "S02": "centro"}):
            with self.subTest(macrozonas=malas):
                with self.assertRaises(ValueError):
                    V.validacion_sinca(series, producto, producto, tpi, self.U, macrozonas=malas)

    def test_sinca_agudo_aviso(self):
        """§5.6 en lo agudo (VAL-20): el S del grupo en la red es S_par de la desviación dentro del estrato de
        ``temp_media`` y ``hr_media``; un error que varía en la semana, proporcional a k del candidato, da S_par = k/k_mín:
        aviso con 1,16 y no con 1,14."""
        h = np.arange(_h_de("2019-01-01T03"), _h_de("2019-04-03T03"), dtype=np.int64)
        estaciones = ("S01", "S02", "S03")
        semana = 2 * np.pi / (24 * 7)
        for k_a, aviso in ((1.16, True), (1.14, False)):
            with self.subTest(k_a=k_a):
                k = {"A": k_a, "B": 1.3, "AB": 1.0, "C": 1.5}
                series, producto = _sinca_sintetica(
                    h, estaciones, ("TEMP", "RHUM"), "agudo",
                    lambda cand, est, hh: {"T": k[cand] * np.sin(semana * hh), "HR": 10 * k[cand] * np.sin(semana * hh)})
                r = V.validacion_sinca(series, producto, producto, dict.fromkeys(estaciones, 0.0), self.U,
                                       ganadores={"agudo/T_Td": "A"}, e0={"agudo/T_Td": tuple(k)})
                self.assertEqual(r["aviso"]["agudo/T_Td"], {"celda": aviso, "punto": aviso, "aviso": aviso,
                                                            "ganador": "A"})
                met = r["metricas"]
                s = {c: float(met[(met.candidato == c) & (met.variable == "temp_media") & (met.metrica == "mse_estrato")
                                  & (met.estrato == "red") & (met.lugar == "celda")].valor.iloc[0]) for c in k}
                self.assertGreater(s["AB"], 0)
                self.assertAlmostEqual(s["A"] / s["AB"], k_a, places=9)

    def test_sinca_pares_hora_de_comienzo_y_calma(self):
        """VAL-19: el par SINCA de la hora u va con la hora de comienzo u − 1 (el día civil y la celda del ciclo), con
        la media del producto en u − 1 y u; con WSPD = 0 el vector es (0, 0) aunque falte WDIR; WDIR 90° es viento del
        este (u < 0)."""
        h = np.array([10, 11, 12], dtype=np.int64)
        prod = {"h": np.arange(8, 14, dtype=np.int64), "T": np.arange(8, 14, dtype=np.float64),
                "HR": np.full(6, 50.0), "u": np.ones(6), "v": np.zeros(6)}
        h0, pred, obs = V._par_sinca({"TEMP": (h, np.array([1.0, 2.0, 3.0]))}, prod, "T")
        np.testing.assert_array_equal(h0, h - 1)
        np.testing.assert_array_equal(pred, [9.5, 10.5, 11.5])
        obs_v = {"WSPD": (h, np.array([0.0, 2.0, 2.0])), "WDIR": (h[2:], np.array([90.0]))}
        h0, pred, obs = V._par_sinca(obs_v, prod, "uv")
        np.testing.assert_array_equal(h0, h - 1)
        np.testing.assert_array_equal(obs[0], [0.0, 0.0])
        self.assertTrue(np.isnan(obs[1]).all())                    # rapidez > 0 sin dirección: sin par
        np.testing.assert_allclose(obs[2], [-2.0, 0.0], atol=1e-12)
        np.testing.assert_array_equal(pred[0], [1.0, 0.0])
        self.assertIsNone(V._par_sinca({"TEMP": (h, h * 1.0)}, None, "T"))
        self.assertIsNone(V._par_sinca({"RHUM": (h, h * 1.0)}, prod, "T"))

    def test_sinca_con_las_series_de_sinca_meteo(self):
        """A12 revisado: la tabla de ``sinca_meteo.series_horarias`` entra tal cual (D47-D50 ya aplicadas), y lo que no
        cumple sus consecuencias se rechaza."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = S.sinca_sintetico(tmp, desde="2019-01-01", hasta="2019-04-15")
            m = SM.leer_manifiestos(raiz, S.huellas_sinca(raiz))
            e = SM.elegir_series(m, self.U)
            politica = {"sinca": {k: (dict(v) if isinstance(v, type(SM.POLITICA_SINCA)) else v)
                                  for k, v in SM.POLITICA_SINCA.items()}}
            veredictos = {"sha256": "a" * 64, "huella_contenido": "b" * 64, "convencion": None, "hora_civil": ()}
            series = SM.series_horarias(raiz, e, politica, self.U, veredictos=veredictos)
        estaciones = sorted(set(series.estacion))
        h = np.arange(series.h.min() - 1, series.h.max() + 1, dtype=np.int32)
        producto = {}
        for cand, sesgo in (("A", 0.1), ("B", 0.2), ("AB", 0.3), ("C", 0.4)):
            producto[("ambiental", cand)] = pd.DataFrame({
                "estacion": np.repeat(estaciones, h.size), "h": np.tile(h, len(estaciones)),
                "T": 18.0 + sesgo, "HR": 60.0, "u": 1.0, "v": 1.0})
        r = V.validacion_sinca(series, producto, producto, {e: 0.0 for e in estaciones}, self.U,
                               ganadores={"ambiental/T_Td": "A"}, e0={"ambiental/T_Td": ("A", "B", "AB", "C")})
        met = r["metricas"]
        t = met[(met.variable == "T") & (met.metrica == "mse_h") & (met.estrato == "red") & (met.lugar == "celda")]
        self.assertEqual(set(t.n_estaciones), {len(estaciones)})
        self.assertEqual(r["aviso"]["ambiental/T_Td"]["aviso"], False)
        dos = series.copy()
        dos.loc[dos.index[0], "serie"] = "otra/serie.csv"
        with self.assertRaises(ValueError):
            V.validacion_sinca(dos, producto, producto, {e: 0.0 for e in estaciones}, self.U)
        repetida = pd.concat([series, series.iloc[:1]], ignore_index=True)
        with self.assertRaises(ValueError):
            V.validacion_sinca(repetida, producto, producto, {e: 0.0 for e in estaciones}, self.U)
        with self.assertRaises(ValueError):
            V.validacion_sinca(series, producto, producto, {}, self.U)


def _verdades(h, k: int) -> dict:
    return {"T": _verdad_t(h) + k, "HR": 60 + 15 * np.cos(2 * np.pi * h / 24),
            "u": 2 + np.cos(2 * np.pi * (h - 16) / 24), "v": -1 + 0.5 * np.sin(2 * np.pi * h / 24)}


def _sinca_sintetica(h, estaciones, variables, uso, delta) -> tuple[pd.DataFrame, dict]:
    """Series SINCA (``ESQUEMA_SINCA_HORA``, todas válidas) de las ``variables`` y el producto de cada candidato del
    uso: la observación de u es la media exacta de la verdad en u − 1 y u, y el producto es la verdad más
    ``delta(candidato, estación, h)`` ({columna: sumando})."""
    filas = []
    for k, est in enumerate(estaciones):
        verdad = _verdades(h, k)
        media = {n: (x[:-1] + x[1:]) / 2 for n, x in verdad.items()}
        hu = h[1:]
        valores = {"TEMP": media["T"], "RHUM": media["HR"], "WSPD": np.hypot(media["u"], media["v"]),
                   "WDIR": np.mod(np.degrees(np.arctan2(-media["u"], -media["v"])), 360)}
        for var in variables:
            filas.append(pd.DataFrame({"estacion": est, "h": hu.astype(np.int32), "variable": var,
                                       "valor": valores[var], "valido": True, "serie": f"{var}/{est}.csv"}))
    series = pd.concat(filas, ignore_index=True).astype(dict(tipos.ESQUEMA_SINCA_HORA))
    producto = {}
    for cand in V.CANDIDATOS_USO[Uso(uso)]:
        partes = []
        for k, est in enumerate(estaciones):
            verdad = _verdades(h, k)
            for col, d in delta(cand, est, h).items():
                verdad[col] = verdad[col] + d
            partes.append(pd.DataFrame({"estacion": est, "h": h.astype(np.int32), **verdad}))
        producto[(uso, cand)] = pd.concat(partes, ignore_index=True)
    return series, producto


def _caso_sinca(U, sesgos: dict, *, ganador: str, sesgos_punto: dict | None = None) -> dict:
    """Tres estaciones SINCA con ≈ 2.200 horas; la observación de u es la media exacta de la verdad en u − 1 y u; el
    producto de cada candidato es la verdad más su sesgo (T en K, HR en 10 × sesgo puntos, el viento en (s, s))."""
    h = np.arange(_h_de("2019-01-01T04"), _h_de("2019-04-03T04"), dtype=np.int64)
    estaciones = ("S01", "S02", "S03")
    filas = []
    for k, est in enumerate(estaciones):
        t = _verdad_t(h) + k
        hr = 60 + 15 * np.cos(2 * np.pi * h / 24)
        u = 2 + np.cos(2 * np.pi * (h - 16) / 24)
        v = -1 + 0.5 * np.sin(2 * np.pi * h / 24)
        media = {n: (x[:-1] + x[1:]) / 2 for n, x in (("T", t), ("HR", hr), ("u", u), ("v", v))}
        hu = h[1:]
        ff = np.hypot(media["u"], media["v"])
        dd = np.mod(np.degrees(np.arctan2(-media["u"], -media["v"])), 360)
        for var, val in (("TEMP", media["T"]), ("RHUM", media["HR"]), ("WSPD", ff), ("WDIR", dd)):
            valido = np.ones(hu.size, dtype=bool)
            valor = val.copy()
            valido[5::97] = False                                   # filas inválidas con un valor absurdo
            valor[5::97] = 999.0 if var != "WDIR" else 400.0
            filas.append(pd.DataFrame({"estacion": est, "h": hu.astype(np.int32), "variable": var, "valor": valor,
                                       "valido": valido, "serie": f"{var}/{est}.csv"}))
    series = pd.concat(filas, ignore_index=True).astype(dict(tipos.ESQUEMA_SINCA_HORA))

    def productos(ses):
        salida = {}
        for cand, s in ses.items():
            partes = []
            for k, est in enumerate(estaciones):
                partes.append(pd.DataFrame({
                    "estacion": est, "h": h.astype(np.int32), "T": _verdad_t(h) + k + s,
                    "HR": 60 + 15 * np.cos(2 * np.pi * h / 24) + 10 * s,
                    "u": 2 + np.cos(2 * np.pi * (h - 16) / 24) + s, "v": -1 + 0.5 * np.sin(2 * np.pi * h / 24) + s}))
            salida[("ambiental", cand)] = pd.concat(partes, ignore_index=True)
        return salida

    celda = productos(sesgos)
    punto = productos(sesgos_punto or sesgos)
    e0 = ("A", "B", "AB", "C")
    return V.validacion_sinca(series, celda, punto, {"S01": -10.0, "S02": 0.0, "S03": 10.0}, U,
                              ganadores={"ambiental/T_Td": ganador, "ambiental/u_v": ganador,
                                         "ambiental/p": ganador},
                              e0={"ambiental/T_Td": e0, "ambiental/u_v": e0, "ambiental/p": e0})


if __name__ == "__main__":
    unittest.main()
