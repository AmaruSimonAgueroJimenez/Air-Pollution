from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import descargar_nightlights as nightlights  # noqa: E402
import _manifiesto_satelital as manifiestos  # noqa: E402
from _chile_aoi import AOI  # noqa: E402


class _ManifiestoGrabador:
    def __init__(self, fuente: Path, falla_evento: str | None = None):
        self.fuente = fuente
        self.falla_evento = falla_evento
        self.llamadas: list[tuple[str, bool, dict]] = []

    def registrar(self, datos: dict) -> None:
        self.llamadas.append((datos["evento"], self.fuente.exists(), datos))
        if datos["evento"] == self.falla_evento or self.falla_evento == "*":
            raise OSError("fsync sintético")

    def archivo(self, **datos) -> None:
        self.llamadas.append(("archivo_validado", self.fuente.exists(), datos))
        if self.falla_evento == "archivo_validado":
            raise OSError("evento final sintético")

    def terminar(self, estado="completo", **datos) -> None:
        self.registrar({"evento": "fin", "estado": estado, **datos})


class WriteAheadNightlightsTests(unittest.TestCase):
    def setUp(self):
        temporal = tempfile.TemporaryDirectory(prefix="nightlights-wal-test-")
        self.addCleanup(temporal.cleanup)
        self.raiz = Path(temporal.name)
        self.destino = self.raiz / "salidas"
        self.destino.mkdir()
        self.src = self.raiz / "VNP46A1.A2020001.h10v11.002.2020010000000.h5"
        self.src.write_bytes(b"fuente sintetica")
        self.out = self.destino / "VNP46A1.continente.chile.h5"
        self.out.write_bytes(b"salida sintetica validada")
        self.aoi = AOI("continente", "continental", (-75.0, -56.0, -66.0, -17.0))
        self.comunas = self.raiz / "comunas.shp"
        self.comunas.write_bytes(b"mascara sintetica")

    def _procesar(self, mani, *, salida=True, error_recorte=None,
                  conservar=False):
        with patch.object(nightlights, "recortar_viirs_black_marble",
                          return_value=self.out if salida else None,
                          side_effect=error_recorte), \
                patch.object(nightlights, "_pixeles", return_value=17), \
                patch.object(nightlights, "_variables",
                             return_value=["UTC_Time", "QF_DNB"]):
            return nightlights._procesar(
                self.src, self.destino, (self.aoi,), short="VNP46A1",
                version="2", temporal_nativo="per_pixel_UTC_Time; native overpass",
                comunas=self.comunas, mascara_sha256="m" * 64,
                conservar_crudo=conservar, mani=mani,
                url="https://example.test/granulo.h5?token=secreto",
                es_temporal=True,
            )

    def _manifiesto_real(self):
        # Evita construir runtime, consultar credenciales o tocar producción.
        mani = manifiestos.Manifiesto.__new__(manifiestos.Manifiesto)
        mani.producto = "VNP46A1"
        mani.execution_id = "prueba-aislada"
        mani.path = self.raiz / "manifiesto.jsonl"
        return mani

    def test_wal_precede_borrado_y_conserva_eventos_finales(self):
        mani = _ManifiestoGrabador(self.src)
        fuente_sha = nightlights.sha256(self.src)
        salida_sha = nightlights.sha256(self.out)

        self.assertEqual(self._procesar(mani), [self.out])

        self.assertFalse(self.src.exists())
        self.assertTrue(self.out.exists())
        self.assertEqual([x[0] for x in mani.llamadas], [
            "granulo_validado_pre_borrado",
            "crudo_eliminado_post_validacion", "archivo_validado",
        ])
        wal = mani.llamadas[0][2]
        self.assertTrue(mani.llamadas[0][1])
        self.assertFalse(wal["crudo_eliminado"])
        self.assertEqual(wal["version"], "2")
        self.assertEqual(wal["sha256_fuente"], fuente_sha)
        self.assertEqual(wal["bytes_fuente"], len(b"fuente sintetica"))
        self.assertEqual(wal["mascara_sha256"], "m" * 64)
        self.assertEqual(wal["url"], "https://example.test/granulo.h5")
        resultado = wal["resultados_aoi"][0]
        self.assertEqual(resultado["aoi_id"], "continente")
        self.assertEqual(resultado["bbox"], self.aoi.bbox)
        self.assertEqual(resultado["pixeles_chile"], 17)
        self.assertEqual(resultado["variables_conservadas"], ["UTC_Time", "QF_DNB"])
        self.assertEqual(resultado["sha256_salida"], salida_sha)
        self.assertFalse(mani.llamadas[1][1])
        self.assertTrue(mani.llamadas[1][2]["crudo_eliminado"])
        self.assertTrue(mani.llamadas[2][2]["crudo_eliminado"])
        self.assertEqual(mani.llamadas[2][2]["checksum_fuente"], fuente_sha)

    def test_registro_real_se_sincroniza_con_fuente_aun_presente(self):
        mani = self._manifiesto_real()
        fuente_presente = []
        fsync_real = manifiestos.os.fsync

        def fsync_observado(fd):
            fuente_presente.append(self.src.exists())
            fsync_real(fd)

        with patch.object(manifiestos.os, "fsync", side_effect=fsync_observado):
            self._procesar(mani)

        registros = [json.loads(x) for x in mani.path.read_text().splitlines()]
        self.assertEqual(fuente_presente, [True, False, False])
        self.assertEqual(registros[0]["evento"], "granulo_validado_pre_borrado")
        self.assertEqual(registros[-1]["evento"], "archivo_validado")

    def test_falla_real_de_fsync_conserva_fuente_y_excepcion_original(self):
        mani = self._manifiesto_real()
        with patch.object(manifiestos.os, "fsync",
                          side_effect=OSError("fsync real sintético")), \
                self.assertRaisesRegex(OSError, "fsync real sintético"):
            self._procesar(mani)

        self.assertTrue(self.src.exists())
        registros = [json.loads(x) for x in mani.path.read_text().splitlines()]
        self.assertNotIn("crudo_eliminado_post_validacion",
                         [x["evento"] for x in registros])

    def test_falla_del_wal_impide_borrado_y_registra_fuente_preservada(self):
        mani = _ManifiestoGrabador(self.src, "granulo_validado_pre_borrado")
        with self.assertRaisesRegex(OSError, "fsync sintético"):
            self._procesar(mani)

        self.assertTrue(self.src.exists())
        fallo = next(x[2] for x in mani.llamadas if x[0] == "archivo_fallido")
        self.assertFalse(fallo["wal_pre_borrado_persistido"])
        self.assertTrue(fallo["crudo_preservado"])
        self.assertFalse(fallo["crudo_temporal_descartado"])

    def test_falla_al_construir_hash_de_salida_impide_borrado(self):
        mani = _ManifiestoGrabador(self.src)
        hash_real = nightlights.sha256

        def hash_con_falla(path):
            if Path(path) == self.out:
                raise ValueError("hash de salida sintético")
            return hash_real(path)

        with patch.object(nightlights, "sha256", side_effect=hash_con_falla), \
                self.assertRaisesRegex(ValueError, "hash de salida sintético"):
            self._procesar(mani)

        self.assertTrue(self.src.exists())
        self.assertNotIn("granulo_validado_pre_borrado",
                         [x[0] for x in mani.llamadas])

    def test_falla_de_recorte_preserva_fuente_aunque_falle_registrar_error(self):
        mani = _ManifiestoGrabador(self.src, "*")
        with self.assertRaisesRegex(ValueError, "recorte sintético"):
            self._procesar(mani, error_recorte=ValueError("recorte sintético"))
        self.assertTrue(self.src.exists())

    def test_evento_posterior_fallido_deja_wal_y_flags_honestos(self):
        mani = _ManifiestoGrabador(self.src, "crudo_eliminado_post_validacion")
        with self.assertRaisesRegex(OSError, "fsync sintético"):
            self._procesar(mani)
        self.assertFalse(self.src.exists())
        self.assertTrue(self.out.exists())
        fallo = mani.llamadas[-1][2]
        self.assertTrue(fallo["wal_pre_borrado_persistido"])
        self.assertFalse(fallo["crudo_preservado"])
        self.assertTrue(fallo["crudo_temporal_descartado"])

    def test_evento_final_fallido_conserva_trazabilidad_wal(self):
        mani = _ManifiestoGrabador(self.src, "archivo_validado")
        with self.assertRaisesRegex(OSError, "evento final sintético"):
            self._procesar(mani)
        self.assertFalse(self.src.exists())
        self.assertTrue(mani.llamadas[-1][2]["wal_pre_borrado_persistido"])
        self.assertTrue(self.out.exists())

    def test_aoi_vacio_queda_en_wal_y_evento_final(self):
        mani = _ManifiestoGrabador(self.src)
        self.assertEqual(self._procesar(mani, salida=False), [])
        self.assertFalse(self.src.exists())
        self.assertEqual([x[0] for x in mani.llamadas], [
            "granulo_validado_pre_borrado",
            "crudo_eliminado_post_validacion", "aoi_sin_pixeles",
        ])
        resultado = mani.llamadas[0][2]["resultados_aoi"][0]
        self.assertEqual(resultado["resultado"], "aoi_sin_pixeles")
        self.assertEqual(resultado["aoi_id"], "continente")
        self.assertEqual(resultado["pixeles_chile"], 0)
        self.assertTrue(mani.llamadas[-1][2]["crudo_eliminado"])

    def test_aoi_no_cruza_queda_en_wal_sin_inventar_archivo_o_vacio(self):
        mani = _ManifiestoGrabador(self.src)
        self.assertEqual(self._procesar(
            mani, error_recorte=ValueError("tile no cruza AOI")), [])
        self.assertFalse(self.src.exists())
        self.assertEqual([x[0] for x in mani.llamadas], [
            "granulo_validado_pre_borrado", "crudo_eliminado_post_validacion",
        ])
        resultado = mani.llamadas[0][2]["resultados_aoi"][0]
        self.assertEqual(resultado["resultado"], "aoi_no_cruza")
        self.assertEqual(resultado["bbox"], self.aoi.bbox)

    def test_conservar_crudo_no_genera_eventos_de_borrado(self):
        mani = _ManifiestoGrabador(self.src)
        self._procesar(mani, conservar=True)
        self.assertTrue(self.src.exists())
        self.assertEqual([x[0] for x in mani.llamadas], ["archivo_validado"])
        self.assertFalse(mani.llamadas[0][2]["crudo_eliminado"])

    def test_except_principal_no_borra_fuente_preservada_por_procesar(self):
        base = self.raiz / "contaminantes"
        fuente_descargada = base / "Nightlights" / "VNP46A1" / "_tmp_tiles" / self.src.name
        mani = _ManifiestoGrabador(fuente_descargada)
        granulo = SimpleNamespace(data_links=lambda: [
            "https://example.test/" + self.src.name,
        ])

        def download(_granulos, destino):
            fuente = Path(destino) / self.src.name
            fuente.write_bytes(b"descarga sintetica sin red")
            return [fuente]

        earthaccess = SimpleNamespace(search_data=lambda **_kw: [granulo],
                                      download=download)
        with patch.dict(sys.modules, {"earthaccess": earthaccess}), \
                patch.object(nightlights, "CONTAMINANTES", base), \
                patch.object(nightlights, "seleccionar", return_value=(self.aoi,)), \
                patch.object(nightlights, "login"), \
                patch.object(nightlights, "resumen_mascara", return_value={}), \
                patch.object(nightlights, "sha256_conjunto_shapefile", return_value="m" * 64), \
                patch.object(nightlights, "Manifiesto", return_value=mani), \
                patch.object(nightlights, "_exigir_reserva_espacio"), \
                patch.object(nightlights, "_procesar", side_effect=OSError("WAL sintético")), \
                self.assertRaises(SystemExit) as error:
            nightlights.main([
                "--producto", "a1", "--desde", "2020-01-01",
                "--hasta", "2020-01-01", "--comunas", str(self.comunas),
                "--no-auditar-legado",
            ])

        self.assertEqual(error.exception.code, 1)
        self.assertTrue(fuente_descargada.exists())
        eventos = [x[0] for x in mani.llamadas]
        self.assertIn("temporal_descarga_fallida_preservado", eventos)
        self.assertNotIn("temporal_descarga_fallida_eliminado", eventos)
        self.assertEqual(mani.llamadas[-1][2]["estado"], "con_fallos")


if __name__ == "__main__":
    unittest.main()
