"""Pruebas sin red de descargar_sinca_ampliacion.py (fuentes sintéticas)."""
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
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
_TMP_DATA = tempfile.TemporaryDirectory()
_ENV_PREVIO = os.environ.get("AIR_POLLUTION_DATA_ROOT")
_PREVIOS = {m: sys.modules.pop(m, None) for m in ("_common", "descargar_sinca_meteorologia")}
os.environ["AIR_POLLUTION_DATA_ROOT"] = _TMP_DATA.name
sys.path.insert(0, str(SCRIPTS))
try:
    # Raíz de datos temporal: la prueba jamás toca el disco externo.
    amp = importlib.import_module("descargar_sinca_ampliacion")
finally:
    if _ENV_PREVIO is None:
        os.environ.pop("AIR_POLLUTION_DATA_ROOT", None)
    else:
        os.environ["AIR_POLLUTION_DATA_ROOT"] = _ENV_PREVIO
    for _m, _previo in _PREVIOS.items():
        if _previo is not None:
            sys.modules[_m] = _previo
        else:
            sys.modules.pop(_m, None)

REGION = """<html><body><table class="gob persist-area" id="tablaRegional"><thead>
<tr class="persist-header"><th>Estaci&oacute;n</th></tr></thead><tbody>
<tr style="width: 100%;"><th><span title="estaci&oacute;n p&uacute;blica" class="icon-publico"></span>
<span title="en l&iacute;nea" class="icon-online"></span><a href="/index.php/estacion/index/id/7">Parque Norte</a><div class="comuna">Comuna A</div></th>
<td><a class="iframe" href="//sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.htmlindico2.cgi?page=pageFrame&amp;macropath=./RM/X01/Cal/PM10&amp;macro=PM10.diario.diario&amp;from=990101&amp;to=261001&amp;">g</a></td>
<td class="cellWidth"><a title="Red Norte" href="//sinca.mma.gob.cl/x" class="iframe"><span class="icon-red"></span></a></td>
<td><a title="ver ficha" href="/index.php/estacion/index/id/7"><span class="icon-ficha"></span></a></td></tr>
<tr class="filtroPublica filtroOnline" style="width: 100%;"><th><span title="estaci&oacute;n meteorol&oacute;gica" class="icon-meteo"></span>
<a href="/index.php/estacion/index/id/8">Solo Meteo</a><div class="comuna">Comuna B</div></th>
<td></td><td><a title="ver ficha" href="/index.php/estacion/index/id/8"><span class="icon-ficha"></span></a></td></tr>
</tbody></table></body></html>"""

VACIA = '<html><table id="tablaRegional"><tbody></tbody></table></html>'


def _enlace(tipo, codigo, macro, desde, hasta, est="X01"):
    return (f'<a class="iframe" href="//sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.htmlindico2.cgi?'
            f'page=pageFrame&amp;header=P&amp;macropath=./RM/{est}/{tipo}/{codigo}&amp;'
            f'macro={macro}&amp;from={desde}&amp;to={hasta}&amp;">g</a>')


FICHA = f"""<html><head><script>
  var latlng = new google.maps.LatLng(-33.45, -70.66);
</script></head><body>
<h1>Estación Parque Norte (Acreditada)</h1>
<table class="gob min" id="tablaGeneral"><tbody>
<tr class="even"><th class="right">Propietario</th><td class="left">Empresa Uno S.A.</td></tr>
<tr class="odd"><th class="right">Operador</th><td class="left">Operadora Dos</td></tr>
<tr class="even"><th class="right">Región</th><td class="left">Metropolitana de Santiago</td></tr>
<tr class="odd"><th class="right">Provincia</th><td class="left">Santiago</td></tr>
<tr class="even"><th class="right">Comuna</th><td class="left">Comuna A</td></tr>
<tr class="odd"><th class="right">Coordenadas UTM</th><td class="left">  346000 E 6300000 N </td></tr>
<tr class="even"><th class="right">Huso horario</th><td class="left"> 19 </td></tr>
<tr class="odd"><th class="right">Recepción de datos</th><td class="left">en línea</td></tr>
<tr class="even"><th class="right">Inicio de operación reportada</th><td class="left">1999-01-01</td></tr>
</tbody></table>
<div class="stn-rep"><table class="gob min"><thead><tr><th></th><th>Inicio</th><th>Término</th></tr></thead>
<tbody><tr class="serie odd"><th class="center">MP10</th><td class="center">01-01-2005</td><td class="center">N/D</td><td>N/D</td></tr></tbody></table></div>
<table id="medicion" class="gob min"><tbody>
<tr class="serie odd master"><th colspan="2"><span><a name="PM10">Material particulado MP 10</a></span><br />(MP 10 - µg/m3N)</th>
<td class="center">01-01-1999</td><td class="center">2026-10-01</td><td class="helpTecnica center">BETA</td>
<td>{_enlace("Cal", "PM10", "PM10.diario.diario", "990101", "261001")}</td></tr>
<tr class="serie hideme odd"><td colspan="6">{_enlace("Cal", "PM10", "PM10.horario.horario", "981231", "261001")} registros horarios</td></tr>
<tr class="serie even master"><th colspan="2"><span><a name="0NOX">Óxidos de nitrógeno</a></span><br />(NOX - ppb)</th>
<td>01-01-2010</td><td>2026-10-01</td><td>QUIMIO</td><td>{_enlace("Cal", "0NOX", "0NOX.diario.diario", "100101", "261001")}</td></tr>
<tr class="serie hideme even"><td colspan="6">{_enlace("Cal", "0NOX", "0NOX.horario.horario", "100101", "261001")}</td></tr>
<tr class="serie odd master"><th colspan="2"><span><a name="PM1D">Material particulado 10 micrometros discreto</a></span></th>
<td>01-01-2015</td><td>2020-03-25</td><td>GRAV</td><td>{_enlace("Cal", "PM1D", "PM1D.discreto.diario", "150101", "200325")}</td></tr>
<tr class="serie odd master"><th colspan="2"><span><a name="0001">Dióxido de azufre</a></span></th>
<td>01-01-2010</td><td>2026-10-01</td><td>UV</td><td>{_enlace("Cal", "0001", "0001.diario.diario", "100101", "261001", est="OTRA")}</td></tr>
</tbody></table>
<table class="gob min"><tbody>
<tr class="serie odd"><th colspan="2"><span><a name="TEMP">Temperatura ambiente</a></span><br />(Temperatura - °C)</th>
<td class="center">horario</td><td class="center">3 m</td><td>15-12-2003</td><td>02-09-2026</td>
<td class="helpTecnica center">SENSOR T</td><td>{_enlace("Met", "TEMP", "horario_003", "031215", "260902")}</td></tr>
<tr class="serie even"><th colspan="2"><span><a name="GLOB">Radiación global</a></span></th>
<td class="center">horario</td><td class="center">3 m</td><td>15-12-2003</td><td>02-09-2026</td>
<td class="helpTecnica center">PIRANOMETRO</td><td>{_enlace("Met", "GLOB", "horario_003", "031215", "260902")}</td></tr>
</tbody></table></body></html>"""

FICHA_SIN_SERIES = """<html><body><h1>Estación Solo Meteo</h1>
<table id="tablaGeneral"><tbody><tr><th class="right">Comuna</th><td class="left">Comuna B</td></tr>
</tbody></table><p>Sin datos</p></body></html>"""

MAPA = [{"nombre": "Parque Norte", "key": "X01", "latitud": -33.4, "longitud": -70.6,
         "red": "Red Norte", "calificacion": "Privada", "empresa": "Empresa Uno"}]


def serie_horaria(desde, hasta, columnas=("12,5", "", "")):
    marca = datetime.fromisoformat(desde) + timedelta(hours=1)
    fin = datetime.fromisoformat(hasta) + timedelta(hours=23)
    filas = ["FECHA (YYMMDD);HORA (HHMM);"]
    while marca <= fin:
        filas.append(f"{marca:%y%m%d;%H%M};" + ";".join(columnas) + ";")
        marca += timedelta(hours=1)
    return "\n".join(filas) + "\n"


def serie_diaria(desde, hasta, columnas=("", "7", "")):
    dia, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
    filas = ["FECHA (YYMMDD);HORA (HHMM);"]
    while dia < fin:
        filas.append(f"{dia:%y%m%d};0000;" + ";".join(columnas) + ";")
        dia += timedelta(days=1)
    return "\n".join(filas) + "\n"


def meteo_horaria(desde, hasta):
    marca = datetime.fromisoformat(desde) + timedelta(hours=1)
    fin = datetime.fromisoformat(hasta) + timedelta(hours=23)
    filas = ["FECHA (YYMMDD);HORA (HHMM);"]
    while marca <= fin:
        filas.append(f"{marca:%y%m%d;%H%M};3,5;")
        marca += timedelta(hours=1)
    return "\n".join(filas) + "\n"


class AnalisisTest(unittest.TestCase):
    def test_pagina_regional(self):
        filas = amp.parsear_pagina_regional(REGION, "M")
        self.assertEqual([f["id_sinca"] for f in filas], ["7", "8"])
        a, b = filas
        self.assertEqual(a["claves_regionales"], [("RM", "X01")])
        self.assertEqual((a["publica_pagina_regional"], a["en_linea"], a["red_regional"]),
                         ("si", "si", "Red Norte"))
        self.assertEqual((b["claves_regionales"], b["con_meteorologia"], b["comuna_regional"]),
                         ([], "si", "Comuna B"))
        with self.assertRaises(ValueError):
            amp.parsear_pagina_regional("<html></html>", "M")

    def test_ficha_general(self):
        g = amp.parsear_ficha_general(FICHA)
        self.assertEqual(g["nombre"], "Parque Norte (Acreditada)")
        self.assertEqual((g["lat"], g["lon"]), ("-33.45", "-70.66"))
        self.assertEqual((g["utm_e"], g["utm_n"], g["huso"]), ("346000", "6300000", "19"))
        self.assertEqual(g["propietario"], "Empresa Uno S.A.")
        self.assertEqual(g["region"], "Región Metropolitana de Santiago")
        self.assertEqual(g["representatividad"], "MP10: 01-01-2005 a N/D")
        self.assertTrue(g["acreditacion"])

    def test_series_de_ficha(self):
        series = amp.series_de_ficha(FICHA, "RM", "X01")
        met = [(s["parametro"], s["macro_ficha"]) for s in series if s["tipo"] == "meteorologia"]
        self.assertEqual(met, [("GLOB", "horario_003"), ("TEMP", "horario_003")])
        cal = {(s["parametro"], s["resolucion"]): s for s in series if s["tipo"] == "contaminante"}
        self.assertEqual(sorted(cal), [("nox", "diario"), ("nox", "horario"),
                                       ("pm10", "diario"), ("pm10", "horario"),
                                       ("pm10_discreto", "diario")])
        self.assertEqual(cal[("nox", "horario")]["unidad_ficha"], "ppb")
        self.assertEqual(cal[("pm10", "horario")]["desde_ficha"], "981231")
        self.assertEqual(cal[("pm10_discreto", "diario")]["macro_ficha"], "PM1D.discreto.diario")

    def test_clave_de_ficha(self):
        self.assertEqual(amp.clave_de_ficha(FICHA, [("RM", "X01")]),
                         (("RM", "X01"), "la ficha enlaza varias estaciones "
                          "[('RM', 'OTRA'), ('RM', 'X01')]; se usa la regional"))
        self.assertEqual(amp.clave_de_ficha(FICHA_SIN_SERIES, []), (("", ""), ""))

    def test_respuesta_horaria_con_estados(self):
        texto = serie_horaria("2026-01-01", "2026-01-02", ("1", "", "3"))
        r = amp.analizar_contaminante(texto, "2026-01-01", "2026-01-02", "horario")
        self.assertEqual((r["estado"], r["filas"], r["filas_con_observacion"]), ("serie", 47, 47))
        self.assertEqual((r["filas_validadas"], r["filas_preliminares"], r["filas_no_validadas"]),
                         (47, 0, 47))
        self.assertEqual(amp.estado_validacion(r), "mixta:validada+no_validada")

    def test_respuesta_diaria_excluye_ultimo_dia(self):
        texto = serie_diaria("2026-01-01", "2026-01-31")
        r = amp.analizar_contaminante(texto, "2026-01-01", "2026-01-31", "diario")
        self.assertEqual((r["estado"], r["filas"], r["ultima_marca"]), ("serie", 30, "260130 0000"))
        self.assertEqual(amp.estado_validacion(r), "solo_preliminar")
        corta = amp.analizar_contaminante(texto, "2026-01-01", "2026-02-01", "diario")
        self.assertEqual(corta["estado"], "incompleta")

    def test_respuestas_no_publicables(self):
        r = amp.analizar_contaminante("psgraph: Could not load macro: x", "2026-01-01",
                                      "2026-01-01", "horario")
        self.assertEqual(r["estado"], "macro_inexistente")
        vacia = serie_horaria("2026-01-01", "2026-01-01", ("", "", ""))
        self.assertEqual(amp.analizar_contaminante(vacia, "2026-01-01", "2026-01-01",
                                                   "horario")["estado"], "sin_observaciones")
        self.assertEqual(amp.analizar_contaminante("<html>error</html>", "2026-01-01",
                                                   "2026-01-01", "horario")["estado"],
                         "formato_no_serie")

    def test_rango_serie(self):
        self.assertEqual(amp.rango_serie({"desde_ficha": "970728"}, "2000-01-01", "2026-10-24",
                                         "1990-01-01"), ("1997-07-28", "2026-10-24"))
        self.assertEqual(amp.rango_serie({"desde_ficha": "700901"}, "2000-01-01", "2026-10-24",
                                         "1990-01-01"), ("1990-01-01", "2026-10-24"))
        self.assertEqual(amp.rango_serie({"desde_ficha": "150101"}, "2000-01-01", "2026-10-24",
                                         "1990-01-01"), ("2000-01-01", "2026-10-24"))

    def test_solo_sinca(self):
        with self.assertRaises(ValueError):
            amp._exigir_sinca("https://example.org/x")
        self.assertTrue(amp._exigir_sinca(amp.URL_MAPA))

    def test_codigo_publico_sin_rutas_personales_ni_arroba(self):
        for ruta in (SCRIPTS / "descargar_sinca_ampliacion.py", Path(__file__)):
            texto = ruta.read_text(encoding="utf-8")
            self.assertNotIn("/" + "Users/", texto)
            self.assertNotIn(chr(64), texto)


class CorridaTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.ampliacion = self.base / "ampliacion"
        self.meteo = self.base / "meteo"
        self.meteo.mkdir()
        self.sinca = self.base / "sinca"
        self.sinca.mkdir()
        self.config = self.base / "config.json"
        self.config.write_text(json.dumps([{"region": "RM", "estacion": "X01"}]),
                               encoding="utf-8")
        self.parches = [
            patch.object(amp, "CONFIG_ESTACIONES", self.config),
            patch.object(amp, "MANIFIESTO_SINCA", self.sinca / "manifiesto_descarga.csv"),
            patch.object(amp, "SINCA", self.sinca),
        ]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        self._tmp.cleanup()

    def _argv(self, fase, *extra):
        return ["--fase", fase, "--ampliacion", str(self.ampliacion), "--meteorologia",
                str(self.meteo), "--desde", "2026-01-01", "--desde-piso", "2026-01-01",
                "--hasta", "2026-01-02", "--pausa", "0", *extra]

    def _catalogo(self):
        def pagina(url):
            if "/region/index/id/M" in url:
                return REGION.encode("utf-8")
            if "/region/" in url:
                return VACIA.encode("utf-8")
            if "listadomapa2k19" in url:
                return json.dumps(MAPA).encode("utf-8")
            if url.endswith("/id/7"):
                return FICHA.encode("utf-8")
            return FICHA_SIN_SERIES.encode("utf-8")

        with patch.object(amp, "pedir_pagina", side_effect=pagina):
            self.assertEqual(amp.main(self._argv("catalogo")), 0)
        return amp.catalogo_vigente(self.ampliacion, None)

    def test_catalogo(self):
        carpeta = self._catalogo()
        estaciones = list(csv.DictReader((carpeta / "estaciones_fichas.csv").open(encoding="utf-8")))
        self.assertEqual([(e["id_sinca"], e["estacion"], e["configurada"]) for e in estaciones],
                         [("7", "X01", "si"), ("8", "", "no")])
        x01 = estaciones[0]
        self.assertEqual((x01["calificacion"], x01["fuente_calificacion"], x01["red"]),
                         ("Privada", "listadomapa2k19", "Red Norte"))
        self.assertEqual((x01["series_contaminantes"], x01["series_meteorologicas"]), ("5", "2"))
        for linea in (carpeta / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
            huella, relativa = linea.split("  ", 1)
            self.assertEqual(hashlib.sha256((carpeta / relativa).read_bytes()).hexdigest(), huella)
        ficha = gzip.decompress((carpeta / "fichas" / "id_7.html.gz").read_bytes())
        self.assertEqual(ficha, FICHA.encode("utf-8"))

    def test_meteorologia_no_toca_registros_previos(self):
        carpeta = self._catalogo()
        previo = {"region": "RM", "estacion": "X01", "parametro": "TEMP",
                  "macro_ficha": "horario_003", "desde": "2000-01-01", "hasta": "2026-10-24"}
        with (self.meteo / "manifiesto_descarga.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(previo))
            w.writeheader()
            w.writerow(previo)
        (self.meteo / "SHA256SUMS.txt").write_text("x  TEMP/a.csv\n", encoding="utf-8")
        (self.meteo / ".descarga_sinca_meteorologia.lock").write_bytes(b"")
        antes = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.meteo.iterdir()
                 if p.is_file()}
        pedidos = []

        def falso(params):
            pedidos.append(params["macro"])
            return meteo_horaria("2026-01-01", "2026-01-02")

        argv = self._argv("meteorologia", "--sufijo", "20261024b")
        with patch.object(amp, "pedir_exportador", side_effect=falso):
            self.assertEqual(amp.main(argv), 0)
        self.assertEqual(pedidos, ["./RM/X01/Met/GLOB//horario_003.ic"])
        for p, (datos, mtime) in antes.items():
            self.assertEqual((p.read_bytes(), p.stat().st_mtime_ns), (datos, mtime))
        filas = list(csv.DictReader((self.meteo / "manifiesto_descarga_20261024b.csv")
                                    .open(encoding="utf-8")))
        self.assertEqual([(f["parametro"], f["variable"], f["accion"]) for f in filas],
                         [("GLOB", "radiacion_global", "descargado")])
        self.assertEqual(list(filas[0]), amp.smet.CAMPOS_MANIFIESTO)
        huella, relativa = (self.meteo / "SHA256SUMS_20261024b.txt").read_text(
            encoding="utf-8").split()
        self.assertEqual(hashlib.sha256((self.meteo / relativa).read_bytes()).hexdigest(), huella)
        self.assertEqual(huella, filas[0]["sha256"])
        # Reanudación: no pide nada y no reescribe el crudo.
        mtime = (self.meteo / relativa).stat().st_mtime_ns
        with patch.object(amp, "pedir_exportador", side_effect=AssertionError("no debe pedir")):
            self.assertEqual(amp.main(argv), 0)
        self.assertEqual((self.meteo / relativa).stat().st_mtime_ns, mtime)
        self.assertFalse(list(self.meteo.rglob("*.part")))
        self.assertTrue(carpeta.exists())

    def test_contaminantes_excluye_lo_que_ya_esta_en_data_sinca(self):
        self._catalogo()
        with (self.sinca / "manifiesto_descarga.csv").open("w", encoding="utf-8",
                                                          newline="") as f:
            w = csv.DictWriter(f, fieldnames=amp.CAMPOS_MANIFIESTO_SINCA)
            w.writeheader()
            w.writerow({"region": "RM", "estacion": "X01", "contaminante": "pm10",
                        "resolucion": "diario"})
        pedidos = []

        def falso(params):
            pedidos.append(params["macro"])
            if "PM1D" in params["macro"]:
                raise RuntimeError("caída simulada")
            if "horario" in params["macro"]:
                return serie_horaria("2026-01-01", "2026-01-02")
            return serie_diaria("2026-01-01", "2026-01-02")

        argv = self._argv("contaminantes")
        with patch.object(amp, "pedir_exportador", side_effect=falso):
            self.assertEqual(amp.main(argv), 1)  # hubo un error
        self.assertNotIn("./RM/X01/Cal/PM10//PM10.diario.diario.ic", pedidos)
        self.assertEqual(len(pedidos), 4)
        leer = lambda nombre: list(csv.DictReader((self.ampliacion / nombre)  # noqa: E731
                                                  .open(encoding="utf-8")))
        contrato = leer("manifiesto_descarga.csv")
        otras = leer("manifiesto_descarga_otras_series.csv")
        self.assertEqual(list(contrato[0]), amp.CAMPOS_MANIFIESTO_CONTAMINANTES)
        self.assertEqual(list(contrato[0])[:25], amp.CAMPOS_MANIFIESTO_SINCA)
        self.assertEqual([(f["contaminante"], f["resolucion"]) for f in contrato],
                         [("pm10", "horario")])
        self.assertEqual(sorted((f["contaminante"], f["resolucion"]) for f in otras),
                         [("nox", "diario"), ("nox", "horario")])
        pm10 = contrato[0]
        self.assertEqual((pm10["macro_ficha"], pm10["unidad_ficha"], pm10["tecnica_ficha"],
                          pm10["propietario"], pm10["operador"], pm10["grupo"]),
                         ("PM10.horario.horario", "µg/m3N", "BETA", "Empresa Uno S.A.",
                          "Operadora Dos", "configurada"))
        self.assertEqual(Path(pm10["ruta"]).parent, self.ampliacion.resolve() / "pm10" / "horario")
        sumas = (self.ampliacion / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(sumas), 3)
        for linea in sumas:
            huella, relativa = linea.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.ampliacion / relativa).read_bytes())
                             .hexdigest(), huella)
        self.assertEqual([f["contaminante"] for f in leer("errores_descarga.csv")],
                         ["pm10_discreto"])
        validacion = {(v["contaminante"], v["resolucion"]): v
                      for v in leer("estado_validacion_series.csv")}
        self.assertEqual(validacion[("pm10", "horario")]["estado_validacion"], "solo_validada")
        self.assertEqual(validacion[("pm10", "horario")]["filas_validadas"], "47")
        self.assertEqual(validacion[("nox", "diario")]["filas_preliminares"], "1")
        self.assertTrue((self.ampliacion / "estaciones_fichas.csv").exists())
        self.assertEqual([p.name for p in self.sinca.rglob("*")], ["manifiesto_descarga.csv"])
        # Reintento de errores: sólo la serie que falló; la plantilla vacía queda registrada.
        pedidos.clear()
        vacia = lambda params: (pedidos.append(params["macro"])  # noqa: E731
                                or serie_diaria("2026-01-01", "2026-01-02", ("", "", "")))
        with patch.object(amp, "pedir_exportador", side_effect=vacia):
            self.assertEqual(amp.main(argv + ["--solo-errores"]), 0)
        self.assertEqual(pedidos, ["./RM/X01/Cal/PM1D//PM1D.discreto.diario.ic"])
        self.assertEqual(leer("errores_descarga.csv"), [])
        self.assertTrue(leer("no_disponibles.csv")[0]["motivo"].startswith("sin_observaciones"))
        # Reanudación completa: nada que descargar de nuevo salvo lo no disponible.
        pedidos.clear()
        with patch.object(amp, "pedir_exportador", side_effect=vacia):
            self.assertEqual(amp.main(argv), 0)
        self.assertEqual(pedidos, ["./RM/X01/Cal/PM1D//PM1D.discreto.diario.ic"])
        self.assertEqual(len(leer("estado_validacion_series.csv")), 3)

    def test_actualizacion_de_las_configuradas(self):
        self._catalogo()
        filas_previas = [("pm10", "2026-01-01"), ("pm10", "2026-01-02"),
                         ("so2", "2026-01-02"), ("co", "2026-01-03"), ("nox", "2026-01-01")]
        with (self.sinca / "manifiesto_descarga.csv").open("w", encoding="utf-8",
                                                          newline="") as f:
            w = csv.DictWriter(f, fieldnames=amp.CAMPOS_MANIFIESTO_SINCA)
            w.writeheader()
            for contaminante, hasta in filas_previas:
                w.writerow({"region": "RM", "estacion": "X01", "contaminante": contaminante,
                            "resolucion": "horario", "desde": "2000-01-01", "hasta": hasta})
        (self.sinca / "estaciones_georreferenciadas.geojson").write_text('{"x": 1}\n')
        (self.sinca / "estaciones_georreferenciadas.csv").write_text("estacion\nX01\n")
        antes = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.sinca.rglob("*")}
        pedidos = []

        def falso(params):
            pedidos.append((params["macro"], params["from"], params["to"]))
            return serie_horaria("2026-01-02", "2026-01-03")

        argv = ["--fase", "actualizacion", "--ampliacion", str(self.ampliacion),
                "--meteorologia", str(self.meteo), "--hasta", "2026-01-03", "--pausa", "0"]
        with patch.object(amp, "pedir_exportador", side_effect=falso):
            self.assertEqual(amp.main(argv), 0)
        # Desde el último día en disco; co ya está al día y nox no es del contrato.
        self.assertEqual(sorted(pedidos), [
            ("./RM/X01/Cal/0001//0001.horario.horario.ic", "260102", "260103"),
            ("./RM/X01/Cal/PM10//PM10.horario.horario.ic", "260102", "260103")])
        destino = self.ampliacion / "actualizacion_configuradas"
        filas = list(csv.DictReader((destino / "manifiesto_descarga.csv").open(encoding="utf-8")))
        self.assertEqual(list(filas[0]), amp.CAMPOS_MANIFIESTO_CONTAMINANTES)
        self.assertEqual(sorted((f["contaminante"], f["desde"], f["hasta"], f["grupo"])
                                for f in filas),
                         [("pm10", "2026-01-02", "2026-01-03", "configurada"),
                          ("so2", "2026-01-02", "2026-01-03", "configurada")])
        pm10 = next(f for f in filas if f["contaminante"] == "pm10")
        self.assertEqual(Path(pm10["ruta"]), destino.resolve() / "pm10" / "horario"
                         / "RM_X01_horario_2026-01-02_2026-01-03.csv")
        self.assertEqual((pm10["unidad_ficha"], pm10["propietario"]), ("µg/m3N", "Empresa Uno S.A."))
        sumas = (destino / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(sumas), 2)
        for linea in sumas:
            huella, relativa = linea.split("  ", 1)
            self.assertEqual(hashlib.sha256((destino / relativa).read_bytes()).hexdigest(), huella)
        self.assertEqual((destino / "estaciones_georreferenciadas.geojson").read_bytes(),
                         b'{"x": 1}\n')
        self.assertFalse((destino / "manifiesto_descarga_otras_series.csv").exists())
        self.assertEqual(antes, {p: (p.read_bytes(), p.stat().st_mtime_ns)
                                 for p in self.sinca.rglob("*")})
        with patch.object(amp, "pedir_exportador", side_effect=AssertionError("no debe pedir")):
            self.assertEqual(amp.main(argv), 0)

    def test_rechaza_destino_dentro_de_data_sinca(self):
        with self.assertRaises(SystemExit):
            amp.main(["--fase", "inventario", "--ampliacion", str(self.sinca / "x"),
                      "--meteorologia", str(self.meteo)])

    def test_inventario(self):
        self._catalogo()
        self.assertEqual(amp.main(self._argv("inventario")), 0)
        plan = json.loads(next((self.ampliacion / "inventario").glob("*/plan.json"))
                          .read_text(encoding="utf-8"))
        self.assertEqual(plan["meteorologia"]["pendientes"]["series"], 2)
        self.assertEqual(plan["contaminante"]["pendientes"]["series"], 5)


if __name__ == "__main__":
    unittest.main()
