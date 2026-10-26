"""Pruebas sin red de descargar_sinca_meteorologia.py (fuentes sintéticas)."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib
import json
import os
import sys
import tempfile
import unittest
from collections import namedtuple
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
_TMP_DATA = tempfile.TemporaryDirectory()
_ENV_PREVIO = os.environ.get("AIR_POLLUTION_DATA_ROOT")
_COMMON_PREVIO = sys.modules.pop("_common", None)
os.environ["AIR_POLLUTION_DATA_ROOT"] = _TMP_DATA.name
sys.path.insert(0, str(SCRIPTS))
try:
    # Raíz de datos temporal: la prueba jamás toca el disco externo.
    smet = importlib.import_module("descargar_sinca_meteorologia")
finally:
    if _ENV_PREVIO is None:
        os.environ.pop("AIR_POLLUTION_DATA_ROOT", None)
    else:
        os.environ["AIR_POLLUTION_DATA_ROOT"] = _ENV_PREVIO
    # Otros módulos de prueba no deben heredar la raíz temporal.
    if _COMMON_PREVIO is not None:
        sys.modules["_common"] = _COMMON_PREVIO
    else:
        sys.modules.pop("_common", None)

FICHA = """<html><body><table>
<tr class="serie odd"><th colspan="2"><span><a name="PM25">PM2,5</a></span><br />(PM2,5 - µg/m³)</th>
<td>horario</td><td>S/I</td><td>01-01-2010</td><td>01-09-2026</td><td>BAM</td>
<td><a href="//x/apub.htmlindico2.cgi?page=pageFrame&amp;macropath=./RM/D14/Cal/PM25&amp;macro=PM25.horario.horario&amp;from=100101&amp;to=260901&amp;">g</a></td></tr>
<tr class="serie odd"><th colspan="2"><span><a name="TEMP">Temperatura ambiente</a></span><br />(Temperatura - °C)</th>
<td class="center">horario</td><td class="center">3 m</td><td>15-12-2003</td><td>02-09-2026</td>
<td class="helpTecnica center">SENSOR MET ONE HMP35A</td>
<td><a class="iframe" href="//x/apub.htmlindico2.cgi?page=pageFrame&amp;header=P&amp;macropath=./RM/D14/Met/TEMP&amp;macro=horario_003&amp;from=031215&amp;to=260902&amp;">g</a></td></tr>
<tr class="serie even"><th colspan="2"><span><a name="WDIR">Dirección del viento</a></span><br />(Dir. viento - °)</th>
<td>horario</td><td>10 m</td><td>15-12-2003</td><td>02-09-2026</td><td>SENSOR - MET ONE 020C</td>
<td><a href="//x/apub.htmlindico2.cgi?page=pageFrame&amp;macropath=./RM/D14/Met/WDIR&amp;macro=horario_010&amp;from=031215&amp;to=260902&amp;">g</a></td></tr>
<tr class="serie even"><th colspan="2"><span><a name="GLOB">Radiación</a></span><br />(Radiación - W/m²)</th>
<td>horario</td><td>2 m</td><td>15-12-2003</td><td>02-09-2026</td><td>PIRANOMETRO</td>
<td><a href="//x/apub.htmlindico2.cgi?page=pageFrame&amp;macropath=./RM/D14/Met/GLOB&amp;macro=horario_002&amp;from=031215&amp;to=260902&amp;">g</a></td></tr>
</table></body></html>"""


def serie_horaria(desde: str, hasta: str, valor="12,5", vacios=()) -> str:
    """Imita la forma del exportador: 01:00 del primer día a 23:00 del último."""
    marca = datetime.fromisoformat(desde) + timedelta(hours=1)
    fin = datetime.fromisoformat(hasta) + timedelta(hours=23)
    filas = ["FECHA (YYMMDD);HORA (HHMM);;"]
    while marca <= fin:
        clave = marca.strftime("%y%m%d;%H%M")
        filas.append(f"{clave};{'' if clave in vacios else valor};")
        marca += timedelta(hours=1)
    return "\n".join(filas) + "\n"


ROSA = "FECHA (YYMMDD);HORA (HHMM);;\n352,5-7,58,7%\n7,5-22,54,3%\n"


class FichaTest(unittest.TestCase):
    def test_solo_series_meteorologicas_pedidas(self):
        series = smet.parsear_ficha(FICHA, "RM", "D14")
        self.assertEqual([(s["parametro"], s["macro_ficha"]) for s in series],
                         [("TEMP", "horario_003"), ("WDIR", "horario_010")])
        temp = series[0]
        self.assertEqual(temp["unidad_ficha"], "°C")
        self.assertEqual(temp["altura_ficha"], "3 m")
        self.assertEqual(temp["instrumento_ficha"], "SENSOR MET ONE HMP35A")
        self.assertEqual((temp["desde_ficha"], temp["hasta_ficha"]), ("031215", "260902"))

    def test_otra_estacion_no_se_mezcla(self):
        self.assertEqual(smet.parsear_ficha(FICHA, "RM", "D15"), [])

    def test_macro_wdir_usa_serie_de_tiempo(self):
        self.assertEqual(smet.macro_exportacion("RM", "D14", "WDIR", "horario_010"),
                         "./RM/D14/Met/WDIR//horario_010_spec.ic")
        self.assertEqual(smet.macro_exportacion("RM", "D14", "TEMP", "horario_003"),
                         "./RM/D14/Met/TEMP//horario_003.ic")


class RespuestaTest(unittest.TestCase):
    def test_serie_completa(self):
        texto = serie_horaria("2026-01-01", "2026-01-02", vacios={"260101;0500"})
        r = smet.analizar_respuesta(texto, "2026-01-01", "2026-01-02")
        self.assertEqual(r["estado"], "serie")
        self.assertEqual(r["filas"], 47)
        self.assertEqual(r["filas_con_observacion"], 46)
        self.assertEqual((r["minimo"], r["maximo"]), ("12.5", "12.5"))

    def test_rosa_de_vientos_no_es_serie(self):
        r = smet.analizar_respuesta(ROSA, "2026-01-01", "2026-01-01")
        self.assertEqual(r["estado"], "formato_no_serie")

    def test_macro_inexistente(self):
        texto = "psgraph: Could not load macro: Can't open macro file x.ic"
        self.assertEqual(smet.analizar_respuesta(texto, "2026-01-01", "2026-01-01")["estado"],
                         "macro_inexistente")

    def test_plantilla_vacia(self):
        texto = serie_horaria("2026-01-01", "2026-01-01", valor="")
        self.assertEqual(smet.analizar_respuesta(texto, "2026-01-01", "2026-01-01")["estado"],
                         "sin_observaciones")

    def test_rango_truncado(self):
        texto = serie_horaria("2026-01-01", "2026-01-01")
        self.assertEqual(smet.analizar_respuesta(texto, "2026-01-01", "2026-01-02")["estado"],
                         "incompleta")


class EscrituraTest(unittest.TestCase):
    def test_no_sobrescribe(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "x.csv"
            ruta.write_bytes(b"original")
            with self.assertRaises(FileExistsError):
                smet.publicar_sin_sobrescribir(b"nuevo", ruta)
            self.assertEqual(ruta.read_bytes(), b"original")
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["x.csv"])

    def test_piso_de_espacio(self):
        Uso = namedtuple("Uso", "total used free")
        with patch.object(smet.shutil, "disk_usage", return_value=Uso(10, 5, 2 * 1024**3)):
            smet.comprobar_piso(Path("."), 1.0, 512 * 1024**2)
            with self.assertRaises(smet.DetencionSegura):
                smet.comprobar_piso(Path("."), 1.0, int(1.5 * 1024**3))


class CorridaTest(unittest.TestCase):
    def _preparar(self, base: Path):
        fichas = base / "fichas"
        fichas.mkdir()
        (fichas / "D14.html.gz").write_bytes(gzip.compress(FICHA.encode("utf-8")))
        config = base / "config.json"
        config.write_text(json.dumps([{"region": "RM", "estacion": "D14",
                                       "nombre": "Parque"}]), encoding="utf-8")
        return fichas, config

    def test_corrida_completa_y_reanudacion(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            fichas, config = self._preparar(base)
            destino = base / "salida"
            pedidos = []

            def falso(params):
                pedidos.append(params["macro"])
                return serie_horaria("2026-01-01", "2026-01-02")

            argv = ["--desde", "2026-01-01", "--hasta", "2026-01-02", "--config",
                    str(config), "--fichas", str(fichas), "--destino", str(destino),
                    "--pausa", "0"]
            with patch.object(smet, "pedir", side_effect=falso):
                self.assertEqual(smet.main(argv), 0)
            self.assertEqual(pedidos, ["./RM/D14/Met/TEMP//horario_003.ic",
                                       "./RM/D14/Met/WDIR//horario_010_spec.ic"])
            with (destino / "manifiesto_descarga.csv").open(encoding="utf-8") as f:
                filas = list(csv.DictReader(f))
            self.assertEqual(len(filas), 2)
            for fila in filas:
                datos = (destino / fila["ruta_relativa"]).read_bytes()
                self.assertEqual(hashlib.sha256(datos).hexdigest(), fila["sha256"])
                self.assertEqual(fila["accion"], "descargado")
            sumas = (destino / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(sumas), 2)
            # Segunda corrida: no pide nada y no reescribe los crudos.
            mtimes = {p: p.stat().st_mtime_ns for p in destino.glob("*/*.csv")}
            with patch.object(smet, "pedir", side_effect=AssertionError("no debe pedir")):
                self.assertEqual(smet.main(argv), 0)
            self.assertEqual(mtimes, {p: p.stat().st_mtime_ns for p in destino.glob("*/*.csv")})
            self.assertFalse(list(destino.rglob("*.part")))

    def test_fallo_de_formato_va_a_no_disponibles(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            fichas, config = self._preparar(base)
            destino = base / "salida"
            argv = ["--desde", "2026-01-01", "--hasta", "2026-01-01", "--config",
                    str(config), "--fichas", str(fichas), "--destino", str(destino),
                    "--pausa", "0", "--parametros", "WDIR"]
            with patch.object(smet, "pedir", return_value=ROSA):
                self.assertEqual(smet.main(argv), 0)
            with (destino / "no_disponibles.csv").open(encoding="utf-8") as f:
                faltantes = list(csv.DictReader(f))
            self.assertEqual(len(faltantes), 1)
            self.assertTrue(faltantes[0]["motivo"].startswith("formato_no_serie"))
            self.assertFalse(list(destino.glob("WDIR/*.csv")))

    def test_rechaza_destino_dentro_de_contaminantes(self):
        with tempfile.TemporaryDirectory() as d:
            fichas, config = self._preparar(Path(d))
            with self.assertRaises(SystemExit):
                smet.main(["--config", str(config), "--fichas", str(fichas),
                           "--destino", str(smet.SINCA / "meteo")])


if __name__ == "__main__":
    unittest.main()
