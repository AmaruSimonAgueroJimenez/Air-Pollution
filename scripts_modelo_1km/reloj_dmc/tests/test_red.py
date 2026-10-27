"""Pruebas de red.py (controles A1 a A7, calibración de E3t, G-dup, cambio del portal y descripción).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Las evidencias se arman a mano con los
esquemas de tipos (métricas de E3 y E4, estados largos, meses y horas); ningún dato es real. Los umbrales
son los anclados en C0 (umbrales.cargar_c0); si faltan el texto o el JSON, las pruebas se omiten y no se
dan por aprobadas. Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import decision, red, tablas, umbrales  # noqa: E402
from reloj_dmc.tipos import (ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_GUARDAS, ESQUEMA_HORAS,  # noqa: E402
                             ESQUEMA_MARCAS, ESQUEMA_MES, ESQUEMA_METRICAS_E2, ESQUEMA_METRICAS_E3,
                             ESQUEMA_METRICAS_E4, ESQUEMA_RACHAS, Conjunto, ConsecuenciasRed, DecisionAnio,
                             Estado, EvidenciaEstacion, InfoEstacion, Linea, ModoE3t, MotivoAnio, Nivel, Regimen,
                             Regla, ResultadoGuarda, Territorio, Veredicto, tabla_vacia)

_APH = Path(umbrales.__file__).resolve().parents[2].parent / "Air-Pollution-Health-Chile"
U = None
CAL = None


def setUpModule():
    global U, CAL
    for ruta in (_APH / umbrales.PROTOCOLO_C0, _APH / umbrales.JSON_C0):
        if not ruta.is_file():
            raise unittest.SkipTest(f"falta {ruta.name} anclado en C0; la prueba no se da por aprobada")
    U = umbrales.cargar_c0(_APH)
    CAL = tablas.cargar_tablas()


C, I, D, S = Estado.COMPATIBLE, Estado.INCOMPATIBLE, Estado.DUDOSA, Estado.SIN_INFORMACION
F0, F3, F4, CS = "F(0)", "F(-3)", "F(-4)", "C(Santiago)"
P_CONT = (F0, F3, F4, CS)
ZS_CONT = ("America/Santiago",)
DESFASES = {"R0": {F0: 0, F3: -3, F4: -4, CS: -3}, "R1": {F0: 0, F3: -3, F4: -4, CS: -4}}   # Santiago, 2 regímenes
SOLO_F0 = {F0: C, F3: I, F4: I, CS: I}


# ---------------------------------------------------------------------------------------------
# Constructores de evidencias sintéticas
def _info(codigo, *, macrozona="centro", lat=-33.4, conjunto=Conjunto.N, tipo=None, propietario=None, region=13):
    return InfoEstacion(codigo=codigo, nombre="sintetica", lat=lat, lon=-70.6, alt_m=500.0, coordenadas_validas=True,
                        coordenadas_inconsistentes=False, territorio=Territorio.CONTINENTAL, region=region,
                        macrozona=macrozona, zs=ZS_CONT, P=tablas.hipotesis_de_P(P_CONT), pixel_id=1,
                        distancia_km=0.0, costera=False, z_pix=500.0, dz=0.0, conjunto=conjunto, tipo=tipo,
                        propietario=propietario)


def _r(r_max):
    """r(c) de c = −9 … 9 con máximo r_max en c = 0."""
    return [float(r_max) - 0.01 * abs(c) for c in range(-9, 10)]


def _fila_e3(codigo, anio, regimen, variable, *, n_pares=2000, c_cont=np.nan, c_f_cont=np.nan, r_max=0.6,
             filtro=False):
    qfe = variable == "QFE"
    return {"codigo": codigo, "anio": anio, "nivel": str(Nivel.REGIMEN), "unidad": regimen, "regimen": regimen,
            "variable": variable, "paso_h": 1, "n_pares": n_pares, "n_bloques": 40, "r": _r(r_max),
            "c_hat": None if np.isnan(c_cont) else int(round(c_cont)), "c_hat_cont": c_cont, "estab_c_hat": np.nan,
            "r_f": _r(r_max) if qfe else None, "c_hat_f": None if np.isnan(c_f_cont) else int(round(c_f_cont)),
            "c_hat_f_cont": c_f_cont, "estab_c_hat_f": np.nan, "fino": False, "filtro_e3t": bool(filtro),
            "cociente_a1": np.nan, "r_diaria": np.nan}


def _fila_e4(codigo, anio, regimen, psi2):
    return {"codigo": codigo, "anio": anio, "nivel": str(Nivel.REGIMEN), "unidad": regimen, "regimen": regimen,
            "variable": "QFE", "paso_h": 1, "n_h": 24, "hueco_max_h": 1, "K": 3, "A1": 0.6, "EE_A1": 0.05,
            "phi1": 4.0, "A2": 0.8, "EE_A2": 0.05, "psi2": psi2}


def _estados(codigo, anio, linea, nivel, unidad, por_h, *, regla=Regla.UNICA, motivo=None):
    return [{"codigo": codigo, "anio": anio, "linea": str(linea), "regla": str(regla), "nivel": str(nivel),
             "unidad": unidad, "H": h, "estado": str(e), "reloj_anomalo": False, "discordante": False,
             "motivo": motivo} for h, e in por_h.items()]


def _tabla(filas, esquema):
    return pd.DataFrame(filas, columns=list(esquema)).astype(esquema) if filas else tabla_vacia(esquema)


def _meses(codigo, meses):
    filas = []
    for i, texto in enumerate(meses):
        anio, m = (int(x) for x in texto.split("-"))
        filas.append({"codigo": codigo, "anio": anio, "mes": m, "manifiesto": f"DMC/estaciones/{codigo}/{texto}.manifest.json",
                      "manifiesto_sha256": "0" * 64, "artefacto_sha256": "1" * 64, "id_artefacto": i,
                      "script_sha256": "2" * 64, "entra": True, "motivo_exclusion": None, "row_count": 24,
                      "source_empty_slots": 0, "expected_hour_slots": 744, "n_available_hours": 744,
                      "duplicate_display_rows_removed": 0, "source_sha256": "3" * 64, "requested_start": None,
                      "requested_end": None, "campos_faltantes": [], "p_ts": 1, "p_qfe": 1, "lat_txt": None,
                      "lon_txt": None, "alt_txt": None})
    return _tabla(filas, ESQUEMA_MES)


def _evidencia(info, *, e3=(), e4=(), estados=(), guardas=(), meses=(), horas=()):
    return EvidenciaEstacion(info=info, estados=_tabla(list(estados), ESQUEMA_ESTADOS),
                             metricas_e2=tabla_vacia(ESQUEMA_METRICAS_E2), metricas_e3=_tabla(list(e3), ESQUEMA_METRICAS_E3),
                             metricas_e4=_tabla(list(e4), ESQUEMA_METRICAS_E4), eventos=tabla_vacia(ESQUEMA_EVENTOS),
                             guardas=_tabla(list(guardas), ESQUEMA_GUARDAS), marcas=tabla_vacia(ESQUEMA_MARCAS),
                             meses=_meses(info.codigo, meses), horas=_tabla(list(horas), ESQUEMA_HORAS))


def _evidencia_a3(codigo, anios, D_por_regimen, *, macrozona="centro", lat=-33.4, e4p_evaluable=True):
    """Estación con E3p filtrada evaluable y E4p evaluable en cada año-régimen; D_por_regimen(i) da D."""
    e3, e4, est = [], [], []
    i = 0
    for anio in anios:
        for reg in ("R0", "R1"):
            d = D_por_regimen(i)
            i += 1
            c_f = 0.05 * np.sin(i)                                 # F(0): ĉ^f_cont ≈ 0
            e3.append(_fila_e3(codigo, anio, reg, "QFE", c_f_cont=c_f))
            e4.append(_fila_e4(codigo, anio, reg, (c_f - d + U.f("E4P_S2_FASE_H")) % 12))
            por_h = {F0: C, F3: I, F4: I, CS: I} if e4p_evaluable else {h: S for h in P_CONT}
            est += _estados(codigo, anio, Linea.E4P, Nivel.REGIMEN, reg, por_h)
    return _evidencia(_info(codigo, macrozona=macrozona, lat=lat), e3=e3, e4=e4, estados=est)


def _evidencia_cal(codigo, anios, delta_de, *, macrozona="centro", h=F0, filtro=True, n_pares=2000,
                   e4p=SOLO_F0, e3p=None, guardas_tp=None):
    """Estación con Ts filtrada (ĉt_cont = c_H(R) + δ) y E3p (gruesa por año-régimen) y E4p anual."""
    e3p = e3p or {h2: (C if DESFASES["R0"][h2] == DESFASES["R0"][h] and DESFASES["R1"][h2] == DESFASES["R1"][h]
                       else I) for h2 in P_CONT}
    e3, est, gu = [], [], []
    for k, anio in enumerate(anios):
        d = delta_de(k)
        for reg in ("R0", "R1"):
            e3.append(_fila_e3(codigo, anio, reg, "Ts", c_cont=DESFASES[reg][h] + d, filtro=filtro, n_pares=n_pares))
            est += _estados(codigo, anio, Linea.E3P, Nivel.REGIMEN, reg, e3p, regla=Regla.GRUESA)
        est += _estados(codigo, anio, Linea.E4P, Nivel.ANIO, f"{anio:04d}", e4p)
        if guardas_tp is not None:
            gu.append({"codigo": codigo, "anio": anio, "guarda": str(Linea.TP), "H": h, "unidad": f"{anio:04d}",
                       "resultado": guardas_tp(k), "detalle": None})
    return _evidencia(_info(codigo, macrozona=macrozona), e3=e3, estados=est, guardas=gu)


ANIOS = tuple(range(2001, 2015)) + tuple(range(2016, 2027))       # 25 años con dos regímenes en Santiago


def _red_cal(n, macrozona, delta_de, *, prefijo="1"):
    """n estación-años de una macrozona, repartidos en estaciones de hasta 25 años."""
    evs, k = [], 0
    while k < n:
        anios = ANIOS[:min(len(ANIOS), n - k)]
        base = k
        evs.append(_evidencia_cal(f"{prefijo}{len(evs):05d}", anios, lambda j, b=base: delta_de(b + j),
                                  macrozona=macrozona))
        k += len(anios)
    return evs


# ---------------------------------------------------------------------------------------------
class PruebasControles(unittest.TestCase):
    def test_a1_eje_y_unidades(self):
        """Paso, huecos, HH:00 y rangos de §3.4."""
        bien = {"eje_ok": True, "mediana_t2m_K": 285.0, "mediana_sp_Pa": 95000.0, "unidades_ok": True}
        self.assertTrue(red.a1(True, {"202401": bien, "202402": SimpleNamespace(**bien)}).pasa)
        self.assertFalse(red.a1(False, {"202401": bien}).pasa)                      # C2 no cumplida
        self.assertFalse(red.a1(True, {}).pasa)                                     # sin meses controlados
        r = red.a1(True, {"202401": bien, "202402": {**bien, "eje_ok": False}})
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["eje_anomalo"], ["202402"])
        r = red.a1(True, {"202401": {**bien, "mediana_t2m_K": 12.0, "unidades_ok": False}})   # t2m en °C
        self.assertEqual((r.pasa, r.detalle["unidades_fuera_de_rango"]), (False, ["202401"]))
        r = red.a1(True, {"202401": {**bien, "mediana_sp_Pa": 950.0, "unidades_ok": True}})   # sp en hPa
        self.assertFalse(r.pasa)
        self.assertEqual(r.detalle["unidades_marca_inconsistente"], ["202401"])
        r = red.a1(True, {"202401": {**bien, "mediana_sp_Pa": float("nan"), "unidades_ok": False}})
        self.assertFalse(r.pasa)
        json.dumps(r.detalle, allow_nan=False)

    def test_a2_desde_huellas(self):
        """Huellas calculadas distintas de las ancladas. Con la Enmienda 3 (E3-2) el control A2 incluye el
        Anexo A3 (eventos de regla vencida)."""
        self.assertTrue(red.a2(CAL.sha256_anexo_a, CAL.sha256_anexo_a2, CAL.sha256_anexo_a3).pasa)
        alterada = {z: [list(f) for f in filas] for z, filas in CAL.anexo_a.items()}
        alterada["America/Santiago"].pop()
        sha_alterada = tablas._sha256(tablas.serializar_anexo_a(alterada))
        r = red.a2(sha_alterada, CAL.sha256_anexo_a2, CAL.sha256_anexo_a3)
        self.assertFalse(r.pasa)
        self.assertFalse(r.detalle["anexo_a"]["reproduce"])
        self.assertTrue(r.detalle["anexo_a2"]["reproduce"])
        self.assertTrue(r.detalle["anexo_a3"]["reproduce"])
        self.assertFalse(red.a2(CAL.sha256_anexo_a, "0" * 64, CAL.sha256_anexo_a3).pasa)
        r3 = red.a2(CAL.sha256_anexo_a, CAL.sha256_anexo_a2, "0" * 64)
        self.assertFalse(r3.pasa)
        self.assertEqual(r3.detalle["anexo_a3"], {"calculada": "0" * 64, "anclada": tablas.SHA_ANEXO_A3,
                                                  "reproduce": False})
        json.dumps(r3.detalle, allow_nan=False)

    def test_a3_nacional_y_por_macrozona(self):
        """Consecuencias: E4p no excluye ni es Q, fina apagada, E3t restringida."""
        bien = lambda i: 0.1 * np.sin(i)  # noqa: E731
        evs = [_evidencia_a3(f"10{k:04d}", range(2001, 2021), bien) for k in range(15)]      # 600 años-régimen
        evs.append(_evidencia_a3("200001", range(2001, 2016), lambda i: 2.0 if i < 4 else 0.0, macrozona="sur"))
        evs.append(_evidencia_a3("300001", range(2001, 2021), lambda i: 3.0, macrozona="austral", lat=-53.0))
        evs.append(_evidencia_a3("400001", range(2001, 2021), lambda i: 3.0, macrozona="norte", e4p_evaluable=False))
        m = red.muestra_a3(evs, U)
        self.assertEqual(len(m), 630)                               # sin |lat| > 50° ni E4p sin información
        self.assertTrue(((m["D"] >= -6) & (m["D"] < 6)).all())
        cons, det = red.controles_red(evs, ["centro", "sur", "austral", "norte"], U, calendario=CAL)
        self.assertFalse(cons.a3_falla_pais)
        self.assertEqual(cons.a3_fallan_macrozonas, frozenset({"sur"}))       # 26/30 < 0,90
        self.assertAlmostEqual(det["A3"]["macrozonas"]["sur"]["frac_dentro"], 26 / 30)
        self.assertFalse(det["A3"]["macrozonas"]["sur"]["frac_dentro"] >= U.f("A3_FRAC_MACRO"))
        self.assertFalse(cons.e4p_activa("sur"))
        self.assertFalse(cons.fina_activa("sur"))
        self.assertEqual(cons.modo_e3t_en("sur"), ModoE3t.RESTRINGIDO)
        for mz in ("centro", "austral", "norte"):
            self.assertTrue(cons.e4p_activa(mz) and cons.fina_activa(mz), mz)
        self.assertNotIn("austral", det["A3"]["macrozonas"])          # RED-1: sin muestra, no se evalúa ni falla
        json.dumps({k: v for k, v in det.items() if k != "tablas"}, allow_nan=False)

        # Falla en el país (≥ 5 % fuera): todo el país pierde E4p y la fina, y E3t queda restringida.
        evs2 = [_evidencia_a3(f"10{k:04d}", range(2001, 2021), lambda i: 2.0 if i % 10 == 0 else 0.0)
                for k in range(15)]
        falla, fallan, det2 = red.a3(red.muestra_a3(evs2, U), U)
        self.assertTrue(falla)
        self.assertEqual(det2["pais"]["frac_dentro"], 0.9)
        cons2 = ConsecuenciasRed(a3_falla_pais=falla, a3_fallan_macrozonas=fallan, a5_alto=False,
                                 modo_e3t={"centro": ModoE3t.COMPLETO}, a4_restringe=False)
        self.assertFalse(cons2.e4p_activa("centro") or cons2.fina_activa("norte"))
        self.assertEqual(cons2.modo_e3t_en("centro"), ModoE3t.RESTRINGIDO)

        # Mediana corrida: |D| ≤ 1 h en todo, pero |mediana| = 0,5 h > 0,30 h.
        evs3 = [_evidencia_a3(f"10{k:04d}", range(2001, 2003), lambda i: 0.5) for k in range(10)]
        falla3, _, det3 = red.a3(red.muestra_a3(evs3, U), U)
        self.assertTrue(falla3)
        self.assertEqual(det3["pais"]["frac_dentro"], 1.0)
        # Con menos de 30 años-régimen no se evalúa (RED-1).
        falla4, fallan4, det4 = red.a3(red.muestra_a3(evs3[:7], U), U)
        self.assertEqual((falla4, fallan4, det4["pais"]["evaluado"]), (False, frozenset(), False))

    def test_a5_alto_no_escribe_politica(self):
        """|m| > 0,30 h con ≥ 30 años-régimen."""
        def ev(codigo, corrimiento, n_anios=10, **kw):
            e3 = [_fila_e3(codigo, a, r, "QFE", c_f_cont=c + corrimiento + 0.02 * np.cos(a), **kw)
                  for a in range(2001, 2001 + n_anios) for r, c in (("R0", -3), ("R1", -4))]
            return _evidencia(_info(codigo, tipo="aerodromo", propietario="DMC"), e3=e3)

        corrida = [ev(f"5{k:05d}", 0.5) for k in range(2)]                  # 40 años-régimen corridos 0,5 h
        m = red.muestra_a5(corrida, U)
        alto, det = red.a5(m, U)
        self.assertTrue(alto)
        self.assertAlmostEqual(abs(det["m"]), 0.5, delta=0.05)
        self.assertGreaterEqual(det["m"], -0.5)
        self.assertLess(det["m"], 0.5)
        self.assertEqual(set(det["por_tipo"]), {"aerodromo"})
        self.assertEqual(det["por_propietario"]["DMC"]["n"], 40)
        cons, det_red = red.controles_red(corrida, ["centro"], U, calendario=CAL)
        self.assertTrue(cons.a5_alto)                 # la corrida termina el informe sin escribir la política
        self.assertTrue(det_red["A5"]["alto"])
        # Sin corrimiento, o con < 30 años-régimen, no hay alto.
        self.assertFalse(red.a5(red.muestra_a5([ev(f"6{k:05d}", 0.0) for k in range(2)], U), U)[0])
        self.assertFalse(red.a5(red.muestra_a5([ev("700000", 0.5, n_anios=14)], U), U)[0])   # 28
        # La muestra deja fuera |lat| > 50°, menos de 1.000 pares y máx r^f < E3_RMAX.
        fuera = [replace(ev("800000", 0.5), info=_info("800000", lat=-53.0)),
                 ev("800001", 0.5, n_pares=999), ev("800002", 0.5, r_max=0.2)]
        self.assertEqual(len(red.muestra_a5(fuera, U)), 0)

    def test_a4_restringe_e3t(self):
        """T-P falla en > 10 % de los evaluados."""
        def decisiones(fallan, pasan, no_eval=50):
            ds = []
            for k, r in enumerate([ResultadoGuarda.FALLA] * fallan + [ResultadoGuarda.PASA] * pasan
                                  + [ResultadoGuarda.NO_EVALUABLE] * no_eval):
                ds.append(DecisionAnio(codigo=f"{k:06d}", anio=2019, P=P_CONT, clases=P_CONT, excluidas={}, K=(F0,),
                                       veredicto=Veredicto.CONFIRMADO, guardas={str(Linea.TP): str(r)}))
            ds.append(DecisionAnio(codigo="999999", anio=2019, P=P_CONT, clases=P_CONT, excluidas={}, K=(F0, F3),
                                   veredicto=Veredicto.INSUFICIENTE, guardas={str(Linea.G_VERSION): "pasa"}))
            return ds

        restringe, det = red.a4(decisiones(11, 89), U)
        self.assertTrue(restringe)
        self.assertEqual((det["evaluados"], det["fallan"]), (100, 11))
        self.assertFalse(red.a4(decisiones(10, 90), U)[0])                  # 10 % no es «más del 10 %»
        self.assertFalse(red.a4(decisiones(0, 0), U)[0])                    # sin evaluados
        base = ConsecuenciasRed(a3_falla_pais=False, a3_fallan_macrozonas=frozenset(), a5_alto=False,
                                modo_e3t={"centro": ModoE3t.COMPLETO, "sur": ModoE3t.COMPLETO})
        con_a4 = red.fijar_a4(base, restringe)
        self.assertEqual({con_a4.modo_e3t_en(z) for z in ("centro", "sur")}, {ModoE3t.RESTRINGIDO})
        self.assertEqual(red.fijar_a4(base, False).modo_e3t_en("centro"), ModoE3t.COMPLETO)
        with self.assertRaises(ValueError):
            red.fijar_a4(con_a4, False)

    def test_a6_d1_contrario(self):
        """Deja sin confirmar dentro de su alcance; E5 inactiva → no hace nada."""
        def d(codigo, anio, veredicto, clase=None):
            return DecisionAnio(codigo=codigo, anio=anio, P=P_CONT, clases=P_CONT, excluidas={}, K=(clase,) if clase else (),
                                veredicto=veredicto, clase_confirmada=clase)

        decisiones = [d("330020", 2012, Veredicto.CONFIRMADO, F4), d("330020", 2013, Veredicto.CONFIRMADO, F0),
                      d("330020", 2016, Veredicto.CONFIRMADO, F4), d("330020", 2014, Veredicto.DISCREPANTE),
                      d("270001", 2012, Veredicto.CONFIRMADO, F4), d("330021", 2015, Veredicto.CONFIRMADO, "F(-3)|C(Santiago)")]
        ruta = _APH / "auditoria/20261023/reloj_dmc/c0/registro_documental.jsonl"
        if ruta.is_file():                                        # el registro sellado en C0: todo pendiente
            registro_c0 = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
        else:
            registro_c0 = [{"id": "DOC-01", "nivel": None, "estado": "pendiente", "cita_literal": None}]
        self.assertEqual(red.a6(registro_c0, decisiones), [])
        d1 = {"id": "DOC-12", "nivel": "D1", "estado": "registrado", "cita_literal": "«La hora es UTC»",
              "reloj_declarado": "F(0)", "alcance": {"estaciones": ["330020", "330021"], "anio_desde": 2010,
                                                     "anio_hasta": "2015-12-31"}}
        d2 = {**d1, "id": "DOC-05", "nivel": "D2", "reloj_declarado": "F(-4)"}
        # 2015 fusionado en F(−3)|C(Santiago) no contiene F(0): también lo contradice; 2016 queda fuera del alcance.
        self.assertEqual(red.a6([d1, d2], decisiones), [("330020", 2012), ("330021", 2015)])
        # Sin alcance, vale para toda la red y todos los años; un reloj civil contenido en una fusión no contradice.
        d1b = {**d1, "reloj_declarado": "C(Santiago)", "alcance": None}
        self.assertEqual(red.a6([d1b], decisiones),
                         [("270001", 2012), ("330020", 2012), ("330020", 2013), ("330020", 2016)])
        with self.assertRaises(ValueError):
            red.a6([{**d1, "cita_literal": ""}], decisiones)
        with self.assertRaises(ValueError):
            red.a6([{**d1, "reloj_declarado": "C(America/Easter)"}], decisiones)

    def test_a7_resume_fallas(self):
        """A7 resume las fallas de §7.3; sin fallas, pasa."""
        self.assertTrue(red.a7([]).pasa)
        r = red.a7(["330020: hora UTC repetida"])
        self.assertEqual((r.control, r.pasa, r.detalle["n"]), ("A7", False, 1))

    def test_g_dup_lista_casos(self):
        """Estación y mes de la URL; marca atraso de Zs."""
        url = "https://climatologia.meteochile.gob.cl/application/mensualb/hojaMensualDatos/{}/{}/{}"
        with tempfile.TemporaryDirectory() as tmp:
            progreso = Path(tmp) / "progreso.json"
            progreso.write_text(json.dumps({"status": "blocked_source", "error_type": "SourceError",
                                            "error": f"{red.MENSAJE_GDUP}. URL={url.format('330020', 2019, 4)}; "
                                                     "response_utf8_sha256=" + "a" * 64}, ensure_ascii=False),
                                encoding="utf-8")
            bitacora = Path(tmp) / "stdout_20261016.log"
            bitacora.write_text("inicio\n"
                                f"SourceError: {red.MENSAJE_GDUP}. URL={url.format('270001', 2019, 9)}; x\n"
                                f"SourceError: {red.MENSAJE_GDUP}.\n"
                                "fin sin errores\n", encoding="utf-8")
            casos = red.g_dup([progreso, bitacora], CAL, zs_de={"270001": ("Pacific/Easter", "America/Santiago")})
        self.assertEqual(len(casos), 3)
        c0, c1, c2 = (casos.iloc[i] for i in range(3))
        self.assertEqual((c0["archivo"], c0["codigo"], c0["mes"]), ("progreso.json", "330020", "2019-04"))
        self.assertTrue(c0["atraso_en_zs"])                        # 2019-04-06 23:00 repetida en Santiago
        self.assertEqual(c0["url"], url.format("330020", 2019, 4))
        self.assertEqual((c1["codigo"], c1["mes"], bool(c1["atraso_en_zs"])), ("270001", "2019-09", False))
        self.assertTrue(pd.isna(c2["codigo"]) and pd.isna(c2["atraso_en_zs"]))
        self.assertFalse(any("/Users/" in str(v) for v in casos["archivo"]))
        # Una ruta bajo /Volumes se rechaza sin consultarla (§8, prueba 27): con un registro propio en bloqueo, el
        # rechazo es el de g_dup y no hay ningún acceso (antes, os.lstat y os.stat de la ruta al resolverla).
        from reloj_dmc import verificar_reloj_dmc as V
        with V.RegistroAccesos((V.VOLUMES,), bloquear=True) as registro:
            with self.assertRaisesRegex(PermissionError, "G-dup lee sólo las copias de C2"):
                red.g_dup([Path("/Volumes/Datos/progreso.json")], CAL)
        self.assertEqual(registro.accesos, [])


class PruebasCalibracion(unittest.TestCase):
    def test_calibracion_e3t_por_macrozona(self):
        """Completo si ≥ 30 estación-años y ≤ 1 % con |δt| > 1 h; no hereda."""
        pequenio = lambda k: 0.3 * np.sin(k)  # noqa: E731
        evs = (_red_cal(40, "centro", pequenio, prefijo="1")
               + _red_cal(25, "norte", pequenio, prefijo="2")                                   # < 30
               + _red_cal(100, "sur", lambda k: 1.5 if k == 7 else pequenio(k), prefijo="3")     # 1 %
               + _red_cal(100, "austral", lambda k: 1.5 if k in (7, 8) else pequenio(k), prefijo="4"))   # 2 %
        cons, det = red.controles_red(evs, ["centro", "norte", "sur", "austral", "insular"], U, calendario=CAL)
        modos = det["calibracion_e3t"]["modos"]
        self.assertEqual(modos, {"austral": "restringido", "centro": "completo", "insular": "restringido",
                                 "norte": "restringido", "sur": "completo"})
        res = det["calibracion_e3t"]["por_macrozona"]
        self.assertEqual((res["centro"]["n"], res["norte"]["n"], res["sur"]["n_fuera"]), (40, 25, 1))
        self.assertEqual(cons.modo_e3t_en("centro"), ModoE3t.COMPLETO)
        self.assertEqual(cons.modo_e3t_en("norte"), ModoE3t.RESTRINGIDO)       # no hereda la nacional
        self.assertEqual(cons.modo_e3t_en("otra"), ModoE3t.RESTRINGIDO)
        tabla = det["tablas"]["calibracion_e3t"]
        self.assertEqual(len(tabla), 265)
        self.assertEqual(int(tabla["fuera"].sum()), 3)
        # Donde falla A3 queda restringida aunque la calibración la habilite; en el país, todas.
        mc = red.muestra_calibracion_e3t(evs, False, frozenset({"centro"}), U, calendario=CAL)
        self.assertEqual(red.calibrar_e3t(mc, False, frozenset({"centro"}), ["centro"], U)[0]["centro"],
                         ModoE3t.RESTRINGIDO)
        self.assertEqual(set(red.calibrar_e3t(mc, True, frozenset(), ["centro", "sur"], U)[0].values()),
                         {ModoE3t.RESTRINGIDO})

    def test_calibracion_muestra(self):
        """c_H(R) por régimen (C(Santiago): −3 y −4); filtro, pares, E4p y H ambigua; estado de T-P."""
        ev_civil = _evidencia_cal("110001", (2018, 2019), lambda k: 0.2, h=CS, e4p={F0: I, F3: C, F4: C, CS: C},
                                  guardas_tp=lambda k: "falla" if k == 0 else "pasa")
        ev_filtro = _evidencia_cal("110002", (2019,), lambda k: 0.2, filtro=False)
        ev_pares = _evidencia_cal("110003", (2019,), lambda k: 0.2, n_pares=999)
        ev_sin_e4p = _evidencia_cal("110004", (2019,), lambda k: 0.2, e4p={h: S for h in P_CONT})
        ambigua = {F0: I, F3: C, F4: I, CS: C}                  # E3p y E4p compatibles con F(−3) y C(Santiago)
        ev_ambigua = _evidencia_cal("110005", (2019,), lambda k: 0.2, h=F3, e3p=ambigua, e4p=ambigua)
        m = red.muestra_calibracion_e3t([ev_civil, ev_filtro, ev_pares, ev_sin_e4p, ev_ambigua], False, frozenset(), U,
                                        calendario=CAL)
        self.assertEqual(list(m["codigo"]), ["110001", "110001", "110005"])
        self.assertEqual(list(m["H"].iloc[:2]), [CS, CS])
        self.assertTrue(np.allclose(m["delta_t"].iloc[:2], 0.2))       # (−3 + 0,2) − (−3) y (−4 + 0,2) − (−4)
        self.assertEqual(list(m["tp"].iloc[:2]), ["falla", "pasa"])
        self.assertEqual(m["H"].iloc[2], "F(-3)|C(Santiago)")
        self.assertTrue(np.isnan(m["delta_t"].iloc[2]))
        self.assertEqual(m["motivo"].iloc[2], red.MOTIVO_H_AMBIGUA)
        # Las clases de la evidencia, si existen, dan c_H(R) igual que el calendario.
        regs = tablas.regimenes_del_anio(ZS_CONT, 2019, CAL)
        ev_civil.clases = {2019: tablas.fusionar(tablas.hipotesis_de_P(P_CONT), regs, ZS_CONT),
                           2018: tablas.fusionar(tablas.hipotesis_de_P(P_CONT), tablas.regimenes_del_anio(ZS_CONT, 2018, CAL),
                                                 ZS_CONT)}
        m2 = red.muestra_calibracion_e3t([ev_civil], False, frozenset(), U)
        pd.testing.assert_frame_equal(m2, m.iloc[:2].reset_index(drop=True))

    def test_p22_sesgo_termico_restringe_e3t(self):
        """Sesgo de +2,5 h en la referencia: restringida."""
        aerodromo = _aerodromo_utc("990001")
        regs = tablas.regimenes_del_anio(ZS_CONT, 2019, CAL)
        clases = tablas.fusionar(tablas.hipotesis_de_P(P_CONT), regs, ZS_CONT)
        resultados = {}
        for sesgo in (0.0, 2.5):
            evs = _red_cal(40, "centro", lambda k, s=sesgo: s + 0.2 * np.sin(k)) + [aerodromo]
            cons, det = red.controles_red(evs, ["centro"], U, calendario=CAL)
            cons = red.fijar_a4(cons, False)
            dec = decision.decidir_anio(aerodromo, 2019, cons, U, clases=clases)
            resultados[sesgo] = (cons.modo_e3t_en("centro"), dec.veredicto, dec.motivo)
            self.assertNotIn("990001", set(det["tablas"]["calibracion_e3t"]["codigo"]))   # sin E4p: fuera de la muestra
        self.assertEqual(resultados[2.5], (ModoE3t.RESTRINGIDO, Veredicto.INSUFICIENTE, MotivoAnio.APOYO))
        # Control: sin sesgo, la calibración habilita E3t y el mismo aeródromo se confirma con E3p y E3t.
        self.assertEqual(resultados[0.0], (ModoE3t.COMPLETO, Veredicto.CONFIRMADO, None))


def _aerodromo_utc(codigo, anio=2019):
    """Aeródromo UTC sin E4p (§8.C.16): E3p excluye las rivales a ≥ 3 h, E2 y E1a no separan F(0) de F(−3);
    sólo E3t (en modo completo) da el segundo apoyo contra F(−3)."""
    est = []
    for reg in ("R0", "R1"):
        est += _estados(codigo, anio, Linea.E3P, Nivel.REGIMEN, reg, SOLO_F0, regla=Regla.GRUESA)
    for m in range(1, 13):
        est += _estados(codigo, anio, Linea.E3P, Nivel.PARTE, f"{anio:04d}-{m:02d}-1", SOLO_F0, regla=Regla.GRUESA)
    est += _estados(codigo, anio, Linea.E3T, Nivel.ANIO, f"{anio:04d}", SOLO_F0, regla=Regla.GRUESA)
    est += _estados(codigo, anio, Linea.E2, Nivel.ANIO, f"{anio:04d}", {F0: C, F3: C, F4: I, CS: I})
    est += _estados(codigo, anio, Linea.E1A, Nivel.ANIO, f"{anio:04d}", {F0: C, F3: C, F4: C, CS: I})
    est += _estados(codigo, anio, Linea.E4P, Nivel.ANIO, f"{anio:04d}", {h: S for h in P_CONT})
    return _evidencia(_info(codigo), estados=est, meses=[f"{anio:04d}-{m:02d}" for m in range(1, 13)])


# ---------------------------------------------------------------------------------------------
def _estacion_desc(codigo, *, conjunto=Conjunto.N, clases=(F0, F0), veredictos=None, macrozona="centro",
                   propietario="DMC", horas_mes=700, motivos=None):
    anios = (2019, 2020)
    veredictos = veredictos or (Veredicto.CONFIRMADO,) * len(anios)
    meses = [f"{a:04d}-{m:02d}" for a in anios for m in range(1, 13)]
    horas = [{"codigo": codigo, "anio": a, "mes": m, "horas_ts_o_qfe": horas_mes} for a in anios for m in range(1, 13)]
    ev = _evidencia(_info(codigo, conjunto=conjunto, macrozona=macrozona, propietario=propietario), meses=meses,
                    horas=horas)
    decs = []
    for i, (a, v) in enumerate(zip(anios, veredictos)):
        clase = clases[i] if v == Veredicto.CONFIRMADO else None
        decs.append(DecisionAnio(codigo=codigo, anio=a, P=P_CONT, clases=P_CONT, excluidas={},
                                 K=(clase,) if clase else (), veredicto=v, clase_confirmada=clase,
                                 motivo=(motivos or {}).get(a)))
    regla = {mes: clases[anios.index(int(mes[:4]))] for mes in meses
             if veredictos[anios.index(int(mes[:4]))] == Veredicto.CONFIRMADO}
    return ev, decs, regla


def _red_desc(especiales=None, n=30):
    evs, decs, regla = [], [], {}
    for k in range(n):
        codigo = f"{330000 + k:06d}"
        ev, ds, rg = _estacion_desc(codigo, **(especiales or {}).get(k, {}))
        evs.append(ev)
        decs += ds
        regla[codigo] = rg
    return evs, decs, regla


class PruebasDescripcion(unittest.TestCase):
    def test_descripcion_red_solo_n(self):
        """Sólo N y con ≥ 30 estaciones; «red en UTC» con las tres condiciones."""
        rachas = tabla_vacia(ESQUEMA_RACHAS)
        evs, decs, regla = _red_desc()
        ev_v, decs_v, regla_v = _estacion_desc("270001", conjunto=Conjunto.V, clases=(F4, F4))
        d = red.describir_red(decs + decs_v, rachas, evs + [ev_v], U, meses_con_regla={**regla, "270001": regla_v})
        self.assertTrue(d["aplica"])
        self.assertEqual(d["n_estaciones_con_datos"], 30)                    # la estación de V no cuenta
        self.assertEqual(d["denominadores"]["estacion_horas"], 30 * 24 * 700)
        self.assertEqual(d["red"]["confirmadas_solo_F0"]["prop_estaciones"], 1.0)
        self.assertTrue(d["red_en_utc"])
        json.dumps(d, allow_nan=False)
        # 29 estaciones de N con datos: no hay descripción.
        self.assertFalse(red.describir_red(decs[2:], rachas, evs[1:], U, meses_con_regla=regla)["aplica"])
        # Sin meses con regla no se afirma.
        self.assertFalse(red.describir_red(decs, rachas, evs, U)["red_en_utc"])
        # Una estación de N confirmada en otro reloj.
        e, ds, rg = _red_desc({0: {"clases": (F0, F4)}})
        d = red.describir_red(ds, rachas, e, U, meses_con_regla=rg)
        self.assertFalse(d["red_en_utc"])
        self.assertEqual(d["red"]["confirmadas_en_otro_reloj"]["estaciones"], 1)
        self.assertFalse(d["condiciones_red_en_utc"]["ninguna_en_otro_reloj"]["cumple"])
        # Discrepantes: 3 de 60 (5 %) cumple; 4 de 60, no.
        disc = {"veredictos": (Veredicto.DISCREPANTE, Veredicto.CONFIRMADO)}
        e, ds, rg = _red_desc({k: disc for k in range(3)})
        d = red.describir_red(ds, rachas, e, U, meses_con_regla=rg)
        self.assertTrue(d["red_en_utc"])                 # 54/60 de las horas en F(0) = 90 %
        self.assertEqual(d["red"]["con_algun_anio_discrepante"]["estaciones"], 3)
        e, ds, rg = _red_desc({k: disc for k in range(4)})
        self.assertFalse(red.describir_red(ds, rachas, e, U, meses_con_regla=rg)["red_en_utc"])
        # Estación-horas en tramos F(0) bajo el 80 %: siete estaciones sin confirmar con muchas horas.
        sin = {"veredictos": (Veredicto.INSUFICIENTE, Veredicto.INSUFICIENTE), "horas_mes": 1000}
        e, ds, rg = _red_desc({k: sin for k in range(7)})
        d = red.describir_red(ds, rachas, e, U, meses_con_regla=rg)
        self.assertFalse(d["red_en_utc"])
        self.assertAlmostEqual(d["condiciones_red_en_utc"]["horas_en_tramos_F0"]["valor"], 23 * 700 / (23 * 700 + 7000))
        self.assertEqual(d["red"]["sin_ningun_anio_confirmado"]["estaciones"], 7)
        # Inestable: por motivo de la decisión, y por discrepantes aunque no tenga años confirmados.
        inest = {"veredictos": (Veredicto.SIN_CONFIRMAR, Veredicto.SIN_CONFIRMAR),
                 "motivos": {2019: MotivoAnio.INESTABLE, 2020: MotivoAnio.INESTABLE}}
        e, ds, rg = _red_desc({0: inest, 1: {"macrozona": "sur", "propietario": None}})
        d = red.describir_red(ds, rachas, e, U, meses_con_regla=rg, sensibilidades_bateria={"F(0)": 0.95})
        self.assertEqual(d["red"]["inestables"]["estaciones"], 1)
        self.assertEqual(set(d["por_macrozona"]), {"centro", "sur"})
        self.assertIn(red.SIN_DATO, d["por_propietario"])
        self.assertEqual(d["sensibilidades_bateria"], {"F(0)": 0.95})

    def test_cambio_del_portal(self):
        """≥ 20 % de las estaciones con datos cambian en el mismo mes."""
        def rachas(cambian):
            filas = []
            for k in range(10):
                codigo = f"{330000 + k:06d}"
                if k < cambian:
                    filas += [(codigo, 1, 2015, 2017, F4), (codigo, 2, 2018, 2020, F0)]
                else:
                    filas += [(codigo, 1, 2015, 2020, F0)]
            return _tabla([{"codigo": c, "racha": r, "anio_desde": a, "anio_hasta": b, "clase": cl, "n_confirmados": 3,
                            "aceptada": True, "motivo": None} for c, r, a, b, cl in filas], ESQUEMA_RACHAS)

        meses = {f"{330000 + k:06d}": [f"{a:04d}-{m:02d}" for a in range(2015, 2021) for m in range(1, 13)
                                       if not (k < 2 and a == 2018 and m < 7)] for k in range(10)}
        cambios = red.cambios_del_portal(rachas(2), meses, U)
        self.assertEqual(len(cambios), 1)
        self.assertEqual((cambios[0]["mes"], cambios[0]["n_cambian"], cambios[0]["n_con_datos"]), ("2018-07", 2, 10))
        self.assertEqual(red.cambios_del_portal(rachas(1), meses, U), [])          # 10 %
        # Rachas con intersección no vacía (2015 fusionado con la racha civil) no son un cambio.
        fus = _tabla([{"codigo": "330000", "racha": 1, "anio_desde": 2014, "anio_hasta": 2015, "clase": "F(-3)|C(Santiago)",
                       "n_confirmados": 2, "aceptada": True, "motivo": None},
                      {"codigo": "330000", "racha": 2, "anio_desde": 2016, "anio_hasta": 2017, "clase": CS,
                       "n_confirmados": 2, "aceptada": True, "motivo": None}], ESQUEMA_RACHAS)
        self.assertEqual(red.cambios_del_portal(fus, {"330000": ["2014-01", "2016-01"]}, U), [])

    def test_predicciones_1_13(self):
        """Cumplida o «predicción no cumplida»; nunca desviación (RED-10). Una estación UTC cumple el bloque
        F(0) y no los de F(−4) ni C(Santiago); una civil con patrón de E1a cumple el de C(Santiago)."""
        utc = _evidencia_predicciones("330001", F0)
        dec = [_dec_pred("330001", a) for a in (2019, 2020)]
        cons = ConsecuenciasRed(a3_falla_pais=False, a3_fallan_macrozonas=frozenset(), a5_alto=False,
                                modo_e3t={"centro": ModoE3t.RESTRINGIDO}, a4_restringe=False)
        p = red.predicciones([utc], dec, consecuencias=cons, calendario=CAL)
        json.dumps(p, allow_nan=False)                                    # va tal cual al informe
        self.assertNotIn("desviaciones", json.dumps(p))
        self.assertEqual((p["conjunto"], p["n_estaciones"], p["n_estacion_anios"]), ("N", 1, 2))
        res = _resultados(p)
        self.assertEqual(res[F0], {"E1a_presente": "cumplida", "E2_clase": "cumplida", "E3p_E4p": "cumplida",
                                   "E1b_delta": "cumplida", "guardas": "cumplida", "A3_A5_sin_alto": "cumplida"})
        self.assertEqual(res[F4], {"E1a_presente": "cumplida", "E2_clase": "predicción no cumplida",
                                   "E3p": "predicción no cumplida"})
        self.assertEqual(res[CS], {"E1a_patron_civil": "predicción no cumplida", "E1a_placebos": "cumplida",
                                   "E2_clase": "predicción no cumplida", "E3p_fina": "sin_datos"})
        f0 = {x["id"]: x for x in p["por_reloj"][F0]["predicciones"]}
        self.assertEqual((f0["E2_clase"]["k"], f0["E2_clase"]["n"], f0["E2_clase"]["minimo"]), (4, 4, 0.95))
        self.assertEqual(f0["guardas"]["maximo"], 0.01)
        self.assertEqual(f0["E1b_delta"]["deltas"], {"-1": 1})
        civil_e2 = {x["id"]: x for x in p["por_reloj"][CS]["predicciones"]}["E2_clase"]["por_desfase"]
        self.assertEqual(civil_e2, {"-3": {"k": 2, "n": 2}, "-4": {"k": 0, "n": 2}})
        self.assertEqual(p["por_reloj"][F0]["cumplidas"], 6)

        # Sin consecuencias, A3 y A5 quedan sin juicio; un año «sin_datos» y una estación de V no entran.
        v = _evidencia_predicciones("330009", F4, conjunto=Conjunto.V)
        p = red.predicciones([utc, v], [_dec_pred("330001", 2019), _dec_pred("330001", 2020, Veredicto.SIN_DATOS),
                                        _dec_pred("330009", 2019)], calendario=CAL)
        self.assertEqual((p["n_estaciones"], p["n_estacion_anios"]), (1, 1))
        self.assertEqual(_resultados(p)[F0]["A3_A5_sin_alto"], "sin_datos")
        e3p = {x["id"]: x for x in p["por_reloj"][F0]["predicciones"]}["E3p_E4p"]
        self.assertEqual((e3p["k"], e3p["n"]), (1, 1))
        alto = replace(cons, a5_alto=True)
        self.assertEqual(_resultados(red.predicciones([utc], dec, consecuencias=alto, calendario=CAL))[F0]
                         ["A3_A5_sin_alto"], "predicción no cumplida")

        # Una guarda que falla en uno de dos años: 50 % > 1 %.
        con_falla = _evidencia_predicciones("330003", F0, falla_2020=True)
        self.assertEqual(_resultados(red.predicciones([con_falla], [_dec_pred("330003", a) for a in (2019, 2020)],
                                                      consecuencias=cons, calendario=CAL))[F0]["guardas"],
                         "predicción no cumplida")

        # Civil de Santiago con patrón de E1a (C(Santiago) compatible en sus adelantos ausentes) y la regla fina.
        civil = _evidencia_predicciones("330002", CS)
        res = _resultados(red.predicciones([civil], [_dec_pred("330002", a) for a in (2019, 2020)],
                                           consecuencias=cons, calendario=CAL))
        self.assertEqual(res[CS], {"E1a_patron_civil": "cumplida", "E1a_placebos": "cumplida", "E2_clase": "cumplida",
                                   "E3p_fina": "cumplida"})
        self.assertEqual(res[F0]["E1a_presente"], "predicción no cumplida")
        # Enmienda 3, E3-2 (A′; RED-10): los eventos de regla vencida no son placebos del patrón civil.
        con_rv = _evidencia_predicciones("330004", CS)
        rv = [_evento("330004", "E1a", "America/Santiago", a, "regla_vencida", f, "ausente")
              for a, f in ((2019, "2019-10-13"), (2020, "2020-10-11"))]
        con_rv.eventos = _tabla(con_rv.eventos.to_dict("records") + rv, ESQUEMA_EVENTOS)
        res_rv = _resultados(red.predicciones([con_rv], [_dec_pred("330004", a) for a in (2019, 2020)],
                                              consecuencias=cons, calendario=CAL))
        self.assertEqual(res_rv[CS], res[CS])
        # Donde falla A3 la regla fina no rige y no se mira (como decision).
        sin_fina = replace(cons, a3_fallan_macrozonas=frozenset({"centro"}))
        self.assertEqual(_resultados(red.predicciones([civil], [_dec_pred("330002", a) for a in (2019, 2020)],
                                                      consecuencias=sin_fina, calendario=CAL))[CS]["E3p_fina"],
                         "sin_datos")
        # Sin evidencias, todo queda sin datos.
        vacio = red.predicciones([], [], consecuencias=cons)
        self.assertTrue(all(b["no_cumplidas"] == 0 for b in vacio["por_reloj"].values()))


def _resultados(p):
    return {reloj: {x["id"]: x["resultado"] for x in b["predicciones"]} for reloj, b in p["por_reloj"].items()}


def _dec_pred(codigo, anio, veredicto=Veredicto.CONFIRMADO):
    return DecisionAnio(codigo=codigo, anio=anio, P=P_CONT, clases=P_CONT, excluidas={}, K=(), veredicto=veredicto)


def _evidencia_predicciones(codigo, h, *, conjunto=Conjunto.N, falla_2020=False):
    """Estación de 2019-2020 con el reloj ``h`` (F(0), F(-4) o C(Santiago)) en E1a, E1b, E2, E3p (gruesa y
    fina), E4p y las guardas. Bajo C(Santiago): R0 = verano (−3), R1 = invierno (−4)."""
    civil = h == CS
    zona = "America/Santiago"
    eventos, e2, e3, est, gu = [], [], [], [], []
    for anio, fecha in ((2019, "2019-09-08"), (2020, "2020-09-06")):
        resultado = "ausente" if civil else "presente"
        eventos.append(_evento(codigo, "E1a", zona, anio, "real", fecha, resultado))
        eventos.append(_evento(codigo, "E1a", zona, anio, "placebo_semana", fecha, "presente"))
        if civil:     # el patrón civil deja a C(Santiago) compatible en el evento ausente (§4.1.1)
            unidad = f"{zona}|{fecha}|adelanto|real"
            est += _estados(codigo, anio, Linea.E1A, Nivel.EVENTO, unidad, {F0: I, F3: I, F4: I, CS: C})
        for reg in ("R0", "R1"):
            c = DESFASES[reg][h]
            e2.append({"codigo": codigo, "anio": anio, "nivel": "parte", "unidad": f"{anio}-0{1 if reg == 'R0' else 6}-1",
                       "regimen": reg, "n_rr": 40, "frac_observador": 1.0, "valida": True, "informativa": True,
                       "j_estrella": c % 3, "kappa3": 0.99, "n_tx": 0, "kappa3_tx": np.nan, "j_tx": None,
                       "hora_modal_tx": None, "n_tn": 0, "kappa3_tn": np.nan, "j_tn": None, "hora_modal_tn": None})
            fila = _fila_e3(codigo, anio, reg, "QFE", c_cont=float(c), c_f_cont=float(c))
            fila["fino"] = civil
            e3.append(fila)
        est += _estados(codigo, anio, Linea.E4P, Nivel.ANIO, f"{anio:04d}",
                        {h2: (C if h2 == h else I) for h2 in P_CONT})
        falla = falla_2020 and anio == 2020
        gu.append({"codigo": codigo, "anio": anio, "guarda": "E3d", "H": h, "unidad": f"{anio:04d}",
                   "resultado": "falla" if falla else "pasa", "detalle": None})
        gu.append({"codigo": codigo, "anio": anio, "guarda": "G-version", "H": "*", "unidad": f"{anio:04d}",
                   "resultado": "pasa", "detalle": None})
    if not civil:
        eventos.append({**_evento(codigo, "E1b", zona, 2019, "real", "2019-09-08", "evaluado"), "delta": -1})
    ev = _evidencia(_info(codigo, conjunto=conjunto), e3=e3, estados=est, guardas=gu)
    ev.metricas_e2 = _tabla(e2, ESQUEMA_METRICAS_E2)
    ev.eventos = _tabla(eventos, ESQUEMA_EVENTOS)
    return ev


def _evento(codigo, linea, zona, anio, clase, fecha, resultado):
    return {"codigo": codigo, "linea": linea, "zona": zona, "anio": anio, "tipo": "adelanto", "clase_evento": clase,
            "fecha_D": fecha, "etiqueta": f"{fecha}T00:00", "p14": 1.0, "pdom": 1.0, "p": 1.0, "resultado": resultado,
            "delta_s": None, "delta_e": None, "delta": None, "casillas": None, "esperadas": None}



class PruebasEnmienda5A3(unittest.TestCase):
    """Enmienda 5, E5-1 (lectura RED-11): ``controles_red(..., a3_solo_pais=True)``, que sólo pide C3b."""

    def _red(self):
        bien = lambda i: 0.1 * np.sin(i)  # noqa: E731
        evs = [_evidencia_a3(f"10{k:04d}", range(2001, 2021), bien) for k in range(15)]      # 600 años-régimen
        evs.append(_evidencia_a3("200001", range(2001, 2016), lambda i: 2.0 if i < 4 else 0.0, macrozona="sur"))
        return evs, ["centro", "sur"]

    def test_e5_1_a3_rige_solo_en_el_pais(self):
        """A3 falla en «sur» (26/30 < 0,90). Con la opción, se informa igual, pero ninguna macrozona pierde E4p, la
        fina ni E3t completo por A3, y la calibración de E3t de «sur» sale de su propia muestra; sin la opción, como
        antes (§5.4)."""
        evs, mzs = self._red()
        cons0, det0 = red.controles_red(evs, mzs, U, calendario=CAL)
        self.assertEqual(cons0.a3_fallan_macrozonas, frozenset({"sur"}))
        self.assertNotIn("rige", det0["A3"])
        self.assertEqual(det0["calibracion_e3t"]["por_macrozona"]["sur"]["motivo"], "falla A3")
        cons, det = red.controles_red(evs, mzs, U, calendario=CAL, a3_solo_pais=True)
        self.assertEqual(cons.a3_fallan_macrozonas, frozenset())
        self.assertFalse(cons.a3_falla_pais)
        self.assertTrue(cons.e4p_activa("sur") and cons.fina_activa("sur"))
        self.assertEqual(det["A3"]["fallan_macrozonas"], ["sur"])                    # A3 se calcula e informa
        self.assertTrue(det["A3"]["macrozonas"]["sur"]["falla"])
        self.assertEqual(det["A3"]["rige"], "pais")
        self.assertEqual(det["A3"]["fallan_macrozonas_sin_consecuencia"], ["sur"])
        self.assertNotEqual(det["calibracion_e3t"]["por_macrozona"]["sur"]["motivo"], "falla A3")
        self.assertEqual({k: v for k, v in det["A3"].items() if k not in ("rige", "fallan_macrozonas_sin_consecuencia")},
                         det0["A3"])
        json.dumps({k: v for k, v in det.items() if k != "tablas"}, allow_nan=False)

    def test_e5_1_la_falla_en_el_pais_rige_igual(self):
        """Con la opción, una falla de A3 en el país sigue apagando E4p, la fina y E3t completo en todo el país."""
        evs = [_evidencia_a3(f"10{k:04d}", range(2001, 2021), lambda i: 2.0 if i % 10 == 0 else 0.0)
               for k in range(15)]
        cons, det = red.controles_red(evs, ["centro"], U, calendario=CAL, a3_solo_pais=True)
        self.assertTrue(cons.a3_falla_pais)
        self.assertFalse(cons.e4p_activa("centro") or cons.fina_activa("centro"))
        self.assertEqual(cons.modo_e3t_en("centro"), ModoE3t.RESTRINGIDO)
        self.assertEqual(det["calibracion_e3t"]["por_macrozona"]["centro"]["motivo"], "falla A3")

    def test_e5_3_lectura_red_1(self):
        """E5-3: la lectura RED-1 ya no dice que Magallanes confirma F(0) con E3p y E4p (§6 enmendado)."""
        red_1 = " ".join(red.__doc__.split()).split("- RED-1 ")[1].split("- RED-2.")[0]
        self.assertIn("[Enmienda 5, E5-3]", red_1)
        self.assertNotIn("F(0) puede confirmarse con E3p y E4p", red_1)
        self.assertIn("la austral, sí tiene muestra al norte de ese corte", red_1)
        red_11 = " ".join(red.__doc__.split()).split("- RED-11 ")[1]
        self.assertIn("[Enmienda 5, E5-1]", red_11)


if __name__ == "__main__":
    unittest.main()
