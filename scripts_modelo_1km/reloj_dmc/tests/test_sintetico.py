"""Pruebas de sintetico.py (generadores independientes de §8, batería D y formato real).

Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
Todo lo sintético va en carpetas temporales. Ningún dato DMC y nada bajo /Volumes. Las pruebas que cargan
código fijado (descargador, adaptador) se omiten con su motivo si el archivo falta o cambió de huella.
"""
import sys

sys.dont_write_bytecode = True

import ast  # noqa: E402
import gzip  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import entorno, fijados, sintetico, tablas, tipos  # noqa: E402
from reloj_dmc import bateria  # noqa: E402

S = sintetico
AP = entorno.rutas_reales().ap


def U(*a):
    return datetime(*a, tzinfo=timezone.utc)


def _descargador(prueba):
    ruta = AP / fijados.RUTA_DESCARGADOR
    if not ruta.is_file():
        prueba.skipTest("no está el descargador en AP")
    sha = entorno.sha256_archivo(ruta)
    if sha not in fijados.VERSIONES_ADMITIDAS_C0:
        prueba.skipTest(f"el descargador en AP ({sha[:8]}…) no es una versión admitida en C0")
    return fijados.cargar_descargador(AP, sha), sha


def _adaptador(prueba):
    ruta = AP / fijados.RUTA_ADAPTADOR
    if not ruta.is_file() or entorno.sha256_archivo(ruta) != fijados.SHA_ADAPTADOR:
        prueba.skipTest("el adaptador fijado falta o cambió de huella")
    return fijados.cargar_adaptador(AP)


def _ajuste(y, tsol, armonicos=2):
    """Ajuste armónico propio de la prueba (A_k y fase en horas del máximo de cada armónico)."""
    columnas = []
    for k in range(1, armonicos + 1):
        columnas += [np.cos(2 * np.pi * k * tsol / 24), np.sin(2 * np.pi * k * tsol / 24)]
    b = np.linalg.lstsq(np.column_stack(columnas + [np.ones_like(tsol)]), y, rcond=None)[0]
    salida = []
    for k in range(armonicos):
        a, s = b[2 * k], b[2 * k + 1]
        periodo = 24 / (k + 1)
        salida.append((math.hypot(a, s), (periodo / (2 * np.pi) * math.atan2(s, a)) % periodo))
    return salida


def _anomalia_diaria(y, u):
    serie = pd.Series(y, index=pd.DatetimeIndex(u))
    return (serie - serie.groupby(serie.index.normalize()).transform("mean")).to_numpy()


def _regla(codigo, desde, hasta, minutos):
    return {"station_code": codigo, "valid_from": desde, "valid_to": hasta,
            "clock": {"verified": True, "timestamp_semantics": "instantaneous", "fixed_offset_minutes": minutos,
                      "valid_from": desde, "valid_to": hasta,
                      "source": f"reloj-dmc/v1 informe=x sha256={'0' * 64} estacion={codigo} tramo=1.1 "
                                f"protocolo={'0' * 64}"}}


class PruebasSintetico(unittest.TestCase):
    def test_generador_no_importa_el_paquete(self):
        """AST: no importa nada de reloj_dmc (ni importaciones relativas, ni importlib); sólo la biblioteca
        estándar, numpy y pandas. Al importarlo solo, no se carga ningún otro módulo del paquete."""
        fuente = Path(S.__file__).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        importados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                importados |= {a.name.split(".")[0] for a in nodo.names}
            elif isinstance(nodo, ast.ImportFrom):
                self.assertEqual(nodo.level, 0, "importación relativa")
                importados.add((nodo.module or "").split(".")[0])
            elif isinstance(nodo, ast.Name):
                self.assertNotEqual(nodo.id, "__import__")
        paquete = {p.stem for p in Path(S.__file__).parent.glob("*.py")}
        self.assertNotIn("reloj_dmc", importados)
        self.assertFalse(importados & paquete, importados & paquete)
        self.assertNotIn("importlib", importados)
        self.assertLessEqual(importados, set(sys.stdlib_module_names) | {"numpy", "pandas"})
        codigo = ("import sys; sys.dont_write_bytecode = True; import reloj_dmc.sintetico; "
                  "print(sorted(m for m in sys.modules if m.startswith('reloj_dmc') or m in ('_comun_modelo', '_common')))")
        salida = subprocess.run([sys.executable, "-B", "-c", codigo], cwd=_RAIZ, capture_output=True, text=True,
                                check=True, timeout=120)
        self.assertEqual(salida.stdout.strip(), "['reloj_dmc', 'reloj_dmc.sintetico']")

    def test_etiquetas_civiles_y_fijas_desde_utc(self):
        """Camino propio de §8: fijas, civiles de las cuatro zonas, regla vencida y calendario de Pascua."""
        e = S.etiqueta_desde_utc
        self.assertEqual(e(U(2019, 1, 1, 12), "F(-4)"), datetime(2019, 1, 1, 8))      # §8 prueba 1
        self.assertEqual(e(U(2019, 1, 1, 12), "F(0)"), datetime(2019, 1, 1, 12))
        self.assertEqual(e(U(2019, 1, 1, 12), S.PASCUA_PROPIO), datetime(2019, 1, 1, 12))
        self.assertEqual(e(U(2019, 1, 1, 22), "F(+1)"), datetime(2019, 1, 1, 23))
        otra_zona = datetime(2019, 1, 1, 9, tzinfo=timezone(timedelta(hours=-3)))      # = 12:00 UTC
        self.assertEqual(e(otra_zona, "F(-4)"), datetime(2019, 1, 1, 8))
        stgo, pascua = "C(America/Santiago)", "C(Pacific/Easter)"
        # Atraso 2019 (03:00 UTC del domingo 7 de abril) y adelanto (04:00 UTC del domingo 8 de septiembre).
        self.assertEqual(e(U(2019, 4, 7, 2), stgo), datetime(2019, 4, 6, 23))
        self.assertEqual(e(U(2019, 4, 7, 3), stgo), datetime(2019, 4, 6, 23))
        self.assertEqual(e(U(2019, 9, 8, 3), stgo), datetime(2019, 9, 7, 23))
        self.assertEqual(e(U(2019, 9, 8, 4), stgo), datetime(2019, 9, 8, 1))
        self.assertEqual(e(U(2019, 4, 7, 2), pascua), datetime(2019, 4, 6, 21))
        self.assertEqual(e(U(2019, 4, 7, 3), pascua), datetime(2019, 4, 6, 21))
        self.assertEqual(e(U(2019, 9, 8, 3), pascua), datetime(2019, 9, 7, 21))
        self.assertEqual(e(U(2019, 9, 8, 4), pascua), datetime(2019, 9, 7, 23))
        self.assertEqual(e(U(2017, 7, 1, 12), "C(America/Punta_Arenas)"), datetime(2017, 7, 1, 9))
        self.assertEqual(e(U(2025, 7, 1, 12), "C(America/Coyhaique)"), datetime(2025, 7, 1, 9))
        self.assertEqual(e(U(2023, 7, 1, 12), "C(America/Coyhaique)"), datetime(2023, 7, 1, 8))
        # Santiago 2014-2020 contra las fechas del Anexo A escritas a mano (2015 sin cambios).
        atrasos = {2014: (4, 26), 2016: (5, 14), 2017: (5, 13), 2018: (5, 12), 2019: (4, 6), 2020: (4, 4)}
        adelantos = {2014: (9, 7), 2016: (8, 14), 2017: (8, 13), 2018: (8, 12), 2019: (9, 8), 2020: (9, 6)}
        cambios = sorted([U(a, m, d, 3) + timedelta(days=1) for a, (m, d) in atrasos.items()]
                         + [U(a, m, d, 4) for a, (m, d) in adelantos.items()])
        for u in S.horas_utc(U(2014, 1, 1), U(2020, 12, 31, 23)):
            previos = [c for c in cambios if c <= u]
            verano = not previos or previos[-1].hour == 4
            self.assertEqual(e(u, stgo), (u + timedelta(hours=-3 if verano else -4)).replace(tzinfo=None), u)
        # El camino vectorial (una vez por zona) da lo mismo que la fórmula instante a instante.
        r = np.random.default_rng(1)
        for reloj in (stgo, pascua, "C(America/Punta_Arenas)", "C(America/Coyhaique)", "Cv(America/Santiago)",
                      "Cv(Pacific/Easter)", "F(-4)"):
            eje = S._etiquetas_eje(reloj)
            for k in np.concatenate([r.integers(0, S.N_EJE, 300), np.arange(S.N_EJE // 2, S.N_EJE // 2 + 48)]):
                u = U(1999, 12, 1) + timedelta(hours=int(k))
                self.assertEqual(eje[k].astype("datetime64[us]").tolist(), e(u, reloj), (reloj, u))
        with self.assertRaises(ValueError):
            e(datetime(2019, 1, 1), "F(0)")                                         # u ingenuo
        for malo in ("F(-04)", "F(4)", "C(Santiago)", "Cv(Europe/Madrid)", "UTC"):
            with self.assertRaises(ValueError):
                e(U(2019, 1, 1), malo)
        with self.assertRaises(Exception):
            e(U(2019, 1, 1), "C(America/Easter)")                                   # §2.2: no existe
        with self.assertRaises(Exception):
            S.caso_simple(reloj="C(America/Easter)")

    def test_regla_anterior_reproduce_el_anexo_a2(self):
        """Cv: regla anterior a 2008 en todos los años; repite e inventa las etiquetas en las fechas placebo
        de marzo y octubre (domingo ≥ 9) del Anexo A2, y coincide con la vigente en 2005 y 2009."""
        def etiquetas(reloj, anio):
            return [S.etiqueta_desde_utc(u, reloj) for u in S.horas_utc(U(anio, 1, 1), U(anio, 12, 31, 23))]
        placebo_atraso = {2008: (3, 8), 2010: (3, 13), 2011: (3, 12), 2012: (3, 10)}
        placebo_adelanto = {2011: (10, 9), 2012: (10, 14)}
        for zona, repetida, inexistente in (("America/Santiago", 23, 0), ("Pacific/Easter", 21, 22)):
            for anio in (2008, 2010, 2011, 2012):
                lista = etiquetas(f"Cv({zona})", anio)
                m, d = placebo_atraso[anio]
                self.assertEqual(lista.count(datetime(anio, m, d, repetida)), 2, (zona, anio))
                self.assertEqual(len(lista) - len(set(lista)), 1)
                if anio in placebo_adelanto:
                    m, d = placebo_adelanto[anio]
                    dia = d if inexistente == 0 else d - 1
                    self.assertNotIn(datetime(anio, m, dia, inexistente), lista)
        for anio in (2005, 2009):
            self.assertEqual(etiquetas("Cv(America/Santiago)", anio), etiquetas("C(America/Santiago)", anio))
        self.assertNotEqual(etiquetas("Cv(America/Santiago)", 2019), etiquetas("C(America/Santiago)", 2019))

    def test_formato_real_por_run_download(self):
        """Cliente falso y guarda con defer_heavy_checks = True; todo en carpeta temporal. Los artefactos se
        leen con leer_artefacto y coinciden fila a fila con el extracto en memoria (R-43)."""
        descargador, sha = _descargador(self)
        adaptador = _adaptador(self)
        casos = [S.caso_simple("900011", "C(America/Santiago)", "b"), S.caso_simple("900012", "F(0)", "e"),
                 S.caso_simple("900013", "F(-4)", "c"), S.caso_simple("900014", "C(Pacific/Easter)", "b", sitio="pascua")]
        self.assertEqual(tuple(descargador.RAW_COLUMNS), S.COLUMNAS_CRUDAS)
        self.assertEqual(tuple(descargador.VARIABLES), S.VARIABLES_DESCARGADOR)
        self.assertEqual(descargador.METADATA_CAUTIONS, S.METADATOS_CAUTELA)
        with tempfile.TemporaryDirectory() as carpeta:
            dmc = S.fabricar_descarga(casos, Path(carpeta), descargador, "2019-09-01", "2019-09-30")
            self.assertEqual(dmc, Path(carpeta).resolve() / "DMC")
            progreso = json.loads((dmc / "progreso.json").read_text(encoding="utf-8"))
            self.assertEqual(progreso["phase"], "finished")
            self.assertIn(progreso["status"], ("finished", "finished_with_pending"))
            self.assertEqual(progreso["script_sha256"], sha)
            self.assertTrue(progreso["verification_deferred"])
            self.assertEqual(progreso["final_verification"]["artifacts_failed"], 0)
            self.assertTrue((dmc / ".meteo_download.lock").is_file())
            catalogo = json.loads(gzip.decompress((dmc / "catalogo_nacional.json.gz").read_bytes()))
            self.assertEqual(catalogo["stations"], S.catalogo_dmc_sintetico(casos))
            self.assertNotIn("_meteo_http_parallel", sys.modules)
            for caso in casos:
                ruta = dmc / "estaciones" / caso.codigo / "2019-09.manifest.json"
                manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
                self.assertEqual(manifiesto["verification_status"], "verified_operational")
                self.assertEqual(manifiesto["script_sha256"], sha)
                rejilla = S.textos_crudos(caso, 2019, 9)
                ext, meses = S.entrada_en_memoria(caso)
                fila_mes = meses[meses.mes == 9].iloc[0]
                self.assertEqual(manifiesto["row_count"] + manifiesto["source_empty_slots"], len(rejilla))
                for campo in ("row_count", "source_empty_slots", "expected_hour_slots",
                              "duplicate_display_rows_removed"):
                    self.assertEqual(manifiesto[campo], int(fila_mes[campo]), (caso.codigo, campo))
                self.assertEqual(manifiesto["duplicate_display_rows_removed"], manifiesto["row_count"])
                payload, meta = adaptador.leer_artefacto(ruta)
                self.assertEqual(meta["content_sha256"], manifiesto["artifact_sha256"])
                filas = payload["rows"]
                ext = ext[ext.mes == 9].reset_index(drop=True)
                self.assertEqual([r["timestamp_source"] for r in filas],
                                 [d.isoformat() for d in ext.L])
                columnas = tuple(descargador.RAW_COLUMNS[2:])
                for r, (_, e) in zip(filas, ext.iterrows()):
                    textos = [r["raw_cells"][k]["text"] for k in columnas]
                    huella = hashlib.sha256(json.dumps(textos, ensure_ascii=False, separators=(",", ":"))
                                            .encode("utf-8")).hexdigest()
                    self.assertEqual(huella, e.huella)
                    for campo, columna in (("Ts", "ts"), ("QFE", "qfe"), ("Td", "td"), ("relative_humidity", "hr")):
                        valor = r["fields"][campo]["value"]
                        self.assertEqual(valor is None, math.isnan(e[columna]))
                        if valor is not None:
                            self.assertEqual(valor, e[columna])
                    self.assertEqual(r["fields"]["RR06"]["raw"].strip() != "", e.rr)
                    self.assertEqual(r["raw_cells"]["TMax"]["text"].strip() != "", e.tx)
                    self.assertEqual(r["raw_cells"]["TMin"]["text"].strip() != "", e.tn)
                    self.assertEqual(any(re.fullmatch(r"\d", r["raw_cells"][k]["text"].strip())
                                         for k in ("CL", "CM", "CH")), e.observador)
            # E1c: la hora civil de Santiago deja una casilla menos en el mes del adelanto (2019-09-08).
            m = json.loads((dmc / "estaciones/900011/2019-09.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(m["row_count"] + m["source_empty_slots"], m["expected_hour_slots"] - 1)
            self.assertNotIn("2019-09-08T00:00:00", m["available_hours"])
        # Una raíz bajo /Volumes (también en minúsculas) se rechaza sin consultarla (§8, prueba 27): con un registro
        # propio en bloqueo, el rechazo es el de la guarda y no hay ningún acceso (antes, os.lstat al resolverla).
        from reloj_dmc import verificar_reloj_dmc as V
        with V.RegistroAccesos((V.VOLUMES,), bloquear=True) as registro:
            for raiz in ("/Volumes/Datos/x", "/volumes/Datos/x"):
                with self.assertRaisesRegex(ValueError, "nunca se escriben bajo /Volumes"):
                    S.GuardaFalsa(Path(raiz))
        self.assertEqual(registro.accesos, [])
        with self.assertRaises(ValueError):
            S.fabricar_descarga(casos, AP / "tmp_sintetico", descargador, "2019-09-01", "2019-09-30")
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            guarda = S.GuardaFalsa(Path(a))
            with self.assertRaises(ValueError):
                guarda.write_atomic_bytes(Path(b) / "x.json", b"{}")

    def test_una_sola_repetida_y_sin_inexistente(self):
        """Relojes civiles: sin la etiqueta inexistente y con una sola repetida (la del primer u)."""
        stgo = S.caso_simple("900021", "C(America/Santiago)", "a")
        abril = [tuple(f[:2]) for f in S.textos_crudos(stgo, 2019, 4)]
        septiembre = [tuple(f[:2]) for f in S.textos_crudos(stgo, 2019, 9)]
        self.assertEqual(len(abril), len(set(abril)))
        self.assertEqual((len(abril), len(septiembre)), (720, 719))
        self.assertIn(("06", "23:00"), abril)
        self.assertNotIn(("08", "00:00"), septiembre)
        mapa = S.u_de_etiqueta(stgo)
        self.assertEqual(mapa[datetime(2019, 4, 6, 23)], U(2019, 4, 7, 2))
        self.assertEqual(mapa[datetime(2019, 4, 7, 0)], U(2019, 4, 7, 4))
        self.assertNotIn(datetime(2019, 9, 8, 0), mapa)
        pascua = S.caso_simple("900022", "C(Pacific/Easter)", "a", sitio="pascua")
        abril = [tuple(f[:2]) for f in S.textos_crudos(pascua, 2019, 4)]
        septiembre = [tuple(f[:2]) for f in S.textos_crudos(pascua, 2019, 9)]
        self.assertEqual((len(abril), len(set(abril)), len(septiembre)), (720, 720, 719))
        self.assertIn(("06", "21:00"), abril)
        self.assertNotIn(("07", "22:00"), septiembre)
        fijo = S.caso_simple("900023", "F(0)", "a")
        self.assertEqual(len(S.textos_crudos(fijo, 2019, 9)), 720)
        cambio = S.caso_simple("900024", "F(-4);F(0)@2018-07-01T00:00Z", "a", anios=(2018, 2018))
        mapa = S.u_de_etiqueta(cambio)
        self.assertEqual(mapa[datetime(2018, 6, 30, 19)], U(2018, 6, 30, 23))
        self.assertEqual(mapa[datetime(2018, 7, 1, 0)], U(2018, 7, 1, 0))
        for h in (20, 21, 22, 23):
            self.assertNotIn(datetime(2018, 6, 30, h), mapa)
        self.assertEqual(len(set(mapa.values())), len(mapa))

    def test_extracto_en_memoria_con_el_esquema_de_extraer_dmc(self):
        """ESQUEMA_EXTRACTO_HORA y ESQUEMA_MES; filas ordenadas sin duplicados; meses sin filas excluidos;
        determinista."""
        self.assertEqual(S.ESQUEMA_EXTRACTO, tipos.ESQUEMA_EXTRACTO_HORA)
        self.assertEqual(S.ESQUEMA_MESES, tipos.ESQUEMA_MES)
        self.assertEqual(S.ESQUEMA_ISD_PROPIO, tipos.ESQUEMA_ISD)
        self.assertEqual(S.VARIABLES_ERA5, tipos.VARIABLES_ERA5)
        caso = S.caso_simple("900031", "C(America/Santiago)", "c", "ralo2008", anios=(2009, 2010))
        ext, meses = S.entrada_en_memoria(caso)
        tipos.validar_esquema(ext, tipos.ESQUEMA_EXTRACTO_HORA, nombre="extracto")
        tipos.validar_esquema(meses, tipos.ESQUEMA_MES, nombre="meses")
        self.assertTrue(ext.L.is_monotonic_increasing and ext.L.is_unique)
        self.assertEqual(len(meses), 24)
        entran = meses[meses.entra]
        self.assertGreater((~meses.entra).sum(), 0)                    # 2009 al 10 %: meses sin filas
        self.assertTrue((meses.loc[~meses.entra, "row_count"] == 0).all())
        self.assertTrue((meses.loc[~meses.entra, "motivo_exclusion"] == S.MOTIVO_MES_SIN_FILAS).all())
        self.assertEqual(int(entran.row_count.sum()), len(ext))
        self.assertEqual(sorted(ext.id_artefacto.unique()), sorted(entran.id_artefacto.astype(int)))
        self.assertTrue((ext.groupby("id_artefacto").size().to_numpy()
                         == entran.sort_values("id_artefacto").row_count.to_numpy()).all())
        self.assertTrue(((ext.motivo_ts == 1) == ext.ts.isna()).all())
        self.assertTrue(((ext.motivo_qfe == 1) == ext.qfe.isna()).all())
        solo_rr = ext[~ext.medida]
        self.assertTrue(len(solo_rr) and solo_rr.rr.all())               # filas con sólo RR06 (aeródromo)
        self.assertTrue(ext.huella.str.fullmatch(r"[0-9a-f]{64}").all())
        self.assertEqual(set(entran.p_ts.dropna()), {1})
        self.assertEqual(entran.script_sha256.unique().tolist(), [S.SCRIPT_SHA256_VIGENTE])
        self.assertTrue(meses.manifiesto.str.fullmatch(r"DMC/estaciones/900031/\d{4}-\d{2}\.manifest\.json").all())
        self.assertEqual(meses.lat_txt.unique().tolist(), ["-33.4"])
        S.vaciar_caches()
        ext2, meses2 = S.entrada_en_memoria(caso)
        pd.testing.assert_frame_equal(ext, ext2)
        pd.testing.assert_frame_equal(meses, meses2)
        isd = S.isd_sintetico(S.caso_simple("900032", "F(-3)", "b"))
        tipos.validar_esquema(isd, tipos.ESQUEMA_ISD, nombre="isd")

    def test_tipos_de_estacion_marcas_y_horarios(self):
        """a: marcas en su propio reloj; b: RR06 a las 00/06/12/18 UTC con observador; Pascua 03/09/15/21;
        c y d: ventana civil (d con cambio administrativo); e: sólo Ts; f: cada 6 h; g: Ts y QFE en relojes
        distintos."""
        def extracto(reloj, tipo, sitio="santiago", anios=(2019, 2019)):
            return S.entrada_en_memoria(S.caso_simple("900041", reloj, tipo, sitio=sitio, anios=anios))[0]

        def horas(serie):
            return set(serie.dt.hour.unique())
        a = extracto("F(-4)", "a")
        self.assertEqual(horas(a.L[a.rr]), {0, 6, 12, 18})
        self.assertEqual((horas(a.L[a.tx]), horas(a.L[a.tn])), ({0}, {12}))
        self.assertFalse(a.observador.any())
        b = extracto("F(-4)", "b")
        self.assertEqual(horas(b.L[b.rr]), {20, 2, 8, 14})                 # clase 2 (§4.2)
        self.assertEqual((horas(b.L[b.tx]), horas(b.L[b.tn])), ({20}, {8}))
        self.assertEqual({h % 3 for h in horas(b.L[b.observador])}, {2})
        self.assertGreaterEqual(b[b.rr].observador.mean(), 0.5)
        p = extracto(S.PASCUA_PROPIO, "b", "pascua")
        self.assertEqual(horas(p.L[p.rr]), {3, 9, 15, 21})
        self.assertEqual((horas(p.L[p.tx]), horas(p.L[p.tn])), ({3}, {15}))
        c = extracto("F(0)", "c")
        enero, julio = c[c.L.dt.month == 1], c[c.L.dt.month == 7]
        self.assertEqual(horas(enero.L[enero.ts.notna()]), set(range(11, 24)))
        self.assertEqual(horas(julio.L[julio.ts.notna()]), set(range(12, 24)) | {0})
        self.assertEqual(horas(c.L[~c.medida]), {0, 6})      # sólo RR06: 06 UTC y, en verano, 00 UTC (21 h civil)
        self.assertEqual(horas(julio.L[~julio.medida]), {6})
        self.assertTrue(c[~c.medida].rr.all())
        d = extracto("F(0)", "d", anios=(2016, 2016))
        junio, julio = d[d.L.dt.month == 6], d[d.L.dt.month == 7]       # invierno; el cambio es el 1 de julio
        self.assertEqual(horas(junio.L[junio.ts.notna()]), set(range(12, 24)) | {0})
        self.assertEqual(horas(julio.L[julio.ts.notna()]), set(range(13, 24)) | {0, 1})
        e = extracto("F(0)", "e")
        self.assertTrue(e.ts.notna().all() and e.qfe.isna().all() and e.td.isna().all() and e.hr.isna().all())
        self.assertFalse((e.rr | e.tx | e.tn | e.observador | e.qff_numerica | e.viento_valido).any())
        f = extracto("F(-3)", "f")
        self.assertEqual(horas(f.L), {21, 3, 9, 15})
        self.assertTrue(f.rr.all() and f.observador.all())
        g = S.caso_simple("900042", "Ts:C(America/Santiago)|QFE:F(0)", "g")
        ts, qfe = S.u_de_etiqueta(g, "Ts"), S.u_de_etiqueta(g, "QFE")
        self.assertEqual(ts[datetime(2019, 7, 1, 12)], U(2019, 7, 1, 16))
        self.assertEqual(qfe[datetime(2019, 7, 1, 12)], U(2019, 7, 1, 12))
        ext_g = S.entrada_en_memoria(g)[0].set_index("L")
        h0 = pd.Timestamp("2019-09-08T00:00")
        self.assertTrue(math.isnan(ext_g.loc[h0, "ts"]) and not math.isnan(ext_g.loc[h0, "qfe"]))
        self.assertFalse(ext_g[["rr", "tx", "tn", "observador"]].any().any())

    def test_escenarios_de_faltantes(self):
        """30 % faltante en bloques de días; 2008-2009 al 10 %; completo sin huecos."""
        def cobertura(escenario, anios):
            caso = S.caso_simple("900051", "F(0)", "a", escenario, anios=anios)
            ext = S.entrada_en_memoria(caso)[0]
            por_dia = ext.groupby(ext.L.dt.normalize()).size()
            dias = pd.date_range(f"{anios[0]}-01-01", f"{anios[1]}-12-31", freq="D")
            return por_dia.reindex(dias, fill_value=0)
        completo = cobertura("completo", (2012, 2013))
        self.assertTrue((completo == 24).all())
        faltante = cobertura("faltante30", (2010, 2019))
        self.assertTrue(faltante.isin([0, 24]).all())                       # bloques de días UTC enteros
        self.assertAlmostEqual((faltante == 0).mean(), 0.30, delta=0.04)
        ralo = cobertura("ralo2008", (2008, 2011))
        self.assertAlmostEqual((ralo[:"2009-12-31"] == 24).mean(), 0.10, delta=0.05)
        self.assertTrue((ralo["2010-01-01":] == 24).all())

    def test_modelo_fisico_s2_y_fase_termica(self):
        """S2 = 1,16·cos³(lat) hPa con máximo a las 9,75 h solares y ±20 % semestral; Ts con máximo a las 15 h;
        las perturbaciones de D2 mueven lo que dicen."""
        u = np.arange(np.datetime64("2012-01-01T00", "h"), np.datetime64("2016-01-01T00", "h"))
        k = S._indice_eje(u).astype(float)

        def fases(caso, columna, referencia=False, sesgo=0.0):
            tabla = S.referencia_era5(caso, u, sesgo_termico_h=sesgo) if referencia else S.senales(caso, u)
            return _ajuste(_anomalia_diaria(tabla[columna].to_numpy(), u), S._hora_solar(k, caso.lon))
        for sitio in ("santiago", "arica", "punta_arenas"):
            caso = S.caso_simple("900061", sitio=sitio, anios=(2012, 2015))
            esperado = 1.16 * math.cos(math.radians(caso.lat)) ** 3
            for columna, referencia in (("qfe", False), ("sp", True)):
                (_, _), (a2, psi2) = fases(caso, columna, referencia)
                self.assertAlmostEqual(a2 / esperado, 1.0, delta=0.03)
                self.assertAlmostEqual(psi2, 9.75, delta=0.05)
            (_, phi1), _ = fases(caso, "ts")
            self.assertAlmostEqual(phi1, 15.0, delta=0.1)
        base = S.caso_simple("900062", anios=(2012, 2015))
        (_, phi1), _ = fases(base, "t2m", referencia=True, sesgo=2.5)
        self.assertAlmostEqual(phi1, 17.5, delta=0.1)
        for perturbacion, valor, columna, armonico, esperado in (
                ("desfase_termico_estacion", -2.5, "ts", 0, 12.5),
                ("fase_s2_estacion", 0.75, "qfe", 1, 10.5),
                ("semantica", 0.5, "ts", 0, 15.5)):
            caso = S.caso_simple("900063", perturbaciones={perturbacion: valor}, anios=(2012, 2015))
            self.assertAlmostEqual(fases(caso, columna)[armonico][1], esperado, delta=0.1, msg=perturbacion)
        caso = S.caso_simple("900064", perturbaciones={"s1_local_amplitud": 2.0, "s1_local_desfase": 4.0},
                             anios=(2012, 2015))
        (a1, phi1), _ = fases(caso, "qfe")
        self.assertAlmostEqual(a1, 2.0, delta=0.05)
        self.assertAlmostEqual(phi1, S.S1_HORA_MAX + 4.0, delta=0.1)
        # Modulación semestral: S2 en los equinoccios ≈ 1,2/0,8 veces la de los solsticios.
        s = S.senales(base, u)
        meses = pd.DatetimeIndex(u).month
        tsol = S._hora_solar(k, base.lon)
        anom = _anomalia_diaria(s.qfe.to_numpy(), u)
        equinoccio = np.isin(meses, (3, 9))
        solsticio = np.isin(meses, (6, 12))
        cociente = _ajuste(anom[equinoccio], tsol[equinoccio])[1][0] / _ajuste(anom[solsticio], tsol[solsticio])[1][0]
        self.assertAlmostEqual(cociente, 1.2 / 0.8, delta=0.15)

    def test_serie_era5_memoria_y_sesgo(self):
        """SerieEra5Memoria: tiene, valores (NaN fuera del eje, fuera de la hora en punto o sin píxel) y media;
        la de la red usa el sesgo común y coincide con referencia_era5."""
        casos = [S.caso_simple("900071"), S.caso_simple("900072", sitio="pascua"),
                 S.caso_simple("900073", sitio="valdivia", perturbaciones={"costera": 1})]
        serie = S.serie_era5_de_casos(casos)
        self.assertEqual(serie.t0, np.datetime64("2000-01-01T00", "h"))
        self.assertEqual(serie.n_horas, int((S.ERA5_ULTIMA - S.ERA5_T0) // np.timedelta64(1, "h")) + 1)
        stgo, pascua, valdivia = (S._pixel_de(c.lat, c.lon)[0] for c in casos)
        self.assertTrue(serie.tiene(stgo))
        self.assertFalse(serie.tiene(pascua))
        self.assertFalse(serie.tiene(valdivia))                              # costera: su celda sin dato
        self.assertTrue(serie.tiene(S._pixel_por_indices(*S._pixel_de(casos[2].lat, casos[2].lon)[3:])[0] + 1))
        u = np.array(["1999-12-31T23", "2000-01-01T00", "2020-01-01T00", "2026-09-15T23", "2026-09-16T00"],
                     dtype="datetime64[h]")
        x = serie.valores(stgo, "t2m", u)
        self.assertTrue(np.isnan(x[[0, 4]]).all() and np.isfinite(x[1:4]).all())
        self.assertTrue(np.isnan(serie.valores(stgo, "sp", np.array(["2020-01-01T00:30"], dtype="datetime64[m]"))).all())
        self.assertTrue(np.isnan(serie.valores(pascua, "sp", u)).all())
        ref = S.referencia_era5(casos[0], u[1:4])
        np.testing.assert_array_equal(serie.valores(stgo, "sp", u[1:4]), ref.sp.to_numpy())
        z_pix = 44330.8 * (1 - (serie.media(stgo, "sp") / 1013.25) ** 0.190263)
        self.assertAlmostEqual(z_pix, casos[0].alt_m, delta=60)
        with self.assertRaises(ValueError):
            serie.valores(stgo, "tp", u)
        sesgada = S.serie_era5_de_casos([S.caso_simple("900074", perturbaciones={"sesgo_termico_referencia": 2.5})])
        ref = S.referencia_era5(casos[0], u[1:4], sesgo_termico_h=2.5)
        np.testing.assert_array_equal(sesgada.valores(stgo, "t2m", u[1:4]), ref.t2m.to_numpy())
        with self.assertRaises(ValueError):
            S.serie_era5_de_casos([S.caso_simple("900075"),
                                   S.caso_simple("900076", sitio="arica", perturbaciones={"sesgo_termico_referencia": 1.0})])
        df = pd.DataFrame({v: np.arange(3.0) for v in S.VARIABLES_ERA5})
        propia = S.SerieEra5Memoria(np.datetime64("2010-01-01T00", "h"), {7: df})
        self.assertEqual(propia.n_horas, 3)
        np.testing.assert_array_equal(propia.valores(7, "u10", np.array(["2010-01-01T02", "2010-01-01T03"],
                                                                         dtype="datetime64[h]")), [2.0, np.nan])
        self.assertEqual(propia.media(7, "v10"), 1.0)

    def test_catalogo_de_pixeles(self):
        """3 × 3 celdas por sitio; sin dato donde no hay píxel; cod_comuna 0 en el incierto; territorio y P
        iguales a los de tablas."""
        casos = [S.caso_simple("900081"), S.caso_simple("900082", sitio="pascua"),
                 S.caso_simple("900083", sitio="incierto"), S.caso_simple("900084", sitio="juan_fernandez"),
                 S.caso_simple("900085", sitio="punta_arenas"), S.caso_simple("900086", sitio="coyhaique"),
                 S.caso_simple("900087", sitio="valdivia", perturbaciones={"costera": 1})]
        cat = S.catalogo_pixeles_sintetico(casos)
        self.assertEqual(len(cat), 9 * len(casos))
        self.assertTrue(cat.pixel_id.is_unique)
        for c in tablas.COLUMNAS_CELDA:
            self.assertIn(c, cat.columns)
        mapa_macrozona = {13: "centro", 12: "austral", 11: "austral", 5: "centro", 14: "sur"}
        for caso in casos:
            pid = tablas.celda_que_contiene(caso.lat, caso.lon, cat)
            fila = cat.set_index("pixel_id").loc[pid]
            self.assertEqual(int(fila.cod_comuna), caso.cod_comuna)
            costera = bool(caso.perturbaciones.get("costera"))
            self.assertEqual(bool(fila.valido), caso.con_pixel and not costera)
            territorio, _, _, _, P = tablas.territorio_y_P(caso.lat, caso.lon, cat, mapa_macrozona)
            propio = S.territorio_sintetico(caso.lat, caso.lon, caso.cod_comuna)
            self.assertEqual(str(territorio), propio)
            self.assertEqual(tuple(h.id for h in P), tuple(S._id_tipos(h) for h in S._P_POR_TERRITORIO[propio]))
        vecinas = cat[(cat.cod_comuna == 14101)]
        self.assertEqual(int(vecinas.valido.sum()), 8)

    def test_isd_sintetico(self):
        """FM-12 coincide con la Ts de la DMC en el desfase verdadero y casi nunca en otro; FM-15 por grados."""
        caso = S.caso_simple("900091", "F(-3)", "b")
        isd = S.isd_sintetico(caso)
        ext = S.entrada_en_memoria(caso)[0]
        doce = isd[isd.tipo_parte == "FM-12"].set_index("u").tmp
        quince = isd[isd.tipo_parte == "FM-15"].set_index("u").tmp
        self.assertEqual(set(doce.index.hour % 3), {0})
        ts = ext.set_index("L").ts.dropna()

        def fraccion(partes, c, igual):
            u = ts.index - pd.Timedelta(hours=c)
            par = partes.reindex(u).to_numpy()
            ok = ~np.isnan(par)
            return igual(ts.to_numpy()[ok], par[ok]).mean()
        def i12(a, b):
            return np.abs(a - b) <= 0.05

        def i15(a, b):
            return np.floor(a + 0.5) == b
        self.assertGreater(fraccion(doce, -3, i12), 0.95)
        for c in (0, -4, -2):
            self.assertLess(fraccion(doce, c, i12), 0.2)
        self.assertGreater(fraccion(quince, -3, i15), 0.95)
        self.assertLess(fraccion(quince, 0, i15), 0.5)

    def test_ida_y_vuelta_con_el_adaptador(self):
        """_utc(L, regla emitida) == u en toda etiqueta con regla; una regla equivocada da fallas."""
        adaptador = _adaptador(self)
        fijo = S.caso_simple("900101", "F(-4)", "b")
        civil = S.caso_simple("900102", "C(America/Santiago)", "a")
        g = S.caso_simple("900103", "Ts:C(America/Santiago)|QFE:F(0)", "g")
        buena = {"politicas_reloj": [
            _regla("900101", "2019-01-01T00:00:00", "2019-12-31T23:00:00", -240),
            _regla("900102", "2019-01-01T00:00:00", "2019-04-06T22:00:00", -180),    # §7.2: bordes civiles
            _regla("900102", "2019-04-07T00:00:00", "2019-09-07T23:00:00", -240),
            _regla("900102", "2019-09-08T01:00:00", "2019-12-31T23:00:00", -180)]}
        self.assertEqual(S.comprobar_ida_y_vuelta(buena, [fijo, civil, g], adaptador), [])
        mala = {"politicas_reloj": [_regla("900102", "2019-01-01T00:00:00", "2019-12-31T23:00:00", -240),
                                    _regla("900103", "2019-01-01T00:00:00", "2019-12-31T23:00:00", 0)]}
        fallas = S.comprobar_ida_y_vuelta(mala, [fijo, civil, g], adaptador, maximo_por_estacion=3)
        self.assertEqual(len([f for f in fallas if f.startswith("900102 ")]), 3)
        self.assertTrue(any(re.fullmatch(r"900102: \d+ fallas más", f) for f in fallas))
        self.assertTrue(any(f.startswith("900103 Ts ") for f in fallas))
        self.assertFalse(any(f.startswith("900103 QFE ") for f in fallas))
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "politica.json"
            ruta.write_text(json.dumps(buena), encoding="utf-8")
            self.assertEqual(S.comprobar_ida_y_vuelta(ruta, [fijo, civil], adaptador), [])

    def test_equivalentes_en_P(self):
        """Verdad por año, etiqueta a etiqueta: fusiones por calendario, relojes fuera de P y reglas vencidas."""
        def eq(reloj, anio, sitio="santiago"):
            return S.equivalentes_en_P(S.caso_simple("900111", reloj, "a", sitio=sitio, anios=(anio, anio)), anio)
        self.assertEqual(eq("F(0)", 2019), ("F(0)",))
        self.assertEqual(eq("F(-3)", 2015), ("F(-3)", "C(Santiago)"))
        self.assertEqual(eq("C(America/Santiago)", 2019), ("C(Santiago)",))
        self.assertEqual(eq("F(+1)", 2019), ())
        self.assertEqual(eq("Cv(America/Santiago)", 2009), ("C(Santiago)",))
        self.assertEqual(eq("Cv(America/Santiago)", 2019), ())
        self.assertEqual(eq("C(America/Punta_Arenas)", 2017, "punta_arenas"), ("F(-3)", "C(Punta_Arenas)"))
        self.assertEqual(eq("C(Pacific/Easter)", 2015, "pascua"), ("F(-5)", "C(Pacific/Easter)"))
        cambio = S.caso_simple("900112", "F(-4);F(0)@2018-07-01T00:00Z", "a", anios=(2017, 2019))
        self.assertEqual([S.equivalentes_en_P(cambio, a) for a in (2017, 2018, 2019)], [("F(-4)",), (), ("F(0)",)])
        self.assertEqual(S.equivalentes_en_P(cambio, 2020), ())

    def test_regla_anterior_difiere_de_la_vigente_solo_en_el_atraso_de_2008_y_2010(self):
        """Riesgo 3 de «Ola 4a cerrada»: el Cv del generador cumple §8.D («la regla anterior a 2008 aplicada en
        todos los años») y el Anexo A2 (marzo y octubre, domingo ≥ 9); no es un error suyo. En 2008, 2009 y
        2010 el adelanto de esa regla coincide con el vigente; el atraso difiere 3 semanas en 2008 y en 2010
        (del sábado placebo del A2 al atraso real) y nada en 2009. En 2010 ningún reloj de P coincide en todas
        las etiquetas, así que §8.D cuenta como errónea toda confirmación (ver PROPUESTA_ENMIENDA_3.md, E3-2)."""
        def distintos(anio):
            return [u for u in S.horas_utc(U(anio, 1, 1), U(anio, 12, 31, 23))
                    if S.etiqueta_desde_utc(u, "Cv(America/Santiago)") != S.etiqueta_desde_utc(u, "C(America/Santiago)")]
        tres_semanas = 21 * 24
        for anio, desde, hasta in ((2008, U(2008, 3, 9, 3), U(2008, 3, 30, 3)),
                                   (2010, U(2010, 3, 14, 3), U(2010, 4, 4, 3))):
            d = distintos(anio)
            self.assertEqual((d[0], d[-1] + timedelta(hours=1), len(d)), (desde, hasta, tres_semanas), anio)
        self.assertEqual(distintos(2009), [])
        for anio, esperado in ((2008, ()), (2009, ("C(Santiago)",)), (2010, ())):
            caso = S.caso_simple("900113", "Cv(America/Santiago)", "b", anios=(anio, anio))
            self.assertEqual(S.equivalentes_en_P(caso, anio), esperado, anio)

    def test_lecturas_del_encabezado_con_identificador_y_enmienda_1_al_dia(self):
        """Las lecturas que van al addendum se citan por su identificador: SIN-1 (Cv) y SIN-2 (tipo d) existen en
        el encabezado. Y el módulo no da por pendiente la Enmienda 1, adoptada y anclada (APH 81bb100)."""
        doc = " ".join(S.__doc__.split())
        self.assertRegex(doc, r"- SIN-1\. Cv\(Z\) es «la regla anterior a 2008 aplicada en todos los años»")
        self.assertRegex(doc, r"- SIN-2\. Tipo d: la ventana civil de 08-20 h pasa a 09-21 h el 2016-07-01")
        fuente = " ".join(Path(S.__file__).read_text(encoding="utf-8").split())
        vieja = re.findall(r"borrador de la Enmienda 1|Enmienda 1[^.;]{0,80}no adoptad", fuente)
        self.assertEqual(vieja, [])


class PruebasRiesgosC1(unittest.TestCase):
    """Trazas de decisión con estaciones del generador para los riesgos de C1 que trató la Enmienda 3
    (PROPUESTA_ENMIENDA_3.md y las decisiones del autor del 2026-10-24). No prueban el generador: lo usan para
    fabricar la celda de la batería que expone el riesgo, en memoria y con la referencia sintética (como
    bateria.correr_red). Fijan en positivo el comportamiento con la enmienda, sin expectedFailure."""

    @classmethod
    def setUpClass(cls):
        import gzip as _gzip
        import zoneinfo
        from reloj_dmc import extraccion, orquestacion, umbrales
        zoneinfo.reset_tzpath(to=[])
        zoneinfo.ZoneInfo.clear_cache()
        aph = AP.parent / "Air-Pollution-Health-Chile"
        if not (aph / umbrales.JSON_C0).is_file() or not (AP / fijados.RUTA_COMUN_MODELO).is_file():
            raise unittest.SkipTest("faltan los umbrales de C0 o _comun_modelo.py; no se da por aprobada")
        cls.U, cls.T, cls.MZ = umbrales.cargar_c0(aph), tablas.cargar_tablas(), fijados.macrozona_region(AP)
        cls.extraccion, cls.O, cls.gzip = extraccion, orquestacion, _gzip

    def _red(self, casos):
        serie = S.serie_era5_de_casos(casos)
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "catalogo.json.gz"
            ruta.write_bytes(self.gzip.compress(json.dumps({"stations": S.catalogo_dmc_sintetico(casos)}).encode()))
            catalogo, _ = self.extraccion.leer_catalogo_dmc(ruta)
        pixeles = S.catalogo_pixeles_sintetico(casos)
        validos = {int(p) for p in pixeles.loc[pixeles["valido"], "pixel_id"]}
        enlaces = self.extraccion.enlazar_pixeles(catalogo, pixeles, validos, self.U)
        infos = self.extraccion.info_estaciones(catalogo, pixeles, enlaces, {p: serie.media(p, "sp") for p in validos},
                                                {}, self.MZ, self.U)
        entradas = [self.O.EntradaEstacion(infos[c.codigo], *S.entrada_en_memoria(c)) for c in casos]
        return self.O.evaluar_red(lambda: entradas, serie, self.T, self.U, self.O.OpcionesCorrida())

    def test_reglas_vencidas_en_automatica_no_se_confirman(self):
        """E3-2 con la Enmienda 3 (A′ más R). Hora civil con la regla anterior a 2008 en una automática de 24 h
        (sin observador: E2 sin información), 2018-2019. Con el texto v1.0.2 y la lectura R-52 por H se
        confirmaba F(−4) en los dos años, con apoyo de E1a y E3p (§8.D lo cuenta como erróneo). Ahora:
        - el mecanismo de E3p sigue igual por año-régimen: R0 mezcla −3 y −4 y no es fino, su gruesa da F(0)
          incompatible y deja residual a F(−4); R1 es fino en −4;
        - R (LF-17): R0 es informativo para todas las H, así que E3p anual ya no es compatible con F(−4)
          (queda residual) y no apoya;
        - A′: E1a señala reloj anómalo en los dos años y quedan discrepantes; ninguno se confirma.
        Con un solo año (2019) A′ no forma el patrón (≥ 2 ausentes), y R basta: el año no se confirma."""
        from reloj_dmc import lineas_fisicas, lineas_registro
        caso = S.caso_simple("907201", "Cv(America/Santiago)", "a", anios=(2018, 2019))
        r = self._red([caso])
        decisiones = {d.anio: d for d in r.decisiones if d.codigo == caso.codigo}
        self.assertEqual(sorted(decisiones), [2018, 2019])
        e = next(ev for ev in r.evidencias if ev.info.codigo == caso.codigo).estados
        e3p = e[e["linea"] == "E3p"]

        def estado(regla, unidad, anio, H):
            fila = e3p[(e3p["regla"] == regla) & (e3p["unidad"] == unidad) & (e3p["anio"] == anio) & (e3p["H"] == H)]
            self.assertEqual(len(fila), 1, (regla, unidad, anio, H))
            return str(fila["estado"].iloc[0])

        for anio in (2018, 2019):
            self.assertEqual(S.equivalentes_en_P(caso, anio), ())         # §8.D: toda confirmación es errónea
            d = decisiones[anio]
            self.assertNotEqual(str(d.veredicto), "confirmado", anio)
            self.assertNotIn("E3p", tuple(map(str, d.lineas_apoyo)), anio)
            self.assertEqual(estado("gruesa", "R0", anio, "F(0)"), "incompatible", anio)
            self.assertEqual(estado("gruesa", "R0", anio, "F(-4)"), "sin_informacion", anio)
            self.assertEqual(estado("fina", "R0", anio, "F(-4)"), "sin_informacion", anio)
            self.assertEqual(estado("fina", "R1", anio, "F(-4)"), "compatible", anio)
            self.assertEqual(estado("fina", "R1", anio, "F(-3)"), "incompatible", anio)
        anual = lineas_fisicas.e3p_anual(e3p[e3p["regla"] == "gruesa"], e3p[e3p["regla"] == "fina"], True)
        for anio in (2018, 2019):
            fila = anual[(anual["anio"] == anio) & (anual["H"] == "F(-4)")]
            self.assertEqual((str(fila["estado"].iloc[0]), fila["motivo"].iloc[0]), ("sin_informacion", "residual"))
        # Un solo año: sin el patrón de A′, R basta para que no se confirme.
        solo = S.caso_simple("907203", "Cv(America/Santiago)", "a", anios=(2019, 2019))
        r1 = self._red([solo])
        ev1 = next(ev for ev in r1.evidencias if ev.info.codigo == solo.codigo)
        self.assertFalse(lineas_registro.patron_regla_vencida(ev1.estados))
        d1 = {d.anio: d for d in r1.decisiones if d.codigo == solo.codigo}[2019]
        self.assertNotEqual(str(d1.veredicto), "confirmado")
        self.assertNotIn("E3p", tuple(map(str, d1.lineas_apoyo)))

    def test_reglas_vencidas_a_prima_patron_por_regla_y_estacion_inestable(self):
        """Enmienda 3, E3-2, opción A′ con el patrón por regla vencida (lineas_registro, lectura 9). La misma
        automática Cv del tipo a, 2018-2019, que con el texto v1.0.2 se confirmaba F(−4) (la prueba
        anterior): los adelantos de octubre de la regla anterior a 2008
        (2018-10-14 y 2019-10-13, 00:00) quedan ausentes, forman el patrón de regla vencida, los dos años
        quedan discrepantes por reloj anómalo en E1a y la estación, inestable con el motivo «civil con
        reglas vencidas». Ningún año confirmado y ningún mes con regla. Una F(−4) de 24 h en la misma red
        sigue confirmada."""
        from reloj_dmc import decision, lineas_registro
        caso = S.caso_simple("907201", "Cv(America/Santiago)", "a", anios=(2018, 2019))
        control = S.caso_simple("907202", "F(-4)", "a", anios=(2018, 2019))
        r = self._red([caso, control])
        ev = next(e for e in r.evidencias if e.info.codigo == caso.codigo)
        rv = ev.eventos[(ev.eventos["linea"] == "E1a") & (ev.eventos["clase_evento"] == "regla_vencida")]
        self.assertEqual(dict(zip(rv["etiqueta"], rv["resultado"])),
                         {"2018-10-14T00:00": "ausente", "2019-10-13T00:00": "ausente"})
        self.assertTrue(lineas_registro.patron_regla_vencida(ev.estados))
        decisiones = {d.anio: d for d in r.decisiones if d.codigo == caso.codigo}
        for anio in (2018, 2019):
            d = decisiones[anio]
            self.assertEqual((str(d.veredicto), str(d.motivo)), ("discrepante", "reloj_anomalo"), anio)
            self.assertIn("E1a", d.detalle)
        rr = r.resultados_rachas[caso.codigo]
        self.assertTrue(rr.inestable)
        self.assertIn(decision.MOTIVO_INESTABLE_REGLAS_VENCIDAS, rr.motivos_inestable)
        self.assertEqual(r.meses_con_regla[caso.codigo], {})
        self.assertEqual(r.estaciones[caso.codigo]["motivo"], "inestable")
        otro = {d.anio: d for d in r.decisiones if d.codigo == control.codigo}
        self.assertEqual({a: (str(d.veredicto), d.clase_confirmada) for a, d in otro.items()},
                         {2018: ("confirmado", "F(-4)"), 2019: ("confirmado", "F(-4)")})
        self.assertFalse(lineas_registro.patron_regla_vencida(
            next(e for e in r.evidencias if e.info.codigo == control.codigo).estados))


class PruebasBateriaD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tabla = S.especificacion_bateria()

    def test_d_tabla_determinista_y_su_sha256(self):
        """bateria_v1.csv igual en dos generaciones, con las columnas de bateria.COLUMNAS_BATERIA."""
        self.assertEqual(S.COLUMNAS_BATERIA, bateria.COLUMNAS_BATERIA)
        self.assertEqual(tuple(self.tabla.columns), bateria.COLUMNAS_BATERIA)

        def sha(t):
            return hashlib.sha256(t.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()
        self.assertEqual(sha(self.tabla), sha(S.especificacion_bateria()))

    def test_d_factores_celdas_y_redes(self):
        """D1 (20 réplicas), D2 (10), D3 (10); celda = factores sin la réplica; redes por sesgo y réplica (R-29)."""
        t = self.tabla
        self.assertEqual(t.groupby("bloque").size().to_dict(), {"D1": 4740, "D2": 2520, "D3": 60})
        self.assertEqual(t.groupby("bloque").celda.nunique().to_dict(), {"D1": 237, "D2": 252, "D3": 6})
        replicas = t.groupby(["bloque", "celda"]).replica.agg(["min", "max", "count"])
        for bloque, n in S.REPLICAS_BATERIA.items():
            self.assertTrue((replicas.loc[bloque] == [1, n, n]).all().all(), bloque)
        self.assertTrue(t.caso.str.fullmatch(r"9\d{5}").all() and t.caso.is_unique)
        self.assertTrue(t.semilla.is_unique and (t.semilla >= 0).all())
        d1 = t[t.bloque == "D1"]
        self.assertEqual(set(d1[d1.tipo == "g"].reloj_verdadero), {"Ts:C(America/Santiago)|QFE:F(0)"})
        self.assertEqual(set(d1[d1.reloj_verdadero == "Ts:C(America/Santiago)|QFE:F(0)"].tipo), {"g"})
        self.assertEqual(set(d1[d1.territorio == "pascua_sala_y_gomez"].tipo), {"a", "b", "e"})
        self.assertFalse(d1[d1.territorio == "pascua_sala_y_gomez"].con_pixel.any())
        self.assertEqual(set(d1.escenario), set(S.ESCENARIOS))
        self.assertEqual(set(t[t.fuera_de_P].reloj_verdadero),
                         {"F(+1)", "F(-1)", "F(-2)", "F(-5)", "Cv(America/Santiago)"})
        self.assertEqual(set(t[t.bloque != "D1"].escenario), {"completo"})
        self.assertEqual(set(t[t.bloque == "D3"].perturbacion), {"isd_sintetico"})
        sesgo = t[t.perturbacion == "sesgo_termico_referencia"]
        self.assertEqual(set(sesgo.red.str[:5]), {"s-2.0", "s+1.0", "s+2.5"})
        self.assertTrue((t[t.perturbacion != "sesgo_termico_referencia"].red.str[:5] == "s+0.0").all())
        por_red = t.groupby("red").size()
        self.assertEqual(len(por_red), 20 + 3 * 10)
        self.assertEqual(int(por_red["s+0.0_r01"]), 237 + 18 * 12 + 6)
        self.assertEqual(int(por_red["s+0.0_r20"]), 237)
        self.assertEqual(int(por_red["s+2.5_r10"]), 12)
        self.assertTrue((t.red.str[-2:].astype(int) == t.replica).all())
        lat = t[t.perturbacion == "latitud"]
        self.assertEqual(sorted(lat.lat.unique()), [-53.0, -45.6, -39.8, -18.5])
        self.assertTrue((lat.lat == lat.valor_perturbacion).all())
        self.assertEqual(set(t[t.perturbacion == "territorio_incierto"].territorio), {"incierto"})
        self.assertEqual(set(t[t.perturbacion == "juan_fernandez"].territorio), {"juan_fernandez_desventuradas"})
        ref = bateria.CELDAS_REFERENCIA
        referencia = t[t.tipo.isin(ref["tipo"]) & t.escenario.isin(ref["escenario"]) & t.lat.isin(ref["lat"])
                       & t.perturbacion.isin(ref["perturbacion"])]
        self.assertTrue({"F(0)", "F(-3)", "F(-4)", "C(America/Santiago)"} <= set(referencia.reloj_verdadero))

    def test_d_reduccion_de_replicas(self):
        """> 48 h → D2 y D3 a 5 réplicas; el núcleo nunca (mismos códigos y semillas en D1)."""
        reducida = S.especificacion_bateria(S.REPLICAS_REDUCIDAS)
        self.assertEqual(reducida.groupby("bloque").size().to_dict(), {"D1": 4740, "D2": 1260, "D3": 30})
        pd.testing.assert_frame_equal(reducida[reducida.bloque == "D1"], self.tabla[self.tabla.bloque == "D1"])
        self.assertEqual(int(reducida.replica[reducida.bloque != "D1"].max()), 5)
        with self.assertRaises(ValueError):
            S.especificacion_bateria(7)

    def test_d_estaciones_desde_el_csv(self):
        """caso_de_fila da la misma estación desde la tabla y desde el CSV releído; perturbaciones y sitios."""
        primeras = self.tabla.groupby("celda", sort=False).head(1)
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "bateria_v1.csv"
            ruta.write_text(self.tabla.to_csv(index=False, lineterminator="\n"), encoding="utf-8")
            releida = pd.read_csv(ruta, dtype={"caso": str}, keep_default_na=True)
        releida = releida.set_index("caso").loc[primeras.caso].reset_index()
        for (_, a), (_, b) in zip(primeras.iterrows(), releida.iterrows()):
            ca, cb = S.caso_de_fila(a), S.caso_de_fila(b)
            self.assertEqual(S._clave(ca), S._clave(cb))
            self.assertEqual(S.texto_de_relojes(ca.relojes), a.reloj_verdadero)
            self.assertEqual(S.fuera_de_P(ca.relojes, S.territorio_sintetico(ca.lat, ca.lon, ca.cod_comuna)),
                             bool(a.fuera_de_P))
        fila = self.tabla[self.tabla.perturbacion == "s1_local_desfase_4h"].iloc[0]
        self.assertEqual(dict(S.caso_de_fila(fila).perturbaciones), {"s1_local_amplitud": fila.valor_perturbacion,
                                                                     "s1_local_desfase": 4.0})
        fila = self.tabla[self.tabla.perturbacion == "semantica"].iloc[0]
        self.assertAlmostEqual(S.caso_de_fila(fila).perturbaciones["semantica"], 1 / 6)
        g = S.caso_de_fila(self.tabla[self.tabla.tipo == "g"].iloc[0])
        self.assertEqual({r.variable for r in g.relojes}, {"Ts", "QFE"})
        self.assertEqual(g.anios, (2008, 2026))


if __name__ == "__main__":
    unittest.main()
