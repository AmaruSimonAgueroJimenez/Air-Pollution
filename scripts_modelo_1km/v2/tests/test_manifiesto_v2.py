"""Invariantes del manifiesto real ``<raíz v2>/pliegues_v2.json`` (sólo lectura).

Se salta si el manifiesto todavía no existe. La ruta sale de ``PLIEGUES_V2_MANIFIESTO`` o, si no está
definida, de la raíz v2 del entorno (``AIR_POLLUTION_MODELO_1KM_ROOT`` o su valor por omisión).
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import pliegues_v2 as pv  # noqa: E402


def _ruta_manifiesto() -> Path:
    explicita = os.environ.get("PLIEGUES_V2_MANIFIESTO")
    return Path(explicita) if explicita else rv.RutasV2.desde_entorno().manifiesto_pliegues


RUTA = _ruta_manifiesto()
M = json.loads(RUTA.read_text(encoding="utf-8")) if RUTA.exists() else None
CFG = json.loads((V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8"))


@unittest.skipIf(M is None, f"todavía no hay manifiesto en {RUTA}")
class ManifiestoRealTests(unittest.TestCase):
    def test_huella_y_esquema(self):
        self.assertEqual(M["schema"], pv.SCHEMA)
        self.assertEqual(pv.huella_pliegues(M), M["huella_pliegues"])
        self.assertEqual(M["bitacora"][0]["evento"], "fijado")
        self.assertEqual(sorted(M["contaminantes"]), ["no2", "pm25"])

    def test_parametros_de_la_configuracion(self):
        p = M["parametros"]
        self.assertEqual(p["LOSO-D"]["umbral_km"], CFG["protocolos"]["LOSO-D"]["umbral_km"])
        self.assertEqual(p["LBO-10"]["radio_km"], CFG["protocolos"]["LBO-10"]["exclusion_adicional"]["radio_km"])
        self.assertEqual((p["BLQ-75"]["crs"], p["BLQ-75"]["lado_m"]), ("EPSG:32719", 75000.0))
        self.assertEqual(p["BLQ-75"]["origen_m"], CFG["protocolos"]["BLQ-75"]["origen_m"]["provisional"])

    def test_procedencia(self):
        t = M["traza"]
        for clave in ("git", "codigo", "contrato", "config", "insumos", "bibliotecas", "hilos", "semillas"):
            self.assertIn(clave, t)
        self.assertEqual(t["contrato"]["sha256"], CFG["contrato"]["sha256"])
        for pol in ("pm25", "no2"):
            panel = M["contaminantes"][pol]["panel"]
            self.assertEqual(panel["sha256"], panel["sha256_declarado_v1"])
            self.assertEqual(t["insumos"][f"panel_{pol}"]["sha256"], panel["sha256"])
        self.assertLessEqual(t["hilos"]["configurados"], 12)
        texto = RUTA.read_text(encoding="utf-8")
        for prohibido in ("/Users/", "GoogleDrive", "CloudStorage"):
            self.assertNotIn(prohibido, texto)

    def test_cada_protocolo_es_coherente(self):
        for pol, d in M["contaminantes"].items():
            total, estaciones = d["panel"]["filas"], sorted(d["estaciones"])
            for prot in pv.PROTOCOLOS:
                pl = d["protocolos"][prot]["pliegues"]
                with self.subTest(pol=pol, prot=prot):
                    self.assertEqual(M["conteos"][pol][prot], len(pl))
                    self.assertEqual([f["k"] for f in pl], list(range(len(pl))))
                    self.assertEqual([f["semilla"] for f in pl], [[42, k] for k in range(len(pl))])
                    self.assertEqual(sum(f["filas_prueba"] for f in pl), total)
                    for f in pl:
                        self.assertEqual(f["filas_prueba"] + f["filas_entrenamiento_disponibles"] + f["filas_fuera_del_pliegue"], total)
                        self.assertTrue(set(f["estaciones_prueba"]) <= set(f["excluidas"]) or prot == "LPO")
                    if prot != "LPO":
                        prueba = sorted(s for f in pl for s in f["estaciones_prueba"])
                        self.assertEqual(prueba, estaciones)                      # partición de las estaciones
                    else:
                        self.assertTrue(all(f["excluidas"] == [] for f in pl))

    def test_lbo_10_comparte_grupos_con_loso_d_y_los_amplia(self):
        for pol, d in M["contaminantes"].items():
            loso, lbo = d["protocolos"]["LOSO-D"]["pliegues"], d["protocolos"]["LBO-10"]["pliegues"]
            self.assertEqual([f["grupo"] for f in loso], [f["grupo"] for f in lbo])
            for a, b in zip(loso, lbo):
                self.assertEqual(a["estaciones_prueba"], b["estaciones_prueba"])
                self.assertTrue(set(a["excluidas"]) <= set(b["excluidas"]))
                self.assertLessEqual(b["filas_entrenamiento_disponibles"], a["filas_entrenamiento_disponibles"])

    def test_conglomerados_del_contrato_y_celdas_compartidas(self):
        celda = {e["estacion"]: e["celda"] for e in M["estaciones"]}
        for pol, d in M["contaminantes"].items():
            grupo_de = {s: f["grupo"] for f in d["protocolos"]["LOSO-D"]["pliegues"] for s in f["estaciones_prueba"]}
            for ej in d["diagnosticos"]["ejemplos_del_contrato"]:
                self.assertTrue(ej["juntas"], f"{pol}: {ej}")
            for ejemplo in CFG["protocolos"]["LOSO-D"]["retira_juntos_ejemplos"]:
                presentes = [s for s in ejemplo if s in grupo_de]
                self.assertLessEqual(len({grupo_de[s] for s in presentes}), 1, f"{pol}: {ejemplo}")
            por_celda: dict[int, set] = {}
            for s in d["estaciones"]:
                por_celda.setdefault(celda[s], set()).add(grupo_de[s])
            self.assertTrue(all(len(g) == 1 for g in por_celda.values()), f"{pol}: celdas compartidas separadas")

    def test_bloques_registrados(self):
        est = {e["estacion"]: e for e in M["estaciones"]}
        origen, lado = M["parametros"]["BLQ-75"]["origen_m"], M["parametros"]["BLQ-75"]["lado_m"]
        for pol, d in M["contaminantes"].items():
            for f in d["protocolos"]["BLQ-75"]["pliegues"]:
                b = f["bloque"]
                self.assertEqual(b["este_min_m"], origen[0] + b["ix"] * lado)
                self.assertEqual(b["norte_min_m"], origen[1] + b["iy"] * lado)
                for s in f["estaciones_prueba"]:
                    self.assertTrue(b["este_min_m"] <= est[s]["utm19s_este_m"] < b["este_max_m"])
                    self.assertTrue(b["norte_min_m"] <= est[s]["utm19s_norte_m"] < b["norte_max_m"])
                    self.assertEqual(est[s]["bloque_blq75"], f["grupo"])

    def test_lro_y_lpo_como_la_v1(self):
        regiones_pm25 = [f["grupo"] for f in M["contaminantes"]["pm25"]["protocolos"]["LRO"]["pliegues"]]
        self.assertEqual(regiones_pm25, ["RI", "RII", "RIII", "RIV", "RIX", "RM", "RV", "RVI", "RVII", "RVIII", "RX",
                                         "RXI", "RXII", "RXIV", "RXV"])
        self.assertNotIn("RXVI", [e["region_lro"] for e in M["estaciones"]])
        for pol in ("pm25", "no2"):
            ventanas = [f["grupo"] for f in M["contaminantes"][pol]["protocolos"]["LPO"]["pliegues"]]
            self.assertEqual(ventanas, ["2000–2003", "2004–2007", "2008–2011", "2012–2015", "2016–2019", "2020–2023",
                                        "2024–2026"])


if __name__ == "__main__":
    unittest.main()
