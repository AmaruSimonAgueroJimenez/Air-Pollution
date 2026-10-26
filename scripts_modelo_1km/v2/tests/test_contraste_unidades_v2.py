"""Pruebas de ``contraste_unidades_v2`` (R6): una serie en ppb, una en µg/m³N y una indeterminada, con CAMS sintético.

También comprueba, si el programa de la primera corrida está a mano (repositorio de salud), que las constantes y la
función de decisión son las mismas: se extraen por AST, sin ejecutar el programa. Sin red ni datos.
"""
from __future__ import annotations

import ast
import hashlib
import math
import os
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2 / "tests"))
import contraste_unidades_v2 as cu  # noqa: E402

PROGRAMA = Path(os.environ.get(
    "AIR_POLLUTION_CONTRASTE_PROGRAMA",
    V2.parents[2] / "Air-Pollution-Health-Chile" / "auditoria" / "20261024" / "sinca_al_modelo" /
    "contraste_unidades_cams.py"))
LAT0, LON0 = -33.0, -70.6


def cams_sintetico(dias: int = 400, pixeles: int = 3, semilla: int = 1):
    rng = np.random.default_rng(semilla)
    t = pd.date_range("2020-01-01", periods=dias * 8, freq="3h")
    base = 20 + 8 * np.sin(np.arange(len(t)) * 2 * np.pi / 8)[:, None] + rng.normal(0, 2, (len(t), pixeles))
    return t, np.clip(base, 1, None)


def serie_sobre(t: pd.DatetimeIndex, cams_col: np.ndarray, factor: float, semilla: int, horas: int | None = None):
    """Serie local (etiqueta = inicio UTC − 3 h) cuyo nivel es ``factor`` × CAMS, con ruido."""
    rng = np.random.default_rng(semilla)
    v = factor * cams_col * rng.lognormal(0, 0.15, len(cams_col))
    etiquetas = t - pd.Timedelta(hours=3)
    if horas is not None:
        etiquetas, v = etiquetas[:horas], v[:horas]
    return cu.preparar_serie(etiquetas, v)


class ContrasteTests(unittest.TestCase):
    def setUp(self):
        self.t, self.c = cams_sintetico()
        self.plat = np.array([LAT0, LAT0 - 1.0, LAT0 - 2.0])
        self.plon = np.array([LON0, LON0, LON0])
        rng = np.random.default_rng(5)
        series, obs = [], {}
        # Referencia de red: 8 series O3 en ppb con razón ≈ 0,5 (dispersión pequeña, como O3).
        for k in range(8):
            p = k % 3
            series.append({"estacion": f"R{k}", "gas": "o3", "grupo": "actual", "rotulo": "ppb",
                           "lat": float(self.plat[p]) + 0.01, "lon": LON0, "nombre": "", "region": ""})
            obs[len(series) - 1] = serie_sobre(self.t, self.c[:, p], 0.5 * rng.lognormal(0, 0.1), 100 + k)
        f_ug = cu.CANDIDATOS["o3"]["µg/m³N"]
        casos = [("UG", "µg/m³N", 0.5 * f_ug, None),        # rotulada µg/m³N y en µg/m³N: confirmada
                 ("PPB", "µg/m³N", 0.5, None),             # rotulada µg/m³N pero en ppb: contradicha
                 ("MEDIO", "µg/m³N", 0.5 * math.sqrt(f_ug), None),   # a mitad de camino: indeterminada
                 ("SIN", "(sin unidad)", 0.5, None),       # sin unidad, en ppb: entra en ppb
                 ("POCAS", "µg/m³N", 0.5 * f_ug, 300)]      # menos de 500 pares: indeterminada
        for est, rot, fac, horas in casos:
            series.append({"estacion": est, "gas": "o3", "grupo": "nueva", "rotulo": rot, "lat": LAT0, "lon": LON0,
                           "nombre": "", "region": ""})
            obs[len(series) - 1] = serie_sobre(self.t, self.c[:, 0], fac, 7, horas)
        series.append({"estacion": "LEJOS", "gas": "o3", "grupo": "nueva", "rotulo": "µg/m³N", "lat": 0.0,
                       "lon": 0.0, "nombre": "", "region": ""})
        obs[len(series) - 1] = serie_sobre(self.t, self.c[:, 0], 0.5, 8)
        self.series, self.obs = series, obs

    def correr(self):
        usados = cu.asignar_pixeles(self.series, self.plat, self.plon)
        col = {p: j for j, p in enumerate(usados)}
        cams = {"o3": self.c[:, usados]}
        return cu.contrastar(self.series, self.obs, self.t, cams, col)

    def test_decisiones(self):
        tabla, refs = self.correr()
        d = tabla.set_index("estacion")
        self.assertEqual(d.loc["UG", "unidad_que_indica"], "µg/m³N")
        self.assertEqual(d.loc["UG", "decision"], "rótulo confirmado: convertir a ppb a 25 °C")
        self.assertEqual(d.loc["PPB", "unidad_que_indica"], "ppb")
        self.assertEqual(d.loc["PPB", "decision"], "rótulo contradicho: los valores vienen en ppb")
        self.assertEqual(d.loc["MEDIO", "unidad_que_indica"], "indeterminada")
        self.assertEqual(d.loc["SIN", "decision"], "entra en ppb")
        self.assertEqual(d.loc["POCAS", "unidad_que_indica"], "indeterminada")
        self.assertIn("menos de 500 pares", d.loc["POCAS", "estadistico"])
        self.assertIn("sin coordenadas", d.loc["LEJOS", "estadistico"])
        self.assertTrue(d.loc["R0", "decision"].startswith("referencia"))
        self.assertEqual(refs["o3"]["n"], 8)
        self.assertEqual(list(tabla.columns), cu.COLUMNAS)

    def test_la_regla_de_unidades_lee_la_tabla(self):
        import unidades_v2 as uv
        tabla, _ = self.correr()
        d = tabla.set_index("estacion")
        self.assertAlmostEqual(uv.decidir_unidad("o3", "µg/m³N", d.loc["UG", "unidad_que_indica"])["factor"],
                               uv.factor_a_ppb("o3"))
        self.assertEqual(uv.decidir_unidad("o3", "µg/m³N", d.loc["PPB", "unidad_que_indica"])["factor"], 1.0)
        self.assertTrue(uv.decidir_unidad("o3", "µg/m³N", d.loc["MEDIO", "unidad_que_indica"])["entra"])   # I

    def test_dispersion_grande_no_decide(self):
        """Con una referencia que varía un factor ≈ 3 entre estaciones (como NO2), el factor 1,88 no se distingue."""
        rng = np.random.default_rng(9)
        series, obs = [], {}
        for k in range(12):
            series.append({"estacion": f"N{k}", "gas": "no2", "grupo": "actual", "rotulo": "ppb", "lat": LAT0,
                           "lon": LON0})
            obs[k] = serie_sobre(self.t, self.c[:, 0], 1.7 * math.exp(rng.normal(0, 1.1)), 200 + k)
        series.append({"estacion": "X", "gas": "no2", "grupo": "nueva", "rotulo": "µg/m³N", "lat": LAT0, "lon": LON0})
        obs[12] = serie_sobre(self.t, self.c[:, 0], 1.7 * cu.CANDIDATOS["no2"]["µg/m³N"], 300)
        usados = cu.asignar_pixeles(series, self.plat, self.plon)
        tabla, _ = cu.contrastar(series, obs, self.t, {"no2": self.c[:, usados]}, {p: j for j, p in enumerate(usados)})
        self.assertEqual(tabla.set_index("estacion").loc["X", "unidad_que_indica"], "indeterminada")

    def test_cambios_entre_corridas(self):
        a = pd.DataFrame({"estacion": ["1", "2", "3"], "contaminante": ["o3", "o3", "so2"],
                          "unidad_que_indica": ["ppb", "indeterminada", "indeterminada"]})
        b = pd.DataFrame({"estacion": ["1", "2"], "contaminante": ["o3", "o3"],
                          "unidad_que_indica": ["ppb", "µg/m³N"]})
        self.assertEqual(cu.cambios_frente_a(a, b),
                         [{"estacion": "2", "contaminante": "o3", "primera": "indeterminada", "segunda": "µg/m³N"}])

    def test_emparejamiento_mas_tres_horas(self):
        s = cu.preparar_serie(pd.to_datetime(["2020-01-01 00:00", "2020-01-01 00:00", "2020-01-01 01:00"]),
                              [1.0, 2.0, -1.0])
        self.assertEqual(list(s.index), [pd.Timestamp("2020-01-01 03:00")])
        self.assertEqual(float(s.iloc[0]), 1.0)


class MismoProgramaTests(unittest.TestCase):
    """Constantes y decisión iguales a las del programa de la primera corrida (extraídas por AST), salvo la masa molar
    del O3: T12 (corrección, [delegada]) la fija en 47,998 g/mol, la literal de R6, también en el contraste."""

    def setUp(self):
        if not PROGRAMA.exists():
            self.skipTest("sin el programa de la primera corrida (repositorio de salud)")
        fuente = PROGRAMA.read_text(encoding="utf-8")
        if hashlib.sha256(fuente.encode("utf-8")).hexdigest() != cu.PROGRAMA_ORIGINAL["sha256"]:
            self.fail("el programa de la primera corrida no tiene la huella citada")
        self.arbol = ast.parse(fuente)

    def constante(self, nombre, M=None):
        """La constante ``nombre`` del programa original; con ``M``, calculada con esas masas molares en lugar de las
        suyas (los CANDIDATOS del original con la M de T12)."""
        espacio = {"math": math, "np": np}
        for nodo in self.arbol.body:
            if isinstance(nodo, ast.Assign) and any(isinstance(t, ast.Name) and t.id in (
                    "M", "M_AIRE", "VM25", "CANDIDATOS", "REF", "MIN_PARES", "LR_MIN", "Z_MAX", "DIST_VECINA_KM",
                    "GASES") for t in nodo.targets):
                exec(compile(ast.Module(body=[nodo], type_ignores=[]), "original", "exec"), espacio)
                if M is not None and any(isinstance(t, ast.Name) and t.id == "M" for t in nodo.targets):
                    espacio["M"] = dict(M)
            elif isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Subscript) and \
                    ast.unparse(nodo.targets[0]).startswith("CANDIDATOS["):
                exec(compile(ast.Module(body=[nodo], type_ignores=[]), "original", "exec"), espacio)
        return espacio[nombre]

    def test_constantes(self):
        """Todas iguales al original salvo una: la masa molar del O3, que es la de la conversión de R6
        (``unidades_v2.MASA_MOLAR``, 47,998; el original usa 47,9982), por T12, sin excepción para el contraste."""
        import unidades_v2 as uv
        for nombre, mio in (("M_AIRE", cu.M_AIRE), ("VM25", cu.VM25), ("REF", cu.REF),
                            ("MIN_PARES", cu.MIN_PARES), ("LR_MIN", cu.LR_MIN), ("Z_MAX", cu.Z_MAX),
                            ("DIST_VECINA_KM", cu.DIST_VECINA_KM), ("GASES", cu.GASES)):
            with self.subTest(constante=nombre):
                self.assertEqual(self.constante(nombre), mio)
        orig_m = self.constante("M")
        self.assertEqual({g: v for g, v in orig_m.items() if g != "o3"}, {g: v for g, v in cu.M.items() if g != "o3"})
        self.assertEqual(orig_m["o3"], 47.9982)                              # la única diferencia, en el original
        self.assertEqual(cu.M["o3"], uv.MASA_MOLAR["o3"])
        self.assertEqual(cu.M, uv.MASA_MOLAR)
        orig = self.constante("CANDIDATOS", M=cu.M)                          # la regla del original, con la M de T12
        for g in cu.CANDIDATOS:
            for u, f in cu.CANDIDATOS[g].items():
                self.assertAlmostEqual(orig[g][u], f, places=12)

    def test_misma_decision(self):
        espacio = {"math": math, "np": np, "CANDIDATOS": self.constante("CANDIDATOS", M=cu.M), "MIN_PARES": cu.MIN_PARES,
                   "Z_MAX": cu.Z_MAX, "LR_MIN": cu.LR_MIN}
        for nodo in self.arbol.body:
            if isinstance(nodo, ast.FunctionDef) and nodo.name == "decidir":
                exec(compile(ast.Module(body=[nodo], type_ignores=[]), "original", "exec"), espacio)
        rng = np.random.default_rng(3)
        for k in range(300):
            g = ("no2", "o3", "so2", "co")[k % 4]
            ref = (float(rng.normal(0, 0.5)), float(rng.uniform(0.3, 2.0)), 40)
            s = {"gas": g, "pixel": None if k % 37 == 0 else 1, "pares": int(rng.integers(100, 5000)),
                 "razon": float(math.exp(rng.normal(0, 1.5)))}
            espacio["ref"] = {g: ref}
            a, b = espacio["decidir"](dict(s)), cu.decidir(dict(s), ref)
            with self.subTest(k=k):
                self.assertEqual(a["unidad_indicada"], b["unidad_indicada"])
                self.assertEqual(a["motivo"], b["motivo"])                    # el mismo texto, completo


class PublicacionTests(unittest.TestCase):
    """La segunda corrida se escribe una vez, en la raíz v2, con su lateral completo (la primera corrida por su huella
    con sus cambios, R6, y las series de NO2 y O3); el panel la acepta y rechaza la primera."""
    CONFIRMADA = staticmethod(lambda repo, rutas: {k: "rastreado" for k in rutas})
    CFG = {"red_de_monitores": {}}

    CAMS = {"desde": "2003-01-01", "hasta": "2025-12-31",
            "archivos": [{"ruta": "contaminantes/CAMS_EAC4/chile_nativo_075deg/mensual/cams_eac4_202301_chile_pixeles.nc",
                          "sha256": "c" * 64}]}

    def info(self, **cambios):
        import unidades_v2 as uv
        base = {"schema": cu.SCHEMA, "cams": self.CAMS,
                "series_leidas": {"raices": ["derived/v1_red2"], "contaminantes": ["no2", "o3"], "series": []},
                "primera_corrida": {"sha256": uv.SHA_CONTRASTE_PRIMERA, "cambios": []}}
        return {**base, **cambios}

    def test_una_vez_y_la_acepta_el_panel(self):
        import json
        sys.path.insert(0, str(V2 / "tests"))
        import panel_red2_v2 as pr
        from _sintetico_v2 import raices_temporales
        tabla = pd.DataFrame({"estacion": ["A"], "contaminante": ["no2"], "decision": ["ppb"]})
        info = self.info()
        with raices_temporales("v2-contraste-") as r:
            with self.assertRaises(SystemExit):                              # sin la traducción confirmada en git
                cu.publicar_una_vez(r, tabla, info, cfg=self.CFG)
            lateral, estado = cu.publicar_una_vez(r, tabla, info, cfg=self.CFG, estado=self.CONFIRMADA)
            self.assertEqual((estado, lateral["schema"]), ("escrito", cu.SCHEMA))
            csv = r.raiz_v2 / "unidades_red2" / cu.NOMBRES_SALIDA[0]
            # quinta revisión, mayores 1 y 2: el lateral lleva su procedencia (§0), con la huella de su programa
            escrito = json.loads(csv.with_suffix(".json").read_text(encoding="utf-8"))
            for clave in ("git", "codigo", "bibliotecas", "hilos", "codigo_red2", "traduccion"):
                self.assertIn(clave, escrito["traza"])
            self.assertEqual(escrito["traza"]["codigo_red2"]["scripts_modelo_1km/v2/contraste_unidades_v2.py"],
                             hashlib.sha256(Path(cu.__file__).read_bytes()).hexdigest())
            self.assertEqual(escrito["cams"]["archivos"], self.CAMS["archivos"])
            self.assertEqual(lateral["sha256_csv"], hashlib.sha256(csv.read_bytes()).hexdigest())
            self.assertEqual(json.loads(csv.with_suffix(".json").read_text(encoding="utf-8"))["sha256_csv"],
                             lateral["sha256_csv"])
            self.assertEqual(cu.publicar_una_vez(r, tabla, info, cfg=self.CFG, estado=self.CONFIRMADA)[1],
                             "sin_cambios")
            with self.assertRaises(SystemExit):                              # otra tabla: no se reescribe
                cu.publicar_una_vez(r, tabla.assign(decision="µg/m³N"), info, cfg=self.CFG, estado=self.CONFIRMADA)
            self.assertEqual(pr.SCHEMA_CONTRASTE, cu.SCHEMA)
            series = {"raices": ["derived/v1_red2"], "series": []}
            self.assertEqual(pr.contraste_y_su_huella(csv, lateral["sha256_csv"], r, series)["sha256"],
                             lateral["sha256_csv"])
            primera = r.raiz_v2 / "unidades_red2" / "contraste_unidades_cams.csv"     # la primera, sin lateral
            primera.write_text("serie\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                pr.contraste_y_su_huella(primera, hashlib.sha256(primera.read_bytes()).hexdigest(), r, series)

    def test_sin_la_primera_corrida_no_se_publica(self):
        """Mayor 5, 15 y 31: R6 pide registrar el cambio de decisión, y la escritura es única: sin la primera corrida
        por su huella y su lista de cambios, o con un subconjunto de gases, no se publica nada."""
        from _sintetico_v2 import raices_temporales
        tabla = pd.DataFrame({"estacion": ["A"], "contaminante": ["no2"], "decision": ["ppb"]})
        malos = {"sin primera corrida": self.info(primera_corrida=None),
                 "otra primera corrida": self.info(primera_corrida={"sha256": "0" * 64, "cambios": []}),
                 "sin la lista de cambios": self.info(primera_corrida={"sha256": self.info()["primera_corrida"]["sha256"]}),
                 "sólo NO2": self.info(series_leidas={"raices": [], "contaminantes": ["no2"], "series": []}),
                 # quinta revisión, menor 7: los archivos CAMS con su sha256 (la corrida se escribe una sola vez)
                 "sin archivos CAMS": self.info(cams={"desde": "x", "hasta": "y", "archivos": []}),
                 "sin cams": self.info(cams=None),
                 "sin sha256": self.info(cams={"archivos": [{"ruta": "contaminantes/x.nc"}]}),
                 "sha256 corto": self.info(cams={"archivos": [{"ruta": "contaminantes/x.nc", "sha256": "c" * 8}]}),
                 "sin ruta": self.info(cams={"archivos": [{"sha256": "c" * 64}]})}
        with raices_temporales("v2-contraste-") as r:
            for nombre, info in malos.items():
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    cu.publicar_una_vez(r, tabla, info, cfg=self.CFG, estado=self.CONFIRMADA)
                if "CAMS" in nombre or "cams" in nombre or "sha256" in nombre or "ruta" in nombre:
                    self.assertIn("archivos CAMS", str(e.exception))
            self.assertFalse((r.raiz_v2 / "unidades_red2").exists())

    def test_corrida_cortada_entre_el_csv_y_el_lateral(self):
        """Menor 20: si la corrida anterior se cortó después del CSV, la siguiente con el mismo CSV escribe el lateral
        («completado»); con otro CSV se detiene diciendo «corrida incompleta»."""
        import _rutas_v2 as rv
        from unittest import mock
        from _sintetico_v2 import raices_temporales
        tabla = pd.DataFrame({"estacion": ["A"], "contaminante": ["no2"], "decision": ["ppb"]})
        with raices_temporales("v2-contraste-") as r:
            with mock.patch.object(rv, "publicar_json", side_effect=RuntimeError("se cortó")):
                with self.assertRaises(RuntimeError):
                    cu.publicar_una_vez(r, tabla, self.info(), cfg=self.CFG, estado=self.CONFIRMADA)
            csv = r.raiz_v2 / "unidades_red2" / cu.NOMBRES_SALIDA[0]
            self.assertTrue(csv.exists() and not csv.with_suffix(".json").exists())
            with self.assertRaises(SystemExit) as e:
                cu.publicar_una_vez(r, tabla.assign(decision="otra"), self.info(), cfg=self.CFG, estado=self.CONFIRMADA)
            self.assertIn("corrida incompleta", str(e.exception))
            lateral, estado = cu.publicar_una_vez(r, tabla, self.info(), cfg=self.CFG, estado=self.CONFIRMADA)
            self.assertEqual(estado, "completado")
            self.assertEqual(lateral["sha256_csv"], hashlib.sha256(csv.read_bytes()).hexdigest())
            self.assertEqual(cu.publicar_una_vez(r, tabla, self.info(), cfg=self.CFG, estado=self.CONFIRMADA)[1],
                             "sin_cambios")

    def test_cams_que_cambia_durante_la_lectura(self):
        """Ronda 4, menor 10: las huellas de los archivos CAMS se calculan antes y después de leerlos; si un mensual se
        reemplaza en medio, la corrida se detiene («CAMS cambió durante la lectura») y no registra una huella que no es
        la de lo leído. Sin cambios, el lateral registra las huellas de antes, que son las de lo leído."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            datos = Path(tmp)
            archivos = []
            for k in (1, 2):
                q = datos / "contaminantes" / "CAMS_EAC4" / f"cams_eac4_20230{k}_chile_pixeles.nc"
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(f"mensual {k}".encode())
                archivos.append(q)
            leido = (pd.DatetimeIndex([]), {}, {})
            _, _, _, huellas = cu.leer_cams_con_huellas(archivos, [0], ("no2",), datos, leer=lambda *a: leido)
            self.assertEqual(huellas, cu.huellas_cams(archivos, datos))
            self.assertEqual(huellas[1]["ruta"], "contaminantes/CAMS_EAC4/cams_eac4_202302_chile_pixeles.nc")

            def leer_y_reemplazar(*a):
                archivos[1].write_bytes(b"otro mensual")                     # una descarga lo reemplaza en medio
                return leido
            with self.assertRaises(SystemExit) as e:
                cu.leer_cams_con_huellas(archivos, [0], ("no2",), datos, leer=leer_y_reemplazar)
            self.assertIn("CAMS cambió durante la lectura", str(e.exception))
            self.assertIn("cams_eac4_202302_chile_pixeles.nc", str(e.exception))
            self.assertNotIn("cams_eac4_202301", str(e.exception))

    def test_la_segunda_corrida_lee_cada_serie_con_su_huella(self):
        """Ronda 5 de la traducción, menor 3: ``series_red2`` lee cada serie desde los bytes cuyo sha256 registró
        ``reloj_sinca_v2.series_con_huella`` (el registro que va al lateral; ``main`` se lo pasa), así que una serie
        reemplazada entre el registro y la lectura detiene la corrida sin leerla."""
        import inspect
        import red_ampliada_v2 as ra
        import reloj_sinca_v2 as rs
        from unittest import mock
        from _sintetico_v2 import raices_temporales
        from test_reloj_sinca_v2 import carpeta_de_version, datos_red2, destino_red2, escribir_derivado
        rot = pd.DataFrame({"estacion": ["C1", "I1"], "contaminante": ["no2", "o3"], "grupo": "actual", "rotulo": "ppb"})
        maestro = pd.DataFrame({"estacion": ["C1", "I1"], "nombre": "x", "region_sinca": "RM", "lat": LAT0,
                                "lon": LON0})
        manifiestos = {k: None for k in ("nuevas", "actualizacion", "otras", "actuales")}
        with raices_temporales("v2-contraste-huella-") as r, mock.patch.object(ra, "LISTA_CERRADA", {}), \
                mock.patch.object(cu.uv, "leer_manifiestos", lambda d: manifiestos), \
                mock.patch.object(cu.uv, "rotulos_de_ficha", lambda *a, **k: rot), \
                mock.patch.object(ra, "maestro_red2", lambda d: maestro):
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            registro, series_d = rs.series_con_huella([raiz], r.datos, ("no2", "o3"))
            huellas = rs.huellas_de(registro)
            series, obs = cu.series_red2([raiz], r.datos, ("no2", "o3"), series_d, huellas)
            self.assertEqual(sorted(s["estacion"] for s in series), ["C1", "I1"])
            q = carpeta_de_version(raiz, "C1", "no2") / "observaciones.parquet"
            pd.read_parquet(q).iloc[:100].to_parquet(q)                     # después de registrar su huella
            with self.assertRaises(SystemExit) as e:
                cu.series_red2([raiz], r.datos, ("no2", "o3"), series_d, huellas)
            self.assertIn("C1:no2", str(e.exception))
            self.assertIn("cambió después de registrar su huella", str(e.exception))
        self.assertIn("series_red2(args.derivado, r.datos, gases, series_leidas, rs.huellas_de(registro_series))",
                      inspect.getsource(cu.main))

    def test_main_no_lee_nada_antes_de_tiempo(self):
        """Menores 19, 23 y 38: ``main`` exige la traducción confirmada antes de leer ningún valor; para escribir, NO2 y
        O3 y la primera corrida; y comprueba la lista cerrada antes de leer los maestros y las series. Quinta revisión,
        menor 6: cada guarda se prueba con la lista cerrada cumplida y los maestros y las series prohibidos, y por su
        mensaje, así que la prueba falla si se quita cualquiera de las tres."""
        import _rutas_v2 as rv
        import red_ampliada_v2 as ra
        import reloj_sinca_v2 as rs
        from unittest import mock
        from _sintetico_v2 import raices_temporales

        def prohibido(*a, **k):
            raise AssertionError("se leyó antes de tiempo")
        confirmada = lambda r, *a, **k: {}                                    # noqa: E731
        with raices_temporales("v2-contraste-main-") as r, mock.patch.object(rv, "rutas_v2", lambda: r), \
                mock.patch.object(cu, "series_red2", prohibido), mock.patch.object(rs, "series_con_huella", prohibido):
            r.config.write_bytes((V2 / "config_v2.json").read_bytes())       # la configuración sin el nodo de la red
            r.contrato.write_bytes((V2 / "DISENO_AMBIENTAL_V2.md").read_bytes())
            with self.assertRaises(SystemExit):                              # sin la traducción confirmada (git)
                cu.main(["--derivado", "x", "--no-escribir"])

            def compuerta_cerrada(*a, **k):
                raise SystemExit("compuerta de prueba: la traducción no está confirmada")
            with mock.patch.object(ra, "LISTA_CERRADA", {}), mock.patch.object(ra, "maestro_red2", prohibido):
                with mock.patch.object(ra, "exigir_traduccion_confirmada", compuerta_cerrada):
                    with self.assertRaises(SystemExit) as e:                 # la compuerta, antes de leer nada
                        cu.main(["--derivado", "x", "--no-escribir"])
                    self.assertIn("compuerta de prueba", str(e.exception))
                with mock.patch.object(ra, "exigir_traduccion_confirmada", confirmada):
                    for argv, mensaje in ((["--derivado", "x"], "para escribir"),                 # sin --primera
                                          (["--derivado", "x", "--gases", "no2", "--primera", "p.csv"], "para escribir"),
                                          (["--derivado", "x", "--gases", "so2,co", "--no-escribir"], "--gases")):
                        with self.subTest(argv=argv), self.assertRaises(SystemExit) as e:
                            cu.main(argv)
                        self.assertIn(mensaje, str(e.exception))
            with mock.patch.object(ra, "exigir_traduccion_confirmada", confirmada):
                with mock.patch.object(ra, "LISTA_CERRADA", {"falta.csv": "0" * 64}), \
                        mock.patch.object(ra, "maestro_red2", prohibido):
                    with self.assertRaises(SystemExit):                      # lista cerrada antes de los maestros
                        cu.main(["--derivado", "x", "--no-escribir"])
                primera = r.datos / "primera.csv"
                primera.write_text("estacion,contaminante,grupo,rotulo,unidad_que_indica\n", encoding="utf-8")
                # la primera, por su huella (cuarta revisión, menor 28): con la lista cerrada cumplida, la parada tiene
                # que ser la de la huella y no otra
                with mock.patch.object(ra, "LISTA_CERRADA", {}), self.assertRaises(SystemExit) as e:
                    cu.main(["--derivado", "x", "--primera", str(primera)])
                self.assertIn("no es el registrado", str(e.exception))
                real = V2.parents[2] / "Air-Pollution-Health-Chile" / "auditoria" / "20261024" / "sinca_al_modelo" / \
                    "contraste_unidades_cams.csv"
                if real.exists():                                            # sólo sus columnas de decisión
                    import derivado_red2_v2 as dr
                    with mock.patch.object(ra, "LISTA_CERRADA", {}), self.assertRaises(SystemExit) as e:
                        cu.main(["--derivado", str(dr.destino_por_omision(r.datos)), "--primera", str(real)])
                    self.assertIn("contraste_unidades_v2", str(e.exception))   # derivado sin corrida completa
                    self.assertIn("no terminó", str(e.exception))


if __name__ == "__main__":
    unittest.main()
