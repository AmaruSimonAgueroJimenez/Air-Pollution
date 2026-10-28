"""Pruebas de ``derivado_red2_v2`` (R5) y del recorrido derivado → reloj → observaciones, con un árbol SINCA sintético.

El árbol imita la raíz de datos: el maestro sellado, la actualización de las configuradas (con solape) y la ampliación
con su maestro del 2026-10-24 (que no se usa) y el corregido de ``geometria_20261025``. La variante explícita
(``preparar_sinca_modelado_red2.py``) se carga por su propia huella y publica en una carpeta temporal. El original
sellado queda intacto como procedencia. Sin red ni datos reales.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import derivado_red2_v2 as dr  # noqa: E402
import panel_red2_v2 as pr  # noqa: E402
import red_ampliada_v2 as ra  # noqa: E402
import reloj_sinca_v2 as rs  # noqa: E402

CABECERA = ["FECHA (YYMMDD)", "HORA (HHMM)", "Registros validados", "Registros preliminares",
            "Registros no validados", ""]
COLUMNAS_MANIFIESTO = ["region", "estacion", "nombre", "contaminante", "resolucion", "desde", "hasta", "ruta", "bytes",
                       "sha256", "filas", "filas_con_observacion", "primera_observacion", "ultima_observacion"]


def escribir_csv(ruta: Path, inicio: str, horas: int, valor: float) -> int:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    t = pd.Timestamp(inicio) + pd.to_timedelta(np.arange(1, horas + 1), unit="h")
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(CABECERA)
        for k, x in enumerate(t):
            w.writerow([x.strftime("%y%m%d"), x.strftime("%H%M"), f"{valor + (k % 5):.1f}".replace(".", ","), "", "", ""])
    return horas


def fila_manifiesto(ruta: Path, region: str, estacion: str, pol: str, desde: str, hasta: str, filas: int) -> dict:
    datos = ruta.read_bytes()
    return {"region": region, "estacion": estacion, "nombre": estacion, "contaminante": pol, "resolucion": "horario",
            "desde": desde, "hasta": hasta, "ruta": str(ruta), "bytes": len(datos),
            "sha256": hashlib.sha256(datos).hexdigest(), "filas": filas, "filas_con_observacion": filas,
            "primera_observacion": "", "ultima_observacion": ""}


def maestro_csv(ruta: Path, estaciones: dict[str, tuple[str, float, float]]) -> None:
    """Un maestro de coordenadas de R8 (sólo identidad), como los que lee ``red_ampliada_v2.maestro_red2``."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"estacion": e, "nombre": e, "region_sinca": reg, "lat": lat, "lon": lon,
                   "cod_comuna_geografica": 13101, "qc_comuna": "coincide", "usable_geoespacial": True}
                  for e, (reg, lat, lon) in estaciones.items()]).to_csv(ruta, index=False)


def geojson(ruta: Path, estaciones: dict[str, tuple[str, float, float]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
              "properties": {"estacion": e, "region_sinca": reg, "nombre": e, "usable_geoespacial": True,
                             "qc_comuna": "coincide", "cod_comuna_geografica": 13101, "comuna_geografica": "x",
                             "comuna_sinca": "x", "coincide_comuna_sinca": True}}
             for e, (reg, lat, lon) in estaciones.items()]
    ruta.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")


def arbol(base: Path) -> Path:
    """Raíz de datos sintética. X01 (actual, PM2,5): sellado 1–3 ene y actualización 2–5 ene (solape con otro valor).
    N01 (nueva, NO2): corregida en geometria_20261025. N99 (nueva): sin coordenada usable en el maestro corregido."""
    datos = base / "datos"
    s = datos / "sinca"
    a = datos / ra.ACT
    n = datos / ra.AMP
    f1 = s / "pm25" / "horario" / "RM_X01_horario_2023-01-01_2023-01-03.csv"
    f2 = a / "pm25" / "horario" / "RM_X01_horario_2023-01-02_2023-01-05.csv"
    f3 = n / "no2" / "horario" / "RV_N01_horario_2023-01-01_2023-01-04.csv"
    f4 = n / "no2" / "horario" / "RV_N99_horario_2023-01-01_2023-01-04.csv"
    filas = [escribir_csv(f1, "2023-01-01", 72, 10.0), escribir_csv(f2, "2023-01-02", 96, 20.0),
             escribir_csv(f3, "2023-01-01", 96, 30.0), escribir_csv(f4, "2023-01-01", 96, 40.0)]
    pd.DataFrame([fila_manifiesto(f1, "RM", "X01", "pm25", "2023-01-01", "2023-01-03", filas[0])],
                 columns=COLUMNAS_MANIFIESTO).to_csv(s / "manifiesto_descarga.csv", index=False)
    pd.DataFrame([fila_manifiesto(f2, "RM", "X01", "pm25", "2023-01-02", "2023-01-05", filas[1])],
                 columns=COLUMNAS_MANIFIESTO).to_csv(a / "manifiesto_descarga.csv", index=False)
    pd.DataFrame([fila_manifiesto(f3, "RV", "N01", "no2", "2023-01-01", "2023-01-04", filas[2]),
                  fila_manifiesto(f4, "RV", "N99", "no2", "2023-01-01", "2023-01-04", filas[3])],
                 columns=COLUMNAS_MANIFIESTO).to_csv(n / "manifiesto_descarga.csv", index=False)
    geojson(s / "estaciones_georreferenciadas.geojson", {"X01": ("RM", -33.45, -70.66)})
    geojson(a / "estaciones_georreferenciadas.geojson", {"X01": ("RM", -33.45, -70.66)})
    geojson(n / "estaciones_georreferenciadas.geojson", {"N01": ("RV", 0.0, 0.0), "N99": ("RV", 0.0, 0.0)})
    geojson(datos / ra.GEOJSON_NUEVAS, {"N01": ("RV", -32.78, -71.52)})
    maestro_csv(datos / ra.MAESTRO_ACTUALES, {"X01": ("RM", -33.45, -70.66)})       # los maestros de R8
    maestro_csv(datos / ra.MAESTRO_NUEVAS, {"N01": ("RV", -32.78, -71.52)})
    return datos


class DerivadoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.datos = arbol(Path(self.tmp.name))
        self.prep = dr.cargar_preparador()
        self.ins = dr.insumos_red2(self.prep, self.datos)

    def tearDown(self):
        self.tmp.cleanup()

    def test_afg_lib_por_el_sha256_del_archivo(self):
        """T8: rige el sha256 de afg_lib.py (el de la v1); las huellas del árbol de sintaxis, como procedencia."""
        sem = dict(self.prep.load_existing_semantics(dr.RUTA_AFG)[3])
        self.assertEqual(sem["file_sha256"], dr.SHA_AFG)
        reg = dr.verificar_afg(sem)
        self.assertEqual(reg["referencias_ast"]["v1"]["python"], "3.14.3")
        self.assertIn("python", reg["esta_corrida"])
        with self.assertRaises(SystemExit):
            dr.verificar_afg({**sem, "file_sha256": "0" * 64})
        otra_ast = {**sem, "ranking_ast_sha256": "1" * 64}                     # otra versión de Python: no decide
        self.assertEqual(dr.verificar_afg(otra_ast)["file_sha256"], dr.SHA_AFG)

    def test_el_derivado_corre_en_amb_v2(self):
        """T8, «el derivado corre en amb_v2» (cuarta revisión, menor 8): verificar_afg se detiene fuera de amb_v2 o con
        otro Python, y plan.json registra el entorno; quien lee rechaza un manifiesto armado con el Python de la v1 (lo
        prueba test_reloj_sinca_v2.test_series_con_huella_exige_el_preparador_t8)."""
        from unittest import mock
        sem = dict(self.prep.load_existing_semantics(dr.RUTA_AFG)[3])
        self.assertEqual(dr.ENTORNO, {"nombre": "amb_v2", "python": dr.PROCEDENCIA_AST_AFG["amb_v2"]["python"]})
        self.assertEqual(dr.plan(self.ins)["ranking_afg"]["esta_corrida"]["entorno"], "amb_v2")
        with mock.patch("platform.python_version", lambda: "3.14.3"), self.assertRaises(SystemExit) as e:
            dr.verificar_afg(sem)
        self.assertIn("amb_v2", str(e.exception))
        with mock.patch.object(dr.sys, "prefix", "/opt/otro_entorno"), self.assertRaises(SystemExit):
            dr.verificar_afg(sem)

    def test_digest_es_el_del_preparador(self):
        """Cuarta revisión, menor 4: el nombre de cada versión es digest(inputs) del preparador; la réplica de quien lee
        es la misma función."""
        for valor in ({"b": [1, 2.5, None], "a": "ñandú", "c": {"z": True}}, [], {"since": None}):
            self.assertEqual(dr.digest_del_preparador(valor), self.prep.digest(valor))

    def test_t8_igual_en_el_codigo_y_en_la_configuracion(self):
        """Menor 21: SHA_AFG y PROCEDENCIA_AST_AFG del código son los de red_de_monitores.calidad.derivado (en la
        configuración aplicada o en la propuesta), con el preparador y su contrato."""
        cfg = json.loads((V2 / "config_v2.json").read_text(encoding="utf-8"))
        if "red_de_monitores" not in cfg:
            cfg = json.loads((V2 / "propuesta_red_ampliada" / "config_v2.propuesto.json").read_text(encoding="utf-8"))
        d = cfg["red_de_monitores"]["calidad"]["derivado"]
        self.assertEqual((d["sha256"], d["contrato"]), (dr.SHA_PREPARADOR, dr.CONTRATO))
        self.assertEqual(d["programa"], str(dr.RUTA_PREPARADOR.relative_to(dr.REPO)))
        self.assertEqual(d["preparador_original"],
                         {"programa": str(dr.RUTA_PREPARADOR_ORIGINAL.relative_to(dr.REPO)),
                          "sha256": dr.SHA_PREPARADOR_ORIGINAL})
        self.assertEqual(d["politica_espacio"]["reserva_gib_por_omision"], dr.RESERVA_GIB)
        self.assertEqual(d["politica_espacio"]["autoridad"], ra.DECISION_ESPACIO)
        self.assertEqual(d["afg_lib"]["sha256"], dr.SHA_AFG)
        self.assertEqual({k: {"python": v["python"], "ranking_ast_sha256": v["ranking"], "parser_ast_sha256": v["analizador"]}
                          for k, v in d["afg_lib"]["procedencia_ast"].items()}, dr.PROCEDENCIA_AST_AFG)

    def test_preparador_con_su_huella(self):
        import inspect
        self.assertEqual(self.prep.CONTRACT, "airpollution.sinca.modelado.v1.0.0")
        self.assertEqual(dr.RUTA_PREPARADOR.name, "preparar_sinca_modelado_red2.py")
        self.assertEqual(self.prep.sha256(dr.RUTA_PREPARADOR), dr.SHA_PREPARADOR)
        self.assertEqual(self.prep.sha256(dr.RUTA_PREPARADOR_ORIGINAL), dr.SHA_PREPARADOR_ORIGINAL)
        self.assertNotEqual(dr.SHA_PREPARADOR, dr.SHA_PREPARADOR_ORIGINAL)
        self.assertEqual(inspect.signature(dr.ejecutar).parameters["reserva_gib"].default, 1)
        with self.assertRaises(SystemExit):
            dr.cargar_preparador(sha256="0" * 64)
        with self.assertRaises(SystemExit):
            dr.cargar_preparador(dr.RUTA_PREPARADOR_ORIGINAL)

    def test_grupos_y_excluidas(self):
        p = dr.plan(self.ins)
        self.assertEqual(p["series"], 2)
        self.assertEqual(p["por_contaminante"], {"pm25": {"actual": 1}, "no2": {"nueva": 1}})
        self.assertEqual([e["estacion"] for e in p["excluidas"]], ["N99"])
        fam, filas = self.ins["grupos"][("X01", "pm25")]
        self.assertEqual(fam, "actual")
        self.assertEqual(sorted(f["origen_red2"] for f in filas), ["actualizacion", "sellado"])
        self.assertTrue(all(not f["relative_path"].startswith("/") for f in filas))

    def test_solape_lo_resuelve_el_ranking(self):
        fam, filas = self.ins["grupos"][("X01", "pm25")]
        sel, alt, stats = self.prep.consolidate(filas, self.ins[fam])
        s = sel.to_pandas()
        self.assertFalse(s["ts_local"].duplicated().any())
        self.assertEqual(stats["filas_originales_leidas"], 72 + 96)
        # En las horas del solape gana la fuente más reciente (misma calidad): la actualización.
        solape = s[(s["ts_local"] > pd.Timestamp("2023-01-02 00:00")) & (s["ts_local"] <= pd.Timestamp("2023-01-04 00:00"))]
        self.assertTrue(solape["source_path"].str.contains("actualizacion_configuradas").all())
        self.assertEqual(len(alt), 48)

    def test_nueva_con_la_geometria_corregida(self):
        fam, filas = self.ins["grupos"][("N01", "no2")]
        sel, _, _ = self.prep.consolidate(filas, self.ins[fam])
        s = sel.to_pandas()
        self.assertAlmostEqual(float(s["lat"].iloc[0]), -32.78)
        self.assertEqual(s["fuente_geo_sha256"].iloc[0], hashlib.sha256((self.datos / ra.GEOJSON_NUEVAS).read_bytes()).hexdigest())

    def test_no_publica_sin_la_traduccion_confirmada(self):
        import types
        r = types.SimpleNamespace(repo=Path(self.tmp.name))
        salida = Path(self.tmp.name) / "derived" / "modelado" / "SINCA" / "v1_red2"
        for cfg in ({}, {"red_de_monitores": {}}):                       # sin traducir; traducida sin confirmar
            with self.subTest(nodo=bool(cfg)), self.assertRaises(SystemExit):
                dr.ejecutar(self.prep, self.ins, salida, self.datos, r=r, cfg=cfg,
                            estado=lambda repo, rutas: {k: "modificado" for k in rutas})
        self.assertFalse(salida.exists())

    def test_salida_alternativa_rechazada_sin_efectos(self):
        sys.path.insert(0, str(V2 / 'tests'))
        from _sintetico_v2 import raices_temporales
        confirmada = lambda repo, rutas: {k: 'rastreado' for k in rutas}
        alternatives = [Path(self.tmp.name) / 'salida-alternativa', dr.destino_por_omision(self.datos) / 'hija']
        with raices_temporales('v2-destino-canonico-') as r:
            for output in alternatives:
                with self.subTest(salida=output.name), self.assertRaisesRegex(SystemExit, 'raíz registrada'):
                    dr.ejecutar(self.prep, self.ins, output, self.datos, r=r, cfg={'red_de_monitores': {}},
                                estado=confirmada)
                self.assertFalse(output.exists())
            self.assertFalse(dr.destino_por_omision(self.datos).exists())

    def test_inicio_con_exactamente_un_gib_no_escribe_nada(self):
        from types import SimpleNamespace
        from unittest import mock
        sys.path.insert(0, str(V2 / 'tests'))
        from _sintetico_v2 import raices_temporales
        output = dr.destino_por_omision(self.datos)
        confirmada = lambda repo, rutas: {k: 'rastreado' for k in rutas}
        real_check = self.prep.check_disk
        def local_check(salida, reserve_gib, pending_bytes=0, volume_uuid=None):
            # Sólo se aísla el montaje: la aritmética de la política es la real, sobre archivos sintéticos.
            return real_check(salida, reserve_gib, pending_bytes, volume_uuid=None)
        with raices_temporales('v2-sin-presupuesto-inicial-') as r, \
                mock.patch.object(self.prep, 'check_disk', side_effect=local_check) as checked, \
                mock.patch.object(self.prep.shutil, 'disk_usage', return_value=SimpleNamespace(free=self.prep.GIB)), \
                self.assertRaises(self.prep.SafeLimit):
            dr.ejecutar(self.prep, self.ins, output, self.datos, r=r, cfg={'red_de_monitores': {}}, estado=confirmada)
        self.assertGreater(checked.call_args.kwargs['pending_bytes'], dr.OVERHEAD_INICIO_BYTES)
        self.assertFalse(output.exists())
        self.assertFalse(output.parent.exists())

    def test_presupuesto_inicio_serializado_y_frontera_inclusiva(self):
        from types import SimpleNamespace
        from unittest import mock
        plan = {'mensaje': 'reserva técnica: ñ', 'contador': 3}
        archived = Path(self.tmp.name) / 'plan-sintetico.json'
        self.prep.json_atomic(archived, plan)
        pending = dr.presupuesto_inicio_corrida(plan)
        self.assertEqual(pending, archived.stat().st_size + dr.OVERHEAD_INICIO_BYTES)
        large = {'mensaje': 'ñ' * 2**20}
        exact = len((json.dumps(large, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8'))
        self.assertEqual(dr.presupuesto_inicio_corrida(large), exact + dr.OVERHEAD_INICIO_BYTES)
        output = dr.destino_por_omision(self.datos)
        required = self.prep.GIB + pending
        for free in (required - 1, required):
            with self.subTest(libre=free), mock.patch.object(self.prep.shutil, 'disk_usage',
                                                          return_value=SimpleNamespace(free=free)):
                if free < required:
                    with self.assertRaises(self.prep.SafeLimit):
                        self.prep.check_disk(output, pending_bytes=pending, volume_uuid=None)
                else:
                    self.assertEqual(self.prep.check_disk(output, pending_bytes=pending, volume_uuid=None), free)
        self.assertFalse(output.exists())

    def test_el_plan_registra_su_codigo_y_su_procedencia(self):
        """Quinta revisión, mayor 1: plan.json de cada corrida registra la huella de derivado_red2_v2.py (que reemplaza la
        geometría de load_inputs) y la procedencia de la corrida (commit, código, bibliotecas, hilos y traducción)."""
        from unittest import mock
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import raices_temporales
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        salida = Path(self.tmp.name) / "derived" / "modelado" / "SINCA" / "v1_red2"
        # el preparador sólo publica en el disco externo (check_disk): aquí se simula la publicación de cada serie
        def publicar(filas, ins, s, reserve_gib, code_bytes):
            self.assertEqual(reserve_gib, 1)
            self.assertEqual(hashlib.sha256(code_bytes).hexdigest(), dr.SHA_PREPARADOR)
            return {"status": "published", "path": "x"}
        with raices_temporales("v2-derivado-") as r, \
                mock.patch.object(self.prep, "check_disk", return_value=66*self.prep.GIB) as checked, \
                mock.patch.object(self.prep, "process_series", publicar):
            res = dr.ejecutar(self.prep, self.ins, salida, self.datos, r=r, cfg={"red_de_monitores": {}},
                              estado=confirmada)
        plan = json.loads((salida / "_runs" / res["corrida"] / "plan.json").read_text(encoding="utf-8"))
        propio = hashlib.sha256(Path(dr.__file__).read_bytes()).hexdigest()
        self.assertEqual((plan["codigo"]["programa"], plan["codigo"]["sha256"]),
                         ("scripts_modelo_1km/v2/derivado_red2_v2.py", propio))
        self.assertEqual(plan["traza"]["codigo_red2"]["scripts_modelo_1km/v2/derivado_red2_v2.py"], propio)
        for clave in ("git", "codigo", "bibliotecas", "python", "hilos", "traduccion"):
            self.assertIn(clave, plan["traza"])
        self.assertEqual(plan["traza"]["insumos"]["afg_lib"]["sha256"], dr.SHA_AFG)
        self.assertEqual(plan["ranking_afg"]["esta_corrida"]["entorno"], "amb_v2")              # T8
        self.assertEqual(plan["codigo"]["preparador_sha256"], dr.SHA_PREPARADOR)
        self.assertEqual(plan["codigo"]["preparador_original"]["sha256"], dr.SHA_PREPARADOR_ORIGINAL)
        self.assertEqual(plan["codigo"]["politica_espacio"]["reserva_gib_por_omision"], 1)
        self.assertEqual(plan["codigo"]["politica_espacio"]["autoridad"], ra.DECISION_ESPACIO)
        self.assertEqual(plan["codigo"]["politica_espacio"]["overhead_inicio_bytes"], dr.OVERHEAD_INICIO_BYTES)
        self.assertEqual(checked.call_args.kwargs["pending_bytes"],
                         (salida / "_runs" / res["corrida"] / "plan.json").stat().st_size + dr.OVERHEAD_INICIO_BYTES)
        self.assertEqual(json.loads((salida / "_runs" / res["corrida"] / "progreso.json").read_text(
            encoding="utf-8"))["status"], dr.ESTADO_COMPLETO)

    def test_el_derivado_completo_con_el_preparador(self):
        """Ronda 3 de la traducción, mayor, con el preparador sellado de verdad: el derivado que publica ``ejecutar``
        (en ``destino_por_omision``, con su ``plan.json``) pasa ``exigir_derivado_completo``; una versión de X01
        publicada por el mismo preparador con ``until`` o sólo con su archivo sellado (sin la actualización), con su
        corrida terminada y el mismo ``plan.json``, no pasa: se detiene mostrando la diferencia con la lista cerrada."""
        import shutil
        from unittest import mock
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import raices_temporales
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        salida = dr.destino_por_omision(self.datos)
        sin_disco = mock.patch.object(self.prep, "check_disk", lambda *a, **k: None)
        with raices_temporales("v2-derivado-completo-") as r, sin_disco:
            res = dr.ejecutar(self.prep, self.ins, salida, self.datos, r=r, cfg={"red_de_monitores": {}},
                              estado=confirmada)
        series = rs.series_del_derivado([salida], dr.CONTAMINANTES)
        d = dr.exigir_derivado_completo([salida], series, self.datos, "prueba")
        self.assertEqual((d["corrida"], d["series"], d["fuentes"]["archivos"]), (res["corrida"], 2, 3))
        # ronda 4, menor 7: las filas publicadas son las de la lista cerrada (X01: 72 + 96; N01: 96), y el preparador
        # declara files con filas y esquema que calzan con los metadatos de sus parquet
        self.assertEqual(d["fuentes"]["filas"], 72 + 96 + 96)
        registro, _ = rs.series_con_huella([salida], self.datos, dr.CONTAMINANTES)
        self.assertEqual(len(registro["series"]), 2)
        self.assertEqual(d["plan"]["sha256"], hashlib.sha256(Path(dr.__file__).read_bytes()).hexdigest())
        self.filas_movidas_a_solapamientos(salida)
        plan = (salida / "_runs" / res["corrida"] / "plan.json").read_bytes()
        prog = json.loads((salida / "_runs" / res["corrida"] / "progreso.json").read_text(encoding="utf-8"))
        fam, filas = self.ins["grupos"][("X01", "pm25")]
        casos = (("until", filas, "2023-01-02", "inputs.until = '2023-01-02'"),
                 ("sin la actualización", [f for f in filas if f["origen_red2"] == "sellado"], None, "faltan 1"))
        for k, (nombre, fuentes, until, mensaje) in enumerate(casos, 1):
            with self.subTest(nombre):
                for v in (salida / "estacion=X01" / "contaminante=pm25").glob("version=*"):
                    shutil.rmtree(v)
                with sin_disco:
                    x = self.prep.process_series(fuentes, self.ins[fam], salida, until=until, reserve_gib=dr.RESERVA_GIB,
                                                 volume_uuid=None, code_bytes=dr.RUTA_PREPARADOR.read_bytes())
                corrida = salida / "_runs" / f"2099010{k}T000000Z-red2"
                corrida.mkdir()
                (corrida / "plan.json").write_bytes(plan)
                (corrida / "progreso.json").write_text(json.dumps({"status": dr.ESTADO_COMPLETO, "results": [
                    y for y in prog["results"] if "estacion=X01" not in y["path"]] + [x]}))
                series = rs.series_del_derivado([salida], dr.CONTAMINANTES)
                with self.assertRaises(SystemExit) as e:
                    dr.exigir_derivado_completo([salida], series, self.datos, "prueba")
                self.assertIn("X01:pm25", str(e.exception))
                self.assertIn(mensaje, str(e.exception))
                self.assertNotIn("N01:no2", str(e.exception))

    def filas_movidas_a_solapamientos(self, salida: Path) -> None:
        """Ronda 5 de la traducción, menor 2 (el caso B del revisor), con el preparador sellado de verdad: en la versión
        completa de X01 (observaciones 120, solapamientos 48) se pasan 30 filas de ``observaciones.parquet`` a
        ``solapamientos.parquet`` (120 → 90 y 48 → 78: el total no cambia) y se pone ``files`` al día. El propio
        ``validate_publication`` del preparador, que compara sólo el total, la acepta, y el ``statistics`` que escribió
        dice todavía 120 y 48: ``exigir_derivado_completo`` se detiene por los conteos de cada archivo. Con
        ``statistics`` también al día (queda fuera de ``digest(inputs)``), lo detiene el ranking (etiquetas de
        solapamientos.parquet que no están en observaciones.parquet)."""
        import pyarrow as pa
        import pyarrow.parquet as pq
        series = rs.series_del_derivado([salida], dr.CONTAMINANTES)
        (x01,) = [s for s in series if s["estacion"] == "X01"]
        c = Path(x01["ruta"]).parent
        m = json.loads((c / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((m["statistics"]["filas_seleccionadas"], m["statistics"]["filas_alternativas_conservadas"]),
                         (120, 48))
        obs, sol = pq.read_table(c / "observaciones.parquet"), pq.read_table(c / "solapamientos.parquet")
        n = 30
        movidas = obs.slice(obs.num_rows - n, n)
        movidas = movidas.set_column(movidas.schema.get_field_index("seleccionada"), "seleccionada",
                                     pa.array([False] * n))
        for q in (c / "observaciones.parquet", c / "solapamientos.parquet"):
            os.chmod(q, 0o644)
        pq.write_table(obs.slice(0, obs.num_rows - n), c / "observaciones.parquet", compression="zstd")
        pq.write_table(pa.concat_tables([sol, movidas]), c / "solapamientos.parquet", compression="zstd")
        for f in m["files"]:
            q = c / f["name"]
            f.update({"sha256": hashlib.sha256(q.read_bytes()).hexdigest(), "bytes": q.stat().st_size,
                      "rows": pq.read_metadata(q).num_rows,
                      "schema_sha256": hashlib.sha256(pq.read_schema(q).serialize().to_pybytes()).hexdigest()})
        os.chmod(c / "manifest.json", 0o644)
        (c / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        self.assertEqual([f["rows"] for f in m["files"]], [90, 78])
        self.prep.validate_publication(c, m["version"])                      # el preparador sólo compara el total
        for nombre, mensaje in (("statistics del completo", "statistics.filas_seleccionadas declara 120"),
                                ("statistics al día", "con etiquetas que no están en observaciones.parquet")):
            if nombre == "statistics al día":
                m["statistics"].update(filas_seleccionadas=90, filas_alternativas_conservadas=78)
                (c / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
            series = rs.series_del_derivado([salida], dr.CONTAMINANTES)
            with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                dr.exigir_derivado_completo([salida], series, self.datos, "prueba")
            self.assertIn("X01:pm25", str(e.exception))
            self.assertIn(mensaje, str(e.exception))
            self.assertNotIn("N01:no2", str(e.exception))

    def test_otro_hasta_con_el_preparador(self):
        """Ronda 4, menor 8, con el preparador sellado de verdad: la fila sellada de X01 con otro «hasta» (2023-01-09;
        el archivo dice 2023-01-03), la misma ruta y el mismo sha256, publica una versión y una corrida nuevas, con su
        plan.json; el preparador toma el «hasta» de la fila y el ranking desempata por él, así que en las horas del
        solape la fila seleccionada pasa de la actualización al sellado (contra R4 y R5). ``exigir_derivado_completo``,
        el reloj que escribe y el panel se detienen mostrando el campo distinto, sin escribir nada."""
        import copy
        import os
        from types import SimpleNamespace
        from unittest import mock
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import raices_temporales
        confirmada = lambda repo, rutas: {k: "rastreado" for k in rutas}      # noqa: E731
        cfg = {"red_de_monitores": {}}
        with raices_temporales("v2-derivado-hasta-") as r, mock.patch.object(ra, "LISTA_CERRADA", {}), \
                mock.patch.object(self.prep, "check_disk", lambda *a, **k: None):
            datos = arbol(r.datos.parent)                                     # la raíz de datos de r
            self.assertEqual(datos.resolve(), Path(r.datos).resolve())
            alterado = copy.deepcopy(dr.insumos_red2(self.prep, datos))
            for f in alterado["grupos"][("X01", "pm25")][1]:
                if f["origen_red2"] == "sellado":
                    self.assertEqual(f["hasta"], "2023-01-03")
                    f["hasta"] = "2023-01-09"
            salida = dr.destino_por_omision(datos)
            dr.ejecutar(self.prep, alterado, salida, datos, r=r, cfg=cfg, estado=confirmada)
            series = rs.series_del_derivado([salida], dr.CONTAMINANTES)
            (x01,) = [s for s in series if s["estacion"] == "X01"]
            sel = pd.read_parquet(x01["ruta"], columns=["ts_local", "source_path"])     # sólo la procedencia
            solape = sel[(sel["ts_local"] > pd.Timestamp("2023-01-02 00:00")) &
                         (sel["ts_local"] <= pd.Timestamp("2023-01-04 00:00"))]
            self.assertEqual(len(solape), 48)
            self.assertTrue(solape["source_path"].str.startswith("sinca/").all())       # gana el sellado
            mensaje = "hasta: '2023-01-03' en la lista cerrada, '2023-01-09' en el derivado"
            with self.assertRaises(SystemExit) as e:
                dr.exigir_derivado_completo([salida], series, datos, "prueba")
            self.assertIn(mensaje, str(e.exception))
            self.assertIn("X01:pm25", str(e.exception))
            self.assertNotIn("N01:no2", str(e.exception))
            with self.assertRaises(SystemExit) as e:                              # el reloj que escribe
                rs.ejecutar_reloj(r, [salida], cfg=cfg, estado=confirmada)
            self.assertIn(mensaje, str(e.exception))
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
            tesela = datos / "contaminantes" / pr.CATALOGO_MAIAC / "tile=h11v10" / "pixeles.parquet"
            tesela.parent.mkdir(parents=True)
            tesela.write_bytes(b"tile")
            vieja = (pr.utc(pr.CORTE_INSUMOS_UTC) - pd.Timedelta(days=50)).timestamp()
            os.utime(tesela, (vieja, vieja))
            pr.registrar_catalogo_maiac(r, datos, cfg=cfg, estado=confirmada)
            inv = pd.DataFrame({"fuente_registro": ["registro_catalogo_maiac (T5): fecha del archivo"]})
            args = SimpleNamespace(derivado=[salida], contraste=r.raiz_v2 / "unidades_red2" / "x.csv",
                                   contraste_sha256="0" * 64, veredictos=r.raiz_v2 / rs.NOMBRE_SALIDA / "v.parquet",
                                   convencion_civil=None)
            with self.assertRaises(SystemExit) as e:                              # el panel
                pr.ejecutar(r, inv, args, cfg=cfg, estado=confirmada)
            self.assertIn(mensaje, str(e.exception))
            self.assertEqual(sorted(q.name for q in (r.raiz_v2 / "insumos_red2").iterdir()), [pr.NOMBRE_REGISTRO_MAIAC])
            self.assertFalse((r.raiz_v2 / "paneles").exists())

    def test_destino(self):
        v1 = dr.raiz_derivados(self.datos).joinpath(*dr.SUBRUTA_V1)
        for malo in (v1, v1 / "red2", self.datos / "x", v1.parent):
            with self.subTest(destino=str(malo)):
                with self.assertRaises(SystemExit):
                    dr.verificar_destino(malo, self.datos)
        self.assertEqual(dr.verificar_destino(dr.destino_por_omision(self.datos), self.datos).name, "v1_red2")

    def test_de_punta_a_punta(self):
        """Derivado publicado (temporal) → reloj → observaciones del panel, con la regla única de inclusión."""
        salida = Path(self.tmp.name) / "derived" / "modelado" / "SINCA" / "v1_red2"
        codigo = dr.RUTA_PREPARADOR.read_bytes()
        for (e, p), (fam, filas) in sorted(self.ins["grupos"].items()):
            res = self.prep.process_series(filas, self.ins[fam], salida, reserve_gib=dr.RESERVA_GIB, volume_uuid=None,
                                           code_bytes=codigo)
            self.assertEqual(res["status"], "published")
            self.assertIsNone(self.prep.validate_publication(Path(res["path"]))["inputs"].get("since"))
        series = rs.series_del_derivado([salida], ("pm25", "no2"))
        self.assertEqual(sorted((s["estacion"], s["contaminante"]) for s in series), [("N01", "no2"), ("X01", "pm25")])
        # T8 en quien lee: los manifiestos del preparador sellado pasan; sin la corrida de derivado_red2_v2 (process_series
        # llamado directo), el derivado no se da por completo.
        import platform
        registro, _ = rs.series_con_huella([salida], self.datos, ("pm25", "no2"))
        self.assertEqual({s["procedencia_afg"]["python"] for s in registro["series"]}, {platform.python_version()})
        with self.assertRaises(SystemExit):
            dr.exigir_derivado_completo([salida], series, self.datos, "prueba")
        tabla, _ = rs.verificar_red(series, {"X01": "RM", "N01": "RV"}, rs.leer_politica(), (2023, 2023))
        self.assertTrue(tabla.empty)                         # menos de 720 etiquetas: regla general
        obs = []
        for s in series:
            df = pd.read_parquet(s["ruta"], columns=["ts_local", "obs", "qc_observacion", "seleccionada"])
            factor = 1.0 if s["contaminante"] == "pm25" else 24.4654 / 46.0055
            obs.append(pr.procesar_serie_sinca(df, s["estacion"], s["contaminante"], factor, {}, "America/Santiago",
                                               "v"))
        x = obs[1] if obs[1]["estacion"].iloc[0] == "X01" else obs[0]
        self.assertEqual(len(x), 72 + 96 - 48)
        self.assertEqual(x["ts_utc"].min(), pd.Timestamp("2023-01-01 04:00"))   # etiqueta 01:00 → inicio 04:00 UTC
        # El mismo recorrido que usa el armado (panel_red2_v2.ejecutar), con SNIFA y la regla única de inclusión.
        snifa = Path(self.tmp.name) / "snifa.parquet"
        pd.DataFrame({"station_id": ["el_penon"], "pollutant": "no2", "numeric_usable": True, "usable_native": True,
                      "date_local": pd.to_datetime("2023-01-02"), "hour_index": [5], "value": [10.0],
                      "unit": ["ug/m3N"], "document_id": "d", "value_conflict": False,
                      "quality_conflict": False}).to_parquet(snifa)
        con_celda = pd.DataFrame({"estacion": ["X01", "N01", "SNIFA-ELPENON"], "celda": [1, 2, 3],
                                  "lat": [-33.45, -32.78, -24.0], "lon": [-70.66, -71.52, -70.0]})
        factor = {("X01", "pm25"): 1.0, ("N01", "no2"): 24.4654 / 46.0055}
        region = {"X01": "RM", "N01": "RV", "SNIFA-ELPENON": "RII"}
        evaluadas = {(s["estacion"], s["contaminante"]) for s in series}       # las que registró el reloj
        huellas = rs.huellas_de(registro)                                      # el sha256 de cada serie registrada
        o, info, esp = pr.observaciones_desde_derivado("pm25", series, factor, {}, region, rs.leer_politica(), snifa,
                                                       con_celda, evaluadas=evaluadas, con_fila=set(), huellas=huellas)
        self.assertEqual(len(o), 72 + 96 - 48)
        self.assertEqual(info["series_que_entran"], 1)
        self.assertTrue(esp.empty)
        o, info, _ = pr.observaciones_desde_derivado("no2", series, factor, {}, region, rs.leer_politica(), snifa,
                                                     con_celda, evaluadas=evaluadas, con_fila=set(), huellas=huellas)
        self.assertEqual(sorted(o["estacion"].unique()), ["N01", "SNIFA-ELPENON"])
        self.assertAlmostEqual(float(o.loc[o["estacion"] == "SNIFA-ELPENON", "obs"].iloc[0]), 10.0 * 0.531793, places=5)
        o, info, _ = pr.observaciones_desde_derivado("no2", series, {}, {}, region, rs.leer_politica(), snifa,
                                                     con_celda, evaluadas=evaluadas, con_fila=set(), huellas=huellas)
        self.assertEqual(sorted(o["estacion"].unique()), ["SNIFA-ELPENON"])      # sin unidad que entra, la serie sale


if __name__ == "__main__":
    unittest.main()
