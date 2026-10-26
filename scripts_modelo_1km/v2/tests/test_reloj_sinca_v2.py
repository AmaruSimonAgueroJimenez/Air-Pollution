"""Pruebas de ``reloj_sinca_v2``: las dos convenciones de etiqueta civil, el verificador original y el paso a UTC.

El original no se importa (importa ``_comun_modelo``, que exige el disco de datos): sus funciones ``transiciones``,
``evaluar_dia`` y ``veredicto`` se extraen por AST, como hace el reloj DMC (``reloj_dmc/fijados.py``), y se ejecutan en
un espacio aislado. Las series son sintéticas, en tres relojes: UTC−4 fijo y hora civil de America/Santiago con cada
una de las dos convenciones de etiqueta (``fin``: la hora del reloj al terminar; ``inicio_mas_1h``: la de inicio + 1 h).
Muestran que el original sólo ve la segunda, que el verificador versionado ve las dos y que el paso a UTC exige que se
elija la convención cuando hay años civiles. Sin red ni datos.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import reloj_sinca_v2 as rs  # noqa: E402

ZONA = "America/Santiago"


def original(nombres=("transiciones", "evaluar_dia", "veredicto")) -> dict:
    """Las funciones del verificador original, extraídas por AST sin ejecutar el resto del módulo."""
    fuente = rs.RUTA_ORIGINAL.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    espacio = {"date": date, "datetime": datetime, "timedelta": timedelta, "ZoneInfo": ZoneInfo, "np": np, "pd": pd}
    for nodo in arbol.body:
        if isinstance(nodo, ast.FunctionDef) and nodo.name in nombres:
            exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(rs.RUTA_ORIGINAL), "exec"), espacio)
    return {n: espacio[n] for n in nombres}


def etiquetas(anio: int, reloj: str, zona: str = ZONA) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Etiquetas de un exportador horario durante ``anio`` y el inicio UTC verdadero de cada una.

    ``reloj`` = «fijo»: etiqueta = fin UTC − 4 h. «civil_fin»: la hora civil del reloj al terminar el intervalo.
    «civil_inicio_mas_1h»: la hora civil de inicio más una hora. Devuelve (etiquetas tal como las deja el derivado: una
    por etiqueta, ordenadas), la bandera ``hora_repetida_en_fuente`` y el inicio UTC de la **primera** aparición."""
    ini = datetime(anio, 1, 1, 4, tzinfo=timezone.utc)
    fin = datetime(anio + 1, 1, 1, 4, tzinfo=timezone.utc)
    tz = ZoneInfo(zona)
    filas, t = [], ini
    while t < fin:
        fin_bin = t + timedelta(hours=1)
        if reloj == "fijo":
            et = (fin_bin - timedelta(hours=4)).replace(tzinfo=None)
        elif reloj == "civil_fin":
            et = fin_bin.astimezone(tz).replace(tzinfo=None)
        elif reloj == "civil_inicio_mas_1h":
            et = t.astimezone(tz).replace(tzinfo=None) + timedelta(hours=1)
        else:
            raise ValueError(reloj)
        filas.append((et, t.replace(tzinfo=None)))
        t = fin_bin
    df = pd.DataFrame(filas, columns=["ts_local", "inicio_utc"])
    rep = df.duplicated("ts_local", keep=False)
    df["rep"] = rep
    df = df.drop_duplicates("ts_local", keep="first").sort_values("ts_local").reset_index(drop=True)
    df = df[df["ts_local"].dt.year == anio]
    return pd.DatetimeIndex(df["ts_local"]), df["rep"].to_numpy(bool), df["inicio_utc"].to_numpy("datetime64[ns]")


class OriginalTests(unittest.TestCase):
    def test_el_original_no_se_modifico(self):
        datos = rs.RUTA_ORIGINAL.read_bytes()
        self.assertEqual(hashlib.sha256(datos).hexdigest(), rs.SHA_ORIGINAL)

    def test_el_original_supone_inicio_mas_una_hora(self):
        """Las horas del original son las de la convención «inicio + 1 h»: una hora después de las de «fin»."""
        t = original()["transiciones"]
        for anio in (2008, 2016, 2023, 2025):
            with self.subTest(anio=anio):
                self.assertEqual(t(ZONA, anio), rs.transiciones(ZONA, anio, "inicio_mas_1h"))
        self.assertEqual(t(ZONA, 2023), [(date(2023, 4, 2), "ambigua", 0), (date(2023, 9, 3), "inexistente", 1)])

    def test_las_horas_reales_de_la_convencion_fin(self):
        # Chile continental: el adelanto salta de 24:00 a 01:00 (no existe el 00:00 del domingo) y el atraso vuelve
        # de 24:00 a 23:00 (se repite el 23:00 del sábado).
        self.assertEqual(rs.transiciones(ZONA, 2023, "fin"),
                         [(date(2023, 4, 1), "ambigua", 23), (date(2023, 9, 3), "inexistente", 0)])
        self.assertEqual(rs.transiciones(ZONA, 2025, "fin"),
                         [(date(2025, 4, 5), "ambigua", 23), (date(2025, 9, 7), "inexistente", 0)])

    def test_horas_civiles_especiales_segun_zoneinfo(self):
        """Cada hora civil «inexistente» no sobrevive al ir y volver de UTC y cada «ambigua» tiene dos desfases, en
        todas las zonas y años del período."""
        for zona in ("America/Santiago", "America/Punta_Arenas", "America/Coyhaique"):
            tz = ZoneInfo(zona)
            for anio in range(2000, 2027):
                for civil, tipo in rs.horas_civiles_especiales(zona, anio):
                    a = civil.replace(tzinfo=tz, fold=0)
                    b = civil.replace(tzinfo=tz, fold=1)
                    ida = a.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
                    with self.subTest(zona=zona, anio=anio, tipo=tipo):
                        if tipo == "inexistente":
                            self.assertNotEqual(ida, civil)
                        else:
                            self.assertNotEqual(a.utcoffset(), b.utcoffset())

    def test_sin_cambio_de_hora(self):
        for conv in rs.CONVENCIONES:
            self.assertEqual(rs.transiciones("America/Punta_Arenas", 2023, conv), [])
            self.assertEqual(rs.transiciones("America/Coyhaique", 2025, conv), [])

    def test_la_convencion_no_tiene_valor_por_omision(self):
        with self.assertRaises(TypeError):
            rs.transiciones(ZONA, 2023)                                   # hay que decir cuál
        with self.assertRaises(ValueError):
            rs.transiciones(ZONA, 2023, "otra")


ZONAS_POLITICA = ("America/Santiago", "America/Punta_Arenas", "America/Coyhaique")


def bytes_de_zona(zona: str) -> bytes:
    """El archivo de ``zona`` en la base de zonas de este entorno (carpeta de ``zoneinfo.TZPATH`` o paquete tzdata)."""
    import importlib.resources
    import zoneinfo
    for d in zoneinfo.TZPATH:
        q = Path(d) / zona
        if q.is_file():
            return q.read_bytes()
    return importlib.resources.files("tzdata.zoneinfo").joinpath(*zona.split("/")).read_bytes()


def otra_base_de_zonas():
    """Una base de zonas en la que America/Santiago es una copia de America/Punta_Arenas (el caso del revisor), puesta
    como única carpeta de ``zoneinfo.TZPATH`` mientras dura el bloque."""
    import contextlib
    import zoneinfo

    def ctx():
        with tempfile.TemporaryDirectory() as tmp:
            datos = {z: bytes_de_zona(z) for z in ZONAS_POLITICA}
            datos["America/Santiago"] = datos["America/Punta_Arenas"]
            for z, b in datos.items():
                q = Path(tmp).resolve() / z
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(b)
            zoneinfo.reset_tzpath([str(Path(tmp).resolve())])
            ZoneInfo.clear_cache()
            try:
                yield Path(tmp).resolve()
            finally:
                zoneinfo.reset_tzpath()
                ZoneInfo.clear_cache()
    return contextlib.contextmanager(ctx)()


class BaseDeZonasTests(unittest.TestCase):
    """Quinta revisión, menor 3: la base de zonas con que se elige T4 y se pasa a UTC queda fijada por sus horas
    especiales (132 en 2000-2026, 96a7b7cb…); otra base se detiene. El origen se registra sin rutas de usuario."""

    def test_la_de_este_entorno_es_la_fijada(self):
        base = rs.base_de_zonas(ZONAS_POLITICA)
        self.assertEqual((base["horas_especiales"], base["huella_horas_especiales"]),
                         (rs.HORAS_ESPECIALES["horas"], rs.HORAS_ESPECIALES["sha256"]))
        self.assertEqual(rs.exigir_base_de_zonas(base)["sha256"][:8], "96a7b7cb")
        self.assertNotIn("/" + "Users/", json.dumps(base, ensure_ascii=False))

    def test_otra_base_se_detiene(self):
        with otra_base_de_zonas() as carpeta:
            base = rs.base_de_zonas(ZONAS_POLITICA)
            self.assertNotEqual(base["horas_especiales"], 132)              # 112 en el caso del revisor
            with self.assertRaises(SystemExit) as e:
                rs.exigir_base_de_zonas(base)
            self.assertIn("base de zonas", str(e.exception))
            self.assertEqual(base["archivos"]["America/Santiago"]["origen"], "TZPATH: " + rs.origen_portable(carpeta))
        self.assertEqual(rs.base_de_zonas(ZONAS_POLITICA)["horas_especiales"], 132)    # de vuelta, la del entorno

    def test_origen_portable(self):
        import zoneinfo
        prefijo = Path(sys.prefix).resolve()
        self.assertEqual(rs.origen_portable(prefijo / "share" / "zoneinfo"),
                         f"<entorno {Path(sys.prefix).name}>/share/zoneinfo")
        self.assertEqual(rs.origen_portable("/usr/share/zoneinfo"), Path("/usr/share/zoneinfo").resolve().as_posix())
        self.assertEqual(rs.origen_portable(Path.home() / "x" / "zoneinfo"), "~/x/zoneinfo")
        primera = next((Path(d) for d in zoneinfo.TZPATH if (Path(d) / ZONA).is_file()), None)
        if primera is not None:
            base = rs.base_de_zonas([ZONA], (2023, 2023))
            self.assertEqual(base["archivos"][ZONA]["origen"], "TZPATH: " + rs.origen_portable(primera))


class LimiteR7Tests(unittest.TestCase):
    """Quinta revisión, menor 4: los años sin cambio de hora dan «sin_transiciones» y siguen la regla general; se
    declaran y se cuentan las unidades así cuyo año vecino da hora_civil con la convención elegida."""

    def test_anios_sin_cambio_de_hora(self):
        self.assertEqual(rs.anios_sin_cambio_de_hora(ZONAS_POLITICA),
                         {"America/Coyhaique": [2015, 2025, 2026],
                          "America/Punta_Arenas": [2015, *range(2017, 2027)], "America/Santiago": [2015]})

    def test_2015_junto_a_anios_civiles(self):
        """Un exportador «fin» de Santiago: 2014 y 2016 dan hora_civil y 2015, sin_transiciones (−03 todo el año: con la
        regla general, 1 h de error en todas sus horas); uno de reloj fijo no se cuenta."""
        filas = []
        for est, reloj in (("S1", "civil_fin"), ("S2", "fijo")):
            for anio in (2014, 2015, 2016):
                et, rep, _ = etiquetas(anio, reloj)
                filas += [{**f, "estacion": est, "contaminante": "pm25"}
                          for f in rs.verificar_serie(et, ZONA, rep, (anio, anio))[0]]
        tabla = pd.DataFrame(filas)
        self.assertEqual(tabla.set_index(["estacion", "anio"])["veredicto_fin"].to_dict(),
                         {("S1", 2014): "hora_civil", ("S1", 2015): "sin_transiciones", ("S1", 2016): "hora_civil",
                          ("S2", 2014): "reloj_fijo", ("S2", 2015): "sin_transiciones", ("S2", 2016): "reloj_fijo"})
        self.assertEqual(rs.sin_transiciones_junto_a_civil(tabla, "fin"),
                         [{"estacion": "S1", "contaminante": "pm25", "anio": 2015, "zona_iana": ZONA,
                           "vecinos_hora_civil": [2014, 2016]}])
        self.assertEqual(rs.sin_transiciones_junto_a_civil(tabla, None), [])
        lim = rs.limite_sin_transiciones(tabla, "fin", ZONAS_POLITICA)
        self.assertEqual((lim["n"], lim["anios_sin_cambio_de_hora"]["America/Santiago"]), (1, [2015]))
        c = rs.convertir(etiquetas(2015, "civil_fin")[0], {2015: "sin_transiciones"}, ZONA, "fin")
        self.assertEqual(set(c["reloj"]), {"fijo"})                          # la regla general: no se convierte


class VeredictoTests(unittest.TestCase):
    def setUp(self):
        self.o = original()

    def veredicto_original(self, et: pd.DatetimeIndex, anio: int) -> str:
        estados = [self.o["evaluar_dia"](et, f, tipo, h)["estado"] for f, tipo, h in self.o["transiciones"](ZONA, anio)]
        return self.o["veredicto"](estados)

    def test_reloj_fijo_con_las_dos_convenciones(self):
        et, rep, _ = etiquetas(2023, "fijo")
        self.assertEqual(self.veredicto_original(et, 2023), "reloj_fijo")
        f = rs.verificar_serie(et, ZONA, rep, (2023, 2023))[0][0]
        self.assertEqual((f["veredicto_fin"], f["veredicto_inicio_mas_1h"]), ("reloj_fijo", "reloj_fijo"))

    def test_civil_fin_el_original_no_la_ve(self):
        et, rep, _ = etiquetas(2023, "civil_fin")
        self.assertEqual(self.veredicto_original(et, 2023), "reloj_fijo_parcial")
        f = rs.verificar_serie(et, ZONA, rep, (2023, 2023))[0][0]
        self.assertEqual((f["veredicto_fin"], f["veredicto_inicio_mas_1h"]), ("hora_civil", "reloj_fijo_parcial"))

    def test_civil_inicio_mas_1h_el_original_si_la_ve(self):
        """La convención de c9: el original la detecta; con sólo «fin», el verificador no la vería."""
        et, rep, _ = etiquetas(2023, "civil_inicio_mas_1h")
        self.assertEqual(self.veredicto_original(et, 2023), "hora_civil")
        f = rs.verificar_serie(et, ZONA, rep, (2023, 2023))[0][0]
        self.assertEqual((f["veredicto_fin"], f["veredicto_inicio_mas_1h"]), ("reloj_fijo_parcial", "hora_civil"))

    def test_civil_sin_la_bandera_de_repeticion(self):
        """Aunque el derivado no traiga ``hora_repetida_en_fuente``, el día del adelanto basta."""
        for reloj, conv in (("civil_fin", "fin"), ("civil_inicio_mas_1h", "inicio_mas_1h")):
            et, _, _ = etiquetas(2023, reloj)
            f = rs.verificar_serie(et, ZONA, None, (2023, 2023))[0][0]
            self.assertEqual(f[f"veredicto_{conv}"], "hora_civil", reloj)

    def test_anio_con_pocas_etiquetas_no_se_evalua(self):
        et, rep, _ = etiquetas(2023, "fijo")
        filas, _ = rs.verificar_serie(et[:100], ZONA, rep[:100], (2023, 2023))
        self.assertEqual(filas, [])

    def test_sin_transiciones(self):
        et, rep, _ = etiquetas(2023, "fijo", "America/Punta_Arenas")
        f = rs.verificar_serie(et, "America/Punta_Arenas", rep, (2023, 2023))[0][0]
        self.assertEqual((f["veredicto_fin"], f["veredicto_inicio_mas_1h"]), ("sin_transiciones", "sin_transiciones"))

    def test_caida_de_la_estacion_es_sin_evidencia(self):
        et, rep, _ = etiquetas(2023, "fijo")
        dia = (et.normalize() == pd.Timestamp("2023-09-03")) & (et.hour < 6)
        f = rs.verificar_serie(et[~dia], ZONA, rep[~dia], (2023, 2023))[0][0]
        self.assertEqual(f["veredicto_fin"], "reloj_fijo_parcial")

    def test_la_convencion_se_exige_si_hay_hora_civil(self):
        et, rep, _ = etiquetas(2023, "civil_inicio_mas_1h")
        filas, _ = rs.verificar_serie(et, ZONA, rep, (2023, 2023))
        tabla = pd.DataFrame([{**f, "estacion": "C1", "contaminante": "pm25"} for f in filas])
        self.assertTrue(rs.convencion_requerida(tabla))
        with self.assertRaises(SystemExit):
            rs.veredictos_por_serie(tabla, None)
        self.assertEqual(rs.veredictos_por_serie(tabla, "inicio_mas_1h"), {("C1", "pm25"): {2023: "hora_civil"}})
        self.assertEqual(rs.veredictos_por_serie(tabla, "fin"), {("C1", "pm25"): {2023: "reloj_fijo_parcial"}})
        et, rep, _ = etiquetas(2023, "fijo")
        filas, _ = rs.verificar_serie(et, ZONA, rep, (2023, 2023))
        fija = pd.DataFrame([{**f, "estacion": "F1", "contaminante": "pm25"} for f in filas])
        self.assertFalse(rs.convencion_requerida(fija))
        self.assertEqual(rs.veredictos_por_serie(fija, None), {})          # todo en la regla general


class EleccionT4Tests(unittest.TestCase):
    """T4 con la unidad de T9 (2026-10-26): una sola convención para todo SINCA; votan las unidades del veredicto de R7
    (estación × contaminante × año local) con hora civil en una convención y no en la otra; empate, también en cero,
    → inicio_mas_1h."""

    def tabla(self, filas):
        return pd.DataFrame([{"estacion": e, "contaminante": p, "anio": a, "veredicto_fin": f, "veredicto_inicio_mas_1h": i}
                             for e, p, a, f, i in filas])

    def test_gana_la_de_mas_estacion_anios(self):
        civil, parcial = "hora_civil", "reloj_fijo_parcial"
        t = self.tabla([("A", "pm25", 2023, civil, parcial), ("A", "no2", 2023, civil, parcial),   # un estación-año
                        ("C", "pm25", 2022, civil, parcial), ("B", "pm25", 2023, parcial, civil),
                        ("D", "pm25", 2023, civil, civil),                                          # las dos: no cuenta
                        ("E", "o3", 2021, "reloj_fijo", "reloj_fijo")])
        e = rs.elegir_convencion(t)
        self.assertEqual((e["conteos"], e["elegida"], e["empate"]),
                         ({"solo_fin": 3, "solo_inicio_mas_1h": 1}, "fin", False))       # A cuenta dos veces (T9)
        self.assertEqual(e["unidades"], 6)
        t2 = self.tabla([("B", "pm25", 2023, parcial, civil), ("B", "pm25", 2024, parcial, civil),
                         ("A", "pm25", 2023, civil, parcial)])
        self.assertEqual(rs.elegir_convencion(t2)["elegida"], "inicio_mas_1h")
        with self.assertRaises(ValueError):                                 # una unidad repetida
            rs.elegir_convencion(self.tabla([("A", "pm25", 2023, civil, parcial)] * 2))

    def test_la_unidad_es_la_del_veredicto_de_r7(self):
        """T9: una estación con tres contaminantes en hora civil «fin» vota tres veces; con la lectura anterior
        (estación × año) habría votado una y habría ganado «inicio + 1 h»."""
        civil, parcial = "hora_civil", "reloj_fijo_parcial"
        t = self.tabla([("A", "pm25", 2023, civil, parcial), ("A", "no2", 2023, civil, parcial),
                        ("A", "o3", 2023, civil, parcial), ("B", "pm25", 2023, parcial, civil),
                        ("C", "pm25", 2023, parcial, civil)])
        e = rs.elegir_convencion(t)
        self.assertEqual((e["conteos"], e["elegida"]), ({"solo_fin": 3, "solo_inicio_mas_1h": 2}, "fin"))
        self.assertIn("contaminante", e["unidad"])

    def test_empate_tambien_en_cero_es_inicio_mas_1h(self):
        civil, parcial = "hora_civil", "reloj_fijo_parcial"
        uno_y_uno = self.tabla([("A", "pm25", 2023, civil, parcial), ("B", "pm25", 2023, parcial, civil)])
        sin_civil = self.tabla([("A", "pm25", 2023, "reloj_fijo", "reloj_fijo")])
        for t in (uno_y_uno, sin_civil, self.tabla([])):
            e = rs.elegir_convencion(t)
            self.assertEqual((e["elegida"], e["empate"]), ("inicio_mas_1h", True))
        self.assertEqual(rs.elegir_convencion(sin_civil)["conteos"], {"solo_fin": 0, "solo_inicio_mas_1h": 0})

    def test_con_series_sinteticas(self):
        """De punta a punta con las etiquetas: dos exportadores «fin» y uno «inicio + 1 h» → fin; la elección sólo usa
        las etiquetas (verificar_serie no recibe valores)."""
        filas = []
        for est, reloj in (("F1", "civil_fin"), ("F2", "civil_fin"), ("I1", "civil_inicio_mas_1h"), ("X", "fijo")):
            et, rep, _ = etiquetas(2023, reloj)
            filas += [{**f, "estacion": est, "contaminante": "pm25"} for f in rs.verificar_serie(et, ZONA, rep, (2023, 2023))[0]]
        e = rs.elegir_convencion(pd.DataFrame(filas))
        self.assertEqual((e["conteos"], e["elegida"]), ({"solo_fin": 2, "solo_inicio_mas_1h": 1}, "fin"))


RELOJES = {("F1", "pm25"): "fijo", ("C1", "no2"): "civil_fin", ("I1", "o3"): "civil_inicio_mas_1h",
           ("C2", "pm25"): "civil_fin"}
NUEVAS_RED2 = ("I1",)                                  # estaciones nuevas del derivado sintético (ampliación)
DOS_ARCHIVOS = {("C1", "no2"), ("C2", "pm25")}         # series con dos archivos en su manifiesto, como en SINCA


def filas_sinteticas(estacion: str, contaminante: str) -> int:
    """Las filas que publica la versión completa de una serie del derivado sintético (``escribir_derivado`` con
    ``RELOJES``; «fijo» si no está): las de ``observaciones.parquet`` (una por etiqueta) más las de
    ``solapamientos.parquet`` (la segunda aparición de cada etiqueta repetida). Es lo que declaran sus filas en los
    manifiestos de ``datos_red2`` (columna «filas»), como en SINCA, donde la suma de las filas de los archivos de una
    serie es la de su versión completa."""
    et, rep, _ = etiquetas(2023, RELOJES.get((estacion, contaminante), "fijo"))
    return int(len(et) + rep.sum())


def fuentes_sinteticas(estacion: str, contaminante: str, nuevas=NUEVAS_RED2) -> list[dict]:
    """Las filas de una serie en los manifiestos sintéticos de ``datos_red2`` (sellado o ampliación), con la ruta
    relativa a la raíz de datos, un sha256 propio por archivo, sus bytes y sus filas (``filas_sinteticas``, repartidas
    entre los archivos): son las ``sources`` que declara su versión, con todas las columnas de identidad
    (``derivado_red2_v2.CAMPOS_DE_LA_FUENTE``)."""
    import red_ampliada_v2 as ra
    carpeta = ra.AMP if estacion in nuevas else "sinca"
    tramos = ((("2000-01-01", "2015-12-31"), ("2016-01-01", "2026-10-24")) if (estacion, contaminante) in DOS_ARCHIVOS
              else (("2000-01-01", "2026-10-24"),))
    total = filas_sinteticas(estacion, contaminante)
    reparto = [total // len(tramos)] * (len(tramos) - 1)
    reparto.append(total - sum(reparto))
    out = []
    for (desde, hasta), filas in zip(tramos, reparto):
        rel = f"{carpeta}/{contaminante}/horario/RM_{estacion}_horario_{desde}_{hasta}.csv"
        out.append({"region": "RM", "estacion": estacion, "contaminante": contaminante, "resolucion": "horario",
                    "desde": desde, "hasta": hasta, "relative_path": rel, "bytes": "1", "filas": str(filas),
                    "sha256": hashlib.sha256(rel.encode("utf-8")).hexdigest()})
    return out


def manifiesto_del_preparador(since: str | None = None, afg: str | None = None, codigo: str | None = None,
                              estacion: str = "F1", contaminante: str = "pm25", etiqueta: str = "v1",
                              python: str = "3.11.16 | prueba", files: list | None = None,
                              until: str | None = None, fuentes: list | None = None,
                              estadisticas: dict | None = None) -> dict:
    """El manifest.json de una versión publicada por el preparador sellado: T8 (contrato, afg_lib, preparador y el
    Python de amb_v2) y su identidad, como la escribe ``process_series``: ``version`` = ``digest(inputs)``, ``inputs``
    con la estación y el contaminante, ``files`` con los dos parquet (``archivos_de_la_version``: sha256, filas y
    huella del esquema; cuarta revisión, menor 4, y ronda 4 de la traducción) y ``statistics`` con sus conteos. Como en
    el armado, sin ventana (``since`` y ``until`` nulos) y con ``sources`` = las filas de la serie en los manifiestos
    de ``datos_red2`` (``fuentes_sinteticas``; ronda 3 de la traducción, mayor). ``etiqueta`` distingue versiones de
    la misma serie."""
    import derivado_red2_v2 as dr
    inputs = {"contract": dr.CONTRATO, "station": estacion, "pollutant": contaminante, "since": since, "until": until,
              "sources": fuentes_sinteticas(estacion, contaminante) if fuentes is None else fuentes,
              "etiqueta_prueba": etiqueta, "code_sha256": codigo or dr.SHA_PREPARADOR,
              "afg_semantics": {"file_sha256": afg or dr.SHA_AFG, "ranking_ast_sha256": "r" * 64,
                                "parser_ast_sha256": "p" * 64},
              "runtime": {"python": python}}
    return {"contract": dr.CONTRATO, "version": dr.digest_del_preparador(inputs), "created_utc": "2026-10-26T00:00:00Z",
            "inputs": inputs, "statistics": dict(estadisticas or {}),
            "files": copy.deepcopy(files) if files is not None else
            [{"name": n, "sha256": None, "rows": None, "schema_sha256": None} for n in ("observaciones.parquet",
                                                                                     "solapamientos.parquet")]}


def archivos_de_la_version(carpeta: Path) -> list[dict]:
    """``files`` de una versión, como lo escribe ``process_series``: por parquet, su sha256, sus bytes, sus filas y la
    huella de su esquema (sólo metadatos)."""
    import pyarrow.parquet as pq
    out = []
    for n in ("observaciones.parquet", "solapamientos.parquet"):
        q = Path(carpeta) / n
        out.append({"name": n, "sha256": hashlib.sha256(q.read_bytes()).hexdigest(), "bytes": q.stat().st_size,
                    "rows": pq.read_metadata(q).num_rows,
                    "schema_sha256": hashlib.sha256(pq.read_schema(q).serialize().to_pybytes()).hexdigest()})
    return out


def carpeta_de_version(raiz: Path, est: str, pol: str) -> Path:
    """La carpeta ``version=…`` (una sola) de una serie del derivado sintético."""
    (c,) = sorted((Path(raiz) / f"estacion={est}" / f"contaminante={pol}").glob("version=*"))
    return c


def con_until(est: str, pol: str, inputs: dict, et, rep):
    """El caso del revisor (ronda 3 de la traducción): C1 de NO2 y C2 de PM2,5 publicadas con ``until`` =
    2023-08-31; sus etiquetas van del 10 de abril al 31 de agosto, sin los días de cambio de hora."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    dentro = (et >= pd.Timestamp("2023-04-10")) & (et < pd.Timestamp("2023-09-01"))
    return {**inputs, "until": "2023-08-31"}, et[dentro], rep[dentro]


def sin_el_ultimo_archivo(est: str, pol: str, inputs: dict, et, rep):
    """Un subconjunto de las fuentes (``ins["grupos"]`` filtrado): C1 de NO2 y C2 de PM2,5 publicadas sólo con su
    primer archivo (2000-2015), así que no traen ninguna etiqueta de 2023."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    dentro = et < pd.Timestamp("2016-01-01")
    return {**inputs, "sources": inputs["sources"][:1]}, et[dentro], rep[dentro]


def con_contenido_recortado(est: str, pol: str, inputs: dict, et, rep):
    """Ronda 4 de la traducción, menor 7 (el caso del revisor): C1 de NO2 y C2 de PM2,5 con los mismos ``inputs`` que
    las completas (la misma versión) y el contenido recortado al 10 de abril - 31 de agosto, con ``files`` y
    ``statistics`` al día (``escribir_derivado`` los calcula de lo escrito): ``files`` queda fuera de
    ``digest(inputs)``."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    dentro = (et >= pd.Timestamp("2023-04-10")) & (et < pd.Timestamp("2023-09-01"))
    return inputs, et[dentro], rep[dentro]


def con_since(est: str, pol: str, inputs: dict, et, rep):
    """Ronda 4, menor 20: C1 de NO2 y C2 de PM2,5 publicadas con ``since`` (sus etiquetas de 2023 quedan todas)."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    return {**inputs, "since": "2016-01-01"}, et, rep


def con_una_fuente_de_mas(est: str, pol: str, inputs: dict, et, rep):
    """Ronda 4, menor 20: una fila ajena a la lista cerrada entre las fuentes de C1 de NO2 y de C2 de PM2,5 (R2)."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    rel = f"sinca/{pol}/horario/RM_Z9_horario_2000-01-01_2026-10-24.csv"
    ajena = {**inputs["sources"][0], "estacion": "Z9", "relative_path": rel,
             "sha256": hashlib.sha256(rel.encode("utf-8")).hexdigest()}
    return {**inputs, "sources": inputs["sources"] + [ajena]}, et, rep


def con_una_fuente_repetida(est: str, pol: str, inputs: dict, et, rep):
    """Ronda 4, menor 20: la primera fuente de C1 de NO2 y de C2 de PM2,5, repetida."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    return {**inputs, "sources": inputs["sources"] + inputs["sources"][:1]}, et, rep


def con_otra_huella(est: str, pol: str, inputs: dict, et, rep):
    """Ronda 4, menor 20: la última fuente de C1 de NO2 y de C2 de PM2,5 con la misma ruta y otro sha256."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    return {**inputs, "sources": inputs["sources"][:-1] + [{**inputs["sources"][-1], "sha256": "0" * 64}]}, et, rep


def con_otro_hasta(est: str, pol: str, inputs: dict, et, rep):
    """Ronda 4, menor 8: la primera fuente de C1 de NO2 y de C2 de PM2,5 con la misma ruta y el mismo sha256 y otro
    «hasta» (el preparador lo toma de la fila, no del archivo)."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    return {**inputs, "sources": [{**inputs["sources"][0], "hasta": "2016-06-30"}] + inputs["sources"][1:]}, et, rep


def _filas_movidas(est: str, pol: str, inputs: dict, et, rep, statistics: str):
    """Ronda 5, menor 2 (el caso del revisor): C1 de NO2 y C2 de PM2,5 con los ``inputs`` del completo (la misma
    versión); las filas de ``observaciones.parquet`` fuera del 10 de abril - 31 de agosto pasan a
    ``solapamientos.parquet`` (el total no cambia) y ``files`` queda al día. ``statistics``: «del_completo» (las del
    derivado completo, como las dejó el revisor) o «al_dia» (las que corresponden a los archivos alterados)."""
    if (est, pol) not in DOS_ARCHIVOS:
        return inputs, et, rep
    dentro = (et >= pd.Timestamp("2023-04-10")) & (et < pd.Timestamp("2023-09-01"))
    solapamientos = et[rep].append(et[~dentro])
    return inputs, et[dentro], rep[dentro], {"solapamientos": solapamientos, "statistics": statistics}


def con_filas_movidas(est: str, pol: str, inputs: dict, et, rep):
    """Las filas movidas a ``solapamientos.parquet`` con ``statistics`` del completo: los conteos por archivo no
    calzan."""
    return _filas_movidas(est, pol, inputs, et, rep, "del_completo")


def con_filas_movidas_y_statistics_al_dia(est: str, pol: str, inputs: dict, et, rep):
    """Las filas movidas con ``statistics`` también al día (queda fuera de ``digest(inputs)``): los conteos calzan y lo
    detiene lo que deja el ranking afg (etiquetas de ``solapamientos.parquet`` que no están en
    ``observaciones.parquet``)."""
    return _filas_movidas(est, pol, inputs, et, rep, "al_dia")


# (nombre, ajustar, mensaje, si cambia la elección de T4): los derivados auténticos que quien lee para escribir rechaza
DERIVADOS_PARCIALES = (
    ("until", con_until, "inputs.until = '2023-08-31'", True),
    ("subconjunto de fuentes", sin_el_ultimo_archivo, "faltan 1", True),
    ("contenido recortado", con_contenido_recortado, "filas publicadas", True),
    ("since", con_since, "inputs.since = '2016-01-01'", False),
    ("una fuente de más", con_una_fuente_de_mas, "sobran 1", False),
    ("una fuente repetida", con_una_fuente_repetida, "repetidas 1", False),
    ("otra huella", con_otra_huella, "faltan 1", False),
    ("otro hasta", con_otro_hasta, "hasta: '2015-12-31' en la lista cerrada, '2016-06-30' en el derivado", False),
    ("filas movidas a solapamientos", con_filas_movidas, "statistics.filas_seleccionadas declara", True),
    ("filas movidas, statistics al día", con_filas_movidas_y_statistics_al_dia,
     "con etiquetas que no están en observaciones.parquet", True))


def plantar_version(raiz: Path, est: str, pol: str) -> Path:
    """Ronda 5, menor 4 (el caso del revisor): junto a la versión que publicó la corrida, otra versión auténtica de la
    misma serie que la corrida no publicó (otra etiqueta en ``inputs``: otro digest), con las fuentes completas, sin
    ventana, los mismos parquet y conteos y un ``created_utc`` posterior: es la que elige ``version_sinca``."""
    (vieja,) = sorted((Path(raiz) / f"estacion={est}" / f"contaminante={pol}").glob("version=*"))
    m = manifiesto_del_preparador(estacion=est, contaminante=pol, etiqueta="plantada")
    m["created_utc"] = "2026-10-28T00:00:00Z"
    c = vieja.parent / f"version={m['version']}"
    c.mkdir()
    for n in ("observaciones.parquet", "solapamientos.parquet"):
        (c / n).write_bytes((vieja / n).read_bytes())
    m["files"] = archivos_de_la_version(c)
    m["statistics"] = json.loads((vieja / "manifest.json").read_text())["statistics"]
    (c / "manifest.json").write_text(json.dumps(m))
    return c


def destino_red2(r) -> Path:
    """La raíz del derivado red 2 junto a la raíz de datos de ``r`` (``derivado_red2_v2.destino_por_omision``)."""
    import derivado_red2_v2 as dr
    return dr.destino_por_omision(r.datos)


def plan_de_prueba() -> dict:
    """Lo que exige quien lee del ``plan.json`` de una corrida (``derivado_red2_v2.exigir_plan_de_la_corrida``)."""
    import derivado_red2_v2 as dr
    return {"schema": dr.SCHEMA_PLAN, "codigo": {"programa": dr.PROGRAMA, "sha256": dr.huella_del_programa()}}


def escribir_derivado(raiz: Path, relojes=None, valores: float = 1.0, version: str = "v1", estado: str | None =
                      "complete_for_selected_scope", afg: str | None = None, ajustar=None,
                      plan: dict | None = None) -> Path:
    """Un derivado red 2 sintético: una versión por serie con su manifest.json (``version=digest(inputs)``; ``files``
    con los dos parquet, ``archivos_de_la_version``; ``statistics`` con los conteos que daría el preparador) y la
    corrida que la publicó (``_runs/<marca>-red2/progreso.json`` y su ``plan.json``, por omisión ``plan_de_prueba``);
    sólo ``ts_local``, ``hora_repetida_en_fuente``, ``obs`` y ``seleccionada``. ``observaciones.parquet`` trae una
    fila por etiqueta y ``solapamientos.parquet`` la segunda aparición de cada etiqueta repetida. ``version`` y
    ``valores`` entran en la identidad: otro valor da otra versión, como un derivado rearmado. ``ajustar(est, pol,
    inputs, etiquetas, repetidas)`` → (inputs, etiquetas, repetidas[, otros]) arma un derivado parcial (los casos de
    ``DERIVADOS_PARCIALES``); ``otros``, si está, puede dar las etiquetas de ``solapamientos.parquet``
    («solapamientos») y si ``statistics`` es la del completo o la de lo escrito («statistics»)."""
    import derivado_red2_v2 as dr
    relojes = RELOJES if relojes is None else relojes
    resultados = []
    for (est, pol), reloj in relojes.items():
        m = manifiesto_del_preparador(afg=afg, estacion=est, contaminante=pol, etiqueta=f"{version}:{valores!r}")
        et, rep, _ = etiquetas(2023, reloj)
        leidas = int(len(et) + rep.sum())                       # todas las filas de sus archivos (sin ventana)
        completas = {"filas_seleccionadas": int(len(et)), "filas_alternativas_conservadas": int(rep.sum())}
        otros = {}
        if ajustar is not None:
            inp, et, rep, *resto = ajustar(est, pol, copy.deepcopy(m["inputs"]), et, rep)
            otros = resto[0] if resto else {}
            m = {**m, "inputs": inp, "version": dr.digest_del_preparador(inp)}
        solap = otros.get("solapamientos", et[rep])
        c = raiz / f"estacion={est}" / f"contaminante={pol}" / f"version={m['version']}"
        c.mkdir(parents=True)
        pd.DataFrame({"ts_local": et, "hora_repetida_en_fuente": rep, "obs": valores,
                      "seleccionada": True}).to_parquet(c / "observaciones.parquet")
        pd.DataFrame({"ts_local": solap, "hora_repetida_en_fuente": True, "obs": valores,
                      "seleccionada": False}).to_parquet(c / "solapamientos.parquet")
        m["files"] = archivos_de_la_version(c)
        en_ventana = int(len(et) + len(solap))
        ventana = m["inputs"].get("since") or m["inputs"].get("until")
        m["statistics"] = {"filas_originales_leidas": leidas if ventana else en_ventana, "filas_en_ventana": en_ventana,
                           **({"filas_seleccionadas": int(len(et)), "filas_alternativas_conservadas": int(len(solap))}
                              if otros.get("statistics") != "del_completo" else completas)}
        (c / "manifest.json").write_text(json.dumps(m))
        resultados.append({"status": "published", "path": str(c), "version": m["version"]})
    if estado is not None:
        corrida = raiz / "_runs" / f"20261027T{len(list((raiz / '_runs').glob('*'))) if (raiz / '_runs').exists() else 0:06d}Z-red2"
        corrida.mkdir(parents=True)
        (corrida / "progreso.json").write_text(json.dumps({"status": estado, "results": resultados}))
        (corrida / "plan.json").write_text(json.dumps(plan_de_prueba() if plan is None else plan))
    return raiz


def datos_red2(datos: Path, series=None, nuevas=NUEVAS_RED2) -> Path:
    """Manifiestos y maestros sintéticos de la red 2 (sólo identidad), región RM: las series de ``series`` en el
    manifiesto sellado y sus estaciones en el maestro de las actuales, salvo las de ``nuevas``, que van al manifiesto
    y al maestro corregido de la ampliación. Cada serie tiene las filas de ``fuentes_sinteticas`` (dos archivos en las
    de ``DOS_ARCHIVOS``), con su ruta bajo la raíz de datos y su sha256."""
    import red_ampliada_v2 as ra
    series = sorted(RELOJES if series is None else series)
    cols = ["region", "estacion", "contaminante", "resolucion", "desde", "hasta", "ruta", "bytes", "sha256", "filas",
            "filas_con_observacion", "primera_observacion", "ultima_observacion"]
    def filas(cuales):
        return [{"region": "RM", "estacion": e, "contaminante": p, "resolucion": "horario", "desde": f["desde"],
                 "hasta": f["hasta"], "ruta": str(Path(datos).resolve() / f["relative_path"]), "bytes": f["bytes"],
                 "sha256": f["sha256"], "filas": f["filas"], "filas_con_observacion": f["filas"],
                 "primera_observacion": "", "ultima_observacion": ""}
                for e, p in cuales for f in fuentes_sinteticas(e, p, nuevas)]
    actuales = [s for s in series if s[0] not in nuevas]
    for rel, cuales in ((ra.MANIFIESTO_SELLADO, actuales), (ra.MANIFIESTO_ACTUALIZACION, []),
                        (ra.MANIFIESTO_NUEVAS, [s for s in series if s[0] in nuevas])):
        q = datos / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(filas(cuales), columns=cols).to_csv(q, index=False)
    def maestro(est):
        return pd.DataFrame({"estacion": est, "nombre": est, "region_sinca": "RM", "lat": -33.4, "lon": -70.6,
                             "cod_comuna_geografica": 13101, "qc_comuna": "coincide", "usable_geoespacial": True})
    for rel, est in ((ra.MAESTRO_ACTUALES, sorted({e for e, _ in actuales})),
                     (ra.MAESTRO_NUEVAS, sorted({e for e, _ in series if e in nuevas}))):
        q = datos / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        maestro(est).to_csv(q, index=False)
    return datos


class EjecutarRelojTests(unittest.TestCase):
    """El reloj que escribe la elección de T4: todo SINCA y el derivado completo de la red 2, con la política y los
    maestros leídos por su huella, series registradas con su huella, una sola vez; la elección no depende de los
    valores."""
    CONFIRMADA = staticmethod(lambda repo, rutas: {k: "rastreado" for k in rutas})
    CFG = {"red_de_monitores": {}}

    def setUp(self):
        import red_ampliada_v2 as ra
        sys.path.insert(0, str(V2 / "tests"))
        from unittest import mock
        self.ra = ra
        self._lista = mock.patch.object(ra, "LISTA_CERRADA", {})          # la lista cerrada de los datos sintéticos
        self._lista.start()
        self.addCleanup(self._lista.stop)

    def raices(self):
        from _sintetico_v2 import raices_temporales
        return raices_temporales("v2-reloj-")

    def escribir(self, r, raiz, **kw):
        return rs.ejecutar_reloj(r, [raiz], cfg=self.CFG, estado=self.CONFIRMADA, **kw)

    def test_un_subconjunto_no_escribe_la_eleccion(self):
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            for kw in ({"anios": (2023, 2023)}, {"contaminantes": ("pm25", "no2")}):
                with self.subTest(**kw), self.assertRaises(SystemExit):
                    self.escribir(r, raiz, **kw)
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
            resumen, _, estado = rs.ejecutar_reloj(r, [raiz], anios=(2023, 2023), escribir=False)   # sin escribir, sí
            self.assertEqual(estado, "sin_escribir")

    def test_region_o_politica_dadas_no_escriben(self):
        """Mayor 17: con escribir, el reloj no acepta regiones ni política dadas a mano (se saltarían la lista cerrada,
        los maestros y la huella de la política)."""
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            for kw in ({"region_de": {e: "RM" for e, _ in RELOJES}}, {"politica": rs.leer_politica()}):
                with self.subTest(sorted(kw)), self.assertRaises(SystemExit):
                    self.escribir(r, raiz, **kw)
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())

    def test_lista_cerrada_antes_de_los_maestros(self):
        """Con una lista cerrada que no se cumple, el reloj se detiene antes de leer los maestros de R8."""
        from unittest import mock
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            def no_debe_leerse(*a, **k):
                raise AssertionError("se leyeron los maestros antes de la lista cerrada")
            with mock.patch.object(self.ra, "LISTA_CERRADA", {"falta.csv": "0" * 64}), \
                    mock.patch.object(self.ra, "maestro_red2", no_debe_leerse):
                for escribir in (True, False):
                    with self.subTest(escribir=escribir), self.assertRaises(SystemExit):
                        rs.ejecutar_reloj(r, [raiz], escribir=escribir, cfg=self.CFG, estado=self.CONFIRMADA)

    def test_una_raiz_parcial_no_escribe(self):
        """Mayor 1 y 10: con una raíz que sólo trae F1 e I1 de las cuatro series de la red 2, o con un derivado cuya
        última corrida no terminó, o con dos raíces, el reloj no escribe la elección."""
        parcial = {k: v for k, v in RELOJES.items() if k[0] in ("F1", "I1")}
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r), parcial)
            with self.assertRaises(SystemExit) as e:
                self.escribir(r, raiz)
            self.assertIn("faltan 2", str(e.exception))
            self.assertIn("C1:no2", str(e.exception))
            a, _, _ = rs.ejecutar_reloj(r, [raiz], escribir=False)            # sin escribir, informa (0/1)
            self.assertEqual(a["convencion_civil"]["conteos"], {"solo_fin": 0, "solo_inicio_mas_1h": 1})
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r), estado="running")
            with self.assertRaises(SystemExit):                              # la última corrida no terminó
                self.escribir(r, raiz)
            otra = escribir_derivado(r.datos.parent / "derived" / "otra", {("X9", "no2"): "fijo"})
            with self.assertRaises(SystemExit) as e:                         # dos raíces
                rs.ejecutar_reloj(r, [raiz, otra], cfg=self.CFG, estado=self.CONFIRMADA)
            self.assertIn("un solo derivado", str(e.exception))             # ronda 5, menor 23: esa parada, no otra
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())

    def test_un_derivado_parcial_no_escribe(self):
        """Ronda 3 de la traducción, mayor (el caso del revisor), y ronda 4, menores 7, 8 y 20: un derivado auténtico
        pero parcial —versiones con su identidad y su corrida en orden, pero publicadas con ``until`` o con un
        subconjunto de sus fuentes, o con los ``inputs`` del completo y el contenido recortado, o (ronda 5, menor 2)
        con filas pasadas de ``observaciones.parquet`` a ``solapamientos.parquet``— cambia la elección de T4
        (inicio_mas_1h en vez de fin); con ``since``, con una fuente de más, repetida, con otra huella o con otro
        «hasta», no la cambia, pero tampoco es el derivado completo. En todos los casos el reloj que escribe se detiene
        mostrando la diferencia con la lista cerrada (T4, R4, R2) y no crea su carpeta. También con otra raíz que la de
        ``destino_por_omision`` (el mensaje la muestra, relativa a la carpeta de la raíz de datos o, fuera de ella, con
        sus últimos componentes: ronda 5, menor 30), sin ``plan.json`` o con un ``plan.json`` sin la huella rastreada de
        ``derivado_red2_v2.py``; y (ronda 5, menores 4 y 23) con una versión que la última corrida no publicó (plantada
        junto a la de la corrida, con ``created_utc`` posterior, que es la que elige ``version_sinca``), con un
        ``progreso.json`` que declara otra versión, o con una fila de los manifiestos que apunta fuera de la raíz de
        datos."""
        import shutil
        import derivado_red2_v2 as dr
        for nombre, ajustar, mensaje, cambia_t4 in DERIVADOS_PARCIALES:
            with self.subTest(nombre), self.raices() as r:
                datos_red2(r.datos)
                raiz = escribir_derivado(destino_red2(r), ajustar=ajustar)
                a, _, _ = rs.ejecutar_reloj(r, [raiz], escribir=False)            # sin escribir, informa
                self.assertEqual(a["convencion_civil"]["elegida"], "inicio_mas_1h" if cambia_t4 else "fin")
                with self.assertRaises(SystemExit) as e:
                    self.escribir(r, raiz)
                self.assertIn("lista cerrada", str(e.exception))
                self.assertIn(mensaje, str(e.exception))
                for serie in ("C1:no2", "C2:pm25"):
                    self.assertIn(serie, str(e.exception))
                self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
        with self.raices() as r:
            datos_red2(r.datos)
            revisor = escribir_derivado(r.datos.parent / "derived" / "v1_red2")     # la raíz del caso del revisor
            with self.assertRaises(SystemExit) as e:
                self.escribir(r, revisor)
            self.assertIn("destino_por_omision", str(e.exception))
            self.assertIn("no derived/v1_red2", str(e.exception))               # menor 22: la diferencia, a la vista
            self.assertNotIn(str(r.datos.parent), str(e.exception))           # sin rutas absolutas
            otra_huella = {"codigo": {"programa": dr.PROGRAMA, "sha256": "0" * 64}}
            otro_programa = {"codigo": {"programa": "scripts_modelo_1km/v2/otro.py", "sha256": dr.huella_del_programa()}}
            for nombre, plan, mensaje in (("sin plan.json", None, "plan.json legible"),
                                          ("otra huella", otra_huella, "huella rastreada"),
                                          ("otro programa", otro_programa, "huella rastreada")):
                raiz = destino_red2(r)
                shutil.rmtree(raiz, ignore_errors=True)
                escribir_derivado(raiz, plan=plan)
                if plan is None:
                    (sorted((raiz / "_runs").glob("*-red2"))[-1] / "plan.json").unlink()
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    self.escribir(r, raiz)
                self.assertIn(mensaje, str(e.exception))
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
            # ronda 5, menor 30: una raíz fuera de la carpeta de la raíz de datos, con sus últimos componentes
            with tempfile.TemporaryDirectory() as otro_disco:
                fuera = escribir_derivado(Path(otro_disco) / "derived" / "modelado" / "SINCA" / "v1_red2")
                with self.assertRaises(SystemExit) as e:
                    self.escribir(r, fuera)
                self.assertIn("no fuera de la carpeta de la raíz de datos: …/derived/modelado/SINCA/v1_red2",
                              str(e.exception))
                self.assertNotIn(str(Path(otro_disco)), str(e.exception))
                self.assertNotIn(str(Path(otro_disco).resolve()), str(e.exception))
            # ronda 5, menores 4 y 23: la versión de cada serie es la que publicó la última corrida
            for nombre in ("versión plantada", "progreso con otra versión"):
                raiz = destino_red2(r)
                shutil.rmtree(raiz, ignore_errors=True)
                escribir_derivado(raiz)
                if nombre == "versión plantada":
                    plantar_version(raiz, "C1", "no2")
                else:
                    corrida = sorted((raiz / "_runs").glob("*-red2"))[-1] / "progreso.json"
                    prog = json.loads(corrida.read_text())
                    for x in prog["results"]:
                        if "estacion=C1/contaminante=no2/" in x["path"]:
                            x["path"] = x["path"].rsplit("version=", 1)[0] + "version=" + "f" * 64
                    corrida.write_text(json.dumps(prog))
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    self.escribir(r, raiz)
                self.assertIn("no tienen la versión que publicó la última corrida", str(e.exception))
                self.assertIn("C1:no2", str(e.exception))
                self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
            # ronda 5, menor 23: una fila de los manifiestos de la red 2 que apunta fuera de la raíz de datos
            raiz = destino_red2(r)
            shutil.rmtree(raiz)
            escribir_derivado(raiz)
            manifiesto = r.datos / self.ra.MANIFIESTO_SELLADO
            tabla = pd.read_csv(manifiesto, dtype=str)
            tabla.loc[0, "ruta"] = str(Path(tempfile.gettempdir()) / "fuera_de_la_raiz" / Path(tabla.loc[0, "ruta"]).name)
            tabla.to_csv(manifiesto, index=False)
            with self.assertRaises(SystemExit) as e:
                self.escribir(r, raiz)
            self.assertIn("apuntan fuera de la raíz de datos", str(e.exception))
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
        with self.raices() as r:
            datos_red2(r.datos)
            self.assertEqual(self.escribir(r, escribir_derivado(destino_red2(r)))[2], "escrito")   # completo, sí

    def test_registra_las_series_y_se_escribe_una_vez(self):
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            with self.assertRaises(SystemExit):                              # sin la traducción confirmada en git
                rs.ejecutar_reloj(r, [raiz], cfg=self.CFG)
            resumen, _, estado = self.escribir(r, raiz)
            self.assertEqual(estado, "escrito")
            self.assertEqual(resumen["raices"], ["derived/modelado/SINCA/v1_red2"])
            self.assertEqual((resumen["anios"], resumen["contaminantes"]), ([2000, 2026], ["no2", "o3", "pm25"]))
            self.assertEqual(resumen["politica_temporal_sha256"], rs.SHA_POLITICA)   # la leída, por su huella
            self.assertEqual(resumen["derivado"]["series"], 4)
            self.assertTrue(resumen["derivado"]["corrida"].endswith("-red2"))
            self.assertEqual([(s["estacion"], s["contaminante"]) for s in resumen["series_registradas"]],
                             [("C1", "no2"), ("C2", "pm25"), ("F1", "pm25"), ("I1", "o3")])
            for s in resumen["series_registradas"]:                          # la versión es digest(inputs)
                self.assertEqual(s["version"], carpeta_de_version(raiz, s["estacion"], s["contaminante"]).name[8:])
            self.assertEqual(resumen["series_registradas"][0]["procedencia_afg"]["python"], "3.11.16")      # T8
            self.assertEqual({(x["region_sinca"], x["zona_iana"]) for x in resumen["evaluacion_por_serie"]},
                             {("RM", "America/Santiago")})
            ruta = carpeta_de_version(raiz, "C1", "no2") / "observaciones.parquet"
            self.assertEqual(resumen["series_registradas"][0]["sha256"], hashlib.sha256(ruta.read_bytes()).hexdigest())
            self.assertEqual((resumen["convencion_civil"]["conteos"], resumen["convencion_civil"]["elegida"]),
                             ({"solo_fin": 2, "solo_inicio_mas_1h": 1}, "fin"))
            self.assertIn("huella_horas_especiales", resumen["zonas_horarias"])
            self.assertEqual(resumen["zonas_horarias"]["conversion"]["biblioteca"], "zoneinfo")
            escrito = json.loads((r.raiz_v2 / rs.NOMBRE_SALIDA / "resumen.json").read_text(encoding="utf-8"))
            self.assertEqual(escrito["huella_series"], resumen["huella_series"])
            # quinta revisión, menor 3 y 4: la base de zonas fijada y el límite de R7, en el resumen
            self.assertEqual(escrito["zonas_horarias"]["fijadas"]["sha256"], rs.HORAS_ESPECIALES["sha256"])
            self.assertEqual((escrito["limite_sin_transiciones"]["n"], escrito["limite_sin_transiciones"]["convencion"]),
                             (0, "fin"))
            # quinta revisión, mayores 1 y 2: la procedencia (§0), con la huella de su propio programa y la traducción
            tr = escrito["traza"]
            for clave in ("git", "codigo", "contrato", "config", "insumos", "bibliotecas", "python", "hilos",
                          "codigo_red2", "traduccion"):
                self.assertIn(clave, tr)
            self.assertEqual(tr["codigo_red2"]["scripts_modelo_1km/v2/reloj_sinca_v2.py"],
                             hashlib.sha256(Path(rs.__file__).read_bytes()).hexdigest())
            self.assertEqual(tr["traduccion"]["compuerta"], {"archivos": len(self.ra.ARCHIVOS_TRADUCCION),
                                                             "confirmada": True})
            self.assertIn("pandas", tr["bibliotecas"])
            self.assertEqual(tr["insumos"]["politica_temporal"]["sha256"], rs.SHA_POLITICA)
            self.assertEqual(self.escribir(r, raiz)[2], "sin_cambios")
            escribir_derivado(raiz, relojes={("F2", "pm25"): "fijo"})          # otra serie: ya no es la red 2
            with self.assertRaises(SystemExit):
                self.escribir(r, raiz)

    def test_ya_escrito_con_otras_series_se_detiene(self):
        """Quinta revisión, menor 5: escrito el reloj, un derivado completo de las mismas cuatro series con otras
        versiones (corrida terminada) no lo reescribe ni devuelve el resumen viejo: se detiene."""
        import shutil
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            self.assertEqual(self.escribir(r, raiz)[2], "escrito")
            antes = (r.raiz_v2 / rs.NOMBRE_SALIDA / "resumen.json").read_bytes()
            shutil.rmtree(raiz)
            escribir_derivado(raiz, valores=5.0)                             # otras versiones de las mismas series
            with self.assertRaises(SystemExit) as e:
                self.escribir(r, raiz)
            self.assertIn("ya existe con otras series", str(e.exception))
            self.assertEqual((r.raiz_v2 / rs.NOMBRE_SALIDA / "resumen.json").read_bytes(), antes)

    def test_archivos_sin_su_resumen_se_detiene(self):
        """Quinta revisión, menor 5: un veredictos.parquet (o un detalle) sin su resumen.json detiene el reloj."""
        for nombre in ("veredictos.parquet", "detalle_transiciones.csv"):
            with self.subTest(nombre), self.raices() as r:
                datos_red2(r.datos)
                raiz = escribir_derivado(destino_red2(r))
                suelto = r.raiz_v2 / rs.NOMBRE_SALIDA / nombre
                suelto.parent.mkdir(parents=True)
                suelto.write_bytes(b"de una corrida cortada")
                with self.assertRaises(SystemExit) as e:
                    self.escribir(r, raiz)
                self.assertIn("archivos sin su resumen.json", str(e.exception))
                self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA / "resumen.json").exists())

    def test_otra_base_de_zonas_no_escribe(self):
        """Quinta revisión, menor 3: con otra base de zonas el reloj que escribe se detiene antes de leer los maestros y
        las series; sin escribir, informa."""
        from unittest import mock

        def prohibido(*a, **k):
            raise AssertionError("se leyó antes de comprobar la base de zonas")
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            with otra_base_de_zonas():
                with mock.patch.object(self.ra, "maestro_red2", prohibido), \
                        mock.patch.object(rs, "series_con_huella", prohibido), self.assertRaises(SystemExit) as e:
                    self.escribir(r, raiz)
                self.assertIn("base de zonas", str(e.exception))
                self.assertEqual(rs.ejecutar_reloj(r, [raiz], escribir=False)[2], "sin_escribir")
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())

    def test_la_politica_se_lee_por_su_huella(self):
        """Menor 17 (cuarta revisión, menor 14): el reloj que escribe lee la política temporal por su huella; con otra
        política en RUTA_POLITICA se detiene antes de leer las series, sin escribir nada."""
        from unittest import mock
        with self.raices() as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            otra = r.datos / "politica_temporal.json"
            otra.write_bytes(rs.RUTA_POLITICA.read_bytes() + b"\n")
            with mock.patch.object(rs, "RUTA_POLITICA", otra), self.assertRaises(SystemExit) as e:
                self.escribir(r, raiz)
            self.assertIn("huella que cita el bloque R7", str(e.exception))
            self.assertFalse((r.raiz_v2 / rs.NOMBRE_SALIDA).exists())
            self.assertEqual(self.escribir(r, raiz)[2], "escrito")             # con la política de su huella, sí

    def test_la_eleccion_no_depende_de_los_valores(self):
        with tempfile.TemporaryDirectory() as tmp:
            uno = escribir_derivado(Path(tmp) / "a", valores=1.0)
            otro = escribir_derivado(Path(tmp) / "b", valores=987.5)
            datos = Path(tmp) / "data"
            from types import SimpleNamespace
            r = SimpleNamespace(datos=datos)
            region = {"F1": "RM", "C1": "RM", "I1": "RM", "C2": "RM"}
            a, ta, _ = rs.ejecutar_reloj(r, [uno], escribir=False, region_de=region)
            b, tb, _ = rs.ejecutar_reloj(r, [otro], escribir=False, region_de=region)
            pd.testing.assert_frame_equal(ta, tb)                            # los mismos veredictos
            self.assertEqual(a["convencion_civil"], b["convencion_civil"])
            self.assertNotEqual(a["huella_series"], b["huella_series"])      # otros archivos, misma elección


class ConversionTests(unittest.TestCase):
    def test_reloj_fijo_mas_tres_horas(self):
        et, _, verdad = etiquetas(2023, "fijo")
        c = rs.convertir(et, {2023: "reloj_fijo"}, ZONA)
        self.assertTrue((c["ts_utc"].to_numpy("datetime64[ns]") == verdad).all())
        self.assertEqual(set(c["reloj"]), {"fijo"})

    def test_cada_convencion_vuelve_al_utc_verdadero(self):
        for reloj, conv in (("civil_fin", "fin"), ("civil_inicio_mas_1h", "inicio_mas_1h")):
            et, _, verdad = etiquetas(2023, reloj)
            c = rs.convertir(et, {2023: "hora_civil"}, ZONA, conv)
            ts = c["ts_utc"].to_numpy("datetime64[ns]")
            amb = c["qc_hora"].to_numpy() == "civil_ambigua_estandar"
            with self.subTest(convencion=conv):
                self.assertEqual(int(amb.sum()), 1)
                self.assertTrue((ts[~amb] == verdad[~amb]).all())          # fuera de la hora repetida, el verdadero
                # La repetida toma la ocurrencia estándar (UTC−4) y registra la de verano (la primera aparición).
                self.assertEqual(pd.Timestamp(ts[amb][0]), pd.Timestamp(verdad[amb][0]) + pd.Timedelta(hours=1))
                self.assertEqual(pd.Timestamp(c.loc[amb, "ts_utc_alternativo"].iloc[0]), pd.Timestamp(verdad[amb][0]))
                # Con UTC−4 fijo, las horas de verano quedarían una hora corridas.
                mal = rs.utc_fijo(et).to_numpy("datetime64[ns]")
                verano = et.month.isin([1, 2, 3, 10, 11, 12])
                self.assertTrue((mal[verano] - verdad[verano] == np.timedelta64(1, "h")).all())

    def test_las_dos_conversiones_difieren_solo_junto_a_los_cambios(self):
        et, _, _ = etiquetas(2023, "civil_fin")
        a = rs.convertir(et, {2023: "hora_civil"}, ZONA, "fin")["ts_utc"].to_numpy("datetime64[ns]")
        b = rs.convertir(et, {2023: "hora_civil"}, ZONA, "inicio_mas_1h")["ts_utc"].to_numpy("datetime64[ns]")
        distintas = et[a != b]
        self.assertGreater(len(distintas), 0)
        self.assertLessEqual(len(distintas), 4)
        self.assertTrue(set(distintas.normalize()) <= {pd.Timestamp("2023-04-01"), pd.Timestamp("2023-04-02"),
                                                       pd.Timestamp("2023-09-03")})

    def test_sin_convencion_no_convierte_anios_civiles(self):
        et, _, _ = etiquetas(2023, "civil_fin")
        with self.assertRaises(SystemExit):
            rs.convertir(et, {2023: "hora_civil"}, ZONA)

    def test_hora_inexistente_se_desplaza_y_se_marca(self):
        et = pd.Series(pd.to_datetime(["2023-09-02 23:00", "2023-09-03 00:00", "2023-09-03 01:00"]))
        c = rs.utc_civil(et, ZONA, "fin")
        self.assertEqual(list(c["qc_hora"]), ["civil_univoca", "civil_inexistente_desplazada", "civil_univoca"])
        self.assertEqual(c["ts_utc"].iloc[1], c["ts_utc"].iloc[2])           # colisión: se promedia aguas abajo
        self.assertEqual(c["ts_utc"].iloc[0], pd.Timestamp("2023-09-03 02:00"))
        c = rs.utc_civil(pd.Series(pd.to_datetime(["2023-09-03 01:00"])), ZONA, "inicio_mas_1h")
        self.assertEqual(list(c["qc_hora"]), ["civil_inexistente_desplazada"])

    def test_solo_los_anios_civiles_se_convierten(self):
        et = pd.Series(pd.to_datetime(["2022-01-10 12:00", "2023-01-10 12:00"]))
        c = rs.convertir(et, {2022: "reloj_fijo", 2023: "hora_civil"}, ZONA, "fin")
        self.assertEqual(list(c["reloj"]), ["fijo", "civil"])
        self.assertEqual(c["ts_utc"].iloc[0], pd.Timestamp("2022-01-10 15:00"))   # +3 h
        self.assertEqual(c["ts_utc"].iloc[1], pd.Timestamp("2023-01-10 14:00"))   # verano: +3 h − 1 h

    def test_otros_veredictos_siguen_la_regla_general(self):
        et = pd.Series(pd.to_datetime(["2023-01-10 12:00"]))
        for v in ("reloj_fijo_parcial", "sin_evidencia", "sin_transiciones", "reloj_fijo"):
            self.assertEqual(rs.convertir(et, {2023: v}, ZONA)["reloj"].iloc[0], "fijo")


class DerivadoTests(unittest.TestCase):
    def escribir(self, raiz: Path, est: str, pol: str, version: str, since: str, filas: int = 30) -> Path:
        c = raiz / f"estacion={est}" / f"contaminante={pol}" / f"version={version}"
        c.mkdir(parents=True)
        et, rep, _ = etiquetas(2023, "fijo")
        pd.DataFrame({"ts_local": et[:filas], "hora_repetida_en_fuente": rep[:filas]}).to_parquet(c / "observaciones.parquet")
        (c / "manifest.json").write_text(json.dumps({"inputs": {"since": since, "until": None}, "created_utc": "x",
                                                     "files": [{"name": "observaciones.parquet", "rows": filas}]}))
        return c / "observaciones.parquet"

    def test_version_y_varias_raices(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            larga = self.escribir(a, "X1", "no2", "v1", "2000-01-01")
            self.escribir(a, "X1", "no2", "v2", "2026-01-01")
            self.escribir(b, "Y1", "no2", "v1", "2000-01-01")
            series = rs.series_del_derivado([a, b], ("no2",))
            self.assertEqual([(s["estacion"], s["ruta"]) for s in series][0], ("X1", larga))
            self.assertEqual(len(series), 2)
            self.escribir(b, "X1", "no2", "v9", "2000-01-01")
            with self.assertRaises(SystemExit):
                rs.series_del_derivado([a, b], ("no2",))

    def test_verificar_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for est, reloj in (("F1", "fijo"), ("C1", "civil_fin")):
                c = raiz / f"estacion={est}" / "contaminante=pm25" / "version=v"
                c.mkdir(parents=True)
                et, rep, _ = etiquetas(2023, reloj)
                pd.DataFrame({"ts_local": et, "hora_repetida_en_fuente": rep}).to_parquet(c / "observaciones.parquet")
            politica = rs.leer_politica()
            series = rs.series_del_derivado([raiz], ("pm25",))
            tabla, _ = rs.verificar_red(series, {"F1": "RM", "C1": "RM", "Z9": "RM"}, politica, (2023, 2023))
            v = rs.veredictos_por_serie(tabla, "fin")
            self.assertEqual(v[("F1", "pm25")], {2023: "reloj_fijo"})
            self.assertEqual(v[("C1", "pm25")], {2023: "hora_civil"})
            self.assertEqual(rs.veredictos_por_serie(tabla, "inicio_mas_1h")[("C1", "pm25")], {2023: "reloj_fijo_parcial"})
            # Una estación fuera de los maestros no se evalúa.
            tabla, _ = rs.verificar_red(series, {"F1": "RM"}, politica, (2023, 2023))
            self.assertEqual(set(tabla["estacion"]), {"F1"})

    def test_la_serie_se_lee_con_su_huella(self):
        """Ronda 5, menor 3: con las huellas que registró ``series_con_huella``, cada serie se lee desde los bytes cuyo
        sha256 es el registrado (``leer_serie``): una serie reemplazada entre el registro y la lectura detiene el reloj
        (y el panel y el contraste, que leen con la misma función) sin leerla; una serie no registrada, también."""
        import red_ampliada_v2 as ra
        from unittest import mock
        sys.path.insert(0, str(V2 / "tests"))
        from _sintetico_v2 import raices_temporales
        with mock.patch.object(ra, "LISTA_CERRADA", {}), raices_temporales("v2-reloj-huella-") as r:
            datos_red2(r.datos)
            raiz = escribir_derivado(destino_red2(r))
            registro, series = rs.series_con_huella([raiz], r.datos)
            huellas = rs.huellas_de(registro)
            region = {s["estacion"]: "RM" for s in series}
            antes, _ = rs.verificar_red(series, region, rs.leer_politica(), huellas=huellas)
            self.assertEqual(antes.to_csv(index=False), rs.verificar_red(series, region, rs.leer_politica())[0]
                             .to_csv(index=False))                          # los mismos veredictos
            q = carpeta_de_version(raiz, "C2", "pm25") / "observaciones.parquet"
            df = pd.read_parquet(q)
            df[(df["ts_local"] >= pd.Timestamp("2023-04-10")) & (df["ts_local"] < pd.Timestamp("2023-09-01"))] \
                .to_parquet(q)                                               # después de registrar su huella
            with self.assertRaises(SystemExit) as e:
                rs.verificar_red(series, region, rs.leer_politica(), huellas=huellas)
            self.assertIn("C2:pm25", str(e.exception))
            self.assertIn("cambió después de registrar su huella", str(e.exception))
            with self.assertRaises(SystemExit) as e:
                rs.leer_serie(series[0], ["ts_local"], {}, "prueba")
            self.assertIn("no está entre las series registradas", str(e.exception))
            # el reloj que escribe lee con las huellas que acaba de registrar
            import inspect
            self.assertIn("huellas=huellas_de(registro)", inspect.getsource(rs.ejecutar_reloj))

    def test_series_con_huella_exige_el_preparador_t8(self):
        """Menores 22 (tercera revisión), 4 y 8 (cuarta): quien lee el derivado exige, en el manifest.json de la versión
        elegida, el contrato, el afg_lib.py de la v1, el preparador sellado y el Python de amb_v2, y que sea la
        publicación del preparador: files con el sha256 del observaciones.parquet que se lee, la versión de la carpeta
        y digest(inputs), y la estación de la carpeta. Una versión publicada por otro camino, armada fuera de amb_v2 o
        con el parquet reemplazado después de publicarse, no entra."""
        import derivado_red2_v2 as dr
        with tempfile.TemporaryDirectory() as tmp:
            datos = Path(tmp) / "data"
            raiz = escribir_derivado(Path(tmp) / "d", {("F1", "pm25"): "fijo", ("I1", "o3"): "civil_inicio_mas_1h"})
            registro, _ = rs.series_con_huella([raiz], datos, ("pm25", "o3"))
            self.assertEqual(registro["series"][0]["procedencia_afg"],
                             {"python": "3.11.16", "ranking_ast_sha256": "r" * 64, "parser_ast_sha256": "p" * 64})
            carpeta = carpeta_de_version(raiz, "F1", "pm25")
            mani = carpeta / "manifest.json"
            bueno = json.loads(mani.read_text())
            afg_malo = {**bueno["inputs"]["afg_semantics"], "file_sha256": "0" * 64}
            casos = {"otro afg_lib": ({"afg_semantics": afg_malo}, {}, "afg_lib.py no es el de la v1"),
                     "otro preparador": ({"code_sha256": "1" * 64}, {}, "no la publicó el preparador sellado"),
                     "otro contrato": ({}, {"contract": "otro"}, "no declara el contrato"),
                     "Python 3.14.3, el de la v1 (T8)": ({"runtime": {"python": "3.14.3 | v1"}}, {}, "amb_v2"),
                     "inputs alterados": ({"since": "1999-01-01"}, {}, "identidad de la publicación está alterada"),
                     "otra versión declarada": ({}, {"version": "f" * 64}, "declara la versión"),
                     "sin observaciones.parquet en files": ({}, {"files": []}, "no es el que publicó el preparador"),
                     # ronda 4, menor 7: files completo, con filas y esquema, sólo con metadatos
                     "sin solapamientos.parquet en files": ({}, {"files": bueno["files"][:1]},
                                                            "no es el que publicó el preparador"),
                     "otro sha256 de solapamientos": ({}, {"files": [bueno["files"][0], {**bueno["files"][1],
                                                                                          "sha256": "0" * 64}]},
                                                      "solapamientos.parquet no es el que publicó el preparador"),
                     "otras filas": ({}, {"files": [{**bueno["files"][0], "rows": 5}, bueno["files"][1]]},
                                     "filas y su manifest.json declara 5"),
                     "otro esquema": ({}, {"files": [{**bueno["files"][0], "schema_sha256": "e" * 64},
                                                     bueno["files"][1]]}, "el esquema de observaciones.parquet")}
            for nombre, (en_inputs, arriba, mensaje) in casos.items():
                m = copy.deepcopy(bueno)
                m["inputs"].update(en_inputs)
                m.update(arriba)
                mani.write_text(json.dumps(m))
                with self.subTest(nombre), self.assertRaises(SystemExit) as e:
                    rs.series_con_huella([raiz], datos, ("pm25", "o3"))
                self.assertIn(mensaje, str(e.exception))
            # el manifiesto de otra estación, con su propia identidad, en la carpeta de F1
            ajeno = manifiesto_del_preparador(estacion="Z9", files=bueno["files"])
            movida = carpeta.rename(carpeta.with_name(f"version={ajeno['version']}"))
            (movida / "manifest.json").write_text(json.dumps(ajeno))
            with self.assertRaises(SystemExit) as e:
                rs.series_con_huella([raiz], datos, ("pm25", "o3"))
            self.assertIn("no de la carpeta", str(e.exception))
            movida.rename(carpeta)
            mani.write_text(json.dumps(bueno))
            # quinta revisión, menor 9: la misma estación y otro contaminante (una versión de O3 puesta en pm25), con su
            # propia identidad y su files[].sha256 intactos
            otro_pol = manifiesto_del_preparador(estacion="F1", contaminante="o3", files=bueno["files"])
            movida = carpeta.rename(carpeta.with_name(f"version={otro_pol['version']}"))
            (movida / "manifest.json").write_text(json.dumps(otro_pol))
            with self.assertRaises(SystemExit) as e:
                rs.series_con_huella([raiz], datos, ("pm25", "o3"))
            self.assertIn("no de la carpeta", str(e.exception))
            movida.rename(carpeta)
            mani.write_text(json.dumps(bueno))
            self.assertEqual(rs.series_con_huella([raiz], datos, ("pm25", "o3"))[0]["huella_series"],
                             registro["huella_series"])
            # el observaciones.parquet reemplazado después de publicarse (las etiquetas de I1), con su manifiesto intacto
            otra = carpeta_de_version(raiz, "I1", "o3") / "observaciones.parquet"
            (carpeta / "observaciones.parquet").write_bytes(otra.read_bytes())
            with self.assertRaises(SystemExit) as e:
                rs.series_con_huella([raiz], datos, ("pm25", "o3"))
            self.assertIn("no es el que publicó el preparador", str(e.exception))
            mani.unlink()
            with self.assertRaises(SystemExit):                                 # sin manifiesto
                rs.series_con_huella([raiz], datos, ("pm25", "o3"))
        self.assertEqual(dr.CONTRATO, "airpollution.sinca.modelado.v1.0.0")

    def test_la_conversion_usa_zoneinfo(self):
        """Menores 18, 36 y 45 (tercera revisión) y 13 (cuarta): el paso a UTC usa la misma base de zonas que el
        veredicto (ZoneInfo); utc_civil dice qué tipo de zona usó de verdad y base_de_zonas registra eso, no una muestra
        aparte; el cuerpo de utc_civil localiza con tz = ZoneInfo(zona)."""
        from unittest import mock
        serie = pd.Series(pd.to_datetime(["2023-01-10 12:00"]))
        c = rs.utc_civil(serie, ZONA, "fin")
        self.assertEqual(c["ts_utc"].iloc[0], pd.Timestamp("2023-01-10 14:00"))
        self.assertEqual(c.attrs["biblioteca_zona"], "zoneinfo")
        base = rs.base_de_zonas([ZONA], (2023, 2023))
        self.assertEqual(base["conversion"]["biblioteca"], "zoneinfo")
        with mock.patch.object(rs, "ZoneInfo", lambda zona: zona):         # la zona como texto: pandas usaría pytz
            self.assertNotEqual(rs.utc_civil(serie, ZONA, "fin").attrs["biblioteca_zona"], "zoneinfo")
        arbol = ast.parse(Path(rs.__file__).read_text(encoding="utf-8"))
        f = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == "utc_civil")
        tz = [n.value for n in ast.walk(f) if isinstance(n, ast.Assign)
              and any(isinstance(x, ast.Name) and x.id == "tz" for x in n.targets)]
        self.assertEqual(len(tz), 1)
        self.assertEqual(ast.dump(tz[0]), ast.dump(ast.parse("ZoneInfo(zona)", mode="eval").body))
        localiza = [n for n in ast.walk(f) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "tz_localize"
                    and not (isinstance(n.args[0], ast.Constant) and n.args[0].value is None)]   # no las de quitar
        self.assertEqual(len(localiza), 3)
        self.assertTrue(all(isinstance(n.args[0], ast.Name) and n.args[0].id == "tz" for n in localiza))

    def test_politica_con_su_huella(self):
        p, sha = rs.leer_politica_con_huella()
        self.assertEqual(sha, rs.SHA_POLITICA)
        self.assertEqual(rs.zona_de("RXII", p), "America/Punta_Arenas")
        self.assertEqual(rs.zona_de("RXI", p), "America/Coyhaique")
        self.assertEqual(rs.zona_de("RM", p), "America/Santiago")


if __name__ == "__main__":
    unittest.main()
