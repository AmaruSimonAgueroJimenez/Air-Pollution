"""Pruebas pequeñas, sin datos reales, DMC, ejecutores ni entrenamiento.

Se ejecutan con amb_v2, python -B y hilos=1. Las fuentes reutilizadas se
comprueban por SHA256. De ambiental se cargan sólo definiciones puras por AST:
no se importa el paquete (su __init__ cambia hilos) ni fijados/reloj_dmc.
Esto no es una prueba de la cadena de producción ni de la compuerta M6.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import socket
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType, ModuleType
from unittest.mock import patch

import numpy as np
import pandas as pd


CARPETA = Path(__file__).resolve().parent
V2 = CARPETA.parent
PAQUETE = V2.parent / "meteo_combinada"
SHA_FUENTES = {
    "tipos.py": "31fc3a1ad00ccdc5219ee44796e77be44e0cc3f813901a03b69d6bf964743dab",
    "ambiental.py": "1e6cd4f8547d89516a514199e1cdc966c1120ef6b436b3cdf54c64c4f802fa1e",
    "meteorologia_v2.py": "f61559eab281846a4935eb1ea66217e039ff37a727833bf8fcaa7a774b776754",
}


def _fuente(ruta):
    contenido = ruta.read_bytes()
    if hashlib.sha256(contenido).hexdigest() != SHA_FUENTES[ruta.name]:
        raise AssertionError(f"fuente distinta de AP b979586: {ruta.name}; revisar, no actualizar automáticamente")
    return contenido


def _cargar(ruta, nombre):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = modulo
    # Compilar los mismos bytes verificados; el cargador no escribe .pyc.
    contenido = _fuente(ruta) if ruta.name in SHA_FUENTES else ruta.read_bytes()
    exec(compile(contenido, str(ruta), "exec"), modulo.__dict__)
    return modulo


def _ambiental_sin_importar(tipos):
    nombres = {"SUFIJOS", "COLUMNAS_MC", "COLUMNAS_FE", "COLUMNAS_R", "COLUMNAS_VARIANTE", "ESQUEMA_DE",
               "UNIDADES", "CLAVE_TRAS_ULTIMA", "METADATOS_LATERAL", "_NAN32", "ErrorAmbiental",
               "_json_canonico", "_nan_canonico", "_variante_de_tabla", "huella_contenido"}
    arbol = ast.parse(_fuente(PAQUETE / "ambiental.py"))
    elegidos, encontrados = [], set()
    for nodo in arbol.body:
        ids = {nodo.name} if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)) else set()
        if isinstance(nodo, ast.Assign):
            ids = {t.id for t in nodo.targets if isinstance(t, ast.Name)}
        elif isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            ids = {nodo.target.id}
        if (isinstance(nodo, ast.ImportFrom) and nodo.module == "__future__") or ids & nombres:
            elegidos.append(nodo)
            encontrados |= ids & nombres
    if encontrados != nombres:
        raise AssertionError("cambió la interfaz pura de ambiental")
    modulo = ModuleType("ambiental_puro_de_la_fuente_fijada")
    modulo.__dict__.update(tipos=tipos, Variante=tipos.Variante, Mapping=Mapping, MappingProxyType=MappingProxyType,
                           np=np, pd=pd, hashlib=hashlib, json=json)
    exec(compile(ast.Module(body=elegidos, type_ignores=[]), "ambiental.py (selección AST)", "exec"), modulo.__dict__)
    return modulo


TIPOS = _cargar(PAQUETE / "tipos.py", "tipos_puros_propuesta")
AMBIENTAL = _ambiental_sin_importar(TIPOS)
ADAPTADOR = _cargar(V2 / "meteorologia_v2.py", "adaptador_fijado_propuesta")
UNION = _cargar(CARPETA / "union_lateral.py", "union_lateral_propuesta")
ULTIMA = pd.Timestamp("2001-01-01T01:00:00Z")


def _metadatos(lateral, variante, tras=0):
    # Huellas exclusivamente de fixtures; no son identidades de archivos reales.
    huellas = {k: hashlib.sha256(f"fixture-sintetico-no-produccion:{k}".encode()).hexdigest()
               for k in UNION.HUELLAS}
    huellas["content_sha256"] = AMBIENTAL.huella_contenido(lateral)
    meta = {"model_ready": True, "source_policy_verified": True, "variante": variante,
            "columnas": list(AMBIENTAL.COLUMNAS_VARIANTE[variante]),
            "unidades": dict(AMBIENTAL.UNIDADES[variante]), **huellas, "claves_tras_ultima_hora": tras}
    return {k: meta[k] for k in AMBIENTAL.METADATOS_LATERAL}, dict(huellas)


def _fixture(variante="I"):
    panel = pd.DataFrame({"estacion": pd.Categorical(["B", "A", "A"]),
                          "ts_utc": pd.to_datetime(["2001-01-01T01:00", "2001-01-01T00:00", "2001-01-01T01:00"]),
                          "obs": [10.0, np.nan, 0.0], "qc": pd.Categorical(["V", "P", None]),
                          "peso": np.array([0.2, 0.3, 0.5], dtype="float64"),
                          "el_tp_1h_mm": np.array([0, np.nan, 2], dtype="float32"),
                          "pliegue_fixture": ["prueba", "ajuste", "ajuste"]},
                         index=pd.Index([9, 3, 9], name="fila_original"))
    lateral = pd.DataFrame({"estacion": pd.array(["A", "A", "B"], dtype="string"),
                            "ts_utc": pd.to_datetime(["2001-01-01T00:00Z", "2001-01-01T01:00Z",
                                                       "2001-01-01T01:00Z"], utc=True)})
    for j, c in enumerate(AMBIENTAL.COLUMNAS_VARIANTE[variante]):
        lateral[c] = np.array([1.25 + j, np.nan if j == 0 else 2.5 + j, 3.75 + j], dtype="float32")
    return panel, lateral


class PruebasUnionLateral(unittest.TestCase):
    def unir(self, panel, lateral, variante="I", *, meta=None, esperadas=None, ultima=ULTIMA, confirmado=True):
        if meta is None:
            meta, defecto = _metadatos(lateral, variante)
            esperadas = defecto if esperadas is None else esperadas
        return UNION.unir_lateral_validada(panel, lateral, meta, variante=variante,
                                           identidades_esperadas=esperadas, ultima_hora_utc=ultima,
                                           ambiental=AMBIENTAL, adaptador=ADAPTADOR,
                                           panel_ingenuo_es_utc=confirmado)

    def test_union_correcta_ambas_variantes_y_panel_intacto(self):
        for variante in ("I", "D"):
            with self.subTest(variante=variante):
                panel, lateral = _fixture(variante)
                panel.attrs["nota"] = "fixture"
                antes, lateral_antes = panel.copy(deep=True), lateral.copy(deep=True)
                resultado, identidad = self.unir(panel, lateral, variante)
                pd.testing.assert_frame_equal(resultado[list(panel.columns)], antes)
                pd.testing.assert_frame_equal(panel, antes)
                pd.testing.assert_frame_equal(lateral, lateral_antes)
                self.assertEqual(resultado.attrs, antes.attrs)
                self.assertTrue(resultado.index.identical(panel.index))
                nuevas = list(AMBIENTAL.COLUMNAS_VARIANTE[variante])
                pd.testing.assert_frame_equal(resultado[nuevas].reset_index(drop=True),
                                              lateral[nuevas].iloc[[2, 0, 1]].reset_index(drop=True))
                self.assertEqual(identidad["panel_rows"], 3)
                self.assertEqual(identidad["sidecar_rows"], 3)
                self.assertEqual(identidad["columns"], nuevas)
                meta, _ = _metadatos(lateral, variante)
                self.assertNotEqual(identidad["content_sha256"], meta["content_sha256"])

    def test_lateral_desordenada_alinea_por_claves_no_posicion(self):
        for variante in ("I", "D"):
            panel, lateral = _fixture(variante)
            a, _ = self.unir(panel, lateral, variante)
            b, _ = self.unir(panel, lateral.iloc[[2, 1, 0]], variante)
            pd.testing.assert_frame_equal(a, b)

    def test_orden_con_huella_anterior_se_rechaza(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral, "I")
        with self.assertRaisesRegex(ValueError, "content_sha256"):
            self.unir(panel, lateral.iloc[::-1], meta=meta, esperadas=esperadas)

    def test_claves_duplicadas_en_cualquiera_de_las_tablas(self):
        panel, lateral = _fixture()
        for p, l in ((pd.concat([panel, panel.iloc[:1]]), lateral),
                     (panel, pd.concat([lateral, lateral.iloc[:1]]))):
            with self.subTest(panel=len(p), lateral=len(l)), self.assertRaisesRegex(ValueError, "duplicadas"):
                self.unir(p, l)

    def test_fila_faltante_no_autorizada(self):
        panel, lateral = _fixture()
        with self.assertRaisesRegex(ValueError, "claves faltantes"):
            self.unir(panel, lateral.iloc[1:])

    def test_fila_extra_no_se_ignora(self):
        panel, lateral = _fixture()
        extra = lateral.iloc[:1].copy()
        extra["estacion"] = pd.array(["NO_ES_DEL_PANEL"], dtype="string")
        with self.assertRaisesRegex(ValueError, "claves extra"):
            self.unir(panel, pd.concat([lateral, extra], ignore_index=True))

    def test_ausencias_solo_despues_de_fon1_y_con_conteo_exacto(self):
        panel, lateral = _fixture()
        lateral = lateral.iloc[:1]
        meta, esperadas = _metadatos(lateral, "I", tras=2)
        salida, _ = self.unir(panel, lateral, meta=meta, esperadas=esperadas,
                              ultima=pd.Timestamp("2001-01-01T00:00Z"))
        self.assertTrue(salida.iloc[[0, 2]][list(AMBIENTAL.COLUMNAS_VARIANTE["I"])].isna().all().all())
        pd.testing.assert_frame_equal(salida[list(panel.columns)], panel)
        for tras in (1, True):
            meta["claves_tras_ultima_hora"] = tras
            with self.assertRaisesRegex(ValueError, "claves_tras_ultima_hora"):
                self.unir(panel, lateral, meta=meta, esperadas=esperadas,
                          ultima=pd.Timestamp("2001-01-01T00:00Z"))

    def test_no_se_autoriza_hueco_anterior_con_un_conteo(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral.iloc[1:], "I", tras=1)
        with self.assertRaisesRegex(ValueError, "claves faltantes"):
            self.unir(panel, lateral.iloc[1:], meta=meta, esperadas=esperadas)

    def test_variante_solicitada_distinta_se_rechaza(self):
        panel, lateral = _fixture("D")
        meta, esperadas = _metadatos(lateral, "D")
        with self.assertRaisesRegex(ValueError, "variante"):
            self.unir(panel, lateral, "I", meta=meta, esperadas=esperadas)

    def test_cada_identidad_incorrecta_se_rechaza(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral, "I")
        for clave in UNION.HUELLAS:
            with self.subTest(clave=clave), self.assertRaisesRegex(ValueError, clave):
                self.unir(panel, lateral, meta={**meta, clave: "0" * 64}, esperadas=esperadas)

    def test_contenido_modificado_sin_rehacer_huella_se_rechaza(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral, "I")
        lateral.loc[0, "mc_t2m"] += np.float32(1)
        with self.assertRaisesRegex(ValueError, "content_sha256"):
            self.unir(panel, lateral, meta=meta, esperadas=esperadas)

    def test_metadatos_flags_unidades_y_campo_extra_se_rechazan(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral, "I")
        for cambio in ({"model_ready": False}, {"source_policy_verified": False},
                       {"unidades": {}}, {"campo_no_contratado": True}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.unir(panel, lateral, meta={**meta, **cambio}, esperadas=esperadas)

    def test_identidad_esperada_incompleta_o_no_sha_se_rechaza(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral, "I")
        for malas in ({}, {**esperadas, "panel_sha256": "no-es-una-huella"}):
            with self.assertRaises(ValueError):
                self.unir(panel, lateral, meta=meta, esperadas=malas)

    def test_panel_ingenuo_necesita_confirmacion_utc(self):
        panel, lateral = _fixture()
        with self.assertRaisesRegex(ValueError, "procedencia UTC"):
            self.unir(panel, lateral, confirmado=False)

    def test_panel_con_otra_zona_conserva_su_representacion(self):
        panel, lateral = _fixture()
        panel["ts_utc"] = panel["ts_utc"].dt.tz_localize("UTC").dt.tz_convert("Etc/GMT+4")
        resultado, _ = self.unir(panel, lateral, confirmado=False)
        pd.testing.assert_frame_equal(resultado[list(panel.columns)], panel)
        self.assertEqual(resultado["mc_t2m"].iloc[0], np.float32(3.75))

    def test_horas_no_exactas_y_limite_sin_zona_se_rechazan(self):
        panel, lateral = _fixture()
        with self.assertRaisesRegex(ValueError, "Timestamp con zona"):
            self.unir(panel, lateral, ultima=ULTIMA.tz_localize(None))
        panel.loc[3, "ts_utc"] += pd.Timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, "HH:00"):
            self.unir(panel, lateral)

    def test_nulos_en_claves_y_columnas_solapadas_se_rechazan(self):
        panel, lateral = _fixture()
        panel.loc[3, "estacion"] = None
        with self.assertRaisesRegex(ValueError, "claves nulas"):
            self.unir(panel, lateral)
        panel, lateral = _fixture()
        panel["mc_t2m"] = 0
        with self.assertRaisesRegex(ValueError, "solapadas"):
            self.unir(panel, lateral)

    def test_no_lee_blanco_calidad_ni_particion_para_calcular_covariables(self):
        panel, lateral = _fixture()
        original, _ = self.unir(panel, lateral)
        panel["obs"] = [99999, -88888, 77777]
        panel["qc"] = "alterada"
        panel["pliegue_fixture"] = "estacion_excluida"
        cambiado, _ = self.unir(panel, lateral)
        nuevas = list(AMBIENTAL.COLUMNAS_VARIANTE["I"])
        pd.testing.assert_frame_equal(original[nuevas], cambiado[nuevas])
        pd.testing.assert_frame_equal(cambiado[list(panel.columns)], panel)
        # La lateral tampoco puede traer el blanco ni etiquetas de pliegue como predictores.
        meta, esperadas = _metadatos(lateral, "I")
        for extra in ("obs", "pliegue"):
            with self.assertRaises((ValueError, AMBIENTAL.ErrorAmbiental)):
                self.unir(panel, lateral.assign(**{extra: 0}), meta=meta, esperadas=esperadas)

    def test_union_en_memoria_sin_archivos_red_ni_dmc(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral, "I")
        with patch("builtins.open", side_effect=AssertionError("acceso a archivos")), \
                patch.object(io, "open", side_effect=AssertionError("acceso a archivos")), \
                patch.object(socket, "socket", side_effect=AssertionError("acceso a red")), \
                patch.dict(sys.modules, {"reloj_dmc": None, "meteo_combinada": None}):
            self.unir(panel, lateral, meta=meta, esperadas=esperadas)

    def test_fila_presente_con_nan_no_se_rellena_ni_se_descarta(self):
        panel, lateral = _fixture()
        lateral.loc[0, list(AMBIENTAL.COLUMNAS_VARIANTE["I"])] = np.float32(np.nan)
        resultado, _ = self.unir(panel, lateral)
        self.assertTrue(resultado.iloc[1][list(AMBIENTAL.COLUMNAS_VARIANTE["I"])].isna().all())
        pd.testing.assert_frame_equal(resultado[list(panel.columns)], panel)

    def test_nulo_en_clave_lateral_se_rechaza_antes_de_hashear(self):
        panel, lateral = _fixture()
        meta, esperadas = _metadatos(lateral, "I")
        lateral.loc[0, "estacion"] = pd.NA
        with self.assertRaisesRegex(ValueError, "claves nulas"):
            self.unir(panel, lateral, meta=meta, esperadas=esperadas)

    def test_cambio_de_ts_por_adaptador_no_se_oculta_al_restaurarlo(self):
        panel, lateral = _fixture()
        unir_real = ADAPTADOR.unir_sidecar

        def defectuoso(*args, **kwargs):
            resultado, identidad = unir_real(*args, **kwargs)
            resultado["ts_utc"] += pd.Timedelta(hours=1)
            return resultado, identidad

        with patch.object(ADAPTADOR, "unir_sidecar", defectuoso), self.assertRaisesRegex(ValueError, "alteró"):
            self.unir(panel, lateral)

    def test_huella_canonica_sobrevive_parquet_sintetico_temporal(self):
        import pyarrow as pa
        pa.set_cpu_count(1)
        pa.set_io_thread_count(1)
        _, lateral = _fixture("D")
        with tempfile.TemporaryDirectory(prefix="_sintetico_", dir=CARPETA) as temporal:
            ruta = Path(temporal) / "lateral_fixture.parquet"
            lateral.to_parquet(ruta, index=False, engine="pyarrow")
            releida = pd.read_parquet(ruta, engine="pyarrow")
            self.assertEqual(AMBIENTAL.huella_contenido(releida), AMBIENTAL.huella_contenido(lateral))
            self.assertNotEqual(hashlib.sha256(ruta.read_bytes()).hexdigest(), AMBIENTAL.huella_contenido(lateral))


if __name__ == "__main__":
    unittest.main(verbosity=2)
