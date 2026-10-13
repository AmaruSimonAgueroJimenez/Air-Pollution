"""Invariantes de la bandera real ``<raíz v2>/paneles/calidad_<pol>.parquet`` (sólo lectura).

Se salta si la bandera todavía no existe. La raíz v2 sale del entorno (``AIR_POLLUTION_MODELO_1KM_ROOT`` o su valor
por omisión) y la v1 de ``AIR_POLLUTION_MODELO_1KM_V1_ROOT``. Para comprobar la alineación 1 a 1 se leen tres
columnas del panel v1; nada se escribe.
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import calidad_v2 as cv  # noqa: E402

R = rv.RutasV2.desde_entorno()
METAS = {pol: rv.leer_json(cv.ruta_meta(R, pol)) for pol in cv.CONTAMINANTES}
HAY = all(METAS.values()) and all(cv.ruta_calidad(R, pol).exists() for pol in cv.CONTAMINANTES)


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(8 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


@unittest.skipUnless(HAY, f"todavía no hay bandera de calidad en {R.raiz_v2 / 'paneles'}")
class BanderaRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pyarrow.parquet as pq

        cls.bandera, cls.panel = {}, {}
        for pol in cv.CONTAMINANTES:
            cls.bandera[pol] = pq.read_table(cv.ruta_calidad(R, pol), columns=cv.COLUMNAS).to_pandas()
            cls.panel[pol] = pq.read_table(R.panel(pol), columns=["estacion", "ts_utc", "version"],
                                           read_dictionary=["estacion", "version"]).to_pandas()

    def test_esquema_archivo_y_huella(self):
        for pol, m in METAS.items():
            with self.subTest(pol=pol):
                q = self.bandera[pol]
                self.assertEqual((m["schema"], m["contaminante"]), (cv.SCHEMA, pol))
                self.assertEqual(m["bitacora"][0]["evento"], "fijado")
                self.assertEqual(m["archivo"]["columnas"], cv.COLUMNAS)
                self.assertEqual(m["archivo"]["sha256"], sha256(cv.ruta_calidad(R, pol)))
                self.assertEqual(m["panel"]["sha256"], m["panel"]["sha256_declarado_v1"])
                huella = cv.sha256_json({"schema": cv.SCHEMA, "contaminante": pol, "panel_sha256": m["panel"]["sha256"],
                                         "parametros": m["parametros"], "contenido": cv.huella_columnas(q, cv.COLUMNAS)})
                self.assertEqual(huella, m["huella_calidad"])

    def test_alineada_1_a_1_con_el_panel(self):
        for pol, m in METAS.items():
            with self.subTest(pol=pol):
                q, p = self.bandera[pol], self.panel[pol]
                self.assertEqual(len(q), len(p))
                self.assertEqual(len(q), m["panel"]["filas"])
                self.assertTrue(np.array_equal(q["ts_utc"].to_numpy("datetime64[ns]"), p["ts_utc"].to_numpy("datetime64[ns]")))
                self.assertTrue(np.array_equal(q["estacion"].astype(str).to_numpy(), p["estacion"].astype(str).to_numpy()))
                fuente = np.where(p["version"].astype(str).to_numpy() == cv.RED_SNIFA, cv.RED_SNIFA, cv.RED_SINCA)
                self.assertTrue(np.array_equal(q["fuente"].to_numpy(dtype=object), fuente.astype(object)))
                self.assertEqual(cv.huella_columnas(q, ["estacion", "ts_utc"]), m["alineacion"]["huella_claves"])

    def test_toda_fila_tiene_bandera_de_su_red(self):
        for pol, m in METAS.items():
            with self.subTest(pol=pol):
                q = self.bandera[pol]
                self.assertEqual(int(q["qc"].isna().sum()), m["conciliacion"]["sin_bandera"])
                self.assertEqual(m["conciliacion"]["sin_bandera"], 0)
                self.assertEqual(m["conciliacion"]["sin_bandera_por_motivo"], {})
                for red, codigos in cv.QC_DE_FUENTE.items():
                    self.assertTrue(q.loc[q["fuente"] == red, "qc"].isin(codigos).all(), red)
                self.assertTrue(m["conciliacion"]["mismas_claves_que_la_replica"])

    def test_distribucion_suma_las_filas(self):
        for pol, m in METAS.items():
            with self.subTest(pol=pol):
                q, d = self.bandera[pol], m["distribucion"]
                n = len(q)
                for clave in ("total", "por_anio", "por_estacion"):
                    self.assertEqual(sum(x["filas"] for x in d[clave]), n, clave)
                    for x in d[clave]:
                        self.assertEqual(x["filas"], sum(x[c] for c in cv.CATEGORIAS))
                conteo = q.groupby(["fuente", "qc"]).size()
                for t in d["total"]:
                    for c in cv.QC_DE_FUENTE[t["fuente"]]:
                        self.assertEqual(t[c], int(conteo.get((t["fuente"], c), 0)))

    def test_reloj_y_auditoria(self):
        for pol, m in METAS.items():
            with self.subTest(pol=pol):
                self.assertTrue(m["convenciones"]["prueba_desfase_sinca"]["confirma_el_reloj"])
                self.assertEqual(m["parametros"]["reloj_sinca"]["desplazamiento_h"], 3)
                a = m["resumen"]["auditoria_coincide"]
                self.assertTrue(a["sinca_panel"])
                self.assertTrue(a["sinca_antes_de_rachas"])
                if pol in cv.CONTAMINANTES_SNIFA:
                    self.assertTrue(a["snifa_antes_de_rachas"])
                self.assertIn(a["sinca_anual"], (True, None))

    def test_procedencia_sin_rutas_absolutas(self):
        for pol, m in METAS.items():
            with self.subTest(pol=pol):
                t = m["traza"]
                for clave in ("git", "codigo", "contrato", "config", "insumos", "bibliotecas", "hilos", "semillas",
                              "insumos_externos"):
                    self.assertIn(clave, t)
                self.assertLessEqual(t["hilos"]["configurados"], 12)
                self.assertEqual(t["insumos"][f"panel_{pol}"]["sha256"], m["panel"]["sha256"])
                self.assertEqual(t["insumos_externos"]["derivado_sinca"]["archivos"],
                                 sum(1 for x in m["reconstruccion"]["derivado_sinca"]["estaciones"] if x.get("archivo")))
                texto = cv.ruta_meta(R, pol).read_text(encoding="utf-8")
                for prohibido in ("/Users/", "GoogleDrive", "CloudStorage", "/Volumes/"):
                    self.assertNotIn(prohibido, texto)

    def test_tablas_del_repositorio(self):
        lateral = rv.leer_json(R.salidas_v2 / cv.NOMBRE_LATERAL)
        self.assertIsNotNone(lateral)
        self.assertEqual(lateral["huellas_calidad"], {pol: METAS[pol]["huella_calidad"] for pol in cv.CONTAMINANTES})
        for nombre, sha in lateral["tablas"].items():
            self.assertEqual(sha256(R.salidas_v2 / nombre), sha, nombre)
        d = pd.read_csv(R.salidas_v2 / cv.TABLA_DISTRIBUCION, dtype={"anio": str})
        for pol, m in METAS.items():
            self.assertEqual(int(d.loc[(d["contaminante"] == pol) & (d["anio"] == "total"), "filas"].sum()),
                             m["panel"]["filas"])
        for nombre in (cv.NOMBRE_LATERAL, *lateral["tablas"]):
            texto = (R.salidas_v2 / nombre).read_text(encoding="utf-8")
            for prohibido in ("/Users/", "GoogleDrive", "CloudStorage", "/Volumes/"):
                self.assertNotIn(prohibido, texto, nombre)


if __name__ == "__main__":
    unittest.main()
