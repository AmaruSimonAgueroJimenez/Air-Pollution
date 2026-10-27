"""Pruebas de extraccion.py (manifiestos, artefactos, ERA5-Land y píxel).

Las que llevan «pNN» son el punto NN de §8 (grupos A, B y C). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s reloj_dmc/tests -t .
A ciegas: no abren datos DMC ni /Volumes. Los artefactos DMC se fabrican con el formato real
(``run_download`` del descargador vigente, con cliente y guarda falsos y ``defer_heavy_checks = True``, como
scripts_pipeline/tests/test_meteo_chile_horaria.py) y los NetCDF de ERA5-Land con la forma real (time × pixel,
float32, sin ``units`` en las variables), siempre en carpetas temporales. Si falta el código fijado (descargador,
adaptador) o los umbrales de C0, la prueba se omite con el motivo.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from reloj_dmc import extraccion, fijados, numerico, tablas, umbrales  # noqa: E402
from reloj_dmc.extraccion import (AUSENTE, CENTINELA, MEDIANA, RACHA, RANGO, VALIDO, EleccionPixel,  # noqa: E402
                                  ErrorExtraccion)
from reloj_dmc.tipos import (ESQUEMA_ESTACIONES, ESQUEMA_EXTRACTO_HORA, ESQUEMA_MES, Conjunto,  # noqa: E402
                             Territorio, validar_esquema)

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"
VIGENTE = fijados.VERSIONES_ADMITIDAS_C0[-1]        # 578fa26e…: la versión vigente del descargador
SIN_CODIGO = fijados.VERSIONES_SIN_CODIGO_C0[0]     # e61d9559…: sin código recuperado
OTRA = "ab" * 32                                    # una versión desconocida
CODIGO, CODIGO_2 = "330020", "330021"
ESTACIONES = {CODIGO: ("Quinta Normal, Santiago", "-33.445", "-70.682777", "521", "Mixta"),
              CODIGO_2: ("Pudahuel, Santiago", "-33.3925", "-70.79", "475", "Automática")}

_CACHE = {}


# --- Recursos fijados (se omiten si faltan) -----------------------------------
def _umbrales():
    if "U" not in _CACHE:
        try:
            _CACHE["U"] = umbrales.cargar_c0(_APH)
        except (OSError, umbrales.ErrorUmbrales) as e:
            raise unittest.SkipTest(f"sin los umbrales anclados en C0: {e}")
    return _CACHE["U"]


def _descargador():
    if "D" not in _CACHE:
        try:
            _CACHE["D"] = fijados.cargar_descargador(_AP, VIGENTE)
        except (OSError, ValueError, RuntimeError) as e:
            raise unittest.SkipTest(f"sin el descargador vigente {VIGENTE[:8]}…: {e}")
    return _CACHE["D"]


def _adaptador():
    if "A" not in _CACHE:
        try:
            _CACHE["A"] = fijados.cargar_adaptador(_AP)
        except (OSError, ValueError, RuntimeError) as e:
            raise unittest.SkipTest(f"sin el adaptador fijado: {e}")
    return _CACHE["A"]


# --- Fabricación con el formato real (run_download + cliente y guarda falsos) ---
def _ts(dia, hora):
    return f"{15 + 6 * math.sin(2 * math.pi * (hora - 9) / 24) + 0.3 * dia:.1f}"


def _qfe(dia, hora):
    return f"{950 + 1.5 * math.cos(2 * math.pi * hora / 12) + 0.2 * dia:.1f}"


def _celdas(desc, dia, hora, **valores):
    fila = dict.fromkeys(desc.RAW_COLUMNS, "")
    fila.update(day=f"{dia:02d}", hour=f"{hora:02d}:00")
    fila.update(valores)
    return [fila[c] for c in desc.RAW_COLUMNS]


def _fila_normal(desc, dia, hora, **extra):
    base = dict(wind_direction_instant="180", wind_speed_instant="005", Ts=_ts(dia, hora), Td="5.1",
                relative_humidity="56", QFE=_qfe(dia, hora), QFF="1013.0")
    base.update(extra)
    return _celdas(desc, dia, hora, **base)


def _filas_normales(desc, dias=3):
    return [_fila_normal(desc, d, h) for d in range(1, dias + 1) for h in range(24)]


def _informe(desc, codigo, anio, mes, filas):
    cabecera = "<tr>" + "".join(f"<th>{x}</th>" for x in desc.GROUP_COLUMNS) + "</tr>"
    cabecera += "<tr>" + "".join(f"<td>{x}</td>" for x in desc.LEAF_COLUMNS) + "</tr>"
    cuerpo = "".join("<tr>" + "".join(f'<td title="original">{x}</td>' for x in f) + "</tr>" for f in filas)
    return (f'<div id="cabezera">Hoja Mensual de Datos Estación ({codigo}) {desc.MONTH_NAMES[mes - 1]} de {anio}'
            f"</div><table>{cabecera}{cuerpo}</table>")


def _catalogo_html(estaciones):
    cab = ["Código Nacional", "Nombre", "Latitud", "Longitud", "Altitud (Mts)", "Tipo"]
    filas = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in (codigo, *datos)) + "</tr>"
                    for codigo, datos in sorted(estaciones.items()))
    return "<table><tr>" + "".join(f"<th>{x}</th>" for x in cab) + "</tr>" + filas + "</table>"


class _Guarda:
    defer_heavy_checks = True

    def check(self, *args, **kwargs):
        pass

    def ensure_directory(self, ruta):
        ruta.mkdir(parents=True, exist_ok=True)

    def write_atomic_bytes(self, ruta, datos):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)


class _Cliente:
    def __init__(self, desc, estaciones, filas_de):
        self.desc, self.estaciones, self.filas_de = desc, estaciones, filas_de

    def catalog(self):
        return self.desc.parse_catalog(_catalogo_html(self.estaciones))

    def inventory(self, code):
        return [{"element_id": e, "first_year": 2000, "last_year": 2026} for e in (26, 28, 57, 64, 65, 66, 70)]

    def report(self, code, year, month, start, end):
        filas = self.filas_de(code, year, month) or []
        texto = _informe(self.desc, code, year, month, filas)
        return self.desc.parse_report(texto, code, year, month, start, end), "https://example.invalid/offline"


def _fabricar(raiz, filas_de, desde, hasta, estaciones=None):
    desc = _descargador()
    estaciones = estaciones or {CODIGO: ESTACIONES[CODIGO]}
    return desc.run_download(str(raiz), desde, hasta, _Guarda(), client=_Cliente(desc, estaciones, filas_de))


def _editar_manifiesto(raiz, codigo, mes, cambio):
    ruta = Path(raiz) / "estaciones" / codigo / f"{mes}.manifest.json"
    m = json.loads(ruta.read_text(encoding="utf-8"))
    cambio(m)
    ruta.write_text(json.dumps(m, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


class _Avance:
    """avance.jsonl en memoria: unidad → huella de entrada registrada."""

    def __init__(self):
        self.reg, self.registrados, self.pasos = {}, [], []

    def hecho(self, unidad, huella):
        return self.reg.get(unidad) == huella

    def registrar(self, unidad, entrada, salida):
        self.reg[unidad] = entrada
        self.registrados.append(unidad)

    def avance(self, hechos, total):
        self.pasos.append((hechos, total))

    def kw(self):
        return dict(hecho=self.hecho, registrar=self.registrar, avance=self.avance)


class _AdaptadorContado:
    """Envuelve ``leer_artefacto`` para contar lecturas o simular un corte en una estación."""

    def __init__(self, adaptador, falla_en=None):
        self.adaptador, self.falla_en, self.llamadas = adaptador, falla_en, []

    def leer_artefacto(self, ruta):
        ruta = Path(ruta)
        self.llamadas.append(f"{ruta.parent.name}/{ruta.name}")
        if ruta.parent.name == self.falla_en:
            raise RuntimeError("corte simulado")
        return self.adaptador.leer_artefacto(ruta)


class _Temporal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reloj_dmc_extraccion_")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def carpeta(self, nombre):
        ruta = self.tmp / nombre
        ruta.mkdir(parents=True, exist_ok=True)
        return ruta


def _extraer(raiz, destino, adaptador=None, versiones=None, avance=None):
    avance = avance or _Avance()
    return extraccion.extraer_dmc(raiz, adaptador or _adaptador(), versiones or {VIGENTE}, _umbrales(), destino,
                                  **avance.kw())


def _payload(desc, filas, anio=2020, mes=1):
    """Payload con filas reales de ``parse_report`` (sin pasar por disco)."""
    rows, _ = desc.parse_report(_informe(desc, CODIGO, anio, mes, filas), CODIGO, anio, mes)
    return {"station": {"code": CODIGO, "source_metadata": {}}, "rows": rows}


def _en(df, dia, hora, anio=2020, mes=1):
    return df.loc[df["L"] == pd.Timestamp(anio, mes, dia, hora)].iloc[0]


# --- Píxeles y ERA5-Land sintéticos -------------------------------------------
def _pid(lat, lon):
    """pixel_id = lat_index_global·3600 + lon_index_global (atributo de los mensuales reales)."""
    return int(round((90 - lat) * 10)) * 3600 + int(round((lon % 360) * 10))


def _catalogo_pixeles(centros, cod_comuna=13101, ids=None):
    filas = []
    for k, (lat, lon) in enumerate(centros):
        filas.append({"pixel_id": ids[k] if ids else _pid(lat, lon), "latitude": lat, "longitude": lon,
                      "cell_west": lon - 0.05, "cell_south": lat - 0.05, "cell_east": lon + 0.05,
                      "cell_north": lat + 0.05, "cod_comuna": cod_comuna, "territorio": "continental"})
    return pd.DataFrame(filas).sort_values("pixel_id").reset_index(drop=True)


LATS, LONS = (-33.3, -33.4, -33.5), (-70.7, -70.6, -70.5)
GRILLA = [(la, lo) for la in LATS for lo in LONS]
CENTRO, OESTE, NORESTE = _pid(-33.4, -70.6), _pid(-33.4, -70.7), _pid(-33.3, -70.5)


def _horas_del_mes(yyyymm):
    mes = np.datetime64(f"{yyyymm[:4]}-{yyyymm[4:]}", "M")
    return np.arange(mes.astype("datetime64[h]"), (mes + 1).astype("datetime64[h]"), np.timedelta64(1, "h"))


def _segundos(t):
    return (t.astype("datetime64[s]") - np.datetime64("1970-01-01T00:00:00", "s")).astype(np.int64)


def _campos_sinteticos(t, n_pix):
    """t2m (K), sp (Pa), u10 y v10 exactos en float32, función de la hora global y de la columna."""
    h = ((t - extraccion.T0_ERA5) // np.timedelta64(1, "h")).astype(np.int64)[:, None]
    j = np.arange(n_pix)[None, :]
    return {"t2m": (280.0 + j + (h % 24) * 0.5).astype(np.float32),
            "sp": (95000.0 + 10 * j + (h % 48)).astype(np.float32),
            "u10": np.broadcast_to(1.0 + j, (len(t), n_pix)).astype(np.float32),
            "v10": np.broadcast_to(-1.0 - j, (len(t), n_pix)).astype(np.float32)}


def _escribir_nc(ruta, segundos, pixel_ids, campos, unidades="seconds since 1970-01-01 00:00:00 UTC"):
    netCDF4 = extraccion._netcdf4()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ds = netCDF4.Dataset(ruta, "w", format="NETCDF4")
    try:
        ds.createDimension("time", len(segundos))
        ds.createDimension("pixel", len(pixel_ids))
        tv = ds.createVariable("time", "i8", ("time",))
        if unidades is not None:
            tv.units = unidades
            tv.calendar = "proleptic_gregorian"
        tv[:] = np.asarray(segundos, dtype=np.int64)
        ds.createVariable("pixel_id", "i8", ("pixel",))[:] = np.asarray(pixel_ids, dtype=np.int64)
        for nombre in ("t2m", "sp", "u10", "v10"):
            v = ds.createVariable(nombre, "f4", ("time", "pixel"), zlib=True, fill_value=np.float32(np.nan))
            v[:] = campos[nombre]
    finally:
        ds.close()


def _mes_nc(raiz, yyyymm, pixel_ids, ajustar=None):
    t = _horas_del_mes(yyyymm)
    campos = _campos_sinteticos(t, len(pixel_ids))
    campos = {k: np.array(v) for k, v in campos.items()}
    segundos = _segundos(t)
    if ajustar is not None:
        segundos, campos = ajustar(segundos, campos)
    ruta = extraccion.ruta_mes_era5(raiz, yyyymm)
    _escribir_nc(ruta, segundos, pixel_ids, campos)
    return ruta


# ===========================================================================
class PruebasDMC(_Temporal):
    def test_admision_cuatro_condiciones(self):
        """verified_operational, artifact_name, row_count ≥ 1, script_sha256 admitido."""
        base = {"verification_status": "verified_operational", "artifact_name": "2020-01." + "c" * 64 + ".json.gz",
                "row_count": 72, "script_sha256": VIGENTE}
        admitir = extraccion.admitir_mes
        self.assertEqual(admitir(base, {VIGENTE}), (True, None))
        casos = [
            ({"verification_status": "pending"}, "pending"),
            ({"verification_status": None}, "pending"),
            ({"verification_status": "failed"}, "failed"),
            ({"verification_status": "pending", "verification_candidate": {"artifact_name": "x.json.gz"}}, "candidato"),
            ({"verification_status": "failed", "verification_candidate": {}}, "candidato"),
            ({"script_sha256": OTRA}, "version_no_admitida"),
            ({"script_sha256": SIN_CODIGO}, "sin_codigo"),
            ({"script_sha256": None}, "sin_codigo"),
            ({"artifact_name": ""}, "artifact_name"),
            ({"artifact_name": "../2020-01.json.gz"}, "artifact_name"),
            ({"artifact_name": "otra/2020-01.json.gz"}, "artifact_name"),
            ({"artifact_name": "2020-01.json"}, "artifact_name"),
            ({"row_count": 0}, "row_count"),
            ({"row_count": "72"}, "row_count"),
            ({"row_count": True}, "row_count"),
            ({"row_count": None}, "row_count"),
        ]
        for cambio, motivo in casos:
            with self.subTest(cambio=cambio):
                self.assertEqual(admitir({**base, **cambio}, {VIGENTE}), (False, motivo))
        sin_estado = {k: v for k, v in base.items() if k != "verification_status"}
        self.assertEqual(admitir(sin_estado, {VIGENTE}), (False, "pending"))
        self.assertEqual(admitir(None, {VIGENTE}), (False, "failed"))
        # Lectura 1: un verificado que aún lleva candidato entra con su artefacto de nivel superior.
        self.assertEqual(admitir({**base, "verification_candidate": {}}, {VIGENTE}), (True, None))
        # El conjunto vigente puede venir de fijados.versiones_admitidas (dict por versión).
        mapa = {VIGENTE: {"admitida": True, "motivo": None}, OTRA: {"admitida": False, "motivo": "huella_distinta"},
                "cd" * 32: {"admitida": False, "motivo": "sin_codigo"}}
        self.assertEqual(admitir(base, mapa), (True, None))
        self.assertEqual(admitir({**base, "script_sha256": OTRA}, mapa), (False, "version_no_admitida"))
        self.assertEqual(admitir({**base, "script_sha256": "cd" * 32}, mapa), (False, "sin_codigo"))
        self.assertEqual(extraccion.conjunto_admitido(mapa), frozenset({VIGENTE}))
        with self.assertRaises(ValueError):
            extraccion.conjunto_admitido({"no-es-sha"})

    def test_meses_excluidos_con_su_motivo(self):
        """pending, failed, candidato no promovido, versión no admitida."""
        desc = _descargador()
        raiz, destino = self.carpeta("DMC"), self.carpeta("corrida")
        _fabricar(raiz, lambda c, a, m: None if m == 3 else _filas_normales(desc, dias=1), "2020-01-01", "2020-06-30")
        _editar_manifiesto(raiz, CODIGO, "2020-02", lambda m: m.update(verification_status="pending"))
        _editar_manifiesto(raiz, CODIGO, "2020-04", lambda m: m.update(
            verification_status="failed", verification_candidate={"artifact_name": "2020-04.x.json.gz"}))
        _editar_manifiesto(raiz, CODIGO, "2020-05", lambda m: m.update(script_sha256=OTRA))
        _editar_manifiesto(raiz, CODIGO, "2020-06", lambda m: m.update(script_sha256=SIN_CODIGO))
        resumen = _extraer(raiz, destino)
        meses = extraccion.leer_meses(destino)
        validar_esquema(meses, ESQUEMA_MES, nombre="meses")
        motivos = {int(f.mes): (bool(f.entra), extraccion._sin_na(f.motivo_exclusion)) for f in meses.itertuples()}
        self.assertEqual(motivos, {1: (True, None), 2: (False, "pending"), 3: (False, "failed"),
                                   4: (False, "candidato"), 5: (False, "version_no_admitida"),
                                   6: (False, "sin_codigo")})
        self.assertEqual(dict(resumen.meses_excluidos), {"candidato": 1, "failed": 1, "pending": 1,
                                                         "sin_codigo": 1, "version_no_admitida": 1})
        self.assertEqual((resumen.estaciones, resumen.meses_evaluados, resumen.filas), (1, 1, 24))
        extracto = extraccion.leer_extracto(destino, CODIGO)
        self.assertEqual(set(extracto["mes"]), {1})
        self.assertEqual(extracto["id_artefacto"].unique().tolist(), [0])
        artefactos = extraccion.leer_artefactos_evaluados(destino)
        self.assertEqual([(a["id_artefacto"], a["mes"]) for a in artefactos], [(0, 1)])
        self.assertTrue(meses.loc[~meses["entra"], "id_artefacto"].isna().all())

    def test_formato_real_por_run_download(self):
        """Artefactos fabricados con sintetico.fabricar_descarga se leen con leer_artefacto.

        Mientras sintetico.fabricar_descarga no esté, se fabrican aquí con el mismo camino: run_download del
        descargador vigente, cliente y guarda falsos y relectura final diferida.
        """
        desc, adaptador = _descargador(), _adaptador()
        raiz, destino = self.carpeta("DMC"), self.carpeta("corrida")
        resumen_descarga = _fabricar(raiz, lambda c, a, m: _filas_normales(desc), "2020-01-01", "2020-02-29")
        self.assertEqual(resumen_descarga["final_verification"]["artifacts_verified"], 2)
        avance = _Avance()
        resumen = _extraer(raiz, destino, avance=avance)
        rutas = extraccion.listar_manifiestos(raiz)
        self.assertEqual([r.name for r in rutas], ["2020-01.manifest.json", "2020-02.manifest.json"])
        self.assertEqual(resumen.huella_manifiestos, extraccion.huella_agregada_manifiestos(
            rutas, lambda r: extraccion.alias_dmc(r, raiz)))
        self.assertEqual((resumen.estaciones, resumen.meses_evaluados, resumen.filas), (1, 2, 144))
        self.assertEqual(dict(resumen.meses_excluidos), {})
        self.assertEqual(avance.registrados, [f"dmc/{CODIGO}"])
        self.assertEqual(avance.pasos, [(1, 1)])

        extracto = extraccion.leer_extracto(destino, CODIGO)
        validar_esquema(extracto, ESQUEMA_EXTRACTO_HORA, nombre="extracto")
        self.assertTrue(extracto["L"].is_monotonic_increasing)
        self.assertEqual(len(extracto), 144)
        self.assertTrue(extracto["medida"].all())
        self.assertTrue((extracto["motivo_ts"] == VALIDO).all() and (extracto["motivo_qfe"] == VALIDO).all())
        fila = _en(extracto, 2, 15, mes=2)
        self.assertEqual((fila["ts"], fila["qfe"], fila["td"], fila["hr"]), (float(_ts(2, 15)), float(_qfe(2, 15)),
                                                                            5.1, 56.0))
        self.assertEqual((fila["ff_kt"], fila["dd_grados"], fila["id_artefacto"]), (5.0, 180.0, 1))
        self.assertTrue(fila["viento_valido"] and fila["qff_numerica"])
        self.assertFalse(fila["rr"] or fila["tx"] or fila["tn"] or fila["observador"])
        # La huella del extracto es la de los 21 textos crudos del artefacto, leído con leer_artefacto.
        payload, meta = adaptador.leer_artefacto(rutas[1])
        crudas = {r["timestamp_source"]: r["raw_cells"] for r in payload["rows"]}
        self.assertEqual(fila["huella"], extraccion.huella_fila(crudas["2020-02-02T15:00:00"]))

        meses = extraccion.leer_meses(destino)
        enero = meses.iloc[0]
        self.assertEqual((enero["codigo"], int(enero["anio"]), int(enero["mes"])), (CODIGO, 2020, 1))
        self.assertEqual(enero["manifiesto"], f"DMC/estaciones/{CODIGO}/2020-01.manifest.json")
        self.assertEqual(enero["manifiesto_sha256"], hashlib.sha256(rutas[0].read_bytes()).hexdigest())
        self.assertEqual(enero["script_sha256"], VIGENTE)
        self.assertEqual((int(enero["row_count"]), int(enero["n_available_hours"]), int(enero["expected_hour_slots"]),
                          int(enero["source_empty_slots"]), int(enero["duplicate_display_rows_removed"])),
                         (72, 72, 744, 0, 0))
        self.assertEqual((enero["requested_start"], enero["requested_end"]), ("2020-01-01", "2020-01-31"))
        self.assertEqual((int(enero["p_ts"]), int(enero["p_qfe"])), (1, 1))
        self.assertEqual((enero["lat_txt"], enero["lon_txt"], enero["alt_txt"]), ("-33.445", "-70.682777", "521"))
        self.assertEqual(enero["campos_faltantes"], [])
        artefactos = extraccion.leer_artefactos_evaluados(destino)
        self.assertEqual([a["id_artefacto"] for a in artefactos], [0, 1])
        self.assertEqual(artefactos[1]["artefacto_sha256"], meta["content_sha256"])
        self.assertEqual(artefactos[1]["artefacto"], f"DMC/estaciones/{CODIGO}/{meta['artifact_name']}")
        # Lectura de un subconjunto de columnas, con sus tipos.
        sub = extraccion.leer_extracto(destino, CODIGO, ["L", "ts"])
        self.assertEqual(list(sub.columns), ["L", "ts"])
        with self.assertRaises(KeyError):
            extraccion.leer_extracto(destino, CODIGO, ["no_existe"])
        with self.assertRaises(ValueError):
            extraccion.leer_extracto(destino, "../x")

    def test_control_propio_ts_qfe_viento(self):
        """Centinelas −40,0 y 500,0, rangos, mediana del mes y rachas de 12/24 h."""
        desc, U = _descargador(), _umbrales()
        especiales = {
            (1, 5): dict(Ts="-40.0"), (1, 6): dict(Ts="55.0"), (1, 7): dict(Ts="-30.0"), (1, 8): dict(Ts="-8.0"),
            (1, 9): dict(wind_direction_instant="400"), (1, 10): dict(wind_speed_instant="-1"),
            (1, 11): dict(wind_direction_instant="000", wind_speed_instant="000"),
            (1, 12): dict(wind_direction_instant=""), (1, 13): dict(Ts=""), (1, 14): dict(Ts="s/p"),
            (2, 3): dict(QFE="500.0"), (2, 4): dict(QFE="1200.0"), (2, 5): dict(QFE="900.0"), (2, 6): dict(QFE="915.0"),
            (5, 6): dict(Ts=""),
        }
        for h in range(12):
            especiales[(3, h)] = dict(Ts="12.3")          # 12 h idénticas: racha
        for h in range(11):
            especiales[(4, h)] = dict(Ts="11.1")          # 11 h: no llega
        for h in range(24):
            especiales[(4, h)] = {**especiales.get((4, h), {}), "QFE": "949.0"}   # 24 h idénticas: racha
        for h in range(23):
            especiales[(5, h)] = {**especiales.get((5, h), {}), "QFE": "948.0"}   # 23 h: no llega
        for h in (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12):
            especiales[(5, h)] = {**especiales.get((5, h), {}), "Ts": "10.0"}     # dos tramos de 6 h cortados por un hueco
        filas = [_fila_normal(desc, d, h, **especiales.get((d, h), {})) for d in range(1, 6) for h in range(24)]
        crudo = extraccion.filas_a_extracto(_payload(desc, filas), 7, U)
        # filas_a_extracto ya aplica centinela y rango, no mediana ni rachas.
        self.assertEqual(_en(crudo, 1, 5)["motivo_ts"], CENTINELA)
        self.assertEqual(_en(crudo, 1, 6)["motivo_ts"], RANGO)
        self.assertEqual(_en(crudo, 1, 7)["motivo_ts"], VALIDO)
        self.assertEqual(_en(crudo, 3, 0)["motivo_ts"], VALIDO)
        ext = extraccion.control_propio(crudo, U)
        esperado_ts = {(1, 5): CENTINELA, (1, 6): RANGO, (1, 7): MEDIANA, (1, 8): VALIDO, (1, 13): AUSENTE,
                       (1, 14): AUSENTE, (3, 0): RACHA, (3, 11): RACHA, (3, 12): VALIDO, (4, 0): VALIDO,
                       (4, 10): VALIDO, (5, 0): VALIDO, (5, 6): AUSENTE, (5, 12): VALIDO}
        for (d, h), codigo in esperado_ts.items():
            with self.subTest(variable="Ts", dia=d, hora=h):
                fila = _en(ext, d, h)
                self.assertEqual(fila["motivo_ts"], codigo)
                self.assertEqual(math.isnan(fila["ts"]), codigo != VALIDO)
        esperado_qfe = {(2, 3): CENTINELA, (2, 4): RANGO, (2, 5): MEDIANA, (2, 6): VALIDO, (4, 0): RACHA,
                        (4, 23): RACHA, (5, 0): VALIDO, (5, 22): VALIDO, (3, 23): VALIDO}
        for (d, h), codigo in esperado_qfe.items():
            with self.subTest(variable="QFE", dia=d, hora=h):
                self.assertEqual(_en(ext, d, h)["motivo_qfe"], codigo)
        self.assertEqual(int((ext["motivo_ts"] == RACHA).sum()), 12)
        self.assertEqual(int((ext["motivo_qfe"] == RACHA).sum()), 24)
        self.assertEqual(_en(ext, 1, 8)["ts"], -8.0)
        # Viento: dominio 0-360 y rapidez ≥ 0; si no, se descarta entero.
        for (d, h), valido in {(1, 9): False, (1, 10): False, (1, 11): True, (1, 12): False, (1, 15): True}.items():
            with self.subTest(viento=(d, h)):
                fila = _en(ext, d, h)
                self.assertEqual(bool(fila["viento_valido"]), valido)
                self.assertEqual(math.isnan(fila["ff_kt"]) or math.isnan(fila["dd_grados"]), not valido)
        self.assertEqual((_en(ext, 1, 11)["ff_kt"], _en(ext, 1, 11)["dd_grados"]), (0.0, 0.0))
        self.assertEqual(set(ext["id_artefacto"]), {7})
        # Una sola aplicación: repetirla recalcularía la mediana sin los descartados.
        with self.assertRaises(ValueError):
            extraccion.control_propio(ext, U)
        # Con paso de 6 h, dos Ts iguales seguidas ya cubren 12 h (lectura 3).
        seis = [_fila_normal(desc, d, h, **({"Ts": "14.0"} if (d, h) in {(1, 6), (1, 12)} else {}))
                for d in range(1, 4) for h in (0, 6, 12, 18)]
        ext6 = extraccion.control_propio(extraccion.filas_a_extracto(_payload(desc, seis), 0, U), U)
        self.assertEqual([_en(ext6, 1, h)["motivo_ts"] for h in (0, 6, 12, 18)], [VALIDO, RACHA, RACHA, VALIDO])

    def test_fila_medida_y_marcas(self):
        """H(L), RR con «s/p», TX/TN, observador por un dígito en CL/CM/CH."""
        desc, U = _descargador(), _umbrales()
        filas = [
            _celdas(desc, 1, 0, RR06="s/p"),
            _celdas(desc, 1, 1, RR06="0.2"),
            _celdas(desc, 1, 2, Ts="-40.0"),
            _celdas(desc, 1, 3, QFE="500.0"),
            _celdas(desc, 1, 4, QFF="1013.2"),
            _celdas(desc, 1, 5, Ts="70.0"),
            _celdas(desc, 1, 6, Td="5.0"),
            _fila_normal(desc, 1, 7, TMax="25.3", CL="7", CH="/"),
            _fila_normal(desc, 1, 8, TMin="3.1", CL="12"),
            _fila_normal(desc, 1, 9, CH="4"),
            _celdas(desc, 1, 10, wind_direction_instant="090", wind_speed_instant="010"),
            _celdas(desc, 1, 11, Ts="s/p"),
            _fila_normal(desc, 1, 12, CM="x"),
        ]
        ext = extraccion.filas_a_extracto(_payload(desc, filas), 0, U)
        validar_esquema(ext, ESQUEMA_EXTRACTO_HORA, nombre="extracto")
        esperado = {  # hora: (medida, rr, tx, tn, observador, qff_numerica)
            0: (False, True, False, False, False, False), 1: (False, True, False, False, False, False),
            2: (False, False, False, False, False, False), 3: (False, False, False, False, False, False),
            4: (True, False, False, False, False, True), 5: (True, False, False, False, False, False),
            6: (True, False, False, False, False, False), 7: (True, False, True, False, True, True),
            8: (True, False, False, True, False, True), 9: (True, False, False, False, True, True),
            10: (True, False, False, False, False, False), 11: (False, False, False, False, False, False),
            12: (True, False, False, False, False, True)}
        for hora, valores in esperado.items():
            with self.subTest(hora=hora):
                fila = _en(ext, 1, hora)
                self.assertEqual(tuple(bool(fila[c]) for c in ("medida", "rr", "tx", "tn", "observador",
                                                                "qff_numerica")), valores)
        self.assertEqual(_en(ext, 1, 5)["motivo_ts"], RANGO)          # cuenta para H(L), pero no es un Ts válido
        self.assertEqual(_en(ext, 1, 2)["motivo_ts"], CENTINELA)
        self.assertEqual(_en(ext, 1, 3)["motivo_qfe"], CENTINELA)
        self.assertEqual(_en(ext, 1, 11)["motivo_ts"], AUSENTE)
        self.assertTrue(_en(ext, 1, 10)["viento_valido"])

    def test_huella_de_fila_21_textos(self):
        """Sin día ni hora; serialización fijada."""
        desc = _descargador()
        self.assertEqual(tuple(c for c in desc.RAW_COLUMNS if c not in ("day", "hour")),
                         extraccion.COLUMNAS_CRUDAS_SIN_DIA_NI_HORA)
        textos = {c: f"t{k}" for k, c in enumerate(desc.RAW_COLUMNS)}
        textos["WW"] = "ñandú °"
        crudas = {c: {"text": t, "attributes": {"title": "x"}} for c, t in textos.items()}
        lista = [textos[c] for c in extraccion.COLUMNAS_CRUDAS_SIN_DIA_NI_HORA]
        esperado = hashlib.sha256(json.dumps(lista, ensure_ascii=False, separators=(",", ":"))
                                  .encode("utf-8")).hexdigest()
        self.assertEqual(extraccion.huella_fila(crudas), esperado)
        self.assertNotEqual(esperado, hashlib.sha256(json.dumps(lista).encode()).hexdigest())
        otra = {**crudas, "day": {"text": "31", "attributes": {}}, "hour": {"text": "23:00", "attributes": {}}}
        self.assertEqual(extraccion.huella_fila(otra), esperado)           # sin día ni hora
        cambiada = {**crudas, "RR06": {"text": "s/p", "attributes": {}}}
        self.assertNotEqual(extraccion.huella_fila(cambiada), esperado)
        # En el extracto, la huella de cada fila es la de sus textos crudos reales.
        filas = _filas_normales(desc, dias=1)
        payload = _payload(desc, filas)
        ext = extraccion.filas_a_extracto(payload, 0, _umbrales())
        self.assertEqual(ext["huella"].tolist(), [extraccion.huella_fila(r["raw_cells"]) for r in payload["rows"]])

    def test_paso_nativo_y_empate(self):
        """Moda de diferencias; empate → la menor."""
        t0 = np.datetime64("2020-01-01T00", "h")
        def p(horas):
            return extraccion.paso_nativo(np.array([t0 + np.timedelta64(h, "h") for h in horas]))
        self.assertEqual(p(range(24)), 1)
        self.assertEqual(p([0, 3, 6, 9, 10, 11]), 3)           # 3, 3, 3, 1, 1
        self.assertEqual(p([0, 1, 2, 4, 6]), 1)                # empate 1-2 → la menor
        self.assertEqual(p([0, 6, 12, 18, 24]), 6)
        self.assertEqual(p([18, 0, 12, 6]), 6)                 # se ordenan
        self.assertEqual(p([0, 0, 6, 12]), 6)                  # sin repetir
        self.assertIsNone(p([5]))
        self.assertIsNone(p([]))
        with self.assertRaises(ValueError):
            extraccion.paso_nativo(np.array(["2020-01-01T00:00", "2020-01-01T00:30"], dtype="datetime64[m]"))
        # Un paso mayor de 127 h (aquí 168 h) cabe en ESQUEMA_MES (Int16) y queda registrado.
        semanal = p([0, 168, 336, 504])
        self.assertEqual(semanal, 168)
        self.assertEqual(extraccion._paso_para_meses(semanal), 168)
        col = pd.array([extraccion._paso_para_meses(semanal), None], dtype=ESQUEMA_MES["p_ts"])
        self.assertEqual((int(col[0]), col[1] is pd.NA), (168, True))

    def test_campo_faltante_no_excluye_el_mes(self):
        """Sin source_empty_slots: E1c sin información, el mes entra."""
        desc = _descargador()
        raiz, destino = self.carpeta("DMC"), self.carpeta("corrida")
        _fabricar(raiz, lambda c, a, m: _filas_normales(desc, dias=1), "2020-01-01", "2020-01-31")
        _editar_manifiesto(raiz, CODIGO, "2020-01", lambda m: [m.pop("source_empty_slots"), m.pop("available_hours")])
        resumen = _extraer(raiz, destino)
        self.assertEqual(resumen.meses_evaluados, 1)
        fila = extraccion.leer_meses(destino).iloc[0]
        self.assertTrue(fila["entra"])
        self.assertEqual(fila["campos_faltantes"], ["available_hours", "source_empty_slots"])
        self.assertTrue(pd.isna(fila["source_empty_slots"]) and pd.isna(fila["n_available_hours"]))
        self.assertEqual(int(fila["row_count"]), 24)
        self.assertEqual(len(extraccion.leer_extracto(destino, CODIGO)), 24)

    def test_p05_coordenadas_inconsistentes_dan_la_marca(self):
        """Artefacto y catálogo difieren > 0,0005° → marca de §3.1."""
        U = _umbrales()
        f = extraccion.coordenadas_inconsistentes
        cat = ("-33.445", "-70.682777", "521")
        self.assertFalse(f([cat, cat], cat, U))
        self.assertFalse(f([("-33,445", "-70.682777", "521")], cat, U))        # otro texto, mismo valor
        self.assertFalse(f([("-33.4455", "-70.682777", "521")], cat, U))       # 0,0005° justo: no basta
        self.assertTrue(f([("-33.4456", "-70.682777", "521")], cat, U))
        self.assertTrue(f([cat, ("-33.445", "-70.6835", "521")], cat, U))      # basta un artefacto
        self.assertFalse(f([("-33.445", "-70.682777", "521.5")], cat, U))      # 0,5 m justo
        self.assertTrue(f([("-33.445", "-70.682777", "521.6")], cat, U))
        self.assertTrue(f([("s/d", "-70.682777", "521")], cat, U))             # distinto y no interpretable
        self.assertTrue(f([(None, "-70.682777", "521")], cat, U))
        self.assertFalse(f([], cat, U))
        # De punta a punta: textos de los artefactos evaluados frente al catálogo vigente en C2.
        desc = _descargador()
        raiz, destino = self.carpeta("DMC"), self.carpeta("corrida")
        _fabricar(raiz, lambda c, a, m: _filas_normales(desc, dias=1), "2020-01-01", "2020-02-29")
        _extraer(raiz, destino)
        meses = extraccion.leer_meses(destino)
        catalogo, sha = extraccion.leer_catalogo_dmc(raiz / extraccion.NOMBRE_CATALOGO_DMC)
        self.assertEqual(sha, hashlib.sha256((raiz / extraccion.NOMBRE_CATALOGO_DMC).read_bytes()).hexdigest())
        self.assertEqual(list(catalogo.columns), list(extraccion.COLUMNAS_CATALOGO_DMC))
        fila = catalogo.iloc[0]
        self.assertEqual((fila["codigo"], fila["nombre"], fila["lat_txt"], fila["tipo"]),
                         (CODIGO, "Quinta Normal, Santiago", "-33.445", "Mixta"))
        self.assertTrue(pd.isna(fila["omm"]))
        pixeles = _catalogo_pixeles([(-33.4, -70.7)])
        infos = extraccion.info_estaciones(catalogo, pixeles, {}, {}, {}, {13: "centro"}, U)
        self.assertFalse(infos[CODIGO].coordenadas_inconsistentes)
        marcadas = extraccion.marcar_coordenadas_inconsistentes(infos, catalogo, meses, U)
        self.assertFalse(marcadas[CODIGO].coordenadas_inconsistentes)
        for lat, marca in (("-33,445", False), ("-33.4453", False), ("-33.4460", True)):
            with self.subTest(lat=lat):
                otro = catalogo.copy()
                otro.loc[0, "lat_txt"] = lat
                self.assertEqual(extraccion.marcar_coordenadas_inconsistentes(infos, otro, meses, U)[CODIGO]
                                 .coordenadas_inconsistentes, marca)
        # Sin artefactos evaluados no hay textos que comparar: no hay marca.
        sin_eval = meses.assign(entra=False)
        otro = catalogo.copy()
        otro.loc[0, "lat_txt"] = "-30.0"
        self.assertFalse(extraccion.marcar_coordenadas_inconsistentes(infos, otro, sin_eval, U)[CODIGO]
                         .coordenadas_inconsistentes)

    def test_huella_agregada_de_manifiestos(self):
        """«sha256␣␣ruta» ordenado por ruta."""
        raiz = self.carpeta("DMC")
        contenidos = {"330021/2020-01": b'{"a": 1}', "330020/2020-02": b'{"b": 2}', "330020/2020-01": b'{"c": 3}'}
        for nombre, datos in contenidos.items():
            ruta = raiz / "estaciones" / f"{nombre}.manifest.json"
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(datos)
        (raiz / "estaciones" / "330020" / "._2020-01.manifest.json").write_bytes(b"AppleDouble")
        (raiz / "estaciones" / "330020" / "2020-01.abc.json.gz").write_bytes(b"artefacto")
        (raiz / "estaciones" / ".DS_Store").write_bytes(b"x")
        rutas = extraccion.listar_manifiestos(raiz)
        self.assertEqual([f"{r.parent.name}/{r.name}" for r in rutas],
                         ["330020/2020-01.manifest.json", "330020/2020-02.manifest.json",
                          "330021/2020-01.manifest.json"])
        def alias(r):
            return extraccion.alias_dmc(r, raiz)
        texto = "".join(f"{hashlib.sha256(contenidos[n]).hexdigest()}  DMC/estaciones/{n}.manifest.json\n"
                        for n in sorted(contenidos))
        esperado = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        self.assertEqual(extraccion.huella_agregada_manifiestos(rutas, alias), esperado)
        self.assertEqual(extraccion.huella_agregada_manifiestos(list(reversed(rutas)), alias), esperado)
        self.assertEqual(alias(rutas[0]), "DMC/estaciones/330020/2020-01.manifest.json")
        # Un nombre fuera del patrón o un enlace simbólico detienen la lectura.
        mal = raiz / "estaciones" / "330020" / "2020-1.manifest.json"
        mal.write_bytes(b"{}")
        with self.assertRaises(ErrorExtraccion):
            extraccion.listar_manifiestos(raiz)
        mal.unlink()
        (raiz / "estaciones" / "330020" / "2020-03.manifest.json").symlink_to(rutas[0])
        with self.assertRaises(ErrorExtraccion):
            extraccion.listar_manifiestos(raiz)


# ===========================================================================
class PruebasPixelYERA5(_Temporal):
    def test_p05_celda_sin_dato_lleva_al_vecino_y_es_costera(self):
        """Centro válido a ≤ 15 km; empate por menor pixel_id."""
        U = _umbrales()
        cat = _catalogo_pixeles(GRILLA)
        todos = set(cat["pixel_id"])
        lat, lon = -33.41, -70.61                                # dentro de la celda central
        self.assertEqual(tablas.celda_que_contiene(lat, lon, cat), CENTRO)
        propia = extraccion.elegir_pixel(lat, lon, cat, todos, U)
        self.assertEqual((propia.pixel_id, propia.costera), (CENTRO, False))
        self.assertAlmostEqual(propia.distancia_km, float(numerico.distancia_km(lat, lon, np.array([-33.4]),
                                                                                np.array([-70.6]))[0]))
        vecino = extraccion.elegir_pixel(lat, lon, cat, todos - {CENTRO}, U)
        self.assertEqual((vecino.pixel_id, vecino.costera), (OESTE, True))
        self.assertLess(vecino.distancia_km, 9.0)
        # Sólo un centro a más de 15 km: sin píxel.
        lejos = extraccion.elegir_pixel(lat, lon, cat, {NORESTE}, U)
        self.assertGreater(float(numerico.distancia_km(lat, lon, np.array([-33.3]), np.array([-70.5]))[0]), 15.0)
        self.assertEqual(lejos, EleccionPixel(None, None, False))
        # Sin celda que la contenga (mar): el vecino válido más cercano, costera.
        mar = extraccion.elegir_pixel(-33.41, -70.76, cat, todos, U)
        self.assertIsNone(tablas.celda_que_contiene(-33.41, -70.76, cat))
        self.assertEqual((mar.pixel_id, mar.costera), (OESTE, True))
        # Empate exacto de distancias: menor pixel_id.
        dobles = _catalogo_pixeles([(-33.4, -70.6), (-33.4, -70.7), (-33.4, -70.7)], ids=[1, 9, 5])
        empate = extraccion.elegir_pixel(lat, lon, dobles, {5, 9}, U)
        self.assertEqual((empate.pixel_id, empate.costera), (5, True))
        # La celda propia no se elige si no es válida, aunque sea la más cercana.
        self.assertEqual(extraccion.elegir_pixel(lat, lon, dobles, {1, 5}, U).pixel_id, 1)
        self.assertEqual(extraccion.elegir_pixel(lat, lon, dobles, set(), U), EleccionPixel(None, None, False))

    def test_p05_antartica_queda_sin_pixel(self):
        """Sin píxel a ≤ 15 km."""
        U = _umbrales()
        cat = _catalogo_pixeles(GRILLA)
        lat, lon = -62.19, -58.98                                # base Frei, isla Rey Jorge
        self.assertEqual(extraccion.elegir_pixel(lat, lon, cat, set(cat["pixel_id"]), U),
                         EleccionPixel(None, None, False))
        self.assertEqual(tablas.territorio_y_P(lat, lon, cat, {12: "austral"})[0], Territorio.ANTARTICA)
        catalogo = pd.DataFrame([{"codigo": "950001", "nombre": "Frei", "lat_txt": "-62.19", "lon_txt": "-58.98",
                                  "alt_txt": "10", "tipo": None, "propietario": None, "omm": None, "oaci": None}],
                                dtype="string")
        enlaces = extraccion.enlazar_pixeles(catalogo, cat, set(cat["pixel_id"]), U)
        self.assertEqual(enlaces, {"950001": EleccionPixel(None, None, False)})
        info = extraccion.info_estaciones(catalogo, cat, enlaces, {}, {}, {12: "austral"}, U)["950001"]
        self.assertEqual((info.territorio, info.macrozona, info.pixel_id, info.costera, info.z_pix, info.dz),
                         (Territorio.ANTARTICA, "austral", None, False, None, None))

    def test_enlaces_e_info_de_estaciones(self):
        """Coordenadas del catálogo → píxel, z_pix con sp̄, Δz, conjunto V/V2/N y tabla de estaciones."""
        U = _umbrales()
        cat = _catalogo_pixeles(GRILLA)
        catalogo = pd.DataFrame([
            {"codigo": "100001", "nombre": "A", "lat_txt": "-33.41", "lon_txt": "-70.61", "alt_txt": "521",
             "tipo": "Mixta", "propietario": None, "omm": "85574", "oaci": "SCQN"},
            {"codigo": "100002", "nombre": "B", "lat_txt": "s/d", "lon_txt": "-70.61", "alt_txt": "100",
             "tipo": None, "propietario": None, "omm": None, "oaci": None},
            {"codigo": "100003", "nombre": "C", "lat_txt": "33°24'36\" S", "lon_txt": "70°36'36\" W",
             "alt_txt": "", "tipo": None, "propietario": None, "omm": None, "oaci": None},
        ], dtype="string")
        lista_v, lista_v2 = self.tmp / "lista_V.csv", self.tmp / "lista_V2.csv"
        lista_v.write_text("codigo,nombre\n100001,A\n", encoding="utf-8")
        lista_v2.write_text("codigo,razon\n100002,x\n100001,y\n", encoding="utf-8")
        conjuntos = extraccion.leer_conjuntos(lista_v, lista_v2)
        self.assertEqual(conjuntos, {"100001": Conjunto.V, "100002": Conjunto.V2})   # V prevalece
        validos = set(cat["pixel_id"]) - {CENTRO}
        enlaces = extraccion.enlazar_pixeles(catalogo, cat, validos, U)
        self.assertEqual(enlaces["100001"].pixel_id, OESTE)
        self.assertEqual(enlaces["100002"], EleccionPixel(None, None, False))         # no interpretable
        self.assertEqual(enlaces["100003"].pixel_id, OESTE)                           # sexagesimal con letras
        infos = extraccion.info_estaciones(catalogo, cat, enlaces, {OESTE: 950.0}, conjuntos, {13: "centro"}, U,
                                           codigos_extra=["100009"])
        a, b, c, extra = infos["100001"], infos["100002"], infos["100003"], infos["100009"]
        self.assertTrue(a.coordenadas_validas and a.costera)
        self.assertEqual((a.territorio, a.region, a.macrozona, a.conjunto), (Territorio.CONTINENTAL, 13, "centro",
                                                                              Conjunto.V))
        self.assertAlmostEqual(a.z_pix, numerico.z_pixel(950.0))
        self.assertAlmostEqual(a.dz, 521.0 - numerico.z_pixel(950.0))
        self.assertEqual((a.omm, a.oaci, a.tipo), ("85574", "SCQN", "Mixta"))
        self.assertEqual([h.id for h in a.P], ["F(0)", "F(-3)", "F(-4)", "C(Santiago)"])
        self.assertFalse(b.coordenadas_validas)
        self.assertEqual((b.lat, b.pixel_id, b.territorio, b.conjunto), (None, None, Territorio.INCIERTO, Conjunto.V2))
        self.assertAlmostEqual(c.lat, -33.41)
        self.assertIsNone(c.alt_m)
        self.assertIsNone(c.dz)
        self.assertEqual(c.conjunto, Conjunto.N)
        self.assertEqual((extra.nombre, extra.territorio, extra.coordenadas_validas), (None, Territorio.INCIERTO,
                                                                                       False))
        tabla = extraccion.tabla_estaciones(infos)
        validar_esquema(tabla, ESQUEMA_ESTACIONES, nombre="estaciones")
        self.assertEqual(tabla["codigo"].tolist(), ["100001", "100002", "100003", "100009"])
        self.assertEqual(tabla.loc[0, "P"], ["F(0)", "F(-3)", "F(-4)", "C(Santiago)"])
        # Catálogo de píxeles con su huella fijada.
        ruta = self.tmp / "catalogo_pixeles.parquet"
        cat.to_parquet(ruta, index=False)
        sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
        self.assertEqual(extraccion.leer_catalogo_pixeles(ruta, sha)["pixel_id"].tolist(), sorted(cat["pixel_id"]))
        with self.assertRaises(ErrorExtraccion):
            extraccion.leer_catalogo_pixeles(ruta, "0" * 64)

    def test_pixeles_validos_interseccion_t2m_sp(self):
        """Los tres meses de validez y ambas variables."""
        U = _umbrales()
        raiz = self.carpeta("ERA5L")
        pixeles = [11, 22, 33, 44, 55]

        def sin_t2m(pixel):
            def ajustar(s, campos):
                campos["t2m"][:, pixeles.index(pixel)] = np.nan
                return s, campos
            return ajustar

        def sin_sp(pixel):
            def ajustar(s, campos):
                campos["sp"][:, pixeles.index(pixel)] = np.nan
                return s, campos
            return ajustar

        def un_valor(pixel):
            def ajustar(s, campos):
                for v in ("t2m", "sp"):
                    campos[v][1:, pixeles.index(pixel)] = np.nan
                return s, campos
            return ajustar

        meses = [str(int(U.f(i))) for i in extraccion.IDS_MESES_VALIDEZ]
        self.assertEqual(meses, ["200001", "201307", "202507"])
        _mes_nc(raiz, meses[0], pixeles, un_valor(44))
        _mes_nc(raiz, meses[1], pixeles, sin_t2m(22))
        _mes_nc(raiz, meses[2], pixeles, sin_sp(33))
        _mes_nc(raiz, "200002", pixeles, sin_t2m(11))              # fuera de los meses de validez: no cuenta
        self.assertEqual(extraccion.pixeles_validos(raiz, U), {11, 44, 55})

    def test_lector_era5_eje_y_unidades(self):
        """Paso 1 h, sin huecos, HH:00; medianas en rango; si no, A1."""
        raiz = self.carpeta("ERA5L")
        pixeles = [101, 102]
        ruta = _mes_nc(raiz, "200002", pixeles)
        tiempos, pid, valores, control = extraccion.leer_mes_era5land(ruta)
        self.assertEqual(tiempos.dtype, np.dtype("datetime64[h]"))
        self.assertEqual(len(tiempos), 29 * 24)                     # 2000 es bisiesto
        self.assertEqual(pid.tolist(), pixeles)
        self.assertEqual(set(valores), {"t2m", "sp", "u10", "v10"})
        self.assertEqual(valores["t2m"].dtype, np.float32)
        self.assertEqual(valores["t2m"].shape, (696, 2))
        self.assertEqual(control.sha256, hashlib.sha256(ruta.read_bytes()).hexdigest())
        self.assertEqual(control.yyyymm, "200002")
        self.assertTrue(control.eje_ok and control.unidades_ok)
        self.assertTrue(200 <= control.mediana_t2m_K <= 330 and 40000 <= control.mediana_sp_Pa <= 110000)

        def leer(yyyymm, ajustar, unidades="seconds since 1970-01-01 00:00:00 UTC"):
            t = _horas_del_mes(yyyymm)
            campos = {k: np.array(v) for k, v in _campos_sinteticos(t, len(pixeles)).items()}
            s, campos = ajustar(_segundos(t), campos)
            r = extraccion.ruta_mes_era5(raiz, yyyymm)
            _escribir_nc(r, s, pixeles, {k: v[:len(s)] if len(v) != len(s) else v for k, v in campos.items()},
                         unidades)
            return extraccion.leer_mes_era5land(r)

        def quitar(i):
            return lambda s, c: (np.delete(s, i), {k: np.delete(v, i, axis=0) for k, v in c.items()})

        def correr_media_hora(s, c):
            s = s.copy()
            s[10] += 1800
            return s, c

        self.assertFalse(leer("200003", quitar(100))[3].eje_ok)        # un hueco
        self.assertFalse(leer("200004", quitar(0))[3].eje_ok)          # empieza tarde
        self.assertFalse(leer("200005", quitar(-1))[3].eje_ok)         # termina antes del fin del mes
        t, _, _, c = leer("200006", correr_media_hora)
        self.assertFalse(c.eje_ok)
        self.assertTrue(np.isnat(t[10]) and not np.isnat(t[11]))
        self.assertFalse(leer("200007", lambda s, c: (s, c), unidades=None)[3].eje_ok)   # sin units del tiempo
        self.assertTrue(leer("200008", lambda s, c: (s, c), unidades="hours since 1970-01-01")[3].eje_ok is False)
        horas = leer("200009", lambda s, c: (s // 3600, c), unidades="hours since 1970-01-01 00:00:00")[3]
        self.assertTrue(horas.eje_ok)
        celsius = leer("200010", lambda s, c: (s, {**c, "t2m": c["t2m"] - 273.15}))[3]
        self.assertTrue(celsius.eje_ok and not celsius.unidades_ok)
        hpa = leer("200011", lambda s, c: (s, {**c, "sp": c["sp"] / 100}))[3]
        self.assertFalse(hpa.unidades_ok)
        # El último mes llega sólo hasta 2026-09-15T23Z (constante de §3.4) y su eje es correcto.
        ultimo = leer("202609", lambda s, c: (s[:15 * 24], {k: v[:15 * 24] for k, v in c.items()}))[3]
        self.assertTrue(ultimo.eje_ok)
        self.assertFalse(leer("202608", lambda s, c: (s[:15 * 24], {k: v[:15 * 24] for k, v in c.items()}))[3].eje_ok)

    def test_serie_mapeada_eje_global_y_bordes(self):
        """t2m en °C y sp en hPa; eje UTC global; NaN fuera del eje, en horas no enteras y en meses sin leer."""
        raiz, destino = self.carpeta("ERA5L"), self.carpeta("corrida")
        en_archivo = [101, 102, 103]
        for m in ("200001", "200002"):
            _mes_nc(raiz, m, en_archivo)
        avance = _Avance()
        serie, controles = extraccion.extraer_era5land(raiz, [103, 101, 999], destino, meses=("200001", "200002"),
                                                       validos={101, 103}, catalogo_sha256="f" * 64, **avance.kw())
        self.assertEqual(set(controles), {"200001", "200002"})
        self.assertTrue(all(c.eje_ok and c.unidades_ok for c in controles.values()))
        self.assertEqual(avance.registrados, ["era5/200001", "era5/200002"])
        self.assertEqual(avance.pasos, [(1, 2), (2, 2)])
        self.assertEqual(serie.t0, np.datetime64("2000-01-01T00", "h"))
        self.assertEqual(serie.n_horas, extraccion.N_HORAS_ERA5)
        self.assertEqual(serie.n_horas, 234120)
        self.assertEqual(serie.pixel_ids, (101, 103, 999))
        self.assertEqual(serie.validos, frozenset({101, 103}))
        self.assertTrue(serie.tiene(101) and serie.tiene(999) and not serie.tiene(102))
        u = np.array(["2000-01-01T05", "2000-01-31T23", "2000-02-01T00", "2000-02-29T23", "2000-03-01T00",
                      "1999-12-31T23", "2026-09-16T00", "NaT"], dtype="datetime64[h]")
        t2m = serie.valores(103, "t2m", u)
        self.assertEqual(t2m.dtype, np.float64)
        horas = ((u[:4] - extraccion.T0_ERA5) // np.timedelta64(1, "h")).astype(np.int64)
        esperado = 280.0 + 2 + (horas % 24) * 0.5 - 273.15        # 103 es la columna 2 del archivo
        np.testing.assert_allclose(t2m[:4], esperado, atol=1e-4)
        self.assertTrue(np.isnan(t2m[4:]).all())
        sp = serie.valores(101, "sp", u[:4])
        np.testing.assert_allclose(sp, (95000.0 + (horas % 48)) / 100, atol=1e-3)
        np.testing.assert_allclose(serie.valores(101, "u10", u[:2]), [1.0, 1.0])
        np.testing.assert_allclose(serie.valores(103, "v10", u[:2]), [-3.0, -3.0])
        self.assertTrue(np.isnan(serie.valores(999, "t2m", u[:4])).all())      # no está en el archivo
        media = np.asarray(np.arange(744 + 696) % 48, dtype=np.float64).mean()
        self.assertAlmostEqual(serie.media(101, "sp"), (95000.0 + media) / 100, places=3)
        self.assertTrue(math.isnan(serie.media(999, "sp")))
        media_hora = np.array(["2000-01-01T05:30"], dtype="datetime64[m]")
        self.assertTrue(np.isnan(serie.valores(101, "t2m", media_hora)).all())
        consciente = pd.DatetimeIndex(["2000-01-01T05:00"], tz="UTC").to_pydatetime()
        np.testing.assert_allclose(serie.valores(103, "t2m", consciente), t2m[:1], atol=1e-6)
        with self.assertRaises(KeyError):
            serie.valores(102, "t2m", u)
        with self.assertRaises(KeyError):
            serie.valores(101, "d2m", u)
        carpeta = destino / "extractos" / "era5"
        self.assertEqual(sorted(p.name for p in carpeta.iterdir()), ["indice.json", "serie.f4"])
        indice = json.loads((carpeta / "indice.json").read_text(encoding="utf-8"))
        self.assertEqual(indice["meses"]["200001"]["sha256"],
                         hashlib.sha256(extraccion.ruta_mes_era5(raiz, "200001").read_bytes()).hexdigest())
        self.assertEqual(indice["catalogo_pixeles_sha256"], "f" * 64)
        otra = extraccion.SerieEra5Mapeada(carpeta)
        np.testing.assert_array_equal(otra.valores(103, "t2m", u), t2m)
        # Un mes sin archivo queda con eje anómalo (A1) y sin sha256.
        _, controles2 = extraccion.extraer_era5land(raiz, [101], self.carpeta("otra"), meses=("200001", "200003"),
                                                    **_Avance().kw())
        self.assertEqual((controles2["200003"].sha256, controles2["200003"].eje_ok), ("", False))
        self.assertTrue(controles2["200001"].eje_ok)

    def test_extraccion_reanudable_y_atomica(self):
        """Unidades con huellas iguales se saltan; un corte no deja archivos a medias."""
        U, desc, adaptador = _umbrales(), _descargador(), _adaptador()
        # --- ERA5-Land: meses.
        raiz_e = self.carpeta("ERA5L")
        meses = ("200001", "200002", "200003")
        for m in meses:
            _mes_nc(raiz_e, m, [101, 103])
        d1, d2 = self.carpeta("e1"), self.carpeta("e2")
        av1 = _Avance()
        extraccion.extraer_era5land(raiz_e, [101, 103], d1, meses=meses, **av1.kw())
        original = extraccion._decodificar_mes
        with mock.patch.object(extraccion, "_decodificar_mes", wraps=original) as dec:
            extraccion.extraer_era5land(raiz_e, [101, 103], d1, meses=meses, **av1.kw())
            dec.assert_not_called()
        self.assertEqual(av1.registrados, [f"era5/{m}" for m in meses])

        def falla(datos, yyyymm, sha):
            if yyyymm == "200002":
                raise RuntimeError("corte simulado")
            return original(datos, yyyymm, sha)

        av2 = _Avance()
        with mock.patch.object(extraccion, "_decodificar_mes", side_effect=falla):
            with self.assertRaises(RuntimeError):
                extraccion.extraer_era5land(raiz_e, [101, 103], d2, meses=meses, **av2.kw())
        carpeta2 = d2 / "extractos" / "era5"
        self.assertFalse((carpeta2 / "serie.f4").exists() or (carpeta2 / "indice.json").exists())
        self.assertTrue((carpeta2 / "serie.f4.part").exists())
        self.assertEqual(av2.registrados, ["era5/200001"])
        with mock.patch.object(extraccion, "_decodificar_mes", wraps=original) as dec:
            extraccion.extraer_era5land(raiz_e, [101, 103], d2, meses=meses, **av2.kw())
            self.assertEqual([c.args[1] for c in dec.call_args_list], ["200002", "200003"])
        self.assertEqual(sorted(p.name for p in carpeta2.iterdir()), ["indice.json", "serie.f4"])
        for nombre in ("serie.f4", "indice.json"):
            self.assertEqual((d1 / "extractos" / "era5" / nombre).read_bytes(), (carpeta2 / nombre).read_bytes())
        # Otros píxeles: otra configuración, la serie se rehace entera.
        with mock.patch.object(extraccion, "_decodificar_mes", wraps=original) as dec:
            serie = extraccion.extraer_era5land(raiz_e, [101], d2, meses=meses, **av2.kw())[0]
            self.assertEqual(dec.call_count, 3)
        self.assertEqual(serie.pixel_ids, (101,))

        # --- DMC: estaciones.
        raiz = self.carpeta("DMC")
        _fabricar(raiz, lambda c, a, m: _filas_normales(desc, dias=1), "2020-01-01", "2020-02-29",
                  estaciones=ESTACIONES)
        d3, d4 = self.carpeta("c1"), self.carpeta("c2")
        av3, contado = _Avance(), _AdaptadorContado(adaptador)
        r1 = _extraer(raiz, d3, adaptador=contado, avance=av3)
        self.assertEqual(len(contado.llamadas), 4)
        self.assertEqual(av3.registrados, [f"dmc/{CODIGO}", f"dmc/{CODIGO_2}"])
        contado.llamadas.clear()
        r2 = _extraer(raiz, d3, adaptador=contado, avance=av3)
        self.assertEqual((contado.llamadas, len(av3.registrados)), ([], 2))
        self.assertEqual(r1, r2)
        self.assertEqual(av3.pasos[-2:], [(1, 2), (2, 2)])
        # Corte en la segunda estación: la primera queda entera, la segunda y los agregados no existen.
        av4 = _Avance()
        with self.assertRaises(RuntimeError):
            _extraer(raiz, d4, adaptador=_AdaptadorContado(adaptador, falla_en=CODIGO_2), avance=av4)
        carpeta4 = d4 / "extractos" / "dmc"
        self.assertTrue((carpeta4 / f"{CODIGO}.parquet").is_file())
        self.assertFalse((carpeta4 / f"{CODIGO_2}.parquet").exists() or (carpeta4 / "meses.parquet").exists())
        self.assertEqual(list(d4.rglob("*.part")), [])
        self.assertEqual(av4.registrados, [f"dmc/{CODIGO}"])
        reanuda = _AdaptadorContado(adaptador)
        r3 = _extraer(raiz, d4, adaptador=reanuda, avance=av4)
        self.assertEqual({ll.split("/")[0] for ll in reanuda.llamadas}, {CODIGO_2})
        self.assertEqual(r3, r1)
        for nombre in (f"{CODIGO}.parquet", f"{CODIGO_2}.parquet", "meses.parquet", "artefactos_evaluados.json",
                       "resumen.json"):
            self.assertEqual((d3 / "extractos" / "dmc" / nombre).read_bytes(), (carpeta4 / nombre).read_bytes())
        # Un manifiesto que cambia cambia la huella de su estación: sólo ésa se vuelve a leer.
        _editar_manifiesto(raiz, CODIGO, "2020-02", lambda m: m.update(nota="cambio"))
        otra = _AdaptadorContado(adaptador)
        r4 = _extraer(raiz, d4, adaptador=otra, avance=av4)
        self.assertEqual({ll.split("/")[0] for ll in otra.llamadas}, {CODIGO})
        self.assertNotEqual(r4.huella_manifiestos, r1.huella_manifiestos)
        # Un archivo de unidad borrado se rehace aunque avance la dé por hecha.
        (carpeta4 / f"{CODIGO_2}.parquet").unlink()
        otra.llamadas.clear()
        _extraer(raiz, d4, adaptador=otra, avance=av4)
        self.assertEqual({ll.split("/")[0] for ll in otra.llamadas}, {CODIGO_2})



# Las tres celdas de la fila 1399 de catalogo_pixeles.parquet de ERA5L (49,9° S), con sus valores tal como están
# guardados; el centro (5039262) es la estación de prueba de C3b donde se vio la errata E-1 de la Enmienda 5.
_CAT_1399 = pd.DataFrame({
    "pixel_id": np.array([5039261, 5039262, 5039263], dtype=np.int64),
    "lat_index_global": [1399, 1399, 1399], "lon_index_global": [2861, 2862, 2863],
    "latitude": [-49.9, -49.9, -49.9], "longitude": [-73.9, -73.8, -73.7],
    "cell_west": [-73.95, -73.85, -73.75], "cell_east": [-73.85, -73.75, -73.65],
    "cell_south": [-49.95, -49.95, -49.95], "cell_north": [-49.85, -49.85, -49.85],
    "cod_comuna": [12401, 12401, 12401], "asignacion_comuna": ["centro"] * 3,
    "territorio": ["continental"] * 3, "aoi_id": ["continente"] * 3})


class PruebasEnmienda5Empate(unittest.TestCase):
    """ERR-1 (errata E-1 de la Enmienda 5) en ``elegir_pixel`` (§3.3, el píxel de las estaciones en C4)."""

    def test_err1_elegir_pixel_celda_propia_no_valida_empate_menor_pixel_id(self):
        """§3.3: «el centro válido más cercano a ≤ 15 km, con empate por menor `pixel_id`». La celda propia
        (5039262) no es válida y sus vecinas este y oeste están a la misma distancia: decide el oeste, 5039261.
        El código anterior a la errata elegía 5039263, el que la coma flotante dejaba 6·10⁻¹³ km más cerca."""
        e = extraccion.elegir_pixel(-49.9, -73.8, _CAT_1399, {5039261, 5039263}, _umbrales())
        self.assertEqual((e.pixel_id, e.costera), (5039261, True))
        self.assertAlmostEqual(e.distancia_km, 7.16233734, places=6)


if __name__ == "__main__":
    unittest.main()
