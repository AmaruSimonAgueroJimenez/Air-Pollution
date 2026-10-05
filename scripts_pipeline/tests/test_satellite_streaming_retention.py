from __future__ import annotations

import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _satellite_streaming import AreaTrabajo, escribir_json_atomico


class RetencionFuentesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "producto" / "trabajo"

    def fuente(self, fecha="2026-09-11"):
        p = self.root / "aqua" / fecha / "fuente.hdf"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fuente-unica")
        return p

    def test_preserva_inicio_reentrada_dia_y_salida_normal(self):
        src = self.fuente()
        with AreaTrabajo(self.root, preservar_no_validados=True) as area:
            self.assertEqual(area.carpeta_dia("2026-09-11", "aqua"), src.parent.resolve())
            self.assertEqual(src.read_bytes(), b"fuente-unica")
            area.carpeta_dia("2026-09-11", "aqua")
            self.assertTrue(src.exists())
        self.assertTrue(src.exists())

    def test_preserva_ante_error_y_restaura_senales(self):
        src = self.fuente()
        prev = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        with self.assertRaisesRegex(OSError, "persistencia"):
            with AreaTrabajo(self.root, preservar_no_validados=True):
                raise OSError("persistencia")
        self.assertTrue(src.exists())
        self.assertEqual(prev, {s: signal.getsignal(s) for s in prev})

    def test_preserva_ante_senal(self):
        src = self.fuente()
        prev = signal.getsignal(signal.SIGTERM)
        with self.assertRaises(KeyboardInterrupt):
            with AreaTrabajo(self.root, preservar_no_validados=True) as area:
                area._interrumpir(signal.SIGTERM, None)
        self.assertTrue(src.exists())
        self.assertEqual(signal.getsignal(signal.SIGTERM), prev)

    def test_retira_solo_dia_explicitamente_validado(self):
        src = self.fuente()
        otro = self.fuente("2026-09-12")
        with AreaTrabajo(self.root, preservar_no_validados=True) as area:
            area.limpiar_dia(src.parent)
            area.limpiar_dia(src.parent)  # retirada idempotente
        self.assertFalse(src.exists())
        self.assertTrue(otro.exists())

    def test_fallo_limpieza_no_se_oculta_ni_se_reintenta_al_salir(self):
        src = self.fuente()
        with AreaTrabajo(self.root, preservar_no_validados=True) as area:
            with patch("_satellite_streaming.shutil.rmtree", side_effect=PermissionError("disco")) as rm:
                with self.assertRaises(PermissionError):
                    area.limpiar_dia(src.parent)
                rm.assert_called_once()
        self.assertTrue(src.exists())

    def test_rechaza_limpieza_global_y_fuera_del_area(self):
        src = self.fuente()
        with AreaTrabajo(self.root, preservar_no_validados=True) as area:
            for accion in (area.limpiar, lambda: area.limpiar_dia(self.root),
                           lambda: area.limpiar_dia(self.root.parent)):
                with self.assertRaises(ValueError):
                    accion()
        self.assertTrue(src.exists())

    def test_rechaza_raiz_amplia_tambien_en_modo_retencion(self):
        with self.assertRaises(ValueError):
            with AreaTrabajo(Path("/"), preservar_no_validados=True):
                self.fail("raiz insegura aceptada")

    def test_modo_heredado_no_cambia(self):
        anterior = self.fuente()
        with AreaTrabajo(self.root) as area:
            self.assertFalse(anterior.exists())
            dia = area.carpeta_dia("2026-09-11", "aqua")
            nuevo = dia / "nuevo.hdf"
            nuevo.write_bytes(b"temporal")
        self.assertFalse(nuevo.exists())

    def test_json_persiste_archivo_y_directorio(self):
        import os
        import json
        destino = self.root / "auditoria.json"
        with patch("_satellite_streaming.os.fsync", wraps=os.fsync) as sync:
            escribir_json_atomico({"crudo_eliminado": False}, destino)
        self.assertEqual(sync.call_count, 2)
        self.assertFalse(json.loads(destino.read_text())["crudo_eliminado"])

    def test_fallo_fsync_directorio_se_propaga_sin_borrar_fuente(self):
        src = self.fuente()
        with AreaTrabajo(self.root, preservar_no_validados=True):
            with patch("_satellite_streaming.os.fsync", side_effect=[None, OSError("directorio")]):
                with self.assertRaisesRegex(OSError, "directorio"):
                    escribir_json_atomico({"crudo_eliminado": False}, self.root / "wal.json")
        self.assertTrue(src.exists())


if __name__ == "__main__":
    unittest.main()
