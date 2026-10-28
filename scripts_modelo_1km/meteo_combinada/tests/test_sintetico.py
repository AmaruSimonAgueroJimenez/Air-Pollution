"""Pruebas de sintetico.py (generadores independientes para S1-S16; §9 del texto, §5 del diseño).

Dueño: I5 (ola 1). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Todo lo sintético va en carpetas temporales. Ningún dato DMC, nada bajo /Volumes, ni SINCA, NASADEM ni GHS-POP
reales. Leen, sin escribir, código fijado y del reloj (descargador, adaptador, dmc_features, reloj_dmc.politica,
reloj_dmc.sintetico) y, por AST, los descargadores de SINCA; si falta un archivo o cambió de huella, la prueba se
omite con el motivo y no se da por aprobada.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zipfile  # noqa: E402
from datetime import date, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import sintetico as S  # noqa: E402
from meteo_combinada import tipos  # noqa: E402

AP = _RAIZ.parent
_PAQUETE = _RAIZ / "meteo_combinada"
_RUTA_DESCARGADOR = AP / "scripts_pipeline" / "descargar_meteo_chile_horaria.py"
_RUTA_DESCARGADOR_SINCA = AP / "scripts_pipeline" / "descargar_sinca_meteorologia.py"
# B-H23: la huella de M0 (APH/auditoria/20261023/meteo_combinada/m0/huellas_m0.json, «codigo_citado»).
SHA_DESCARGADOR_SINCA = "0942c4d071cefffb95da76d2b010c981ef126858ea7b3c028ef3c7c23a51b145"
_RUTA_COMUN_MODELO = _RAIZ / "_comun_modelo.py"
SHA_COMUN_MODELO = "a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4"
_V2 = _RAIZ / "v2"


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _descargador(prueba):
    from reloj_dmc import fijados
    if not _RUTA_DESCARGADOR.is_file() or _sha(_RUTA_DESCARGADOR) != S.SHA_DESCARGADOR:
        prueba.skipTest("el descargador 578fa26e… falta o cambió de huella; no se da por aprobada")
    return fijados.cargar_descargador(AP, S.SHA_DESCARGADOR)


def _adaptador_y_dmc(prueba):
    from reloj_dmc import fijados
    for ruta, sha in ((AP / fijados.RUTA_ADAPTADOR, fijados.SHA_ADAPTADOR),
                      (AP / fijados.RUTA_DMC_FEATURES, fijados.SHA_DMC_FEATURES)):
        if not ruta.is_file() or _sha(ruta) != sha:
            prueba.skipTest(f"{ruta.name} falta o cambió de huella; no se da por aprobada")
    return fijados.cargar_adaptador(AP), fijados.cargar_dmc_features(AP)


def _horas(desde: str, n: int) -> pd.DatetimeIndex:
    return pd.date_range(desde, periods=n, freq="h")


_APH = AP.parent / "Air-Pollution-Health-Chile"
_U = None


def _umbrales(prueba):
    """Los umbrales anclados en M0 (sólo el texto y el JSON de APH, con sus huellas); sin ellos, la prueba se omite."""
    global _U
    from meteo_combinada import umbrales
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            prueba.skipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


# Series de S4 de la ola 1, con la semilla del protocolo (20261023): filas y sumas (math.fsum) de Ts, QFE, QFF y p_F.
# Se calcularon con dt_clima_k = 0 y ciclo_diario_m = 0 después de comprobar que esas series eran, bit a bit (sha256
# de los bytes de cada columna), las del código de la ola 1, sin las señales de SIN-20.
_SUMAS_OLA_1 = {
    ("estacionaria", 500.0): (52608, 618012.6955019867, 50235283.69252259, 53322840.95754952, 50236608.608852394),
    ("estacionaria", 2500.0): (52608, -65783.88338770233, 39300554.56142156, 53324432.98754492, 39298892.886326544),
    ("traslado", 500.0): (52608, 618344.9670675127, 50148000.60404329, 53277122.162623376, 50193089.713505544),
    ("traslado", 2500.0): (52608, -65788.87951529588, 39259951.6162631, 53316899.650147475, 39295261.566554174),
    ("barometro", 500.0): (52608, 618131.2782340217, 50241808.14471768, 53329646.4865729, 50202124.85736609),
    ("barometro", 2500.0): (52608, -65704.58825020067, 39343656.02815525, 53382685.289185196, 39303623.91876689),
    ("reduccion", 500.0): (52608, 618253.3964745401, 50225483.44072911, 53311540.71860399, 50224271.15520859),
    ("reduccion", 2500.0): (52608, -65280.2418498973, 39302014.19950505, 53322457.422267094, 39303798.578811504),
    ("horario", 500.0): (40552, 512397.8519580009, 38704793.87776592, 41076077.34394953, 38706551.316780776),
    ("horario", 2500.0): (40552, -14517.614569210493, 30279586.948089752, 41044432.8433651, 30279122.26950735),
}


class PruebasIndependencia(unittest.TestCase):
    def test_no_importa_el_paquete_ni_el_reloj(self):
        """§1 del diseño (AST): sintetico no importa meteo_combinada ni reloj_dmc."""
        arbol = ast.parse((_PAQUETE / "sintetico.py").read_text(encoding="utf-8"))
        nombres = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                self.assertEqual(nodo.level, 0, "sin importaciones relativas")
                nombres.add((nodo.module or "").split(".")[0])
        self.assertFalse(nombres & {"meteo_combinada", "reloj_dmc", "_comun_modelo", "_common"}, nombres)

    def test_esquemas_iguales_a_tipos(self):
        """Las copias de los esquemas son las de tipos: columnas, orden, tipos y versión."""
        for nombre, (version, columnas) in S.ESQUEMAS_COPIADOS.items():
            with self.subTest(esquema=nombre):
                esquema = tipos.ESQUEMAS[nombre]
                self.assertEqual(list(columnas.items()), list(esquema.items()))
                self.assertEqual(version, esquema.version)
        self.assertEqual(S.LULC, tipos.LULC)

    def test_rechaza_volumes_y_repositorios_sin_tocar_el_disco(self):
        """Ninguna escritura bajo /Volumes ni en los repositorios (ruta léxica primero)."""
        cat = S.catalogo_pixeles(-33.0, -71.0, 1, 2)
        campos = {"t2m": np.full((1, 2), 290.0)}
        for ruta in (Path("/Volumes/Datos/meteo_combinada_prueba.nc"), Path("/volumes/x/y.nc"),
                     AP / "meteo_combinada_prueba_que_no_debe_existir.nc",
                     _RAIZ / "meteo_combinada" / "no_debe_existir.nc"):
            with self.subTest(ruta=ruta.name), self.assertRaises(ValueError):
                S.mes_era5_netcdf(ruta, campos, S.horas_del_mes(2019, 1)[:1], cat.pixel_id)
            self.assertFalse(ruta.exists() if not str(ruta).casefold().startswith("/volumes") else False)
        with self.assertRaises(ValueError):
            S.GuardaFalsaMC(Path("/Volumes/Datos/DMC"))
        with self.assertRaises(ValueError):
            S.sinca_sintetico(AP / "sinca_prueba_que_no_debe_existir")
        self.assertFalse((AP / "sinca_prueba_que_no_debe_existir").exists())

    def test_solo_bajo_la_carpeta_temporal_del_sistema(self):
        """H13 (SIN-18): un destino fuera de tempfile.gettempdir() se rechaza (LOCAL, /tmp, la carpeta personal) y un
        enlace en una carpeta temporal que lleva fuera también; lo de adentro pasa."""
        local = Path.home() / "Asesorias_Data_local" / "AirPollution" / "modelado_1km" / "grilla_1km" / "no_debe_existir.json"
        for ruta in (local, Path("/tmp") / "meteo_combinada_no_debe_existir.json",
                     Path.home() / "meteo_combinada_no_debe_existir.json"):
            with self.subTest(ruta=ruta.name), self.assertRaises(ValueError):
                S.destino_temporal(ruta)
            self.assertFalse(ruta.exists())
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(S.destino_temporal(Path(tmp) / "a" / "b.json"), Path(tmp) / "a" / "b.json")
            enlace = Path(tmp) / "afuera"
            enlace.symlink_to(Path.home())
            with self.assertRaises(ValueError):
                S.destino_temporal(enlace / "x.json")
            with self.assertRaises(ValueError):
                S.sinca_sintetico(enlace / "sinca")
        self.assertEqual(S.carpeta_temporal(), Path(os.path.realpath(tempfile.gettempdir())))


class PruebasPortalDMC(unittest.TestCase):
    def test_constantes_del_descargador(self):
        d = _descargador(self)
        self.assertEqual(tuple(d.RAW_COLUMNS), S.COLUMNAS_CRUDAS)
        self.assertEqual(set(S.ELEMENTOS_INVENTARIO) - set(d.INVENTORY_IDS), set())

    def test_hoja_html_paridad_con_el_reloj(self):
        """Mismo HTML que reloj_dmc.sintetico.html_informe con los mismos textos, y la rejilla de filas_del_mes
        reproduce los textos del reloj (SIN-1)."""
        from reloj_dmc import sintetico as RS
        d = _descargador(self)
        caso = RS.caso_simple(codigo="900001", reloj="F(0)")
        textos = RS.textos_crudos(caso, 2019, 9)
        self.assertEqual(S.hoja_html(caso.codigo, 2019, 9, textos, d), RS.html_informe(caso, 2019, 9, d))
        L = [datetime(2019, 9, int(f[0]), int(f[1][:2])) for f in textos]
        columnas = {c: [f[k + 2] for f in textos] for k, c in enumerate(S.COLUMNAS_TEXTO)}
        est = S.estacion_sintetica(caso.codigo, caso.lat, caso.lon, caso.alt_m, L, **columnas)
        self.assertEqual(S.filas_del_mes(est, 2019, 9), [list(f) for f in textos])
        filas, meta = d.parse_report(S.hoja_html(caso.codigo, 2019, 9, textos, d), caso.codigo, 2019, 9)
        self.assertGreater(len(filas), 0)
        self.assertGreaterEqual(meta["duplicate_display_rows_removed"], len(filas))     # la tabla va dos veces

    def test_formato_de_los_textos(self):
        r = S.reportes_desde(_horas("2019-09-01", 3), Ts=[-0.04, 12.345, float("nan")],
                             wind_direction_instant=[270, 0, "990"], wind_speed_instant=[10, 5, -5],
                             relative_humidity=[55.4, 100, None], RR06=["s/p", 0.0, 12.0])
        self.assertEqual(list(r["Ts"]), ["0.0", "12.3", ""])
        self.assertEqual(list(r["wind_direction_instant"]), ["270", "000", "990"])
        self.assertEqual(list(r["wind_speed_instant"]), ["010", "005", "-05"])
        self.assertEqual(list(r["relative_humidity"]), ["55", "100", ""])
        self.assertEqual(list(r["RR06"]), ["s/p", "0.0", "12.0"])
        with self.assertRaises(ValueError):
            S.reportes_desde(_horas("2019-09-01", 2).append(_horas("2019-09-01", 1)), Ts=1.0)
        with self.assertRaises(ValueError):
            S.reportes_desde(_horas("2019-09-01", 1), Nubes=1)
        u = np.array(["2019-09-01T04:00", "2019-09-01T05:00"], dtype="datetime64[ns]")
        self.assertEqual(list(S.etiquetas_desde_utc(u, -240)),
                         list(np.array(["2019-09-01T00:00", "2019-09-01T01:00"], dtype="datetime64[ns]")))

    def test_descarga_por_run_download_y_lectura_con_el_codigo_fijado(self):
        """run_download con el cliente y la guarda falsos deja artefactos que el adaptador lee y que cargar_dmc
        normaliza con una política mínima; DD 270 con 10 kt da u = +5,144 m/s (S11) y nada sale de la carpeta."""
        d = _descargador(self)
        adaptador, dmc_features = _adaptador_y_dmc(self)
        L = _horas("2019-09-01", 30 * 24)
        n = len(L)
        est = S.estacion_sintetica("900001", -33.45, -70.66, 520.0, L, Ts=np.full(n, 15.0), Td=np.full(n, 5.0),
                                   relative_humidity=np.full(n, 50.0), wind_direction_instant=np.full(n, 270.0),
                                   wind_speed_instant=np.full(n, 10.0), QFE=np.full(n, 955.0),
                                   QFF=np.full(n, 1015.0), RR06=["s/p"] * n)
        with tempfile.TemporaryDirectory() as tmp:
            dmc = S.fabricar_descarga([est], Path(tmp), d, "2019-09-01", "2019-09-30")
            manifiestos = S.manifiestos_de(dmc)
            self.assertEqual(list(manifiestos), ["900001"])
            (manifiesto,) = manifiestos["900001"]
            payload, meta = adaptador.leer_artefacto(manifiesto)
            self.assertEqual(len(payload["rows"]), n)
            self.assertEqual(S.artefactos_de_descarga(dmc), {"900001": [meta["content_sha256"]]})
            politica = _politica_minima("900001")
            larga, meta_l = dmc_features.cargar_dmc([manifiesto], [politica], adapter_sha256=adaptador_sha())
            for c in tipos.COLUMNAS_LARGA_DMC:
                self.assertIn(c, larga.columns)
            for c in tipos.META_LARGA_DMC:
                self.assertIn(c, meta_l)
            ts = larga[larga.variable == "Ts"]
            self.assertTrue(ts.usable.all())
            u = larga[larga.variable == "wind_u"]
            self.assertTrue(u.usable.all())
            self.assertAlmostEqual(float(u.value.iloc[0]), 10 * 1852 / 3600, places=9)
            v = larga[larga.variable == "wind_v"]
            self.assertLess(abs(float(v.value.iloc[0])), 1e-9)
            utc = pd.Timestamp(ts.timestamp_utc.iloc[0])
            self.assertEqual(utc.tz_convert(None), pd.Timestamp("2019-09-01T04:00"))
            fuera = [p for p in Path(tmp).rglob("*") if p.is_file() and Path(tmp).resolve() not in p.resolve().parents]
            self.assertEqual(fuera, [])

    def test_alterar_artefacto_para_los_abortos_de_s15(self):
        """SIN-3: un código QC presente, puesto en el artefacto ya descargado, aborta cargar_dmc (ValueError)."""
        d = _descargador(self)
        adaptador, dmc_features = _adaptador_y_dmc(self)
        L = _horas("2019-09-01", 48)
        est = S.estacion_sintetica("900002", -33.45, -70.66, 520.0, L, Ts=np.full(48, 15.0))
        with tempfile.TemporaryDirectory() as tmp:
            dmc = S.fabricar_descarga([est], Path(tmp), d, "2019-09-01", "2019-09-30")
            (manifiesto,) = S.manifiestos_de(dmc)["900002"]

            def con_codigo(p):
                p["rows"][0]["fields"]["Ts"]["source_qc"] = "1"
                return p
            sha = S.alterar_artefacto(manifiesto, con_codigo)
            _, meta = adaptador.leer_artefacto(manifiesto)
            self.assertEqual(meta["content_sha256"], sha)
            with self.assertRaises(ValueError):
                dmc_features.cargar_dmc([manifiesto], [_politica_minima("900002")], adapter_sha256=adaptador_sha())


def adaptador_sha() -> str:
    from reloj_dmc import fijados
    return fijados.SHA_ADAPTADOR


def _politica_minima(codigo: str) -> dict:
    """Una política de lectura mínima (reloj F(−4), coordenadas, mediciones y calidad de Ts y del viento)."""
    desde, hasta = "2019-09-01T00:00:00", "2019-09-30T23:00:00"
    base = {"verified": True, "source": "prueba sintetica", "valid_from": desde, "valid_to": hasta}
    medicion = {**base, "statistic": "instantaneous", "interval_minutes": 0}

    def calidad(unidad, a, b):
        return {**base, "unit": unidad, "method": "documented_numeric_checks", "accepted_source_codes": [],
                "allow_unknown_source_qc": True, "minimum": float(a), "maximum": float(b)}
    return {"station_code": codigo, "valid_from": desde, "valid_to": hasta,
            "clock": {**base, "timestamp_semantics": "instantaneous", "fixed_offset_minutes": -240},
            "coordinates": {**base, "latitude": -33.45, "longitude": -70.66},
            "measurements": {v: dict(medicion) for v in ("Ts", "wind_speed_instant", "wind_direction_instant")},
            "quality": {"Ts": calidad("degC", -39, 50), "wind_speed_instant": calidad("m/s", 0, 50),
                        "wind_direction_instant": calidad("degree", 0, 360)}}


class PruebasPoliticaReloj(unittest.TestCase):
    def test_constantes_del_reloj(self):
        from reloj_dmc import fijados, politica, tablas
        self.assertEqual(S.ESQUEMA_POLITICA_RELOJ, politica.ESQUEMA_POLITICA)
        self.assertEqual(S.CLAVES_POLITICA_RELOJ, politica.CLAVES_POLITICA)
        self.assertEqual(S.RUTA_PUBLICACION_RELOJ, politica.RUTA_PUBLICACION_AP)
        self.assertEqual((S.ARCHIVO_POLITICA, S.ARCHIVO_INFORME, S.ARCHIVO_ARTEFACTOS),
                         (politica.ARCHIVO_POLITICA, politica.ARCHIVO_INFORME, politica.ARCHIVO_ARTEFACTOS))
        self.assertEqual(S.SHA_ANEXO_A_RELOJ, tablas.SHA_ANEXO_A)
        self.assertEqual(S.SHA_ADAPTADOR, fijados.SHA_ADAPTADOR)
        self.assertEqual(S.SHA_DESCARGADOR, fijados.VERSIONES_ADMITIDAS_C0[-1])

    def test_validar_regla_acepta_la_politica_sintetica(self):
        """validar_regla_reloj_dmc acepta una regla publicada con un artefacto evaluado, y rechaza un artefacto que no
        está, el de otra estación, una regla alterada y un tramo sin veredicto (cada caso en su carpeta, MC-40)."""
        from reloj_dmc import politica
        sha_a, sha_b = hashlib.sha256(b"a").hexdigest(), hashlib.sha256(b"b").hexdigest()
        reglas = {"900001": [{"tramo": "1.1", "valid_from": "2019-01-01T00:00:00", "valid_to": "2019-12-31T23:00:00",
                              "minutos": -240, "veredicto": "F(-4)"},
                             {"tramo": "2.1", "valid_from": "2020-01-01T00:00:00", "valid_to": "2020-12-31T23:00:00",
                              "minutos": 0, "veredicto": None}],
                  "900002": [{"tramo": "1.1", "valid_from": "2019-01-01T00:00:00", "valid_to": "2019-12-31T23:00:00",
                              "minutos": 0, "veredicto": "F(0)"}]}
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.politica_reloj_sintetica(Path(tmp) / "caso1", {"900001": [sha_a], "900002": [sha_b]}, reglas,
                                              coordenadas_inconsistentes=["900002"])
            pol = json.loads(ruta.read_text(encoding="utf-8"))
            self.assertEqual(tuple(sorted(pol)), tuple(sorted(S.CLAVES_POLITICA_RELOJ)))
            r1, r2, r3 = pol["politicas_reloj"]
            politica.validar_regla_reloj_dmc(r1, sha_a, politica_ruta=ruta)
            politica.validar_regla_reloj_dmc({**r3, "quality": {}, "coordinates": {}}, sha_b, politica_ruta=ruta)
            for regla, sha in ((r1, hashlib.sha256(b"c").hexdigest()), (r1, sha_b), (r2, sha_a),
                               ({**r1, "valid_to": "2019-06-30T23:00:00"}, sha_a)):
                with self.subTest(tramo=regla["clock"]["source"][-90:]), self.assertRaises(ValueError):
                    politica.validar_regla_reloj_dmc(regla, sha, politica_ruta=ruta)
            rutas = S.rutas_politica_sintetica(Path(tmp) / "caso1")
            informe = json.loads(rutas["informe"].read_text(encoding="utf-8"))
            self.assertEqual(informe["coordenadas_inconsistentes"], ["900002"])
            registro = json.loads(rutas["registro"].read_text(encoding="utf-8"))
            self.assertEqual(registro["sha256_politica"], _sha(ruta))
            self.assertEqual(registro["sha256_artefactos"], _sha(rutas["artefactos"]))
            self.assertEqual(json.loads(gzip.decompress(rutas["artefactos"].read_bytes())),
                             [{"artefacto_sha256": sha_a, "codigo": "900001"},
                              {"artefacto_sha256": sha_b, "codigo": "900002"}])
            # H14 (SIN-5): el registro trae rutas, huellas y el commit; las banderas son de la política.
            self.assertEqual(set(registro), {"schema", "politica_ruta", "sha256_politica", "artefactos_ruta",
                                             "sha256_artefactos", "commit_c5", "errata_confirmada"})
            campos = {f.name for f in tipos.RegistroReloj.__dataclass_fields__.values()}
            self.assertEqual(campos - set(registro) - {"ruta"}, {"post_hoc", "errata_post_c4"})
            self.assertEqual((pol["post_hoc"], pol["errata_post_c4"]), (False, False))
            # Un caso con −240 y veredicto F(0): la comprobación 1 lo rechaza (otra carpeta).
            malo = S.politica_reloj_sintetica(Path(tmp) / "caso2", {"900003": [sha_a]},
                                              {"900003": [{"tramo": "1.1", "valid_from": "2019-01-01T00:00:00",
                                                           "valid_to": "2019-12-31T23:00:00", "minutos": -240,
                                                           "veredicto": "F(0)"}]},
                                              post_hoc=True, alterar_registro={"sha256_politica": "0" * 64})
            regla = json.loads(malo.read_text(encoding="utf-8"))["politicas_reloj"][0]
            with self.assertRaises(ValueError):
                politica.validar_regla_reloj_dmc(regla, sha_a, politica_ruta=malo)
            reg2 = json.loads(S.rutas_politica_sintetica(Path(tmp) / "caso2")["registro"].read_text(encoding="utf-8"))
            self.assertEqual(reg2["sha256_politica"], "0" * 64)
            self.assertNotIn("post_hoc", reg2)
            self.assertIs(json.loads(malo.read_text(encoding="utf-8"))["post_hoc"], True)


class PruebasEra5Land(unittest.TestCase):
    def test_mes_en_el_formato_real(self):
        """SIN-6: tiempo int64 en segundos desde 1970 UTC, proleptic_gregorian; variables float32 tiempo × píxel sin
        empaquetar; NaN se conserva; las unidades malas cambian valores y no el atributo."""
        import netCDF4
        cat = S.catalogo_pixeles(-33.0, -71.0, 2, 3)
        t = S.horas_del_mes(2019, 2)
        T, P = len(t), len(cat)
        campos = {"t2m": np.full((T, P), 290.0), "sp": np.full((T, P), 95000.0), "tp": np.zeros((T, P))}
        campos["t2m"][0, 0] = np.nan
        with tempfile.TemporaryDirectory() as tmp:
            for unidades in S.UNIDADES_MALAS:
                ruta = S.mes_era5_netcdf(Path(tmp) / f"{unidades}.nc", campos, t, cat.pixel_id, unidades=unidades)
                with netCDF4.Dataset(ruta) as nc:
                    nc.set_auto_maskandscale(False)
                    self.assertEqual(nc.temporal_operation, S.OPERACION_TEMPORAL_ERA5L)
                    self.assertEqual(float(nc.spatial_resolution_degrees), 0.1)
                    tv = nc["time"]
                    self.assertEqual((tv.dtype, tv.units, tv.calendar),
                                     (np.dtype("int64"), S.UNIDADES_TIEMPO_ERA5L, "proleptic_gregorian"))
                    s = np.asarray(tv[:])
                    inicio = int(np.datetime64("2019-02-01T00", "s").astype(np.int64))
                    self.assertTrue(np.array_equal(s, inicio + np.arange(T) * 3600))
                    self.assertEqual(list(np.asarray(nc["pixel_id"][:])), list(cat.pixel_id))
                    np.testing.assert_allclose(np.asarray(nc["latitude"][:]), cat.latitude)
                    for var in ("t2m", "sp", "tp"):
                        v = nc[var]
                        self.assertEqual((v.dimensions, v.dtype), (("time", "pixel"), np.dtype("float32")))
                        self.assertFalse({"scale_factor", "add_offset", "missing_value", "valid_min", "valid_max",
                                          "valid_range"} & set(v.ncattrs()))
                        self.assertEqual(v.units, S.UNIDADES_ERA5L[var])
                    x = np.asarray(nc["t2m"][:])
                    self.assertTrue(np.isnan(x[0, 0]))
                    esperado_t = 290.0 - (273.15 if unidades == "t2m_celsius" else 0.0)
                    self.assertAlmostEqual(float(x[1, 1]), esperado_t, places=4)
                    esperado_sp = 950.0 if unidades == "sp_hpa" else 95000.0
                    self.assertAlmostEqual(float(nc["sp"][0, 0]), esperado_sp, places=2)
        with self.assertRaises(ValueError):
            S.mes_era5_netcdf(Path("x.nc"), campos, t, cat.pixel_id, unidades="kelvin")

    def test_hora_no_nativa_queda_en_el_archivo(self):
        """S12: el generador escribe una hora que no es HH:00 tal cual (el lector propio debe rechazarla)."""
        import netCDF4
        t = np.array(["2019-01-01T00:00", "2019-01-01T01:30"], dtype="datetime64[s]")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.mes_era5_netcdf(Path(tmp) / "m.nc", {"t2m": np.full((2, 1), 290.0)}, t, [4430890])
            with netCDF4.Dataset(ruta) as nc:
                self.assertEqual(int(nc["time"][1]) % 3600, 1800)

    def test_tp_acumulado_desde_las_00_utc(self):
        """El acumulado de ERA5-Land: 01 UTC = la primera hora; 00 UTC = el paso 24 del día anterior."""
        t = np.arange(np.datetime64("2019-01-01T01"), np.datetime64("2019-01-03T01"), np.timedelta64(1, "h"))
        lluvia = np.ones(len(t)) * 0.001
        tp = S.tp_acumulado(t, lluvia)
        self.assertAlmostEqual(tp[0], 0.001)                         # 01 UTC del 1 de enero
        self.assertAlmostEqual(tp[23], 0.024)                        # 00 UTC del 2 de enero: paso 24
        self.assertAlmostEqual(tp[24], 0.001)                        # 01 UTC del 2 de enero
        dif = np.r_[tp[0], np.diff(tp)]
        dif[(t.astype("datetime64[h]").astype(np.int64) % 24) == 1] = tp[(t.astype("datetime64[h]").astype(np.int64) % 24) == 1]
        np.testing.assert_allclose(dif, lluvia)

    def test_catalogo_de_pixeles(self):
        """SIN-7: pixel_id = i·3.600 + j, como el sintético del reloj y el geopotencial."""
        from reloj_dmc import sintetico as RS
        cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        self.assertEqual(tuple(cat.columns), S.COLUMNAS_CATALOGO_PIXELES)
        for fila in cat.itertuples():
            pid, lat, lon, i, j = RS._pixel_de(fila.latitude, fila.longitude)
            self.assertEqual((pid, lat, lon, i, j), (fila.pixel_id, fila.latitude, fila.longitude,
                                                     fila.lat_index_global, fila.lon_index_global))
        self.assertEqual(len(set(cat.pixel_id)), 12)

    def test_geopotencial_alineado_y_corrido(self):
        """SIN-8 y S13: con la grilla en su lugar, z/9,80665 del NetCDF en cada píxel es el z_m del parquet; corrida
        una fila, difiere."""
        import netCDF4
        cat = S.catalogo_pixeles(-33.0, -71.0, 3, 4)
        z = np.linspace(100.0, 1200.0, len(cat))
        with tempfile.TemporaryDirectory() as tmp:
            for corrimiento, iguales in ((0, True), (1, False)):
                r = S.geopotencial_sintetico(Path(tmp) / f"c{corrimiento}", cat, z, corrimiento_filas=corrimiento)
                derivado = pd.read_parquet(r["altitud"])
                self.assertEqual(list(derivado.columns), ["pixel_id", "lat_index_global", "lon_index_global",
                                                          "latitude", "longitude", "z_m2_s2", "z_m"])
                with netCDF4.Dataset(r["geopotencial"]) as nc:
                    self.assertEqual(nc["z"].units, "m**2 s**-2")
                    lat = np.asarray(nc["latitude"][:])
                    lon = np.asarray(nc["longitude"][:])
                    rej = np.ma.filled(nc["z"][0], np.nan)
                ii = [int(np.argmin(np.abs(lat - la))) for la in derivado.latitude]
                jj = [int(np.argmin(np.abs(lon - lo))) for lo in derivado.longitude]
                desde_nc = rej[ii, jj] / S.G0
                cerca = np.isfinite(desde_nc) & (np.abs(desde_nc - derivado.z_m.to_numpy()) <= 0.001)
                self.assertEqual(bool(cerca.all()), iguales)
                np.testing.assert_allclose(derivado.z_m.to_numpy(), z, atol=1e-3)


class PruebasTeselas(unittest.TestCase):
    def test_nasadem_pixel_punto_con_mascara(self):
        """SIN-9: GeoTIFF int16 EPSG:4326 de 1/3.600°, centros en múltiplos exactos, nodata y máscara interna."""
        import rasterio
        with tempfile.TemporaryDirectory() as tmp:
            ruta = S.tesela_nasadem(Path(tmp) / "t.tif", lambda la, lo: 1000.0 + 100000.0 * (lo + 70.7),
                                    mascara=lambda la, lo: lo < -70.6795, oeste=-70.70, norte=-33.40, filas=60,
                                    columnas=90)
            with rasterio.open(ruta) as ds:
                self.assertEqual((ds.count, ds.dtypes[0], ds.crs.to_epsg(), ds.nodata), (1, "int16", 4326, -32768))
                self.assertAlmostEqual(abs(ds.transform.a), 1 / 3600, places=12)
                x, y = ds.xy(0, 0)                       # centro del primer píxel
                self.assertAlmostEqual(x, -70.70, places=9)
                self.assertAlmostEqual(y, -33.40, places=9)
                datos = ds.read(1)
                mascara = ds.dataset_mask() > 0
                self.assertEqual(ds.tags()["vertical_units"], "meters")
            lon = -70.70 + np.arange(90) * (1 / 3600)
            dentro = lon < -70.6795
            self.assertTrue((mascara[:, dentro]).all() and not (mascara[:, ~dentro]).any())
            self.assertTrue((datos[:, ~dentro] == -32768).all())
            self.assertEqual(int(datos[0, 0]), 1000)
            self.assertEqual(S.id_tesela_nasadem(-34, -71), "s34w071")

    def test_ghs_en_mollweide_dentro_de_un_zip(self):
        """SIN-10: float32 en ESRI:54009 de 100 m, nodata −200, alineado a la rejilla de teselas, legible con /vsizip/."""
        import rasterio
        with tempfile.TemporaryDirectory() as tmp:
            nombre = S.nombre_tesela_ghs(12, 13) + ".zip"
            ruta = S.tesela_ghs(Path(tmp) / nombre, lambda la, lo: np.where(la > -33.45, 10.0, np.nan), filas=40,
                                columnas=50)
            with zipfile.ZipFile(ruta) as z:
                self.assertEqual(z.namelist(), [S.nombre_tesela_ghs(12, 13) + ".tif"])
            with rasterio.open(f"/vsizip/{ruta}/{S.nombre_tesela_ghs(12, 13)}.tif") as ds:
                self.assertEqual((ds.dtypes[0], ds.nodata, ds.res), ("float32", -200.0, (100.0, 100.0)))
                self.assertIn("Mollweide", ds.crs.to_wkt())
                self.assertAlmostEqual(((ds.transform.c - S.GHS_X0) / 100.0) % 1.0, 0.0)
                self.assertAlmostEqual(((S.GHS_Y0 - ds.transform.f) / 100.0) % 1.0, 0.0)
                datos = ds.read(1)
            self.assertTrue((datos == 10.0).any() and (datos == -200.0).any())


class PruebasGrillaYVerdad(unittest.TestCase):
    def test_grilla(self):
        g = S.grilla(30, (13101, 13102, 13103))
        self.assertEqual(list(g["celdas"].columns), ["celda", "lat", "lon", "cod_comuna", "aoi_id", "origen", "codregion",
                                                     "region_rellenada_por_vecino", "macrozona", "macrozona_cod"])
        self.assertEqual(g["celdas"]["celda"].is_unique, True)
        self.assertEqual(sorted(g["celdas"]["cod_comuna"].unique()), [13101, 13102, 13103])
        self.assertEqual(set(g["estaticas_lulc"]["anio"]), {2015, 2020})
        tipos.validar_esquema(g["estaticas_mc"], tipos.ESQUEMA_ESTATICAS_CELDA, nombre="estaticas_mc")
        self.assertEqual(g["estaticas_mc"].attrs["esquema"], tipos.ESQUEMA_ESTATICAS_CELDA.version)
        self.assertEqual(list(g["pesos"].columns), ["celda", "anio", "cod_comuna", "pob_ghs", "w_ghs", "w_ur", "w_dasim",
                                                    "ghs_respaldo_ur"])
        self.assertTrue((g["pesos"]["w_ghs"] == 0).any() and (g["pesos"]["w_ghs"] > 0).any())
        e = g["enlaces_productos"]
        self.assertTrue((e["era5land_dist_km"] < 8).all())
        self.assertEqual(S.grilla(10, 2)["comunas"], (13101, 13102))
        self.assertEqual(set(g["celdas"]["macrozona"]), {"centro"})
        self.assertEqual(set(g["celdas"]["macrozona_cod"]), {2})

    def test_macrozonas_de_comun_modelo(self):
        """SIN-19 (TIP-8, D9): MACROZONA_REGION y MACROZONA_CODIGO son los de _comun_modelo (AST, a83c0384…); las celdas
        con cod_comuna = 0 quedan «sin_region» (5), que no es macrozona."""
        from reloj_dmc import fijados
        if not _RUTA_COMUN_MODELO.is_file() or _sha(_RUTA_COMUN_MODELO) != SHA_COMUN_MODELO:
            self.skipTest("_comun_modelo.py falta o cambió de huella; no se da por aprobada")
        fuente = fijados.extraer_por_ast(_RUTA_COMUN_MODELO, SHA_COMUN_MODELO, ("MACROZONA_REGION", "MACROZONA_CODIGO"), {})
        self.assertEqual(S.MACROZONA_REGION, fuente["MACROZONA_REGION"])
        self.assertEqual(S.MACROZONA_CODIGO, fuente["MACROZONA_CODIGO"])
        g = S.grilla(20, (5101, 8101, 13101), celdas_sin_comuna=3)
        cel = g["celdas"]
        self.assertEqual(int((cel.cod_comuna == 0).sum()), 3)
        for fila in cel.itertuples():
            nombre = S.MACROZONA_REGION[int(fila.cod_comuna) // 1000]
            self.assertEqual((fila.macrozona, int(fila.macrozona_cod)), (nombre, S.MACROZONA_CODIGO[nombre]))
        self.assertEqual(set(cel[cel.cod_comuna == 0].macrozona), {tipos.MACROZONA_SIN_REGION})
        self.assertIsNone(tipos.macrozona_o_ninguna("sin_region"))
        self.assertTrue((g["pesos"][g["pesos"].cod_comuna == 0].w_ghs == 0).all())

    def test_verdad_es_fondo_mas_sesgo_mas_anomalias(self):
        h = np.arange(0, 24 * 60, 1)
        lat = np.array([-33.40, -33.41, -34.5])
        lon = np.array([-70.60, -70.61, -71.4])
        F = np.tile(np.arange(len(h))[:, None] * 0.0 + 10.0, (1, 3))
        v = S.verdad({"h": h, "lat": lat, "lon": lon, "F": F}, lambda la, lo, m, hh: np.full(len(la), m + hh / 100),
                     {"sigma": 1.5, "L_km": 100.0, "tau_h": 24.0, "media_cero": True}, semilla=1)
        np.testing.assert_allclose(v["obs"], v["F"] + v["b"] + v["a"])
        self.assertAlmostEqual(float(v["b"][25, 0]), 1 + 1 / 100)
        c = np.corrcoef(v["a"].T)
        self.assertGreater(c[0, 1], c[0, 2])
        self.assertLess(float(np.abs(v["a"][: 24 * 31].mean(axis=0)).max()), 1e-12)
        v2 = S.verdad({"h": h, "lat": lat, "lon": lon, "F": F}, np.zeros((3, 12, 24)), {"sigma": 1.5}, semilla=1)
        self.assertTrue(np.array_equal(v2["a"], S.verdad({"h": h, "lat": lat, "lon": lon, "F": F}, np.zeros((3, 12, 24)),
                                                         {"sigma": 1.5}, semilla=1)["a"]))

    def test_verdad_con_las_anomalias_de_mc50(self):
        """SIN-21 (MC-50, D42): ``anomalias=True`` o «MC-50» da σ = 1,5 K, L = 100 km, τ = 48 h y media 0 en cada punto ×
        mes × año (≤ 10⁻¹² en float64), con la semilla del protocolo; las claves que faltan se toman de MC-50; sin la
        media 0 (la prueba informativa de D42) las medias por mes no son 0. Las de I9 (las cuatro claves) no cambian."""
        self.assertEqual(dict(S.ANOMALIAS_MC50), {"sigma": 1.5, "L_km": 100.0, "tau_h": 48.0, "media_cero": True})
        h = np.arange(int((np.datetime64("2003-11-01T00", "h") - np.datetime64("2000-01-01T00", "h")).astype(int)),
                      int((np.datetime64("2004-03-01T00", "h") - np.datetime64("2000-01-01T00", "h")).astype(int)))
        lat, lon = np.array([-33.40, -33.45, -34.0]), np.array([-70.60, -70.70, -71.2])
        base = {"h": h, "lat": lat, "lon": lon, "F": np.zeros((len(h), 3))}
        sesgo = np.zeros((3, 12, 24))
        semilla = S.SEMILLA_POR_OMISION
        mc50 = S.verdad(base, sesgo, True, semilla=semilla)
        self.assertEqual(mc50["anomalias"], dict(S.ANOMALIAS_MC50))
        for otra in ("MC-50", dict(S.ANOMALIAS_MC50), {}, {"tau_h": 48.0}):
            np.testing.assert_array_equal(S.verdad(base, sesgo, otra, semilla=semilla)["a"], mc50["a"])
        anio, mes, _ = S._mes_y_hora(h)
        claves = sorted(set(zip(anio.tolist(), mes.tolist())))
        self.assertEqual(len(claves), 4)                                    # nov-2003 a feb-2004: cruza el año
        for a_, m_ in claves:
            k = (anio == a_) & (mes == m_)
            self.assertLess(float(np.abs(mc50["a"][k].mean(axis=0)).max()), 1e-12, (a_, m_))
        sin_media = S.verdad(base, sesgo, {"media_cero": False}, semilla=semilla)
        self.assertGreater(max(float(np.abs(sin_media["a"][(anio == a_) & (mes == m_)].mean(axis=0)).max())
                               for a_, m_ in claves), 1e-3)
        np.testing.assert_allclose(np.std(sin_media["a"], axis=0), 1.5, rtol=0.5)
        self.assertIsNone(S.verdad(base, sesgo, None, semilla=semilla)["anomalias"])
        self.assertFalse(S.verdad(base, sesgo, None, semilla=semilla)["a"].any())
        for mala in ({"sigma": 1.5, "tau": 48.0}, "MC-49", 3):
            with self.subTest(anomalias=mala), self.assertRaises(ValueError):
                S.verdad(base, sesgo, mala, semilla=semilla)
        # Las anomalías de S5 de I9 (las cuatro claves con los valores de MC-50) son las de MC-50 tal cual.
        explicitas = {"sigma": 1.5, "L_km": 100.0, "tau_h": 48.0, "media_cero": True}
        np.testing.assert_array_equal(S.verdad(base, sesgo, explicitas, semilla=semilla)["a"], mc50["a"])


class PruebasRedS6(unittest.TestCase):
    def test_red_s6(self):
        """MC-07 y MC-50 (SIN-12): 20 históricas fuera de los valles desde el inicio y 120 desde 2010; sesgo de −1,5 K
        en los valles; anomalías de media 0 en cada punto × mes × año; deriva por década; campos iguales se pidan como
        se pidan."""
        r = S.red_s6(anios=(2008, 2011), deriva_k_decada=0.3)
        est = r["estaciones"]
        self.assertEqual(len(est), 140)
        hist = est[est.historica]
        self.assertEqual(len(hist), 20)
        self.assertFalse(hist.valle.any())
        self.assertTrue((hist.desde_anio == 2008).all())
        self.assertTrue((est[~est.historica].desde_anio == 2010).all())
        self.assertTrue(est[~est.historica].valle.any())
        self.assertEqual(r["celdas"]["cod_comuna"].nunique(), 25)
        self.assertEqual(len(r["celdas"]), 100)
        ne = len(est)
        valle = np.r_[est.valle.to_numpy(), r["celdas"].valle.to_numpy()]
        np.testing.assert_array_equal(r["beta"], np.where(valle, -1.5, 0.0))
        self.assertEqual(r["parametros"]["tau_h"], 48.0)
        for m in (96, 97, 120):                                     # enero y febrero de 2008, enero de 2010
            hh, a = S.anomalias_s6(r, m)
            self.assertEqual(len(hh), 24 * (29 if m == 97 else 31))
            self.assertLess(float(np.abs(a.mean(axis=0)).max()), 1e-12)
            np.testing.assert_array_equal(a, S.anomalias_s6(r, m)[1])
        c = S.campos_s6(r)
        self.assertEqual(len(c["h"]), len(r["h"]))
        self.assertTrue(np.isnan(c["obs"][c["anio"] < 2010, 30]).all())
        self.assertFalse(np.isnan(c["obs"][:, 0]).any())
        np.testing.assert_allclose(c["obs"] - c["fondo"],
                                   np.where(np.isnan(c["obs"]), np.nan,
                                            np.concatenate([S.anomalias_s6(r, m)[1] for m in range(96, 144)])[:, :ne]
                                            - r["beta"][None, :ne] - S.deriva_s6(r, c["h"])[:, None]))
        un_anio = S.campos_s6(r, anios=(2009, 2009))
        k = c["anio"] == 2009
        np.testing.assert_array_equal(un_anio["verdad"], c["verdad"][k])
        decadas = (r["h"][-1] - r["h"][0]) / (24 * 365.25 * 10)
        self.assertAlmostEqual(float(S.deriva_s6(r, r["h"][-1:])[0]), 0.3 * decadas, places=9)
        self.assertTrue(np.array_equal(S.anomalias_s6(S.red_s6(anios=(2008, 2011)), 120)[1], S.anomalias_s6(r, 120)[1]))
        self.assertNotEqual(float(S.anomalias_s6(S.red_s6(anios=(2008, 2011), tau_h=6.0), 120)[1][1, 0]),
                            float(S.anomalias_s6(r, 120)[1][1, 0]))

    def test_red_s6_da_tf2_evaluable(self):
        """H10 (EMC1-2, MC-47): con el paso por omisión (1 h) las 20 históricas tienen ≥ 50 % de las horas UTC de cada
        año en 25 de los 26 años 2000-2025, así que la red constante de la regla r2000_2025 tiene ≥ 10 estaciones; y A
        tiene 24 horas UTC distintas, con hueco circular de 1 h (§4.3)."""
        r = S.red_s6()
        self.assertEqual(r["parametros"]["paso_h"], 1)
        anios_validos = np.zeros(len(r["estaciones"]), int)
        for anio in range(2000, 2026):
            if anio > r["parametros"]["anios"][1]:
                continue
            c = S.campos_s6(r, anios=(anio, anio))
            horas_del_anio = 24 * (366 if anio % 4 == 0 else 365)
            anios_validos += (np.isfinite(c["obs"]).sum(axis=0) / horas_del_anio >= 0.5)
        red_constante = int((anios_validos >= 22).sum())
        self.assertGreaterEqual(red_constante, 10)
        self.assertEqual(red_constante, 20)
        horas = sorted(set((r["h"] % 24).tolist()))
        self.assertEqual(horas, list(range(24)))
        self.assertEqual(max(np.diff(horas + [horas[0] + 24])), 1)


class PruebasTraslados(unittest.TestCase):
    @staticmethod
    def _z_impl(df):
        tbar = df.Ts + 273.15 + 0.0065 * df.attrs["z_cat"] / 2
        return 29.27 * tbar * np.log(df.QFF / df.QFE)

    def test_series_de_s4(self):
        """SIN-13: traslado de 15 m mueve z_impl y T2b de forma coherente; el barómetro mueve T2b y no z_impl; el
        horario diurno sólo trae 11-23 UTC antes del cambio; la estacionaria no tiene saltos."""
        for altitud in (500.0, 2500.0):
            with self.subTest(altitud=altitud):
                base = S.series_traslado("estacionaria", altitud, semilla=3)
                cambio = base.attrs["cambio_h"]
                for tipo in S.TIPOS_TRASLADO:
                    df = S.series_traslado(tipo, altitud, semilla=3)
                    antes, despues = df.h < cambio, df.h >= cambio
                    z = self._z_impl(df)
                    t2b = df.QFE - df.p_F
                    dz = z[despues].median() - z[antes].median()
                    dp = t2b[despues].median() - t2b[antes].median()
                    if tipo == "traslado":
                        self.assertAlmostEqual(dz, 15.0, delta=3.0)
                        dz_b = -dp * 287.05 * (df.Ts.mean() + 273.15) / (9.80665 * df.QFE.mean())
                        self.assertAlmostEqual(dz_b, 15.0, delta=3.0)
                    elif tipo == "barometro":
                        self.assertAlmostEqual(dp, 1.5, delta=0.3)
                        self.assertLess(abs(dz), 3.0)
                    elif tipo == "horario":
                        horas = df.h[antes] % 24
                        self.assertTrue(((horas >= 11) & (horas <= 23)).all())
                        self.assertEqual(set((df.h[despues] % 24).unique()), set(range(24)))
                    elif tipo == "estacionaria":
                        self.assertLess(abs(dz), 3.0)
                        self.assertLess(abs(dp), 0.5)
        r = S.series_traslado("traslado", 1000.0, semilla=3, magnitud=5.0)
        self.assertEqual(r.attrs["magnitud"], 5.0)
        with self.assertRaises(ValueError):
            S.series_traslado("otro", 1000.0, semilla=1)
        with self.assertRaises(ValueError):
            S.series_traslado("horario", 1000.0, semilla=1, ciclo_diario_m=float("nan"))

    def test_s4_iguales_a_la_ola_1_sin_las_senales(self):
        """SIN-13 y SIN-20: las señales de la reducción y del horario no cambian ninguna otra extracción del generador.
        Con ``dt_clima_k = 0`` y ``ciclo_diario_m = 0`` cada serie es la de la ola 1 (sus sumas, con la semilla del
        protocolo, guardadas aquí antes del cambio), y por omisión sólo cambian «reduccion» y «horario»."""
        semilla = 20261023                       # SEMILLA del Anexo A (D42)
        for (tipo, altitud), (n, *sumas) in _SUMAS_OLA_1.items():
            with self.subTest(tipo=tipo, altitud=altitud):
                df = S.series_traslado(tipo, altitud, semilla=semilla, dt_clima_k=0.0, ciclo_diario_m=0.0)
                self.assertEqual(len(df), n)
                for col, suma in zip(("Ts", "QFE", "QFF", "p_F"), sumas):
                    self.assertAlmostEqual(math.fsum(df[col].to_numpy()) / suma, 1.0, delta=1e-12, msg=col)
                por_omision = S.series_traslado(tipo, altitud, semilla=semilla)
                if tipo in ("reduccion", "horario"):
                    self.assertFalse(np.array_equal(por_omision["QFF"].to_numpy(), df["QFF"].to_numpy()))
                    np.testing.assert_array_equal(por_omision["p_F"].to_numpy(), df["p_F"].to_numpy())
                else:
                    pd.testing.assert_frame_equal(por_omision, df)

    def _cambio(self, df, desde_antes: int = 12, meses_despues: int = 12):
        """Medias de z_impl y de T2b en los ``meses_despues`` meses posteriores al cambio menos las de los
        ``desde_antes`` anteriores (como D(k) pero con medias simples y todas las horas observadas)."""
        h = df.h.to_numpy(np.int64)
        epoca = np.datetime64("2000-01-01T00", "h")
        meses = ((epoca + h.astype("timedelta64[h]")).astype("datetime64[M]").astype(np.int64)
                 - (epoca + np.int64(df.attrs["cambio_h"]).astype("timedelta64[h]")).astype("datetime64[M]")
                 .astype(np.int64))
        antes, despues = (meses < 0) & (meses >= -desde_antes), (meses >= 0) & (meses < meses_despues)
        z, t2b = self._z_impl(df).to_numpy(), (df.QFE - df.p_F).to_numpy()
        return antes, despues, z, t2b

    def test_s4_reduccion_estandar_a_real_mueve_z_impl(self):
        """SIN-20, hallazgo 4: con el clima de la estación 10 K más cálido que la atmósfera estándar, z_impl salta
        −z·ΔT/T̄_std en el cambio (sobre el umbral de T2a en 500, 1.000 y 2.500 m) y T2b no se mueve: la prueba de S4
        tiene una señal de T2a sin T2b que clasificar. Con ΔT = 0 (la serie de la ola 1) no hay salto."""
        U = _umbrales(self)
        from meteo_combinada import constantes
        self.assertEqual(S.DT_CLIMA_REDUCCION_K, 10.0)
        for altitud in constantes.valor("S4_ALTITUDES_M"):
            with self.subTest(altitud=altitud):
                df = S.series_traslado("reduccion", float(altitud), semilla=U.a("SEMILLA"))
                self.assertEqual(df.attrs["dt_clima_k"], 10.0)
                antes, despues, z, t2b = self._cambio(df)
                salto = float(z[despues].mean() - z[antes].mean())
                esperado = -altitud * 10.0 / (288.15 - 0.0065 * altitud / 2)
                self.assertAlmostEqual(salto, esperado, delta=1.0)
                self.assertGreater(abs(salto), 1.5 * U.a("K4_T2A_M"))
                self.assertLess(abs(float(t2b[despues].mean() - t2b[antes].mean())), 0.2 * U.a("K4_T2B_HPA"))
                plano = S.series_traslado("reduccion", float(altitud), semilla=U.a("SEMILLA"), dt_clima_k=0.0)
                a0, d0, z0, _ = self._cambio(plano)
                self.assertLess(abs(float(z0[d0].mean() - z0[a0].mean())), 0.1 * U.a("K4_T2A_M"))
                # Después del cambio la reducción es la real: z_impl = z más el ruido de 5 m (SIN-13).
                self.assertAlmostEqual(float(np.mean(z[despues])), altitud, delta=0.5)
                self.assertAlmostEqual(float(np.std(z[despues])), S.SIGMA_Z_IMPL_M, delta=0.5)

    def test_s4_horario_con_ciclo_diario_en_t2a_y_t2b(self):
        """SIN-20, hallazgo 4: z_impl y T2b traen un ciclo diario coherente con un desplazamiento vertical. Con sólo
        11-23 UTC antes del cambio, las medias de todas las horas observadas saltan más que los umbrales de T2a y T2b
        en 500, 1.000 y 2.500 m, y como un traslado (Δz_b compatible con Δz_a por la regla de §2.5): sin H*(k) de §2.5
        se declararía un traslado. En las mismas horas UTC de los dos lados no hay salto."""
        U = _umbrales(self)
        from meteo_combinada import constantes
        self.assertEqual((S.CICLO_HORARIO_M, S.HORA_MAXIMO_CICLO_UTC, S.HORARIO_DIURNO_UTC), (50.0, 19.0, (11, 23)))
        for altitud in constantes.valor("S4_ALTITUDES_M"):
            with self.subTest(altitud=altitud):
                df = S.series_traslado("horario", float(altitud), semilla=U.a("SEMILLA"))
                amp_p = S.ciclo_diario_t2b_hpa(50.0, float(altitud))
                self.assertEqual((df.attrs["ciclo_diario_m"], df.attrs["ciclo_diario_t2b_hpa"]), (50.0, amp_p))
                tbar = 288.15 - 0.0065 * altitud / 2
                p_std = 1013.25 * (1 - 2.25577e-5 * altitud) ** 5.25588
                self.assertAlmostEqual(amp_p, 50.0 * 9.80665 * p_std / (287.05 * tbar), places=9)
                antes, despues, z, t2b = self._cambio(df, desde_antes=36, meses_despues=36)
                hora = df.h.to_numpy() % 24
                self.assertTrue(((hora[antes] >= 11) & (hora[antes] <= 23)).all())
                dz_a = float(z[despues].mean() - z[antes].mean())
                dqfe = float(t2b[despues].mean() - t2b[antes].mean())
                self.assertGreater(abs(dz_a), 2 * U.a("K4_T2A_M"))
                self.assertGreater(abs(dqfe), 1.5 * U.a("K4_T2B_HPA"))
                pbar = float(df.QFE[antes | despues].mean())
                tb = float((df.Ts + 273.15 + 0.0065 * altitud / 2)[antes | despues].mean())
                dz_b = -dqfe * 287.05 * tb / (9.80665 * pbar)                    # §2.5
                self.assertLessEqual(abs(dz_a - dz_b), max(U.a("K4_COINC_M"), U.a("K4_COINC_FRAC") * abs(dz_b)))
                # Ciclo diario en las dos estadísticas: amplitud de las medias por hora UTC después del cambio.
                medias_z = pd.Series(z[despues]).groupby(hora[despues]).mean()
                medias_p = pd.Series(t2b[despues]).groupby(hora[despues]).mean()
                self.assertAlmostEqual((medias_z.max() - medias_z.min()) / 2, 50.0, delta=5.0)
                self.assertAlmostEqual((medias_p.max() - medias_p.min()) / 2, amp_p, delta=0.2 * amp_p)
                self.assertEqual(int(medias_z.idxmax()), 19)
                self.assertEqual(int(medias_p.idxmin()), 19)
                # En las mismas horas UTC (las de H*), los dos lados coinciden.
                mismas = despues & (hora >= 11) & (hora <= 23)
                self.assertLess(abs(float(z[mismas].mean() - z[antes].mean())), 0.05 * U.a("K4_T2A_M"))
                self.assertLess(abs(float(t2b[mismas].mean() - t2b[antes].mean())), 0.1 * U.a("K4_T2B_HPA"))
                # Sin el ciclo (la serie de la ola 1), el salto ingenuo no existe: la prueba antigua no probaba nada.
                plano = S.series_traslado("horario", float(altitud), semilla=U.a("SEMILLA"), ciclo_diario_m=0.0)
                a0, d0, z0, p0 = self._cambio(plano, desde_antes=36, meses_despues=36)
                self.assertLess(abs(float(z0[d0].mean() - z0[a0].mean())), 0.1 * U.a("K4_T2A_M"))
                self.assertLess(abs(float(p0[d0].mean() - p0[a0].mean())), 0.2 * U.a("K4_T2B_HPA"))


# Anexo A, escrito a mano en la prueba (lo que comprueba que los esperados de sintetico estén bien calculados):
_CD = {"T": 0.05, "HR": 0.5, "rapidez": 0.05, "p": 0.05}             # CD 1,10× + …
_EX = {"T": 0.25, "Td": 0.40, "temp_media": 0.25, "hr_media": 2.0, "rapidez": 0.30}    # EX mín + … (no hay EX en p)
_ORDEN = {"A": 0, "AB": 1, "B": 2, "C": 3, "C_est": 3}            # §6.2, paso 3: desempate A, AB, B, C (C_est)


def _compuertas_a_mano(d: dict) -> dict[str, set[str]]:
    """Compuertas que falla cada candidato de E0, recalculadas en la prueba con §6.1 y el Anexo A: las métricas son las
    del agregado (P1 y P2 juntos, §5.3) y MZ rige en una macrozona con ≥ 10 estaciones en el agregado y publicable en
    P1, en P2 y en el agregado (MC-61)."""
    v, tf = d["validacion"], d["tf"]
    e0 = [c for c in d["candidatos"] if c not in d["e0_excluidos"]]
    fallas: dict[str, set[str]] = {c: set() for c in e0}
    nac = v[(v.estrato == "nacional") & (v.particion == "agregado") & v.candidato.isin(e0)]
    for var, g in nac.groupby("variable"):
        g = g.set_index("candidato")
        if g["CD"].notna().all():
            minimo = g["CD"].min()
            for c, x in g["CD"].items():
                if x > 1.10 * minimo + _CD[var] + 1e-12:
                    fallas[c].add("CD")
        if g["EX"].notna().all() and var in _EX:
            minimo = g["EX"].min()
            for c, x in g["EX"].items():
                if x > minimo + _EX[var] + 1e-12:
                    fallas[c].add("EX")
        for col, nombre in (("nivel", "nivel"), ("anomalia", "anomalia")):
            if g[col].notna().all():
                minimo = g[col].min()
                for c, x in g[col].items():
                    if x > 1.15 * minimo + 1e-12:
                        fallas[c].add(nombre)
    mz_todas = v[(v.estrato == "macrozona") & v.candidato.isin(e0)]
    publicable = mz_todas.groupby(["variable", "valor_estrato"])["publicable"].all()
    mz = mz_todas[mz_todas.particion == "agregado"]
    for clave, g in mz.groupby(["variable", "valor_estrato"]):
        if not (publicable[clave] and (g.n_estaciones >= 10).all()):
            continue
        g = g.set_index("candidato")
        for c, x in g["S"].items():
            if x > 1.15 * g["S"].min() + 1e-12:
                fallas[c].add("MZ")
    for f in tf.itertuples():
        if f.candidato not in fallas:
            continue
        if f.resultado == "falla" or (f.resultado == "no_evaluable" and f.candidato in ("B", "AB")):
            fallas[f.candidato].add("TF")
    return {c: s for c, s in fallas.items() if s}


def _supera(comp: pd.DataFrame, pol: str, sentido: str, margen_pp: float = 1.0) -> bool:
    """Las 7 condiciones del Anexo B en LRO y en BLQ-75 a la vez, recalculadas en la prueba (NMB en %)."""
    filas = comp[(comp.contaminante == pol) & (comp.sentido == sentido)]
    if set(filas.protocolo) != {"LRO", "BLQ-75"}:
        return False
    return all(bool(f.ic_bajo > 0 and f.segunda_prueba_coincide and f.supera_ruido and f.consistencia_e2
                    and f.sobrevive_bloque and f.signo_sin_ponderar and f.signo_log and f.decision_sigma2
                    and abs(f.nmb_c) <= abs(f.nmb_otra) + margen_pp) for f in filas.itertuples())


class PruebasCasosDeLaRegla(unittest.TestCase):
    def test_tablas_metricas(self):
        """Cada caso de S7 trae sus tablas en los esquemas de tipos y un esperado coherente: las compuertas que falla
        cada candidato, recalculadas aquí con §6.1 y el Anexo A, son las de ``esperado["fallas"]``; las filas van en
        P1, P2 y el agregado (MC-61, SIN-22); la TF de A, C y C_est es 0 (§5.7) y las notas siguen DEC-10."""
        for caso in S.CASOS_METRICAS:
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                if caso == "soporte":
                    tipos.validar_esquema(d["evaluaciones"], tipos.ESQUEMA_EVALUACIONES, nombre=caso)
                    aus = d["evaluaciones"][d["evaluaciones"].codigo.map(lambda c: d["infos"][c]["macrozona"]) == "austral"]
                    self.assertTrue((aus[aus.candidato != "C"].frac_sin_soporte > 0.5).all())
                    continue
                val, tf = d["validacion"], d["tf"]
                tipos.validar_esquema(val, tipos.ESQUEMA_VALIDACION_PUB, nombre=caso)
                tipos.validar_esquema(tf, tipos.ESQUEMA_TF, nombre=caso)
                tipos.validar_esquema(d["replicas"], tipos.ESQUEMA_REPLICAS, nombre=caso)
                e = d["esperado"]
                self.assertEqual({c: set(s) for c, s in e["fallas"].items()}, _compuertas_a_mano(d))
                self.assertTrue(set(e["e1"]) <= set(e["e0"]) <= set(d["candidatos"]))
                self.assertIn(e["ganador"], e["conjunto"])
                self.assertTrue(set(e["conjunto"]) <= set(e["e0"]))
                self.assertEqual(e["ganador"], min(e["conjunto"], key=lambda c: (e["S"][c], _ORDEN[c])))
                for c in d["e0_excluidos"]:
                    self.assertNotIn(c, e["e0"])
                self.assertEqual(set(d["replicas"].candidato), set(e["e0"]))
                # Notas de DEC-10, recalculadas aquí: la regla crónica (§6.2, paso 5), E1 vacío y TF2 no evaluable.
                cronica = (d["uso"] == "cronico" and not {"B", "AB"} & set(e["e1"])
                           and any("TF" in e["fallas"].get(c, ()) or "deriva" in d["e0_excluidos"].get(c, ())
                                   for c in ("B", "AB")))
                notas = tuple(n for n, si in (("regla crónica", cronica), ("regla sin ganador", not e["e1"]),
                                              ("TF2 no evaluable", bool((tf.resultado == "no_evaluable").any())))
                              if si)
                self.assertEqual(e["notas"], notas)
                # §5.7: A, C y C_est dan 0 por construcción (o TF2 «no evaluable», EMC1-2).
                cero = tf[tf.candidato.isin(list(S.CERO_POR_CONSTRUCCION)).to_numpy(dtype=bool)]
                evaluable = (cero.resultado != "no_evaluable").to_numpy(dtype=bool)
                self.assertTrue((cero.media_pond[evaluable] == 0).all() and (cero.p95_pond[evaluable] == 0).all())
                self.assertTrue((cero.resultado != "falla").all())
                # MC-61 (SIN-22): cada fila en P1, P2 y el agregado; evaluaciones y reparto entre particiones.
                claves = val.groupby(["estrato", "valor_estrato", "variable", "candidato"])["particion"]
                self.assertTrue(all(sorted(ps) == sorted(S.PARTICIONES_VALIDACION) for _, ps in claves))
                agr = (val.particion == "agregado").to_numpy(dtype=bool)
                self.assertTrue((val.n_evaluaciones[agr] == 2 * val.n_estaciones[agr]).all())
                self.assertTrue((val.n_evaluaciones[~agr] == val.n_estaciones[~agr]).all())
                self.assertTrue(val.publicable[(val.estrato == "nacional").to_numpy(dtype=bool)].all())
                indice = ["estrato", "valor_estrato", "variable", "candidato"]
                por = {p: val[(val.particion == p).to_numpy(dtype=bool)].set_index(indice).sort_index()
                       for p in S.PARTICIONES_VALIDACION}
                for col in ("S", "CD", "EX", "nivel", "anomalia"):
                    np.testing.assert_allclose(por["agregado"][col] ** 2, (por["P1"][col] ** 2 + por["P2"][col] ** 2) / 2,
                                               rtol=1e-12)
                mz = val[(val.estrato == "macrozona").to_numpy(dtype=bool)]
                for _, g in mz.groupby(["variable", "valor_estrato", "particion"]):
                    self.assertEqual(g.publicable.nunique(), 1)
                    self.assertEqual(g.n_estaciones.nunique(), 1)
        ganadores = {"ganador_claro": "AB", "compuerta_cd": "B", "falla_cd_hr": "B", "falla_ex_td": "B",
                     "falla_mz_hr": "B", "falla_tf_td": "B", "tf2_falla": "B", "e1_vacio": "B", "empate": "A",
                     "deriva": "AB", "finitud": "B", "mz_no_aplica": "AB", "mz_no_publicable": "AB",
                     "mz_no_publicable_p2": "AB", "agudo_nivel": "B", "falla_ex_hr_media": "B", "falla_mz_agudo": "B",
                     "uv": "A", "falla_mz_rapidez": "C", "p_sin_ex": "B", "cronica": "A", "cronica_mixta": "C_est",
                     "tf2_no_evaluable": "C_est", "falla_mz_cronica": "AB"}
        self.assertEqual(set(ganadores), set(S.CASOS_METRICAS) - {"soporte"})
        for caso, ganador in ganadores.items():
            self.assertEqual(S.tablas_metricas(caso)["esperado"]["ganador"], ganador, caso)
        # «e1_vacio»: cada uno falla una compuerta; AB (el de menor S) falla TF1 en Td y el paso 4 elige B; C, por CD.
        e = S.tablas_metricas("e1_vacio")
        self.assertEqual((e["esperado"]["e1"], e["esperado"]["notas"], e["esperado"]["conjunto"]),
                         ((), ("regla sin ganador",), ("A", "B", "C")))
        self.assertEqual(e["esperado"]["fallas"], {"A": ("CD",), "B": ("EX",), "AB": ("TF",), "C": ("CD",)})
        self.assertEqual(min(e["esperado"]["S"], key=e["esperado"]["S"].get), "AB")
        tf = e["tf"]
        self.assertEqual(set(tf[tf.resultado == "falla"][["candidato", "variable", "prueba"]]
                             .itertuples(index=False, name=None)), {("AB", "Td", "TF1")})
        self.assertEqual(S.tablas_metricas("cronica_mixta")["esperado"]["notas"], ("regla crónica", "regla sin ganador"))
        self.assertEqual(S.tablas_metricas("cronica_mixta")["esperado"]["conjunto"], ("A", "C_est"))
        mz = S.tablas_metricas("mz_no_aplica")["validacion"]
        self.assertEqual(set(mz[mz.estrato == "macrozona"].n_estaciones), {8})
        mz = S.tablas_metricas("mz_no_publicable")["validacion"]
        self.assertFalse(mz[mz.estrato == "macrozona"].publicable.any())
        mz = S.tablas_metricas("mz_no_publicable_p2")["validacion"]
        mz = mz[mz.estrato == "macrozona"]
        self.assertEqual(dict(mz.groupby("particion").publicable.all()), {"P1": True, "P2": False, "agregado": True})
        for caso, variables in (("uv", {"uv", "rapidez"}), ("falla_mz_agudo", {"temp_media", "hr_media"}),
                                ("falla_mz_cronica", {"T"}), ("ganador_claro", {"T", "HR"}), ("p_sin_ex", {"p"})):
            v = S.tablas_metricas(caso)["validacion"]
            self.assertEqual(set(v[v.estrato == "macrozona"].variable), variables, caso)      # DEC-1, D43
        v = S.tablas_metricas("falla_mz_cronica")["validacion"]
        self.assertEqual(set(v[v.estrato == "macrozona"].n_estaciones), {12})
        p = S.tablas_metricas("p_sin_ex")["validacion"]
        self.assertGreater(float(p[(p.candidato == "B") & (p.variable == "p") & (p.estrato == "nacional")
                                   & (p.particion == "agregado")].EX.iloc[0]), 5)
        self.assertEqual(S.tablas_metricas("finitud")["e0_excluidos"], {"AB": ("finitud",)})
        tf = S.tablas_metricas("tf2_no_evaluable")["tf"]
        tf2 = tf[tf.prueba == "TF2"]
        self.assertTrue((tf2.resultado == "no_evaluable").all() and (tf2.regla_red == "ninguna").all())
        for v in tf.regla_red.unique():
            tipos.ReglaRedConstante(v)
        tf = S.tablas_metricas("tf2_falla")["tf"]
        self.assertEqual(set(tf[tf.resultado == "falla"][["candidato", "prueba"]].itertuples(index=False, name=None)),
                         {("AB", "TF2")})
        with self.assertRaises(ValueError):
            S.tablas_metricas("otro")
        with self.assertRaises(ValueError):                 # §5.7: pedir una TF fallida de C es un error del caso
            S._filas_tf("ambiental", ("A", "C"), ("T",), fallas=(("C", "T", "TF1"),))
        with self.assertRaises(ValueError):
            S._publicable_por_particion({"P1": True, "agregado": True})

    def test_tablas_m6(self):
        """S16 (SIN-17): comparaciones en ESQUEMA_COMPARACION_M6; quién supera, recalculado aquí con las 7 condiciones
        en LRO y BLQ-75 y el NMB en %, es el esperado; cada caso de una sola condición fallida aísla esa condición, y
        con 0,01 en lugar de 1 punto porcentual «c7_en_puntos» daría otro resultado."""
        for caso in S.CASOS_M6:
            with self.subTest(caso=caso):
                d = S.tablas_m6(caso)
                comp = d["comparacion"]
                tipos.validar_esquema(comp, tipos.ESQUEMA_COMPARACION_M6, nombre=caso)
                self.assertEqual(len(comp), 8)
                for s in comp.sentido.unique():
                    tipos.Sentido(s)
                for p in comp.protocolo.unique():
                    tipos.Protocolo(p)
                e = d["esperado"]
                for pol in ("pm25", "no2"):
                    quien = [s[0] for s in S.SENTIDOS_M6 if _supera(comp, pol, s)]
                    self.assertLessEqual(len(quien), 1)                     # simetría: a lo más una supera
                    self.assertEqual(e["supera"][pol], quien[0] if quien else None, pol)
                self.assertEqual(set(e["rama"]), {"pm25", "no2"})
                self.assertIn(e["variante"]["O3"], ("I", "D"))
                if caso.startswith("falla_c"):
                    fila = comp[(comp.contaminante == "pm25") & (comp.sentido == "D_frente_a_I")].iloc[0]
                    base = S._fila_m6("pm25", "D_frente_a_I", "LRO", "supera")
                    distintas = [k for k in base if k not in ("protocolo",) and base[k] != fila[k]]
                    self.assertEqual(len(distintas), 1 if caso != "falla_c7" else 2, distintas)
        d = S.tablas_m6("c7_en_puntos")["comparacion"]
        self.assertTrue(_supera(d, "pm25", "D_frente_a_I"))
        self.assertFalse(_supera(d, "pm25", "D_frente_a_I", margen_pp=0.01))
        self.assertEqual(S.tablas_m6("rama3")["esperado"]["rama"]["pm25"], 3)
        self.assertTrue(S.tablas_m6("rama3")["esperado"]["restringido"])
        self.assertEqual(S.tablas_m6("o3_difieren")["esperado"]["variante"]["O3"], "I")
        self.assertEqual(S.tablas_m6("rama2_supera_falla_tf")["esperado"]["variante"]["pm25"], "I")
        self.assertEqual(S.tablas_m6("solo_lro")["esperado"]["rama"]["pm25"], 2)
        self.assertEqual(S.tablas_m6("borde_c7")["esperado"]["variante"], {"pm25": "D", "no2": "D", "O3": "D"})


class PruebasCalceConDecision(unittest.TestCase):
    """Acuerdo A11 (TIP-12): las tablas de ``tablas_metricas``, tal como salen, son entradas de ``decision``."""

    @staticmethod
    def _entradas(d, validacion=None):
        return tipos.EntradasDecision(tipos.Uso(d["uso"]), tipos.Grupo(d["grupo"]),
                                      d["validacion"] if validacion is None else validacion, d["tf"], d["replicas"],
                                      d["e0_excluidos"])

    @staticmethod
    def _fallidas(tabla) -> dict[str, set[str]]:
        salida: dict[str, set[str]] = {}
        for f in tabla[~tabla.pasa.to_numpy(dtype=bool)].itertuples():
            salida.setdefault(f.candidato, set()).add(f.compuerta)
        return salida

    def test_cada_caso_tal_como_sale(self):
        """Sin ningún cambio a mano, ``compuertas`` y ``decidir_combinacion`` aceptan los casos (macrozonas en P1, P2 y
        el agregado, MC-61; MZ en «uv» y en la rapidez, D43; la TF de A, C y C_est en 0, §5.7) y dan el esperado: las
        compuertas fallidas, E0, E1, el ganador, el S del grupo, los motivos y las notas (DEC-10)."""
        U = _umbrales(self)
        from meteo_combinada import decision
        # Copias de sintetico (no importa el paquete) frente a sus fuentes.
        self.assertEqual(S.PARTICIONES_VALIDACION, (tipos.Particion.P1.value, tipos.Particion.P2.value,
                                                    tipos.PARTICION_AGREGADO))
        self.assertEqual(S.CERO_POR_CONSTRUCCION, decision.CERO_POR_CONSTRUCCION)
        self.assertEqual(S.ORDEN_NOTAS, tuple(n for n in decision.ORDEN_NOTAS if n != decision.NOTA_RESTRINGIDO))
        for caso in S.CASOS_METRICAS:
            if caso == "soporte":
                continue
            with self.subTest(caso=caso):
                d = S.tablas_metricas(caso)
                e = d["esperado"]
                tabla = decision.compuertas(d["uso"], d["grupo"], self._entradas(d), U)
                self.assertEqual(self._fallidas(tabla), {c: set(s) for c, s in e["fallas"].items()})
                r = decision.decidir_combinacion(d["uso"], d["grupo"], self._entradas(d), umbrales=U)
                self.assertEqual((r.e0, r.e1, r.ganador, r.notas), (e["e0"], e["e1"], e["ganador"], e["notas"]))
                self.assertEqual(r.S, e["S"])                            # la misma fórmula: igualdad exacta
                self.assertEqual(set(r.motivos), set(e["fallas"]) | set(d["e0_excluidos"]))
                self.assertEqual(set(r.ic_delta_S), set(e["e0"]))

    def test_una_regla_que_leyera_p1_o_p2_cambiaria_de_resultado(self):
        """SIN-22: el reparto entre P1 y P2 depende del candidato; si la regla leyera las métricas de P1 (o de P2) en
        lugar de las del agregado, el resultado cambiaría en cada caso con alguna de las dos (DEC-2)."""
        U = _umbrales(self)
        from meteo_combinada import decision
        cambian = {}
        for caso in S.CASOS_METRICAS:
            if caso == "soporte":
                continue
            d = S.tablas_metricas(caso)
            e = d["esperado"]
            for p in ("P1", "P2"):
                v = d["validacion"]
                v = v[(v.particion != "agregado").to_numpy(dtype=bool)].copy()
                v.loc[(v.particion == p).to_numpy(dtype=bool), "particion"] = "agregado"
                copia = v[(v.particion == "agregado").to_numpy(dtype=bool)].copy()
                copia["particion"] = pd.array([p] * len(copia), dtype="string")
                v = pd.concat([v, copia], ignore_index=True).astype(dict(tipos.ESQUEMA_VALIDACION_PUB))
                tabla = decision.compuertas(d["uso"], d["grupo"], self._entradas(d, v), U)
                r = decision.decidir_combinacion(d["uso"], d["grupo"], self._entradas(d, v), umbrales=U)
                cambian[(caso, p)] = (self._fallidas(tabla) != {c: set(s) for c, s in e["fallas"].items()}
                                      or r.ganador != e["ganador"] or r.S != e["S"])
        casos = {c for c, _ in cambian}
        self.assertEqual({c for (c, _), si in cambian.items() if si}, casos)
        self.assertEqual(sum(cambian[(c, "P1")] for c in casos), len(casos))


class PruebasSincaYRed2(unittest.TestCase):
    def test_sinca_con_el_formato_del_descargador(self):
        """SIN-15: las columnas de los manifiestos son las del descargador SINCA (AST) y cada serie pasa su
        analizar_respuesta (extraída por AST, sin importar el módulo) con los mismos conteos del manifiesto."""
        from reloj_dmc import fijados
        if not _RUTA_DESCARGADOR_SINCA.is_file() or _sha(_RUTA_DESCARGADOR_SINCA) != SHA_DESCARGADOR_SINCA:
            self.skipTest("descargar_sinca_meteorologia.py falta o no tiene la huella de M0; no se da por aprobada")
        codigo = fijados.extraer_por_ast(_RUTA_DESCARGADOR_SINCA, SHA_DESCARGADOR_SINCA,
                                         ("CAMPOS_MANIFIESTO", "CAMPOS_FALTANTES", "_RE_DATO", "_yymmdd",
                                          "analizar_respuesta"), {"re": re, "math": math, "date": date})
        self.assertEqual(S.CAMPOS_MANIFIESTO_SINCA, codigo["CAMPOS_MANIFIESTO"])
        self.assertEqual(S.CAMPOS_FALTANTES_SINCA, codigo["CAMPOS_FALTANTES"])
        with tempfile.TemporaryDirectory() as tmp:
            raiz = S.sinca_sintetico(Path(tmp) / "sinca_meteorologia")
            m1 = pd.read_csv(raiz / "manifiesto_descarga.csv", dtype=str, keep_default_na=False)
            m2 = pd.read_csv(raiz / "manifiesto_descarga_20261024b.csv", dtype=str, keep_default_na=False)
            self.assertEqual(list(m1.columns), S.CAMPOS_MANIFIESTO_SINCA)
            self.assertFalse(set(m1.estacion) & set(m2.estacion))
            self.assertTrue({"PRES", "RAIN", "GLOB"} <= set(m2.parametro))
            for m in (m1, m2):
                for f in m.itertuples():
                    texto = (raiz / f.ruta_relativa).read_text(encoding="utf-8")
                    resumen = codigo["analizar_respuesta"](texto, f.desde, f.hasta)
                    self.assertEqual(resumen["estado"], "serie", f.ruta_relativa)
                    for clave in ("filas", "filas_con_observacion", "filas_no_numericas"):
                        self.assertEqual(str(resumen[clave]), getattr(f, clave), (f.ruta_relativa, clave))
                    for clave in ("minimo", "maximo", "primera_observacion", "ultima_observacion"):
                        self.assertEqual(resumen[clave], getattr(f, clave), (f.ruta_relativa, clave))
                    self.assertEqual(hashlib.sha256((raiz / f.ruta_relativa).read_bytes()).hexdigest(), f.sha256)
            sumas = (raiz / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(sumas), len(m1))
            h = S.huellas_sinca(raiz)
            self.assertEqual(h["no_disponibles.csv"], h["no_disponibles_20261024b.csv"])
            d12 = m1[(m1.estacion == "D12") & (m1.parametro == "TEMP")]
            self.assertEqual(sorted(d12.altura_ficha), ["2", "2"])
            self.assertEqual(len(set(d12.filas_con_observacion)), 2)

    def test_panel_y_pliegues_de_la_red_2(self):
        """SIN-16: paneles con sus columnas y su .json, y el manifiesto con estaciones, panel y protocolos."""
        with tempfile.TemporaryDirectory() as tmp:
            r = S.panel_y_pliegues(Path(tmp))
            m = json.loads(r["pliegues"].read_text(encoding="utf-8"))
            self.assertEqual(m["schema"], S.ESQUEMA_PLIEGUES_V2)
            self.assertEqual({e["estacion"] for e in m["estaciones"]}, set(r["monitores"].estacion))
            for pol in ("pm25", "no2"):
                panel = pd.read_parquet(r[f"panel_{pol}"])
                self.assertEqual(tuple(panel.columns), S.COLUMNAS_PANEL_RED2)
                self.assertIsNone(panel["ts_utc"].dt.tz)
                info = m["contaminantes"][pol]["panel"]
                self.assertEqual(info["sha256"], _sha(r[f"panel_{pol}"]))
                self.assertEqual(info["filas"], len(panel))
                self.assertEqual(set(m["contaminantes"][pol]["protocolos"]), {"LRO", "BLQ-75"})
                meta = json.loads(r[f"panel_{pol}"].with_suffix(".json").read_text(encoding="utf-8"))
                self.assertEqual(meta["sha256"], info["sha256"])
            no2 = pd.read_parquet(r["panel_no2"])
            self.assertNotIn("S012", set(no2.estacion))
            self.assertEqual(r["pliegues"].name, S.NOMBRE_PLIEGUES_RED2)
            self.assertEqual(m["schema_red2"], S.ESQUEMA_PLIEGUES_RED2)
            self.assertEqual(m["bloque"], S.BLOQUE_RED_AMPLIADA)
            self.assertIn("parametros", m)
            self.assertEqual(m["huella_pliegues"], S.huella_pliegues(m))
            for e in m["estaciones"]:
                self.assertRegex(e["bloque_blq75"], r"E\d{3}N\d{3}")
            self.assertEqual({e["region_lro"] for e in m["estaciones"] if e["region_sinca"] == "RXVI"}, {"RVIII"})

    def test_huella_y_esquemas_de_los_pliegues_como_en_v2(self):
        """H15 (SIN-16): CLAVES_HUELLA, los dos esquemas, el nombre y el bloque son los de v2 (AST, sólo código), y la
        huella es la que daría pliegues_v2.huella_pliegues con el JSON canónico de _traza_v2."""
        from reloj_dmc import fijados
        rutas = {n: _V2 / n for n in ("pliegues_v2.py", "pliegues_red2_v2.py", "red_ampliada_v2.py", "_traza_v2.py")}
        faltan = [n for n, p in rutas.items() if not p.is_file()]
        if faltan:
            self.skipTest(f"faltan {faltan}; no se da por aprobada")
        pv = fijados.extraer_por_ast(rutas["pliegues_v2.py"], None, ("SCHEMA", "CLAVES_HUELLA"), {})
        pr = fijados.extraer_por_ast(rutas["pliegues_red2_v2.py"], None, ("SCHEMA", "NOMBRE"), {})
        ra = fijados.extraer_por_ast(rutas["red_ampliada_v2.py"], None, ("BLOQUE",), {})
        tz = fijados.extraer_por_ast(rutas["_traza_v2.py"], None, ("json_canonico", "sha256_json"),
                                     {"json": json, "hashlib": hashlib, "a_json": str})
        self.assertEqual(S.ESQUEMA_PLIEGUES_V2, pv["SCHEMA"])
        self.assertEqual(S.CLAVES_HUELLA_PLIEGUES, pv["CLAVES_HUELLA"])
        self.assertEqual((S.ESQUEMA_PLIEGUES_RED2, S.NOMBRE_PLIEGUES_RED2), (pr["SCHEMA"], pr["NOMBRE"]))
        self.assertEqual(S.BLOQUE_RED_AMPLIADA, ra["BLOQUE"])
        with tempfile.TemporaryDirectory() as tmp:
            m = json.loads(S.panel_y_pliegues(Path(tmp))["pliegues"].read_text(encoding="utf-8"))
        self.assertEqual(m["huella_pliegues"], tz["sha256_json"]({k: m.get(k) for k in pv["CLAVES_HUELLA"]}))


if __name__ == "__main__":
    unittest.main()
