from __future__ import annotations

import csv
import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import geopandas as gpd
import numpy as np
import pandas as pd
from affine import Affine
from shapely.geometry import box

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import descargar_maiac_aod as maiac  # noqa: E402
from scripts_pipeline.tests.test_producciones_modis import (  # noqa: E402
    maiac as granulos_maiac_reales,
)


class TrazabilidadCodigoTests(unittest.TestCase):
    def test_main_captura_el_hash_del_codigo_una_sola_vez(self):
        sha_fijo = "a" * 64
        with patch.object(maiac, "sha256_archivo", return_value=sha_fijo) as sha:
            resultado = maiac.main([
                "--desde", "2000-01-01",
                "--hasta", "2000-01-01",
                "--dry-run",
            ])

        self.assertEqual(resultado, 0)
        self.assertEqual(sha.call_args_list, [
            call(Path(maiac.__file__).resolve()),
            call(Path(maiac.producciones_modis.__file__).resolve()),
        ])

    def test_auditoria_reutiliza_el_hash_capturado_sin_releer_script(self):
        documento = {}
        ruta = Path("auditoria_prueba.json")
        codigo_archivo = Path("/codigo/descargar_maiac_aod.py")
        codigo_sha256 = "b" * 64

        def escribir(doc, destino):
            documento.update(doc)
            self.assertEqual(destino, ruta)
            return "sha-auditoria"

        with patch.object(
                maiac, "sha256_archivo",
                side_effect=AssertionError("la auditoría releyó el código")), \
                patch.object(maiac, "escribir_json_atomico",
                             side_effect=escribir):
            resultado = maiac._auditar(
                ruta=ruta,
                execution_id="ejecucion-prueba",
                codigo_archivo=codigo_archivo,
                codigo_sha256=codigo_sha256,
                fecha="2000-01-01",
                granulos=[],
                obs_path=None,
                pas_path=None,
                pasadas=None,
                cobertura={
                    "continente": 0,
                    "juan_fernandez": 0,
                    "desventuradas": 0,
                    "rapa_nui": 0,
                },
                catalogos_pixeles=[],
                mask_sha256="c" * 64,
                estado="no_disponible",
                raw_eliminado=True,
            )

        self.assertEqual(resultado, "sha-auditoria")
        self.assertEqual(documento["codigo"], {
            "archivo": str(codigo_archivo),
            "sha256": codigo_sha256,
        })


class _GrillaSintetica:
    """Interfaz mínima de DataArray/rio, sin HDF ni datos externos."""

    sizes = {"x": 2, "y": 2}
    rio = SimpleNamespace(
        crs="EPSG:4326",
        transform=lambda: Affine(1, 0, -70.5, 0, -1, -32.5),
    )

    def __getitem__(self, coordenada):
        valores = {"x": [-70.0, -69.0], "y": [-33.0, -34.0]}
        return SimpleNamespace(values=np.array(valores[coordenada]))


class TrazabilidadCatalogoCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="maiac-cache-test-")
        self.addCleanup(self.temporal.cleanup)
        self.catalogos = Path(self.temporal.name) / "catalogo_pixeles"
        for parche in (
            patch.object(maiac, "CATALOGO_PIXELES", self.catalogos),
            patch.object(maiac, "N_TILE", 2),
            patch.object(maiac, "N_COLUMNAS_GLOBALES", 36 * 2),
            patch("requests.sessions.Session.request", side_effect=AssertionError(
                "Las pruebas de caché no pueden abrir la red")),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        self.grilla = _GrillaSintetica()
        self.comunas = gpd.GeoDataFrame({
            "_ci": [0], "cod_comuna": [13101], "Comuna": ["Comuna sintetica"],
        }, geometry=[box(-70.25, -34.25, -69.75, -32.75)], crs="EPSG:4326")
        self.destino = self.catalogos / "tile=h11v12" / "pixeles.parquet"

    def comprobar_cache_del_dia_siguiente(self, cache, original):
        hash_antes = maiac.sha256_archivo(self.destino)
        cache.catalogos_usados.clear()
        with patch("rasterio.features.rasterize", side_effect=AssertionError(
                "Un cache hit no debe recalcular la máscara")), \
                patch.object(maiac, "escribir_parquet_atomico", side_effect=AssertionError(
                    "Un cache hit no debe reescribir el catálogo")):
            recuperado = cache.obtener(self.grilla, "h11v12", 11, 12)
        self.assertIs(recuperado, original)
        self.assertIsInstance(recuperado, tuple)
        self.assertEqual(len(recuperado), 4)
        self.assertEqual(recuperado[2:], (11, 12))
        self.assertEqual(cache.catalogos_usados, {self.destino})
        self.assertEqual(maiac.sha256_archivo(self.destino), hash_antes)

    def test_cache_hit_tras_clear_vuelve_a_registrar_catalogo_real(self):
        cache = maiac.CacheMascarasTile(self.comunas)
        original = cache.obtener(self.grilla, "h11v12", 11, 12)
        self.assertTrue(self.destino.is_file())
        self.assertEqual(maiac.validar_parquet(
            self.destino, maiac.COLUMNAS_CATALOGO, maiac._validar_catalogo,
        ), 2)
        np.testing.assert_array_equal(original[0], [[1, 0], [1, 0]])
        np.testing.assert_array_equal(original[1], [[0, -1], [0, -1]])
        self.comprobar_cache_del_dia_siguiente(cache, original)

    def test_catalogo_preexistente_tambien_se_registra_en_cache_hit(self):
        previo = maiac.CacheMascarasTile(self.comunas)
        previo.obtener(self.grilla, "h11v12", 11, 12)
        cache = maiac.CacheMascarasTile(self.comunas)
        with patch.object(maiac, "escribir_parquet_atomico", side_effect=AssertionError(
                "El catálogo preexistente válido debe reutilizarse")):
            original = cache.obtener(self.grilla, "h11v12", 11, 12)
        self.comprobar_cache_del_dia_siguiente(cache, original)

    def test_tile_sin_pixeles_chile_no_inventa_catalogo_en_cache_hit(self):
        fuera = self.comunas.copy()
        fuera.geometry = [box(10, 10, 11, 11)]
        cache = maiac.CacheMascarasTile(fuera)
        with patch.object(maiac, "escribir_parquet_atomico", side_effect=AssertionError(
                "Un tile sin píxeles de Chile no debe crear catálogo")):
            original = cache.obtener(self.grilla, "h11v12", 11, 12)
            cache.catalogos_usados.clear()
            recuperado = cache.obtener(self.grilla, "h11v12", 11, 12)
        self.assertIs(recuperado, original)
        self.assertEqual(len(recuperado), 4)
        self.assertEqual(recuperado[2:], (11, 12))
        np.testing.assert_array_equal(recuperado[0], np.zeros((2, 2), dtype=np.int32))
        np.testing.assert_array_equal(recuperado[1], np.full((2, 2), -1, dtype=np.int8))
        self.assertEqual(cache.catalogos_usados, set())
        self.assertFalse(self.destino.exists())


    def test_catalogo_previo_invalido_se_preserva_sin_reemplazar(self):
        self.destino.parent.mkdir(parents=True)
        self.destino.write_bytes(b"catalogo-unico-no-recuperado")
        cache = maiac.CacheMascarasTile(self.comunas)
        with self.assertRaises(Exception):
            cache.obtener(self.grilla, "h11v12", 11, 12)
        self.assertEqual(self.destino.read_bytes(), b"catalogo-unico-no-recuperado")

    def test_catalogo_previo_valido_pero_distinto_se_preserva(self):
        maiac.CacheMascarasTile(self.comunas).obtener(self.grilla, "h11v12", 11, 12)
        df = pd.read_parquet(self.destino)
        df["lat"] += np.float32(0.01)
        df.to_parquet(self.destino, index=False)
        previo = self.destino.read_bytes()
        with self.assertRaises(AssertionError):
            maiac.CacheMascarasTile(self.comunas).obtener(self.grilla, "h11v12", 11, 12)
        self.assertEqual(self.destino.read_bytes(), previo)

    def test_cache_hit_detecta_catalogo_alterado(self):
        cache = maiac.CacheMascarasTile(self.comunas)
        cache.obtener(self.grilla, "h11v12", 11, 12)
        self.destino.write_bytes(b"cambio-no-autorizado")
        with self.assertRaisesRegex(RuntimeError, "catálogo cambió"):
            cache.obtener(self.grilla, "h11v12", 11, 12)
        self.assertEqual(self.destino.read_bytes(), b"cambio-no-autorizado")

    def test_cache_hit_detecta_catalogo_ausente(self):
        cache = maiac.CacheMascarasTile(self.comunas)
        cache.obtener(self.grilla, "h11v12", 11, 12)
        self.destino.unlink()
        with self.assertRaises(FileNotFoundError):
            cache.obtener(self.grilla, "h11v12", 11, 12)


class SeguridadTransaccionalTests(unittest.TestCase):
    FECHA = "2003-08-16"
    EXECUTION_ID = "exec-prueba"

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="maiac-wal-test-")
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.base = self.raiz / "MCD19A2.061"
        self.trabajo = self.base / "_trabajo_descarga"
        self.salida = self.base / "pixeles_horario"
        self.observaciones = self.salida / "observaciones"
        self.pasadas_root = self.salida / "catalogo_pasadas"
        self.catalogos = self.salida / "catalogo_pixeles"
        self.auditoria = self.base / "manifiestos_pixeles_horario"
        self.ledger = self.base / "manifest_pixeles_horario.csv"
        self.base.mkdir(parents=True)
        self.cache = SimpleNamespace(catalogos_usados=set())
        self.comunas = gpd.GeoDataFrame(
            {"cod_comuna": [13101], "Comuna": ["Santiago"],
             "Region": ["RM"], "Provincia": ["Santiago"]},
            geometry=[box(-71, -34, -70, -33)], crs="EPSG:4326",
        )
        self.granulo_anterior, self.granulo = granulos_maiac_reales()
        self.nombre_fuente = self.granulo.data_links()[0].rsplit("/", 1)[-1]
        self.bytes_fuente = b"hdf-maiac-sintetico"

        def descargar(_earthaccess, _granulos, carpeta, _fecha):
            path = Path(carpeta) / self.nombre_fuente
            if not path.exists():
                path.write_bytes(self.bytes_fuente)
            return [path]

        parches = (
            patch.object(maiac, "BASE", self.base),
            patch.object(maiac, "TRABAJO", self.trabajo),
            patch.object(maiac, "RAIZ_SALIDA", self.salida),
            patch.object(maiac, "OBSERVACIONES", self.observaciones),
            patch.object(maiac, "CATALOGO_PASADAS", self.pasadas_root),
            patch.object(maiac, "CATALOGO_PIXELES", self.catalogos),
            patch.object(maiac, "AUDITORIA", self.auditoria),
            patch.object(maiac, "MANIFIESTO", self.ledger),
            patch.object(maiac, "SHP", self.raiz / "comunas.shp"),
            patch.object(maiac, "requerir_modulos"),
            patch.object(maiac, "login"),
            patch.object(maiac, "cargar_comunas", return_value=self.comunas),
            patch.object(maiac, "componentes_shapefile", return_value=[]),
            patch.object(maiac, "sha256_conjunto", return_value="m" * 64),
            patch.object(maiac, "CacheMascarasTile", return_value=self.cache),
            patch.object(maiac, "_buscar_dia", return_value=[self.granulo]),
            patch.object(maiac, "_descargar", side_effect=descargar),
            patch.object(maiac.uuid, "uuid4", return_value=self.EXECUTION_ID),
        )
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

        self.carpeta = self.trabajo / maiac.FLUJO / self.FECHA
        self.fuente = self.carpeta / self.nombre_fuente
        self.canonica = maiac._ruta_auditoria(self.FECHA)
        self.wal = maiac._ruta_auditoria_ejecucion(
            self.FECHA, self.EXECUTION_ID, "pre_borrado",
        )
        self.error = maiac._ruta_auditoria_ejecucion(
            self.FECHA, self.EXECUTION_ID, "error",
        )
        self.seleccion = maiac._ruta_auditoria_ejecucion(
            self.FECHA, self.EXECUTION_ID, "seleccion",
        )

    def _resultado_con_datos(self):
        ts = datetime.fromisoformat(self.FECHA).replace(
            hour=14, minute=30, tzinfo=timezone.utc,
        )
        overpass_id = maiac._overpass_id(ts, "Terra")
        obs = pd.DataFrame({
            "overpass_id": np.array([overpass_id], dtype=np.uint32),
            "pixel_id": np.array([123], dtype=np.uint32),
            "aod055": np.array([0.2], dtype=np.float32),
            "qa_raw": np.array([1], dtype=np.uint16),
        })
        pasadas = pd.DataFrame({
            "overpass_id": np.array([overpass_id], dtype=np.uint32),
            "ts_utc": [pd.Timestamp(ts)],
            "fecha": [self.FECHA],
            "hora_utc": np.array([14], dtype=np.uint8),
            "minuto_utc": np.array([30], dtype=np.uint8),
            "satelite": ["Terra"],
            "coleccion": ["MCD19A2.061"],
            "orbit_amount": ["1"],
            "granulos": [self.nombre_fuente],
        })
        cobertura = {
            "continente": 1,
            "juan_fernandez": 0,
            "desventuradas": 0,
            "rapa_nui": 0,
        }
        return obs, pasadas, cobertura

    def _resultado_vacio(self):
        return (
            pd.DataFrame(columns=maiac.COLUMNAS_OBS),
            pd.DataFrame(columns=maiac.COLUMNAS_PASADAS),
            {"continente": 0, "juan_fernandez": 0,
             "desventuradas": 0, "rapa_nui": 0},
        )

    def _ejecutar(self, resultado=None, side_effect=None):
        earthaccess = SimpleNamespace()
        def procesar_sintetico(*args):
            if isinstance(side_effect, BaseException):
                raise side_effect
            valor = (side_effect(*args) if side_effect else
                     (resultado if resultado is not None else self._resultado_con_datos()))
            if not valor[0].empty:
                self._catalogo_durabilidad()
            return valor
        procesar = patch.object(
            maiac, "_procesar", side_effect=procesar_sintetico,
        )
        previo = sys.modules.get("earthaccess")
        sys.modules["earthaccess"] = earthaccess
        try:
            with procesar:
                return maiac.main([
                    "--desde", self.FECHA, "--hasta", self.FECHA,
                    "--reserva-gb", "0",
                ])
        finally:
            if previo is None:
                sys.modules.pop("earthaccess", None)
            else:
                sys.modules["earthaccess"] = previo

    def _ledger_unico(self):
        with self.ledger.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_exito_persiste_wal_y_canonico_honesto_antes_de_borrar(self):
        real = maiac.escribir_json_atomico
        orden = []

        def registrar_orden(documento, ruta):
            orden.append((Path(ruta), self.fuente.exists(), documento))
            return real(documento, ruta)

        with patch.object(maiac, "escribir_json_atomico",
                          side_effect=registrar_orden):
            self.assertEqual(self._ejecutar(), 0)

        self.assertFalse(self.carpeta.exists())
        self.assertEqual([x[0] for x in orden],
                         [self.seleccion, self.wal, self.canonica, self.canonica])
        self.assertFalse(orden[0][1], "la selección debe preceder la descarga")
        self.assertTrue(orden[1][1], "el WAL debe preceder el borrado")
        self.assertTrue(orden[2][1], "el canónico validado precede al borrado")
        self.assertFalse(orden[2][2]["crudo_eliminado"])
        self.assertFalse(orden[3][1], "el cierre de retiro sigue al borrado")
        wal = json.loads(self.wal.read_text())
        canonica = json.loads(self.canonica.read_text())
        self.assertFalse(wal["crudo_eliminado"])
        self.assertEqual(
            wal["transaccion"]["evento"],
            "particion_validada_pre_borrado",
        )
        fuente = wal["transaccion"]["archivos_crudos_verificados"][0]
        self.assertEqual(fuente["sha256"], hashlib.sha256(
            self.bytes_fuente).hexdigest())
        self.assertTrue(canonica["crudo_eliminado"])
        self.assertEqual(canonica["transaccion"]["wal"]["archivo"],
                         str(self.wal))
        self.assertEqual(canonica["transaccion"]["wal"]["sha256"],
                         maiac.sha256_archivo(self.wal))
        self.assertEqual(self._ledger_unico()["estado"], "ok")

    def test_dia_vacio_tambien_persiste_wal_antes_de_borrar(self):
        real = maiac.escribir_json_atomico
        orden = []

        def registrar_orden(documento, ruta):
            orden.append((Path(ruta), self.fuente.exists(), documento))
            return real(documento, ruta)

        with patch.object(maiac, "escribir_json_atomico",
                          side_effect=registrar_orden):
            self.assertEqual(self._ejecutar(self._resultado_vacio()), 0)

        self.assertEqual([x[0] for x in orden],
                         [self.seleccion, self.wal, self.canonica, self.canonica])
        self.assertFalse(orden[0][1])
        self.assertTrue(orden[1][1])
        self.assertTrue(orden[2][1])
        self.assertFalse(orden[3][1])
        self.assertEqual(json.loads(self.wal.read_text())["estado"], "sin_datos")
        self.assertEqual(json.loads(self.canonica.read_text())["salidas"], [])
        self.assertEqual(self._ledger_unico()["estado"], "sin_datos")

    def test_seleccion_real_precede_hdf_y_persiste_identica_en_wal_canonico(self):
        real_sha = maiac.sha256_archivo

        def descargar(_earthaccess, granulos, carpeta, _fecha):
            self.assertEqual(granulos, [self.granulo])
            pre = json.loads(self.seleccion.read_text())
            self.assertEqual(pre["seleccion_granulos"]["candidatos_unicos"], 2)
            self.assertEqual(pre["seleccion_granulos"]["superseded"], 1)
            fuente = carpeta / self.nombre_fuente
            fuente.write_bytes(self.bytes_fuente)
            return [fuente]

        with patch.object(maiac, "_buscar_dia", return_value=[self.granulo_anterior, self.granulo]), \
                patch.object(maiac, "_descargar", side_effect=descargar) as bajar, \
                patch.object(maiac, "sha256_archivo", wraps=real_sha) as sha:
            self.assertEqual(self._ejecutar(), 0)
        bajar.assert_called_once()
        for archivo in (Path(maiac.__file__).resolve(), Path(maiac.producciones_modis.__file__).resolve()):
            # Captura inicial, guard prepublicación y guard prerretiro.
            self.assertEqual(sha.call_args_list.count(call(archivo)), 3)
        pre, wal, canonica = [json.loads(p.read_text()) for p in (self.seleccion, self.wal, self.canonica)]
        seleccion = canonica["seleccion_granulos"]
        self.assertEqual(seleccion, wal["seleccion_granulos"])
        self.assertEqual(seleccion["registro_pre_descarga"], {
            "archivo": str(self.seleccion), "sha256": real_sha(self.seleccion)})
        self.assertEqual(seleccion["codigo"]["sha256"], real_sha(Path(maiac.producciones_modis.__file__)))
        self.assertEqual({k: v for k, v in seleccion.items() if k != "registro_pre_descarga"}, pre["seleccion_granulos"])
        self.assertEqual(canonica["granulos"][0]["concept_id"], self.granulo["meta"]["concept-id"])
        self.assertTrue(canonica["crudo_eliminado"])
        self.assertFalse(self.carpeta.exists())

    def test_identidad_invalida_no_descarga_ni_borra(self):
        self.carpeta.mkdir(parents=True)
        retenida = self.carpeta / "retenida.hdf"
        retenida.write_bytes(b"fuente unica no validada")
        self.granulo.enlaces = ["https://example.test/invalido.hdf"]
        with patch.object(maiac, "_descargar") as bajar, \
                patch.object(maiac.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        bajar.assert_not_called()
        limpiar.assert_not_called()
        self.assertTrue(retenida.exists())
        self.assertFalse(self.canonica.exists())
        self.assertFalse(self.wal.exists())
        self.assertEqual(json.loads(self.error.read_text())["transaccion"]["fase"], "seleccion_produccion_nativa")

    def test_fallo_sidecar_seleccion_impide_descarga(self):
        with patch.object(maiac, "_auditar_inmutable", side_effect=OSError("fsync seleccion")), \
                patch.object(maiac, "_descargar") as bajar, \
                patch.object(maiac.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        bajar.assert_not_called()
        limpiar.assert_not_called()
        self.assertFalse(self.canonica.exists())

    def test_fallo_nueva_produccion_no_intenta_anterior(self):
        def fallar(*args):
            self.assertEqual(args[1], [self.granulo])
            self.assertTrue(self.seleccion.is_file())
            raise OSError("fuente nueva no disponible")
        with patch.object(maiac, "_buscar_dia", return_value=[self.granulo_anterior, self.granulo]), \
                patch.object(maiac, "_descargar", side_effect=fallar) as bajar:
            self.assertEqual(self._ejecutar(), 1)
        bajar.assert_called_once()
        error = json.loads(self.error.read_text())
        self.assertEqual(error["seleccion_granulos"]["superseded"], 1)
        self.assertEqual(error["transaccion"]["fase"], "descarga")
        self.assertFalse(self.canonica.exists())
        self.assertEqual(self._ledger_unico()["estado"], "error")

    def test_publicacion_previa_bloquea_sin_tocar_fuente_canonico_ledger(self):
        self.canonica.parent.mkdir(parents=True)
        contenido_previo = b"manifiesto-canonico-valido-previo"
        self.canonica.write_bytes(contenido_previo)
        maiac.Manifiesto(self.ledger).marcar(
            self.FECHA, maiac.FLUJO, "ok", 17, "hash-ledger-previo",
        )
        ledger_previo = self.ledger.read_bytes()
        self.carpeta.mkdir(parents=True)
        self.fuente.write_bytes(self.bytes_fuente)
        with patch.object(maiac, "_descargar") as bajar:
            self.assertEqual(self._ejecutar(), 2)
        bajar.assert_not_called()
        self.assertTrue(self.fuente.exists())
        self.assertFalse(self.wal.exists())
        self.assertEqual(self.canonica.read_bytes(), contenido_previo)
        self.assertEqual(self.ledger.read_bytes(), ledger_previo)
        self.assertFalse(self.error.exists())

    def test_falla_canonica_posterior_conserva_wal_y_sidecar_honesto(self):
        real = maiac._auditar

        def fallar_canonica(*, ruta, **kwargs):
            if Path(ruta) == self.canonica and kwargs["raw_eliminado"]:
                raise OSError("fsync canonico sintetico")
            return real(ruta=ruta, **kwargs)

        with patch.object(maiac, "_auditar", side_effect=fallar_canonica):
            self.assertEqual(self._ejecutar(), 1)

        self.assertFalse(self.carpeta.exists())
        self.assertTrue(self.wal.is_file())
        self.assertTrue(self.canonica.exists())
        self.assertFalse(json.loads(self.canonica.read_text())["crudo_eliminado"])
        sidecar = json.loads(self.error.read_text())
        self.assertTrue(sidecar["crudo_eliminado"])
        self.assertFalse(sidecar["transaccion"]["crudo_preservado"])
        self.assertEqual(sidecar["transaccion"]["wal"]["archivo"], str(self.wal))
        self.assertEqual(self._ledger_unico()["estado"], "error")

    def test_senal_despues_del_wal_preserva_fuente_y_provenance(self):
        real = maiac._archivos_crudos_verificados
        llamadas = 0

        def interrumpir_segunda_verificacion(*args, **kwargs):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                raise KeyboardInterrupt("SIGTERM sintetica")
            return real(*args, **kwargs)

        with patch.object(
                maiac, "_archivos_crudos_verificados",
                side_effect=interrumpir_segunda_verificacion):
            self.assertEqual(self._ejecutar(), 130)

        self.assertTrue(self.fuente.exists())
        self.assertTrue(self.wal.is_file())
        self.assertFalse(self.canonica.exists())
        sidecar = json.loads(self.error.read_text())
        self.assertTrue(sidecar["transaccion"]["crudo_preservado"])
        self.assertEqual(sidecar["transaccion"]["wal"]["archivo"], str(self.wal))
        self.assertEqual(self._ledger_unico()["estado"], "error")

    def test_senal_antes_del_wal_preserva_fuente_y_hash_descargado(self):
        self.assertEqual(
            self._ejecutar(side_effect=KeyboardInterrupt("SIGINT sintetica")),
            130,
        )

        self.assertTrue(self.fuente.exists())
        self.assertFalse(self.wal.exists())
        sidecar = json.loads(self.error.read_text())
        self.assertTrue(sidecar["transaccion"]["crudo_preservado"])
        self.assertIsNone(sidecar["transaccion"]["wal"])
        self.assertEqual(
            sidecar["granulos"][0]["sha256_descargado"],
            hashlib.sha256(self.bytes_fuente).hexdigest(),
        )
        self.assertEqual(self._ledger_unico()["estado"], "error")

    def test_wal_existente_es_inmutable(self):
        self.wal.parent.mkdir(parents=True)
        contenido = b"wal-previo-inmutable"
        self.wal.write_bytes(contenido)
        with patch.object(maiac, "_auditar") as auditar, \
                self.assertRaises(FileExistsError):
            maiac._auditar_inmutable(ruta=self.wal)
        auditar.assert_not_called()
        self.assertEqual(self.wal.read_bytes(), contenido)

    def _comprobar_fallo_tras_publicacion(self, tipo, previa):
        obs_path, pas_path = maiac._destinos(self.FECHA)
        objetivo = obs_path if tipo == "observaciones" else pas_path
        if previa:
            objetivo.parent.mkdir(parents=True, exist_ok=True)
            objetivo.write_bytes(b"contenido-previo-distinto")
            with patch.object(maiac, "_descargar") as bajar:
                self.assertEqual(self._ejecutar(), 2)
            bajar.assert_not_called()
            self.assertEqual(objetivo.read_bytes(), b"contenido-previo-distinto")
            self.assertFalse(self.ledger.exists())
            return
        real = maiac.escribir_parquet_atomico

        def publicar_y_fallar(df, ruta, *args, **kwargs):
            resultado = real(df, ruta, *args, **kwargs)
            if Path(ruta) == objetivo:
                raise OSError("fallo sintetico despues de os.replace")
            return resultado

        with patch.object(maiac, "escribir_parquet_atomico",
                          side_effect=publicar_y_fallar):
            self.assertEqual(self._ejecutar(), 1)

        sidecar = json.loads(self.error.read_text())
        self.assertTrue(sidecar["transaccion"]["salidas_publicadas"][tipo])
        self.assertTrue(sidecar["transaccion"]["salida_nueva_publicada"])
        salidas = {Path(item["archivo"]) for item in sidecar["salidas"]}
        self.assertIn(objetivo, salidas)
        self.assertTrue(self.fuente.exists())
        self.assertFalse(self.wal.exists())
        self.assertFalse(self.canonica.exists())
        self.assertEqual(self._ledger_unico()["estado"], "error")

    def test_fallo_tras_publicar_observaciones_nuevas(self):
        self._comprobar_fallo_tras_publicacion("observaciones", False)

    def test_fallo_tras_sustituir_observaciones_previas(self):
        self._comprobar_fallo_tras_publicacion("observaciones", True)

    def test_fallo_tras_publicar_pasadas_nuevas(self):
        self._comprobar_fallo_tras_publicacion("catalogo_pasadas", False)

    def test_fallo_tras_sustituir_pasadas_previas(self):
        self._comprobar_fallo_tras_publicacion("catalogo_pasadas", True)

    def test_system_exit_preserva_fuente_registra_error_y_se_propaga(self):
        with self.assertRaises(SystemExit) as salida:
            self._ejecutar(side_effect=SystemExit(7))
        self.assertEqual(salida.exception.code, 7)
        self.assertTrue(self.fuente.exists())
        self.assertTrue(self.error.is_file())
        self.assertFalse(self.wal.exists())
        self.assertEqual(self._ledger_unico()["estado"], "error")

    def test_fuente_huerfana_impide_skip_y_borrado_de_archivo_no_auditado(self):
        self.carpeta.mkdir(parents=True)
        huerfano = self.carpeta / "huerfano.hdf"
        huerfano.write_bytes(b"no auditado")
        with patch.object(maiac, "_particion_valida", return_value=True) as valida:
            self.assertEqual(self._ejecutar(), 1)

        valida.assert_not_called()
        self.assertTrue(huerfano.exists())
        self.assertTrue(self.fuente.exists())
        self.assertFalse(self.wal.exists())
        sidecar = json.loads(self.error.read_text())
        presentes = sidecar["transaccion"]["archivos_crudos_presentes"]
        self.assertEqual({Path(x["archivo"]).name for x in presentes},
                         {self.nombre_fuente, "huerfano.hdf"})
        self.assertEqual(self._ledger_unico()["estado"], "error")


    def test_wal_fallido_preserva_crudo_sin_publicar_canonico(self):
        real = maiac.escribir_json_atomico
        def fallar(doc, path):
            if Path(path) == self.wal:
                raise OSError("WAL fallido")
            return real(doc, path)
        with patch.object(maiac, "escribir_json_atomico", side_effect=fallar):
            self.assertEqual(self._ejecutar(), 1)
        self.assertEqual(self.fuente.read_bytes(), self.bytes_fuente)
        self.assertFalse(self.canonica.exists())

    def test_publicacion_canonica_pre_retiro_fallida_preserva_crudo(self):
        real = maiac._auditar
        def fallar(*, ruta, **kwargs):
            if Path(ruta) == self.canonica:
                raise OSError("canónico pre-retiro fallido")
            return real(ruta=ruta, **kwargs)
        with patch.object(maiac, "_auditar", side_effect=fallar), \
                patch.object(maiac.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        limpiar.assert_not_called()
        self.assertEqual(self.fuente.read_bytes(), self.bytes_fuente)
        self.assertTrue(self.wal.exists())
        self.assertEqual(json.loads(self.error.read_text())["transaccion"]["fase"],
                         "auditoria_canonica_pre_borrado")

    def _catalogo_durabilidad(self):
        path = self.catalogos / "tile=h11v12" / "pixeles.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            pd.DataFrame({
                "pixel_id": np.array([123], dtype=np.uint32), "tile": ["h11v12"],
                "fila": np.array([0], dtype=np.uint16),
                "columna": np.array([0], dtype=np.uint16),
                "lat": np.array([-33.5], dtype=np.float32),
                "lon": np.array([-70.5], dtype=np.float32),
                "cod_comuna": np.array([13101], dtype=np.int32),
                "etiqueta_comuna": ["Santiago"], "territorio": ["continente"],
            }).to_parquet(path, index=False)
        self.cache.catalogos_usados.add(path)
        return path

    def test_fsync_abarca_referencias_y_canonico_antes_del_primer_retiro(self):
        real_sync = maiac._sincronizar_publicacion
        real_limpiar = maiac.AreaTrabajo.limpiar_dia
        sincronizados = []
        def procesar(*_args):
            self._catalogo_durabilidad()
            return self._resultado_con_datos()
        def sincronizar(archivos):
            self.assertTrue(self.fuente.exists())
            doc = json.loads(self.canonica.read_text())
            self.assertTrue(doc["validacion"])
            self.assertFalse(doc["crudo_eliminado"])
            obs, pas = maiac._destinos(self.FECHA)
            self.assertEqual(set(archivos), {
                obs, pas, self.wal, self.seleccion, self.canonica,
                self.catalogos / "tile=h11v12" / "pixeles.parquet",
            })
            real_sync(archivos)
            sincronizados.append(True)
        def retirar(area, path):
            self.assertEqual(sincronizados, [True])
            return real_limpiar(area, path)
        with patch.object(maiac, "_sincronizar_publicacion", side_effect=sincronizar), \
                patch.object(maiac.AreaTrabajo, "limpiar_dia", new=retirar):
            self.assertEqual(self._ejecutar(side_effect=procesar), 0)

    def _comprobar_fallo_fsync_directorio(self, tipo):
        real_sync = maiac._sincronizar_publicacion
        real_open = os.open
        real_fsync = os.fsync
        obs, pas = maiac._destinos(self.FECHA)
        objetivos = {"obs": obs.parent, "pas": pas.parent,
                     "catalogo": self.catalogos / "tile=h11v12",
                     "auditoria": self.canonica.parent, "ancestro": self.base}
        def procesar(*_args):
            self._catalogo_durabilidad()
            return self._resultado_con_datos()
        def sincronizar(archivos):
            fallar_fd = set()
            def abrir(path, *args, **kwargs):
                fd = real_open(path, *args, **kwargs)
                if Path(path).resolve() == objetivos[tipo].resolve():
                    fallar_fd.add(fd)
                return fd
            def fsync(fd):
                if fd in fallar_fd:
                    raise OSError("fsync directorio sintético")
                return real_fsync(fd)
            with patch.object(maiac.os, "open", side_effect=abrir), \
                    patch.object(maiac.os, "fsync", side_effect=fsync):
                real_sync(archivos)
        with patch.object(maiac, "_sincronizar_publicacion", side_effect=sincronizar), \
                patch.object(maiac.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(side_effect=procesar), 1)
        limpiar.assert_not_called()
        self.assertEqual(self.fuente.read_bytes(), self.bytes_fuente)
        self.assertFalse(json.loads(self.canonica.read_text())["crudo_eliminado"])
        self.assertEqual(json.loads(self.error.read_text())["transaccion"]["fase"],
                         "fsync_publicacion_pre_borrado")

    def test_fsync_directorio_obs_fallido_preserva_crudo(self):
        self._comprobar_fallo_fsync_directorio("obs")

    def test_fsync_directorio_pasadas_fallido_preserva_crudo(self):
        self._comprobar_fallo_fsync_directorio("pas")

    def test_fsync_directorio_catalogo_fallido_preserva_crudo(self):
        self._comprobar_fallo_fsync_directorio("catalogo")

    def test_fsync_directorio_auditoria_fallido_preserva_crudo(self):
        self._comprobar_fallo_fsync_directorio("auditoria")

    def test_fsync_ancestro_fallido_preserva_crudo(self):
        self._comprobar_fallo_fsync_directorio("ancestro")

    def test_reentrada_tras_fsync_fallido_no_reemplaza_publicacion(self):
        with patch.object(maiac, "_sincronizar_publicacion", side_effect=OSError("fsync")):
            self.assertEqual(self._ejecutar(), 1)
        protegidos = {p: p.read_bytes() for p in
                      (*maiac._destinos(self.FECHA), self.canonica, self.wal,
                       self.ledger, self.fuente)}
        with patch.object(maiac, "_descargar") as bajar:
            self.assertEqual(self._ejecutar(), 2)
        bajar.assert_not_called()
        for path, contenido in protegidos.items():
            self.assertEqual(path.read_bytes(), contenido)

    def test_parciales_previos_no_se_borran_y_se_inspeccionan_bajo_lock(self):
        parciales = [self.salida / "historico.parquet.part.parquet",
                     self.auditoria / "previo.json.part",
                     self.ledger.with_name(self.ledger.name + ".part")]
        for path in parciales:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"parcial-previo-unico")
        real_rechazar = maiac._rechazar_parciales_pendientes
        def rechazar():
            import fcntl
            with (self.base / ".descargar_pixeles.lock").open("r") as fh:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            real_rechazar()
        with patch.object(maiac, "_rechazar_parciales_pendientes", side_effect=rechazar), \
                patch.object(maiac, "_descargar") as bajar, \
                self.assertRaisesRegex(RuntimeError, "parciales previos"):
            self._ejecutar()
        bajar.assert_not_called()
        for path in parciales:
            self.assertEqual(path.read_bytes(), b"parcial-previo-unico")
        self.assertFalse(self.ledger.exists())

    def test_codigo_cambiado_tras_publicacion_preliminar_preserva_crudo(self):
        real_guard = maiac._verificar_codigo_actual
        llamadas = 0
        def verificar(*args):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                raise RuntimeError("código cambió durante la ejecución")
            return real_guard(*args)
        with patch.object(maiac, "_verificar_codigo_actual", side_effect=verificar), \
                patch.object(maiac.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        limpiar.assert_not_called()
        self.assertEqual(self.fuente.read_bytes(), self.bytes_fuente)
        self.assertFalse(json.loads(self.canonica.read_text())["crudo_eliminado"])

    def test_reentrada_completa_solo_revalida_sin_reescribir(self):
        self.assertEqual(self._ejecutar(), 0)
        protegidos = {p: p.read_bytes() for p in
                      (*maiac._destinos(self.FECHA), self.canonica, self.wal, self.ledger)}
        with patch.object(maiac, "_descargar") as bajar:
            self.assertEqual(self._ejecutar(), 0)
        bajar.assert_not_called()
        for path, contenido in protegidos.items():
            self.assertEqual(path.read_bytes(), contenido)

    def test_sin_catalogo_referenciado_no_publica_ni_retira(self):
        with patch.object(self, "_catalogo_durabilidad"), \
                patch.object(maiac.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        limpiar.assert_not_called()
        self.assertEqual(self.fuente.read_bytes(), self.bytes_fuente)
        self.assertFalse(self.canonica.exists())

    def test_reentrada_catalogo_alterado_bloquea_sin_reparar(self):
        self.assertEqual(self._ejecutar(), 0)
        catalogo = self.catalogos / "tile=h11v12" / "pixeles.parquet"
        catalogo.write_bytes(b"catalogo-alterado")
        ledger = self.ledger.read_bytes()
        with patch.object(maiac, "_descargar") as bajar:
            self.assertEqual(self._ejecutar(), 2)
        bajar.assert_not_called()
        self.assertEqual(catalogo.read_bytes(), b"catalogo-alterado")
        self.assertEqual(self.ledger.read_bytes(), ledger)

    def test_hdf_cambiado_mismo_tamano_post_wal_no_se_retira(self):
        real_sync = maiac._sincronizar_publicacion
        alterado = b"x" * len(self.bytes_fuente)
        def sincronizar(archivos):
            real_sync(archivos)
            self.fuente.write_bytes(alterado)
        with patch.object(maiac, "_sincronizar_publicacion", side_effect=sincronizar), \
                patch.object(maiac.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        limpiar.assert_not_called()
        self.assertEqual(self.fuente.read_bytes(), alterado)
        self.assertEqual(json.loads(self.error.read_text())["transaccion"]["fase"],
                         "rehash_fuentes_pre_retiro")

    def test_publicacion_sin_ledger_no_inventa_cierre(self):
        self.assertEqual(self._ejecutar(), 0)
        self.ledger.unlink()
        previo = self.canonica.read_bytes()
        with patch.object(maiac, "_descargar") as bajar:
            self.assertEqual(self._ejecutar(), 2)
        bajar.assert_not_called()
        self.assertFalse(self.ledger.exists())
        self.assertEqual(self.canonica.read_bytes(), previo)


class BarreraDurableTests(unittest.TestCase):
    def test_fsync_todos_los_ancestros_hasta_base_sin_cambiar_bytes(self):
        with tempfile.TemporaryDirectory(prefix="maiac-fsync-test-") as temp:
            base = Path(temp).resolve()
            path = base / "producto" / "year=2026" / "day=14" / "salida"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"observaciones")
            directorios = []
            real_open = os.open
            def abrir(p, *args, **kwargs):
                fd = real_open(p, *args, **kwargs)
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    directorios.append(Path(p))
                return fd
            with patch.object(maiac, "BASE", base), \
                    patch.object(maiac.os, "open", side_effect=abrir):
                maiac._sincronizar_publicacion({path: maiac.sha256_archivo(path)})
            self.assertEqual(directorios, [path.parent, path.parent.parent,
                                         path.parent.parent.parent, base])
            self.assertEqual(path.read_bytes(), b"observaciones")

    def test_guard_detecta_hash_actual_distinto(self):
        with tempfile.TemporaryDirectory(prefix="maiac-code-test-") as temp:
            p = Path(temp) / "codigo.py"
            p.write_bytes(b"version-original")
            sha = maiac.sha256_archivo(p)
            p.write_bytes(b"version-modificada")
            with self.assertRaisesRegex(RuntimeError, "código cambió"):
                maiac._verificar_codigo_actual(p, sha, {"archivo": str(p), "sha256": sha})


if __name__ == "__main__":
    unittest.main()
