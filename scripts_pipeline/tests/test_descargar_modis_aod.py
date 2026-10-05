from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import descargar_modis_aod as modis  # noqa: E402
from scripts_pipeline.tests.test_producciones_modis import (  # noqa: E402
    Granulo as GranuloCMR, terra as granulos_terra_reales,
)


class _LedgerGrabador:
    def __init__(self, falla: bool = False):
        self.falla = falla
        self.llamadas = []

    def marcar(self, *args, **kwargs):
        self.llamadas.append((args, kwargs))
        if self.falla:
            raise OSError("ledger sintético")

    def obtener(self, _fecha, _flujo):
        return None


class AuditoriaTests(unittest.TestCase):
    def test_main_captura_el_hash_del_codigo_una_sola_vez(self):
        sha_fijado = "c" * 64
        with patch.object(modis, "sha256_archivo", return_value=sha_fijado) as sha:
            resultado = modis.main([
                "--desde", "2000-01-01",
                "--hasta", "2000-01-01",
                "--dry-run",
            ])

        self.assertEqual(resultado, 0)
        self.assertEqual(sha.call_args_list, [
            call(Path(modis.__file__).resolve()),
            call(Path(modis.producciones_modis.__file__).resolve()),
        ])

    def test_reutiliza_identidad_de_codigo_fijada_por_la_ejecucion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            codigo = root / "descargar_modis_aod.py"
            codigo.write_text("primera version", encoding="utf-8")
            sha_fijado = "a" * 64
            rutas = [root / "audit_1.json", root / "audit_2.json"]

            # _auditar no debe volver a leer ni hashear el .py. En una corrida
            # real, main entrega a todas las auditorías esta misma identidad.
            with patch.object(
                modis,
                "sha256_archivo",
                side_effect=AssertionError("se recalculó el hash del código"),
            ):
                for indice, ruta in enumerate(rutas, start=1):
                    codigo.write_text(f"version sincronizada {indice}", encoding="utf-8")
                    modis._auditar(
                        destino=None,
                        ruta=ruta,
                        execution_id="ejecucion-prueba",
                        codigo_archivo=codigo,
                        codigo_sha256=sha_fijado,
                        fecha=f"2020-01-0{indice}",
                        sensor="terra",
                        short_name="MOD04_3K",
                        version="6.1",
                        granulos=[],
                        pixeles=None,
                        mask_sha256="b" * 64,
                        estado="no_disponible",
                        raw_eliminado=True,
                    )

            identidades = [
                json.loads(ruta.read_text(encoding="utf-8"))["codigo"]
                for ruta in rutas
            ]
            self.assertEqual(
                identidades,
                [{"archivo": str(codigo), "sha256": sha_fijado}] * 2,
            )


class WALParticionTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="modis-wal-test-")
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.trabajo = self.raiz / "_trabajo_descarga"
        self.carpeta = self.trabajo / "aqua" / "2026-09-11"
        self.carpeta.mkdir(parents=True)
        self.src = self.carpeta / "MYD04_3K.A2026254.2100.061.test.hdf"
        self.src.write_bytes(b"fuente MODIS sintetica")
        self.destino = self.raiz / "modis_aqua_20260911.parquet"
        self.destino.write_bytes(b"salida Parquet sintetica validada")
        self.audit_path = self.raiz / "modis_aqua_20260911.json"
        self.execution_id = "exec-prueba"
        self.granulos = [{
            "concept_id": "G-PRUEBA",
            "url": "https://example.test/fuente.hdf",
            "archivo_descargado": self.src.name,
            "bytes_descargados": self.src.stat().st_size,
            "sha256_descargado": modis.sha256_archivo(self.src),
        }]
        self.pixeles = modis.pd.DataFrame({
            "territorio": ["continente"],
            "ts_utc": modis.pd.to_datetime(["2026-09-11T21:00:00Z"]),
            "fuente": ["DT_DB_combined"],
            "tiempo_fuente": ["Scan_Start_Time_TAI93"],
        })

    def _auditoria(self):
        return {
            "execution_id": self.execution_id,
            "codigo_archivo": self.raiz / "descargar_modis_aod.py",
            "codigo_sha256": "c" * 64,
            "fecha": "2026-09-11",
            "sensor": "aqua",
            "short_name": "MYD04_3K",
            "version": "6.1",
            "granulos": self.granulos,
            "pixeles": self.pixeles,
            "mask_sha256": "m" * 64,
        }

    def _confirmar_ok(self, area, ledger):
        return modis._confirmar_particion(
            area=area,
            carpeta=self.carpeta,
            destino=self.destino,
            audit_path=self.audit_path,
            estado="ok",
            filas=1,
            sha_salida=modis.sha256_archivo(self.destino),
            manifiesto=ledger,
            flujo="aqua",
            auditoria=self._auditoria(),
        )

    def _sidecar_error(self, mensaje, *, salida=True, fase="prueba"):
        return modis._registrar_error_sidecar(
            carpeta=self.carpeta,
            destino=self.destino,
            audit_path=self.audit_path,
            salida_nueva_publicada=salida,
            fase=fase,
            error=mensaje,
            auditoria=self._auditoria(),
        )

    def test_exito_persiste_wal_antes_de_borrar_y_encadena_canonico(self):
        ledger = _LedgerGrabador()
        with modis.AreaTrabajo(
            self.trabajo, preservar_no_validados=True,
        ) as area:
            wal_path, sha_audit = self._confirmar_ok(area, ledger)

        self.assertFalse(self.carpeta.exists())
        wal = json.loads(wal_path.read_text(encoding="utf-8"))
        canonico = json.loads(self.audit_path.read_text(encoding="utf-8"))
        self.assertFalse(wal["crudo_eliminado"])
        self.assertEqual(
            wal["transaccion"]["evento"],
            "particion_validada_pre_borrado",
        )
        self.assertEqual(
            wal["transaccion"]["archivos_crudos_verificados"][0]["sha256"],
            self.granulos[0]["sha256_descargado"],
        )
        self.assertTrue(canonico["crudo_eliminado"])
        self.assertEqual(
            canonico["transaccion"]["wal"]["sha256"],
            modis.sha256_archivo(wal_path),
        )
        self.assertEqual(modis.sha256_archivo(self.audit_path), sha_audit)
        self.assertEqual(ledger.llamadas[0][1]["estado"], "ok")
        self.assertIn("+", ledger.llamadas[0][1]["sha256"])

    def test_sin_datos_tambien_usa_wal_y_luego_confirma_borrado(self):
        ledger = _LedgerGrabador()
        auditoria = self._auditoria()
        auditoria["pixeles"] = None
        with modis.AreaTrabajo(
            self.trabajo, preservar_no_validados=True,
        ) as area:
            wal_path, _ = modis._confirmar_particion(
                area=area, carpeta=self.carpeta, destino=None,
                audit_path=self.audit_path, estado="sin_datos", filas=0,
                sha_salida="", manifiesto=ledger, flujo="aqua",
                auditoria=auditoria,
            )

        self.assertFalse(self.carpeta.exists())
        self.assertFalse(json.loads(wal_path.read_text())["crudo_eliminado"])
        self.assertTrue(json.loads(self.audit_path.read_text())["crudo_eliminado"])
        self.assertEqual(ledger.llamadas[0][1]["estado"], "sin_datos")
        self.assertNotIn("+", ledger.llamadas[0][1]["sha256"])

    def test_extra_no_auditado_falla_y_area_optin_preserva_todo_al_salir(self):
        extra = self.carpeta / "residuo_otra_ejecucion.hdf"
        extra.write_bytes(b"no atribuir")
        self.audit_path.write_bytes(b'{"canonico_previo": true}\n')
        previo = self.audit_path.read_bytes()
        ledger = _LedgerGrabador()

        with self.assertRaisesRegex(RuntimeError, "extras no auditados"):
            with modis.AreaTrabajo(
                self.trabajo, preservar_no_validados=True,
            ) as area:
                self._confirmar_ok(area, ledger)

        self.assertTrue(self.src.exists())
        self.assertTrue(extra.exists())
        self.assertEqual(self.audit_path.read_bytes(), previo)
        self.assertFalse(ledger.llamadas)
        wal_path = modis._ruta_evento_auditoria(
            self.audit_path, self.execution_id, "pre_borrado",
        )
        self.assertFalse(wal_path.exists())

    def test_output_nuevo_y_falla_wal_preserva_fuente_y_canonico_previo(self):
        self.audit_path.write_bytes(b'{"canonico_previo": true}\n')
        previo = self.audit_path.read_bytes()
        ledger = _LedgerGrabador()
        with patch.object(
            modis, "_auditar_inmutable", side_effect=OSError("fsync WAL sintético"),
        ), self.assertRaisesRegex(OSError, "fsync WAL sintético"):
            with modis.AreaTrabajo(
                self.trabajo, preservar_no_validados=True,
            ) as area:
                self._confirmar_ok(area, ledger)

        self.assertTrue(self.src.exists())
        self.assertTrue(self.destino.exists())
        self.assertEqual(self.audit_path.read_bytes(), previo)
        error_path, _ = self._sidecar_error("WAL falló", salida=True,
                                            fase="wal_y_confirmacion")
        error = json.loads(error_path.read_text())
        self.assertFalse(error["crudo_eliminado"])
        self.assertTrue(error["transaccion"]["crudo_preservado"])
        self.assertTrue(error["transaccion"]["salida_nueva_publicada"])
        self.assertEqual(
            error["salida"]["sha256"], modis.sha256_archivo(self.destino),
        )

    def test_falla_limpieza_deja_wal_y_fuente_para_recuperacion(self):
        self.audit_path.write_bytes(b'{"canonico_previo": true}\n')
        previo = self.audit_path.read_bytes()
        ledger = _LedgerGrabador()
        with modis.AreaTrabajo(
            self.trabajo, preservar_no_validados=True,
        ) as area, patch.object(
            area, "limpiar_dia", side_effect=OSError("limpieza sintética"),
        ), self.assertRaisesRegex(OSError, "limpieza sintética"):
            self._confirmar_ok(area, ledger)

        wal_path = modis._ruta_evento_auditoria(
            self.audit_path, self.execution_id, "pre_borrado",
        )
        self.assertTrue(wal_path.exists())
        self.assertTrue(self.src.exists())
        self.assertEqual(self.audit_path.read_bytes(), previo)
        error_path, _ = self._sidecar_error("limpieza falló", salida=True)
        error = json.loads(error_path.read_text())
        self.assertFalse(error["crudo_eliminado"])
        self.assertIsNotNone(error["transaccion"]["wal"])

    def test_falla_ledger_postcommit_conserva_wal_y_canonico(self):
        ledger = _LedgerGrabador(falla=True)
        with self.assertRaisesRegex(OSError, "ledger sintético"):
            with modis.AreaTrabajo(
                self.trabajo, preservar_no_validados=True,
            ) as area:
                self._confirmar_ok(area, ledger)

        wal_path = modis._ruta_evento_auditoria(
            self.audit_path, self.execution_id, "pre_borrado",
        )
        self.assertFalse(self.carpeta.exists())
        self.assertTrue(wal_path.exists())
        self.assertTrue(json.loads(self.audit_path.read_text())["crudo_eliminado"])
        error_path, _ = self._sidecar_error("ledger falló", salida=True,
                                            fase="wal_y_confirmacion")
        error = json.loads(error_path.read_text())
        self.assertTrue(error["crudo_eliminado"])
        self.assertFalse(error["transaccion"]["crudo_preservado"])
        self.assertEqual(
            error["transaccion"]["wal"]["sha256"],
            modis.sha256_archivo(wal_path),
        )

    def test_fuente_pendiente_impide_saltar_canonico_previo_valido(self):
        with patch.object(modis, "_particion_valida", return_value=True) as validar:
            reutilizable = modis._particion_reutilizable_sin_crudo(
                carpeta=self.carpeta, destino=self.destino,
                fecha="2026-09-11", flujo="aqua",
                manifiesto=object(), audit_path=self.audit_path,
            )
        self.assertFalse(reutilizable)
        validar.assert_not_called()

    def test_keyboard_interrupt_main_escribe_sidecar_y_area_preserva_hdf(self):
        base = self.raiz / "producto"
        trabajo = base / "_trabajo_descarga"
        salida = base / "pixeles_horario"
        auditorias = base / "manifiestos_pixeles_horario"
        ledger = _LedgerGrabador()
        granulo = GranuloCMR(
            "G123-LAADS", "MYD04_3K.A2026254.2100.061.2026257120000.hdf",
        )

        def descargar(_earthaccess, _granulos, carpeta, _descripcion):
            src = carpeta / "interrumpido.hdf"
            src.write_bytes(b"fuente interrumpida")
            return [src]

        def anotar(descripciones, paths):
            item = dict(descripciones[0])
            item.update({
                "archivo_descargado": paths[0].name,
                "bytes_descargados": paths[0].stat().st_size,
                "sha256_descargado": modis.sha256_archivo(paths[0]),
            })
            return [item]

        earthaccess = SimpleNamespace()
        with patch.dict(sys.modules, {"earthaccess": earthaccess}), \
                patch.object(modis, "BASE", base), \
                patch.object(modis, "TRABAJO", trabajo), \
                patch.object(modis, "SALIDA", salida), \
                patch.object(modis, "AUDITORIA", auditorias), \
                patch.object(modis, "MANIFIESTO", base / "ledger.csv"), \
                patch.object(modis, "SHP", self.raiz / "comunas.shp"), \
                patch.object(modis, "requerir_modulos"), \
                patch.object(modis, "login"), \
                patch.object(modis, "cargar_comunas", return_value=object()), \
                patch.object(modis, "limpiar_parciales"), \
                patch.object(modis, "Manifiesto", return_value=ledger), \
                patch.object(modis, "componentes_shapefile", return_value=[]), \
                patch.object(modis, "sha256_conjunto", return_value="m" * 64), \
                patch.object(modis, "_buscar_dia", return_value=[granulo]), \
                patch.object(modis, "describir_granulos", return_value=[{
                    "concept_id": "G-INTERRUPCION", "url": "",
                    "checksum_origen": [],
                }]), \
                patch.object(modis, "_descargar", side_effect=descargar), \
                patch.object(modis, "anotar_checksums_descargados", side_effect=anotar), \
                patch.object(modis, "_procesar", side_effect=KeyboardInterrupt("INT")):
            resultado = modis.main([
                "--sensor", "aqua", "--desde", "2026-09-11",
                "--hasta", "2026-09-11", "--reserva-gb", "0",
            ])

        carpeta = trabajo / "aqua" / "2026-09-11"
        self.assertTrue((carpeta / "interrumpido.hdf").exists())
        errores = list(auditorias.rglob("*.error.json"))
        self.assertEqual(len(errores), 1)
        doc = json.loads(errores[0].read_text())
        self.assertFalse(doc["crudo_eliminado"])
        self.assertTrue(doc["transaccion"]["crudo_preservado"])
        self.assertEqual(resultado, 130)
        self.assertEqual(ledger.llamadas[-1][0][2], "error")


class SeleccionMainTests(unittest.TestCase):
    """Main real hasta Parquet/WAL, con CMR y HDF exclusivamente sintéticos."""
    FECHA = "2022-10-24"

    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="modis-seleccion-test-")
        self.addCleanup(temporal.cleanup)
        self.base = Path(temporal.name)
        self.trabajo = self.base / "trabajo"
        self.auditoria = self.base / "auditoria"
        self.ledger = _LedgerGrabador()
        self.viejo, self.nuevo = granulos_terra_reales()
        self.nombre = self.nuevo.data_links()[0].rsplit("/", 1)[-1]
        for parche in (
            patch.object(modis, "BASE", self.base),
            patch.object(modis, "TRABAJO", self.trabajo),
            patch.object(modis, "SALIDA", self.base / "salidas"),
            patch.object(modis, "AUDITORIA", self.auditoria),
            patch.object(modis, "MANIFIESTO", self.base / "ledger.csv"),
            patch.object(modis, "SHP", self.base / "comunas.shp"),
            patch.object(modis, "requerir_modulos"),
            patch.object(modis, "login"),
            patch.object(modis, "cargar_comunas", return_value=object()),
            patch.object(modis, "limpiar_parciales"),
            patch.object(modis, "Manifiesto", return_value=self.ledger),
            patch.object(modis, "componentes_shapefile", return_value=[]),
            patch.object(modis, "sha256_conjunto", return_value="m" * 64),
            patch.object(modis.uuid, "uuid4", return_value="exec-seleccion"),
            patch.object(modis, "_buscar_dia", return_value=[self.viejo, self.nuevo]),
            patch.object(modis, "_procesar", return_value=self._pixeles()),
            patch("requests.sessions.Session.request", side_effect=AssertionError("sin red")),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        self.canonica = modis._ruta_auditoria(self.FECHA, "terra")
        self.seleccion = modis._ruta_evento_auditoria(self.canonica, "exec-seleccion", "seleccion")
        self.wal = modis._ruta_evento_auditoria(self.canonica, "exec-seleccion", "pre_borrado")
        self.error = modis._ruta_evento_auditoria(self.canonica, "exec-seleccion", "error")
        self.carpeta = self.trabajo / "terra" / self.FECHA

    def _pixeles(self):
        return modis.pd.DataFrame({
            "pixel_id": [123], "granulo": [self.nombre], "producto": ["MOD04_3K"],
            "satelite": ["Terra"], "ts_utc": modis.pd.to_datetime([self.FECHA + "T14:15:03Z"]),
            "fecha": [self.FECHA], "hora_utc": [14], "minuto_utc": [15],
            "fila": [1], "columna": [2], "lat": [-33.4], "lon": [-70.6],
            "cod_comuna": [13101], "etiqueta_comuna": ["Santiago"], "aod550": [0.2],
            "qa": [3], "fuente": ["DT_DB_combined"], "tiempo_fuente": ["Scan_Start_Time_TAI93"],
            "scan_start_tai93": [940428903.0], "territorio": ["continente"],
        })

    def _ejecutar(self):
        previo = sys.modules.get("earthaccess")
        sys.modules["earthaccess"] = SimpleNamespace()
        try:
            return modis.main(["--sensor", "terra", "--desde", self.FECHA,
                               "--hasta", self.FECHA, "--reserva-gb", "0"])
        finally:
            if previo is None:
                sys.modules.pop("earthaccess", None)
            else:
                sys.modules["earthaccess"] = previo

    def _descargar(self, _earthaccess, granulos, carpeta, _descripcion):
        self.assertEqual(granulos, [self.nuevo])
        pre = json.loads(self.seleccion.read_text())
        self.assertEqual(pre["seleccion_granulos"]["candidatos_unicos"], 2)
        self.assertEqual(pre["seleccion_granulos"]["superseded"], 1)
        self.assertFalse(pre["crudo_eliminado"])
        fuente = carpeta / self.nombre
        fuente.write_bytes(b"HDF sintetico, no NASA")
        return [fuente]

    def test_seleccion_durable_antes_de_hdf_se_propaga_a_wal_y_canonico(self):
        real_sha = modis.sha256_archivo
        with patch.object(modis, "_descargar", side_effect=self._descargar) as descargar, \
                patch.object(modis, "sha256_archivo", wraps=real_sha) as sha:
            self.assertEqual(self._ejecutar(), 0)
        descargar.assert_called_once()
        for archivo in (Path(modis.__file__).resolve(), Path(modis.producciones_modis.__file__).resolve()):
            self.assertEqual(sha.call_args_list.count(call(archivo)), 1)
        pre, wal, canonica = [json.loads(p.read_text()) for p in (self.seleccion, self.wal, self.canonica)]
        seleccion = canonica["seleccion_granulos"]
        self.assertEqual(seleccion, wal["seleccion_granulos"])
        self.assertEqual(seleccion["registro_pre_descarga"], {
            "archivo": str(self.seleccion), "sha256": real_sha(self.seleccion)})
        self.assertEqual(seleccion["codigo"]["sha256"], real_sha(Path(modis.producciones_modis.__file__)))
        self.assertEqual({k: v for k, v in seleccion.items() if k != "registro_pre_descarga"}, pre["seleccion_granulos"])
        self.assertEqual(canonica["granulos"][0]["concept_id"], self.nuevo["meta"]["concept-id"])
        self.assertTrue(canonica["crudo_eliminado"])
        self.assertFalse(self.carpeta.exists())
        self.assertEqual(self.ledger.llamadas[-1][1]["estado"], "ok")

    def test_identidad_invalida_no_descarga_ni_borra_fuente_previa(self):
        self.carpeta.mkdir(parents=True)
        retenida = self.carpeta / "retenida.hdf"
        retenida.write_bytes(b"fuente unica no validada")
        self.nuevo.enlaces = ["https://example.test/invalido.hdf"]
        with patch.object(modis, "_descargar") as descargar, \
                patch.object(modis.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        descargar.assert_not_called()
        limpiar.assert_not_called()
        self.assertTrue(retenida.exists())
        self.assertFalse(self.canonica.exists())
        self.assertFalse(self.wal.exists())
        self.assertEqual(json.loads(self.error.read_text())["transaccion"]["fase"], "seleccion_produccion_nativa")

    def test_fallo_sidecar_seleccion_impide_descarga(self):
        with patch.object(modis, "_auditar_inmutable", side_effect=OSError("fsync seleccion")), \
                patch.object(modis, "_descargar") as descargar, \
                patch.object(modis.AreaTrabajo, "limpiar_dia") as limpiar:
            self.assertEqual(self._ejecutar(), 1)
        descargar.assert_not_called()
        limpiar.assert_not_called()
        self.assertFalse(self.canonica.exists())

    def test_fallo_nueva_produccion_no_intenta_anterior(self):
        def fallar(*args):
            self.assertEqual(args[1], [self.nuevo])
            self.assertTrue(self.seleccion.is_file())
            raise OSError("fuente nueva no disponible")
        with patch.object(modis, "_descargar", side_effect=fallar) as descargar:
            self.assertEqual(self._ejecutar(), 1)
        descargar.assert_called_once()
        error = json.loads(self.error.read_text())
        self.assertEqual(error["seleccion_granulos"]["superseded"], 1)
        self.assertEqual(error["transaccion"]["fase"], "descarga_crudo")
        self.assertFalse(self.canonica.exists())


if __name__ == "__main__":
    unittest.main()
