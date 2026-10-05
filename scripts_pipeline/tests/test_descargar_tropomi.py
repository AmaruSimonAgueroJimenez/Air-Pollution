from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import descargar_tropomi as tropomi  # noqa: E402
from _chile_aoi import AOI  # noqa: E402


class _ManifiestoGrabador:
    def __init__(self, fuente: Path, falla_evento: str | None = None):
        self.fuente = fuente
        self.falla_evento = falla_evento
        self.llamadas: list[tuple[str, bool, dict]] = []

    def registrar(self, datos: dict) -> None:
        self.llamadas.append((datos["evento"], self.fuente.exists(), datos))
        if datos["evento"] == self.falla_evento:
            raise OSError("fsync sintético")

    def archivo(self, **datos) -> None:
        self.llamadas.append(("archivo_validado", self.fuente.exists(), datos))


class WriteAheadTropomiTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="tropomi-wal-test-")
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.destino = self.raiz / "salidas"
        self.destino.mkdir()
        self.src = self.raiz / "S5P_granulo.nc"
        self.src.write_bytes(b"fuente sintetica")
        self.out = self.destino / "S5P_granulo.continente.chile.nc"
        self.out.write_bytes(b"salida sintetica validada")
        self.aoi = AOI("continente", "continental", (-75.0, -56.0, -66.0, -17.0))

    def _procesar(self, mani: _ManifiestoGrabador, *, salida=True):
        with patch.object(
                tropomi, "recortar", return_value=self.out if salida else None), \
                patch.object(tropomi, "validar_recorte",
                             return_value={"pixeles_chile": 17}), \
                patch.object(tropomi, "_variables_salida",
                             return_value=["PRODUCT/no2", "PRODUCT/qa_value"]):
            return tropomi._procesar(
                self.src,
                self.destino,
                (self.aoi,),
                pol="no2",
                comunas=self.raiz / "comunas.shp",
                mascara_sha256="m" * 64,
                conservar_global=False,
                mani=mani,
                url="https://example.test/granulo.nc?token=secreto",
                temporal=True,
            )

    def test_wal_durable_precede_borrado_y_archivo_validado_sigue_compatible(self):
        mani = _ManifiestoGrabador(self.src)
        checksum_salida = tropomi.sha256(self.out)

        resultado = self._procesar(mani)

        self.assertEqual(resultado, [self.out])
        self.assertFalse(self.src.exists())
        self.assertEqual([x[0] for x in mani.llamadas], [
            "granulo_validado_pre_borrado",
            "crudo_eliminado_post_validacion",
            "archivo_validado",
        ])
        wal = mani.llamadas[0]
        self.assertTrue(wal[1], "el WAL debe persistirse con el crudo presente")
        self.assertFalse(wal[2]["crudo_eliminado"])
        self.assertEqual(wal[2]["version"], tropomi.VERSION)
        self.assertEqual(wal[2]["resultados_aoi"][0]["aoi_id"], "continente")
        self.assertEqual(wal[2]["resultados_aoi"][0]["pixeles_chile"], 17)
        self.assertEqual(wal[2]["resultados_aoi"][0]["sha256_salida"],
                         checksum_salida)
        self.assertFalse(mani.llamadas[1][1],
                         "el evento posterior sólo puede afirmar el borrado después")
        self.assertTrue(mani.llamadas[1][2]["crudo_eliminado"])
        self.assertTrue(mani.llamadas[2][2]["crudo_eliminado"])
        self.assertEqual(mani.llamadas[2][2]["checksum_fuente"],
                         wal[2]["sha256_fuente"])

    def test_falla_de_fsync_del_wal_impide_borrado(self):
        mani = _ManifiestoGrabador(
            self.src, falla_evento="granulo_validado_pre_borrado")

        with self.assertRaisesRegex(OSError, "fsync sintético"):
            self._procesar(mani)

        self.assertTrue(self.src.exists())
        self.assertNotIn("crudo_eliminado_post_validacion",
                         [x[0] for x in mani.llamadas])
        fallo = next(x[2] for x in mani.llamadas if x[0] == "archivo_fallido")
        self.assertFalse(fallo["wal_pre_borrado_persistido"])
        self.assertTrue(fallo["crudo_preservado"])

    def test_falla_al_construir_hash_de_salida_impide_borrado(self):
        mani = _ManifiestoGrabador(self.src)
        hash_real = tropomi.sha256

        def hash_con_falla(path):
            if Path(path) == self.out:
                raise ValueError("hash de salida sintético")
            return hash_real(path)

        with patch.object(tropomi, "sha256", side_effect=hash_con_falla), \
                self.assertRaisesRegex(ValueError, "hash de salida sintético"):
            self._procesar(mani)

        self.assertTrue(self.src.exists())
        self.assertNotIn("granulo_validado_pre_borrado",
                         [x[0] for x in mani.llamadas])
        self.assertNotIn("crudo_eliminado_post_validacion",
                         [x[0] for x in mani.llamadas])

    def test_aoi_sin_pixeles_tambien_queda_en_wal_antes_de_borrar(self):
        mani = _ManifiestoGrabador(self.src)

        resultado = self._procesar(mani, salida=False)

        self.assertEqual(resultado, [])
        self.assertFalse(self.src.exists())
        self.assertEqual([x[0] for x in mani.llamadas], [
            "granulo_validado_pre_borrado",
            "crudo_eliminado_post_validacion",
            "aoi_sin_pixeles",
        ])
        wal = mani.llamadas[0]
        self.assertTrue(wal[1])
        self.assertEqual(wal[2]["resultados_aoi"], [{
            "resultado": "aoi_sin_pixeles",
            "aoi_id": "continente",
            "territorio": "continental",
            "bbox": tuple(tropomi._bbox(self.aoi)),
        }])
        self.assertFalse(wal[2]["crudo_eliminado"])
        self.assertFalse(mani.llamadas[1][1])
        self.assertTrue(mani.llamadas[2][2]["crudo_eliminado"])


if __name__ == "__main__":
    unittest.main()
