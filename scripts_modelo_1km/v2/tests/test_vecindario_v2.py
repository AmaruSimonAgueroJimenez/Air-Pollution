"""Pruebas de ``vecindario_v2``: núcleo, descuento exacto, guardas numéricas, pliegues, registro y la v1 real.

Los casos sintéticos ponen las estaciones sobre un meridiano, donde la distancia haversine es exacta en
kilómetros, y comparan el descuento con la réplica literal del cálculo de la v1 (``obs_vecinas_para`` y
``ajuste_por_red`` sin el atajo). La red tiene gemelos a 100 m, una pareja aislada a 800 km de todo (para que lo
excluido pese casi todo y actúe la guarda de cancelación) y una estación a 560 km de su vecina más cercana (para
el umbral de 1e-6). Las pruebas con datos reales (panel v1 y manifiesto) se saltan si faltan y no escriben nada.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import vecindario_v2 as vv  # noqa: E402

KM_POR_GRADO = vv.RADIO_TIERRA_KM * np.pi / 180.0
LAT0, LON0 = -20.0, -70.0
TOL = 1e-10                         # muy por debajo del 1e-9 de la pieza; el real queda en ~1e-13

# (código, km al norte de LAT0 sobre el meridiano LON0)
#   A1–A2 gemelos a 0,1 km; B a 30 km; C a 100 km; D a 250 km; E a 400 km;
#   F–F2 gemelos a 0,5 km y a 800 km de E (aislados); G a 560 km de F (umbral de 1e-6).
KM = {"A1": 0.0, "A2": 0.1, "B": 30.0, "C": 100.0, "D": 250.0, "E": 400.0, "F": 1200.0, "F2": 1200.5, "G": 1760.0}


def lat_a(km: float) -> float:
    return LAT0 + km / KM_POR_GRADO


def coordenadas() -> dict:
    return {s: (lat_a(km), LON0) for s, km in KM.items()}


def tabla_sintetica(semilla: int = 7, horas: int = 300, p: float = 0.7) -> pd.DataFrame:
    """Una fila por (estación, hora) observada, con ceros y algunas horas diseñadas a mano."""
    rng = np.random.default_rng(semilla)
    ts0 = pd.Timestamp("2020-01-01 04:00")
    nombres = list(KM)
    filas = []
    for h in range(horas):
        for s in nombres:
            if rng.random() < p:
                v = 0.0 if rng.random() < 0.05 else float(np.round(rng.gamma(2.0, 15.0), 3))
                filas.append((s, ts0 + pd.Timedelta(hours=h), v))
    t = pd.DataFrame(filas, columns=["estacion", "ts_utc", "obs"])
    # hora H1: sólo A1 y A2 midieron (sin A2, A1 se queda sin vecinas)
    # hora H2: A1 fila, A2/B excluibles con valor, C y D con cero (sin A2 ni B, obs_vec de A1 debe ser 0 exacto)
    # hora H3: G con F y F2 (dos vecinas a ~560 km: Σw ≈ 1,8e-6 > 1e-6); sin F2 queda una (8,8e-7 → NaN)
    extra = []
    for k, (h, presentes) in enumerate(((horas, {"A1": 12.0, "A2": 30.0}),
                                        (horas + 1, {"A1": 9.0, "A2": 41.25, "B": 17.5, "C": 0.0, "D": 0.0}),
                                        (horas + 2, {"G": 5.0, "F": 20.0, "F2": 22.0}))):
        for s, v in presentes.items():
            extra.append((s, ts0 + pd.Timedelta(hours=h), v))
    t = pd.concat([t, pd.DataFrame(extra, columns=t.columns)], ignore_index=True)
    t["anio"] = np.where(t["ts_utc"] < ts0 + pd.Timedelta(hours=150), 2020, 2021).astype("int16")
    return t


def vecindario(t: pd.DataFrame | None = None, **kw) -> vv.Vecindario:
    t = tabla_sintetica() if t is None else t
    return vv.Vecindario("pm25", t["estacion"], t["ts_utc"].to_numpy(), t["obs"].to_numpy(), coordenadas(),
                         anio=t["anio"].to_numpy(), hilos=2, **kw)


def literal(vec: vv.Vecindario, excluidas, filas=None):
    """La réplica literal de la v1 sobre las filas pedidas (todas por omisión), en float64."""
    filas = np.arange(vec.n) if filas is None else np.asarray(filas)
    js = vec.js[filas]
    return vv.recalculo_directo_v1(vec.matriz_O(), vec.lat, vec.lon, vec.estaciones[js],
                                   vec.tiempos[vec.it[filas]].to_numpy(), vec.lat[js], vec.lon[js], excluidas,
                                   precision="float64")


def rel_max(a: np.ndarray, b: np.ndarray) -> float:
    ok = ~(np.isnan(a) | np.isnan(b)) & (b != 0)
    return float((np.abs(a[ok] - b[ok]) / np.abs(b[ok])).max(initial=0.0))


class AyudaComparar(unittest.TestCase):
    def assertIgualALaV1(self, vec, excluidas, rec=None, tol=TOL):
        rec = rec or vec.recalcular(excluidas, precision="float64", registrar=False)
        ov, pw, dist = literal(vec, excluidas)
        self.assertTrue(np.array_equal(np.isnan(rec.obs_vec), np.isnan(ov)), f"NaN distintos con {excluidas}")
        self.assertLessEqual(rel_max(rec.obs_vec, ov), tol, f"obs_vec con {excluidas}")
        self.assertLessEqual(rel_max(rec.peso_vec, pw), tol, f"peso_vec con {excluidas}")
        cero = pw == 0
        self.assertTrue(np.array_equal(rec.peso_vec[cero], pw[cero]), f"peso_vec cero con {excluidas}")
        oc = ov == 0
        self.assertTrue(np.array_equal(rec.obs_vec[oc], ov[oc]), f"obs_vec cero con {excluidas}")
        np.testing.assert_array_equal(rec.dist_est_km, dist)
        return rec


# ---------------------------------------------------------------------------
# Núcleo y geometría
# ---------------------------------------------------------------------------
class NucleoTests(unittest.TestCase):
    def test_nucleo_gaussiano_de_la_v1(self):
        self.assertEqual(vv.nucleo_gaussiano(0.0), 1.0)
        self.assertEqual(vv.nucleo_gaussiano(150.0), np.exp(-1.0))
        self.assertAlmostEqual(float(vv.nucleo_gaussiano(300.0)), np.exp(-4.0), places=15)
        self.assertEqual((vv.H_KM_V1, vv.UMBRAL_PESO_V1, vv.RADIO_TIERRA_KM), (150.0, 1e-6, 6371.0))

    def test_distancias_sobre_el_meridiano(self):
        vec = vecindario()
        i, j = list(vec.estaciones).index("A1"), list(vec.estaciones).index("C")
        self.assertAlmostEqual(vec.D[i, j], 100.0, places=9)
        self.assertTrue(np.array_equal(vec.D, vec.D.T))              # haversine simétrica bit a bit
        self.assertTrue(np.all(np.diag(vec.W0) == 0))                 # la propia no cuenta

    def test_config_traduce_el_nucleo_de_la_v1(self):
        cfg = json.loads((V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8"))
        imp = cfg["vecindario"]["implementacion"]
        self.assertEqual((imp["ancho_km"], imp["umbral_suma_de_pesos"]), (vv.H_KM_V1, vv.UMBRAL_PESO_V1))
        self.assertFalse(cfg["vecindario"]["recalculo"]["atajo_para_conjuntos_de_una_estacion"])
        self.assertEqual(cfg["vecindario"]["recalculo"]["protocolos"], list(vv.PROTOCOLOS_ESPACIALES))


# ---------------------------------------------------------------------------
# Descuento frente a la réplica literal de la v1
# ---------------------------------------------------------------------------
class DescuentoTests(AyudaComparar):
    @classmethod
    def setUpClass(cls):
        cls.t = tabla_sintetica()
        cls.vec = vecindario(cls.t)

    def test_base_igual_a_la_v1(self):
        rec = self.assertIgualALaV1(self.vec, ())
        self.assertEqual(rec.registro["n_excluidas"], 0)
        self.assertEqual(rec.registro["filas_suma_directa"], 0)

    def test_cada_estacion_sola_sin_atajo(self):
        base = self.vec.recalcular((), precision="float64", registrar=False)
        for s in self.vec.estaciones:
            with self.subTest(excluida=s):
                rec = self.assertIgualALaV1(self.vec, [s])
                propia = self.vec.estaciones[self.vec.js] == s
                # las filas de prueba (la propia) ya la excluían: no cambian
                np.testing.assert_array_equal(rec.peso_vec[propia], base.peso_vec[propia])
                # las de entrenamiento pierden su contribución donde midió: sin atajo
                if s in ("A1", "A2", "B"):
                    self.assertTrue((rec.peso_vec[~propia] < base.peso_vec[~propia]).any())

    def test_gemelos_regiones_y_conjuntos_al_azar(self):
        rng = np.random.default_rng(3)
        nombres = list(self.vec.estaciones)
        conjuntos = [["A1", "A2"], ["F", "F2"], ["A1", "A2", "B"], ["B", "C", "D", "E"], ["F2"], ["G", "F"]]
        conjuntos += [sorted(rng.choice(nombres, size=k, replace=False).tolist()) for k in (2, 3, 5, 7, 8) for _ in range(3)]
        for E in conjuntos:
            with self.subTest(excluidas=E):
                self.assertIgualALaV1(self.vec, E)
                d = self.vec.recalcular(E, precision="float64", registrar=False)
                x = self.vec.recalcular(E, metodo="directo", precision="float64", registrar=False)
                self.assertTrue(np.array_equal(np.isnan(d.obs_vec), np.isnan(x.obs_vec)))
                self.assertLessEqual(rel_max(d.obs_vec, x.obs_vec), TOL)
                self.assertLessEqual(rel_max(d.peso_vec, x.peso_vec), TOL)

    def test_guarda_de_cancelacion(self):
        # Sin F2, lo que queda para F pesa ~1e-13 de su total (E está a 800 km): la resta sola perdería dígitos.
        rec = self.assertIgualALaV1(self.vec, ["F2"])
        self.assertGreater(rec.registro["filas_suma_directa"], 0)
        f = self.vec.estaciones[self.vec.js] == "F"
        self.assertTrue(np.all(rec.peso_vec[f] < 1e-6))
        self.assertTrue(np.all(np.isnan(rec.obs_vec[f])))

    def test_sin_la_guarda_la_resta_pierde_digitos(self):
        # Con κ ≈ 0 la guarda no actúa (salvo restos ≤ 0) y la resta sola se aleja del cálculo directo donde lo
        # excluido pesa casi todo; con κ = 1e-3 vuelve a coincidir. Documenta por qué existe la guarda.
        E = ["A1", "A2", "B", "C", "D", "E"]
        ov, pw, _ = literal(self.vec, E)
        sin_guarda = vecindario(self.t, kappa=1e-300).recalcular(E, precision="float64", registrar=False)
        con_guarda = self.vec.recalcular(E, precision="float64", registrar=False)
        self.assertGreater(rel_max(sin_guarda.peso_vec, pw), 1e-6)
        self.assertLessEqual(rel_max(con_guarda.peso_vec, pw), TOL)

    def test_cero_exacto_y_sin_vecinas(self):
        ts0 = pd.Timestamp("2020-01-01 04:00")
        horas = 300
        h1, h2 = ts0 + pd.Timedelta(hours=horas), ts0 + pd.Timedelta(hours=horas + 1)
        fila = lambda s, ts: int(np.flatnonzero((self.vec.estaciones[self.vec.js] == s)  # noqa: E731
                                                & (self.vec.tiempos[self.vec.it] == ts))[0])
        rec = self.vec.recalcular(["A2", "B"], precision="float64", registrar=False)
        self.assertEqual(rec.obs_vec[fila("A1", h2)], 0.0)              # quedan C y D, que midieron 0
        self.assertGreater(rec.peso_vec[fila("A1", h2)], 0.0)
        rec = self.vec.recalcular(["A2"], precision="float64", registrar=False)
        self.assertTrue(np.isnan(rec.obs_vec[fila("A1", h1)]))           # nadie más midió en H1
        self.assertEqual(rec.peso_vec[fila("A1", h1)], 0.0)
        self.assertGreater(rec.registro["filas_sin_vecinas"], 0)

    def test_umbral_de_un_millonesimo(self):
        ts = pd.Timestamp("2020-01-01 04:00") + pd.Timedelta(hours=302)
        g = int(np.flatnonzero((self.vec.estaciones[self.vec.js] == "G") & (self.vec.tiempos[self.vec.it] == ts))[0])
        base = self.vec.recalcular((), precision="float64", registrar=False)
        w_f, w_f2 = vv.nucleo_gaussiano(560.0), vv.nucleo_gaussiano(559.5)
        self.assertAlmostEqual(base.peso_vec[g], w_f + w_f2, delta=1e-15)
        self.assertGreater(base.peso_vec[g], 1e-6)
        self.assertAlmostEqual(base.obs_vec[g], (20.0 * w_f + 22.0 * w_f2) / (w_f + w_f2), places=9)
        sin_f2 = self.vec.recalcular(["F2"], precision="float64", registrar=False)
        self.assertLess(sin_f2.peso_vec[g], 1e-6)                        # una sola vecina a 560 km: 8,8e-7
        self.assertTrue(np.isnan(sin_f2.obs_vec[g]))

    def test_dist_est_km(self):
        base = self.vec.distancias()
        self.assertAlmostEqual(base["A1"], 0.1, places=9)
        self.assertAlmostEqual(base["F"], 0.5, places=9)
        self.assertAlmostEqual(base["G"], 559.5, places=6)
        sin = self.vec.distancias(["A2", "F2"])
        self.assertAlmostEqual(sin["A1"], 30.0, places=9)               # la de prueba: entre las que quedan
        self.assertAlmostEqual(sin["A2"], 0.1, places=9)                # A2 excluida: su más cercana es A1
        self.assertAlmostEqual(sin["G"], 560.0, places=6)
        rec = self.vec.recalcular(["A2", "F2"], registrar=False)
        np.testing.assert_array_equal(rec.dist_est_km, sin.to_numpy()[self.vec.js].astype("float32"))

    def test_una_sola_estacion_que_queda(self):
        resto = [s for s in self.vec.estaciones if s != "C"]
        rec = self.vec.recalcular(resto, registrar=False)
        c = self.vec.estaciones[self.vec.js] == "C"
        self.assertTrue(np.all(np.isinf(rec.dist_est_km[c])))           # como la v1: mínimo de un conjunto vacío
        self.assertEqual(rec.registro["dist_est_km_inf"], ["C"])
        self.assertTrue(np.all(np.isnan(rec.obs_vec[c])))
        with self.assertRaises(ValueError):
            self.vec.recalcular(list(self.vec.estaciones))

    def test_float32_es_el_redondeo_del_float64(self):
        for E in ((), ["A1"], ["F", "F2", "G"]):
            a = self.vec.recalcular(E, registrar=False)
            b = self.vec.recalcular(E, precision="float64", registrar=False)
            for c in vv.VARIABLES:
                self.assertEqual(getattr(a, c).dtype, np.float32)
                np.testing.assert_array_equal(getattr(a, c), getattr(b, c).astype("float32"))


# ---------------------------------------------------------------------------
# Construcción, pliegues y registro
# ---------------------------------------------------------------------------
class ConstruccionTests(unittest.TestCase):
    def test_no_depende_del_orden_de_las_filas(self):
        t = tabla_sintetica()
        perm = np.random.default_rng(11).permutation(len(t))
        a, b = vecindario(t), vecindario(t.iloc[perm].reset_index(drop=True))
        self.assertEqual(list(a.estaciones), list(b.estaciones))
        for E in ((), ["B", "F2"]):
            ra, rb = a.recalcular(E, registrar=False), b.recalcular(E, registrar=False)
            for c in vv.VARIABLES:
                np.testing.assert_array_equal(getattr(ra, c)[perm], getattr(rb, c))

    def test_orden_lexicografico_como_el_pivote(self):
        t = tabla_sintetica()
        vec = vecindario(t)
        O = t.pivot_table(index="ts_utc", columns="estacion", values="obs", aggfunc="mean")
        self.assertEqual(list(vec.estaciones), list(O.columns))
        pd.testing.assert_frame_equal(vec.matriz_O(), O, check_names=False, check_freq=False)

    def test_duplicados_rechazados(self):
        t = tabla_sintetica()
        with self.assertRaises(ValueError):
            vecindario(pd.concat([t, t.iloc[:1]], ignore_index=True))

    def test_obs_nan_cuenta_como_no_medido(self):
        t = tabla_sintetica()
        t.loc[0, "obs"] = np.nan
        vec = vecindario(t)
        self.assertEqual(vec.M.sum(), len(t) - 1)
        s, ts = t.loc[0, "estacion"], t.loc[0, "ts_utc"]
        otras = (t["ts_utc"] == ts) & (t["estacion"] != s)
        ref = vecindario(t[t.index != 0].reset_index(drop=True))
        a = vec.recalcular((), precision="float64", registrar=False)
        b = ref.recalcular((), precision="float64", registrar=False)
        np.testing.assert_allclose(a.obs_vec[1:][otras.to_numpy()[1:]], b.obs_vec[otras.to_numpy()[1:]], rtol=1e-13)
        self.assertTrue(np.isfinite(a.peso_vec[0]))                    # la fila sin valor igual recibe vecindario

    def test_coordenadas_faltantes_o_estacion_ajena(self):
        t = tabla_sintetica()
        c = coordenadas()
        c.pop("G")
        with self.assertRaises(ValueError):
            vv.Vecindario("pm25", t["estacion"], t["ts_utc"].to_numpy(), t["obs"].to_numpy(), c)
        vec = vecindario(t)
        with self.assertRaises(ValueError):
            vec.recalcular(["NO-EXISTE"])


class PliegueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vec = vecindario()

    def test_mascaras_de_un_pliegue_con_entorno(self):
        f = {"k": 3, "grupo": "A1+A2", "estaciones_prueba": ["A1", "A2"], "excluidas": ["A1", "A2", "B"]}
        rec = self.vec.para_pliegue(f, "LBO-10")
        est = self.vec.estaciones[self.vec.js]
        np.testing.assert_array_equal(rec.entrenamiento, ~np.isin(est, ["A1", "A2", "B"]))
        np.testing.assert_array_equal(rec.prueba, np.isin(est, ["A1", "A2"]))
        self.assertFalse((rec.entrenamiento & rec.prueba).any())
        self.assertFalse((rec.entrenamiento | rec.prueba)[est == "B"].any())   # entorno: ni entrena ni se predice
        g = rec.registro
        self.assertEqual((g["protocolo"], g["k"], g["grupo"]), ("LBO-10", 3, "A1+A2"))
        self.assertEqual(g["excluidas"], ["A1", "A2", "B"])
        self.assertEqual(g["filas_entrenamiento"], int(rec.entrenamiento.sum()))
        self.assertEqual(g["filas_prueba"], int(rec.prueba.sum()))

    def test_lpo_usa_la_red_concurrente(self):
        f = {"k": 0, "grupo": "2020–2023", "estaciones_prueba": list(self.vec.estaciones), "excluidas": [],
             "exclusion_temporal": {"anio_desde": 2020, "anio_hasta": 2020}}
        rec = self.vec.para_pliegue(f, "LPO")
        base = self.vec.base(registrar=False)
        np.testing.assert_array_equal(rec.obs_vec, base.obs_vec)
        np.testing.assert_array_equal(rec.prueba, self.vec.anio == 2020)
        np.testing.assert_array_equal(rec.entrenamiento, self.vec.anio != 2020)
        with self.assertRaises(ValueError):
            self.vec.para_pliegue({**f, "excluidas": ["A1"]}, "LPO")

    def test_pliegues_mal_formados(self):
        with self.assertRaises(ValueError):
            self.vec.para_pliegue({"k": 0, "grupo": "x", "estaciones_prueba": ["A1"], "excluidas": ["A2"]}, "LOSO-D")
        with self.assertRaises(ValueError):
            self.vec.para_pliegue({"k": 0, "grupo": "x", "estaciones_prueba": ["A1"], "excluidas": ["A1"]}, "OTRO")

    def test_asignar_y_columnas(self):
        rec = self.vec.recalcular(["B"], registrar=False)
        feats = ["hora_local", "obs_vec", "peso_vec", "x", "dist_est_km"]
        filas = np.array([5, 0, 17])
        X = np.zeros((3, len(feats)), dtype="float32")
        rec.asignar(X, feats, filas=filas)
        np.testing.assert_array_equal(X[:, [1, 2, 4]], rec.columnas(filas))
        self.assertTrue(np.all(X[:, [0, 3]] == 0))


class RegistroTests(unittest.TestCase):
    def test_registro_huellas_y_determinismo(self):
        vec = vecindario()
        a = vec.recalcular(["C", "A2"], contexto={"protocolo": "LRO", "k": 1, "grupo": "x"})
        b = vec.recalcular(["A2", "C"])
        vec.recalcular(["C"], registrar=False)
        self.assertEqual(len(vec.registro), 2)
        self.assertEqual(a.registro["excluidas"], ["A2", "C"])
        self.assertEqual(a.registro["sha256"], b.registro["sha256"])
        self.assertEqual(a.registro["sha256"]["obs_vec"], hashlib.sha256(a.obs_vec.tobytes()).hexdigest())
        for clave in ("utc", "metodo", "n_excluidas", "filas", "filas_con_descuento", "filas_suma_directa",
                      "filas_sin_vecinas", "obs_vec_nan", "vecindario", "segundos"):
            self.assertIn(clave, a.registro)
        self.assertEqual(vec.huella()["huella"], vecindario().huella()["huella"])
        t = tabla_sintetica()
        t.loc[3, "obs"] += 1.0
        self.assertNotEqual(vecindario(t).huella()["huella"], vec.huella()["huella"])

    def test_publicar_registro_con_candado_y_sin_rutas_absolutas(self):
        with tempfile.TemporaryDirectory(prefix="vecindario-v2-") as tmp:
            base = Path(tmp).resolve()
            scripts = base / "repo" / "scripts_modelo_1km" / "v2"
            scripts.mkdir(parents=True)
            (base / "v1").mkdir()
            (base / "datos").mkdir()
            r = rv.RutasV2(raiz_v2=base / "v2", raiz_v1=base / "v1", datos=base / "datos", repo=base / "repo",
                           scripts_v2=scripts)
            vec = vecindario()
            vec.recalcular(["A1"])
            destino = r.raiz_v2 / "vecindario" / "registro.json"
            sha = vec.publicar_registro(destino, r)
            texto = destino.read_text(encoding="utf-8")
            self.assertEqual(sha, hashlib.sha256(texto.encode("utf-8")).hexdigest())
            doc = json.loads(texto)
            self.assertEqual(doc["schema"], vv.SCHEMA_REGISTRO)
            self.assertEqual(len(doc["recalculos"]), 1)
            for clave in ("git", "codigo", "insumos", "bibliotecas", "hilos", "semillas", "parametros"):
                self.assertIn(clave, doc["traza"])
            self.assertNotIn(str(base), texto)
            with self.assertRaises(rv.EscrituraNoPermitida):
                vec.publicar_registro(base / "fuera.json", r)


# ---------------------------------------------------------------------------
# Datos reales (sólo lectura)
# ---------------------------------------------------------------------------
R = rv.RutasV2.desde_entorno()
MANIFIESTO = rv.leer_json(R.manifiesto_pliegues) if R.manifiesto_pliegues.exists() else None
HAY_REAL = MANIFIESTO is not None and all(R.panel(p).exists() for p in ("pm25", "no2"))


@unittest.skipUnless(HAY_REAL, "faltan el panel v1 o el manifiesto de pliegues")
class PanelRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pyarrow.parquet as pq

        cls.vec, cls.panel = {}, {}
        for pol in ("pm25", "no2"):
            cls.vec[pol] = vv.Vecindario.desde_panel(pol, R, manifiesto=MANIFIESTO, hilos=4)
            cls.panel[pol] = pq.read_table(R.panel(pol), columns=list(vv.VARIABLES)).to_pandas()

    def test_base_reproduce_las_columnas_del_panel(self):
        for pol in ("pm25", "no2"):
            rec = self.vec[pol].base(registrar=False)
            p = self.panel[pol]
            with self.subTest(pol=pol):
                np.testing.assert_array_equal(rec.peso_vec, p["peso_vec"].to_numpy())
                np.testing.assert_array_equal(rec.dist_est_km, p["dist_est_km"].to_numpy())
                a, b = rec.obs_vec, p["obs_vec"].to_numpy()
                self.assertTrue(np.array_equal(np.isnan(a), np.isnan(b)))
                ok = ~np.isnan(a)
                ulp = np.abs(a[ok].view(np.int32).astype(np.int64) - b[ok].view(np.int32).astype(np.int64))
                self.assertLessEqual(int(ulp.max()), 1)                 # cota del redondeo de obs a float32

    def test_pliegues_reales_contra_la_v1_literal(self):
        for pol, prot, marca in (("pm25", "LOSO-D", "309"), ("pm25", "LRO", "RXI"), ("no2", "LBO-10", "503")):
            vec = self.vec[pol]
            pl = MANIFIESTO["contaminantes"][pol]["protocolos"][prot]["pliegues"]
            f = next(x for x in pl if marca in x["estaciones_prueba"] or x["grupo"] == marca)
            rec = vec.para_pliegue(f, prot, precision="float64", registrar=False)
            rng = np.random.default_rng([42, f["k"]])
            filas = np.unique(np.concatenate([rng.choice(np.flatnonzero(rec.prueba), 1500),
                                              rng.choice(np.flatnonzero(rec.entrenamiento), 1500)]))
            ov, pw, dist = literal(vec, f["excluidas"], filas)
            with self.subTest(pol=pol, prot=prot, grupo=f["grupo"]):
                self.assertTrue(np.array_equal(np.isnan(rec.obs_vec[filas]), np.isnan(ov)))
                self.assertLessEqual(rel_max(rec.obs_vec[filas], ov), 1e-9)
                self.assertLessEqual(rel_max(rec.peso_vec[filas], pw), 1e-9)
                np.testing.assert_array_equal(rec.dist_est_km[filas], dist)

    def test_registro_publicado_coincide(self):
        for pol in ("pm25", "no2"):
            ruta = R.raiz_v2 / "vecindario" / f"registro_recalculos_{pol}.json"
            if not ruta.exists():
                self.skipTest(f"todavía no hay registro publicado en {ruta.name}")
            doc = json.loads(ruta.read_text(encoding="utf-8"))
            with self.subTest(pol=pol):
                self.assertEqual(doc["vecindario"]["huella"], self.vec[pol].huella()["huella"])
                previo = next(g for g in doc["recalculos"] if g.get("protocolo") == "LOSO-D" and g.get("k") == 0)
                f = MANIFIESTO["contaminantes"][pol]["protocolos"]["LOSO-D"]["pliegues"][0]
                rec = self.vec[pol].para_pliegue(f, "LOSO-D", registrar=False)
                self.assertEqual(rec.registro["sha256"], previo["sha256"])


if __name__ == "__main__":
    unittest.main()
