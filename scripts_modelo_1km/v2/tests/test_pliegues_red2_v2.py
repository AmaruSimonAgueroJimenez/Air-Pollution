"""Pruebas de ``pliegues_red2_v2`` (R13-R16): las reglas de ``pliegues_v2`` sobre una red ampliada sintética, pesos,
bloque más influyente, evaluabilidad de E2 y la fuente única ``pliegues_v2_red2.json`` (M1): al fijarla, el
``pliegues_v2.json`` vigente pasa intacto a ``pliegues_v2_reemplazado_<marca>.json`` (R13), nada se escribe sin la
traducción confirmada en git (R22) y el anexo exige su huella.

Estaciones sobre un meridiano (distancia haversine exacta en km) y paneles de juguete en carpetas temporales, con la
configuración real. No lee ni escribe datos reales.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2 / "tests"))
import _rutas_v2 as rv  # noqa: E402
import metricas_v2 as mv  # noqa: E402
import pliegues_red2_v2 as plr  # noqa: E402
import pliegues_v2 as pv  # noqa: E402
from _sintetico_v2 import raices_temporales  # noqa: E402

# La configuración sin el nodo de la red (como antes de aplicar la propuesta); CFG_RED2, con un nodo mínimo.
CFG = {k: v for k, v in json.loads((V2 / "config_v2.json").read_text(encoding="utf-8")).items()
       if k != "red_de_monitores"}
CFG_RED2 = {**CFG, "red_de_monitores": {"registro_de_la_red": {"pliegues": {"sha256": None}}}}
CONFIRMADA = lambda repo, rutas: {k: "rastreado" for k in rutas}          # noqa: E731
# La traducción con que se escribieron los artefactos de juguete (traza.traduccion de red_ampliada_v2.traza_red2).
TRAD = {"commit": "a" * 40, "commit_espejo": "b" * 40, "huella_archivos": "h" * 64}
PROPUESTO = json.loads((V2 / "propuesta_red_ampliada" / "config_v2.propuesto.json").read_text(encoding="utf-8"))
KM = pv.RADIO_TIERRA_KM * np.pi / 180.0
LAT0, LON0 = -33.45, -70.66
# código: (km al norte, celda, región, red, comuna)
ESTACIONES = {
    "A1": (0.0, 101, "RM", "sinca", 13101), "A2": (0.5, 102, "RM", "sinca", 13101),
    "N1": (1.0, 103, "RM", "sinca", 13102),                       # nueva, a 1 km de A1: se une a su conglomerado
    "B": (30.0, 201, "RM", "sinca", 13201), "C": (-150.0, 301, "RVI", "sinca", 6101),
    "D": (-500.0, 401, "RVIII", "sinca", 8101), "N2": (-497.0, 402, "RXVI", "sinca", 16101),
    "SNIFA-X": (-520.0, 501, "RVIII", "snifa", 8102),
}
POB = {"A1": [100.0, 300.0, 200.0], "A2": [50.0, 50.0, 50.0], "N1": [80.0], "B": [10.0, 30.0], "C": [5.0],
       "D": [400.0, 400.0], "N2": [20.0], "SNIFA-X": [1.0]}
PANELES = {"pm25": ["A1", "A2", "N1", "B", "C", "D", "N2"], "no2": ["A1", "B", "D", "SNIFA-X"]}


def lat(km: float) -> float:
    return LAT0 + km / KM


def universo() -> pd.DataFrame:
    filas = [{"estacion": e, "nombre": e, "region_sinca": reg, "lat": lat(km), "lon": LON0, "cod_comuna": com,
              "red": red, "celda": celda, "grupo": "nueva" if e.startswith("N") else "actual"}
             for e, (km, celda, reg, red, com) in ESTACIONES.items()]
    est = pd.DataFrame(filas)
    est["cod_comuna"] = est["cod_comuna"].astype("Int64")
    return est


def panel(pol: str, pob: dict | None = None) -> pd.DataFrame:
    pob = POB if pob is None else pob
    partes = []
    for e in PANELES[pol]:
        km, celda, reg, _, _ = ESTACIONES[e]
        for k, p in enumerate(pob[e]):
            ts = pd.Timestamp(f"{2019 + k}-03-01 04:00") + pd.to_timedelta(np.arange(48), unit="h")
            partes.append(pd.DataFrame({"estacion": e, "ts_utc": ts, "celda": celda, "region_sinca": reg,
                                        "lat_est": np.float32(lat(km)), "lon_est": np.float32(LON0),
                                        "anio": np.int16(2019 + k), "pob_dens": np.float32(p)}))
    return pd.concat(partes, ignore_index=True)


# Regímenes por contaminante como los escribe panel_red2_v2 en el json de cada panel (R17).
REGIMENES = {pol: {"tramos": [{"anios": [2000, 2018], "familias": "cams"},
                              {"anios": [2019, 2026], "familias": "cams+tropomi"}]} for pol in PANELES}


def sha(q: Path) -> str:
    return hashlib.sha256(Path(q).read_bytes()).hexdigest()


def escribir_regimenes(r: rv.RutasV2, por_contaminante: dict, comunes: dict | None = None) -> Path:
    """paneles/regimenes_red2.json como lo escribe panel_red2_v2 (``comunes`` = regimenes_comunes, salvo que se dé)."""
    import panel_red2_v2 as pr
    ruta = r.raiz_v2.joinpath(*plr.RUTA_REGIMENES)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"schema": "prueba", "por_contaminante": por_contaminante,
                                "comunes": pr.regimenes_comunes(por_contaminante) if comunes is None else comunes,
                                "traza": {"traduccion": TRAD}}), encoding="utf-8")
    return ruta


def escribir(r: rv.RutasV2, pob: dict | None = None, validado=("A1", "D"), regimenes=None,
             qc: dict | None = None) -> tuple[dict, dict]:
    """Paneles, banderas, el json de cada panel (sha256, calidad_sha256 y regímenes, como el armado) y
    regimenes_red2.json. ``validado``: las estaciones con «validado»; las demás, «preliminar», salvo las de ``qc``
    (estación → código)."""
    regimenes = REGIMENES if regimenes is None else regimenes
    paneles, calidades = {}, {}
    (r.raiz_v2 / "paneles").mkdir(parents=True, exist_ok=True)
    for pol in PANELES:
        df = panel(pol, pob)
        ruta = r.raiz_v2 / "paneles" / plr.NOMBRE_PANEL.format(pol=pol)
        df.to_parquet(ruta, index=False)
        q = df[["estacion", "ts_utc"]].copy()
        q["qc"] = np.where(q["estacion"].isin(validado), "validado", "preliminar")
        for e, codigo in (qc or {}).items():
            q.loc[q["estacion"] == e, "qc"] = codigo
        q["fuente"] = "sinca"
        rq = r.raiz_v2 / "paneles" / plr.NOMBRE_CALIDAD.format(pol=pol)
        q.to_parquet(rq, index=False)
        ruta.with_suffix(".json").write_text(json.dumps({"sha256": sha(ruta), "calidad_sha256": sha(rq),
                                                         "regimenes": regimenes[pol], "traza": {"traduccion": TRAD}}),
                                             encoding="utf-8")
        paneles[pol], calidades[pol] = ruta, rq
    escribir_regimenes(r, regimenes)
    return paneles, calidades


POBLACION = pd.DataFrame({"cod_comuna": [13101, 13102, 13201, 6101, 8101, 8102, 16101] * 2,
                          "anio": [2019] * 7 + [2020] * 7,
                          "poblacion": [1000.0, 500.0, 200.0, 100.0, 300.0, 50.0, 80.0] * 2})


class PlieguesRed2Tests(unittest.TestCase):
    def manifiesto(self, r, pob=None, validado=("A1", "D"), qc=None, cfg=None):
        paneles, calidades = escribir(r, pob, validado, qc=qc)
        return plr.construir_manifiesto_red2(r, CFG if cfg is None else cfg, universo(), paneles, {}, POBLACION,
                                             calidades, hilos=1)

    def test_mismas_reglas_que_pliegues_v2(self):
        """Los protocolos son, tal cual, los que da ``pliegues_v2.construir_contaminante`` con la misma entrada."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            universo_ = pv.completar_universo(universo(), CFG)
            for pol in PANELES:
                por_est, conteos, _ = plr.leer_panel_red2(r.raiz_v2 / "paneles" / plr.NOMBRE_PANEL.format(pol=pol))
                directo = pv.construir_contaminante(pol, universo_, por_est, conteos, CFG, m["contaminantes"][pol]["panel"])
                self.assertEqual(json.dumps(directo, sort_keys=True, default=str),
                                 json.dumps(m["contaminantes"][pol], sort_keys=True, default=str))
            pm = m["contaminantes"]["pm25"]["protocolos"]
            self.assertEqual([f["grupo"] for f in pm["LOSO-D"]["pliegues"]], ["A1+A2+N1", "B", "C", "D", "N2"])
            self.assertEqual([f["semilla"] for f in pm["LOSO-D"]["pliegues"]], [[42, k] for k in range(5)])
            lro = [f["grupo"] for f in pm["LRO"]["pliegues"]]
            self.assertEqual(lro, ["RM", "RVI", "RVIII"])                 # RXVI → RVIII
            self.assertIn("N2", pm["LRO"]["pliegues"][2]["estaciones_prueba"])
            lbo_d = next(f for f in pm["LBO-10"]["pliegues"] if f["grupo"] == "D")
            self.assertEqual(lbo_d["excluidas"], ["D", "N2"])               # N2 a 3 km: fuera de LOSO-D, dentro de LBO-10
            self.assertEqual(lbo_d["radio_incluye_fuera_del_panel"], [])
            self.assertEqual(m["huella_pliegues"], pv.huella_pliegues(m))
            self.assertEqual(m["parametros"], pv.parametros_de(CFG)[0])
            self.assertEqual(m["conteos"]["no2"]["LOSO-D"], 4)

    def test_universo_de_los_radios_es_la_red_2(self):
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            no2 = m["contaminantes"]["no2"]["protocolos"]["LBO-10"]["pliegues"]
            d = next(f for f in no2 if f["grupo"] == "D")
            self.assertEqual(d["radio_incluye_fuera_del_panel"], ["N2"])    # nueva sin NO2, cuenta en el radio
            self.assertEqual(len(m["estaciones"]), len(ESTACIONES))

    def test_pesos_fijos(self):
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            w = m["pesos"]["pm25"]["por_estacion"]
            self.assertEqual(w["A1"], 200.0)                                # mediana de 100, 300 y 200
            self.assertEqual(w["B"], 20.0)
            d = m["pesos"]["pm25"]["desagrupamiento"]
            self.assertEqual(d["A1"], 500.0)                                 # comuna 13101 / 2 estaciones (A1, A2)
            self.assertEqual(d["N1"], 500.0)
            self.assertGreater(m["pesos"]["pm25"]["kish"]["sin_ponderar"], 1.0)
            self.assertEqual(m["pesos"]["pm25"]["G_efectivo"]["LRO"]["G"], 3)

    def test_bloque_mas_influyente(self):
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            b = m["bloque_mas_influyente"]["LRO"]
            # RVIII: D pesa 400 × 96 filas en cada contaminante; RM: A1 200 × 144 + A2 50 × 144 + N1 80 × 48 + B …
            self.assertEqual(b["grupo"], "RVIII")
            self.assertTrue(b["cambia"])                                     # no es el RM que nombró la Enmienda 1
            pob = dict(POB, D=[1.0, 1.0])
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r, pob)
            self.assertEqual(m["bloque_mas_influyente"]["LRO"]["grupo"], "RM")
            self.assertFalse(m["bloque_mas_influyente"]["LRO"]["cambia"])

    def test_bloque_mas_influyente_por_peso_y_filas(self):
        """Ronda 5 de la traducción, menor 10 (T1(1)): el peso de un bloque es el peso fijo × las filas de sus
        estaciones, no la suma de los pesos fijos. Con D (RVIII, peso 400) en un solo año (48 filas por contaminante),
        RVIII tiene la mayor suma de pesos fijos (821 contra 570 de la RM) y la RM el mayor peso × filas (72.480 contra
        39.408): rige la RM, la suma de pesos fijos queda informada con RVIII y las dos lecturas no coinciden."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r, dict(POB, D=[400.0]))
        b = m["bloque_mas_influyente"]["LRO"]
        self.assertEqual((b["grupo"], b["con_suma_de_pesos_fijos"], b["coinciden"]), ("RM", "RVIII", False))
        self.assertEqual([(x["grupo"], x["peso"]) for x in b["ranking"][:2]], [("RM", 72480.0), ("RVIII", 39408.0)])
        self.assertFalse(b["cambia"])

    def test_la_bandera_y_el_panel_por_su_json(self):
        """Cuarta revisión, menor 10: al fijar con la red 2, el json de cada panel es obligatorio, y su sha256 y su
        calidad_sha256 tienen que ser los de los archivos que se leen; la bandera se alinea por estación y hora."""
        with raices_temporales("v2-red2-") as r:
            paneles, calidades = escribir(r)
            construir = lambda: plr.construir_manifiesto_red2(r, CFG, universo(), paneles, {}, POBLACION,  # noqa: E731
                                                              calidades, hilos=1)
            m = construir()
            self.assertEqual(m["traza"]["insumos"]["calidad_pm25"]["sha256"], sha(calidades["pm25"]))
            meta = paneles["pm25"].with_suffix(".json")
            bueno = meta.read_text(encoding="utf-8")
            for nombre, cambio, mensaje in (("otra bandera", {"calidad_sha256": "q" * 64}, "calidad_sha256"),
                                            ("otro panel", {"sha256": "o" * 64}, "registra su json")):
                meta.write_text(json.dumps({**json.loads(bueno), **cambio}), encoding="utf-8")
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    construir()
                self.assertIn(mensaje, str(e.exception))
            meta.unlink()
            with self.assertRaises(SystemExit) as e:                          # sin el json del panel
                construir()
            self.assertIn("falta el json", str(e.exception))
            meta.write_text(bueno, encoding="utf-8")
            q = pd.read_parquet(calidades["pm25"])
            q["estacion"] = q["estacion"].iloc[::-1].to_numpy()                # mismas horas, otras estaciones
            q.to_parquet(calidades["pm25"], index=False)
            meta.write_text(json.dumps({**json.loads(bueno), "calidad_sha256": sha(calidades["pm25"])}), encoding="utf-8")
            with self.assertRaises(SystemExit) as e:
                construir()
            self.assertIn("estación y hora", str(e.exception))

    def test_los_regimenes_van_al_manifiesto(self):
        """Cuarta revisión, menores 11 y 18: R17 escribe los regímenes en el manifiesto antes de cualquier ajuste: los
        tramos comunes de regimenes_red2.json, con su sha256, bajo huella_pesos, y sólo si son los de los json de los
        paneles."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            ruta = r.raiz_v2.joinpath(*plr.RUTA_REGIMENES)
            self.assertEqual(m["regimenes"]["sha256"], sha(ruta))
            self.assertEqual([x["id"] for x in m["regimenes"]["comunes"]], ["2000-2018", "2019-2026"])
            otro = copy.deepcopy(m)
            otro["regimenes"]["comunes"][0]["id"] = "otro"
            self.assertNotEqual(plr.huella_pesos(otro), m["huella_pesos"])   # están bajo huella_pesos
            # el reviewer: json de los paneles con 2000-2017, 2018 y 2019-2026; regimenes_red2.json con 2000-2018 y
            # 2019-2026
            otros = {"pm25": {"tramos": [{"anios": [2000, 2017], "familias": "cams"},
                                         {"anios": [2018, 2026], "familias": "cams+tropomi"}]},
                     "no2": {"tramos": [{"anios": [2000, 2018], "familias": "cams"},
                                        {"anios": [2019, 2026], "familias": "cams+tropomi"}]}}
            import panel_red2_v2 as pr
            self.assertEqual([x["id"] for x in pr.regimenes_comunes(otros)["tramos"]], ["2000-2017", "2018", "2019-2026"])
            metas = {pol: {"regimenes": otros[pol]} for pol in PANELES}
            with self.assertRaises(SystemExit):                              # por_contaminante distinto
                plr.verificar_regimenes(json.loads(ruta.read_text(encoding="utf-8")), metas)
            with self.assertRaises(SystemExit):                              # comunes que no son los de los paneles
                plr.verificar_regimenes({"por_contaminante": otros,
                                         "comunes": json.loads(ruta.read_text(encoding="utf-8"))["comunes"]}, metas)
            ruta.unlink()
            paneles = {pol: r.raiz_v2 / "paneles" / plr.NOMBRE_PANEL.format(pol=pol) for pol in PANELES}
            calidades = {pol: r.raiz_v2 / "paneles" / plr.NOMBRE_CALIDAD.format(pol=pol) for pol in PANELES}
            with self.assertRaises(SystemExit) as e:                         # al fijar, sin regimenes_red2.json
                plr.construir_manifiesto_red2(r, CFG, universo(), paneles, {}, POBLACION, calidades, hilos=1)
            self.assertIn("regimenes_red2.json", str(e.exception))

    def test_evaluabilidad_e2(self):
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            e = m["pesos"]["pm25"]["evaluabilidad_e2"]
            self.assertEqual(e["umbrales"], {"minimo_fraccion": 0.5, "minimo_grupos": 5})
            self.assertEqual(e["estaciones_sin_ninguna_fila_E2"]["n"], 5)
            lro = e["por_protocolo"]["LRO"]
            self.assertEqual(lro["grupos_con_E2"], 2)                       # RM (A1) y RVIII (D)
            self.assertFalse(lro["evaluable"])                              # < 5 grupos
            self.assertEqual(lro["estado"], "sin confirmación con datos validados")

    def test_evaluabilidad_e2_con_los_umbrales_de_la_decision(self):
        """Ronda 5 de la traducción, menor 9 (R15, «con los mismos umbrales»): los códigos de E2 (``validado`` de SINCA
        y ``usable_native`` de SNIFA) y el mínimo de horas del día civil se leen de la configuración, como en la
        decisión (``correr_v2.evidencia_de_decision``), y los grupos son los del protocolo, no las estaciones."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r, validado=("A1", "A2"), qc={"SNIFA-X": "usable_native"})
        pm = m["pesos"]["pm25"]["evaluabilidad_e2"]
        no2 = m["pesos"]["no2"]["evaluabilidad_e2"]
        # PM2,5 en LRO: 7 estaciones en 3 grupos (RM, RVI, RVIII); E2 en dos estaciones de un solo grupo (la RM)
        self.assertEqual((pm["por_protocolo"]["LRO"]["grupos_E1"], pm["por_protocolo"]["LRO"]["grupos_con_E2"]), (3, 1))
        # NO2 en LRO: la RM (A1, validado) y RVIII (la SNIFA, usable_native)
        self.assertEqual((no2["por_protocolo"]["LRO"]["grupos_E1"], no2["por_protocolo"]["LRO"]["grupos_con_E2"]), (2, 2))
        self.assertEqual(no2["estaciones_sin_ninguna_fila_E2"]["estaciones"], ["B", "D"])
        self.assertEqual(no2["codigos_E2"], list(mv.codigos_evaluacion_de_config(CFG)[mv.E2]))
        self.assertEqual(no2["minimo_horas_dia"], CFG["metricas"]["niveles"]["diario"]["minimo_horas"])
        # con otro mínimo de horas en la configuración (24 en vez de 18), sólo cuenta el día completo de cada año
        cfg24 = copy.deepcopy(CFG)
        cfg24["metricas"]["niveles"]["diario"]["minimo_horas"] = 24
        with raices_temporales("v2-red2-") as r:
            m24 = self.manifiesto(r, validado=("A1", "A2"), qc={"SNIFA-X": "usable_native"}, cfg=cfg24)
        e24 = m24["pesos"]["pm25"]["evaluabilidad_e2"]
        self.assertEqual(e24["minimo_horas_dia"], 24)
        self.assertLess(e24["por_protocolo"]["LRO"]["peso_E1"], pm["por_protocolo"]["LRO"]["peso_E1"])

    def original(self, r):
        """Un pliegues_v2.json vigente de juguete, con su propia huella."""
        m = {"schema": pv.SCHEMA, "parametros": {}, "estaciones": [], "contaminantes": {}, "bitacora": [{"evento": "fijado"}]}
        m["huella_pliegues"] = pv.huella_pliegues(m)
        ruta = r.raiz_v2 / "pliegues_v2.json"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(m), encoding="utf-8")
        return ruta, hashlib.sha256(ruta.read_bytes()).hexdigest(), m["huella_pliegues"]

    def test_una_sola_fuente_y_reemplazo_de_r13(self):
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            ruta, sha, huella = self.original(r)
            with self.assertRaises(SystemExit):                             # no es el f001d48c… que nombra R13
                plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA)
            self.assertTrue(ruta.exists())
            self.assertEqual(list(r.raiz_v2.glob("pliegues_v2_reemplazado_*.json")), [])
            final, estado = plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, sha_original=sha)
            self.assertEqual(estado, "fijado")
            self.assertFalse(ruta.exists())                                 # R13: el vigente pasa a respaldo
            respaldos = list(r.raiz_v2.glob("pliegues_v2_reemplazado_*.json"))
            self.assertEqual(len(respaldos), 1)
            self.assertEqual(hashlib.sha256(respaldos[0].read_bytes()).hexdigest(), sha)   # intacto
            e = final["bitacora"][0]
            self.assertEqual((e["evento"], e["huella_anterior"], e["respaldo"]["sha256"]), ("reemplazo", huella, sha))
            escrito = json.loads((r.raiz_v2 / plr.NOMBRE).read_text(encoding="utf-8"))
            for clave in ("contaminantes", "pesos", "bloque_mas_influyente", "huella_pliegues", "huella_pesos"):
                self.assertIn(clave, escrito)                                # pliegues, pesos, E2 y bloque, juntos
            self.assertIn("evaluabilidad_e2", escrito["pesos"]["pm25"])
            self.assertEqual(plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA)[1], "sin_cambios")
            otro = self.manifiesto(r, dict(POB, D=[1.0, 1.0]))
            with self.assertRaises(SystemExit):
                plr.fijar(otro, r, CFG_RED2, estado=CONFIRMADA)
            final, estado = plr.fijar(otro, r, CFG_RED2, reemplazar=True, motivo="prueba", estado=CONFIRMADA)
            self.assertEqual(estado, "reemplazado")
            self.assertEqual(len(list(r.raiz_v2.glob("pliegues_v2_red2_reemplazado_*.json"))), 1)
            self.assertEqual(rv.candado_de(r.raiz_v2 / plr.NOMBRE, r), "pliegues")      # el mismo candado
            self.assertEqual(rv.candado_de(r.raiz_v2 / "pliegues_v2.json", r), "pliegues")

    def test_tras_reemplazar_sigue_el_evento_de_r13(self):
        """Ronda 4, menor 13: después de ``fijar --reemplazar`` (el camino que prevé ``con_el_anexo``), la bitácora del
        archivo escrito sigue empezando con el evento «reemplazo» de R13, copiado tal cual del manifiesto anterior (con
        su respaldo de pliegues_v2.json y su sha256), y cumple las aserciones de la prueba sellada
        ``test_manifiesto_v2.test_red_ampliada_una_sola_fuente`` (reemplazo 4 de test_manifiesto_v2 en CAMBIOS). Un
        manifiesto anterior sin el evento de R13 no se reemplaza."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            _, sha, huella = self.original(r)
            primero, _ = plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, sha_original=sha)
            r13 = primero["bitacora"][0]
            otro = self.manifiesto(r, dict(POB, D=[1.0, 1.0]))
            final, estado = plr.fijar(otro, r, CFG_RED2, reemplazar=True, motivo="prueba", estado=CONFIRMADA)
            self.assertEqual(estado, "reemplazado")
            M = json.loads((r.raiz_v2 / plr.NOMBRE).read_text(encoding="utf-8"))
            self.assertEqual(M["bitacora"][0], r13)                               # tal cual
            self.assertEqual([e["evento"] for e in M["bitacora"]], ["reemplazo", "reemplazo", "fijado"])
            self.assertEqual(M["bitacora"][1]["respaldo"]["ruta"].split("_reemplazado_")[0], "pliegues_v2_red2")
            # las aserciones de test_red_ampliada_una_sola_fuente, sobre el archivo escrito
            for clave in ("pesos", "bloque_mas_influyente", "huella_pesos"):
                self.assertIn(clave, M)
            self.assertEqual(plr.huella_pesos(M), M["huella_pesos"])
            for pol in ("pm25", "no2"):
                self.assertIn("evaluabilidad_e2", M["pesos"][pol])
            e = M["bitacora"][0]
            self.assertEqual((e["evento"], e["regla"]), ("reemplazo", "R13"))
            respaldo = (r.raiz_v2 / plr.NOMBRE).parent / e["respaldo"]["ruta"]
            self.assertTrue(respaldo.name.startswith("pliegues_v2_reemplazado_"))
            self.assertEqual(hashlib.sha256(respaldo.read_bytes()).hexdigest(), e["respaldo"]["sha256"])
            self.assertEqual((e["respaldo"]["sha256"], e["huella_anterior"]), (sha, huella))
            # un segundo reemplazo también lo conserva
            tercero = self.manifiesto(r, dict(POB, D=[2.0, 2.0]))
            plr.fijar(tercero, r, CFG_RED2, reemplazar=True, motivo="prueba", estado=CONFIRMADA)
            self.assertEqual(json.loads((r.raiz_v2 / plr.NOMBRE).read_text(encoding="utf-8"))["bitacora"][0], r13)
            self.assertEqual(plr.evento_r13([{"evento": "reemplazo", "bitacora_anterior": [r13]}]), r13)
        with raices_temporales("v2-red2-") as r:                                 # sin el evento de R13
            m = self.manifiesto(r)
            plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, permitir_sin_r13=True)
            otro = self.manifiesto(r, dict(POB, D=[1.0, 1.0]))
            with self.assertRaises(SystemExit) as e:
                plr.fijar(otro, r, CFG_RED2, reemplazar=True, motivo="prueba", estado=CONFIRMADA)
            self.assertIn("R13", str(e.exception))
            self.assertEqual(json.loads((r.raiz_v2 / plr.NOMBRE).read_text(encoding="utf-8"))["huella_pliegues"],
                             m["huella_pliegues"])

    def test_en_la_decision_rige_la_evaluabilidad_registrada(self):
        """Ronda 5 de la traducción, mayor 1 (R15: «se calcula sobre el panel de R11, con los mismos umbrales, antes de
        cualquier ajuste»; «Calcularlo antes cierra la puerta a declararlo según convenga»): en la decisión rige la
        evaluabilidad de E2 registrada en pliegues_v2_red2.json; la que la decisión vuelve a calcular sobre sus pares
        sólo queda en el registro. Con la evidencia en «no evaluable» (E2 en 4 bloques; fracción 0,49) y la registrada en
        «evaluable» (0,51), la condición 3 se exige y XGBoost, con E2 de otro signo, no la pasa; al revés, no bloquea.
        Con la registrada evaluable y la evidencia sin pares E2 se detiene (defecto de la corrida); sin la registrada,
        también. Ninguna parada deja la elección al autor."""
        import inspect
        import decision_v2 as dc
        from test_decision_v2 import REGLA_RAPIDA, evidencia
        evaluable = {"evaluable": True, "fraccion_del_peso": 0.51, "grupos_con_E2": 5, "peso_E1": 100.0, "peso_E2": 51.0,
                     "estado": "evaluable", "motivo": []}
        no_evaluable = {**evaluable, "evaluable": False, "fraccion_del_peso": 0.3, "estado": mv.SIN_CONFIRMACION,
                        "motivo": ["E2 conserva 30,0 % del peso de E1 (< 50 %)"]}

        def man(reg):
            return {"pesos": {"pm25": {"evaluabilidad_e2": {"por_protocolo": {"LRO": dict(reg)}}}}}
        ev = evidencia("LRO", semilla=40, efectos={"xgboost": 0.5}, efecto_e2={"xgboost": -0.1}, frac_e2=0.6,
                       bloques_e2=4)
        ev["evaluabilidad_E2"]["fraccion_del_peso"] = 0.49
        self.assertFalse(ev["evaluabilidad_E2"]["evaluable"])
        antes = json.dumps(ev, sort_keys=True)
        rige, registro = plr.evaluabilidad_e2_que_rige(ev, man(evaluable), "pm25", "LRO")
        self.assertEqual(json.dumps(ev, sort_keys=True), antes)                # la evidencia leída no cambia
        self.assertTrue(rige["evaluabilidad_E2"]["evaluable"])
        self.assertEqual(registro["rige"], {c: evaluable[c] for c in plr.CAMPOS_E2})
        self.assertEqual((registro["de_la_decision"]["fraccion_del_peso"], registro["coinciden"]), (0.49, False))
        self.assertEqual(registro["evidencia_consolidada_sha256"], dc.huella_evidencia(ev))
        con_la_suya = dc.evaluar_protocolo(ev, regla=REGLA_RAPIDA)["candidatos"]["xgboost"]
        con_la_registrada = dc.evaluar_protocolo(rige, regla=REGLA_RAPIDA)["candidatos"]["xgboost"]
        self.assertEqual((con_la_suya["e2_evaluable"], con_la_suya["consistencia_con_E2"]), (False, True))
        self.assertLess(con_la_registrada["delta_r2_E2"], 0)
        self.assertEqual((con_la_registrada["e2_evaluable"], con_la_registrada["consistencia_con_E2"]), (True, False))
        self.assertFalse(con_la_registrada["pasa_sin_c6"])
        # al revés: la evidencia evaluable y la registrada no; rige la registrada y la condición 3 no bloquea
        ev2 = evidencia("LRO", semilla=40, efectos={"xgboost": 0.5}, efecto_e2={"xgboost": -0.1}, frac_e2=0.6)
        self.assertTrue(ev2["evaluabilidad_E2"]["evaluable"])
        rige2, registro2 = plr.evaluabilidad_e2_que_rige(ev2, man(no_evaluable), "pm25", "LRO")
        x2 = dc.evaluar_protocolo(rige2, regla=REGLA_RAPIDA)["candidatos"]["xgboost"]
        self.assertEqual((x2["e2_evaluable"], x2["consistencia_con_E2"], registro2["coinciden"]), (False, True, False))
        # la registrada evaluable y la evidencia sin pares E2: un defecto de la corrida, no una elección
        sin_pares = {**ev, "vistas": {k: v for k, v in ev["vistas"].items() if k != dc.V_E2}}
        with self.assertRaises(SystemExit) as e:
            plr.evaluabilidad_e2_que_rige(sin_pares, man(evaluable), "pm25", "LRO")
        for texto in ("R15", "defecto de la corrida", "0.51"):
            self.assertIn(texto, str(e.exception))
        self.assertFalse(plr.evaluabilidad_e2_que_rige(sin_pares, man(no_evaluable), "pm25", "LRO")[0]
                         ["evaluabilidad_E2"]["evaluable"])                    # no evaluable: no bloquea
        with self.assertRaises(SystemExit):                                    # sin la registrada
            plr.evaluabilidad_e2_que_rige(ev, {"pesos": {}}, "pm25", "LRO")
        self.assertNotIn("lo decide el autor", inspect.getsource(plr))

    def test_nada_se_escribe_sin_la_traduccion_confirmada(self):
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            ruta, sha, _ = self.original(r)
            for cfg, estado in ((CFG, CONFIRMADA), (CFG_RED2, None)):       # sin nodo; sin git (carpeta temporal)
                with self.subTest(nodo="red_de_monitores" in cfg), self.assertRaises(SystemExit):
                    plr.fijar(m, r, cfg, estado=estado)
            self.assertFalse((r.raiz_v2 / plr.NOMBRE).exists())
            self.assertEqual(hashlib.sha256(ruta.read_bytes()).hexdigest(), sha)

    def test_opciones_que_no_fijan_a_medias(self):
        """--sin-e2 sólo sin escribir (R15) y, para escribir, la población del INE (R14), antes de leer nada."""
        with raices_temporales("v2-red2-") as r:
            ine = r.datos / "poblacion.csv"
            with self.assertRaises(SystemExit):
                plr.comprobar_opciones(False, True, ine)                     # --sin-e2 escribiendo
            with self.assertRaises(SystemExit):
                plr.comprobar_opciones(False, False, ine)                    # escribir sin la población
            plr.comprobar_opciones(True, True, ine)                          # sin escribir, las dos sirven
            ine.write_text("x", encoding="utf-8")
            plr.comprobar_opciones(False, False, ine)

    def artefactos_del_armado(self, r):
        """Los json y archivos pequeños del armado que lee el anexo (reloj, contraste, registro MAIAC, inventario,
        copia congelada y json de los paneles), de juguete y coherentes entre sí; el json de cada panel conserva lo
        que escribió ``escribir`` (sha256, calidad_sha256 y regímenes)."""
        def escribir_json(partes, d):
            q = r.raiz_v2.joinpath(*partes)
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_text(json.dumps(d), encoding="utf-8")
            return hashlib.sha256(q.read_bytes()).hexdigest()
        ver = r.raiz_v2 / plr.RUTA_RELOJ[0] / "veredictos.parquet"
        ver.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"estacion": ["A1"], "anio": [2023]}).to_parquet(ver)
        sha_ver = hashlib.sha256(ver.read_bytes()).hexdigest()
        traza = {"traduccion": TRAD}
        sha_res = escribir_json(plr.RUTA_RELOJ, {"sha256_veredictos": sha_ver, "huella_series": "s" * 64,
                                                 "convencion_civil": {"conteos": {"solo_fin": 2, "solo_inicio_mas_1h": 1},
                                                                      "elegida": "fin"},
                                                 "limite_sin_transiciones": {"unidades_junto_a_civil": [
                                                     {"estacion": "A1", "contaminante": "pm25", "anio": 2015}]},
                                                 "traza": traza})
        csv = r.raiz_v2.joinpath(*plr.RUTA_CONTRASTE)
        csv.parent.mkdir(parents=True, exist_ok=True)
        csv.write_text("a\n", encoding="utf-8")
        sha_csv = hashlib.sha256(csv.read_bytes()).hexdigest()
        sha_lat = escribir_json(plr.RUTA_CONTRASTE[:-1] + (csv.with_suffix(".json").name,), {"sha256_csv": sha_csv,
                                                                                           "traza": traza})
        sha_maiac = escribir_json(plr.RUTA_REGISTRO_MAIAC, {"huella_teselas": "t" * 64, "traza": traza})
        sha_inv = escribir_json(plr.RUTA_INVENTARIO, {"resumen": {"tropomi_no2": {"por_fecha_de_modificacion": {
            "entran": 2, "por_anio": {"2020": 1, "2024": 1}, "huella_lista": "l" * 64}}}, "traza": traza})
        sha_cong = escribir_json(plr.RUTA_CONGELADOS, {"archivos": 0, "traza": traza})
        for pol, partes in plr.JSON_PANEL.items():
            previo = r.raiz_v2.joinpath(*partes)
            previo = json.loads(previo.read_text(encoding="utf-8")) if previo.exists() else {"sha256": "o" * 64}
            escribir_json(partes, {
                **previo, "qc": {"duplicados": [{"grupo": pol}]},
                "reloj": {"veredictos_sha256": sha_ver, "resumen_sha256": sha_res},
                "unidades": {"contraste_sha256": sha_csv, "segunda_corrida": {"lateral_sha256": sha_lat}},
                "registro_catalogo_maiac": {"sha256": sha_maiac},
                "insumos": {"inventario_sha256": sha_inv, "congelados_sha256": sha_cong}, "traza": traza})

    def cfg_del_anexo(self, r, m, reg):
        """La configuración como la dejaría el anexo, armada con el programa (cuarta revisión, menor 34):
        ``anexo_desde_artefactos`` (registro de los pliegues, de los regímenes y de los demás artefactos del armado, el
        bloque más influyente, los regímenes calculados con su rótulo y la cobertura de E2) y ``con_el_anexo``, que lo
        escribe donde lo leen decision_v2 y metricas_v2. ``reg`` (sha256 y huella de los pliegues) se compara con el
        que arma el programa."""
        self.artefactos_del_armado(r)
        anexo = plr.anexo_desde_artefactos(r)
        self.assertEqual({k: anexo["registro_de_la_red"]["pliegues"][k] for k in reg}, dict(reg))
        self.assertEqual(anexo["bloque_mas_influyente"], {p: m["bloque_mas_influyente"][p]["grupo"] for p in ("LRO", "BLQ-75")})
        base = copy.deepcopy(CFG)
        base["red_de_monitores"] = {"registro_de_la_red": {"regimenes": {"archivo": "paneles/regimenes_red2.json"}}}
        return plr.con_el_anexo(base, anexo)

    def test_rige_lo_calculado_r16_r17(self):
        """El registro exige que la configuración tenga el bloque más influyente y los regímenes calculados, y que esos
        regímenes sean los de los json de los paneles y los del manifiesto (cuarta revisión, menores 11 y 18)."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, permitir_sin_r13=True)
            ruta = r.raiz_v2 / plr.NOMBRE
            reg = {"sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "huella_pliegues": m["huella_pliegues"]}
            cfg = self.cfg_del_anexo(r, m, reg)
            plr.exigir_registro(r, cfg, estado=CONFIRMADA)
            rotulo = copy.deepcopy(cfg)                                      # menor 25: el rótulo también cuenta
            rotulo["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]["valor"][1]["disponibilidad"] = \
                "sin GEOS-CF ni TROPOMI"
            bloque = copy.deepcopy(cfg)
            bloque["inferencia_diferencias"]["influencia"]["bloque_mas_influyente"]["LRO"] = "otra"
            tramos = copy.deepcopy(cfg)
            tramos["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]["valor"] = \
                CFG["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]["valor"]  # los 5 de la E1
            sin_reg = copy.deepcopy(cfg)
            del sin_reg["red_de_monitores"]["registro_de_la_red"]["regimenes"]
            enm2 = cfg["inferencia_diferencias"]["influencia"]["bloque_mas_influyente_enmienda_2"]
            self.assertEqual((enm2["red_original"], enm2["aviso"]["LRO"]),
                             (plr.NOMBRADOS_ENMIENDA_1, {"calculado": "RVIII", "nombrado_por_la_enmienda_1": "RM",
                                                         "cambia": True}))   # R16: «se dice»
            sin_aviso, otro_original = copy.deepcopy(cfg), copy.deepcopy(cfg)
            sin_aviso["inferencia_diferencias"]["influencia"]["bloque_mas_influyente_enmienda_2"]["aviso"]["LRO"]["cambia"] \
                = False
            otro_original["inferencia_diferencias"]["influencia"]["bloque_mas_influyente_enmienda_2"]["red_original"] = \
                {"LRO": "RV", "BLQ-75": "E004N084"}
            for nombre, c, mensaje in (("bloque", bloque, "R16"), ("tramos", tramos, "R17"),
                                       ("rótulo falso", rotulo, "R17"), ("sin registro", sin_reg, "R17"),
                                       ("aviso falso", sin_aviso, "aviso"), ("red_original pisado", otro_original,
                                                                            "red_original")):
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    plr.exigir_registro(r, c, estado=CONFIRMADA)
                self.assertIn(mensaje, str(e.exception))
            # quinta revisión, menor 10: pliegues_v2_red2.json fijado con otros regímenes (otro sha256 u otros tramos)
            # y sus dos huellas propias recalculadas; el anexo registra su sha256 y un regimenes_red2.json coherente
            # con los json de los paneles: «no copió»
            fijado = json.loads(ruta.read_text(encoding="utf-8"))
            for nombre, cambio in (("otro sha256", {"sha256": "0" * 64}),
                                   ("otros tramos", {"comunes": fijado["regimenes"]["comunes"][:1]})):
                otro = {**fijado, "regimenes": {**fijado["regimenes"], **cambio}}
                otro["huella_pliegues"], otro["huella_pesos"] = pv.huella_pliegues(otro), plr.huella_pesos(otro)
                ruta.write_text(rv.texto_json(otro), encoding="utf-8")
                c = copy.deepcopy(cfg)
                c["red_de_monitores"]["registro_de_la_red"]["pliegues"] = {
                    "sha256": sha(ruta), "huella_pliegues": otro["huella_pliegues"], "huella_pesos": otro["huella_pesos"]}
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    plr.exigir_registro(r, c, estado=CONFIRMADA)
                self.assertIn("no copió", str(e.exception))
            ruta.write_text(rv.texto_json(fijado), encoding="utf-8")
            self.assertEqual(sha(ruta), reg["sha256"])
            plr.exigir_registro(r, cfg, estado=CONFIRMADA)
            # regimenes_red2.json y la configuración coherentes entre sí, pero no con los json de los paneles
            otros = {"pm25": {"tramos": [{"anios": [2000, 2017], "familias": "cams"},
                                         {"anios": [2018, 2026], "familias": "cams+tropomi"}]},
                     "no2": REGIMENES["no2"]}
            ruta_reg = escribir_regimenes(r, otros)
            falso = copy.deepcopy(cfg)
            falso["red_de_monitores"]["registro_de_la_red"]["regimenes"]["sha256"] = sha(ruta_reg)
            falso["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]["valor"] = [
                {k: x[k] for k in ("id", "anios", "disponibilidad")}
                for x in json.loads(ruta_reg.read_text(encoding="utf-8"))["comunes"]["tramos"]]
            with self.assertRaises(SystemExit) as e:
                plr.exigir_registro(r, falso, estado=CONFIRMADA)
            self.assertIn("json de los paneles", str(e.exception))           # verificar_regimenes (menor 11)
            r.raiz_v2.joinpath(*plr.RUTA_REGIMENES).write_text(json.dumps({"comunes": {"tramos": []}}))
            with self.assertRaises(SystemExit):                              # el archivo ya no es el registrado
                plr.exigir_registro(r, cfg, estado=CONFIRMADA)

    def test_el_anexo_exige_la_huella(self):
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, permitir_sin_r13=True)
            ruta = r.raiz_v2 / plr.NOMBRE
            with self.assertRaises(SystemExit):
                plr.exigir_registro(r, CFG_RED2)                             # el anexo todavía no la registró
            reg = {"sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "huella_pliegues": m["huella_pliegues"]}
            cfg = self.cfg_del_anexo(r, m, reg)
            self.assertEqual(plr.exigir_registro(r, cfg, estado=CONFIRMADA)["huella_pliegues"], m["huella_pliegues"])
            cfg_mal = copy.deepcopy(cfg)
            cfg_mal["red_de_monitores"]["registro_de_la_red"]["pliegues"]["sha256"] = "0" * 64
            with self.assertRaises(SystemExit):
                plr.exigir_registro(r, cfg_mal, estado=CONFIRMADA)
            # después del anexo, el piloto anota recortes en la bitácora (§10): siguen valiendo
            texto = ruta.read_text(encoding="utf-8")
            con_recorte = json.loads(texto)
            con_recorte["bitacora"].append({"utc": "2026-11-01T00:00:00Z", "evento": "recorte_presupuesto",
                                            "recorte": 1, "etiqueta": "x", "aplicados": [1]})
            ruta.write_text(rv.texto_json(con_recorte), encoding="utf-8")
            self.assertEqual(plr.exigir_registro(r, cfg, estado=CONFIRMADA)["bitacora"][-1]["evento"], "recorte_presupuesto")
            # cualquier otro cambio, no: otro evento al final, o la traza tocada aunque sólo se agreguen recortes
            otro = {**con_recorte, "bitacora": con_recorte["bitacora"] + [{"utc": "x", "evento": "fijado"}]}
            tocado = {**con_recorte, "traza": {**con_recorte["traza"], "hilos": {"configurados": 99}}}
            for malo in (otro, tocado):
                ruta.write_text(rv.texto_json(malo), encoding="utf-8")
                with self.subTest(malo=sorted(malo)), self.assertRaises(SystemExit):
                    plr.exigir_registro(r, cfg, estado=CONFIRMADA)
            ruta.write_text(texto, encoding="utf-8")
            self.assertEqual(plr.exigir_registro(r, cfg, estado=CONFIRMADA)["huella_pliegues"], m["huella_pliegues"])

    def test_el_anexo_es_el_de_los_artefactos(self):
        """Menores 40 (tercera revisión) y 34 (cuarta): el anexo se arma con los artefactos del armado
        (anexo_desde_artefactos, que trae también los pliegues, los regímenes, el bloque y la cobertura) y
        exigir_registro lo compara campo por campo; un campo escrito a mano, o un json de panel que declara otra
        huella que la de su artefacto, detienen la corrida."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, permitir_sin_r13=True)
            ruta = r.raiz_v2 / plr.NOMBRE
            reg = {"sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(), "huella_pliegues": m["huella_pliegues"]}
            cfg = self.cfg_del_anexo(r, m, reg)
            anexo = cfg["red_de_monitores"]["registro_de_la_red"]
            self.assertEqual(sorted(set(plr.CAMPOS_DEL_ANEXO) - set(anexo)), [])
            self.assertEqual(anexo["tropomi_por_fecha"]["por_anio"], {"2020": 1, "2024": 1})       # T11
            self.assertEqual({k: anexo["traduccion"][k] for k in TRAD}, TRAD)                         # mayor 2
            self.assertEqual(len(anexo["traduccion"]["artefactos"]), 9)
            self.assertEqual(anexo["reloj"]["sin_transiciones_junto_a_civil"], ["A1:pm25:2015"])      # menor 4
            self.assertEqual([v["estado"] for v in anexo["procedencia_descarga"]["versiones"]],
                             ["perdida", "perdida", "perdida"])                                     # menor 22
            self.assertEqual(anexo["lista_cerrada"]["archivos"], 20)
            self.assertEqual(set(anexo["pliegues"]) >= {"sha256", "huella_pliegues", "huella_pesos"}, True)
            self.assertEqual(anexo["regimenes"]["sha256"], sha(r.raiz_v2.joinpath(*plr.RUTA_REGIMENES)))
            crit = cfg["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
            antes = CFG["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
            self.assertEqual(crit["valor_red_original"], antes.get("valor_red_original", antes["valor"]))   # Enmienda 1
            cob = cfg["calidad_blanco"]["evaluacion"]["cobertura_conocida"]["red_ampliada"]
            self.assertEqual({pol: cob[pol] for pol in PANELES},
                             {pol: plr.texto_cobertura(m["pesos"][pol]["evaluabilidad_e2"]) for pol in PANELES})
            # ronda 4, menor 15 (R15, «se escribe en el registro de la red»): la evaluabilidad de E2 por contaminante y
            # protocolo, la del manifiesto
            e2 = anexo["evaluabilidad_e2"]
            for pol in PANELES:
                for prot, x in m["pesos"][pol]["evaluabilidad_e2"]["por_protocolo"].items():
                    self.assertEqual(e2[pol][prot], {c: x[c] for c in plr.CAMPOS_E2})
            self.assertEqual(set(e2["pm25"]["LRO"]), {"evaluable", "fraccion_del_peso", "grupos_con_E2", "peso_E1",
                                                      "peso_E2"})
            plr.exigir_registro(r, cfg, estado=CONFIRMADA)
            for campo, valor in (("evaluable", not e2["pm25"]["LRO"]["evaluable"]), ("grupos_con_E2", 99)):
                c = copy.deepcopy(cfg)
                c["red_de_monitores"]["registro_de_la_red"]["evaluabilidad_e2"]["pm25"]["LRO"][campo] = valor
                with self.subTest(f"evaluabilidad_e2.{campo}"), self.assertRaises(SystemExit) as e:
                    plr.exigir_registro(r, c, estado=CONFIRMADA)
                self.assertIn("evaluabilidad_e2", str(e.exception))
            for entrada, campo, valor in (("reloj", "elegida", "inicio_mas_1h"), ("calidad", "pm25", "0" * 64),
                                          ("tropomi_por_fecha", "por_anio", {"2020": 1}),
                                          ("contraste_segunda_corrida", "lateral_sha256", "0" * 64),
                                          ("reloj", "sin_transiciones_junto_a_civil", []),
                                          ("traduccion", "commit", "f" * 40),
                                          ("procedencia_descarga", "versiones", [])):
                c = copy.deepcopy(cfg)
                c["red_de_monitores"]["registro_de_la_red"][entrada][campo] = valor
                with self.subTest(f"{entrada}.{campo}"), self.assertRaises(SystemExit):
                    plr.exigir_registro(r, c, estado=CONFIRMADA)
            cob = copy.deepcopy(cfg)                                          # R15 (menor 19): la cobertura de E2
            cob["calidad_blanco"]["evaluacion"]["cobertura_conocida"]["red_ampliada"]["pm25"] = "0 de las 7 estaciones"
            with self.assertRaises(SystemExit) as e:
                plr.exigir_registro(r, cob, estado=CONFIRMADA)
            self.assertIn("R15", str(e.exception))
            # menor 10: la E2 del manifiesto se calculó con otra bandera que la registrada; el json del panel y el anexo
            # dicen otra cosa, coherentes entre sí
            meta = r.raiz_v2.joinpath(*plr.JSON_PANEL["pm25"])
            bueno = meta.read_text(encoding="utf-8")
            meta.write_text(json.dumps({**json.loads(bueno), "calidad_sha256": "0" * 64}), encoding="utf-8")
            base = copy.deepcopy(CFG)
            base["red_de_monitores"] = {"registro_de_la_red": {}}
            otra = plr.con_el_anexo(base, plr.anexo_desde_artefactos(r))
            with self.assertRaises(SystemExit) as e:
                plr.exigir_registro(r, otra, estado=CONFIRMADA)
            self.assertIn("otra bandera", str(e.exception))
            meta.write_text(bueno, encoding="utf-8")
            plr.exigir_registro(r, cfg, estado=CONFIRMADA)
            # quinta revisión, mayor 2: un artefacto sin su traza, o escrito con otra traducción, detiene el anexo
            # (regimenes_red2.json: ningún json de panel declara su sha256, así que la parada es la de la traducción)
            q = r.raiz_v2.joinpath(*plr.RUTA_REGIMENES)
            bueno_q = q.read_text(encoding="utf-8")
            for nombre, traza, mensaje in (("sin traza", None, "no declara"),
                                           ("otro commit", {"traduccion": {**TRAD, "commit": "f" * 40}}, "misma traducción"),
                                           ("commit desconocido", {"traduccion": {**TRAD, "commit_espejo": "desconocido"}},
                                            "no declara")):
                q.write_text(json.dumps({**json.loads(bueno_q), "traza": traza}), encoding="utf-8")
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    plr.registro_de_la_red_desde_artefactos(r)
                self.assertIn(mensaje, str(e.exception))
            q.write_text(bueno_q, encoding="utf-8")
            plr.exigir_registro(r, cfg, estado=CONFIRMADA)
            # menor 22: una copia recuperada de la v1.0.0, con su huella, cambia el estado que registra el anexo
            import red_ampliada_v2 as ra
            from unittest import mock
            copia = r.raiz_v2 / ra.CARPETA_PROCEDENCIA_DESCARGA / "descargar_sinca_ampliacion_v1.0.0.py"
            copia.parent.mkdir(parents=True)
            copia.write_bytes(b"la v1.0.0 recuperada")
            primera = {**ra.PROCEDENCIA_DESCARGA["versiones"][0], "script_sha256": sha(copia)}
            with mock.patch.dict(ra.PROCEDENCIA_DESCARGA, {"versiones": [primera, *ra.PROCEDENCIA_DESCARGA["versiones"][1:]]}):
                v = plr.procedencia_descarga_desde_artefactos(r)["versiones"]
                self.assertEqual((v[0]["estado"], v[0]["copia"]["ruta"], v[0]["copia"]["sha256"]),
                                 ("recuperada", f"{ra.CARPETA_PROCEDENCIA_DESCARGA}/{copia.name}", sha(copia)))
                with self.assertRaises(SystemExit):                        # el anexo escrito decía «perdida»
                    plr.exigir_registro(r, cfg, estado=CONFIRMADA)
            q = r.raiz_v2.joinpath(*plr.JSON_PANEL["o3"])
            d = json.loads(q.read_text(encoding="utf-8"))
            d["reloj"]["veredictos_sha256"] = "0" * 64                     # el json del panel declara otro reloj
            q.write_text(json.dumps(d), encoding="utf-8")
            with self.assertRaises(SystemExit):
                plr.exigir_registro(r, cfg, estado=CONFIRMADA)

    def test_la_opcion_anexo_lo_muestra_validado(self):
        """Menor 34: ``pliegues_red2_v2.py --anexo`` arma el anexo desde los artefactos, lo valida con exigir_registro
        y lo muestra, sin escribir nada; si los artefactos no calzan, se detiene."""
        import contextlib
        import io
        from unittest import mock
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, permitir_sin_r13=True)
            self.artefactos_del_armado(r)
            antes = sorted(str(q) for q in r.raiz_v2.rglob("*"))
            salida = io.StringIO()
            with mock.patch.object(rv, "rutas_v2", lambda: r), mock.patch.object(rv, "cargar_config", lambda r_: CFG), \
                    contextlib.redirect_stdout(salida):
                self.assertEqual(plr.main(["--anexo"]), 0)
            anexo = json.loads(salida.getvalue())
            self.assertEqual(set(anexo), {"registro_de_la_red", "bloque_mas_influyente", "aviso_r16", "regimenes",
                                          "cobertura_red_ampliada", "donde"})
            self.assertEqual(sorted(str(q) for q in r.raiz_v2.rglob("*")), antes)      # no escribió nada
            r.raiz_v2.joinpath(*plr.RUTA_REGIMENES).write_text("{}", encoding="utf-8")
            with mock.patch.object(rv, "rutas_v2", lambda: r), mock.patch.object(rv, "cargar_config", lambda r_: CFG), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                plr.main(["--anexo"])

    def test_el_anexo_se_puede_aplicar_dos_veces(self):
        """Quinta revisión, menores 11 y 14: con_el_anexo aplicado sobre una configuración que ya trae otro anexo (después
        de ``fijar --reemplazar``) conserva el bloque de la Enmienda 1 en red_original y los regímenes de la Enmienda 1
        en valor_red_original, y escribe el aviso de R16 del anexo nuevo."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, permitir_sin_r13=True)
            self.artefactos_del_armado(r)
            anexo = plr.anexo_desde_artefactos(r)
            base = copy.deepcopy(CFG)
            base["red_de_monitores"] = {"registro_de_la_red": {}}
            inf = base["inferencia_diferencias"]["influencia"]
            inf["bloque_mas_influyente_enmienda_2"] = copy.deepcopy(
                PROPUESTO["inferencia_diferencias"]["influencia"]["bloque_mas_influyente_enmienda_2"])
            crit0 = copy.deepcopy(base["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"])
            uno = {**anexo, "bloque_mas_influyente": {"LRO": "RV", "BLQ-75": "E004N084"},
                   "aviso_r16": {p: {**a, "cambia": True} for p, a in anexo["aviso_r16"].items()}}
            dos = {**anexo, "bloque_mas_influyente": {"LRO": "RVIII", "BLQ-75": "E005N080"}}
            c = plr.con_el_anexo(plr.con_el_anexo(base, uno), dos)
            enm2 = c["inferencia_diferencias"]["influencia"]["bloque_mas_influyente_enmienda_2"]
            self.assertEqual(enm2["red_original"], {"LRO": "RM", "BLQ-75": "E004N083"})
            self.assertEqual((enm2["valor"], enm2["aviso"]), (dos["bloque_mas_influyente"], dos["aviso_r16"]))
            self.assertEqual(enm2["regla"], PROPUESTO["inferencia_diferencias"]["influencia"]
                             ["bloque_mas_influyente_enmienda_2"]["regla"])
            crit = c["metricas"]["desagregaciones"]["regimen_de_predictores"]["criterio"]
            self.assertEqual(crit["valor_red_original"], crit0.get("valor_red_original", crit0["valor"]))
            # el anexo de verdad, aplicado dos veces, vale; aplicado sobre uno ajeno, también
            for c in (plr.con_el_anexo(plr.con_el_anexo(base, anexo), anexo), plr.con_el_anexo(plr.con_el_anexo(base, uno),
                                                                                                anexo)):
                plr.exigir_registro(r, c, estado=CONFIRMADA)

    def test_sin_la_configuracion_confirmada_no_corre(self):
        """Quinta revisión, menor 12 (R22, paso 4: «el anexo, confirmado en git»): exigir_registro, que corre en
        Contexto.desde_disco (también en el piloto) y en decidir, exige config_v2.json rastreado y sin cambios; --anexo,
        que no ajusta nada, lo valida en memoria."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, permitir_sin_r13=True)
            ruta = r.raiz_v2 / plr.NOMBRE
            reg = {"sha256": sha(ruta), "huella_pliegues": m["huella_pliegues"]}
            cfg = self.cfg_del_anexo(r, m, reg)
            for estado in ("modificado", "sin_rastrear", "desconocido"):
                with self.subTest(estado=estado), self.assertRaises(SystemExit) as e:
                    plr.exigir_registro(r, cfg, estado=lambda repo, rutas: {k: estado for k in rutas})
                self.assertIn("confirmado en git", str(e.exception))
            with self.assertRaises(SystemExit) as e:                         # sin git (la carpeta temporal)
                plr.exigir_registro(r, cfg)
            self.assertIn("confirmado en git", str(e.exception))
            self.assertEqual(plr.exigir_registro(r, cfg, exigir_confirmada=False)["huella_pliegues"], m["huella_pliegues"])
            self.assertEqual(plr.exigir_registro(r, cfg, estado=CONFIRMADA)["huella_pliegues"], m["huella_pliegues"])

    def test_r13_si_el_original_ya_no_esta(self):
        """Menores 28 y 47: sin pliegues_v2.json, fijar no publica sin el evento de R13: busca el respaldo por su
        sha256 (no por el nombre) y, si no lo hay, se detiene."""
        with raices_temporales("v2-red2-") as r:
            m = self.manifiesto(r)
            with self.assertRaises(SystemExit):                              # ni el original ni su respaldo
                plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA)
            self.assertFalse((r.raiz_v2 / plr.NOMBRE).exists())
            ruta, sha, huella = self.original(r)
            otro = r.raiz_v2 / "pliegues_v2_reemplazado_20261013T000000Z.json"   # un respaldo de la Enmienda 1
            otro.write_text(json.dumps({"schema": pv.SCHEMA, "otro": True}), encoding="utf-8")
            respaldo = ruta.rename(r.raiz_v2 / "pliegues_v2_reemplazado_20261027T000000Z.json")   # corte tras renombrar
            self.assertEqual(plr.respaldo_de_r13(r, sha), respaldo)
            final, estado = plr.fijar(m, r, CFG_RED2, estado=CONFIRMADA, sha_original=sha)
            self.assertEqual(estado, "fijado")
            e = final["bitacora"][0]
            self.assertEqual((e["evento"], e["huella_anterior"], e["respaldo"]["sha256"]), ("reemplazo", huella, sha))
            self.assertEqual(e["respaldo"]["ruta"], respaldo.name)


if __name__ == "__main__":
    unittest.main()
