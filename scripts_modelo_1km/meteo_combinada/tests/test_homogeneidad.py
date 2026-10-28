"""Pruebas de homogeneidad.py (§2.5 (K4) y §4.8).

Dueño: I9 (olas 2 y 3). Las que llevan «sNN» son la prueba NN de §9 del texto: S4 entera y la parte de S5 del cambio
de sensor (un tramo; que no pase a B ni a AB lo prueba I13 en ``candidatos``). Correr desde scripts_modelo_1km con
  ~/micromamba/envs/amb_v2/bin/python -B -m unittest discover -s meteo_combinada/tests -t .
Datos sólo sintéticos y en memoria: las series de S4 son las de ``sintetico.series_traslado`` (ruido de MC-49 con la
estructura de SIN-13 y las señales de SIN-20), la verdad de S5 la de ``sintetico.verdad`` con las anomalías de MC-50
(SIN-21) y el resto son tablas hechas a mano aquí. Nada se escribe en el disco, y ninguna prueba abre DMC, la
meteorología SINCA real, NASADEM real, ERA5L real ni GHS-POP real. Los umbrales son los anclados en M0
(``umbrales.cargar_m0``); sólo se leen el texto y el JSON de umbrales de APH.

Semillas (D42; HOM-13 y HOM-14 de ``homogeneidad``). Cada caso de S4 y S5 se prueba con la semilla del protocolo
(``SEMILLA`` del Anexo A, 20261023), que no se eligió probando semillas. S4 informa además la tasa sobre un conjunto
fijado de antemano, SEMILLA + i con i = 0…``N_SEMILLAS_S4`` − 1 en cada caso y altitud (el que usó el revisor de la
ola 2 para P28; no se midió ningún otro), y la declara en ``TASAS_S4``; los falsos quiebres usan SEMILLA + i, i = 0…199
(§9: «200 series»). La clasificación es la de EMC2-1 (Enmienda 2 del producto, texto v2.3; D52, sobre P28): con la
semilla del protocolo el traslado de 15 m se declara a 500 y 1.000 m; a 2.500 m la prueba sigue omitida, con el motivo
de P47 (D56), y su tasa se informa igual. La prueba informativa de S5 sin la media 0 (D42) usa SEMILLA + i,
i = 0…``N_SEMILLAS_S5`` − 1, y no decide S5.
"""
import sys

sys.dont_write_bytecode = True

import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from meteo_combinada import constantes, homogeneidad, sintetico, tipos, umbrales  # noqa: E402
from meteo_combinada.tipos import ClaseQuiebre, Estadistico  # noqa: E402

_AP = _RAIZ.parent
_APH = _AP.parent / "Air-Pollution-Health-Chile"

# Valores del Anexo A (fila «Traslados» y «Tramos homogéneos») que suponen las tablas hechas a mano; la prueba
# ``test_valores_que_suponen_las_pruebas_son_los_del_anexo_a`` los compara con los anclados.
VALORES_ANEXO_A = {"K4_T2A_M": 10, "K4_T2B_HPA": 1.2, "K4_MIN_MES_HORA": 5, "K4_HORAS_PCT": 80, "K4_VENTANA": 12,
                   "K4_MIN_LADO": 6, "K4_MIN_PARES": 100, "K4_MAX_QUIEBRES": 3, "K4_TRAMO_MIN": 12,
                   "K4_COINC_MESES": 3, "K4_COINC_M": 10, "K4_COINC_FRAC": 0.3, "HOM_T": 0.5, "HOM_TD": 1.0,
                   "SEMILLA": 20261023}

# D42 y D52 (HOM-14): tasas de S4 sobre SEMILLA + i, i = 0…N_SEMILLAS_S4 − 1, en cada caso y altitud, con la regla de
# EMC2-1 (v2.3). El conjunto se fijó antes de medir (es el que usó el revisor de la ola 2 para P28 y el borrador de la
# Enmienda 2) y no se midió ningún otro. Aciertos de N_SEMILLAS_S4 (la definición de acierto es la de ``_acierto_s4``);
# si el generador o el detector cambian, la prueba falla y las tasas se vuelven a declarar aquí y en el addendum. Con la
# regla literal del v2.2 el traslado de 15 m daba 90, 89 y 81; lo demás no cambia.
N_SEMILLAS_S4 = 100
TASAS_S4 = {
    "traslado_15": {500: 100, 1000: 100, 2500: 96},
    "traslado_5": {500: 100, 1000: 100, 2500: 100},
    "barometro": {500: 100, 1000: 99, 2500: 100},
    "reduccion": {500: 100, 1000: 100, 2500: 100},
    "horario": {500: 100, 1000: 100, 2500: 100},
}
FALSOS_S4 = 0                   # series estacionarias con algún quiebre, de las 200 de §9 (SEMILLA + i, i = 0…199)

# D42 (HOM-13): prueba informativa de S5 sobre SEMILLA + i, i = 0…N_SEMILLAS_S5 − 1. «falsos»: residuos estacionarios
# con más de un tramo (de N_SEMILLAS_S5); «sensor»: cambios de sensor de 1 K recuperados (de 2·N_SEMILLAS_S5, en las
# dos fechas de ``CAMBIOS_S5``; la definición es la de ``_cambio_de_sensor``). No decide S5.
N_SEMILLAS_S5 = 20
CAMBIOS_S5 = ("2013-01-01T00", "2013-07-01T00")
# MC-50 (σ = 1,5 K, correlación de 100 km y media 0 en cada estación-mes-año) con τ = 48 h (D42), escritas a mano:
# ``_verdad_s5`` exige que ``sintetico.verdad(…, "MC-50")`` use éstas.
ANOMALIAS_MC50 = {"sigma": 1.5, "L_km": 100.0, "tau_h": 48.0, "media_cero": True}
INFORMATIVA_S5 = {"MC-50": {"falsos": 0, "sensor": 40}, "sin_media_cero": {"falsos": 14, "sensor": 9}}

# P47 (D56; antes en D52): el traslado de 15 m a 2.500 m con la semilla del protocolo sigue omitido, con un motivo
# nuevo, y la tasa se informa (HOM-14).
MOTIVO_P47 = ("P47 (D56): con la semilla del protocolo, a 2.500 m no hay quiebre de T2b (máx |D| = 1,187 hPa < 1,2 hPa; "
              "15 m mueven QFE ≈ 1,37 hPa): sale sólo un quiebre de T2a («método de reducción») y ninguna regla de "
              "clasificación puede declarar el traslado. Es un límite de la señal, no de la regla. Tasa con EMC2-1 sobre "
              "SEMILLA + i, i = 0…99: 96 de 100; las 4 que fallan (i = 0, 14, 20 y 30) no tienen quiebre de T2b (HOM-14)")
_U = None


def _umbrales():
    global _U
    if _U is None:
        texto = _APH / umbrales.TEXTO_M0
        if not texto.is_file():
            raise unittest.SkipTest(f"falta {texto.name} anclado en M0; la prueba no se da por aprobada")
        _U = umbrales.cargar_m0(_APH)
    return _U


_EPOCA = np.datetime64("2000-01-01T00", "h")


def _h(fecha: str) -> int:
    return int((np.datetime64(fecha, "h") - _EPOCA).astype(np.int64))


def _horas(desde: str, hasta: str) -> np.ndarray:
    """Horas UTC de ``desde`` (incluida) a ``hasta`` (excluida)."""
    return np.arange(_h(desde), _h(hasta), dtype=np.int64)


def _serie(tipo: str, altitud: float, **kw) -> pd.DataFrame:
    return sintetico.series_traslado(tipo, altitud, semilla=kw.pop("semilla", _umbrales().a("SEMILLA")), **kw)


def _k4(df: pd.DataFrame, **kw) -> tipos.ResultadoK4:
    tabla = df[["h", "Ts", "QFE", "QFF"]]
    return homogeneidad.k4(tabla, df["p_F"].to_numpy(), df.attrs["z_cat"], _umbrales(), codigo="330020", **kw)


def _mes_del_cambio(df: pd.DataFrame) -> int:
    return int(homogeneidad.mes2000(np.array([df.attrs["cambio_h"]]))[0])


def _media_meseta() -> int:
    """Media anchura de la meseta de D(k) en un escalón limpio: con la mediana de 12 meses, D(k) no cambia mientras
    ≤ 5 de los 12 meses de una ventana queden del otro lado del escalón (HOM-5)."""
    return _umbrales().a("K4_VENTANA") // 2 - 1


def _medianas_a_mano(filas: dict[int, tuple[int, dict[int, float]]]) -> pd.DataFrame:
    """Tabla de ``medianas_mes_hora`` hecha a mano: {mes: (pares, {hora: mediana})}."""
    meses = sorted(filas)
    datos = np.full((len(meses), homogeneidad.HORAS_DIA), np.nan)
    pares = np.zeros(len(meses), dtype=np.int64)
    for i, m in enumerate(meses):
        pares[i] = filas[m][0]
        for hora, v in filas[m][1].items():
            datos[i, hora] = v
    df = pd.DataFrame(datos, index=pd.Index(np.array(meses, dtype=np.int64), name="mes"),
                      columns=list(homogeneidad.COLUMNAS_HORA))
    df.insert(0, homogeneidad.COLUMNA_PARES, pares)
    return df


def _escalones(h: np.ndarray, cortes: list[int], niveles: list[float]) -> np.ndarray:
    """Residuo sin ruido: ``niveles[i]`` desde el mes ``cortes[i − 1]`` (mes2000) hasta antes de ``cortes[i]``."""
    meses = homogeneidad.mes2000(h)
    tramo = np.searchsorted(np.array(cortes), meses, side="right")
    return np.array(niveles, dtype=np.float64)[tramo]


def _verdad_s5(h: np.ndarray, semilla: int, anomalias="MC-50") -> np.ndarray:
    """Residuo de una estación sintética: sesgo b(x, m, h) estacional y diurno más las anomalías de MC-50 (D42, SIN-21,
    HOM-13: σ = 1,5 K, L = 100 km, τ = 48 h y media 0 en cada mes × año, para probar el método y no el ruido de
    muestreo). ``anomalias`` = ``{"media_cero": False}`` es la prueba informativa de D42."""
    def sesgo(lat, lon, m, hora):
        return np.full(len(lat), 1.0 + 0.5 * np.cos(2 * np.pi * (m - 1) / 12) + 0.8 * np.cos(2 * np.pi * (hora - 15) / 24))
    v = sintetico.verdad({"h": h, "lat": np.array([-33.4]), "lon": np.array([-70.6]), "F": np.zeros((len(h), 1))},
                         sesgo, anomalias, semilla=semilla)
    if anomalias == "MC-50" and v["anomalias"] != ANOMALIAS_MC50:
        raise AssertionError(f"anomalías de S5 distintas de las de MC-50 y D42: {v['anomalias']}")
    return (v["obs"] - v["F"])[:, 0]


def _cambio_de_sensor(h: np.ndarray, r: np.ndarray, cambio: str, U) -> dict:
    """S5 (§4.8): suma al residuo ``r`` un cambio de sensor de ``S5_SENSOR_K`` desde el mes de ``cambio`` y da los
    tramos, los δ, los tramos de r̃ = r − δ(g) y si el cambio se recuperó: dos tramos, el corte en la meseta de su mes,
    δ(1) − δ(0) a ≤ 0,2 K del escalón y r̃ sin quiebre (un tramo)."""
    sensor = constantes.valor("S5_SENSOR_K")
    k0 = int(homogeneidad.mes2000(np.array([_h(cambio)]))[0])
    rs = r + np.where(homogeneidad.mes2000(h) >= k0, sensor, 0.0)
    tramos = homogeneidad.tramos_homogeneos(h, rs, tipos.Variable.T, U)
    salida = {"k0": k0, "tramos": tramos, "d": None, "tramos_rt": None, "recuperado": False}
    if len(tramos) != 2 or abs(tramos[1][0] - k0) > _media_meseta():
        return salida
    d = homogeneidad.desplazamientos(h, rs, tramos, U)
    g = np.searchsorted([a for a, _ in tramos], homogeneidad.mes2000(h), side="right") - 1
    rt = rs - np.array([d[i] for i in range(len(tramos))])[g]
    tramos_rt = homogeneidad.tramos_homogeneos(h, rt, "T", U)
    salida.update(d=d, tramos_rt=tramos_rt,
                  recuperado=abs(d[1] - d[0] - sensor) <= 0.2 and len(tramos_rt) == 1)
    return salida


def _salto_sin_h_estrella(t, k: int, umbrales_) -> float | None:
    """Oráculo de D(k) **sin** H*(k), con la firma de ``homogeneidad._salto``: M(j) es la media de todas las medianas
    que tenga el mes j (de cualquier hora UTC), en los meses con ≥ 100 pares, con ≥ 6 de esos meses por lado. Es la
    media diaria ingenua que H*(k) evita (§2.5: «Así un cambio de horario … no mueve la estadística»)."""
    medias = []
    for lado in homogeneidad._lados(t, k, umbrales_):
        cand = lado[t.pares[lado] >= umbrales_.a("K4_MIN_PARES")]
        if len(cand) < umbrales_.a("K4_MIN_LADO"):
            return None
        medias.append(np.nanmean(t.med[cand], axis=1))
    antes, despues = medias
    return float(np.median(despues) - np.median(antes))


def _estadisticos(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """h, T2a y T2b de §2.5 escritos a mano (oráculo): z_impl = 29,27 · T̄ · ln(QFF/QFE) y QFE − p_F."""
    h = df["h"].to_numpy().astype(np.int64)
    t2a = _Z_IMPL * _tbar(df["Ts"].to_numpy(), df.attrs["z_cat"]) * np.log(df["QFF"].to_numpy() / df["QFE"].to_numpy())
    t2b = (df["QFE"] - df["p_F"]).to_numpy()
    return h, t2a, t2b


def _acierto_s4(caso: str, r: tipos.ResultadoK4, k0: int) -> bool:
    """Acierto de una serie de S4 (HOM-14), con el k a ≤ media meseta (5 meses) del mes del cambio ``k0``."""
    w = _media_meseta()
    clases = [(q.estadistico, q.clase) for q in r.quiebres]
    cerca = all(abs(q.mes - k0) <= w for q in r.quiebres)
    if caso == "traslado_15":
        return r.ultimo_traslado is not None and r.ultimo_barometro is None and abs(r.ultimo_traslado - k0) <= w
    if caso in ("traslado_5", "horario"):
        return r.quiebres == ()
    if caso == "barometro":
        return clases == [(T2B, BAROMETRO)] and cerca
    if caso == "reduccion":
        return clases == [(T2A, REDUCCION)] and cerca
    raise ValueError(caso)


def _serie_s4(caso: str, altitud: float, semilla: int) -> pd.DataFrame:
    tipo, magnitud = {"traslado_15": ("traslado", constantes.valor("S4_TRASLADOS_M")[0]),
                      "traslado_5": ("traslado", constantes.valor("S4_TRASLADOS_M")[1]),
                      "barometro": ("barometro", constantes.valor("S4_BAROMETRO_HPA")),
                      "reduccion": ("reduccion", None), "horario": ("horario", None)}[caso]
    return sintetico.series_traslado(tipo, float(altitud), semilla=semilla, magnitud=magnitud)


# Fórmulas de §2.5 escritas aquí a mano, como oráculo independiente del código (la prueba
# ``test_formulas_de_2_5_que_suponen_las_pruebas`` las compara con ``constantes``): z_impl = 29,27 · T̄ · ln(QFF/QFE),
# con T̄ = Ts + 273,15 + 0,0065·z_cat/2 (K), y Δz_b = −ΔQFE · 287,05 · T̄ / (9,80665 · p̄).
_Z_IMPL, _KELVIN, _GAMMA_TBAR, _R_SECO, _GRAVEDAD = 29.27, 273.15, 0.0065, 287.05, 9.80665
_T0_ESTANDAR = 288.15           # K: atmósfera estándar a nivel del mar; T̄_std = 288,15 − 0,0065·z/2 (SIN-20)
_P_F = 880.0                    # fondo constante (hPa) de las series de K4 hechas a mano
T2A, T2B = Estadistico.T2A.value, Estadistico.T2B.value
TRASLADO, BAROMETRO, REDUCCION = ClaseQuiebre.TRASLADO, ClaseQuiebre.BAROMETRO, ClaseQuiebre.METODO_REDUCCION


def _tbar(ts, z_cat: float):
    return ts + _KELVIN + _GAMMA_TBAR * z_cat / 2


def _serie_k4(meses: int, *, z_cat: float = 1000.0, p0: float = 900.0, z0: float = 1000.0, saltos_qfe=(),
              saltos_z=()) -> pd.DataFrame:
    """Serie de K4 hecha a mano y sin ruido, de enero de 2000 (mes2000 0) a ``meses`` meses después: Ts con un ciclo
    diurno que sólo depende de la hora UTC, p_F constante, QFE = p0 + los saltos (mes, ΔQFE) de ``saltos_qfe`` y
    z_impl = z0 + los saltos (mes, Δz) de ``saltos_z``; QFF = QFE · exp(z_impl / (29,27 · T̄)). Un salto de QFE sin
    salto de z es un error del barómetro (QFE y QFF en la misma proporción); uno de z sin QFE mueve sólo QFF. Todos
    los meses de un tramo traen los mismos valores en cada hora UTC: medianas, M y D son exactos salvo el redondeo de
    float64, y las mesetas de D empatan (el quiebre cae en su mes, HOM-5)."""
    fin = (np.datetime64("2000-01", "M") + meses).astype("datetime64[h]")
    h = np.arange(0, int((fin - _EPOCA).astype(np.int64)), dtype=np.int64)
    mes = homogeneidad.mes2000(h)
    ts = 15.0 + 5.0 * np.cos(2 * np.pi * (h % 24 - 19) / 24)
    qfe = np.full(len(h), p0)
    for k, d in saltos_qfe:
        qfe = qfe + np.where(mes >= k, d, 0.0)
    z = np.full(len(h), z0)
    for k, d in saltos_z:
        z = z + np.where(mes >= k, d, 0.0)
    qff = qfe * np.exp(z / (_Z_IMPL * _tbar(ts, z_cat)))
    df = pd.DataFrame({"h": h, "Ts": ts, "QFE": qfe, "QFF": qff, "p_F": np.full(len(h), _P_F)})
    df.attrs["z_cat"] = z_cat
    return df


def _dz_b(df: pd.DataFrame, d_qfe: float, desde: int, hasta: int) -> float:
    """Δz_b de §2.5 hecho a mano, con T̄ y p̄ medias sobre las horas con T2b del tramo [desde, hasta] que el quiebre
    partió (HOM-7)."""
    mes = homogeneidad.mes2000(df["h"].to_numpy())
    en = (mes >= desde) & (mes <= hasta) & np.isfinite((df["QFE"] - df["p_F"]).to_numpy())
    tbar = float(np.mean(_tbar(df["Ts"].to_numpy()[en], df.attrs["z_cat"])))
    pbar = float(np.mean(df["QFE"].to_numpy()[en]))
    return -d_qfe * _R_SECO * tbar / (_GRAVEDAD * pbar)


def _dqfe_traslado(dz: float, p: float, z_cat: float = 1000.0) -> float:
    """ΔQFE (hPa) aproximado de un traslado de ``dz`` m hacia arriba con la presión ``p`` (la inversa de Δz_b con la
    T̄ media del día): basta para quedar muy dentro de la tolerancia de §2.5."""
    return -dz * _GRAVEDAD * p / (_R_SECO * _tbar(15.0, z_cat))


def _clases(r: tipos.ResultadoK4) -> list[tuple[str, int, ClaseQuiebre | None]]:
    return [(q.estadistico, q.mes, q.clase) for q in r.quiebres]


def _una_hora(valores, pares=500) -> pd.DataFrame:
    """Tabla de medianas hecha a mano con una sola hora UTC (la 0) y meses 0, 1…: H* = {0} y M(j) es la mediana
    misma, sin promedios entre horas (D exacto). ``pares`` es un número o una lista por mes."""
    lista = pares if isinstance(pares, (list, tuple)) else [pares] * len(valores)
    return _medianas_a_mano({m: (lista[m], {0: float(v)}) for m, v in enumerate(valores)})


class PruebasS4(unittest.TestCase):
    """S4 (§9) con la semilla del protocolo: traslados, barómetro, reducción, horario y falsos quiebres, con
    ``sintetico.series_traslado`` (D42; las tasas sobre el conjunto de semillas fijado van en ``PruebasS4Tasas``)."""

    def _traslado_de_15_m(self, altitud: float):
        U = _umbrales()
        magnitud = constantes.valor("S4_TRASLADOS_M")[0]
        df = _serie("traslado", altitud, magnitud=magnitud)
        k = _mes_del_cambio(df)
        r = _k4(df)
        self.assertEqual(r.codigo, "330020")
        self.assertFalse(r.sin_prueba)
        self.assertIsNone(r.ultimo_barometro)
        self.assertIsNotNone(r.ultimo_traslado)
        self.assertLessEqual(abs(r.ultimo_traslado - k), U.a("K4_COINC_MESES"))
        t2b = [q for q in r.quiebres if q.estadistico == Estadistico.T2B]
        t2a = [q for q in r.quiebres if q.estadistico == Estadistico.T2A]
        self.assertEqual([q.clase for q in t2b], [ClaseQuiebre.TRASLADO])
        self.assertLess(t2b[0].D, -U.a("K4_T2B_HPA"))          # la estación sube: QFE baja
        self.assertEqual(len(t2a), 1)
        self.assertIsNone(t2a[0].clase)                        # A4: el de T2a con T2b cerca va sin clase
        self.assertAlmostEqual(t2a[0].D, magnitud, delta=1.0)  # z_impl sube 15 m

    def test_s04_traslado_de_15_m_coherente_es_traslado(self):
        """QFE y QFF coherentes: traslado, a 500 y 1.000 m (la altitud más alta, 2.500 m, va en la prueba siguiente)."""
        altitudes = constantes.valor("S4_ALTITUDES_M")
        for altitud in altitudes:
            if altitud == max(altitudes):
                continue
            with self.subTest(altitud=altitud):
                self._traslado_de_15_m(float(altitud))

    @unittest.skip(MOTIVO_P47)
    def test_s04_traslado_de_15_m_a_2500_m(self):
        """D42: el traslado de 15 m se prueba en las tres altitudes; la de 2.500 m queda omitida con el motivo de P47
        (D56): con la semilla del protocolo no hay quiebre de T2b, y su tasa se informa en ``TASAS_S4``."""
        self._traslado_de_15_m(float(max(constantes.valor("S4_ALTITUDES_M"))))

    def test_s04_traslado_de_5_m_no_se_detecta(self):
        """Un traslado de 5 m no se declara (en 500, 1.000 y 2.500 m no hay ningún quiebre)."""
        magnitud = constantes.valor("S4_TRASLADOS_M")[1]
        for altitud in constantes.valor("S4_ALTITUDES_M"):
            with self.subTest(altitud=altitud):
                r = _k4(_serie("traslado", float(altitud), magnitud=magnitud))
                self.assertIsNone(r.ultimo_traslado)
                self.assertEqual(r.quiebres, ())

    def test_s04_barometro_de_1_5_hpa_es_inhomogeneidad(self):
        """Error de barómetro de 1,5 hPa: inhomogeneidad, no traslado (z_impl no cambia: no hay quiebre de T2a)."""
        magnitud = constantes.valor("S4_BAROMETRO_HPA")
        for altitud in constantes.valor("S4_ALTITUDES_M"):
            with self.subTest(altitud=altitud):
                df = _serie("barometro", float(altitud), magnitud=magnitud)
                r = _k4(df)
                self.assertIsNone(r.ultimo_traslado)
                self.assertIsNotNone(r.ultimo_barometro)
                self.assertLessEqual(abs(r.ultimo_barometro - _mes_del_cambio(df)), _media_meseta())
                self.assertEqual([(q.estadistico, q.clase) for q in r.quiebres],
                                 [(Estadistico.T2B.value, ClaseQuiebre.BAROMETRO)])
                self.assertGreater(r.quiebres[0].D, 0.0)

    def test_s04_reduccion_estandar_a_real_no_es_traslado(self):
        """Cambio de la atmósfera estándar a la real en la reducción, en 500, 1.000 y 2.500 m (SIN-20): la estación es
        ``dt_clima_k`` = 10 K más cálida que la atmósfera estándar y z_impl salta −z·ΔT/T̄_std (−17,5, −35 y −89 m),
        sobre el umbral de T2a, sin tocar QFE. K4 ve ese salto como un solo quiebre, de T2a y «cambio del método de
        reducción» (sólo se informa), en la meseta de su mes y con D a ≤ 10 % del salto, sin traslado ni barómetro.
        Con la señal en 0 (``dt_clima_k = 0``) no hay ningún quiebre: el que se ve es el de la señal (pedido 3 de
        I5)."""
        U = _umbrales()
        for altitud in constantes.valor("S4_ALTITUDES_M"):
            z = float(altitud)
            with self.subTest(altitud=altitud):
                df = _serie("reduccion", z)
                salto = -z * df.attrs["dt_clima_k"] / (_T0_ESTANDAR - _GAMMA_TBAR * z / 2)
                self.assertGreaterEqual(abs(salto), U.a("K4_T2A_M"))
                r = _k4(df)
                self.assertEqual([(q.estadistico, q.clase) for q in r.quiebres], [(T2A, REDUCCION)])
                self.assertLessEqual(abs(r.quiebres[0].mes - _mes_del_cambio(df)), _media_meseta())
                self.assertAlmostEqual(r.quiebres[0].D, salto, delta=0.1 * abs(salto))
                self.assertEqual((r.ultimo_traslado, r.ultimo_barometro, r.sin_prueba), (None, None, False))
                self.assertEqual(_k4(_serie("reduccion", z, dt_clima_k=0.0)).quiebres, ())

    def test_s04_horario_diurno_a_24h_no_es_traslado(self):
        """Un aeródromo diurno (11-23 UTC) que pasa a 24 h, en 500, 1.000 y 2.500 m, con el ciclo diario de SIN-20 en
        T2a (50 m) y en T2b (el de un desplazamiento vertical equivalente): ningún quiebre. H*(k) del mes del cambio
        son las 11-23 UTC en T2a y en T2b, y D en ese mes queda bajo los umbrales."""
        U = _umbrales()
        for altitud in constantes.valor("S4_ALTITUDES_M"):
            with self.subTest(altitud=altitud):
                df = _serie("horario", float(altitud))
                self.assertGreater(df.attrs["ciclo_diario_m"], 0.0)
                self.assertGreater(df.attrs["ciclo_diario_t2b_hpa"], 0.0)
                r = _k4(df)
                self.assertEqual((r.quiebres, r.ultimo_traslado, r.ultimo_barometro), ((), None, None))
                k = _mes_del_cambio(df)
                desde, hasta = df.attrs["horario_diurno_utc"]
                h, t2a, t2b = _estadisticos(df)
                for x, umbral in ((t2a, "K4_T2A_M"), (t2b, "K4_T2B_HPA")):
                    med = homogeneidad.medianas_mes_hora(h, x, None, U)
                    self.assertEqual(homogeneidad.horas_estables(med, k, U), frozenset(range(desde, hasta + 1)))
                    self.assertLess(abs(homogeneidad.salto(med, k, U)), U.a(umbral))

    def test_s04_horario_sin_h_estrella_moveria_d(self):
        """D42: sin H*(k) el cambio de horario sí movería D. Con la media de todas las medianas de cada mes
        (``_salto_sin_h_estrella``), en el mes del cambio T2a salta ≈ −25 m y T2b de + 2 a + 3 hPa: sobre los umbrales
        de §2.5 y compatibles como un traslado (|Δz_a − Δz_b| ≤ máx(10 m; 0,3·|Δz_b|), con T̄ y p̄ del registro). K4
        con ese D ve un quiebre de T2a y uno de T2b junto al cambio y retira datos (marca 1 o 16); con H*(k), ninguno.
        Con el ciclo diario en 0, la media ingenua tampoco se mueve: lo que H*(k) neutraliza es el ciclo de SIN-20."""
        U = _umbrales()
        for altitud in constantes.valor("S4_ALTITUDES_M"):
            with self.subTest(altitud=altitud):
                df = _serie("horario", float(altitud))
                k = _mes_del_cambio(df)
                h, t2a, t2b = _estadisticos(df)
                tablas = (homogeneidad._desde_tabla(homogeneidad.medianas_mes_hora(h, x, None, U)) for x in (t2a, t2b))
                d_a, d_b = (_salto_sin_h_estrella(t, k, U) for t in tablas)
                self.assertLessEqual(d_a, -U.a("K4_T2A_M"))
                self.assertGreaterEqual(d_b, U.a("K4_T2B_HPA"))
                meses = homogeneidad.mes2000(h)
                dz_b = _dz_b(df, d_b, int(meses.min()), int(meses.max()))
                self.assertLessEqual(abs(d_a - dz_b), max(U.a("K4_COINC_M"), U.a("K4_COINC_FRAC") * abs(dz_b)))
                with mock.patch.object(homogeneidad, "_salto", _salto_sin_h_estrella):
                    r = _k4(df)
                self.assertEqual(sorted(q.estadistico for q in r.quiebres), [T2A, T2B])
                self.assertTrue(all(abs(q.mes - k) <= _media_meseta() for q in r.quiebres))
                self.assertTrue(r.ultimo_traslado is not None or r.ultimo_barometro is not None)
                self.assertEqual(_k4(df).quiebres, ())                    # sin el parche: el detector de §2.5
                h0, a0, b0 = _estadisticos(_serie("horario", float(altitud), ciclo_diario_m=0.0))
                for x, umbral in ((a0, "K4_T2A_M"), (b0, "K4_T2B_HPA")):
                    t = homogeneidad._desde_tabla(homogeneidad.medianas_mes_hora(h0, x, None, U))
                    self.assertLess(abs(_salto_sin_h_estrella(t, k, U)), U.a(umbral))

    def test_s04_falsos_quiebres_en_200_series_estacionarias(self):
        """≤ 2 % con el ruido de MC-49, sobre SEMILLA + i, i = 0…199, con las altitudes en ciclo (D42): cuenta las
        series con algún quiebre de T2a o T2b (la lectura más estricta) y lo declara (``FALSOS_S4``)."""
        U = _umbrales()
        pct, n = constantes.valor("S4_FALSOS")
        altitudes = constantes.valor("S4_ALTITUDES_M")
        con_quiebre = 0
        for i in range(n):
            df = _serie("estacionaria", float(altitudes[i % len(altitudes)]), semilla=U.a("SEMILLA") + i)
            con_quiebre += bool(_k4(df).quiebres)
        self.assertLessEqual(con_quiebre * 100, pct * n)
        self.assertEqual(con_quiebre, FALSOS_S4)


class PruebasS4Tasas(unittest.TestCase):
    """D42 y D52 (HOM-14): S4 informa la tasa de cada caso sobre SEMILLA + i, i = 0…``N_SEMILLAS_S4`` − 1, en 500,
    1.000 y 2.500 m, con la regla de EMC2-1, y la declara en ``TASAS_S4``. Se mide una sola vez para la clase (1.500
    series)."""

    _medidas: dict | None = None

    @classmethod
    def _medir(cls) -> dict:
        if cls._medidas is None:
            U = _umbrales()
            medidas = {}
            for caso in TASAS_S4:
                for altitud in constantes.valor("S4_ALTITUDES_M"):
                    aciertos = traslados = 0
                    for i in range(N_SEMILLAS_S4):
                        df = _serie_s4(caso, altitud, U.a("SEMILLA") + i)
                        r = _k4(df)
                        aciertos += _acierto_s4(caso, r, _mes_del_cambio(df))
                        traslados += r.ultimo_traslado is not None
                    medidas[caso, int(altitud)] = (aciertos, traslados)
            cls._medidas = medidas
        return cls._medidas

    def test_s04_tasas_declaradas(self):
        """Las tasas medidas (aciertos de ``N_SEMILLAS_S4`` por caso y altitud) son las declaradas en ``TASAS_S4``."""
        altitudes = sorted(int(a) for a in constantes.valor("S4_ALTITUDES_M"))
        self.assertTrue(all(sorted(fila) == altitudes for fila in TASAS_S4.values()))
        medidas = self._medir()
        self.assertEqual({caso: {a: medidas[caso, a][0] for a in altitudes} for caso in TASAS_S4}, TASAS_S4)

    def test_s04_ningun_traslado_fuera_de_los_traslados(self):
        """«uno de 5 m, no»; el barómetro, «no traslado»; reducción y horario, «no se declaran traslado» (§9): en todas
        las series del conjunto, la lectura más estricta del criterio sobre la tasa."""
        medidas = self._medir()
        for caso in ("traslado_5", "barometro", "reduccion", "horario"):
            for altitud in constantes.valor("S4_ALTITUDES_M"):
                with self.subTest(caso=caso, altitud=altitud):
                    self.assertEqual(medidas[caso, int(altitud)][1], 0)


class PruebasHomogeneidad(unittest.TestCase):
    def test_valores_que_suponen_las_pruebas_son_los_del_anexo_a(self):
        U = _umbrales()
        self.assertEqual({k: U.a(k) for k in VALORES_ANEXO_A}, VALORES_ANEXO_A)

    def test_formulas_de_2_5_que_suponen_las_pruebas(self):
        """Los números de §2.5 que las pruebas escriben a mano son los de ``constantes`` (verificados contra el
        texto en ``test_constantes``)."""
        self.assertEqual(constantes.valor("Z_IMPLICITA"), (_Z_IMPL, _KELVIN, _GAMMA_TBAR))
        self.assertEqual(constantes.valor("Z_IMPLICITA_DIVISOR"), 2)
        self.assertEqual((constantes.valor("R_SECO"), constantes.valor("GRAVEDAD")), (_R_SECO, _GRAVEDAD))

    def test_horas_estables_en_dos_pasos_mc06(self):
        """MC-06: meses candidatos, H*(k) y meses válidos."""
        U = _umbrales()
        k = 12
        filas: dict[int, tuple[int, dict[int, float]]] = {}
        for m in range(0, 3):                       # antes, sin 100 pares: no son candidatos (ni cuentan en el 80 %)
            filas[m] = (50, {x: 100.0 for x in range(0, 6)})
        for m in range(3, 12):                      # antes: 9 candidatos con 11-23 h; 0-10 h sólo en 6 de 9
            horas = set(range(11, 24)) | (set(range(0, 11)) if m < 9 else set())
            if m == 3:
                horas.discard(20)                   # la 20 en 8 de 9 (89 %): estable; con 12 meses serían 8/12
            filas[m] = (500, {x: 1.0 + 0.01 * m for x in horas})
        for m in range(12, 24):                     # después: 12 candidatos con 24 h; fuera de H* valen 1.000
            valores = {x: (1000.0 if x < 11 else 3.0 + 0.01 * (m - 14)) for x in range(24)}
            if m in (12, 13):
                del valores[15]                     # la 15 en 10 de 12 (83 %): estable; estos dos meses no son válidos
                valores.update({x: 50.0 for x in valores if x >= 11})
            filas[m] = (600, valores)
        med = _medianas_a_mano(filas)
        self.assertEqual(homogeneidad.horas_estables(med, k, U), frozenset(range(11, 24)))
        # Válidos: antes 4…11 (el 3 no tiene la 20), después 14…23. D = mediana(3,00…3,09) − mediana(1,04…1,11).
        self.assertAlmostEqual(homogeneidad.salto(med, k, U), 3.045 - 1.075, places=12)
        # Con menos de 6 válidos de un lado, D no se define.
        menos = med.copy()
        menos.loc[4:7, homogeneidad.COLUMNA_PARES] = 50
        self.assertIsNone(homogeneidad.salto(menos, k, U))
        # Un lado sin candidatos deja H*(k) vacío y D sin definir.
        sin_lado = med.copy()
        sin_lado.loc[0:11, homogeneidad.COLUMNA_PARES] = 0
        self.assertEqual(homogeneidad.horas_estables(sin_lado, k, U), frozenset())
        self.assertIsNone(homogeneidad.salto(sin_lado, k, U))

    def test_medianas_mes_hora(self):
        """≥ 5 valores por mes y hora; mediana de un número par = media de los centrales; pares; validos; meses
        consecutivos (HOM-2)."""
        U = _umbrales()
        h, x, ok = [], [], []
        for dia, v in enumerate([1.0, 2.0, 3.0, 4.0, 10.0]):          # enero de 2000, 0 h: mediana 3
            h.append(dia * 24); x.append(v); ok.append(True)
        h.append(5 * 24); x.append(-50.0); ok.append(False)            # inválida: no cuenta
        for dia, v in enumerate([1.0, 2.0, 3.0, 4.0]):                # 1 h: sólo 4 valores, sin mediana
            h.append(dia * 24 + 1); x.append(v); ok.append(True)
        for dia, v in enumerate([6.0, 1.0, 5.0, 2.0, 4.0, 3.0]):      # 2 h: 6 valores, mediana 3,5
            h.append(dia * 24 + 2); x.append(v); ok.append(True)
        h.append(_h("2000-03-01T07")); x.append(float("nan")); ok.append(True)
        h.append(_h("2000-03-02T07")); x.append(7.0); ok.append(True)
        orden = np.argsort(h)
        med = homogeneidad.medianas_mes_hora(np.array(h)[orden], np.array(x)[orden], np.array(ok)[orden], U)
        self.assertEqual(list(med.index), [0, 1, 2])
        self.assertEqual(list(med.columns), [homogeneidad.COLUMNA_PARES, *homogeneidad.COLUMNAS_HORA])
        self.assertEqual(med[homogeneidad.COLUMNA_PARES].tolist(), [15, 0, 1])
        self.assertEqual(med.loc[0, "h00"], 3.0)
        self.assertTrue(np.isnan(med.loc[0, "h01"]))
        self.assertEqual(med.loc[0, "h02"], 3.5)
        self.assertTrue(np.isnan(med.loc[2, "h07"]))
        with self.assertRaises(TypeError):
            homogeneidad.medianas_mes_hora(np.array([0.0]), np.array([1.0]), None, U)
        with self.assertRaises(ValueError):
            homogeneidad.medianas_mes_hora(np.array([0]), np.array([1.0, 2.0]), None, U)

    def test_medianas_mes_hora_sin_horas_repetidas(self):
        """HOM-2: h creciente y sin repetir, como en k4 y tramos_homogeneos. Cinco veces la hora 0 con 1…5 darían 5
        pares y una mediana de 3,0 a las 00 UTC con una sola hora real."""
        U = _umbrales()
        with self.assertRaisesRegex(ValueError, "sin repetir"):
            homogeneidad.medianas_mes_hora(np.zeros(5, dtype=np.int64), np.arange(1.0, 6.0), None, U)
        with self.assertRaisesRegex(ValueError, "sin repetir"):       # repetida aunque sea inválida
            homogeneidad.medianas_mes_hora(np.array([0, 24, 24]), np.array([1.0, 2.0, 3.0]),
                                           np.array([True, True, False]), U)
        with self.assertRaisesRegex(ValueError, "creciente"):
            homogeneidad.medianas_mes_hora(np.array([24, 0]), np.array([1.0, 2.0]), None, U)
        med = homogeneidad.medianas_mes_hora(np.arange(5, dtype=np.int64) * 24, np.arange(1.0, 6.0), None, U)
        self.assertEqual((int(med.loc[0, homogeneidad.COLUMNA_PARES]), float(med.loc[0, "h00"])), (5, 3.0))

    def test_mes2000_es_el_de_a4(self):
        """HOM-1: el mes2000 de la hora UTC es el de la fórmula de A4 (con años bisiestos y los bordes de mes)."""
        h = np.concatenate([np.arange(-48, 24 * 366 * 27, 37), [_h("2000-02-29T23"), _h("2000-03-01T00"),
                                                                 _h("2024-12-31T23"), _h("2025-01-01T00")]])
        a4 = (np.datetime64("2000-01-01T00", "h") + h).astype("datetime64[M]").astype(np.int64) - 360
        self.assertEqual(homogeneidad.mes2000(h).tolist(), a4.tolist())
        self.assertEqual(homogeneidad.mes2000(np.array([_h("2015-01-01T00")])).tolist(), [180])
        self.assertEqual(homogeneidad.hora_utc(np.array([-1, 0, 25])).tolist(), [23, 0, 1])

    def test_segmentacion_binaria_hasta_3_quiebres(self):
        """Tramos de ≥ 12 meses, hasta 3 quiebres: de cuatro escalones limpios (3, −2, 1,5 y 1 K, cada 18 meses)
        entran los tres mayores, cada uno en su mes (el central de la meseta, HOM-5)."""
        U = _umbrales()
        h = _horas("2000-01-01T00", "2008-01-01T00")                 # 96 meses
        r = _escalones(h, [18, 36, 54, 72], [0.0, 3.0, 1.0, 2.5, 3.5])
        med = homogeneidad.medianas_mes_hora(h, r, None, U)
        quiebres = homogeneidad.segmentar(med, U.a("HOM_T"), U)
        self.assertEqual(quiebres, [(18, 3.0), (36, -2.0), (54, 1.5)])
        tramos = homogeneidad.tramos_homogeneos(h, r, "T", U)
        self.assertEqual(tramos, [(0, 17), (18, 35), (36, 53), (54, 95)])
        self.assertTrue(all(b - a + 1 >= U.a("K4_TRAMO_MIN") for a, b in tramos))
        # Con un umbral mayor que el escalón, ninguno; con un registro de < 24 meses no hay corte posible.
        self.assertEqual(homogeneidad.segmentar(med, 3.5, U), [])
        corto = _horas("2000-01-01T00", "2001-11-01T00")              # 22 meses
        self.assertEqual(homogeneidad.tramos_homogeneos(corto, _escalones(corto, [11], [0.0, 5.0]), "T", U),
                         [(0, 21)])

    def test_empate_en_la_meseta_toma_el_central(self):
        """HOM-5: un escalón limpio en el mes 30 da |D| igual en 25…35; se toma el central, 30. Con un número par
        de empatados, el más tardío de los dos centrales."""
        U = _umbrales()
        h = _horas("2000-01-01T00", "2005-01-01T00")                 # 60 meses
        med = homogeneidad.medianas_mes_hora(h, _escalones(h, [30], [0.0, 2.0]), None, U)
        meseta = [k for k in range(12, 49) if homogeneidad.salto(med, k, U) == 2.0]
        self.assertEqual(meseta, list(range(30 - _media_meseta(), 30 + _media_meseta() + 1)))
        self.assertEqual(homogeneidad.segmentar(med, U.a("HOM_T"), U), [(30, 2.0)])
        self.assertEqual(homogeneidad._k_del_maximo([4, 5, 6, 7], [1.0, -1.0, 1.0, 1.0]), (6, 1.0))   # par
        self.assertEqual(homogeneidad._k_del_maximo([4, 5, 6], [-1.0, 1.0, 1.0]), (5, 1.0))           # impar
        self.assertEqual(homogeneidad._k_del_maximo([4, 5, 6, 7], [1.0, 2.0, 1.0, 0.5]), (5, 2.0))
        self.assertIsNone(homogeneidad._k_del_maximo([], []))

    def test_empate_en_los_bordes_del_tramo(self):
        """D39 (HOM-5, justificación corregida): constancia de los bordes del tramo. En el tramo 0…59 los cortes
        admisibles son 12…48 (HOM-4), y la meseta de un escalón limpio en k0, k0 − 5 … k0 + 5, queda recortada a ellos:
        cerca de los bordes el central de lo que queda no es k0 (ni lo serían el primero ni el último). Para cada
        k0 = 1…59, con un escalón de 2 en una sola hora UTC:
        - k0 = 17…44: el corte cae en k0 (la meseta entera cabe; la asimetría es la del más tardío de los dos
          centrales);
        - k0 = 7…16: de 5 a 1 meses tarde (7 → 12, 16 → 17); k0 = 45…53: de 1 a 5 meses antes (45 → 44, 53 → 48);
        - k0 = 6 o 54 (6 meses de un nivel): en el primer o el último corte admisible, con la mitad del escalón;
        - k0 ≤ 5 o ≥ 55: D(k) = 0 en todos los cortes admisibles y no hay quiebre.
        Y dos mesetas que empatan exactamente (escalones iguales en 24 y 48 de un tramo 0…71) dan el central de todas
        sus posiciones, 43, el borde de la segunda; el paso siguiente pone el otro en 24 (D39: «como HOM-5»)."""
        U = _umbrales()
        n, s = 60, 2.0
        a, b = 0, n - 1
        primero, ultimo = a + U.a("K4_TRAMO_MIN"), b - U.a("K4_TRAMO_MIN") + 1
        w = _media_meseta()
        self.assertEqual((primero, ultimo, w), (12, 48, 5))
        obtenido = {}
        for k0 in range(a + 1, b + 1):
            obtenido[k0] = homogeneidad.segmentar(_una_hora([0.0] * (k0 - a) + [s] * (b - k0 + 1)), U.a("HOM_T"), U)
            lo, hi = max(k0 - w, primero), min(k0 + w, ultimo)
            if lo <= hi:
                esperado = [(lo + (hi - lo + 1) // 2, s)]           # el central de la meseta recortada (D39)
            elif k0 - a == w + 1:
                esperado = [(primero, s / 2)]
            elif b - k0 + 1 == w + 1:
                esperado = [(ultimo, s / 2)]
            else:
                esperado = []
            with self.subTest(k0=k0):
                self.assertEqual(obtenido[k0], esperado)
        self.assertEqual([k0 for k0, q in obtenido.items() if q == [(k0, s)]], list(range(17, 45)))
        self.assertEqual({k0: obtenido[k0] for k0 in (5, 6, 7, 16, 17, 44, 45, 53, 54, 55)},
                         {5: [], 6: [(12, 1.0)], 7: [(12, 2.0)], 16: [(17, 2.0)], 17: [(17, 2.0)], 44: [(44, 2.0)],
                          45: [(44, 2.0)], 53: [(48, 2.0)], 54: [(48, 1.0)], 55: []})
        # Dos mesetas separadas que empatan: el central de las 22 posiciones (43) y, en el paso siguiente, 24.
        dos = _una_hora([0.0] * 24 + [s] * 24 + [2 * s] * 24)
        self.assertEqual([k for k in range(12, 61) if homogeneidad.salto(dos, k, U) == s],
                         [*range(19, 30), *range(43, 54)])
        quiebres = homogeneidad._segmentar(homogeneidad._desde_tabla(dos), U.a("HOM_T"), U)
        self.assertEqual([(k, d) for k, d, _, _ in quiebres], [(43, s), (24, s)])

    def test_desplazamientos_sin_quiebres_es_cero(self):
        """Sin quiebres, δ = 0 (exacto); con dos tramos limpios, δ lleva cada tramo a la mediana de todo el
        registro; sin horas estables comunes, δ = NaN (HOM-11)."""
        U = _umbrales()
        h = _horas("2010-01-01T00", "2014-01-01T00")
        r = _verdad_s5(h, U.a("SEMILLA"))
        tramos = homogeneidad.tramos_homogeneos(h, r, "T", U)
        self.assertEqual(len(tramos), 1)
        self.assertEqual(homogeneidad.desplazamientos(h, r, tramos, U), {0: 0.0})
        self.assertEqual(homogeneidad.desplazamientos(h, r, [], U), {})
        # Dos tramos de 12 meses (2002 y 2003, de 365 días) en 0 y 1: la mediana del registro a cada hora es 0,5
        # (número par de valores), así que δ = −0,5 y +0,5.
        h2 = _horas("2002-01-01T00", "2004-01-01T00")
        m0 = int(homogeneidad.mes2000(h2[:1])[0])
        tramos2 = [(m0, m0 + 11), (m0 + 12, m0 + 23)]
        r2 = _escalones(h2, [m0 + 12], [0.0, 1.0])
        self.assertEqual(homogeneidad.desplazamientos(h2, r2, tramos2, U), {0: -0.5, 1: 0.5})
        # Tramo 0 sólo de 0-11 UTC y tramo 1 sólo de 12-23 UTC: H*_δ vacío.
        hora = homogeneidad.hora_utc(h2)
        meses = homogeneidad.mes2000(h2)
        r3 = np.where(((meses < m0 + 12) & (hora < 12)) | ((meses >= m0 + 12) & (hora >= 12)), r2, np.nan)
        d3 = homogeneidad.desplazamientos(h2, r3, tramos2, U)
        self.assertEqual(sorted(d3), [0, 1])
        self.assertTrue(all(np.isnan(v) for v in d3.values()))
        with self.assertRaises(ValueError):                          # tramos que no son contiguos
            homogeneidad.desplazamientos(h2, r2, [(m0, m0 + 10), (m0 + 12, m0 + 23)], U)

    def test_s05_cambio_de_sensor_de_1_k_es_un_tramo(self):
        """S5: un cambio de sensor sintético de 1 K se detecta como tramo, en la meseta de su mes, y después de
        restar δ el residuo ya no tiene quiebre (r̃ sin el escalón). Verdad con las anomalías de MC-50 y la semilla
        del protocolo (D42, HOM-13); sin el cambio, el mismo residuo es un solo tramo."""
        U = _umbrales()
        h = _horas("2010-01-01T00", "2016-01-01T00")
        r = _verdad_s5(h, U.a("SEMILLA"))
        self.assertEqual(len(homogeneidad.tramos_homogeneos(h, r, "T", U)), 1)
        for cambio in CAMBIOS_S5:
            with self.subTest(cambio=cambio):
                c = _cambio_de_sensor(h, r, cambio, U)
                self.assertEqual(len(c["tramos"]), 2)
                self.assertLessEqual(abs(c["tramos"][1][0] - c["k0"]), _media_meseta())
                self.assertAlmostEqual(c["d"][1] - c["d"][0], constantes.valor("S5_SENSOR_K"), delta=0.2)
                self.assertEqual(len(c["tramos_rt"]), 1)
                self.assertTrue(c["recuperado"])

    def test_informativa_s5_sin_media_cero(self):
        """D42 (HOM-13): prueba informativa, que no decide S5. Sobre SEMILLA + i, i = 0…``N_SEMILLAS_S5`` − 1, con las
        anomalías de MC-50 y con las mismas sin la media 0 por mes × año (``{"media_cero": False}``), cuenta los
        residuos estacionarios con un tramo falso (0,5 K) y los cambios de sensor de 1 K recuperados
        (``_cambio_de_sensor``, en las dos fechas de ``CAMBIOS_S5``), y los declara en ``INFORMATIVA_S5``: sin la media
        0, 14 de 20 falsos y 9 de 40 recuperados; con ella, 0 de 20 y 40 de 40. Es la razón de MC-50: sin la media 0,
        la prueba mediría el ruido de muestreo de cada mes y no el detector."""
        U = _umbrales()
        h = _horas("2010-01-01T00", "2016-01-01T00")
        medido = {}
        for nombre, anomalias in (("MC-50", "MC-50"), ("sin_media_cero", {"media_cero": False})):
            falsos = recuperados = 0
            for i in range(N_SEMILLAS_S5):
                r = _verdad_s5(h, U.a("SEMILLA") + i, anomalias)
                falsos += len(homogeneidad.tramos_homogeneos(h, r, "T", U)) > 1
                recuperados += sum(_cambio_de_sensor(h, r, cambio, U)["recuperado"] for cambio in CAMBIOS_S5)
            medido[nombre] = {"falsos": falsos, "sensor": recuperados}
        self.assertEqual(medido, INFORMATIVA_S5)

    def test_tramos_solo_t_y_td(self):
        """§4.8: «Viento y presión no se segmentan»; Td usa 1,0 K; sin residuo válido no hay tramos."""
        U = _umbrales()
        h = _horas("2000-01-01T00", "2005-01-01T00")
        r = _escalones(h, [30], [0.0, 0.8])                           # 0,8 K: tramo en T (0,5), no en Td (1,0)
        self.assertEqual(len(homogeneidad.tramos_homogeneos(h, r, "T", U)), 2)
        self.assertEqual(len(homogeneidad.tramos_homogeneos(h, r, "Td", U)), 1)
        for variable in ("u", "v", "p", "HR", "x"):
            with self.subTest(variable=variable), self.assertRaises(ValueError):
                homogeneidad.tramos_homogeneos(h, r, variable, U)
        self.assertEqual(homogeneidad.tramos_homogeneos(h, np.full(len(h), np.nan), "T", U), [])
        with self.assertRaises(ValueError):                          # h con horas repetidas
            homogeneidad.tramos_homogeneos(np.r_[h[:1], h], np.r_[r[:1], r], "T", U)


class PruebasK4(unittest.TestCase):
    """Clasificación de §2.5 y la interfaz A4, con series de ``sintetico.series_traslado`` cambiadas a mano."""

    def test_t2a_sin_t2b_es_cambio_del_metodo_de_reduccion(self):
        """QFF sube como si z_impl subiera 20 m y QFE no cambia: sólo un quiebre de T2a, «método de reducción»."""
        df = _serie("estacionaria", 1000.0)
        despues = df["h"] >= df.attrs["cambio_h"]
        tbar = df["Ts"] + 273.15 + 0.0065 * df.attrs["z_cat"] / 2
        df.loc[despues, "QFF"] = df.loc[despues, "QFF"] * np.exp(20.0 / (29.27 * tbar[despues]))
        r = _k4(df)
        self.assertEqual([(q.estadistico, q.clase) for q in r.quiebres],
                         [(Estadistico.T2A.value, ClaseQuiebre.METODO_REDUCCION)])
        self.assertIsNone(r.ultimo_traslado)
        self.assertIsNone(r.ultimo_barometro)

    def test_t2a_incompatible_con_t2b_es_barometro(self):
        """Barómetro de +1,5 hPa (Δz_b ≈ −13 m) y, a la vez, z_impl +40 m: no son compatibles → barómetro, y el de
        T2a, con T2b cerca, va sin clase."""
        df = _serie("barometro", 500.0)
        despues = df["h"] >= df.attrs["cambio_h"]
        tbar = df["Ts"] + 273.15 + 0.0065 * df.attrs["z_cat"] / 2
        df.loc[despues, "QFF"] = df.loc[despues, "QFF"] * np.exp(40.0 / (29.27 * tbar[despues]))
        r = _k4(df)
        t2a = [q for q in r.quiebres if q.estadistico == Estadistico.T2A]
        t2b = [q for q in r.quiebres if q.estadistico == Estadistico.T2B]
        self.assertEqual([q.clase for q in t2b], [ClaseQuiebre.BAROMETRO])
        self.assertEqual(len(t2a), 1)
        self.assertGreater(t2a[0].D, 30.0)
        cerca = abs(t2a[0].mes - t2b[0].mes) <= _umbrales().a("K4_COINC_MESES")
        self.assertIs(t2a[0].clase, None if cerca else ClaseQuiebre.METODO_REDUCCION)
        self.assertIsNone(r.ultimo_traslado)
        self.assertEqual(r.ultimo_barometro, t2b[0].mes)

    def test_sin_qff_un_traslado_es_barometro(self):
        """Límite declarado de §2.5: sin QFF, un traslado real se trata como inhomogeneidad del barómetro."""
        df = _serie("traslado", 500.0)
        df["QFF"] = np.nan
        r = _k4(df)
        self.assertIsNone(r.ultimo_traslado)
        self.assertIsNotNone(r.ultimo_barometro)
        self.assertEqual([q.estadistico for q in r.quiebres], [Estadistico.T2B.value])

    def test_sin_z_cat_no_hay_t2a(self):
        """Sin z_cat legible no hay T̄ ni T2a: un traslado queda como barómetro (HOM-6, HOM-7)."""
        df = _serie("traslado", 500.0)
        df.attrs["z_cat"] = float("nan")
        r = _k4(df)
        self.assertEqual([(q.estadistico, q.clase) for q in r.quiebres],
                         [(Estadistico.T2B.value, ClaseQuiebre.BAROMETRO)])

    def test_sin_presion_no_hay_prueba(self):
        """Sin QFE válida: marca 21 (``sin_prueba``), sin quiebres."""
        df = _serie("traslado", 500.0)
        df["QFE"] = np.nan
        r = _k4(df)
        self.assertTrue(r.sin_prueba)
        self.assertEqual((r.quiebres, r.ultimo_traslado, r.ultimo_barometro), ((), None, None))

    def test_entrada_a4(self):
        """h creciente y sin repetir, p_F alineado, columnas de A4; las demás columnas se ignoran; float32 (A1) da la
        misma clasificación; la misma entrada da el mismo resultado (determinismo)."""
        U = _umbrales()
        df = _serie("traslado", 500.0)
        base = _k4(df)
        self.assertEqual(_k4(df), base)
        con_mas = df.assign(Td=1.0, marcas_QFE=np.uint32(0))
        self.assertEqual(homogeneidad.k4(con_mas, df["p_F"].to_numpy(), df.attrs["z_cat"], U, codigo="330020"), base)
        f4 = df.astype({"Ts": "float32", "QFE": "float32", "QFF": "float32"})
        r4 = homogeneidad.k4(f4[["h", "Ts", "QFE", "QFF"]], df["p_F"].astype("float32").to_numpy(),
                             df.attrs["z_cat"], U, codigo="330020")
        self.assertEqual([(q.estadistico, q.clase) for q in r4.quiebres],
                         [(q.estadistico, q.clase) for q in base.quiebres])
        self.assertEqual(r4.codigo, "330020")
        with self.assertRaises(ValueError):
            homogeneidad.k4(df.iloc[::-1], df["p_F"].to_numpy()[::-1], df.attrs["z_cat"], U, codigo="330020")
        with self.assertRaises(ValueError):
            homogeneidad.k4(df, df["p_F"].to_numpy()[1:], df.attrs["z_cat"], U, codigo="330020")
        with self.assertRaises(ValueError):
            homogeneidad.k4(df.drop(columns=["QFF"]), df["p_F"].to_numpy(), df.attrs["z_cat"], U, codigo="330020")
        self.assertEqual([q.mes for q in base.quiebres], sorted(q.mes for q in base.quiebres))

    def test_codigo_obligatorio(self):
        """HOM-9: ``codigo`` es de palabra clave, obligatorio y sin valor por omisión; vacío o en blanco es
        ValueError y no texto, TypeError. Un ResultadoK4 sin código no se casaría con su estación (A5)."""
        U = _umbrales()
        df = _serie_k4(24)
        tabla, pf, z = df[["h", "Ts", "QFE", "QFF"]], df["p_F"].to_numpy(), df.attrs["z_cat"]
        with self.assertRaises(TypeError):                           # como dice hoy A4, sin el código
            homogeneidad.k4(tabla, pf, z, U)
        with self.assertRaises(TypeError):                           # no va por posición
            homogeneidad.k4(tabla, pf, z, U, "330020")
        for vacio in ("", "   "):
            with self.subTest(codigo=vacio), self.assertRaises(ValueError):
                homogeneidad.k4(tabla, pf, z, U, codigo=vacio)
        with self.assertRaises(TypeError):
            homogeneidad.k4(tabla, pf, z, U, codigo=330020)
        self.assertEqual(homogeneidad.k4(tabla, pf, z, U, codigo="330020").codigo, "330020")
        sin_qfe = tabla.assign(QFE=np.nan)                           # también con sin_prueba
        self.assertEqual(homogeneidad.k4(sin_qfe, pf, z, U, codigo="330020").codigo, "330020")
        with self.assertRaises(ValueError):
            homogeneidad.k4(sin_qfe, pf, z, U, codigo="")


class PruebasBordesK4(unittest.TestCase):
    """Bordes de la clasificación de §2.5 con series de K4 hechas a mano y sin ruido (``_serie_k4``)."""

    def test_coincidencia_a_5_meses_si_y_a_6_no(self):
        """EMC2-1 (D52; antes ``test_coincidencia_a_3_meses_si_y_a_4_no``, la regla literal del v2.2): es traslado si el
        D(k) de T2a en el mes del quiebre de T2b (36) es compatible, y sin ruido eso vale mientras el salto de z_impl
        quede en la meseta de ese mes, a ≤ 5 meses (HOM-5); el T2a va entonces sin clase, también a 4 y 5 meses, porque
        el D(k) de T2b en su mes es el salto entero. A 6 meses el D(k) de T2a en el mes 36 es la mitad del salto:
        barómetro, y el T2a sigue sin clase porque el D(k) de T2b en su mes es la mitad de −5 hPa (≥ 1,2 hPa). A 7 meses,
        barómetro y «cambio del método de reducción». Con la regla literal, ±3 era traslado y ±4 barómetro. Fija también
        el mes: con k_b ± 1, a −5 o a +5 el D(k) de T2a ya sería la mitad del salto."""
        U = _umbrales()
        w = _media_meseta()
        self.assertEqual(w, 5)
        d_qfe = -5.0
        base = {"saltos_qfe": ((36, d_qfe),)}
        dz_b = _dz_b(_serie_k4(72, **base), d_qfe, 0, 71)
        for desfase in (-(w + 2), -(w + 1), -w, -(w - 1), -U.a("K4_COINC_MESES"), 0, U.a("K4_COINC_MESES"), w - 1, w,
                        w + 1, w + 2):
            with self.subTest(desfase=desfase):
                r = _k4(_serie_k4(72, **base, saltos_z=((36 + desfase, dz_b),)))
                en_meseta = abs(desfase) <= w
                t2a = (T2A, 36 + desfase, None if abs(desfase) <= w + 1 else REDUCCION)
                t2b = (T2B, 36, TRASLADO if en_meseta else BAROMETRO)
                self.assertEqual(_clases(r), [t2a, t2b] if desfase <= 0 else [t2b, t2a])
                self.assertEqual((r.ultimo_traslado, r.ultimo_barometro), (36, None) if en_meseta else (None, 36))
        h, _, t2b = _estadisticos(_serie_k4(72, **base))   # el D(k) de T2b en el mes del T2a a 6 y a 7 meses
        med = homogeneidad.medianas_mes_hora(h, t2b, None, U)
        self.assertAlmostEqual(homogeneidad.salto(med, 36 + w + 1, U), d_qfe / 2, delta=1e-9)
        self.assertAlmostEqual(homogeneidad.salto(med, 36 + w + 2, U), 0.0, delta=1e-9)

    def test_traslado_exige_d_de_t2a_de_10_m_en_el_mes_del_quiebre(self):
        """EMC2-1: «cumple |D(k)| ≥ 10 m», inclusivo. Un traslado de 15 m en QFE (Δz_b ≈ 15 m) con un salto de z_impl
        de 9 m en el mismo mes es compatible (|9 − 15| ≤ 10 m) pero no llega a 10 m: barómetro, y no hay quiebre de
        T2a. Con 10,001 m, traslado (y un quiebre de T2a sin clase); con 9,999 m, barómetro."""
        p0 = 900.0
        d_qfe = _dqfe_traslado(15.0, p0)
        for dz_a, clases in ((9.0, [(T2B, 36, BAROMETRO)]), (9.999, [(T2B, 36, BAROMETRO)]),
                             (10.001, [(T2A, 36, None), (T2B, 36, TRASLADO)])):
            with self.subTest(dz_a=dz_a):
                df = _serie_k4(72, p0=p0, saltos_qfe=((36, d_qfe),), saltos_z=((36, dz_a),))
                dz_b = _dz_b(df, d_qfe, 0, 71)
                self.assertLessEqual(abs(dz_a - dz_b), _umbrales().a("K4_COINC_M"))      # compatibles
                r = _k4(df)
                self.assertEqual(_clases(r), clases)
                self.assertEqual(r.ultimo_traslado, 36 if dz_a > 10 else None)

    def test_t2a_con_quiebre_de_t2b_cerca_va_sin_clase_aunque_su_d_no_se_defina(self):
        """EMC2-1, regla de T2a: «sin T2b» exige las dos cosas, ningún quiebre de T2b a ≤ 3 meses y, en el mes del de
        T2a, un D(k) de T2b que no se define o no llega a 1,2 hPa. Barómetro de +3 hPa en el mes 36 (y −1 hPa en el 48)
        y T2b sin fondo en los meses 40…47: el quiebre de T2b cae en el 34 (barómetro; el D de T2b no se define en
        35…41). Con z_impl + 20 m en el 36, el 37 o el 38, el quiebre de T2a cae en ese mes, a 2, 3 o 4 meses del de T2b,
        y en su mes el D de T2b no se define. A 2 y 3 meses el quiebre de T2b está cerca y el de T2a va sin clase; a 4,
        es «cambio del método de reducción»."""
        U = _umbrales()
        c = U.a("K4_COINC_MESES")
        for k_a in (34 + c - 1, 34 + c, 34 + c + 1):
            with self.subTest(meses=k_a - 34):
                df = _serie_k4(72, saltos_qfe=((36, 3.0), (48, -1.0)), saltos_z=((k_a, 20.0),))
                mes = homogeneidad.mes2000(df["h"].to_numpy())
                df.loc[(mes >= 40) & (mes <= 47), "p_F"] = np.nan
                r = _k4(df)
                self.assertEqual(_clases(r), [(T2B, 34, BAROMETRO), (T2A, k_a, None if k_a - 34 <= c else REDUCCION)])
                self.assertEqual((r.ultimo_traslado, r.ultimo_barometro), (None, 34))
                h, _, t2b = _estadisticos(df)
                self.assertIsNone(homogeneidad.salto(homogeneidad.medianas_mes_hora(h, t2b, None, U), k_a, U))

    def test_d_de_t2b_que_no_se_define_sin_quiebre_cerca_es_metodo_de_reduccion(self):
        """EMC2-1, regla de T2a: «no se define» cuenta como sin T2b. z_impl + 20 m en el mes 36, QFE sin saltos y T2b
        sin fondo en los meses 30…42: no hay ningún quiebre de T2b y el D de T2b del mes 36 no se define (5 meses
        válidos después): el quiebre de T2a es «cambio del método de reducción»."""
        U = _umbrales()
        df = _serie_k4(72, saltos_z=((36, 20.0),))
        mes = homogeneidad.mes2000(df["h"].to_numpy())
        df.loc[(mes >= 30) & (mes <= 42), "p_F"] = np.nan
        r = _k4(df)
        self.assertEqual(_clases(r), [(T2A, 36, REDUCCION)])
        h, _, t2b = _estadisticos(df)
        self.assertIsNone(homogeneidad.salto(homogeneidad.medianas_mes_hora(h, t2b, None, U), 36, U))

    def test_d_de_t2b_en_el_mes_del_t2a_a_1_21_y_1_19_hpa(self):
        """EMC2-1, regla de T2a, a 6 meses: barómetro de +2,42 o +2,38 hPa en el mes 36 y z_impl + 20 m en el 42. El
        quiebre de T2a cae en el 42, sin quiebre de T2b a ≤ 3 meses, y en su mes el D de T2b es la mitad del salto:
        1,21 hPa (llega a 1,2: sin clase) o 1,19 hPa (no llega: «cambio del método de reducción»)."""
        U = _umbrales()
        for paso, d_b, clase in ((2.42, 1.21, None), (2.38, 1.19, REDUCCION)):
            with self.subTest(paso=paso):
                df = _serie_k4(72, saltos_qfe=((36, paso),), saltos_z=((42, 20.0),))
                h, _, t2b = _estadisticos(df)
                self.assertAlmostEqual(homogeneidad.salto(homogeneidad.medianas_mes_hora(h, t2b, None, U), 42, U), d_b,
                                       delta=1e-9)
                self.assertEqual(_clases(_k4(df)), [(T2B, 36, BAROMETRO), (T2A, 42, clase)])

    def test_umbrales_inclusivos_con_d_exactos(self):
        """EMC2-1: «|D(k)| ≥ 10 m» y «|D(k)| < 1,2 hPa», con un D exactamente igual al umbral en float64 (fabricado sin
        ruido; la prueba exige primero que el D sea exacto).
        - T2b: con 8 horas UTC por día (cada 3 h, para que las medias de las medianas sean exactas), p_F = 0, QFE de
          0,5 hPa que sube 1,2 hPa en el mes 36 y z_impl + 20 m en el 41: el D de T2b en el 41 es 1,2 exacto, así que el
          de T2a (a 5 meses del de T2b) va sin clase, no «cambio del método de reducción».
        - T2a: con 24 horas, ΔQFE = −1,5 hPa (Δz_b ≈ 14 m) y z_impl + (10 − 2⁻⁴³) m en el mes 36, el D de T2a en el 36
          es 10 m exacto (hallado probando los saltos vecinos de 10 m): traslado."""
        U = _umbrales()
        df = _serie_k4(72, p0=0.5, saltos_qfe=((36, U.a("K4_T2B_HPA")),), saltos_z=((41, 20.0),))
        df = df[(df["h"] % 3 == 0).to_numpy()].reset_index(drop=True)
        df["p_F"] = 0.0
        df.attrs["z_cat"] = 1000.0
        h, _, t2b = _estadisticos(df)
        self.assertEqual(homogeneidad.salto(homogeneidad.medianas_mes_hora(h, t2b, None, U), 41, U), U.a("K4_T2B_HPA"))
        self.assertEqual(_clases(_k4(df)), [(T2B, 36, BAROMETRO), (T2A, 41, None)])
        df = _serie_k4(72, saltos_qfe=((36, -1.5),), saltos_z=((36, 10.0 - 2.0 ** -43),))
        h, t2a, _ = _estadisticos(df)
        self.assertEqual(homogeneidad.salto(homogeneidad.medianas_mes_hora(h, t2a, None, U), 36, U), U.a("K4_T2A_M"))
        r = _k4(df)
        self.assertEqual(_clases(r), [(T2A, 36, None), (T2B, 36, TRASLADO)])
        self.assertEqual(r.quiebres[0].D, U.a("K4_T2A_M"))

    def test_tolerancia_max_10_m_y_30_por_ciento(self):
        """|Δz_a − Δz_b| ≤ máx(10 m; 0,3·|Δz_b|), inclusivo, con T̄ (con 0,0065·z_cat/2) y p̄ medias del tramo que el
        quiebre partió (HOM-7). Un barómetro de +30 hPa en el mes 24 se detecta primero y deja el quiebre del mes 48
        en el tramo 24…71, cuyo p̄ difiere del de todo el registro en ≈ 1 %. Δz_a va a 0,01 m de cada borde, por
        dentro y por fuera: con ΔQFE = ∓5 hPa (Δz_b ≈ ±46 m) rige 0,3·|Δz_b| ≈ 13,8 m > 10 m; con +2,65 hPa
        (Δz_b ≈ −24 m), 10 m. Sin el término de z_cat en T̄, con el p̄ de todo el registro, con 10 m fijos o sin el
        valor absoluto, Δz_b o la tolerancia se mueven más de 0,01 m y alguno de los doce casos cambia de clase."""
        U = _umbrales()
        eps = 0.01
        for d_qfe, rige_frac in ((-5.0, True), (5.0, True), (2.65, False)):
            base = {"saltos_qfe": ((24, 30.0), (48, d_qfe))}
            dz_b = _dz_b(_serie_k4(72, **base), d_qfe, 24, 71)
            tol = max(U.a("K4_COINC_M"), U.a("K4_COINC_FRAC") * abs(dz_b))
            self.assertEqual(tol > U.a("K4_COINC_M"), rige_frac)      # los dos regímenes de máx(…)
            for lado in (-1, 1):
                for dentro in (True, False):
                    dz_a = dz_b + lado * (tol - eps if dentro else tol + eps)
                    with self.subTest(d_qfe=d_qfe, lado=lado, dentro=dentro):
                        r = _k4(_serie_k4(72, **base, saltos_z=((48, dz_a),)))
                        self.assertEqual(_clases(r), [(T2B, 24, BAROMETRO), (T2A, 48, None),
                                                      (T2B, 48, TRASLADO if dentro else BAROMETRO)])
                        self.assertAlmostEqual(r.quiebres[1].D, dz_a, delta=1e-9)
                        self.assertAlmostEqual(r.quiebres[2].D, d_qfe, delta=1e-9)
                        self.assertEqual((r.ultimo_traslado, r.ultimo_barometro), (48, 24) if dentro else (None, 48))

    def test_ultimo_traslado_y_ultimo_barometro_son_el_mayor_k(self):
        """«Los tramos anteriores al último traslado» (marca 1) y «antes del último quiebre de este tipo» (marca 16):
        con dos quiebres de la misma clase, el último es el de mayor k (HOM-8). Pasos de tamaños distintos (sin
        empates): A, traslado de 20 m en 24, barómetro de +3 hPa en 48 y traslado de 40 m en 72; B, barómetro de
        +2 hPa en 24, traslado de 30 m en 48 y barómetro de +4 hPa en 72."""
        p0 = 900.0
        a1 = _dqfe_traslado(20.0, p0)
        a3 = _dqfe_traslado(40.0, p0 + a1 + 3.0)
        r = _k4(_serie_k4(96, p0=p0, saltos_qfe=((24, a1), (48, 3.0), (72, a3)), saltos_z=((24, 20.0), (72, 40.0))))
        self.assertEqual(_clases(r), [(T2A, 24, None), (T2B, 24, TRASLADO), (T2B, 48, BAROMETRO), (T2A, 72, None),
                                      (T2B, 72, TRASLADO)])
        self.assertEqual((r.ultimo_traslado, r.ultimo_barometro), (72, 48))
        b2 = _dqfe_traslado(30.0, p0 + 2.0)
        r = _k4(_serie_k4(96, p0=p0, saltos_qfe=((24, 2.0), (48, b2), (72, 4.0)), saltos_z=((48, 30.0),)))
        self.assertEqual(_clases(r), [(T2B, 24, BAROMETRO), (T2A, 48, None), (T2B, 48, TRASLADO),
                                      (T2B, 72, BAROMETRO)])
        self.assertEqual((r.ultimo_traslado, r.ultimo_barometro), (48, 72))

    def test_z_impl_exacta(self):
        """z_impl = 29,27 · T̄ · ln(QFF/QFE) con T̄ = Ts + 273,15 + 0,0065·z_cat/2: con z_impl = z_cat que sube 15 m
        en el mes 24 (sólo QFF), D de T2a es 15 m con tolerancia 1e-9 (sin el «/2», ≈ 15,17 m a 1.000 m)."""
        salto = constantes.valor("S4_TRASLADOS_M")[0]
        for z_cat in (1000.0, 2500.0):
            with self.subTest(z_cat=z_cat):
                r = _k4(_serie_k4(48, z_cat=z_cat, z0=z_cat, saltos_z=((24, salto),)))
                self.assertEqual(_clases(r), [(T2A, 24, REDUCCION)])
                self.assertAlmostEqual(r.quiebres[0].D, salto, delta=1e-9)

    def test_t2a_solo_con_presiones_positivas(self):
        """HOM-2: T2a sólo con QFE > 0 y QFF > 0. En los meses 0…23 las presiones no son positivas y no hay fondo
        (no hay T2b); 24…47 es una serie normal con un cambio de sólo QFF de 20 m en el mes 36. Con el filtro, el
        resultado es el de la serie sin los meses 0…23: el quiebre de T2a en 36. Sin él, T2a valdría ±inf (QFE o QFF
        nulas) o un z_impl falso 50 m más alto (las dos negativas) en 0…23, y el primer quiebre caería en el mes 24."""
        esperado = [(T2A, 36, REDUCCION)]
        for caso in ("QFE = 0", "QFF = 0", "QFE y QFF < 0"):
            with self.subTest(caso=caso):
                df = _serie_k4(48, saltos_z=((36, 20.0),))
                antes = homogeneidad.mes2000(df["h"].to_numpy()) < 24
                self.assertEqual(_clases(_k4(df.loc[~antes].reset_index(drop=True))), esperado)
                df.loc[antes, "p_F"] = np.nan
                if caso == "QFE = 0":
                    df.loc[antes, "QFE"] = 0.0
                elif caso == "QFF = 0":
                    df.loc[antes, "QFF"] = 0.0
                else:
                    tbar = _tbar(df.loc[antes, "Ts"], df.attrs["z_cat"])
                    df.loc[antes, "QFF"] = -df.loc[antes, "QFF"] * np.exp(50.0 / (_Z_IMPL * tbar))
                    df.loc[antes, "QFE"] = -df.loc[antes, "QFE"]
                r = _k4(df)
                self.assertFalse(r.sin_prueba)
                self.assertEqual(_clases(r), esperado)
                self.assertAlmostEqual(r.quiebres[0].D, 20.0, delta=1e-9)


class PruebasBordesDetector(unittest.TestCase):
    """Bordes del detector que fija el Anexo A («horas en ≥ 80 % de los meses; 12 + 12 meses con ≥ 6 por lado;
    ≥ 100 pares por mes; ≤ 3 quiebres; tramos ≥ 12 meses») y de δ (§4.8), con tablas hechas a mano."""

    def test_horas_estables_80_por_ciento_inclusivo(self):
        """Antes de k = 12, 10 candidatos (los meses 0 y 1 tienen 99 pares y no cuentan): la hora 5 en 8 de 10 (80 %)
        es estable y la 6 en 7 de 10 no. Después, 5 candidatos (17…23 con 99 pares): la hora 7 en 4 de 5 (80 %) es
        estable y la 8 en 3 de 5 no. Los meses de 99 pares no tienen las horas 5 ni 7: si contaran, no llegarían."""
        U = _umbrales()
        candidatos = range(2, 17)                     # antes: 2…11 (10); después: 12…16 (5)
        horas_por_mes = {
            0: range(24),                             # en todos los meses
            5: range(4, 17),                          # antes, 8 de 10 (falta en 2 y 3); después, 5 de 5
            6: [*range(2, 9), *range(12, 24)],        # antes, 7 de 10; después, 5 de 5
            7: range(2, 16),                          # antes, 10 de 10; después, 4 de 5 (falta en 16)
            8: [*range(2, 15), *range(17, 24)],       # antes, 10 de 10; después, 3 de 5 (si contaran 17…23, 10 de 12)
        }
        filas = {m: (500 if m in candidatos else 99, {x: 1.0 for x, meses in horas_por_mes.items() if m in meses})
                 for m in range(24)}
        self.assertEqual(homogeneidad.horas_estables(_medianas_a_mano(filas), 12, U), frozenset({0, 5, 7}))

    def test_mes_candidato_con_100_pares_exactos(self):
        """«≥ 100 pares por mes» es inclusivo: antes de k = 12, seis meses de 100 pares (valores 1…6) y seis de 99
        (valor 50); después, doce de 100 pares (valor 10). D = 10 − 3,5; si los de 99 contaran, D = 10 − 28."""
        U = _umbrales()
        med = _una_hora([50.0] * 6 + [1.0, 2.0, 3.0, 4.0, 5.0, 6.0] + [10.0] * 12, pares=[99] * 6 + [100] * 18)
        self.assertEqual(homogeneidad.horas_estables(med, 12, U), frozenset({0}))
        self.assertEqual(homogeneidad.salto(med, 12, U), 6.5)

    def test_seis_meses_validos_por_lado(self):
        """«≥ 6 por lado» es inclusivo, y los válidos se cuentan después de fijar H*(k) (MC-06). Antes de k = 12: los
        meses 0…4 no son candidatos; 5…11 sí (7), y al 5 le falta la hora 1 (en 6 de 7, 86 %: estable), así que el 5
        no es válido y quedan 6 (valores 1…6). Después: 12…17 válidos (10…15) y 18…23 sin 100 pares. D = 12,5 − 3,5.
        Con un candidato menos de cada lado quedan 5 válidos y D no se define."""
        U = _umbrales()

        def tabla(sin_par_antes=(), sin_par_despues=()):
            filas: dict[int, tuple[int, dict[int, float]]] = {}
            for m in range(24):
                pares = 50 if m < 5 or m >= 18 or m in sin_par_antes or m in sin_par_despues else 500
                if m < 12:
                    v = 99.0 if m <= 5 else float(m - 5)
                else:
                    v = float(m - 2)
                horas = {0: v} if m == 5 else {0: v, 1: v}
                filas[m] = (pares, horas)
            return _medianas_a_mano(filas)

        med = tabla()
        self.assertEqual(homogeneidad.horas_estables(med, 12, U), frozenset({0, 1}))
        self.assertEqual(homogeneidad.salto(med, 12, U), 9.0)
        self.assertIsNone(homogeneidad.salto(tabla(sin_par_antes=(6,)), 12, U))       # 7…11: 5 válidos
        self.assertIsNone(homogeneidad.salto(tabla(sin_par_despues=(17,)), 12, U))    # 12…16: 5 válidos

    def test_umbral_inclusivo(self):
        """«máx_k |D(k)| ≥ umbral» es inclusivo en los cuatro umbrales (T2a, T2b, T y Td): un escalón de exactamente
        el umbral, hacia arriba o hacia abajo, se detecta en su mes (24); uno un ulp menor, no. Con las 24 horas,
        tramos_homogeneos parte en el mes 30 un escalón de exactamente 0,5 K en T y 1,0 K en Td."""
        U = _umbrales()
        for nombre in ("K4_T2A_M", "K4_T2B_HPA", "HOM_T", "HOM_TD"):
            u = float(U.a(nombre))
            menos = float(np.nextafter(u, 0.0))
            with self.subTest(umbral=nombre):
                self.assertEqual(homogeneidad.segmentar(_una_hora([0.0] * 24 + [u] * 24), u, U), [(24, u)])
                self.assertEqual(homogeneidad.segmentar(_una_hora([u] * 24 + [0.0] * 24), u, U), [(24, -u)])
                self.assertEqual(homogeneidad.segmentar(_una_hora([0.0] * 24 + [menos] * 24), u, U), [])
        h = _horas("2000-01-01T00", "2005-01-01T00")
        for variable, nombre in (("T", "HOM_T"), ("Td", "HOM_TD")):
            u = U.a(nombre)
            with self.subTest(variable=variable):
                self.assertEqual(homogeneidad.tramos_homogeneos(h, _escalones(h, [30], [0.0, u]), variable, U),
                                 [(0, 29), (30, 59)])
                casi = _escalones(h, [30], [0.0, u * (1 - 1e-9)])
                self.assertEqual(homogeneidad.tramos_homogeneos(h, casi, variable, U), [(0, 59)])

    def test_primer_y_ultimo_corte_admisibles(self):
        """«tramos ≥ 12 meses»: en el tramo 0…35 los cortes van de a + 12 = 12 a b − 11 = 24. En cada tabla, D tiene
        su máximo en el borde de afuera (11 o 25: un tramo de 11 meses) y el segundo, sin empate, en el de adentro
        (12 o 24): el corte cae en 12 o en 24 con D = 2,5, no en 11 ni en 25 con D = 3."""
        U = _umbrales()
        s = 2.0
        izquierda = _una_hora([-1.0] * 6 + [0.0] * 6 + [s] * 24)
        self.assertEqual(homogeneidad.salto(izquierda, 11, U), s + 1.0)
        self.assertEqual(homogeneidad.salto(izquierda, 12, U), s + 0.5)
        self.assertEqual(homogeneidad.segmentar(izquierda, U.a("HOM_T"), U), [(12, s + 0.5)])
        derecha = _una_hora([0.0] * 24 + [s] * 6 + [s + 1.0] * 6)
        self.assertEqual(homogeneidad.salto(derecha, 25, U), s + 1.0)
        self.assertEqual(homogeneidad.salto(derecha, 24, U), s + 0.5)
        self.assertEqual(homogeneidad.segmentar(derecha, U.a("HOM_T"), U), [(24, s + 0.5)])
        # Con 24 meses sólo cabe el corte 12 (a + 12 = b − 11).
        self.assertEqual(homogeneidad.segmentar(_una_hora([0.0] * 12 + [s] * 12), U.a("HOM_T"), U), [(12, s)])
        self.assertEqual(homogeneidad.segmentar(_una_hora([0.0] * 12 + [s] * 11), U.a("HOM_T"), U), [])

    def test_segmentacion_toma_el_mayor_entre_todos_los_tramos(self):
        """HOM-4: en cada paso gana el mayor |D| entre todos los tramos, no el primer tramo con corte. Escalones de 1;
        3; 1,5 y 2 en 18, 36, 54 y 72 (el mayor no es el primero por la izquierda): entran 3, luego 2 (tramo de la
        derecha, aunque el de la izquierda tiene el corte de 1) y luego 1,5."""
        U = _umbrales()
        niveles = [0.0] * 18 + [1.0] * 18 + [4.0] * 18 + [5.5] * 18 + [7.5] * 24
        quiebres = homogeneidad._segmentar(homogeneidad._desde_tabla(_una_hora(niveles)), U.a("HOM_T"), U)
        self.assertEqual([(k, d) for k, d, _, _ in quiebres], [(36, 3.0), (72, 2.0), (54, 1.5)])
        self.assertEqual(homogeneidad.segmentar(_una_hora(niveles), U.a("HOM_T"), U), [(36, 3.0), (54, 1.5), (72, 2.0)])

    def test_empate_entre_tramos_lo_gana_el_primero(self):
        """HOM-5: un empate de |D| entre tramos lo gana el primero en el orden de los meses. Escalones de +1, +3, +2 y
        −1 en 18, 36, 54 y 72: tras 3 y 2, los tramos 0…35 (+1 en 18) y 54…95 (−1 en 72) empatan en |D| = 1 y el
        tercer quiebre es el de 18."""
        U = _umbrales()
        niveles = [0.0] * 18 + [1.0] * 18 + [4.0] * 18 + [6.0] * 18 + [5.0] * 24
        self.assertEqual(homogeneidad.segmentar(_una_hora(niveles), U.a("HOM_T"), U), [(18, 1.0), (36, 3.0), (54, 2.0)])

    def test_desplazamientos_con_medianas_y_no_medias(self):
        """§4.8: «mediana del residuo en el tramo g a la hora h − mediana en todo el registro a la hora h». Dos tramos
        (2002 y 2003, de 365 días) en 0 y 1, y en 2003 veinte días con +100 en todas las horas (atípicos asimétricos):
        las medianas no se mueven (δ = −0,5 y +0,5), pero la media del registro (≈ 3,21) y la de 2003 (≈ 6,42) sí."""
        U = _umbrales()
        h = _horas("2002-01-01T00", "2004-01-01T00")
        m0 = int(homogeneidad.mes2000(h[:1])[0])
        r = _escalones(h, [m0 + 12], [0.0, 1.0])
        dia = (h - h[0]) // 24
        r = np.where((dia >= 365) & (dia < 385), 100.0, r)
        self.assertEqual(homogeneidad.desplazamientos(h, r, [(m0, m0 + 11), (m0 + 12, m0 + 23)], U),
                         {0: -0.5, 1: 0.5})

    def test_desplazamientos_80_por_ciento_inclusivo(self):
        """HOM-11: H*_δ son las horas con mediana en ≥ 80 % de los candidatos de cada tramo, inclusivo. En 2002 y
        2003 (0 y 1), febrero y marzo sin residuo (no son candidatos: quedan 10 por tramo) y la hora 5 sin residuo en
        abril y mayo (en 8 de 10, el 80 %), con los mismos conteos en los dos años. En 2003 la hora 5 vale 3: con
        ella en H*_δ, δ = ∓13/24; sin ella, ∓0,5."""
        U = _umbrales()
        h = _horas("2002-01-01T00", "2004-01-01T00")
        mes, hora = homogeneidad.mes2000(h), homogeneidad.hora_utc(h)
        m0 = int(mes[0])
        r = _escalones(h, [m0 + 12], [0.0, 1.0])
        r = np.where((mes >= m0 + 12) & (hora == 5), 3.0, r)
        mes_cal = (mes - m0) % 12                                     # 0 = enero
        r = np.where(np.isin(mes_cal, (1, 2)), np.nan, r)
        r = np.where(np.isin(mes_cal, (3, 4)) & (hora == 5), np.nan, r)
        d = homogeneidad.desplazamientos(h, r, [(m0, m0 + 11), (m0 + 12, m0 + 23)], U)
        self.assertEqual(sorted(d), [0, 1])
        self.assertAlmostEqual(d[0], -13 / 24, places=12)
        self.assertAlmostEqual(d[1], 13 / 24, places=12)


if __name__ == "__main__":
    unittest.main()
