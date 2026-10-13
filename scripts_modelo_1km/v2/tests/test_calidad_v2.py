"""Pruebas de ``calidad_v2``: reloj, réplicas de la v1, agregación, rachas, conciliación y ciclo completo.

Las pruebas de punta a punta corren sobre carpetas temporales con un catálogo, una red SNIFA, una grilla, un derivado
SINCA y paneles de juguete. Los paneles se arman aquí con las reglas de la v1 escritas de nuevo, en forma directa y
sin las funciones del módulo, para que la prueba no sea circular. Nada lee ni escribe datos reales, salvo
``CitasV1Tests``, que sólo lee el código de la v1 para comprobar que las líneas citadas siguen diciendo lo mismo.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
REPO = V2.parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import calidad_v2 as cv  # noqa: E402
import pliegues_v2 as pv  # noqa: E402

KM_POR_GRADO = 6371.0 * np.pi / 180.0
LAT0, LON0 = -33.0, -70.5
T0 = pd.Timestamp("2020-01-01 00:00")
RANGO = {"pm25": (0.0, 1500.0), "no2": (0.0, 1000.0)}
SNIFA = {"charrua": "SNIFA-CHARRUA", "progreso": "SNIFA-PROGRESO", "el_penon": "SNIFA-ELPENON"}
FACTOR = {"charrua": 1.0, "progreso": 1.0, "el_penon": 22.414 / 46.0055}
COORD_KM = {"charrua": 300.0, "progreso": 310.0, "el_penon": 320.0, "quinel": 330.0}
CON_CELDA = {"S1", "S2", *SNIFA.values()}
VA, VB, VC, VD, VE, VF = ("a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64, "f" * 64)


def lat_a(km: float) -> float:
    return LAT0 + km / KM_POR_GRADO


def horas(desde, n: int) -> pd.DatetimeIndex:
    return pd.Timestamp(desde) + pd.to_timedelta(np.arange(n), unit="h")


def fila_snifa(st, doc, fecha, h, valor, unidad="ppb", pol="no2", nativo=True, numerico=True, c_valor=False,
               c_codigo=False) -> dict:
    return {"station_id": st, "pollutant": pol, "numeric_usable": numerico, "usable_native": nativo and numerico,
            "date_local": fecha, "hour_index": h, "value": float(valor), "unit": unidad, "document_id": doc,
            "value_conflict": c_valor, "quality_conflict": c_codigo, "latitude": lat_a(COORD_KM[st]), "longitude": LON0}


class Mundo:
    """Raíces temporales completas con datos de juguete.

    * SINCA: S1 (dos versiones de PM2,5; version_sinca elige la que parte antes) y S2 con una racha de 30 valores
      idénticos; S3 usable pero sin celda; S9 no usable. S1 tiene una fila sin dato, dos fuera de rango y un registro
      solapado no seleccionado.
    * SNIFA (NO2): documentos 0–23 y 1–24; un documento cuya etiqueta 24 cae fuera de rango (queda como 0–23, igual
      que en la v1); otro cuya etiqueta 24 no es numeric_usable; El Peñón con dos documentos superpuestos (tres horas
      promediadas, una con un registro no nativo); y filas que la v1 descarta (Quinel, SO2, unidad, numeric_usable).
    """

    def __init__(self, base: Path):
        self.base = base
        self.repo = base / "repo"
        scripts = self.repo / "scripts_modelo_1km" / "v2"
        scripts.mkdir(parents=True)
        shutil.copy2(V2 / rv.NOMBRE_CONTRATO, scripts / rv.NOMBRE_CONTRATO)
        shutil.copy2(V2 / rv.NOMBRE_CONFIG, scripts / rv.NOMBRE_CONFIG)
        self.r = rv.RutasV2(raiz_v2=base / "v2", raiz_v1=base / "v1", datos=base / "datos", repo=self.repo,
                            scripts_v2=scripts)
        self.raiz_der = base / "derived"
        self.derivado = cv.derivado_sinca(self.raiz_der)
        self.auditoria = base / "sin_auditoria.json"
        self._catalogo()
        self._grilla()
        self._snifa()
        self._sinca()

    def _catalogo(self) -> None:
        filas = [("RM", "S1", 0.0, 13101, True), ("RM", "S2", 10.0, 13101, True), ("RV", "S3", 200.0, 5101, True),
                 ("RV", "S9", 210.0, 5101, False)]
        cat = pd.DataFrame([{"region_sinca": reg, "estacion": e, "nombre": f"Sitio {e}", "lat": lat_a(km), "lon": LON0,
                             "cod_comuna_geografica": cod, "usable_geoespacial": u} for reg, e, km, cod, u in filas])
        self.r.catalogo_sinca.parent.mkdir(parents=True)
        cat.to_csv(self.r.catalogo_sinca, index=False)

    def _grilla(self) -> None:
        g = self.r.grilla_v1
        g.mkdir(parents=True)
        pd.DataFrame({"celda": [11, 12, 21, 22, 23], "lat": [lat_a(k) for k in (0.0, 10.0, 300.0, 310.0, 320.0)],
                      "lon": [LON0] * 5, "cod_comuna": [13101, 13101, 8101, 8102, 2101]}).to_parquet(
            g / "celdas.parquet", index=False)
        pd.DataFrame({"estacion": ["S1", "S2", "S3", "S9"], "celda": [11, 12, -1, -1]}).to_parquet(
            g / "estaciones_enlaces.parquet", index=False)
        pd.DataFrame({"estacion": list(SNIFA.values()), "celda": [21, 22, 23]}).to_parquet(
            g / "estaciones_enlaces_adicional.parquet", index=False)

    def _snifa(self) -> None:
        f = []
        f += [fila_snifa("charrua", 100, "2020-01-02", h, 3 + 0.1 * h, nativo=h != 5, c_valor=h == 5) for h in range(24)]
        f += [fila_snifa("charrua", 101, "2020-01-03", h, 4 + 0.1 * h if h < 24 else -5.0) for h in range(1, 25)]
        f += [fila_snifa("progreso", 200, "2020-01-02", h, 2 + 0.2 * h, unidad="ug/m3N") for h in range(1, 25)]
        f += [fila_snifa("progreso", 201, "2020-01-03", h, 6.0 + h, unidad="ppbv") for h in range(4)]
        f += [fila_snifa("progreso", 201, "2020-01-03", 24, 1.0, unidad="ppbv", numerico=False)]
        f += [fila_snifa("el_penon", 300, "2020-01-02", h, 4.0 + 0.1 * h, unidad="ug/m3N") for h in range(1, 25)]
        f += [fila_snifa("el_penon", 301, "2020-01-02", h, 1.0 + h, nativo=h != 0, c_codigo=h == 0) for h in range(3)]
        f += [fila_snifa("quinel", 400, "2020-01-02", h, 10.0, unidad="ug/m3N") for h in range(4)]
        f += [fila_snifa("charrua", 102, "2020-01-02", h, 1.0, pol="so2") for h in range(3)]
        f += [fila_snifa("charrua", 103, "2020-01-03", 0, 2.0, unidad="mg/m3N")]
        f += [fila_snifa("charrua", 104, "2020-01-03", 0, 2.0, numerico=False)]
        df = pd.DataFrame(f)
        df["hour_index"] = df["hour_index"].astype("int16")
        self.r.snifa.parent.mkdir(parents=True)
        df.to_parquet(self.r.snifa, index=False)

    def escribir_version(self, est, pol, version, ts_local, obs, qc, seleccionada=None, since="2000-01-01",
                         until="2020-01-03", creado="2026-09-15T10:00:00+00:00") -> None:
        carpeta = self.derivado / f"estacion={est}" / f"contaminante={pol}" / f"version={version}"
        carpeta.mkdir(parents=True, exist_ok=True)
        n = len(qc)
        pd.DataFrame({"estacion": est, "ts_local": pd.to_datetime(list(ts_local)).astype("datetime64[us]"),
                      "obs": np.asarray(obs, dtype="float64"), "qc_observacion": list(qc),
                      "seleccionada": list(seleccionada) if seleccionada is not None else [True] * n}).to_parquet(
            carpeta / "observaciones.parquet", index=False)
        sha = hashlib.sha256((carpeta / "observaciones.parquet").read_bytes()).hexdigest()
        (carpeta / "manifest.json").write_text(json.dumps(
            {"created_utc": creado, "inputs": {"since": since, "until": until},
             "files": [{"name": "observaciones.parquet", "rows": n, "sha256": sha}]}), encoding="utf-8")

    def _sinca(self) -> None:
        i = np.arange(74)
        obs = 10.0 + (i % 5) * 1.5 + i * 0.01
        qc = [cv.QC_SINCA[k % 3] for k in i]
        obs[7], qc[7] = np.nan, "sin_dato"
        obs[9], obs[11] = 2000.0, -1.0
        ts = list(horas(T0, 74)) + [horas(T0, 74)[5]]                      # registro solapado, no seleccionado
        self.escribir_version("S1", "pm25", VA, ts, list(obs) + [999.0], qc + ["validado"], [True] * 74 + [False])
        self.escribir_version("S1", "pm25", VB, horas(T0, 74), 50.0 + i, [cv.QC_SINCA[k % 3] for k in i],
                              since="2020-01-02", creado="2026-09-16T10:00:00+00:00")
        j = np.arange(40)
        self.escribir_version("S2", "pm25", VC, horas(T0 + pd.Timedelta(hours=1), 40), np.where(j < 30, 5.0, 20.0 + j),
                              ["validado" if k < 30 else ("no_validado" if k % 2 else "preliminar") for k in j])
        self.escribir_version("S3", "pm25", VD, horas("2020-01-01 05:00", 10), 7.0 + np.arange(10), ["validado"] * 10)
        self.escribir_version("S9", "pm25", VE, horas("2020-01-01 05:00", 10), 8.0 + np.arange(10), ["validado"] * 10)
        k = np.arange(20)
        self.escribir_version("S1", "no2", VF, horas("2020-01-02", 20), 1.5 + 0.25 * k,
                              [cv.QC_SINCA[(x + 1) % 3] for x in k])

    def panel(self, pol: str, versiones: dict, alterar=None, sha_declarado: str | None = None) -> pd.DataFrame:
        """Panel de juguete con las reglas de la v1, escritas aquí de nuevo en forma directa."""
        filas = []
        lo, hi = RANGO[pol]
        for est, ver in versiones.items():
            df = pd.read_parquet(self.derivado / f"estacion={est}" / f"contaminante={pol}" / f"version={ver}"
                                 / "observaciones.parquet")
            for f in df.itertuples(index=False):
                if f.seleccionada and not pd.isna(f.obs) and lo <= f.obs <= hi:
                    filas.append((est, pd.Timestamp(f.ts_local) + pd.Timedelta(hours=3), float(f.obs), ver))
        if pol == "no2":
            o = pd.read_parquet(self.r.snifa)
            o = o[o["station_id"].isin(list(SNIFA)) & o["numeric_usable"] & (o["pollutant"] == "no2")
                  & o["unit"].isin(["ppb", "ppbv", "ug/m3N"])].copy()
            o["obs"] = [v * FACTOR[s] if u == "ug/m3N" else v for v, u, s in zip(o["value"], o["unit"], o["station_id"])]
            o = o[(o["obs"] >= lo) & (o["obs"] <= hi)]
            maximo = o.groupby("document_id")["hour_index"].max().to_dict()
            for f in o.itertuples(index=False):
                hora = int(f.hour_index) - (1 if maximo[f.document_id] == 24 else 0)
                filas.append((SNIFA[f.station_id], pd.Timestamp(f.date_local) + pd.Timedelta(hours=hora + 4),
                              float(f.obs), "snifa"))
        t = pd.DataFrame(filas, columns=["estacion", "ts_utc", "obs", "version"])
        g = (t.groupby(["estacion", "ts_utc"], as_index=False)
             .agg(obs=("obs", "mean"), n=("obs", "size"), version=("version", "first"))
             .sort_values(["estacion", "ts_utc"]).reset_index(drop=True))
        racha = np.zeros(len(g), dtype=bool)
        inicio = 0
        for k in range(1, len(g) + 1):
            if k == len(g) or g.at[k, "estacion"] != g.at[inicio, "estacion"] or g.at[k, "obs"] != g.at[inicio, "obs"]:
                if k - inicio >= 24:
                    racha[inicio:k] = True
                inicio = k
        local = g["ts_utc"] - pd.Timedelta(hours=4)
        dentro = (local >= pd.Timestamp("2020-01-01")) & (local < pd.Timestamp("2020-01-04"))
        p = g[~racha & g["estacion"].isin(CON_CELDA) & dentro].copy()
        p["obs"] = p["obs"].astype("float32")
        p["n"] = p["n"].astype("int64")
        p["anio"] = (p["ts_utc"] - pd.Timedelta(hours=4)).dt.year.astype("int16")
        p = p.sample(frac=1.0, random_state=11).reset_index(drop=True)      # otro orden que el de la réplica
        if alterar is not None:
            alterar(p)
        p = p[["estacion", "ts_utc", "obs", "n", "version", "anio"]].reset_index(drop=True)
        ruta = self.r.panel(pol)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        p.to_parquet(ruta, index=False)
        sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
        meta = {"sha256": sha_declarado or sha, "reloj_sinca": "UTC-4 fijo; etiqueta=fin", "desde": "2020-01-01",
                "hasta": "2020-01-03", "qc_racha_minima": 24, "redes": ["sinca", "snifa"], "codigo": "prueba"}
        self.r.panel_meta(pol).write_text(json.dumps(meta), encoding="utf-8")
        return p


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------
class RelojTests(unittest.TestCase):
    def test_desplazamiento_de_la_etiqueta(self):
        self.assertEqual(cv.desplazamiento_sinca(4, "fin"), 3)
        self.assertEqual(cv.desplazamiento_sinca(4, "inicio"), 4)
        with self.assertRaises(ValueError):
            cv.desplazamiento_sinca(4, "mitad")

    def test_etiqueta_18_local_es_el_bin_de_las_21_utc(self):
        s = cv.a_bin_utc(pd.Series(pd.to_datetime(["2024-06-01 18:00", "2024-06-02 00:00"])), 3)
        self.assertEqual(list(s), [pd.Timestamp("2024-06-01 21:00"), pd.Timestamp("2024-06-02 03:00")])
        # La etiqueta 00 del día D es el bin de las 23:00 locales del día anterior.
        self.assertEqual(s.iloc[1] - pd.Timedelta(hours=4), pd.Timestamp("2024-06-01 23:00"))
        self.assertEqual(str(s.dtype), "datetime64[ns]")

    def test_reloj_del_panel(self):
        r = cv.reloj_del_panel({"reloj_sinca": "UTC-4 fijo; etiqueta=fin"})
        self.assertEqual((r["offset_utc_h"], r["etiqueta"], r["desplazamiento_h"]), (4, "fin", 3))
        for malo in ({}, {"reloj_sinca": "UTC-3 civil"}, {"reloj_sinca": "UTC-4 fijo; etiqueta=centro"}):
            with self.subTest(malo=malo), self.assertRaises(SystemExit):
                cv.reloj_del_panel(malo)

    def test_periodo_por_dia_local(self):
        self.assertEqual(cv.periodo_del_panel({"desde": "2000-01-01", "hasta": "2026-09-13"}),
                         (pd.Timestamp("2000-01-01"), pd.Timestamp("2026-09-14")))
        with self.assertRaises(SystemExit):
            cv.periodo_del_panel({"desde": "2000-01-01"})

    def test_hora_local_snifa_por_documento(self):
        np.testing.assert_array_equal(cv.hora_local_snifa([1, 1, 1, 2, 2, 2], [1, 2, 24, 0, 1, 23]), [0, 1, 23, 0, 1, 23])

    def test_claves_exigen_horas_enteras(self):
        k = cv.claves(np.array([0, 2]), pd.to_datetime(["2020-01-01 00:00", "2020-01-01 01:00"]).to_numpy())
        self.assertEqual(int(k[1] - k[0]), 2 * cv.BASE_CLAVE + 1)
        with self.assertRaises(ValueError):
            cv.claves(np.array([0]), pd.to_datetime(["2020-01-01 00:30"]).to_numpy())


class AgregadoYRachasTests(unittest.TestCase):
    def test_hora_agregada_toma_la_peor_bandera(self):
        f = pd.DataFrame({"ts_utc": pd.to_datetime(["2020-01-01 00:00"] * 2 + ["2020-01-01 01:00"] * 2
                                                   + ["2020-01-01 02:00"]),
                          "obs": [1.0, 2.0, 3.0, 5.0, 7.0], "qc": np.array([0, 1, 2, 2, 0], dtype="int8")})
        a = cv.agregar_por_hora(f)
        self.assertEqual(a["obs"].tolist(), [1.5, 4.0, 7.0])
        self.assertEqual(a["n"].tolist(), [2, 2, 1])
        self.assertEqual([cv.QC_TODOS[c] for c in a["qc"]], ["preliminar", "no_validado", "validado"])
        self.assertEqual(a["mixta"].tolist(), [True, False, False])
        s = pd.DataFrame({"estacion": ["X", "X"], "ts_utc": pd.to_datetime(["2020-01-01"] * 2), "obs": [1.0, 2.0],
                          "qc": np.array([cv.CODIGO_QC["usable_native"], cv.CODIGO_QC["solo_numeric_usable"]], "int8")})
        b = cv.agregar_por_hora(s, por=("estacion", "ts_utc"))
        self.assertEqual(cv.QC_TODOS[int(b["qc"].iloc[0])], "solo_numeric_usable")

    def test_sin_repetidos_no_toca_el_valor(self):
        f = pd.DataFrame({"ts_utc": pd.to_datetime(["2020-01-01 01:00", "2020-01-01 00:00"]),
                          "obs": [0.1 + 0.2, 1 / 3], "qc": np.array([2, 0], dtype="int8")})
        a = cv.agregar_por_hora(f)
        self.assertEqual(a["obs"].tolist(), [1 / 3, 0.1 + 0.2])               # ordenado por hora, bit a bit
        self.assertEqual(a["n"].tolist(), [1, 1])

    def test_rachas_como_la_v1(self):
        est = ["A"] * 7 + ["B"] * 3
        ts = pd.to_datetime(["2020-01-01 00:00", "2020-01-01 01:00", "2020-01-05 00:00", "2020-01-05 01:00",
                             "2020-01-05 02:00", "2020-01-05 03:00", "2020-01-09 00:00",
                             "2020-01-01 00:00", "2020-01-01 01:00", "2020-01-01 02:00"]).to_numpy()
        obs = [1, 1, 1, 2, 2, 2, 2, 2, 2, 2]
        # A: 1,1,1 (con un hueco de días, que no corta) y 2,2,2,2; B: 2,2,2, que no se une a la corrida de A.
        np.testing.assert_array_equal(cv.marcar_rachas(est, ts, obs, 3), [True] * 10)
        np.testing.assert_array_equal(cv.marcar_rachas(est, ts, obs, 4), [False] * 3 + [True] * 4 + [False] * 3)
        orden = np.random.default_rng(3).permutation(10)
        np.testing.assert_array_equal(cv.marcar_rachas(np.array(est)[orden], ts[orden], np.array(obs)[orden], 4),
                                      (np.array([False] * 3 + [True] * 4 + [False] * 3))[orden])
        np.testing.assert_array_equal(cv.marcar_rachas(est, ts, obs, 0), [False] * 10)

    def test_huella_de_columnas(self):
        df = pd.DataFrame({"estacion": ["a", "b"], "ts_utc": pd.to_datetime(["2020-01-01", "2020-01-02"]),
                           "qc": ["validado", None], "fuente": ["sinca", "sinca"]})
        h = cv.huella_columnas(df, cv.COLUMNAS)
        self.assertEqual(h, cv.huella_columnas(df.copy(), cv.COLUMNAS))
        otro = df.copy()
        otro.loc[1, "qc"] = "preliminar"
        self.assertNotEqual(h, cv.huella_columnas(otro, cv.COLUMNAS))
        self.assertNotEqual(h, cv.huella_columnas(df.iloc[::-1].reset_index(drop=True), cv.COLUMNAS))


class VersionSincaTests(unittest.TestCase):
    def test_orden_de_version_sinca(self):
        with tempfile.TemporaryDirectory(prefix="calidad-version-") as tmp:
            carpeta = Path(tmp) / "estacion=X" / "contaminante=pm25"
            versiones = {"v1": ("2000-01-01", "2026-09-13", "2026-09-15T10:00:00+00:00"),
                         "v2": ("2026-09-01", "2026-09-13", "2026-09-16T10:00:00+00:00"),
                         "v3": ("2000-01-01", "2026-09-13", "2026-09-17T10:00:00+00:00"),
                         "v4": None}
            for v, datos in versiones.items():
                d = carpeta / f"version={v}"
                d.mkdir(parents=True)
                pd.DataFrame({"obs": [1.0]}).to_parquet(d / "observaciones.parquet", index=False)
                if datos:
                    since, until, creado = datos
                    (d / "manifest.json").write_text(json.dumps(
                        {"created_utc": creado, "inputs": {"since": since, "until": until},
                         "files": [{"name": "observaciones.parquet", "rows": 1}]}), encoding="utf-8")
            self.assertEqual([c["version"] for c in cv.candidatas_sinca(carpeta)], ["v3", "v1", "v2", "v4"])


class AuditoriaTests(unittest.TestCase):
    def test_coincidencia_con_la_precision_publicada(self):
        self.assertTrue(cv.coincide_redondeado(37.746, 37.75))
        self.assertFalse(cv.coincide_redondeado(37.746, 37.8))                # el doble redondeo del md
        self.assertTrue(cv.coincide_redondeado(67.5898, 67.59))
        self.assertTrue(cv.coincide_redondeado(37.5526, 37.55))
        self.assertIsNone(cv.coincide_redondeado(None, 1.0))

    def test_comparacion_por_anio_de_la_etiqueta(self):
        recon = pd.DataFrame({"estacion": ["S1"] * 4, "fuente": "sinca", "usable": True, "en_periodo": True, "n": 1,
                              "ts_utc": pd.to_datetime(["2019-12-31 23:00", "2020-01-01 03:00", "2020-01-01 04:00",
                                                        "2020-06-01 10:00"]),
                              "qc": np.array([0, 1, 0, 2], dtype="int8")})
        out = pd.DataFrame({"fuente": ["sinca"] * 4, "qc": ["validado", "preliminar", "validado", "no_validado"]})
        # 2020-01-01 03:00 UTC es la etiqueta 00:00 del 1 de enero: cuenta en 2020 (año de la etiqueta), no en 2019.
        anual = {"pm25": {"2019": {"validado": 1.0, "preliminar": 0.0, "no_validado": 0.0},
                          "2020": {"validado": 0.333, "preliminar": 0.333, "no_validado": 0.333}}}
        res = cv.comparar_auditoria("pm25", out, recon, {"aplica": False}, 3, anual)
        self.assertTrue(res["sinca_anual"]["coincide"])
        anual["pm25"]["2020"]["validado"] = 0.4
        anual["pm25"]["2021"] = {"validado": 1.0}
        res = cv.comparar_auditoria("pm25", out, recon, {"aplica": False}, 3, anual)
        self.assertFalse(res["sinca_anual"]["coincide"])
        self.assertEqual((res["sinca_anual"]["anios_distintos"], res["sinca_anual"]["anios_solo_en_la_auditoria"]),
                         ([2020], ["2021"]))
        self.assertEqual(res["sinca_panel"]["v2"]["filas"], 4)
        self.assertIsNone(cv.comparar_auditoria("pm25", out, recon, {"aplica": False}, 3, None)["sinca_anual"]["coincide"])


class CitasV1Tests(unittest.TestCase):
    """Las réplicas citan archivo:línea de la v1 (congelada); si una línea cambiara, la réplica dejaría de valer."""

    V1 = REPO / "scripts_modelo_1km"
    QMD = REPO / "docs" / "modelo_1km_horario.qmd"
    CITAS = [
        ("_comun_modelo.py", 66, 'os.environ.get("AIR_POLLUTION_DERIVED_ROOT") or DATA.parent / "derived"'),
        ("_comun_modelo.py", 67, 'SINCA_DERIVADO = DERIVED_ROOT / "modelado" / "SINCA" / "v1"'),
        ("_comun_modelo.py", 78, 'RANGO_VALIDO = {"pm25": (0.0, 1500.0), "no2": (0.0, 1000.0)}'),
        ("_comun_modelo.py", 81, "OFFSET_UTC_H = 4"),
        ("_comun_modelo.py", 82, 'ETIQUETA_SINCA = os.environ.get("MODELO_1KM_ETIQUETA_SINCA", "fin")'),
        ("_comun_modelo.py", 105, 'desplazamiento = OFFSET_UTC_H - (1 if ETIQUETA_SINCA == "fin" else 0)'),
        ("_comun_modelo.py", 656, 'columns=["ts_local", "obs", "qc_observacion", "seleccionada"]'),
        ("_comun_modelo.py", 657, 'df[df["seleccionada"].astype(bool) & df["obs"].notna()]'),
        ("_comun_modelo.py", 659, 'df = df[df["obs"].between(lo, hi)]'),
        ("_comun_modelo.py", 666, 'out["ts_utc"] = sinca_local_a_bin_utc(out["ts_local"])'),
        ("_comun_modelo.py", 668, 'obs=("obs", "mean"), n=("obs", "size")'),
        ("_red_adicional.py", 37, "OFFSET_UTC_H_SNIFA = 4"),
        ("_red_adicional.py", 38, "PPB_POR_UG_M3N_NO2 = 22.414 / 46.0055"),
        ("_red_adicional.py", 43, '"charrua":  {"estacion": "SNIFA-CHARRUA"'),
        ("_red_adicional.py", 44, '"progreso": {"estacion": "SNIFA-PROGRESO"'),
        ("_red_adicional.py", 45, '"el_penon": {"estacion": "SNIFA-ELPENON"'),
        ("_red_adicional.py", 49, 'CONTAMINANTES_ADICIONALES = ("no2",)'),
        ("_red_adicional.py", 50, 'UNIDADES_ACEPTADAS = ("ppb", "ppbv", "ug/m3N")'),
        ("_red_adicional.py", 62, 'o["numeric_usable"].astype(bool)'),
        ("_red_adicional.py", 68, 'desplaza = (rango == 24).astype("int8")'),
        ("_red_adicional.py", 115, "hora_local(o) + OFFSET_UTC_H_SNIFA"),
        ("_red_adicional.py", 117, 'agg(obs=("obs", "mean"), n=("obs", "size"))'),
        ("_red_adicional.py", 118, 'out["version"] = RED'),
        ("produccion.py", 43, 'QC_RACHA = int(os.environ.get("MODELO_1KM_QC_RACHA", "24"))'),
        ("produccion.py", 85, 'cambio = (o["estacion"] != o["estacion"].shift()) | (o["obs"] != o["obs"].shift())'),
        ("produccion.py", 87, ">= minimo"),
    ]
    CITAS_QMD = [
        (2007, 'local = obs["ts_utc"] - pd.Timedelta(hours=OFFSET_UTC_H)'),
        (2009, 'obs[~obs["racha"] & obs["estacion"].isin(estaciones_con_celda()["estacion"]) & (local >= t0) & (local < t1)]'),
        (2060, 'df[c] = df[c].astype("float32")'),
        (2064, '"reloj_sinca": f"UTC-{OFFSET_UTC_H} fijo; etiqueta={ETIQUETA_SINCA}"'),
    ]

    def _linea(self, ruta: Path, n: int) -> str:
        return ruta.read_text(encoding="utf-8").splitlines()[n - 1]

    def test_lineas_citadas(self):
        for nombre, n, texto in self.CITAS:
            ruta = self.V1 / nombre
            if not ruta.exists():
                self.skipTest(f"no está {nombre}")
            with self.subTest(cita=f"{nombre}:{n}"):
                self.assertIn(texto, self._linea(ruta, n))
        if self.QMD.exists():
            for n, texto in self.CITAS_QMD:
                with self.subTest(cita=f"qmd:{n}"):
                    self.assertIn(texto, self._linea(self.QMD, n))

    def test_constantes_replicadas(self):
        self.assertEqual(cv.RANGO_VALIDO, {"pm25": (0.0, 1500.0), "no2": (0.0, 1000.0)})
        self.assertEqual(cv.PPB_POR_UG_M3N_NO2, 22.414 / 46.0055)
        self.assertEqual({k: v[0] for k, v in cv.ESTACIONES_SNIFA.items()}, {k: v[0] for k, v in pv.ESTACIONES_SNIFA.items()})
        self.assertEqual(cv.UNIDADES_SNIFA, ("ppb", "ppbv", "ug/m3N"))
        self.assertEqual(cv.SUBRUTA_SINCA, ("modelado", "SINCA", "v1"))


# ---------------------------------------------------------------------------
# De punta a punta
# ---------------------------------------------------------------------------
class CicloCompletoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="calidad-v2-")
        self.m = Mundo(Path(self._tmp.name).resolve())
        self.panel_pm25 = self.m.panel("pm25", {"S1": VA, "S2": VC})
        self.panel_no2 = self.m.panel("no2", {"S1": VF})

    def tearDown(self):
        self._tmp.cleanup()

    def ejecutar(self, **kw):
        kw.setdefault("raiz_der", self.m.raiz_der)
        kw.setdefault("auditoria", self.m.auditoria)
        return cv.ejecutar(self.m.r, rv.cargar_config(self.m.r), **kw)

    def bandera(self, pol: str) -> pd.DataFrame:
        return pd.read_parquet(cv.ruta_calidad(self.m.r, pol))

    def test_ciclo(self):
        metas, estados = self.ejecutar()
        self.assertEqual(estados, {"pm25": "fijado", "no2": "fijado"})
        for pol, panel in (("pm25", self.panel_pm25), ("no2", self.panel_no2)):
            with self.subTest(pol=pol):
                q = self.bandera(pol)
                self.assertEqual(list(q.columns), cv.COLUMNAS)
                self.assertEqual(q["estacion"].tolist(), panel["estacion"].tolist())     # alineada 1 a 1
                self.assertTrue((q["ts_utc"].to_numpy() == panel["ts_utc"].to_numpy()).all())
                self.assertFalse(q["qc"].isna().any())
                meta = rv.leer_json(cv.ruta_meta(self.m.r, pol))
                c = meta["conciliacion"]
                self.assertEqual((c["sin_bandera"], c["replica_que_el_panel_no_tiene"]["filas"]), (0, 0))
                self.assertTrue(c["mismas_claves_que_la_replica"])
                self.assertTrue(meta["convenciones"]["prueba_desfase_sinca"]["confirma_el_reloj"])
                self.assertEqual(meta["archivo"]["sha256"],
                                 hashlib.sha256(cv.ruta_calidad(self.m.r, pol).read_bytes()).hexdigest())
                self.assertEqual(meta["huella_calidad"], metas[pol]["huella_calidad"])
                self.assertEqual(sum(t["filas"] for t in meta["distribucion"]["total"]), len(panel))
                self.assertEqual(sum(t["filas"] for t in meta["distribucion"]["por_anio"]), len(panel))
                for clave in ("git", "codigo", "contrato", "config", "insumos", "bibliotecas", "hilos", "semillas"):
                    self.assertIn(clave, meta["traza"])
                self.assertEqual(meta["traza"]["insumos"][f"panel_{pol}"]["raiz"], "raiz_v1")
                self.assertEqual(meta["traza"]["insumos_externos"]["derivado_sinca"]["raiz"], "derivados")
                texto = cv.ruta_meta(self.m.r, pol).read_text(encoding="utf-8")
                self.assertNotIn(str(self.m.base), texto)                                # sin rutas absolutas

        # PM2,5: cada fila lleva el qc_observacion de su etiqueta; los filtros y el período son los de la v1.
        q = self.bandera("pm25")
        s1 = q[q["estacion"] == "S1"]
        i = ((s1["ts_utc"] - pd.Timedelta(hours=3) - T0) / pd.Timedelta(hours=1)).astype(int).to_numpy()
        self.assertEqual(s1["qc"].tolist(), [cv.QC_SINCA[k % 3] for k in i])
        self.assertEqual(sorted(i.tolist()), [k for k in range(1, 73) if k not in (7, 9, 11)])
        s2 = q[q["estacion"] == "S2"]
        j = ((s2["ts_utc"] - pd.Timedelta(hours=4) - T0) / pd.Timedelta(hours=1)).astype(int).to_numpy()
        self.assertEqual(sorted(j.tolist()), list(range(30, 40)))                        # la racha de 30 no entra
        self.assertEqual(s2["qc"].tolist(), ["no_validado" if k % 2 else "preliminar" for k in j])
        self.assertEqual(set(q["fuente"]), {"sinca"})
        meta = rv.leer_json(cv.ruta_meta(self.m.r, "pm25"))
        rp = meta["conciliacion"]["replica"]
        self.assertEqual((rp["en_racha"], rp["no_usables"], rp["sin_celda"]), (30, 10, 20))
        reg = {x["estacion"]: x for x in meta["reconstruccion"]["derivado_sinca"]["estaciones"]}
        self.assertEqual((reg["S1"]["version_sinca"], reg["S1"]["version_usada"]), (VA, VA))
        self.assertEqual(reg["S1"]["filas_seleccionadas"], 71)
        v = meta["filas_por_variante"]["sinca"]
        self.assertEqual(v["todo"]["filas"], 79)
        self.assertEqual(v["solo_validado"]["estaciones"], 1)                           # S2 no tiene validados
        self.assertEqual(v["estaciones_sin_filas_validadas"], ["S2"])

        # NO2: la red SNIFA con su convención por documento y la peor bandera en las horas promediadas.
        q = self.bandera("no2")

        def qc(est, ts):
            return q.loc[(q["estacion"] == est) & (q["ts_utc"] == pd.Timestamp(ts)), "qc"].tolist()

        self.assertEqual(qc("SNIFA-CHARRUA", "2020-01-02 09:00"), ["solo_numeric_usable"])   # conflicto de valor
        self.assertEqual(qc("SNIFA-CHARRUA", "2020-01-02 08:00"), ["usable_native"])
        self.assertEqual(qc("SNIFA-CHARRUA", "2020-01-03 05:00"), ["usable_native"])          # doc. 101 queda 0–23
        self.assertEqual(qc("SNIFA-PROGRESO", "2020-01-03 04:00"), ["usable_native"])         # la etiqueta 24 no cuenta
        self.assertEqual(qc("SNIFA-PROGRESO", "2020-01-02 04:00"), ["usable_native"])         # doc. 200 es 1–24
        self.assertEqual(qc("SNIFA-ELPENON", "2020-01-02 04:00"), ["solo_numeric_usable"])    # promedio con uno no nativo
        self.assertEqual(qc("SNIFA-ELPENON", "2020-01-02 05:00"), ["usable_native"])
        self.assertEqual(set(q.loc[q["estacion"].str.startswith("SNIFA"), "fuente"]), {"snifa"})
        self.assertEqual(set(q.loc[q["estacion"] == "S1", "qc"]) <= set(cv.QC_SINCA), True)
        meta = rv.leer_json(cv.ruta_meta(self.m.r, "no2"))
        self.assertEqual((meta["conciliacion"]["horas_promediadas_en_el_panel"],
                          meta["conciliacion"]["horas_mixtas_con_bandera"]), (3, 1))
        sn = meta["reconstruccion"]["snifa"]
        self.assertEqual((sn["registros_no_usable_native"], sn["conflicto_de_valor"], sn["conflicto_de_codigo"],
                          sn["fuera_de_unidad"], sn["fuera_de_rango"], sn["horas_promediadas"]), (2, 1, 1, 1, 1, 3))
        self.assertEqual(meta["resumen"]["snifa"]["solo_numeric_usable"], 2)

        # Tablas pequeñas y su JSON lateral.
        lateral = rv.leer_json(self.m.r.salidas_v2 / cv.NOMBRE_LATERAL)
        for nombre in (cv.TABLA_DISTRIBUCION, cv.TABLA_ESTACIONES, cv.TABLA_AUDITORIA):
            ruta = self.m.r.salidas_v2 / nombre
            self.assertEqual(lateral["tablas"][nombre], hashlib.sha256(ruta.read_bytes()).hexdigest())
        self.assertEqual(lateral["huellas_calidad"], {pol: metas[pol]["huella_calidad"] for pol in cv.CONTAMINANTES})
        d = pd.read_csv(self.m.r.salidas_v2 / cv.TABLA_DISTRIBUCION, dtype={"anio": str})
        total = d[(d["contaminante"] == "pm25") & (d["fuente"] == "sinca") & (d["anio"] == "total")].iloc[0]
        self.assertEqual(int(total["filas"]), 79)
        self.assertEqual(int(total["validado"] + total["preliminar"] + total["no_validado"]), 79)
        self.assertNotIn(str(self.m.base), (self.m.r.salidas_v2 / cv.NOMBRE_LATERAL).read_text(encoding="utf-8"))

    def test_lee_la_version_que_registra_el_panel(self):
        self.m.panel("pm25", {"S1": VB, "S2": VC})
        metas, estados = self.ejecutar(escribir=False)
        m = metas["pm25"]
        self.assertEqual(estados["pm25"], "sin_escribir")
        self.assertEqual(m["conciliacion"]["sin_bandera"], 0)
        reg = {x["estacion"]: x for x in m["reconstruccion"]["derivado_sinca"]["estaciones"]}
        self.assertEqual((reg["S1"]["version_sinca"], reg["S1"]["version_panel"], reg["S1"]["version_usada"]),
                         (VA, VB, VB))
        self.assertEqual(m["reconstruccion"]["derivado_sinca"]["version_del_panel_distinta_de_version_sinca"], ["S1"])

    def test_fila_que_no_calza_queda_sin_bandera_y_con_su_motivo(self):
        def alterar(p):
            k = p.index[p["estacion"] == "S1"][0]
            p.loc[k, "obs"] = np.float32(p.loc[k, "obs"] + 0.25)

        self.m.panel("pm25", {"S1": VA, "S2": VC}, alterar=alterar)
        with self.assertRaises(SystemExit):
            self.ejecutar()
        self.assertFalse(self.m.r.raiz_v2.exists())                                    # no se escribió nada
        metas, _ = self.ejecutar(permitir_sin_bandera=True)
        c = metas["pm25"]["conciliacion"]
        self.assertEqual(c["sin_bandera"], 1)
        self.assertEqual(c["sin_bandera_por_motivo"]["obs_distinta"], {"filas": 1, "por_estacion": {"S1": 1}})
        self.assertEqual(int(self.bandera("pm25")["qc"].isna().sum()), 1)
        d = pd.read_csv(self.m.r.salidas_v2 / cv.TABLA_DISTRIBUCION, dtype={"anio": str})
        self.assertEqual(int(d.loc[(d["contaminante"] == "pm25") & (d["anio"] == "total"), "sin_bandera"].sum()), 1)

    def test_no_se_reemplaza_en_silencio(self):
        self.ejecutar()
        archivos = [cv.ruta_calidad(self.m.r, p) for p in cv.CONTAMINANTES] + \
                   [cv.ruta_meta(self.m.r, p) for p in cv.CONTAMINANTES] + list(self.m.r.salidas_v2.iterdir())
        antes = {p: p.stat().st_mtime_ns for p in archivos}
        _, estados = self.ejecutar()
        self.assertEqual(estados, {"pm25": "sin_cambios", "no2": "sin_cambios"})
        self.assertEqual({p: p.stat().st_mtime_ns for p in archivos}, antes)
        # Otro panel (sin una fila): otra huella, que no se acepta sin --reemplazar.
        self.m.panel("pm25", {"S1": VA, "S2": VC}, alterar=lambda p: p.drop(index=p.index[0], inplace=True))
        with self.assertRaises(SystemExit):
            self.ejecutar()
        metas, estados = self.ejecutar(reemplazar=True)
        self.assertEqual(estados, {"pm25": "reemplazado", "no2": "sin_cambios"})
        self.assertEqual([e["evento"] for e in metas["pm25"]["bitacora"]], ["fijado", "reemplazo", "reemplazado"])
        respaldos = sorted((self.m.r.raiz_v2 / "paneles").glob("calidad_pm25_reemplazado_*"))
        self.assertEqual(sorted(p.suffix for p in respaldos), [".json", ".parquet"])
        self.assertEqual(len(self.bandera("pm25")), 78)

    def test_no_escribir_no_crea_nada(self):
        _, estados = self.ejecutar(escribir=False)
        self.assertEqual(estados, {"pm25": "sin_escribir", "no2": "sin_escribir"})
        self.assertFalse(self.m.r.raiz_v2.exists())
        self.assertFalse(self.m.r.salidas_v2.exists())

    def test_rechaza_un_panel_distinto_del_publicado(self):
        self.m.panel("no2", {"S1": VF}, sha_declarado="f" * 64)
        with self.assertRaises(SystemExit):
            self.ejecutar(escribir=False)

    def test_rechaza_un_panel_distinto_del_de_los_pliegues(self):
        self.m.r.raiz_v2.mkdir(parents=True)
        self.m.r.manifiesto_pliegues.write_text(json.dumps(
            {"huella_pliegues": "x", "contaminantes": {"pm25": {"panel": {"sha256": "0" * 64}}}}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.ejecutar(escribir=False)

    def test_sin_derivado_se_detiene(self):
        with self.assertRaises(SystemExit):
            self.ejecutar(escribir=False, raiz_der=self.m.base / "no_existe")

    def test_codigo_qc_inesperado_se_detiene(self):
        self.m.escribir_version("S2", "pm25", VC, [T0 + pd.Timedelta(hours=1)], [3.0], ["sin_dato"])
        with self.assertRaises(SystemExit):
            self.ejecutar(escribir=False)

    def test_derivado_que_no_calza_con_su_manifiesto_se_detiene(self):
        ruta = self.m.derivado / "estacion=S2" / "contaminante=pm25" / f"version={VC}" / "manifest.json"
        mani = json.loads(ruta.read_text(encoding="utf-8"))
        mani["files"][0]["sha256"] = "0" * 64
        ruta.write_text(json.dumps(mani), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.ejecutar(escribir=False)

    def test_cargar_bandera_verifica_la_alineacion(self):
        self.ejecutar()
        q = cv.cargar_bandera("pm25", panel=self.panel_pm25, r=self.m.r)
        self.assertEqual(len(q), len(self.panel_pm25))
        with self.assertRaises(ValueError):
            cv.cargar_bandera("pm25", panel=self.panel_pm25.iloc[::-1].reset_index(drop=True), r=self.m.r)


if __name__ == "__main__":
    unittest.main()
