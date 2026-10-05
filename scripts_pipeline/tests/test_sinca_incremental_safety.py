"""Regresiones SINCA con fuentes sintéticas: sin red ni mediciones reales."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd


SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
ENCABEZADO = "FECHA;HORA;VALIDADO;PRELIMINAR;NO_VALIDADO;\n"
POLITICA = {
    "sinca": {
        "reloj_fuente": "hora_local_civil_sinca_sin_offset",
        "zona_iana_default": "America/Santiago",
        "zonas_iana_por_region": {
            "RXI": "America/Coyhaique", "RXII": "America/Punta_Arenas",
        },
    },
    "merra2_comunal": {"horas_para_recuperar_utc": 3},
}


def _cargar_modulo(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _texto(filas) -> str:
    return ENCABEZADO + "".join(
        f"{fecha};{hora};{v1};{v2};{v3};\n"
        for fecha, hora, v1, v2, v3 in filas
    )


def _tabla_horaria(desde: str, hasta: str, cambios=None) -> str:
    """Imita únicamente la forma 01:00 inicial–23:00 final del exportador."""
    inicio = datetime.fromisoformat(desde) + timedelta(hours=1)
    fin = datetime.fromisoformat(hasta) + timedelta(hours=23)
    cambios = cambios or {}
    filas = []
    marca = inicio
    while marca <= fin:
        valores = cambios.get(marca.strftime("%y%m%d %H%M"), ("10", "", ""))
        filas.append((marca.strftime("%y%m%d"), marca.strftime("%H%M"), *valores))
        marca += timedelta(hours=1)
    return _texto(filas)


class _HoyFijo(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 10)


class SincaAislado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entorno = tempfile.TemporaryDirectory(prefix="sinca-regresion-")
        cls.addClassCleanup(cls.entorno.cleanup)
        raiz = Path(cls.entorno.name)
        config = raiz / "config" / "sinca"
        config.mkdir(parents=True)
        (config / "politica_temporal.json").write_text(
            json.dumps(POLITICA), encoding="utf-8",
        )
        datos = raiz / "data"
        sinca = datos / "sinca"
        sinca.mkdir(parents=True)
        (sinca / "estaciones_georreferenciadas.csv").write_text(
            "region_sinca,estacion,nombre,comuna_geografica,usable_geoespacial\n"
            "RM,T01,Estacion sintetica,Comuna sintetica,true\n",
            encoding="utf-8",
        )
        variables = {
            "AFG_REPO_ROOT": str(raiz),
            "AIR_POLLUTION_DATA_ROOT": str(datos),
            "AIR_POLLUTION_DERIVED_ROOT": str(raiz / "derived"),
            "MPLCONFIGDIR": str(raiz / "matplotlib"),
        }
        with patch.dict(os.environ, variables), \
                patch.object(sys, "path", [str(SCRIPTS), *sys.path]), \
                patch("requests.sessions.Session.request", side_effect=AssertionError(
                    "Las pruebas SINCA no pueden abrir la red")):
            cls.lector = _cargar_modulo(
                "_afg_sinca_regresion", REPO / "scripts_superficie" / "afg_lib.py",
            )
            comun = _cargar_modulo("_common_sinca_regresion", SCRIPTS / "_common.py")
            comun.REPO_ROOT = raiz
            with patch.dict(sys.modules, {"_common": comun}):
                geo = _cargar_modulo(
                    "_geo_sinca_regresion", SCRIPTS / "actualizar_geometria_sinca.py",
                )
                with patch.dict(sys.modules, {"actualizar_geometria_sinca": geo}):
                    cls.descargador = _cargar_modulo(
                        "_descargar_sinca_regresion", SCRIPTS / "descargar_sinca.py",
                    )

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(prefix="caso-sinca-")
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.destino = self.raiz / "pm25" / "horario"
        self.destino.mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(self.lector, "SINCA_DIR", self.raiz).start()
        patch.object(self.descargador, "date", _HoyFijo).start()
        patch.object(
            self.descargador.shutil, "disk_usage",
            return_value=SimpleNamespace(free=500 * 1024**3),
        ).start()
        patch("requests.sessions.Session.request", side_effect=AssertionError(
            "Las pruebas SINCA no pueden abrir la red")).start()

    def guardar(self, desde, hasta, filas):
        ruta = self.destino / f"RM_T01_horario_{desde}_{hasta}.csv"
        ruta.write_text(_texto(filas), encoding="utf-8")
        return ruta

    def comparar_solape(self, antiguo, nuevo):
        self.guardar("2000-01-01", "2026-09-03", [antiguo])
        # La segunda fila obliga a leer el archivo nuevo incluso si la fila
        # solapada está vacía; no queremos un falso positivo por omitir un
        # archivo que carezca de cualquier observación.
        self.guardar("2026-09-03", "2026-09-10", [
            nuevo, ("260910", "1300", "22", "", ""),
        ])
        resultado = self.lector.leer_sinca("pm25")
        self.assertEqual(
            resultado.loc[resultado["ts_local"] == pd.Timestamp("2026-09-10 13:00"),
                          "obs"].tolist(),
            [22.0],
        )
        marca = pd.to_datetime(antiguo[0] + antiguo[1], format="%y%m%d%H%M")
        return resultado.loc[resultado["ts_local"] == marca]


class LectorIncrementalTests(SincaAislado):
    def test_rangos_de_plausibilidad_coinciden_entre_lector_y_descargador(self):
        self.assertEqual(self.lector.RANGO_VALIDO, self.descargador.RANGO_VALIDO)

    def test_fila_nueva_vacia_no_oculta_medicion_validada(self):
        resultado = self.comparar_solape(
            ("260903", "1400", "12", "", ""),
            ("260903", "1400", "", "", ""),
        )
        self.assertEqual(resultado["obs"].tolist(), [12.0])

    def test_nueva_menor_calidad_no_desplaza_validada(self):
        for calidad in (1, 2):
            with self.subTest(columna=calidad):
                valores = ["", "", ""]
                valores[calidad] = "99"
                resultado = self.comparar_solape(
                    ("260903", "1400", "12", "", ""),
                    ("260903", "1400", *valores),
                )
                self.assertEqual(resultado["obs"].tolist(), [12.0])

    def test_misma_calidad_prioriza_fecha_final_mas_reciente(self):
        resultado = self.comparar_solape(
            ("260903", "1400", "12", "", ""),
            ("260903", "1400", "15", "", ""),
        )
        self.assertEqual(resultado["obs"].tolist(), [15.0])

    def test_mejor_calidad_antigua_preliminar_gana_a_no_validada(self):
        resultado = self.comparar_solape(
            ("260903", "1400", "", "12", ""),
            ("260903", "1400", "", "", "99"),
        )
        self.assertEqual(resultado["obs"].tolist(), [12.0])

    def test_infinito_o_fuera_de_rango_no_desplaza_observacion_util(self):
        for invalido in ("inf", "-inf", "nan", "1501", "-1"):
            with self.subTest(valor=invalido):
                resultado = self.comparar_solape(
                    ("260903", "1400", "", "12", ""),
                    ("260903", "1400", invalido, "", ""),
                )
                self.assertEqual(resultado["obs"].tolist(), [12.0])

    def test_parser_fallback_numerico_y_calidad(self):
        ruta = self.guardar("2026-09-03", "2026-09-10", [
            ("260903", "0100", "texto", "12,5", "99"),
            ("260903", "0200", "inf", "otro texto", "7,25"),
            ("260903", "0300", "  ", "-inf", "NaN"),
            ("260903", "0400", "0", "2", "3"),
        ])
        resultado = self.lector.leer_sinca_serie(ruta)
        np.testing.assert_allclose(
            resultado["obs"].to_numpy(), [12.5, 7.25, np.nan, 0.0], equal_nan=True,
        )
        self.assertEqual(resultado["qc_observacion"].tolist(), [
            "preliminar", "no_validado", "sin_dato", "validado",
        ])

    def test_conserva_horas_reales_sin_agregar(self):
        self.guardar("2026-09-03", "2026-09-10", [
            ("260903", "0100", "10", "", ""),
            ("260903", "0200", "20", "", ""),
        ])
        resultado = self.lector.leer_sinca("pm25").sort_values("ts_local")
        self.assertEqual(resultado["ts_local"].tolist(), [
            pd.Timestamp("2026-09-03 01:00"), pd.Timestamp("2026-09-03 02:00"),
        ])
        self.assertEqual(resultado["ts"].tolist(), [
            pd.Timestamp("2026-09-03 05:00"), pd.Timestamp("2026-09-03 06:00"),
        ])
        self.assertEqual(resultado["qc_hora"].tolist(), ["ok", "ok"])

    def test_dst_mantiene_reloj_original_y_banderas(self):
        self.guardar("2026-04-04", "2026-09-10", [
            ("260404", "2300", "10", "", ""),
            ("260906", "0000", "20", "", ""),
        ])
        resultado = self.lector.leer_sinca("pm25").sort_values("ts_local")
        self.assertEqual(resultado["ts_local"].tolist(), [
            pd.Timestamp("2026-04-04 23:00"), pd.Timestamp("2026-09-06 00:00"),
        ])
        self.assertEqual(resultado["qc_hora"].tolist(), [
            "ambigua_asumida_estandar", "inexistente_desplazada_adelante",
        ])
        self.assertEqual(resultado["ts"].tolist(), [
            pd.Timestamp("2026-04-05 03:00"), pd.Timestamp("2026-09-06 04:00"),
        ])
        self.assertEqual(
            resultado.iloc[0]["ts_utc_alternativo"], pd.Timestamp("2026-04-05 02:00"),
        )


class CheckpointYBloqueoTests(SincaAislado):
    def test_checkpoint_preserva_historia_y_retira_faltante_recuperado(self):
        antigua = self.guardar("2000-01-01", "2026-09-03", [
            ("260903", "1400", "12", "", ""),
        ])
        reciente = self.guardar("2026-09-03", "2026-09-09", [
            ("260904", "1400", "15", "", ""),
        ])
        base = {"region": "RM", "estacion": "T01", "nombre": "Sintetica",
                "contaminante": "pm25", "resolucion": "horario"}
        historica = {**base, "desde": "2000-01-01", "hasta": "2026-09-03",
                     "ruta": str(antigua), "sha256": "hash-historico"}
        faltante = {**base, "desde": "2026-09-03", "hasta": "2026-09-09",
                    "motivo": "error temporal"}
        pendiente_distinto = {**faltante, "estacion": "T02"}
        recuperada = {**base, "desde": "2026-09-03", "hasta": "2026-09-09",
                      "ruta": str(reciente), "sha256": "hash-recuperado"}
        with patch.object(self.descargador, "SINCA", self.raiz):
            self.descargador._guardar_manifiestos(
                [historica], [faltante, pendiente_distinto],
            )
            self.descargador._guardar_manifiestos([recuperada], [])
            # Repetir el checkpoint no duplica éxitos ni revive faltantes.
            self.descargador._guardar_manifiestos([recuperada], [])
        with (self.raiz / "manifiesto_descarga.csv").open(encoding="utf-8") as f:
            exitos = list(csv.DictReader(f))
        with (self.raiz / "no_disponibles.csv").open(encoding="utf-8") as f:
            pendientes = list(csv.DictReader(f))
        self.assertEqual(len(exitos), 2)
        self.assertEqual({r["sha256"] for r in exitos}, {
            "hash-historico", "hash-recuperado",
        })
        self.assertEqual([r["estacion"] for r in pendientes], ["T02"])
        self.assertTrue(antigua.exists())

    def test_bloqueo_rechaza_segundo_escritor_y_se_libera(self):
        with patch.object(self.descargador, "SINCA", self.raiz):
            with self.descargador._bloqueo_descarga():
                with self.assertRaisesRegex(SystemExit, "otra descarga SINCA activa"):
                    with self.descargador._bloqueo_descarga():
                        self.fail("El segundo escritor adquirió el bloqueo")
            with self.descargador._bloqueo_descarga():
                pass


class GuardaDescargaTests(SincaAislado):
    def preparar_existente(self, desde="2026-09-10", hasta="2026-09-10"):
        ruta = self.destino / f"RM_T01_horario_{desde}_{hasta}.csv"
        contenido = _tabla_horaria(desde, hasta)
        ruta.write_text(contenido, encoding="utf-8")
        return ruta, contenido

    def descargar_respuesta(self, texto, desde="2026-09-10", hasta="2026-09-10"):
        with patch.object(self.descargador, "_get", return_value=SimpleNamespace(text=texto)):
            return self.descargador.descargar_serie(
                "RM", "T01", "PM25", "horario", desde, hasta, self.destino,
            )

    def test_reserva_insuficiente_aborta_antes_de_red_y_abrir_archivos(self):
        ruta, contenido = self.preparar_existente()
        archivos_antes = sorted(p.name for p in self.destino.iterdir())
        with patch.object(self.descargador.shutil, "disk_usage",
                          return_value=SimpleNamespace(free=99 * 1024**3)), \
                patch.object(self.descargador, "_get") as red, \
                patch.object(Path, "open", side_effect=AssertionError(
                    "No debe abrir archivos cuando falta la reserva")):
            with self.assertRaisesRegex(OSError, "reserva"):
                self.descargador.descargar_serie(
                    "RM", "T01", "PM25", "horario", "2026-09-10", "2026-09-10",
                    self.destino,
                )
        red.assert_not_called()
        self.assertEqual(ruta.read_text(encoding="utf-8"), contenido)
        self.assertEqual(sorted(p.name for p in self.destino.iterdir()), archivos_antes)

    def test_reserva_se_revisa_otra_vez_antes_de_escribir_la_respuesta(self):
        ruta, contenido = self.preparar_existente()
        nueva = _tabla_horaria("2026-09-10", "2026-09-10", {
            "260910 1200": ("11", "", ""),
        })
        with patch.object(self.descargador.shutil, "disk_usage", side_effect=[
            SimpleNamespace(free=500 * 1024**3),
            SimpleNamespace(free=100 * 1024**3),
        ]):
            with self.assertRaisesRegex(OSError, "reserva"):
                self.descargar_respuesta(nueva)
        self.assertEqual(ruta.read_text(encoding="utf-8"), contenido)
        self.assertEqual(list(self.destino.glob("*.part")), [])

    def test_refresco_rechaza_perder_una_medicion_y_conserva_original(self):
        ruta, contenido = self.preparar_existente()
        nueva = _tabla_horaria("2026-09-10", "2026-09-10", {
            "260910 1200": ("", "", ""),
        })
        with self.assertRaises(ValueError):
            self.descargar_respuesta(nueva)
        self.assertEqual(ruta.read_text(encoding="utf-8"), contenido)
        self.assertEqual(list(self.destino.glob("*.part")), [])

    def test_refresco_rechaza_bajar_calidad_y_conserva_original(self):
        ruta, contenido = self.preparar_existente()
        nueva = _tabla_horaria("2026-09-10", "2026-09-10", {
            "260910 1200": ("", "99", ""),
        })
        with self.assertRaises(ValueError):
            self.descargar_respuesta(nueva)
        self.assertEqual(ruta.read_text(encoding="utf-8"), contenido)
        self.assertEqual(list(self.destino.glob("*.part")), [])

    def test_refresco_rechaza_valor_nuevo_fuera_de_rango(self):
        ruta, contenido = self.preparar_existente()
        nueva = _tabla_horaria("2026-09-10", "2026-09-10", {
            "260910 1200": ("1501", "", ""),
        })
        with self.assertRaises(ValueError):
            self.descargar_respuesta(nueva)
        self.assertEqual(ruta.read_text(encoding="utf-8"), contenido)
        self.assertEqual(list(self.destino.glob("*.part")), [])

    def test_refresco_acepta_revision_de_igual_calidad(self):
        ruta, anterior = self.preparar_existente()
        nueva = _tabla_horaria("2026-09-10", "2026-09-10", {
            "260910 1200": ("11", "", ""),
        })
        resultado = self.descargar_respuesta(nueva)
        self.assertEqual(resultado[0], ruta)
        self.assertEqual(ruta.read_text(encoding="utf-8"), nueva)
        self.assertEqual(list(self.destino.glob("*.part")), [])
        eventos = [json.loads(linea) for linea in (
            self.destino / "reemplazos_sinca.jsonl"
        ).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(eventos), 1)
        self.assertEqual(
            eventos[0]["sha256_anterior"], hashlib.sha256(anterior.encode()).hexdigest(),
        )
        self.assertEqual(
            eventos[0]["sha256_nueva"], hashlib.sha256(nueva.encode()).hexdigest(),
        )
        self.assertEqual(eventos[0]["script_version"], self.descargador.SCRIPT_VERSION)
        self.assertEqual(eventos[0]["script_sha256"], self.descargador.SCRIPT_SHA256)

    def test_retiro_no_elimina_historia_si_nueva_copia_pierde_calidad(self):
        antigua, contenido = self.preparar_existente("2026-09-09", "2026-09-09")
        nueva = self.destino / "RM_T01_horario_2026-09-09_2026-09-10.csv"
        texto_nuevo = _tabla_horaria("2026-09-09", "2026-09-10", {
            "260909 1200": ("", "99", ""),
        })
        nueva.write_text(texto_nuevo, encoding="utf-8")
        try:
            retiradas = self.descargador._retirar_series_suplantadas(
                self.destino, "RM", "T01", "horario", "2026-09-09", "2026-09-10",
                nueva, texto_nuevo,
            )
        except ValueError:
            retiradas = 0
        self.assertEqual(retiradas, 0)
        self.assertTrue(antigua.exists())
        self.assertEqual(antigua.read_text(encoding="utf-8"), contenido)

    def test_retiro_no_elimina_historia_si_nueva_copia_pierde_medicion(self):
        antigua, contenido = self.preparar_existente("2026-09-09", "2026-09-09")
        nueva = self.destino / "RM_T01_horario_2026-09-09_2026-09-10.csv"
        texto_nuevo = _tabla_horaria("2026-09-09", "2026-09-10", {
            "260909 1200": ("", "", ""),
        })
        nueva.write_text(texto_nuevo, encoding="utf-8")
        try:
            retiradas = self.descargador._retirar_series_suplantadas(
                self.destino, "RM", "T01", "horario", "2026-09-09", "2026-09-10",
                nueva, texto_nuevo,
            )
        except ValueError:
            retiradas = 0
        self.assertEqual(retiradas, 0)
        self.assertTrue(antigua.exists())
        self.assertEqual(antigua.read_text(encoding="utf-8"), contenido)

    def test_retiro_no_elimina_historia_por_valor_nuevo_fuera_de_rango(self):
        antigua, contenido = self.preparar_existente("2026-09-09", "2026-09-09")
        nueva = self.destino / "RM_T01_horario_2026-09-09_2026-09-10.csv"
        texto_nuevo = _tabla_horaria("2026-09-09", "2026-09-10", {
            "260909 1200": ("1501", "", ""),
        })
        nueva.write_text(texto_nuevo, encoding="utf-8")
        try:
            retiradas = self.descargador._retirar_series_suplantadas(
                self.destino, "RM", "T01", "horario", "2026-09-09", "2026-09-10",
                nueva, texto_nuevo,
            )
        except ValueError:
            retiradas = 0
        self.assertEqual(retiradas, 0)
        self.assertTrue(antigua.exists())
        self.assertEqual(antigua.read_text(encoding="utf-8"), contenido)


if __name__ == "__main__":
    unittest.main()
