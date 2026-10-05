"""Fallos transaccionales del descargador; todas las fuentes son sinteticas."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import xarray as xr

EXTRACTORES = Path(__file__).resolve().parents[2] / "scripts_superficie" / "extractores"
sys.path.insert(0, str(EXTRACTORES))
import descargar_era5land as d
import normalizar_era5land_chile as motor


class PublicacionSeguraTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = Path(self.stack.enter_context(TemporaryDirectory()))
        self.raiz = self.tmp / "producto"
        self.raiz.mkdir()
        self.staging = self.tmp / "staging"
        self.fuente = self.staging / "202609" / "era5land_202609.continente.nc"
        self.fuente.parent.mkdir(parents=True)
        self.periodo = pd.Period("2026-09", freq="M")
        self.variables = list(d.CANONICAS_LAND)
        self.catalogo = self.raiz / "catalogo_pixeles.parquet"
        self.relacion = self.raiz / "relacion_pixel_comuna.parquet"
        self.cat_manifest = self.raiz / "catalogo.json"
        cat = pd.DataFrame({
            "latitude": [-33., -33.1], "longitude": [-70., -69.9],
            "lat_index_global": [1230, 1231], "lon_index_global": [2900, 2901],
            "pixel_id": [1230 * 3600 + 2900, 1231 * 3600 + 2901],
            "cod_comuna": [1, 1], "territorio": ["continental"] * 2,
            "aoi_id": ["continente"] * 2,
        })
        cat.to_parquet(self.catalogo)
        cat[["pixel_id", "cod_comuna"]].to_parquet(self.relacion)
        self.cat_manifest.write_text("{}")
        for modulo in (d, motor):
            self.stack.enter_context(patch.object(modulo, "asegurar_disco_externo"))
        self.stack.enter_context(patch.object(d, "STAGING", self.staging))
        self.stack.enter_context(patch.object(d, "COMUNAS", self.tmp / "comunas.shp"))
        self.stack.enter_context(patch.object(motor, "crear_catalogos", return_value=(
            self.catalogo, self.relacion, self.cat_manifest,
        )))
        self.stack.enter_context(patch.object(motor, "_versiones_software", return_value={
            "motor_normalizacion_sha256": d.sha256_archivo(Path(motor.__file__)),
            "script_producto_sha256": d.sha256_archivo(Path(motor.__file__)),
            "fixture": "sintetica",
        }))
        self.escribir_fuente(192)
        self.salida, self.manifest = motor.normalizar_mes(
            [self.fuente], self.periodo, self.raiz, d.COMUNAS,
            self.variables, True,
        )
        self.prev_salida = self.salida.read_bytes()
        self.prev_manifest = self.manifest.read_bytes()
        self.escribir_fuente(216)
        d._CRUDOS_TRANSITORIOS.clear()
        d._PARCIALES_ACTIVOS.clear()
        d._LOCK_ACTIVO = None
        self.addCleanup(d._CRUDOS_TRANSITORIOS.clear)
        self.addCleanup(d._PARCIALES_ACTIVOS.clear)

    def escribir_fuente(self, horas):
        times = pd.date_range("2026-09-01", periods=horas, freq="h")
        data = np.arange(horas * 4, dtype="float32").reshape(horas, 2, 2)
        ds = xr.Dataset(
            {v: (("time", "lat", "lon"), data + i)
             for i, v in enumerate(self.variables)},
            coords={"time": times, "lat": [-33., -33.1], "lon": [-70., -69.9]},
        )
        ds.to_netcdf(self.fuente, engine="netcdf4")
        ds.close()

    def publicar(self):
        return d._publicar_mes_seguro(
            [self.fuente], [self.fuente], self.periodo, self.raiz,
            self.catalogo, self.variables, True,
            [{"aoi_id": "continente", "variable": d.VARS_LAND}],
            pd.Timestamp("2026-09-09", tz="UTC"),
        )

    def verificar_respaldo(self):
        registros = list((self.raiz / "_respaldos_publicacion").rglob("respaldo.json"))
        self.assertEqual(len(registros), 1)
        meta = json.loads(registros[0].read_text())
        self.assertFalse(meta["retiro_automatico_permitido"])
        self.assertEqual(meta["manifiesto_previo"], json.loads(self.prev_manifest))
        esperado = {self.salida.name: self.prev_salida, self.manifest.name: self.prev_manifest}
        for item in meta["artefactos"]:
            copia = Path(item["respaldo"])
            self.assertEqual(copia.read_bytes(), esperado[copia.name])
            self.assertEqual(d.sha256_archivo(copia), item["sha256"])
        return registros[0]

    def assert_fuente_conservada(self):
        self.assertTrue(self.fuente.exists())
        d._CRUDOS_TRANSITORIOS.add(self.fuente)
        d._limpiar_recursos()
        self.assertTrue(self.fuente.exists())

    def test_camino_feliz_conserva192h_y_respaldo_y_retira_solo_tras_fsync(self):
        sincronizadas = []
        fsync_real = d._fsync_directorio
        retirar_real = d.eliminar_fuentes_validadas

        def sync(path):
            sincronizadas.append(Path(path))
            return fsync_real(path)

        def retirar(*args):
            meta = json.loads(self.manifest.read_text())
            self.assertIn(self.salida.parent, sincronizadas)
            self.assertIn(self.manifest.parent, sincronizadas)
            self.assertEqual(meta["salida"]["sha256"], d.sha256_archivo(self.salida))
            self.assertEqual(meta["retiro_transitorios_prevalidado"]["fuentes"], [str(self.fuente)])
            self.assertEqual(meta["fuentes"][0]["sha256"], d.sha256_archivo(self.fuente))
            self.verificar_respaldo()
            return retirar_real(*args)

        with patch.object(d, "_fsync_directorio", side_effect=sync), patch.object(
            d, "eliminar_fuentes_validadas", side_effect=retirar,
        ):
            liberados = self.publicar()
        self.assertGreater(liberados, 0)
        self.assertFalse(self.fuente.exists())
        registro = self.verificar_respaldo()
        meta = json.loads(self.manifest.read_text())
        self.assertEqual(meta["validacion"]["horas"], 216)
        self.assertTrue(meta["fuentes_eliminadas_despues_de_validar"])
        self.assertEqual(meta["respaldo_publicacion_previa"]["sha256"], d.sha256_archivo(registro))
        with xr.open_dataset(self.salida) as nuevo, xr.open_dataset(registro.parent / self.salida.name) as previo:
            for v in self.variables:
                np.testing.assert_array_equal(nuevo[v][:192], previo[v])

    def test_fallo_normalizacion_conserva_pareja_previa_y_fuente(self):
        with patch.object(d, "normalizar_mes", side_effect=RuntimeError("normalizar")):
            with self.assertRaisesRegex(RuntimeError, "normalizar"):
                self.publicar()
        self.assertEqual(self.salida.read_bytes(), self.prev_salida)
        self.assertEqual(self.manifest.read_bytes(), self.prev_manifest)
        self.assert_fuente_conservada()
        self.verificar_respaldo()

    def test_fallo_anotacion_conserva_respaldo_y_fuente(self):
        with patch.object(d, "_anotar_descarga", side_effect=RuntimeError("anotar")):
            with self.assertRaisesRegex(RuntimeError, "anotar"):
                self.publicar()
        self.assert_fuente_conservada()
        self.verificar_respaldo()

    def test_fallo_replace_salida_no_pierde_pareja_previa(self):
        real = motor.os.replace

        def reemplazar(src, dst):
            if Path(dst) == self.salida:
                raise OSError("replace salida")
            return real(src, dst)

        with patch.object(motor.os, "replace", side_effect=reemplazar):
            with self.assertRaisesRegex(OSError, "replace salida"):
                self.publicar()
        self.assertEqual(self.salida.read_bytes(), self.prev_salida)
        self.assertEqual(self.manifest.read_bytes(), self.prev_manifest)
        self.assert_fuente_conservada()
        self.verificar_respaldo()

    def test_fallo_manifest_despues_replace_conserva_respaldo_y_crudo(self):
        real = motor._escribir_json_atomico

        def escribir(path, meta):
            if Path(path) == self.manifest:
                raise OSError("manifest")
            return real(path, meta)

        with patch.object(motor, "_escribir_json_atomico", side_effect=escribir):
            with self.assertRaisesRegex(OSError, "manifest"):
                self.publicar()
        self.assertNotEqual(self.salida.read_bytes(), self.prev_salida)
        self.assertEqual(self.manifest.read_bytes(), self.prev_manifest)
        self.assert_fuente_conservada()
        self.verificar_respaldo()

    def test_fallo_cleanup_no_dispara_borrado_al_salir(self):
        with patch.object(d, "eliminar_fuentes_validadas", side_effect=RuntimeError("cleanup")):
            with self.assertRaisesRegex(RuntimeError, "cleanup"):
                self.publicar()
        self.assert_fuente_conservada()
        self.verificar_respaldo()

    def test_reentrada_tras_anotacion_fallida_no_omite_y_completa(self):
        with patch.object(d, "_anotar_descarga", side_effect=RuntimeError("anotar")):
            with self.assertRaises(RuntimeError):
                self.publicar()
        self.assertFalse(d._salida_ya_valida(
            self.raiz, self.periodo, self.variables, 216, True,
        ))
        self.assert_fuente_conservada()
        self.publicar()
        self.assertTrue(d._salida_ya_valida(
            self.raiz, self.periodo, self.variables, 216, True,
        ))
        self.assertFalse(self.fuente.exists())
        self.assertEqual(len(list((self.raiz / "_respaldos_publicacion").rglob("respaldo.json"))), 2)

    def test_reentrada_tras_retiro_fallido_no_omite_y_completa(self):
        with patch.object(d, "eliminar_fuentes_validadas", side_effect=RuntimeError("retiro")):
            with self.assertRaises(RuntimeError):
                self.publicar()
        self.assertFalse(d._salida_ya_valida(
            self.raiz, self.periodo, self.variables, 216, True,
        ))
        self.publicar()
        self.assertTrue(d._salida_ya_valida(
            self.raiz, self.periodo, self.variables, 216, True,
        ))
        self.assertFalse(self.fuente.exists())

    def test_gate_no_exige_retiro_de_legados_anteriores(self):
        self.fuente.unlink()
        d._anotar_descarga(self.manifest, [{"fuente_reutilizada": "legado.nc"}],
                          pd.Timestamp("2026-09-08", tz="UTC"))
        self.assertFalse(json.loads(self.manifest.read_text())["fuentes_eliminadas_despues_de_validar"])
        self.assertTrue(d._salida_ya_valida(
            self.raiz, self.periodo, self.variables, 192, True,
        ))

    def test_gate_sin_anotacion_no_omite_aunque_no_haya_staging(self):
        self.fuente.unlink()
        self.assertFalse(d._salida_ya_valida(
            self.raiz, self.periodo, self.variables, 192, True,
        ))

    def test_gate_con_part_pendiente_no_declara_completo(self):
        self.publicar()
        parcial = self.fuente.with_name(f"{self.fuente.stem}.part.nc")
        parcial.write_bytes(b"parcial por revisar")
        self.assertFalse(d._salida_ya_valida(
            self.raiz, self.periodo, self.variables, 216, True,
        ))
        self.assertEqual(parcial.read_bytes(), b"parcial por revisar")

    def test_fallo_fsync_manifest_impide_retiro(self):
        real = d._fsync_directorio

        def sync(path):
            if Path(path) == self.manifest.parent:
                raise OSError("durabilidad")
            return real(path)

        with patch.object(d, "_fsync_directorio", side_effect=sync), patch.object(
            d, "eliminar_fuentes_validadas",
        ) as retirar:
            with self.assertRaisesRegex(OSError, "durabilidad"):
                self.publicar()
        retirar.assert_not_called()
        self.assert_fuente_conservada()
        self.verificar_respaldo()

    def test_fallo_copia_respaldo_impide_reemplazo(self):
        with patch.object(d.shutil, "copyfileobj", side_effect=OSError("respaldo")), patch.object(
            d, "normalizar_mes",
        ) as normalizar:
            with self.assertRaisesRegex(OSError, "respaldo"):
                self.publicar()
        normalizar.assert_not_called()
        self.assertEqual(self.salida.read_bytes(), self.prev_salida)
        self.assertEqual(self.manifest.read_bytes(), self.prev_manifest)
        self.assert_fuente_conservada()

    def test_limpieza_solo_libera_lock_y_conserva_completos_y_part(self):
        parcial = self.fuente.with_suffix(".part.nc")
        parcial.write_bytes(b"datos por revisar")
        lock = self.tmp / "lock"
        lock.write_text(str(d.os.getpid()))
        d._LOCK_ACTIVO = lock
        d._CRUDOS_TRANSITORIOS.add(self.fuente)
        d._PARCIALES_ACTIVOS.add(parcial)
        d._limpiar_recursos()
        self.assertFalse(lock.exists())
        self.assertTrue(self.fuente.exists())
        self.assertEqual(parcial.read_bytes(), b"datos por revisar")

    def pedir(self, cliente):
        return d.pedir(cliente, {}, self.fuente, d.VARS_LAND, 216, self.periodo,
                       [-33., -70., -33.1, -69.9], 100)

    def test_fuente_preexistente_invalida_no_se_borra_ni_reemplaza(self):
        previo = self.fuente.read_bytes()
        cliente = Mock()
        with patch.object(d, "asegurar_espacio"), patch.object(
            d, "validar_netcdf", side_effect=ValueError("horas"),
        ):
            with self.assertRaisesRegex(RuntimeError, "se conserva"):
                self.pedir(cliente)
        cliente.retrieve.assert_not_called()
        self.assertEqual(self.fuente.read_bytes(), previo)

    def test_parcial_preexistente_no_validable_se_conserva(self):
        self.fuente.unlink()
        parcial = self.fuente.with_name(f"{self.fuente.stem}.part.nc")
        parcial.write_bytes(b"parcial")
        cliente = Mock()
        with patch.object(d, "asegurar_espacio"), patch.object(
            d, "validar_netcdf", side_effect=ValueError("parcial"),
        ):
            with self.assertRaisesRegex(ValueError, "parcial"):
                self.pedir(cliente)
        cliente.retrieve.assert_not_called()
        self.assertEqual(parcial.read_bytes(), b"parcial")

    def test_descarga_que_falla_conserva_su_parcial(self):
        self.fuente.unlink()
        cliente = Mock()

        def descargar(_dataset, _request, destino):
            Path(destino).write_bytes(b"descarga interrumpida")
            raise KeyboardInterrupt()

        cliente.retrieve.side_effect = descargar
        with patch.object(d, "asegurar_espacio"), redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                self.pedir(cliente)
        parcial = self.fuente.with_name(f"{self.fuente.stem}.part.nc")
        self.assertEqual(parcial.read_bytes(), b"descarga interrumpida")
        d._limpiar_recursos()
        self.assertTrue(parcial.exists())

    def test_parcial_completa_reutilizable_sin_descargar(self):
        previo = self.fuente.read_bytes()
        parcial = self.fuente.with_name(f"{self.fuente.stem}.part.nc")
        self.fuente.rename(parcial)
        cliente = Mock()
        with patch.object(d, "asegurar_espacio"), patch.object(d, "validar_netcdf"):
            self.assertEqual(self.pedir(cliente), self.fuente)
        cliente.retrieve.assert_not_called()
        self.assertEqual(self.fuente.read_bytes(), previo)

    def test_main_error_con_aois_listos_no_borra_fuente(self):
        aoi = SimpleNamespace(id="continente", territorio="continental")
        with ExitStack() as stack, redirect_stdout(io.StringIO()):
            for name, value in {"CONT": self.tmp, "LEGADO": self.tmp / "legacy",
                                "RAIZ_SALIDA": self.raiz}.items():
                stack.enter_context(patch.object(d, name, value))
            stack.enter_context(patch.object(sys, "argv", ["descargar_era5land.py", "--desde", "2000-01", "--hasta", "2000-01"]))
            stack.enter_context(patch.object(d, "_activar_limpieza"))
            stack.enter_context(patch.object(d, "crear_catalogos", return_value=(self.catalogo, self.relacion, self.cat_manifest)))
            stack.enter_context(patch.object(d, "_cargar_aois", return_value=[aoi]))
            stack.enter_context(patch.object(d, "_area_cds", return_value=[-33., -70., -33.1, -69.9]))
            stack.enter_context(patch.object(d, "_salida_ya_valida", return_value=False))
            stack.enter_context(patch.object(d, "_otros_descargadores_python", return_value=[]))
            stack.enter_context(patch("cdsapi.Client"))
            stack.enter_context(patch.object(d, "pedir", return_value=self.fuente))
            stack.enter_context(patch.object(d, "_publicar_mes_seguro", side_effect=RuntimeError("publicar")))
            with self.assertRaisesRegex(RuntimeError, "publicar"):
                d.main()
        self.assert_fuente_conservada()


if __name__ == "__main__":
    unittest.main()
