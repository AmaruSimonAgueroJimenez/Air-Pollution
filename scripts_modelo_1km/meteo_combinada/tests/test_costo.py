"""Pruebas de costo.py (§4.9, §7.1 y §8; §8.1 del diseño).

Dueño: I21 (ola 6). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos, en carpetas temporales: ninguna prueba abre DMC, la meteorología SINCA real, NASADEM real,
GHS-POP real, ERA5-Land real ni ``celdas.parquet``. La medición a escala real (§8.1, horas) no corre aquí: la corre el
coordinador con la máquina libre. Aquí: la proyección, la memoria, el veredicto y el recorte con mediciones fabricadas
(con factores de escala distintos de 1 y los bordes de 36 h); la escala de §8.1 y sus negativas (por tamaños, antes de
lanzar nada); la medición a escala mínima en este proceso, un punto y la contención en trabajadores, y el camino de
``real_era5`` con los seis puntos sobre un árbol sintético; y que ``costo_m1.json`` pasa la guarda de su clase.
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import copy  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import ceguera, constantes, costo, entorno, orquestacion, sintetico, tendencias  # noqa: E402
from meteo_combinada import umbrales  # noqa: E402

_APH = _RAIZ.parent.parent / "Air-Pollution-Health-Chile"
_P = int(constantes.valor("PROCESOS"))
_GB = 10 ** 9
_FISICA = 128 * _GB


def _umbrales():
    if not (_APH / umbrales.TEXTO_M0).is_file() or not (_APH / umbrales.TEXTO_VIGENTE).is_file():
        raise unittest.SkipTest("faltan los textos anclados en APH; la prueba no se da por aprobada")
    return umbrales.cargar_m0(_APH)


def _vigiladas() -> tuple:
    """Donde están los datos reales: /Volumes (DMC, ERA5-Land, NASADEM, GHS-POP, SINCA), LOCAL (la grilla, los pesos,
    los productos v3 y las corridas del reloj), la publicación del reloj en AP y la auditoría de APH. Las raíces de AP y
    APH no: ``sintetico`` las consulta para negarse a escribir en un repositorio (SIN-18)."""
    reales = entorno.rutas_reales()
    return ("/" + "Volumes", reales.local, reales.ap / "config", reales.aph / "auditoria")


def _t(pared: float) -> dict:
    return {"pared_s": float(pared), "cpu_s": float(pared)}


# Factores de escala de las mediciones fabricadas (H9): un medio de las horas con dato, un tercio de las estaciones,
# un cuarto de las celdas, la mitad de los píxeles y un octavo de la grilla medida (con la división entera de abajo).
_C = costo.CONTEOS
_F_H = _C["horas_con_dato"] / (_C["horas_con_dato"] // 2)
_F_N = _C["estaciones"] / (_C["estaciones"] // 3)
_F_C = _C["celdas_pobladas"] / (_C["celdas_pobladas"] // 4)
_F_PIX = _C["pixeles"] / (_C["pixeles"] // 2)
_F_G = _C["celdas"] / (_C["celdas"] // 8)


def _mediciones(*, ms_por_hora=1.0, seleccion=60.0, por_estacion=4.0, mes_tf=(300.0, 200.0), lectura=(1.0, 2.0),
                contencion=1.25, pico_seleccion=3.0, pico_tf=4.0, pico_mes_real=0.6, fisica=_FISICA, antes_qc=0.2,
                pico_m5=2.0) -> dict:
    """Mediciones fabricadas con los conteos divididos por los factores de arriba: la proyección se comprueba a mano.
    ``pico_mes_real``: el pico del trabajador del mes real, la memoria de la representatividad (None: sin medir)."""
    C = costo.CONTEOS
    pl = {"estaciones": C["estaciones"] // 3, "horas": C["horas"], "horas_dato": C["horas_con_dato"] // 2,
          "filas_residuos": 1000, "pliegues_p1": 10, "pliegues_p2": 100, "prueba": 5, "prueba_max_p1": 20,
          "entrenamiento": 180, "selecciones": 26, "evaluaciones": 1, "residuos_s": 100.0, "en_horas_residuos_s": 20.0,
          "clima_a_s": 30.0, "filas_c_s": 40.0, "representatividad_s": 50.0,
          "residuos_tablas": {"codificar_s_por_fila": 1e-3, "releer_s_por_fila": 2e-3},
          "pliegue": _t(seleccion + 5 * por_estacion), "prueba_p1": 15,
          "pliegue_tibio": _t(seleccion - 10.0 + 5 * por_estacion),            # la caché ya armada: 10 s menos
          "pliegue_p1": _t(seleccion - 10.0 + 15 * por_estacion),
          "por_estacion_prueba_s": por_estacion, "memoria_inicio_gb": 0.2, "memoria_pico_gb": pico_seleccion,
          "bytes": {"residuos": 1 * _GB, "campos_estaciones": _GB // 4, "filas_c": _GB // 2, "clima_estaciones": 0,
                    "clima_a": 0, "cache_series": 0, "estaticos_celdas": _GB // 10, "clima_pixeles": _GB // 20,
                    "filas_estaticos": _C["celdas"], "filas_clima_pixeles": _C["pixeles"] * 288}}
    meses = [{"mes": "201701", "horas": 744, "redes": 3, **_t(mes_tf[0] + 50.0)},       # 50 s de arranque
             {"mes": "201702", "horas": 744, "redes": 3, **_t(mes_tf[0])},
             {"mes": "201207", "horas": 744, "redes": 2, **_t(mes_tf[1])}]
    tf = {"celdas": C["celdas_pobladas"] // 4, "pixeles": 1, "horas_dato": C["horas_con_dato"] // 2,
          "estaciones": C["estaciones"] // 3,
          "pasadas": {p: {"armar": _t(10.0), "meses": meses} for p in costo.PASADAS},
          "memoria_inicio_gb": 0.2, "memoria_tras_fabricar_gb": 3.0, "memoria_pico_gb": pico_tf,
          "bytes": {"residuos": _GB // 2, "filas_c": _GB // 2, "cache_series": 0, "clima_a": 0,
                    "estaticos_celdas": _GB // 10, "clima_pixeles": _GB // 20, "filas_estaticos": _C["celdas"],
                    "filas_clima_pixeles": _C["pixeles"] * 288}}
    barrido = {"base": _t(10.0), "T_Td=B": _t(14.0), "T_Td=AB": _t(16.0), "T_Td=C": _t(12.0), "u_v=B": _t(11.0),
               "u_v=AB": _t(13.0), "u_v=C": _t(9.0), "p=B": _t(10.5), "p=AB": _t(11.0), "p=C": _t(15.0)}
    m5 = {"pixeles": C["pixeles"] // 2, "celdas_salud": C["celdas_pobladas"] // 4, "horas": 744,
          "memoria_pico_gb": pico_m5,
          "bytes": {"residuos": 0, "filas_c": _GB // 2, "cache_series": 0},
          "pixeles_producto": barrido, "pixeles_netcdf": _t(1.0), "bytes_netcdf": 10 ** 6,
          "salud": {"agudo": {"base": _t(20.0), "T_Td=B": _t(25.0), "T_Td=AB": _t(30.0), "T_Td=C": _t(40.0)},
                    "cronico": {"base": _t(20.0), "T_Td=B": _t(21.0), "T_Td=AB": _t(22.0), "T_Td=C_est": _t(35.0)}},
          "lluvia": _t(4.0), "operador_salud": {"pared_s": 6.0, "celdas": 1000, "bytes": 10 ** 6,
                                                "estaticos_bytes": 10 ** 6, "real": False}}
    gr = {"celdas": C["celdas"], "celdas_medidas": C["celdas"] // 8, "horas": 744, "lote": 4096, "pixeles": 1,
          "memoria_pico_gb": 2.0, "bytes": {"residuos": 0, "filas_c": _GB // 2, "cache_series": 0},
          "operador_mayor": {**_t(100.0), "bytes": _GB},
          "configuraciones": {k: {"operador": _t(50.0), "operador_bytes": 1,
                                  "variantes": {"I": _t(v["pared_s"] * 10), "D": _t(v["pared_s"] * 20)}}
                              for k, v in barrido.items()}}
    real = {"bytes": 10, "pixeles": 1, "horas": 744, "huella": _t(lectura[0]), "lectura": _t(lectura[1])}
    if pico_mes_real is not None:
        real["memoria_pico_gb"] = pico_mes_real
    qc = {"artefactos": 60, "horas_dato": 1, "horas_estacion": 8760, "ms_por_hora": ms_por_hora,
          "memoria_pico_gb": 0.5, "memoria_antes_unidades_gb": antes_qc, "memoria_por_meses": {"6": 100 * 10 ** 6,
                                                                                         "12": 130 * 10 ** 6},
          "anchas_tablas": {"codificar_s_por_fila": 1e-6, "releer_s_por_fila": 3e-6, "bytes_por_fila": 200.0}}
    return {"esquema": costo.ESQUEMA_MEDICIONES, "escala": dataclasses.asdict(costo.ESCALA_REAL), "a_escala": True,
            "fallas_escala": [], "real_era5": True, "aislada": True, "procesos": _P,
            "sistema": {"memoria_fisica_bytes": fisica, "nucleos": 16},
            "carga": {"inicio": 1.0, "maxima": 1.2, "lecturas": 9, "libre": True},
            "puntos": {"qc": qc, "pliegue": pl, "tf": tf, "m5": m5, "grilla": gr, "mes_real": real,
                       "contencion": {"factor": contencion, "procesos": _P}}}


class PruebasCosto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()

    def test_proyeccion_y_recorte(self):
        """T = Σ t_u·n_u·c/P + T_serie + arranque + el desequilibrio, fase por fase, con factores de escala ≠ 1 y la
        contención c (COS-6, COS-7, COS-18, COS-20); un desequilibrio por pasada de TF (H4)."""
        U, C = self.U, costo.CONTEOS
        m = _mediciones()
        p = costo.proyectar(m, U, procesos=_P)
        f = p["m34"]["fases"]
        lec, c = 3.0, 1.25
        meses, anios = costo._meses_y_anios()
        self.assertEqual((len(meses), len(anios)), (321, 27))
        t_h = 1.0 / 1000
        self.assertAlmostEqual(f["control_de_calidad"]["pared_h"],
                               (t_h * C["horas_con_dato"] * c / _P + t_h * C["horas"]) / 3600, places=9)
        # selección: tibia (con la caché armada) en cada pliegue y fría en el primero de un trabajador (COS-15)
        n_pl = U.a("P1_PLIEGUES") + C["bloques_p2"] + 1
        t_sel = (70.0 - 5 * 4.0) * _F_H                                  # el de P2 en tibio sin sus 5 de prueba
        frio = (80.0 - 70.0) * _F_H                                      # lo que el primero trae de más (COS-15)
        t_est = 4.0 * _F_H / _F_N
        datos = 40.0 * _F_N
        esperado = ((n_pl * t_sel + 2 * C["estaciones"] * t_est) * c / _P + datos + frio
                    + t_sel + math.ceil(20 * _F_N) * t_est) / 3600
        self.assertAlmostEqual(f["seleccion"]["pared_h"], esperado, places=9)
        serie = ((100.0 + 20.0 + 30.0) * _F_H + datos + 1e-3 * 1000 * _F_H + 321 * lec
                 + (1e-6 + 3e-6) * C["horas_con_dato"] + costo.REFERENCIAS["serie_no_medida_h"] * 3600)
        self.assertAlmostEqual(f["serie_m34"]["pared_h"], serie / 3600, places=9)
        self.assertIn("metricas_remuestreo_pi_decision_cota", f["serie_m34"]["partes_h"])
        # TF: cada año con su k, ×4 por las celdas; cada pasada con su desequilibrio y su arranque (H4)
        k = costo._k_reales(f["tf"]["regla"])
        tasa = {3: 300.0 / 744 * _F_C, 2: 200.0 / 744 * _F_C}
        t_meses = [tasa[k[costo._anio(x)]] * costo._horas_reales_mes(x) if k[costo._anio(x)] else lec for x in meses]
        arranque = (2 * 10.0 + 50.0) * _F_C + datos
        por_pasada = (sum(t_meses) * c / _P + arranque + max(t_meses)) / 3600
        self.assertAlmostEqual(f["tf"]["pared_h"], 2 * por_pasada, places=6)
        for pasada in costo.PASADAS:
            self.assertAlmostEqual(f["tf"]["pasadas"][pasada]["desequilibrio_h"], max(t_meses) / 3600, places=9)
        self.assertEqual(f["tf"]["regla"], tendencias.tipos.ReglaRedConstante.R2000_2025.value)
        self.assertAlmostEqual(p["m34"]["pared_h"], sum(x["pared_h"] for x in f.values()), places=9)
        self.assertLess(p["m34"]["pared_h_regla_menor"], p["m34"]["pared_h"])
        self.assertTrue(p["m34"]["completa"])
        # M5: el peor ganador (COS-5), el agudo dos veces, la lluvia, una lectura por mes y por enero siguiente
        pix = 10.0 + (16.0 - 10.0) + (13.0 - 10.0) + (15.0 - 10.0)
        t_mes_h = ((pix + 1.0) * _F_PIX + (2 * 40.0 + 35.0 + 4.0) * _F_C) / 744
        t_anio = [sum(costo._horas_reales_mes(x) * t_mes_h + lec for x in meses if costo._anio(x) == a) + lec
                  for a in anios]
        arr_m5 = datos + 6.0 * C["celdas"] / 1000                     # el operador de salud: sin la real, la cota
        self.assertAlmostEqual(p["m5"]["anual"]["pared_h"],
                               (sum(t_anio) * c / _P + arr_m5 + max(t_anio)) / 3600, places=9)
        self.assertEqual(p["m5"]["peor"]["pixeles"], {"T_Td": "AB", "u_v": "AB", "p": "C"})
        self.assertEqual(p["m5"]["peor"]["agudo"], {"T_Td": "C"})
        self.assertAlmostEqual(p["m5"]["serie_h"]["operador_de_la_grilla"], 100.0 / 3600)
        self.assertAlmostEqual(p["m5"]["serie_h"]["representatividad"], 50.0 * _F_H / 3600)
        # la grilla v2 por variante: el peor ganador, 321 meses ×8 por las celdas medidas
        for var, x in (("I", 10), ("D", 20)):
            t_mes = (pix * x) * _F_G / 744
            t_meses_g = [t_mes * costo._horas_reales_mes(mm) + lec for mm in meses]
            g = p["grilla_v2"]["variantes"][var]
            self.assertAlmostEqual(g["pared_h"], (sum(t_meses_g) * c / _P + 50.0 + max(t_meses_g)) / 3600, places=9)
        self.assertTrue(p["veredicto"]["decide"], p["veredicto"]["motivos"])
        self.assertEqual(costo.recorte(p, U), "mod11")
        with self.assertRaises(costo.ErrorCosto):
            costo.proyectar(m, U, procesos=0)

    def test_mod23_si_mas_de_36h(self):
        """Si T > 36 h, «mod23»; 36 h exactas es «mod11» (§4.9: «más de 36 h»; COS-12)."""
        U = self.U
        umbral = float(U.a("SEL_UMBRAL_H"))
        decide = {"decide": True, "motivos": []}
        for t, esperado in ((umbral, f"mod{U.a('SEL_MOD')}"),
                            (math.nextafter(umbral, math.inf), f"mod{U.a('SEL_MOD_RECORTE')}"),
                            (umbral - 1e-9, "mod11"), (umbral + 1e-6, "mod23"), (0.0, "mod11")):
            self.assertEqual(costo.recorte({"m34": {"pared_h": t}, "veredicto": decide}, U), esperado, t)
        with self.assertRaises(costo.ErrorCosto):
            costo.recorte({"m34": {"pared_h": math.nan}, "veredicto": decide}, U)
        with self.assertRaises(costo.ErrorCosto):
            costo.recorte({"m34": {"pared_h": 1.0}}, U)                 # sin veredicto
        # desde mediciones: un control de calidad que por sí solo lleva M3-4 a cada lado de 36 h
        base = costo.proyectar(_mediciones(), U)
        resto = base["m34"]["pared_h"] - base["m34"]["fases"]["control_de_calidad"]["pared_h"]
        C = costo.CONTEOS
        factor = (C["horas_con_dato"] * 1.25 / _P + C["horas"]) / 1000 / 3600        # horas de pared por ms/hora
        justo = (umbral - resto) / factor
        self.assertEqual(costo.recorte(costo.proyectar(_mediciones(ms_por_hora=justo * (1 - 1e-6)), U), U), "mod11")
        self.assertEqual(costo.recorte(costo.proyectar(_mediciones(ms_por_hora=justo * (1 + 1e-6)), U), U), "mod23")

    def test_recorte_pendiente_sin_veredicto(self):
        """H1-H3 (COS-22, COS-25): «pendiente», con su motivo, si la proyección está incompleta, si P ≠ 8, si la
        medición no es la de §8.1, sin el mes real, si la carga llegó al tope (también una lectura NaN), si una fase de
        reparto no cabe ni con un proceso (D59) o no se midió su memoria; ``contenido_costo`` lo lleva marcado."""
        U = self.U
        casos = {
            "incompleta": lambda m: m["puntos"].pop("qc"),
            "contencion": lambda m: m["puntos"].pop("contencion"),
            "escala": lambda m: m.update(a_escala=False),
            "mes real": lambda m: m.update(real_era5=False),
            "carga": lambda m: m.update(carga={"libre": False}),
            "memoria": lambda m: m["puntos"]["pliegue"].update(memoria_pico_gb=9.0),
            "fisica": lambda m: m.update(sistema={"memoria_fisica_bytes": 5 * _GB}),
            "representatividad": lambda m: m["puntos"]["mes_real"].pop("memoria_pico_gb"),
        }
        for nombre, cambio in casos.items():
            with self.subTest(caso=nombre):
                m = _mediciones()
                cambio(m)
                p = costo.proyectar(m, U)
                self.assertFalse(p["veredicto"]["decide"])
                self.assertTrue(p["veredicto"]["motivos"])
                self.assertEqual(costo.recorte(p, U), costo.PENDIENTE)
                c = costo.contenido_costo(m, p, U)
                self.assertTrue(c["recorte_pendiente"])
                self.assertEqual(c["recorte"], costo.PENDIENTE)
        p = costo.proyectar(_mediciones(), U, procesos=_P - 1)
        self.assertEqual(costo.recorte(p, U), costo.PENDIENTE)
        self.assertIn("P = ", " ".join(p["veredicto"]["motivos"]))
        self.assertFalse(costo._carga_libre([1.0, math.nan]))
        self.assertFalse(costo._carga_libre([1.0, float(constantes.valor("COSTO_CARGA_MAX"))]))
        self.assertFalse(costo._carga_libre([]))
        self.assertTrue(costo._carga_libre([0.5, 1.9]))

    def test_carga_ajena_a_la_medicion(self):
        """COS-13 (P-COS-6 revisada): durante un punto cuenta la carga ajena, la bruta menos los procesos de la
        medición que corren, sin bajar de 0: bruta 2,4 con un trabajador = 1,4, libre; 3,1 con uno = 2,1, no libre; NaN,
        no libre. Al empezar, la bruta."""
        self.assertAlmostEqual(costo.carga_ajena(2.4, 1), 1.4)
        self.assertAlmostEqual(costo.carga_ajena(3.1, 1), 2.1)
        self.assertEqual(costo.carga_ajena(0.5, 1), 0.0)
        self.assertTrue(math.isnan(costo.carga_ajena(math.nan, 1)))
        r = costo.resumen_carga([1.2, 2.4, 2.4], 1)
        self.assertTrue(r["libre"])
        self.assertEqual((r["bruta"], r["propios"]), ([1.2, 2.4, 2.4], 1))
        self.assertEqual([round(x, 9) for x in r["ajena"]], [0.2, 1.4, 1.4])
        self.assertAlmostEqual(r["maxima_ajena"], 1.4)
        self.assertFalse(costo.resumen_carga([1.2, 3.1], 1)["libre"])
        self.assertFalse(costo.resumen_carga([1.2, math.nan], 1)["libre"])
        self.assertEqual(costo.resumen_carga([1.2, math.nan], 1)["no_finitas"], 1)
        U = self.U
        for durante, libre in ((2.4, True), (3.1, False), (math.nan, False)):
            lecturas = iter([1.0] + [durante] * 100)                # la primera es la de inicio
            with self.subTest(durante=durante), tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(costo, "_carga", side_effect=lambda: next(lecturas)):
                m = costo.medir(entorno.rutas_sinteticas(tmp), real_era5=False, umbrales=U, temporal=tmp,
                                escala=costo.ESCALA_PRUEBA, aislar=False, puntos=("mes_real",))
                self.assertEqual(m["carga"]["libre"], libre)
                self.assertTrue(m["carga"]["inicio_libre"])
                c = m["puntos"]["mes_real"]["carga"]
                self.assertEqual(c["libre"], libre)
                self.assertTrue(all(b == durante or (math.isnan(b) and math.isnan(durante)) for b in c["bruta"]))
                contenido = costo.contenido_costo(m, costo.proyectar(m, U), U)
                self.assertIn("ajena", contenido["mediciones"]["mes_real"]["carga"])
                self.assertIn("bruta", contenido["mediciones"]["mes_real"]["carga"])
        lecturas = iter([2.4] + [1.0] * 100)                        # al empezar cuenta la bruta
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(costo, "_carga", side_effect=lambda: next(lecturas)):
            m = costo.medir(entorno.rutas_sinteticas(tmp), real_era5=False, umbrales=U, temporal=tmp,
                            escala=costo.ESCALA_PRUEBA, aislar=False, puntos=("mes_real",))
        self.assertFalse(m["carga"]["inicio_libre"])
        self.assertFalse(m["carga"]["libre"])

    def test_proyeccion_sin_puntos_los_declara(self):
        """Lo que no se midió queda en «sin_medir» con su motivo, no suma, y M3-4 no se da por completa."""
        m = _mediciones()
        m["puntos"]["qc"] = {"estado": costo.PENDIENTE, "motivo": "un motivo"}
        del m["puntos"]["mes_real"]
        p = costo.proyectar(m, self.U)
        self.assertFalse(p["m34"]["completa"])
        self.assertNotIn("control_de_calidad", p["m34"]["fases"])
        self.assertEqual(p["sin_medir"]["control_de_calidad"], "un motivo")
        self.assertIn("lectura_mes", p["sin_medir"])
        self.assertEqual(set(p["m34"]["faltan"]), {"control_de_calidad", "lectura_mes"})

    def test_peor_configuracion(self):
        """COS-5 (H6): t(base) + Σ_g máx_c máx(0, t(g=c) − t(base)), con el candidato más caro de cada grupo."""
        r = costo.peor_configuracion({"base": 10.0, "T_Td=B": 14.0, "T_Td=C": 12.0, "u_v=B": 9.0, "p=C": 15.0})
        self.assertEqual(r["pared_s"], 10.0 + 4.0 + 0.0 + 5.0)
        self.assertEqual(r["ganador"], {"T_Td": "B", "u_v": "A", "p": "C"})
        barrido = costo._barrido("ambiental")
        self.assertEqual(len(barrido), 1 + 3 * 3)
        self.assertEqual(barrido["base"], {"T_Td": "A", "u_v": "A", "p": "A"})
        self.assertEqual(barrido["u_v=C"], {"T_Td": "A", "u_v": "C", "p": "A"})
        self.assertEqual(set(costo._barrido("cronico")), {"base", "T_Td=B", "T_Td=AB", "T_Td=C_est"})

    def test_k_de_cada_anio_y_las_reglas(self):
        """COS-8: con la regla 2000-2025, 57 años-red (15 × 2 + 5 × 3 + 5 × 2 + 2: las 499.680 h de §8 del diseño son
        57 años medios); 2026 no tiene TF; las otras reglas, menos años."""
        R = tendencias.tipos.ReglaRedConstante
        k = costo._k_reales(R.R2000_2025.value)
        self.assertEqual(sum(k.values()), 57)
        self.assertEqual((k[2000], k[2017], k[2022], k[2025], k[2026]), (2, 3, 2, 2, 0))
        self.assertLess(sum(costo._k_reales(R.R2010_2025.value).values()), 57)

    def test_memoria_por_proceso_y_del_grupo(self):
        """COS-11, COS-24 (H2; ORQ-42 a ORQ-44): el pico de cada punto ya trae su armado por el camino de la corrida; a
        otra escala se suma lo que la red real trae de más (por horas, por estaciones, por celdas y píxeles); el grupo
        es P trabajadores más el principal, frente a la memoria física; el principal de M3-4, el máximo entre armar la
        ligera y tenerla con un año de meses; el control de calidad en la estación más larga; el tope es
        MEMORIA_MAX_GB·10⁹ B, también para el principal."""
        C = costo.CONTEOS
        mem = costo.proyectar(_mediciones(), self.U)["memoria"]
        self.assertEqual(mem["tope_gb"], float(constantes.valor("MEMORIA_MAX_GB")))
        self.assertEqual(mem["unidad"], "GB = 10^9 B")
        sel = 3.0 * _GB + (_F_H - 1) * (1 * _GB + _GB / 4) + (_F_N - 1) * (_GB / 2)
        self.assertAlmostEqual(mem["trabajador_gb"]["seleccion"], sel / _GB)
        falta_tf = (_F_H - 1) * (_GB / 2) + (_F_N - 1) * (_GB / 2)
        self.assertAlmostEqual(mem["trabajador_gb"]["tf"], (4.0 * _GB + falta_tf) / _GB)
        ligera = _GB / 2 * _F_H + _GB / 2 * _F_N + _GB / 10 + _GB / 20
        mes = 744 * 1 * 6 * 4                                            # el mes real fabricado: 744 h × 1 píxel
        principal = max(3.0 * _GB + falta_tf, 0.2 * _GB + ligera + 12 * mes)
        self.assertAlmostEqual(mem["principal_gb"]["m34"], principal / _GB)
        f = mem["fases"]["seleccion"]
        self.assertAlmostEqual(f["grupo_gb"], (_P * sel + principal) / _GB)
        self.assertEqual(f["procesos_que_caben"], min(_P, int((_FISICA - principal) // sel)))
        qc = mem["control_de_calidad_frente_al_texto"]
        pendiente = 30 * 10 ** 6 / (6 * 8760 / 12)
        self.assertAlmostEqual(qc["estacion_mas_larga_gb"] * _GB,
                               0.2 * _GB + 100 * 10 ** 6 + pendiente * (C["horas"] - 6 * 8760 / 12))
        self.assertFalse(qc["bajo_el_texto"])
        self.assertTrue(mem["principal_m34_cabe"])
        self.assertEqual(mem["sin_procesos"], [])
        self.assertAlmostEqual(mem["trabajador_gb"]["representatividad"], 0.6)       # el pico del mes real (COS-25)
        # una selección de 9 GB pasa el tope de 8·10⁹ B: no cabe ni con un proceso (D59); un principal de 9 GB pasa
        # del tope
        mem = costo.proyectar(_mediciones(pico_seleccion=9.0), self.U)["memoria"]
        self.assertFalse(mem["fases"]["seleccion"]["cabe"])
        self.assertEqual(mem["fases"]["seleccion"]["procesos_que_caben"], 0)
        self.assertEqual(mem["procesos_por_fase"]["m34"]["seleccion_y_prediccion"], 0)
        self.assertEqual(mem["sin_procesos"], ["m34/seleccion_y_prediccion"])
        m = _mediciones()
        m["puntos"]["tf"]["memoria_tras_fabricar_gb"] = 9.0
        self.assertFalse(costo.proyectar(m, self.U)["memoria"]["principal_m34_cabe"])

    def test_escala_real_fijada_contra_8_1(self):
        """``ESCALA_REAL`` es la de §8.1 (≥ 50 artefactos de un año, 579 estaciones, H horas, 108.579 celdas, un año
        de TF con meses de 2 y 3 redes, un mes de M5 y de la grilla en 838.430 celdas) y se juzga por los tamaños."""
        E, C = costo.ESCALA_REAL, costo.CONTEOS
        self.assertEqual(costo.fallas_escala(E), [])
        self.assertGreaterEqual(E.artefactos, 50)
        self.assertLessEqual(E.qc_meses, 12)
        self.assertEqual((E.estaciones, E.horas, E.desde), (579, 234_120, "2000-01-01"))
        self.assertEqual((E.celdas_tf, E.celdas_salud, E.celdas_grilla), (108_579, 108_579, 838_430))
        self.assertEqual(len(set(E.meses_tf)), 12)
        self.assertEqual({costo._redes_reales(costo._anio(m)) for m in E.meses_tf}, {2, 3})
        self.assertEqual((C["estaciones"], C["horas"], C["celdas"], C["celdas_pobladas"]), (579, 234_120, 838_430,
                                                                                         108_579))
        self.assertTrue(costo.fallas_escala(costo.ESCALA_PRUEBA))
        otra = dataclasses.replace(E, nombre="otra")                   # el nombre no importa
        self.assertEqual(costo.fallas_escala(otra), [])
        for cambio in ({"estaciones": 578}, {"celdas_grilla": 1}, {"qc_meses": 9}, {"meses_tf": E.meses_tf[:6]}):
            self.assertTrue(costo.fallas_escala(dataclasses.replace(E, **cambio)), cambio)

    def test_escala_real_exige_real_era5_y_la_maquina_libre(self):
        """Las negativas de §8.1 (por los tamaños: también con otro nombre) ocurren antes de lanzar ningún trabajador
        y de abrir nada (``orquestacion.repartir`` reemplazado por una guarda que falla; registro en bloqueo)."""
        U = self.U
        otra = dataclasses.replace(costo.ESCALA_REAL, nombre="otra")
        guarda = mock.patch.object(orquestacion, "repartir", side_effect=AssertionError("no debía lanzar nada"))
        with tempfile.TemporaryDirectory() as tmp, guarda, \
                ceguera.RegistroAccesos(_vigiladas(), bloquear=True) as reg:
            rutas = entorno.rutas_sinteticas(tmp)
            for escala in (costo.ESCALA_REAL, otra):
                with self.assertRaisesRegex(costo.ErrorCosto, "real_era5"):
                    costo.medir(rutas, real_era5=False, umbrales=U, temporal=tmp, escala=escala)
            for carga in (float(constantes.valor("COSTO_CARGA_MAX")), math.nan):
                with mock.patch.object(costo, "_carga", return_value=carga), \
                        self.assertRaisesRegex(costo.ErrorCosto, "libre"):
                    costo.medir(rutas, real_era5=True, umbrales=U, temporal=tmp, escala=otra)
            with self.assertRaises(costo.ErrorCosto):
                costo.medir(rutas, real_era5=False, umbrales=U, temporal=tmp, escala=costo.ESCALA_PRUEBA,
                            puntos=("otro",))
            with self.assertRaises(costo.ErrorCosto):
                costo.medir(rutas, real_era5=False, umbrales=U, temporal=tmp, escala=costo.ESCALA_PRUEBA, procesos=0)
        self.assertEqual((reg.accesos, reg.por_enlace, reg.negados_dentro), ([], [], []))

    def test_carpeta_temporal_propia(self):
        """H10, COS-23: sin ``temporal``, ``medir`` corre en una carpeta de ``entorno.carpeta_de_trabajo`` bajo la
        temporal del sistema, que existe mientras mide y se borra al terminar, también con un error en medio. Una
        carpeta dada debe estar bajo la temporal del sistema."""
        U = self.U
        real = entorno.carpeta_de_trabajo
        vistas = []

        @contextlib.contextmanager
        def espia(prefijo):
            with real(prefijo) as carpeta:
                vistas.append((prefijo, carpeta))
                yield carpeta

        def falla(ctx):
            self.assertTrue(Path(ctx["temporal"]).is_dir())
            raise RuntimeError("un punto que falla")
        temporal = Path(tempfile.gettempdir()).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            with mock.patch.object(entorno, "carpeta_de_trabajo", espia):
                m = costo.medir(rutas, real_era5=False, umbrales=U, escala=costo.ESCALA_PRUEBA, aislar=False,
                                puntos=("tf",))                        # la TF escribe sus meses en la carpeta
                with mock.patch.dict(costo._MEDIDORES, {"mes_real": falla}), \
                        self.assertRaisesRegex(RuntimeError, "un punto que falla"):
                    costo.medir(rutas, real_era5=False, umbrales=U, escala=costo.ESCALA_PRUEBA, aislar=False,
                                puntos=("mes_real",))
            self.assertEqual([p for p, _ in vistas], [costo.PREFIJO_TRABAJO] * 2)
            for _, carpeta in vistas:
                self.assertEqual(carpeta.parent, temporal)
                self.assertFalse(carpeta.exists())
            self.assertEqual(m["puntos"]["tf"]["celdas"], costo.ESCALA_PRUEBA.celdas_tf)
            with self.assertRaises(ValueError):
                costo.medir(rutas, real_era5=False, umbrales=U, temporal=_RAIZ, escala=costo.ESCALA_PRUEBA,
                            puntos=("mes_real",))

    def test_ruta_del_mes_real(self):
        """COS-10: el mes real es el de S14 (2024-01), bajo ERA5L/mensual."""
        reales = entorno.rutas_reales()
        self.assertEqual(entorno.alias(costo.ruta_mes_real(reales), reales),
                         "ERA5L/mensual/era5land_202401_chile_pixeles.nc")


def _todas(n: int) -> dict:
    """«procesos_por_fase» con n en todas las fases de reparto de ``orquestacion.FASES_REPARTO`` (A39)."""
    return {c: {f: n for f in fs} for c, fs in orquestacion.FASES_REPARTO.items()}


def _numeros(p: dict) -> dict:
    """Lo que la proyección proyecta (sin la memoria ni el veredicto), como JSON de Python."""
    return costo._limpio({k: p[k] for k in ("m34", "tf_por_regla", "m5", "m6", "grilla_v2")})


def _pared_seleccion(U, n: int, c: float = 1.25) -> float:
    """La pared de la selección de ``_mediciones()`` con n procesos (la cuenta de ``test_proyeccion_y_recorte``)."""
    C = costo.CONTEOS
    n_pl = U.a("P1_PLIEGUES") + C["bloques_p2"] + 1
    t_sel, frio, t_est, datos = (70.0 - 5 * 4.0) * _F_H, (80.0 - 70.0) * _F_H, 4.0 * _F_H / _F_N, 40.0 * _F_N
    return ((n_pl * t_sel + 2 * C["estaciones"] * t_est) * c / n + datos + frio + t_sel
            + math.ceil(20 * _F_N) * t_est) / 3600


class PruebasProcesosPorFase(unittest.TestCase):
    """D59 (P145; P146 en M5; A39; COS-25): la fase de reparto que no cabe en memoria con 8 procesos corre con el mayor
    número que quepa, y su pared se proyecta con él; si no cabe ni con uno, el recorte queda «pendiente»."""

    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()

    def test_procesos_que_caben(self):
        """El mayor n de 1 a P con el trabajador bajo el tope y n·trabajador + principal ≤ la memoria física («≤»);
        0 si no cabe ni con uno o si falta una medida."""
        tope = float(constantes.valor("MEMORIA_MAX_GB")) * _GB
        f = costo._procesos_que_caben
        self.assertEqual(f(4 * _GB, 4 * _GB, 128 * _GB, tope, _P), _P)
        self.assertEqual(f(5 * _GB, 4 * _GB, 29 * _GB, tope, _P), 5)                 # 5·5 + 4 = 29: justo
        self.assertEqual(f(5 * _GB, 4 * _GB, 29 * _GB - 1, tope, _P), 4)
        self.assertEqual(f(5 * _GB, 4 * _GB, 8.9 * _GB, tope, _P), 0)                # ni con uno
        self.assertEqual(f(tope, 0.0, 128 * _GB, tope, _P), _P)                       # en el tope, cabe
        self.assertEqual(f(tope + 1, 0.0, 128 * _GB, tope, _P), 0)                    # sobre el tope, no
        for falta in ((None, 1.0, 9.0), (1.0, None, 9.0), (1.0, 1.0, 0.0), (math.nan, 1.0, 9.0)):
            self.assertEqual(f(*(x if x is None else x * _GB for x in falta), tope, _P), 0, falta)

    def test_fases_de_reparto_de_orquestacion(self):
        """Las fases son exactamente las de ``orquestacion.FASES_REPARTO`` y cada una sale de una memoria medida."""
        fases = {f for fs in orquestacion.FASES_REPARTO.values() for f in fs}
        self.assertEqual(set(costo._MEMORIA_DE_FASE), fases)
        p = costo.proyectar(_mediciones(), self.U)
        self.assertEqual({c: set(fs) for c, fs in p["procesos_por_fase"].items()},
                         {c: set(fs) for c, fs in orquestacion.FASES_REPARTO.items()})

    def test_d59_todo_cabe_con_8_no_cambia_nada(self):
        """Regresión: con la memoria física holgada, «procesos_por_fase» da 8 en todas, la proyección es la de antes (la
        que no mira la memoria: 8 en todas las fases) y el recorte también, sin nota de D59."""
        U = self.U
        m = _mediciones()
        p = costo.proyectar(m, U)
        self.assertEqual(p["procesos_por_fase"], _todas(_P))
        with mock.patch.object(costo, "_procesos_que_caben", lambda *a, **k: _P):
            antes = costo.proyectar(m, U)
        self.assertEqual(_numeros(p), _numeros(antes))
        self.assertEqual(costo.recorte(p, U), costo.recorte(antes, U))
        self.assertEqual(costo.recorte(p, U), "mod11")
        holgada = costo.proyectar(_mediciones(fisica=10 ** 15), U)
        self.assertEqual(_numeros(p), _numeros(holgada))
        f = p["m34"]["fases"]
        self.assertEqual((f["control_de_calidad"]["procesos"], f["seleccion"]["procesos"], f["tf"]["procesos"]),
                         (_P, _P, _P))
        self.assertEqual((p["m5"]["primera_pasada"]["procesos"], p["m5"]["anual"]["procesos"]), (_P, _P))
        self.assertFalse([n for n in p["veredicto"]["notas"] if "D59" in n or "P147" in n])
        self.assertEqual(p["m34"]["pared_h_con_P"], p["m34"]["pared_h"])
        for k, f_ in p["m34"]["fases"].items():
            self.assertEqual(f_["pared_h_con_P"], f_["pared_h"], k)
        self.assertEqual(costo.contenido_costo(m, p, U)["procesos_por_fase"], _todas(_P))
        g = p["memoria"]["fases"]["seleccion"]
        self.assertEqual(g["grupo_con_n_gb"], g["grupo_gb"])

    def _con_5_en_la_seleccion(self, **kw):
        """Las mediciones con una selección de 7,9 GB y la TF chica, y la memoria física justa para que la selección
        quepa con 5 procesos y todo lo demás con 8."""
        m = _mediciones(pico_seleccion=5.65, pico_tf=2.0, **kw)
        mem = costo.proyectar(m, self.U)["memoria"]
        w = mem["trabajador_gb"]["seleccion"] * _GB
        self.assertLessEqual(w, float(constantes.valor("MEMORIA_MAX_GB")) * _GB)
        m["sistema"]["memoria_fisica_bytes"] = mem["principal_gb"]["m34"] * _GB + 5.5 * w
        return m

    def test_d59_una_fase_con_5_procesos(self):
        """Una fase que sólo cabe con 5: su pared se proyecta con 5 (mayor), las demás, la grilla v2 y M6 no cambian,
        el veredicto decide con una nota de D59, y el recorte decide con esa pared: puede pasar a «mod23»."""
        U = self.U
        m5_ = self._con_5_en_la_seleccion()
        p5 = costo.proyectar(m5_, U)
        esperado = _todas(_P)
        esperado["m34"]["seleccion_y_prediccion"] = 5
        self.assertEqual(p5["procesos_por_fase"], esperado)
        m8 = _mediciones(pico_seleccion=5.65, pico_tf=2.0, fisica=10 ** 15)
        p8 = costo.proyectar(m8, U)
        self.assertEqual(p8["procesos_por_fase"], _todas(_P))
        s5, s8 = p5["m34"]["fases"]["seleccion"], p8["m34"]["fases"]["seleccion"]
        self.assertEqual((s5["procesos"], s8["procesos"]), (5, _P))
        self.assertAlmostEqual(s5["pared_h"], _pared_seleccion(U, 5), places=9)
        self.assertAlmostEqual(s8["pared_h"], _pared_seleccion(U, _P), places=9)
        self.assertGreater(s5["pared_h"], s8["pared_h"])
        for k in ("control_de_calidad", "tf", "serie_m34"):
            self.assertEqual(costo._limpio(p5["m34"]["fases"][k]), costo._limpio(p8["m34"]["fases"][k]), k)
        for k in ("grilla_v2", "m6", "m5"):
            self.assertEqual(costo._limpio(p5[k]), costo._limpio(p8[k]), k)
        self.assertAlmostEqual(p5["m34"]["pared_h"] - p8["m34"]["pared_h"], s5["pared_h"] - s8["pared_h"], places=9)
        g = p5["memoria"]["fases"]["seleccion"]                          # el grupo con n, junto al de P
        w, pr = g["trabajador_gb"], p5["memoria"]["principal_gb"]["m34"]
        self.assertAlmostEqual(g["grupo_con_n_gb"], 5 * w + pr)
        self.assertAlmostEqual(g["grupo_gb"], _P * w + pr)
        self.assertLessEqual(g["grupo_con_n_gb"] * _GB, m5_["sistema"]["memoria_fisica_bytes"])
        self.assertGreater(g["grupo_gb"] * _GB, m5_["sistema"]["memoria_fisica_bytes"])
        self.assertEqual(p5["m34"]["fases"]["seleccion"]["pared_h_con_P"], s8["pared_h"])
        self.assertEqual(p5["m34"]["pared_h_con_P"], p8["m34"]["pared_h"])               # P147: la de antes de D59
        self.assertTrue(p5["veredicto"]["decide"], p5["veredicto"]["motivos"])
        nota = " ".join(p5["veredicto"]["notas"])
        self.assertIn("D59", nota)
        self.assertIn("m34/seleccion_y_prediccion con 5", nota)
        c = costo.contenido_costo(m5_, p5, U)
        self.assertEqual(c["procesos_por_fase"], esperado)
        self.assertEqual(c["proyeccion"]["procesos_por_fase"], esperado)
        ceguera.vigilar_salida("costo_m1.json", c, clase="resumen")
        # el control de calidad lleva M3-4 justo bajo 36 h con 8 procesos en la selección: con 5, pasa
        umbral = float(U.a("SEL_UMBRAL_H"))
        delta = p5["m34"]["pared_h"] - p8["m34"]["pared_h"]
        C = costo.CONTEOS
        factor = (C["horas_con_dato"] * 1.25 / _P + C["horas"]) / 1000 / 3600        # horas de pared por ms/hora
        ms = 1.0 + (umbral - delta / 2 - p8["m34"]["pared_h"]) / factor
        self.assertGreater(ms, 0)
        p8b = costo.proyectar(_mediciones(pico_seleccion=5.65, pico_tf=2.0, fisica=10 ** 15, ms_por_hora=ms), U)
        p5b = costo.proyectar(self._con_5_en_la_seleccion(ms_por_hora=ms), U)
        self.assertLess(p8b["m34"]["pared_h"], umbral)
        self.assertGreater(p5b["m34"]["pared_h"], umbral)
        self.assertEqual((costo.recorte(p8b, U), costo.recorte(p5b, U)), ("mod11", "mod23"))
        # P147: decide la pared con n; la de P en todas las fases va aparte, con su nota cuando el recorte sería otro
        self.assertEqual(p5b["m34"]["pared_h_con_P"], p8b["m34"]["pared_h"])
        p147 = [n for n in p5b["veredicto"]["notas"] if "P147" in n]
        self.assertEqual(len(p147), 1)
        self.assertIn("mod11", p147[0])
        self.assertFalse([n for n in p8b["veredicto"]["notas"] if "P147" in n])
        self.assertFalse([n for n in p5["veredicto"]["notas"] if "P147" in n])       # mismo recorte: sin nota

    def _comparar_con_holgada(self, p, holgada, distinta: str):
        """Las fases de M3-4 que no son ``distinta``, M5, la grilla v2 y M6 iguales a las de la memoria holgada."""
        for k in p["m34"]["fases"]:
            if k != distinta:
                self.assertEqual(costo._limpio(p["m34"]["fases"][k]), costo._limpio(holgada["m34"]["fases"][k]), k)
        for k in ("m5", "grilla_v2", "m6"):
            self.assertEqual(costo._limpio(p[k]), costo._limpio(holgada[k]), k)
        self.assertEqual(p["m34"]["pared_h_con_P"], holgada["m34"]["pared_h"])

    def test_d59_control_de_calidad_con_k(self):
        """Sólo «artefactos» cabe con k = 5 (un control de calidad de 7,7·10⁹ B en 49·10⁹ B físicos): su n sale de la
        memoria del control de calidad (no de la de la TF), su fase lleva 5 procesos y su pared se proyecta con 5."""
        U, C = self.U, costo.CONTEOS
        p = costo.proyectar(_mediciones(antes_qc=6.0, fisica=49 * _GB), U)
        esperado = _todas(_P)
        esperado["m34"]["artefactos"] = 5                               # (49 − 4,5) / 7,67 = 5,8
        self.assertEqual(p["procesos_por_fase"], esperado)
        f = p["m34"]["fases"]["control_de_calidad"]
        t_h, c = 1.0 / 1000, 1.25
        self.assertEqual(f["procesos"], 5)
        self.assertAlmostEqual(f["pared_h"], (t_h * C["horas_con_dato"] * c / 5 + t_h * C["horas"]) / 3600, places=9)
        self.assertAlmostEqual(f["pared_h_con_P"], (t_h * C["horas_con_dato"] * c / _P + t_h * C["horas"]) / 3600,
                               places=9)
        self._comparar_con_holgada(p, costo.proyectar(_mediciones(antes_qc=6.0, fisica=10 ** 15), U),
                                   "control_de_calidad")
        self.assertIn("m34/artefactos con 5", " ".join(p["veredicto"]["notas"]))

    def test_d59_tf_con_k(self):
        """Sólo «tendencias_y_finitud» cabe con k = 5 (una TF de 7,8·10⁹ B en 49·10⁹ B físicos): su n, el de sus dos
        pasadas y de cada regla de red, y su pared con 5; «artefactos» sigue con 8."""
        U = self.U
        p = costo.proyectar(_mediciones(pico_tf=6.3, fisica=49 * _GB), U)
        esperado = _todas(_P)
        esperado["m34"]["tendencias_y_finitud"] = 5                     # (49 − 4,5) / 7,8 = 5,7
        self.assertEqual(p["procesos_por_fase"], esperado)
        f = p["m34"]["fases"]["tf"]
        self.assertEqual(f["procesos"], 5)
        self.assertEqual({x["procesos"] for x in f["pasadas"].values()}, {5})
        self.assertEqual({v["procesos"] for v in p["tf_por_regla"].values()}, {5})
        meses, _ = costo._meses_y_anios()
        k = costo._k_reales(f["regla"])
        lec, c = 3.0, 1.25
        tasa = {3: 300.0 / 744 * _F_C, 2: 200.0 / 744 * _F_C}
        t_meses = [tasa[k[costo._anio(x)]] * costo._horas_reales_mes(x) if k[costo._anio(x)] else lec for x in meses]
        arranque = (2 * 10.0 + 50.0) * _F_C + 40.0 * _F_N
        for n, clave in ((5, "pared_h"), (_P, "pared_h_con_P")):
            self.assertAlmostEqual(f[clave], 2 * (sum(t_meses) * c / n + arranque + max(t_meses)) / 3600, places=6)
        self._comparar_con_holgada(p, costo.proyectar(_mediciones(pico_tf=6.3, fisica=10 ** 15), U), "tf")

    def test_d59_m5_con_su_principal(self):
        """Las dos fases de M5 usan el principal de M5, no el de M3-4 (aquí mucho mayor): con la física justa, las dos
        caben con 7 con el de M5 (con el de M3-4 serían 6); sus pasadas llevan esos procesos."""
        U = self.U
        m = _mediciones(pico_mes_real=4.5)
        m["puntos"]["tf"]["memoria_tras_fabricar_gb"] = 6.0             # el principal de M3-4: 7,5·10⁹ B
        mem = costo.proyectar(m, U)["memoria"]
        p_m5, p_m34 = mem["principal_gb"]["m5"], mem["principal_gb"]["m34"]
        w_anual, w_rep = mem["trabajador_gb"]["m5"], mem["trabajador_gb"]["representatividad"]
        self.assertGreater(p_m34 - p_m5, 3)
        fisica = p_m5 + 7.5 * w_anual
        m["sistema"]["memoria_fisica_bytes"] = fisica * _GB
        for w in (w_anual, w_rep):                                      # el escenario: 7 con el de M5, 6 con el de M3-4
            self.assertEqual((int((fisica - p_m5) // w), int((fisica - p_m34) // w)), (7, 6))
        p = costo.proyectar(m, U)
        self.assertEqual(p["procesos_por_fase"]["m5"], {"representatividad": 7, "anual": 7})
        self.assertEqual((p["m5"]["primera_pasada"]["procesos"], p["m5"]["anual"]["procesos"]), (7, 7))

    def test_d59_m5_anual_con_k(self):
        """Sólo «anual» cabe con k = 5 (un trabajador de M5 de 7,9·10⁹ B en 49·10⁹ B físicos): «m5.anual.procesos» es
        5 y su pared se proyecta con 5; M3-4 y su recorte no cambian."""
        U, C = self.U, costo.CONTEOS
        p = costo.proyectar(_mediciones(pico_m5=5.225, fisica=49 * _GB), U)
        esperado = _todas(_P)
        esperado["m5"]["anual"] = 5                                     # (49 − 3,85) / 7,9 = 5,7
        self.assertEqual(p["procesos_por_fase"], esperado)
        self.assertEqual(p["m5"]["anual"]["procesos"], 5)
        meses, anios = costo._meses_y_anios()
        lec, c = 3.0, 1.25
        pix = 10.0 + (16.0 - 10.0) + (13.0 - 10.0) + (15.0 - 10.0)
        t_mes_h = ((pix + 1.0) * _F_PIX + (2 * 40.0 + 35.0 + 4.0) * _F_C) / 744
        t_anio = [sum(costo._horas_reales_mes(x) * t_mes_h + lec for x in meses if costo._anio(x) == a) + lec
                  for a in anios]
        arr_m5 = 40.0 * _F_N + 6.0 * C["celdas"] / 1000
        self.assertAlmostEqual(p["m5"]["anual"]["pared_h"], (sum(t_anio) * c / 5 + arr_m5 + max(t_anio)) / 3600,
                               places=9)
        holgada = costo.proyectar(_mediciones(pico_m5=5.225, fisica=10 ** 15), U)
        self.assertEqual(costo._limpio(p["m34"]), costo._limpio(holgada["m34"]))
        self.assertEqual(costo.recorte(p, U), costo.recorte(holgada, U))
        self.assertGreater(p["m5"]["pared_h"], holgada["m5"]["pared_h"])

    def test_d59_una_fase_que_no_cabe_ni_con_1(self):
        """Una fase que no cabe ni con un proceso: «pendiente», con el motivo que nombra la fase (D59); su pared se
        proyecta con P, sólo como información. Sin memoria física para nada, todas las fases van en el motivo. Un
        principal de M3-4 sobre el tope, también «pendiente»."""
        U = self.U
        m = _mediciones(pico_seleccion=9.0)                             # 11,25·10⁹ B: sobre el tope de 8·10⁹ B
        p = costo.proyectar(m, U)
        self.assertEqual(p["procesos_por_fase"]["m34"]["seleccion_y_prediccion"], 0)
        self.assertEqual(costo.recorte(p, U), costo.PENDIENTE)
        motivos = " ".join(p["veredicto"]["motivos"])
        self.assertIn("D59", motivos)
        self.assertIn("m34/seleccion_y_prediccion", motivos)
        self.assertEqual(p["m34"]["fases"]["seleccion"]["procesos"], _P)        # informativa, con P
        self.assertEqual(_numeros(p), _numeros(costo.proyectar(_mediciones(), U)))
        c = costo.contenido_costo(m, p, U)
        self.assertEqual((c["recorte"], c["procesos_por_fase"]["m34"]["seleccion_y_prediccion"]), (costo.PENDIENTE, 0))
        p = costo.proyectar(_mediciones(fisica=4 * _GB), U)               # cada principal y uno: > 4·10⁹ B
        self.assertEqual(p["procesos_por_fase"], _todas(0))
        for c_, fs in orquestacion.FASES_REPARTO.items():
            for f_ in fs:
                self.assertIn(f"{c_}/{f_}", " ".join(p["veredicto"]["motivos"]))
        self.assertEqual(costo.recorte(p, U), costo.PENDIENTE)
        m = _mediciones()
        m["puntos"]["tf"]["memoria_tras_fabricar_gb"] = 9.0
        p = costo.proyectar(m, U)
        self.assertEqual(costo.recorte(p, U), costo.PENDIENTE)
        self.assertIn("principal de M3-4", " ".join(p["veredicto"]["motivos"]))

    def test_d59_la_representatividad(self):
        """M5 (P146): la representatividad toma el pico del trabajador del mes real; sin él (o sin el mes real), no se
        midió: «pendiente», con su motivo. Con un pico grande corre con menos procesos: su primera pasada se proyecta
        con ellos y el recorte de M3-4 no cambia."""
        U = self.U
        for nombre, m in (("sin_pico", _mediciones(pico_mes_real=None)),
                          ("sin_mes", _mediciones()), ):
            if nombre == "sin_mes":
                m["puntos"]["mes_real"] = {"estado": costo.SIN_MEDIR, "motivo": "sin real_era5", "memoria_pico_gb": 0.1}
            with self.subTest(caso=nombre):
                p = costo.proyectar(m, U)
                self.assertEqual(p["procesos_por_fase"]["m5"]["representatividad"], 0)
                self.assertEqual(costo.recorte(p, U), costo.PENDIENTE)
                self.assertIn("m5/representatividad", " ".join(p["veredicto"]["motivos"]))
        m = _mediciones(pico_mes_real=7.0, fisica=50 * _GB)
        p = costo.proyectar(m, U)
        esperado = _todas(_P)
        esperado["m5"]["representatividad"] = 6                         # (50 − 3,85) / 7 = 6,6
        self.assertEqual(p["procesos_por_fase"], esperado)
        lec, c = 3.0, 1.25
        self.assertEqual(p["m5"]["primera_pasada"]["procesos"], 6)
        self.assertAlmostEqual(p["m5"]["primera_pasada"]["pared_h"], (321 * lec * c / 6 + lec) / 3600, places=9)
        antes = costo.proyectar(_mediciones(pico_mes_real=7.0, fisica=10 ** 15), U)
        self.assertGreater(p["m5"]["pared_h"], antes["m5"]["pared_h"])
        self.assertEqual(costo._limpio(p["m34"]), costo._limpio(antes["m34"]))
        self.assertEqual(costo.recorte(p, U), costo.recorte(antes, U))
        self.assertIn("m5/representatividad con 6", " ".join(p["veredicto"]["notas"]))


class PruebasMedicion(unittest.TestCase):
    """La medición a escala mínima en este proceso, una vez para todas las pruebas de la clase (≈ 40 s)."""

    @classmethod
    def setUpClass(cls):
        cls.U = _umbrales()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.rutas = entorno.rutas_sinteticas(cls._tmp.name)
        with ceguera.RegistroAccesos(_vigiladas(), bloquear=True) as reg:
            cls.m = costo.medir(cls.rutas, real_era5=False, umbrales=cls.U, temporal=Path(cls._tmp.name) / "costo",
                                escala=costo.ESCALA_PRUEBA, aislar=False)
        cls.registro = reg
        cls.p = costo.proyectar(cls.m, cls.U)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_sin_real_era5_no_se_abre_nada_real(self):
        """Con ``real_era5=False`` nada real se abre: ni ERA5-Land, ni ``celdas.parquet``, ni LOCAL ni APH."""
        reg = self.registro
        self.assertEqual((reg.accesos, reg.por_enlace, reg.negados_dentro), ([], [], []))
        self.assertEqual(self.m["puntos"]["mes_real"]["estado"], costo.SIN_MEDIR)
        self.assertFalse(self.m["real_era5"])
        for nombre, r in self.m["puntos"].items():
            self.assertEqual(r.get("lecturas_reales", []), [], nombre)

    def test_medir_a_escala_minima(self):
        """Los puntos, con sus tiempos (pared y CPU), su memoria y su carga; la contención, sin aislar, sin medir."""
        pts = self.m["puntos"]
        self.assertEqual(tuple(pts), costo.PUNTOS)
        for nombre in ("qc", "pliegue", "tf", "m5", "grilla", "mes_real"):
            r = pts[nombre]
            with self.subTest(punto=nombre):
                self.assertGreater(r["memoria_pico_gb"], 0)
                self.assertGreaterEqual(r["total"]["pared_s"], 0)
                self.assertGreaterEqual(r["carga"]["lecturas"], 2)
                self.assertEqual(len(r["carga"]["bruta"]), len(r["carga"]["ajena"]))
        self.assertEqual(pts["contencion"]["estado"], costo.SIN_MEDIR)
        qc = pts["qc"]                                                  # COS-16
        self.assertEqual((qc["artefactos"], qc["estaciones"]), (costo.ESCALA_PRUEBA.artefactos,
                                                                 costo.ESCALA_PRUEBA.qc_estaciones))
        self.assertEqual(qc["filas_anchas"], qc["horas_dato"])
        self.assertAlmostEqual(qc["ms_por_hora"], qc["pared_s"] * 1000 / qc["horas_dato"])
        self.assertEqual(len(qc["memoria_por_meses"]), 2)
        self.assertGreater(qc["anchas_tablas"]["bytes_por_fila"], 0)
        pl = pts["pliegue"]
        self.assertEqual(pl["estaciones"], costo.ESCALA_PRUEBA.estaciones)
        self.assertGreater(pl["pliegue_p1"]["pared_s"], 0)
        self.assertGreaterEqual(pl["prueba_p1"], pl["prueba"])
        # ORQ-42: la selección guarda el fondo sólo de los días de selección (≈ 1/11), por la receta de la corrida
        fondo = pl["filas_campos_estaciones"]
        self.assertLess(fondo["guardado"], fondo["entero"] / (self.U.a("SEL_MOD") - 1))
        self.assertGreater(fondo["guardado"], 0)
        self.assertEqual(pl["bytes"]["filas_estaticos"], costo.ESCALA_PRUEBA.celdas_grilla)
        for nombre in ("tf", "m5", "grilla"):                            # ORQ-44: la ligera, sin el fondo
            self.assertEqual(pts[nombre]["bytes"]["campos_estaciones"], 0, nombre)
            self.assertEqual(pts[nombre]["estaciones"], costo.ESCALA_PRUEBA.estaciones, nombre)
        self.assertGreater(pl["pliegues_p2"], 1)
        self.assertGreater(pl["evaluaciones"], 0)
        self.assertEqual(pl["pliegues_p1"], self.U.a("P1_PLIEGUES"))
        self.assertGreater(pl["representatividad_s"], 0)
        self.assertGreater(pl["residuos_tablas"]["codificar_s_por_fila"], 0)
        self.assertGreaterEqual(pl["bytes"]["cache_series"], 0)          # COS-15: la caché (r̄), medida
        tf = pts["tf"]
        for pasada in costo.PASADAS:
            meses = tf["pasadas"][pasada]["meses"]
            self.assertEqual([x["mes"] for x in meses], list(costo.ESCALA_PRUEBA.meses_tf))
            self.assertEqual({x["redes"] for x in meses}, {2, 3})
            self.assertGreater(tf["pasadas"][pasada]["e0"], 0)            # la TF medida lleva la finitud de E0
            self.assertTrue(all(x["finitud_e0"] == tf["pasadas"][pasada]["e0"] for x in meses))
            redes = tf["pasadas"][pasada]["redes"]                       # H6: los tamaños de las redes
            self.assertGreater(redes["historica"], 0)
            self.assertGreater(redes["constante"], 0)
        for cand in ("C", "C_est"):                                     # C y C_est en las celdas (CAN-18, TEN-14)
            self.assertGreater(tf["c_en_celdas"][cand]["pared_s"], 0)
        m5 = pts["m5"]
        self.assertEqual(set(m5["pixeles_producto"]), set(costo._barrido("ambiental")))
        self.assertEqual(set(m5["salud"]["agudo"]), set(costo._barrido("agudo")))
        self.assertEqual(set(m5["salud"]["cronico"]), set(costo._barrido("cronico")))
        self.assertTrue(all(x["agregacion_s"] > 0 for x in m5["salud"]["agudo"].values()))
        self.assertGreater(m5["lluvia"]["pared_s"], 0)
        self.assertGreater(m5["operador_salud"]["celdas"], 0)
        self.assertFalse(m5["operador_salud"]["real"])
        gr = pts["grilla"]
        self.assertEqual(set(gr["configuraciones"]), set(costo._barrido("ambiental")))
        self.assertGreater(gr["operador_mayor"]["bytes"], gr["configuraciones"]["base"]["operador_bytes"] - 1)
        self.assertEqual(gr["celdas_medidas"], costo.ESCALA_PRUEBA.celdas_grilla)
        self.assertGreater(self.m["sistema"]["memoria_fisica_bytes"], 0)

    def test_proyeccion_de_la_medicion_minima(self):
        """La proyección corre sobre una medición de verdad: horas finitas, el veredicto «pendiente» (no es la de §8.1
        ni trae el mes real ni la contención) y la memoria."""
        p = self.p
        self.assertFalse(p["m34"]["completa"])
        self.assertEqual(set(p["m34"]["faltan"]), {"lectura_mes", "contencion"})
        for nombre, f in p["m34"]["fases"].items():
            self.assertTrue(math.isfinite(f["pared_h"]) and f["pared_h"] >= 0, nombre)
        self.assertEqual(costo.recorte(p, self.U), costo.PENDIENTE)
        self.assertFalse(p["veredicto"]["decide"])
        self.assertGreater(p["m5"]["pared_h"], 0)
        self.assertEqual(set(p["grilla_v2"]["variantes"]), set(costo.VARIANTES))
        self.assertGreater(p["m6"]["celda_horas"], 0)
        self.assertTrue({"seleccion", "tf", "m5", "grilla", "control_de_calidad"} <= set(p["memoria"]["fases"]))

    def test_contenido_de_costo_m1_pasa_la_guarda(self):
        """``costo_m1.json`` es resumen (CEG-20): pasa ``ceguera.vigilar_salida``, sin rutas absolutas, sin la carpeta
        de usuario ni arroba, JSON estricto (sin NaN), con el recorte «pendiente» marcado."""
        contenido = costo.contenido_costo(self.m, self.p, self.U)
        ceguera.vigilar_salida("costo_m1.json", contenido, clase="resumen")
        texto = json.dumps(contenido, ensure_ascii=False, allow_nan=False)
        self.assertNotIn("/" + "Users" + "/", texto)
        self.assertNotIn(chr(64), texto)
        self.assertNotIn(str(Path.home()), texto)
        self.assertTrue(entorno.sin_datos_privados(texto))

        def textos(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    yield k
                    yield from textos(v)
            elif isinstance(x, list):
                for v in x:
                    yield from textos(v)
            elif isinstance(x, str):
                yield x
        self.assertEqual([t for t in textos(contenido) if t.startswith("/")], [])
        self.assertEqual((contenido["recorte"], contenido["recorte_pendiente"]), (costo.PENDIENTE, True))
        self.assertEqual(contenido["procesos_por_fase"], contenido["proyeccion"]["procesos_por_fase"])     # A39
        self.assertEqual({c: set(fs) for c, fs in contenido["procesos_por_fase"].items()},
                         {c: set(fs) for c, fs in orquestacion.FASES_REPARTO.items()})
        self.assertEqual(contenido["procesos_por_fase"]["m5"]["representatividad"], 0)     # sin el mes real (COS-25)
        self.assertTrue(contenido["veredicto"]["motivos"])
        self.assertEqual(contenido["lecturas"], [f"COS-{n}" for n in range(1, len(costo.LECTURAS) + 1)])
        malo = copy.deepcopy(contenido)
        malo["mediciones"]["fondo_prueba"] = 1
        with self.assertRaises(ceguera.SalidaProhibida):
            ceguera.vigilar_salida("costo_m1.json", malo, clase="resumen")

    def test_un_punto_y_la_contencion_en_trabajadores(self):
        """COS-3, COS-20: con ``aislar`` cada punto corre en un trabajador propio, y la contención en P copias a la
        vez (aquí P = 2)."""
        with tempfile.TemporaryDirectory() as tmp:
            m = costo.medir(entorno.rutas_sinteticas(tmp), real_era5=False, umbrales=self.U,
                            temporal=Path(tmp) / "costo", escala=costo.ESCALA_PRUEBA, aislar=True,
                            puntos=("tf", "contencion"), procesos=2)
        self.assertTrue(m["aislada"])
        r = m["puntos"]["tf"]
        self.assertEqual(set(r["pasadas"]), set(self.m["puntos"]["tf"]["pasadas"]))
        self.assertNotIn("pid", r)
        c = m["puntos"]["contencion"]
        self.assertEqual((c["procesos"], len(c["copias_s"])), (2, 2))
        self.assertGreaterEqual(c["factor"], 1.0)


class PruebasCaminoReal(unittest.TestCase):
    def test_camino_real_con_insumos_sinteticos(self):
        """El camino de ``real_era5=True`` (COS-4, COS-10, COS-21) con los seis puntos, cada uno en su trabajador y
        bajo su propio registro en bloqueo, sobre un árbol sintético con la anidación real: la geometría de
        ``GRILLA/celdas.parquet`` y la huella y la lectura de ``ERA5L/mensual/era5land_202401_chile_pixeles.nc``; cada
        punto lee sólo lo suyo."""
        import numpy as np
        import pandas as pd
        U = _umbrales()
        with tempfile.TemporaryDirectory() as tmp:
            rutas = entorno.rutas_sinteticas(tmp)
            n = 400
            k = np.arange(n)
            celdas = pd.DataFrame({"celda": (k + 7).astype(np.int64), "lat": -33.0 - 0.01 * (k // 20),
                                   "lon": -71.0 + 0.01 * (k % 20),
                                   "cod_comuna": np.where(k % 5 == 0, 0, 13101 + k // 40), "otra": 1.0})
            celdas.to_parquet(rutas.grilla / "celdas.parquet", index=False)
            cat = sintetico.catalogo_pixeles(-32.9, -71.2, 6, 6)
            pid = cat["pixel_id"].to_numpy()
            t = sintetico.horas_del_mes(2024, 1)
            forma = (t.size, pid.size)
            campos = {"t2m": np.full(forma, 290.0), "d2m": np.full(forma, 280.0), "sp": np.full(forma, 95000.0),
                      "u10": np.ones(forma), "v10": np.ones(forma),
                      "tp": sintetico.tp_acumulado(t, np.full(forma, 1e-4))}
            ruta_mes = costo.ruta_mes_real(rutas)
            sintetico.mes_era5_netcdf(ruta_mes, campos, t, pid)
            m = costo.medir(rutas, real_era5=True, umbrales=U, temporal=Path(tmp) / "costo",
                            escala=costo.ESCALA_PRUEBA, aislar=True,
                            puntos=("qc", "pliegue", "tf", "m5", "grilla", "mes_real"))
        lecturas = {k: v["lecturas_reales"] for k, v in m["puntos"].items()}
        self.assertEqual(lecturas, {"qc": [], "pliegue": [], "tf": ["celdas.parquet"], "m5": ["celdas.parquet"],
                                    "grilla": ["celdas.parquet"], "mes_real": [ruta_mes.name]})
        r = m["puntos"]["mes_real"]
        self.assertEqual((r["pixeles"], r["horas"]), (pid.size, t.size))
        self.assertGreater(r["bytes"], 0)
        self.assertEqual(m["puntos"]["tf"]["celdas"], costo.ESCALA_PRUEBA.celdas_tf)
        self.assertTrue(m["puntos"]["m5"]["operador_salud"]["real"])
        self.assertEqual(m["puntos"]["m5"]["operador_salud"]["celdas"], int((celdas["cod_comuna"] > 0).sum()))
        self.assertFalse(m["a_escala"])
        p = costo.proyectar(m, U)
        self.assertNotIn("lectura_mes", p["sin_medir"])

    def test_celdas_sorteadas_con_comuna(self):
        """COS-4: las celdas pobladas se sortean con la semilla entre las de ``cod_comuna`` > 0, sin repetir, en orden
        de celda, con un w_ghs sintético > 0; el sorteo es el mismo dos veces."""
        import numpy as np
        import pandas as pd
        U = _umbrales()
        k = np.arange(1000)
        base = pd.DataFrame({"celda": k + 1, "lat": -33.0 - 0.001 * k, "lon": -71.0 + 0.0 * k,
                             "cod_comuna": np.where(k % 3 == 0, 0, 13101)})
        ctx = {"U": U, "escala": costo.ESCALA_PRUEBA, "rutas": None, "real_era5": True}
        with mock.patch.object(costo, "_leer_celdas_reales", return_value=base):
            a = costo._celdas(ctx, 300, pobladas=True, semilla="tf")
            b = costo._celdas(ctx, 300, pobladas=True, semilla="tf")
        self.assertEqual(len(a), 300)
        self.assertTrue((a["cod_comuna"] > 0).all())
        self.assertTrue(a["celda"].is_unique and a["celda"].is_monotonic_increasing)
        self.assertTrue((a["w_ghs"] > 0).all())
        pd.testing.assert_frame_equal(a, b)


if __name__ == "__main__":
    unittest.main()
