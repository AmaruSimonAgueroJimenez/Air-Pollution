"""Detector común de quiebres (§2.5, K4) y tramos homogéneos de los residuos (§4.8).

Medianas por mes y hora UTC, H*(k), D(k), segmentación binaria; K4 (T2a, T2b y su clasificación); tramos y δ.
Las estadísticas se calculan en memoria y no se guardan (§0.4.6): ninguna función escribe, y ``k4`` devuelve sólo
meses, clases y D en un ``tipos.ResultadoK4`` que tampoco se escribe tal cual (acuerdo A4 de ``COORDINACION_M1.md``).

Dueño: I9 (olas 2 y 3; en la ola 3, D39 a D42; después, EMC2-1 por D52).
Lecturas propias (HOM-n), para el addendum de M1:
- HOM-1. **Mes y hora.** El mes es el ``mes2000`` del instante UTC de la hora (A4: «medianas por mes y hora UTC»,
  §2.5): (año − 2000)·12 + mes − 1, con 0 = enero de 2000; la hora es la hora UTC, h mód 24. ``mes2000`` lo calcula
  con aritmética de fechas de numpy (calendario gregoriano proléptico), y una prueba lo compara con la fórmula de A4.
- HOM-2. **Horas válidas y «pares».** Una hora cuenta para un estadístico si el estadístico es finito en ella: T2a con
  Ts, QFE y QFF finitos (y positivos las dos presiones) y z_cat legible; T2b con QFE y p_F finitos; en §4.8, con el
  residuo finito. Quien llama pone NaN donde el valor no es válido (A4); aquí no se leen marcas. Los «pares» de un mes
  (§2.5: «Un mes es válido con ≥ 100 pares») son esas horas del mes, de todas las horas UTC. La mediana de un mes y
  una hora existe con ≥ ``K4_MIN_MES_HORA`` valores; con un número par de valores es la media de los dos centrales.
  Las horas ``h`` van crecientes y sin repetir en toda función pública que las recibe (``medianas_mes_hora``, ``k4``,
  ``tramos_homogeneos`` y ``desplazamientos``; A4): una hora repetida contaría dos veces en los pares y en los ≥ 5
  valores de un mes y una hora. Si no, ValueError.
- HOM-3. **H*(k) y meses válidos en dos pasos (MC-06, aceptada en D5).** Ventanas: antes = k−12 … k−1 y después =
  k … k+11 (``K4_VENTANA``), recortadas a los meses del tramo. (1) Los meses candidatos de un lado son los que tienen
  ≥ ``K4_MIN_PARES`` pares; H*(k) son las horas UTC con mediana en ≥ ``K4_HORAS_PCT`` % de los candidatos de cada
  lado, con la comparación entera 100·n_h ≥ 80·n (sin redondeos de coma flotante). Un lado sin candidatos deja H*(k)
  vacío. (2) Los meses válidos son los candidatos con mediana en todas las horas de H*(k). M(j; k) es la media de las
  medianas del mes j en H*(k). D(k) = mediana de M en los válidos de después − mediana en los de antes; no se define
  sin H*(k) o con menos de ``K4_MIN_LADO`` válidos en un lado (None).
- HOM-4. **Segmentación binaria codiciosa (MC-06).** El tramo inicial va del primer al último mes con algún par. Un
  corte k en el tramo [a, b] exige ≥ ``K4_TRAMO_MIN`` meses a cada lado (k − a ≥ 12 y b − k + 1 ≥ 12); así las
  ventanas de 12 + 12 meses caen siempre dentro del tramo y el recorte de MC-06 nunca muerde. En cada paso, entre todos
  los tramos, gana el mayor |D(k)| que cumpla |D| ≥ umbral (inclusivo, «máx_k |D(k)| ≥ 10 m»); el tramo se parte en
  [a, k−1] y [k, b], y se sigue hasta ``K4_MAX_QUIEBRES`` quiebres o hasta que ningún tramo tenga un corte sobre el
  umbral. D es el del paso en que se detectó. ``segmentar`` da [(k, D)] en orden de k.
- HOM-5. **El k del máximo con empates (D39 [delegada], sobre P29; antes HOM-P1 y HOM-P5).** El texto dice «en el k
  del máximo», pero la mediana de 12 meses hace mesetas: con un escalón limpio en k0, D(k) vale exactamente lo mismo
  para k0 − 5 … k0 + 5 (los k en que ≤ 5 de los 12 meses de cada ventana quedan del otro lado del escalón), recortado
  a los cortes admisibles del tramo [a, b], a + 12 … b − 11 (HOM-4). Con ruido, dos k vecinos empatan cuando, en las
  dos ventanas, el mes que sale y el que entra quedan del mismo lado del par central, y H*(k) y los meses válidos no
  cambian. Con las semillas de HOM-14 (SEMILLA + i, i = 0…99; los cinco casos de S4 en las tres altitudes), 320 de los
  1.195 quiebres (27 %) tienen el máximo empatado, y en 13 de ellos los empatados no son consecutivos (huecos de 1 o 2
  meses dentro de la misma meseta). **Regla (D39):** entre los k cuyo |D| es igual al máximo (igualdad en float64,
  MC-63) se toma el central, la mediana de sus posiciones; con un número par, el más tardío de los dos centrales (el
  más estricto de los dos para las marcas 1 y 16, que van en las horas con mes2000 < k). Sin empate es el k del
  máximo. Un empate entre tramos distintos se resuelve por el primer tramo en el orden de los meses. La mediana se toma
  sobre todos los k empatados del tramo, también si no son consecutivos o forman dos mesetas separadas (D39: «dos
  mesetas separadas, como HOM-5»): con dos escalones limpios del mismo tamaño en 24 y 48 de un tramo 0…71 (mesetas
  19…29 y 43…53), el central es 43, el borde de la segunda, y el paso siguiente pone el otro en 24.
  **Justificación (corregida por D39).** Ninguna regla de empate es la más estricta en todos los usos: el k más
  tardío pone más horas bajo las marcas 1 y 16, pero en un escalón limpio corre el quiebre 5 meses y deja en §4.8
  cinco meses del sensor nuevo en el tramo viejo. El central pone en su mes un escalón limpio sin ciclo anual sólo si
  su meseta entera cabe entre los cortes admisibles: con k0 − a ≥ 17 meses del nivel viejo y b − k0 + 1 ≥ 16 del
  nuevo (la asimetría es la del más tardío de los dos centrales). La versión anterior decía que el central era «el
  único que pone en su mes un escalón limpio», sin esa condición, y eso no vale en los bordes del tramo, donde la
  meseta queda recortada y ninguna regla de empate acierta: con 7 a 16 meses del nivel viejo el corte cae de 5 a 1
  meses tarde; con 7 a 15 del nuevo, de 5 a 1 meses antes; con exactamente 6 de un lado, en el primer o el último
  corte admisible y con la mitad del escalón; con 5 o menos, D(k) = 0 en todos los cortes admisibles y el escalón no se
  ve. Es efecto de los tramos de ≥ 12 meses y de las ventanas de 12 + 12 meses (HOM-4, MC-06), no de la regla de
  empate, y ``test_homogeneidad`` lo deja escrito mes a mes (``test_empate_en_los_bordes_del_tramo``). Con ciclo anual
  tampoco acierta siempre ninguna regla, porque el sesgo depende del mes calendario del cambio: en «reduccion» de S4,
  z_impl hereda antes del cambio el ciclo anual de Ts, y el quiebre cae en k0 − 3 en 30, 38 y 52 de las 100 series a
  500, 1.000 y 2.500 m.
- HOM-6. **Estadísticos de K4.** T2a = z_impl = 29,27 · T̄ · ln(QFF/QFE), con T̄ = Ts + 273,15 + 0,0065·z_cat/2 (K),
  en m; T2b = QFE − p_F en hPa, con el p_F de ``fondo_era5l.en_horas`` (A2 y A3: la diferencia en hPa no es r_p). Sin
  z_cat legible no hay T2a (T̄ no se define). Todo en float64, aunque las entradas lleguen en float32 (A1).
- HOM-7. **Clasificación (EMC2-1, la Enmienda 2 del producto, texto v2.3; D52 del autor, sobre P28, antes HOM-P4).**
  ΔQFE es el D de un quiebre de T2b (el salto de QFE respecto del fondo). T̄ y p̄ (§2.5: «T̄ en K y p̄ la media de QFE
  del tramo») son las medias sobre las horas del tramo que ese quiebre partió (el tramo de la segmentación en el paso
  en que se detectó; D41 [delegada], sobre P31, antes HOM-P3): p̄ sobre las horas con T2b válido y T̄ sobre las que
  además tienen Ts. Δz_b = −ΔQFE · 287,05 · T̄ / (9,80665 · p̄). Δz_a es el D(k) de T2a en el mes k mismo del quiebre de
  T2b, con las ventanas dentro de ese tramo (``_salto`` sobre las medianas de T2a recortadas a él). Es **traslado** si
  Δz_b es finito, Δz_a se define, |Δz_a| ≥ ``K4_T2A_M`` y |Δz_a − Δz_b| ≤ máx(``K4_COINC_M``; ``K4_COINC_FRAC``·|Δz_b|);
  si no (también sin QFF, o sin T̄ y por eso sin Δz_b), **barómetro**. Un quiebre de T2a es **cambio del método de
  reducción** (sólo se informa) si no hay ningún quiebre de T2b a ≤ ``K4_COINC_MESES`` meses y, en su mes, el D(k) de
  T2b (con las ventanas dentro del tramo que ese quiebre de T2a partió) no se define o queda bajo ``K4_T2B_HPA``; si no,
  va sin clase (A4: la clase va en los de T2b y en los de T2a sin T2b). El D de cada quiebre sigue siendo el suyo:
  ``ResultadoK4`` y A4 no cambian. El autor mantuvo D52 conociendo su costo sobre Q2 (D55): un traslado retira con la
  marca 1 toda la fila, no sólo QFE y QFF.
  **Por qué en el mismo mes.** La mediana de 12 meses deja el D de un salto limpio igual en ±5 meses (HOM-5), y con el
  ruido de MC-49 el máximo de T2a y el de T2b caen cada uno en cualquier punto de su meseta. La regla literal del v2.2
  («hay un quiebre de T2a a ≤ 3 meses», con Δz_a = el D de ese quiebre) declaraba el traslado de 15 m en 90, 89 y 81 de
  100 series a 500, 1.000 y 2.500 m; con EMC2-1, en 100, 100 y 96 (HOM-14). Sin ruido, un salto de QFE y uno de z_impl
  compatibles se juntan en un traslado hasta a 5 meses (la meseta) y no más: a 6 el de T2b es barómetro y el de T2a va
  sin clase (el D de T2b en su mes es la mitad del salto), y a 7 es «método de reducción» (``PruebasBordesK4``).
  **Las ventanas en el tramo.** Por HOM-4, las 12 + 12 de un corte admisible caen siempre dentro de su tramo, así que el
  D(k) en el tramo es el mismo que en todo el registro: tomar las ventanas en todo el registro es una mutación
  equivalente y no lleva prueba propia.
  **Texto vigente.** El código sigue EMC2-1 desde su adopción (D52). Desde el anclaje de la Enmienda 2 (APH
  ``dd6c1c6``, sello ``e3f9f97``), ``umbrales.TEXTO_VIGENTE`` y sus copias en ``ceguera`` y ``fijados`` son el v2.3
  (b4175f78…).
- HOM-8. **Salida de K4.** ``quiebres`` en orden de (mes, estadístico); ``ultimo_traslado`` y ``ultimo_barometro``
  son el mayor k de cada clase (las marcas 1 y 16 van en las horas con mes2000 < k; A4). ``sin_prueba`` (marca 21) es
  «sin QFE válida» en todo el registro (A4); entonces no hay quiebres. Con QFE pero sin p_F en ninguna hora (estación
  sin fondo) no hay T2b, y un quiebre de T2a queda como cambio del método de reducción: sólo informa.
- HOM-9. **Entrada de K4 (A4).** ``tabla_estacion`` trae ``h`` (entero, creciente y sin repetir), ``Ts``, ``QFE`` y
  ``QFF``; las demás columnas se ignoran. ``p_F`` va alineado con las filas. Si no, ValueError. ``ResultadoK4`` lleva
  el código: ``k4`` lo recibe por la palabra clave ``codigo``, obligatoria y sin valor por omisión (agregada a la firma
  de §3 y de A4; pedido al coordinador). Un código que no es texto es TypeError, y uno vacío o en blanco, ValueError:
  un ``ResultadoK4`` sin código no se puede casar con su estación en ``politicas_efectivas`` (A5).
- HOM-10. **Tramos homogéneos (§4.8).** El mismo detector sobre el residuo de T (``HOM_T``) o de Td (``HOM_TD``).
  «Viento y presión no se segmentan»: otra variable es ValueError. Los tramos [(desde_mes, hasta_mes)] son
  inclusivos, en orden, contiguos y cubren del primer al último mes con residuo válido; sin residuo válido, [].
- HOM-11. **Desplazamientos δ (§4.8; D40 [delegada], sobre P30, antes HOM-P2).** El texto dice «media, sobre las
  horas de H*», pero H* sólo está definido para un corte k. Regla (D40): H*_δ son las horas UTC con mediana en ≥ 80 %
  de los meses candidatos (≥ 100 pares) de cada tramo, la extensión de «de cada lado» a todos los tramos (el conjunto
  más chico, y el mismo para todos los g). «Mediana del residuo en el tramo g a la hora h» es la de todos sus valores
  horarios a esa hora UTC en el tramo, y «en todo el registro», la de todos los valores válidos a esa hora.
  δ(g) = media sobre H*_δ de la diferencia. Sin quiebres (un tramo) δ = 0 exacto. Si H*_δ queda vacío, δ = NaN en
  todos los tramos: r̃ queda sin definir y la estación no entra en B ni en AB (la lectura más estricta).
- HOM-12. Las medianas, H*, M y D viven sólo en memoria (§0.4.6): ``medianas_mes_hora`` las devuelve a quien llama
  y ningún módulo las escribe (S7 lo vigila con ``ceguera.GuardaResiduo``).
- HOM-13. **La verdad de la parte de S5 de §4.8 (D42 [delegada], sobre P32; lectura provisional hasta el addendum).**
  Las pruebas del cambio de sensor de 1 K usan ``sintetico.verdad(…, anomalias="MC-50")`` (SIN-21): σ = 1,5 K,
  L = 100 km, τ = 48 h y media 0 en cada punto × mes × año, con la semilla ``SEMILLA`` (20261023). MC-50 se escribió
  para S6 («Anomalías de S6»); D42 la extiende a S5, para que la prueba mida el detector y no el ruido de muestreo de
  un mes. Es provisional porque D42 es delegada y el addendum todavía no la fija. Sin la media 0 el residuo
  estacionario da tramos falsos con 0,5 K; una prueba informativa, que no decide S5
  (``test_informativa_s5_sin_media_cero``), lo declara con las semillas SEMILLA + i, i = 0…19: sin la media 0, 14 de
  20 residuos estacionarios dan un tramo falso y el cambio de sensor se recupera (dos tramos, el corte en la meseta,
  Δδ a ≤ 0,2 K de 1 K y r̃ sin quiebre) en 9 de 40 casos; con ella, 0 de 20 y 40 de 40.
- HOM-14. **Semillas y tasas de S4 (D42 [delegada], sobre P32 y los revisores de S4; D52, sobre P28; D56, sobre
  P47).** Ruido y señales de ``sintetico.series_traslado`` (MC-49, SIN-13 y SIN-20), que el addendum fija antes de
  correr S4. Cada caso se prueba con la semilla del protocolo, ``SEMILLA``, y la tasa se informa sobre un conjunto
  fijado de antemano: SEMILLA + i, i = 0…99, en cada caso y altitud (el mismo que usó el revisor de la ola 2 para P28 y el borrador de la
  Enmienda 2; no se midió ningún otro), y SEMILLA + i, i = 0…199, con las altitudes en ciclo, para los falsos quiebres
  (§9: «200 series»). Acierto por caso: traslado de 15 m, un último traslado a ≤ 5 meses del cambio y ningún barómetro;
  traslado de 5 m y horario, ningún quiebre; barómetro, un solo quiebre, de T2b y «barómetro», a ≤ 5 meses; reducción,
  un solo quiebre, de T2a y «método de reducción», a ≤ 5 meses. Tasas con EMC2-1, a 500, 1.000 y 2.500 m: traslado de
  15 m, 100, 100 y 96 de 100 (con la regla literal del v2.2 eran 90, 89 y 81); 5 m, 100 en las tres; barómetro, 100, 99 y
  100; reducción y horario, 100 en las tres. Ninguna de las 1.200 series de 5 m, barómetro, reducción y horario declara
  un traslado; falsos quiebres, 0 de 200 (§9: ≤ 2 %). En 5 de los traslados de 15 m a 2.500 m, el quiebre de T2a queda a
  más de 3 meses del de T2b y en su mes el D de T2b no llega a 1,2 hPa, así que se informa además como «método de
  reducción» (doble informe, del lado de informar de más; con la regla literal de T2a serían 15).
  **P47 (D56; antes en D52).** El traslado de 15 m a 2.500 m con la semilla del protocolo sigue omitido, con un motivo
  nuevo: ahí no
  hay quiebre de T2b (15 m mueven QFE ≈ 1,37 hPa y el máximo de |D| de T2b es 1,187 hPa, bajo 1,2 hPa), sale sólo un
  quiebre de T2a («método de reducción») y ninguna regla de clasificación puede declararlo traslado. Es un límite de la
  señal, no de la regla: las 4 de las 100 semillas que fallan con EMC2-1 (i = 0, 14, 20 y 30) son las que no tienen
  quiebre de T2b. §9 no nombra altitudes para el traslado de 15 m, y la tasa (96 de 100) se informa en ``TASAS_S4`` y
  en el addendum. Sin H*(k), el cambio de horario sí movería D: ≈ −25 m en T2a y de + 2,0 a + 3,3 hPa en T2b en el mes
  del cambio, compatibles como un traslado, y K4 vería un quiebre en cada estadístico.
Depende de: tipos y constantes. Los umbrales llegan como objeto (``.a``); la tabla de §1 del diseño permite además
umbrales y numerico, que no hacen falta.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from meteo_combinada import constantes
from meteo_combinada.tipos import ClaseQuiebre, Estadistico, Quiebre, ResultadoK4, Variable

HORAS_DIA = 24
PORCIENTO = 100
COLUMNA_PARES = "pares"
COLUMNAS_HORA = tuple(f"h{i:02d}" for i in range(HORAS_DIA))
NOMBRE_INDICE = "mes"

_EPOCA_H = np.datetime64("2000-01-01T00", "h")     # h = 0 (tipos.EPOCA_H)
_EPOCA_M = np.datetime64("2000-01", "M")           # mes2000 = 0
_Z_IMPL, _KELVIN, _GAMMA_TBAR = constantes.valor("Z_IMPLICITA")     # 29,27, 273,15 y 0,0065 de z_impl (§2.5)
_DIVISOR_TBAR = constantes.valor("Z_IMPLICITA_DIVISOR")       # el «/2» de T̄
_R_SECO = constantes.valor("R_SECO")
_GRAVEDAD = constantes.valor("GRAVEDAD")

# §4.8: «0,5 K en T y 1,0 K en Td. Viento y presión no se segmentan».
UMBRAL_TRAMOS = {Variable.T: "HOM_T", Variable.TD: "HOM_TD"}
UMBRAL_K4 = {Estadistico.T2A: "K4_T2A_M", Estadistico.T2B: "K4_T2B_HPA"}


# ---------------------------------------------------------------------------
# Tiempo
# ---------------------------------------------------------------------------
def _horas(h) -> np.ndarray:
    """``h`` como int64 de una dimensión; TypeError si no es entero."""
    arr = np.asarray(h)
    if arr.ndim != 1:
        raise ValueError("h debe ser de una dimensión")
    if arr.dtype == bool or not np.issubdtype(arr.dtype, np.integer):
        raise TypeError(f"h debe ser entero (horas desde 2000-01-01T00Z), no {arr.dtype}")
    return arr.astype(np.int64)


def _creciente(h: np.ndarray, nombre: str) -> None:
    if len(h) > 1 and not bool(np.all(np.diff(h) > 0)):
        raise ValueError(f"{nombre}: h debe ser creciente y sin repetir (A4)")


def mes2000(h) -> np.ndarray:
    """HOM-1: meses desde enero de 2000 del instante UTC de cada hora (0 = 2000-01)."""
    hh = _horas(h)
    meses = (_EPOCA_H + hh.astype("timedelta64[h]")).astype("datetime64[M]")
    return (meses - _EPOCA_M).astype(np.int64)


def hora_utc(h) -> np.ndarray:
    """Hora UTC (0-23) de cada hora."""
    return np.mod(_horas(h), HORAS_DIA)


# ---------------------------------------------------------------------------
# Medianas por mes y hora UTC (en memoria)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class _Medianas:
    """Meses consecutivos ``mes0`` … ``mes0 + n − 1``; ``pares`` (n,) y ``med`` (n × 24, NaN sin mediana)."""
    mes0: int
    pares: np.ndarray
    med: np.ndarray

    @property
    def n(self) -> int:
        return len(self.pares)

    @property
    def ultimo(self) -> int:
        return self.mes0 + self.n - 1

    def recortar(self, a: int, b: int) -> "_Medianas":
        """Los meses a … b (inclusivos) que hay en la tabla."""
        i0 = max(a, self.mes0) - self.mes0
        i1 = min(b, self.ultimo) - self.mes0 + 1
        if i1 <= i0:
            return _Medianas(max(a, self.mes0), np.zeros(0, np.int64), np.zeros((0, HORAS_DIA)))
        return _Medianas(self.mes0 + i0, self.pares[i0:i1], self.med[i0:i1])

    def con_datos(self) -> tuple[int, int] | None:
        """Primer y último mes con algún par."""
        idx = np.flatnonzero(self.pares > 0)
        if len(idx) == 0:
            return None
        return self.mes0 + int(idx[0]), self.mes0 + int(idx[-1])


def _construir(h: np.ndarray, x: np.ndarray, umbrales) -> _Medianas:
    """Medianas por mes y hora UTC de los valores ``x`` (ya filtrados: finitos y válidos) en las horas ``h``."""
    if len(h) == 0:
        return _Medianas(0, np.zeros(0, np.int64), np.zeros((0, HORAS_DIA)))
    mes = mes2000(h)
    hora = hora_utc(h)
    m0 = int(mes.min())
    n_meses = int(mes.max()) - m0 + 1
    clave = (mes - m0) * HORAS_DIA + hora
    orden = np.lexsort((x, clave))
    xs = x[orden]
    cuenta = np.bincount(clave, minlength=n_meses * HORAS_DIA)
    inicio = np.concatenate(([0], np.cumsum(cuenta)[:-1]))
    med = np.full(n_meses * HORAS_DIA, np.nan)
    hay = cuenta >= umbrales.a("K4_MIN_MES_HORA")
    bajo = inicio[hay] + (cuenta[hay] - 1) // 2
    alto = inicio[hay] + cuenta[hay] // 2
    med[hay] = (xs[bajo] + xs[alto]) / 2
    pares = cuenta.reshape(n_meses, HORAS_DIA).sum(axis=1).astype(np.int64)
    return _Medianas(m0, pares, med.reshape(n_meses, HORAS_DIA))


def _a_tabla(t: _Medianas) -> pd.DataFrame:
    indice = pd.Index(np.arange(t.mes0, t.mes0 + t.n, dtype=np.int64), name=NOMBRE_INDICE)
    df = pd.DataFrame(t.med, index=indice, columns=list(COLUMNAS_HORA))
    df.insert(0, COLUMNA_PARES, t.pares.astype(np.int64))
    return df


def _desde_tabla(medianas) -> _Medianas:
    """La tabla de ``medianas_mes_hora`` (o un ``_Medianas``) como arreglos; los meses que faltan, sin pares."""
    if isinstance(medianas, _Medianas):
        return medianas
    if not isinstance(medianas, pd.DataFrame):
        raise TypeError("medianas debe ser la tabla de medianas_mes_hora")
    columnas = [COLUMNA_PARES, *COLUMNAS_HORA]
    if list(medianas.columns) != columnas:
        raise ValueError(f"medianas: columnas {list(medianas.columns)} distintas de {columnas}")
    if len(medianas) == 0:
        return _Medianas(0, np.zeros(0, np.int64), np.zeros((0, HORAS_DIA)))
    meses = np.asarray(medianas.index)
    if meses.dtype == bool or not np.issubdtype(meses.dtype, np.integer) or len(set(meses.tolist())) != len(meses):
        raise ValueError("medianas: el índice debe ser mes2000 entero y sin repetir")
    m0, m1 = int(meses.min()), int(meses.max())
    completo = medianas.reindex(np.arange(m0, m1 + 1))
    pares = completo[COLUMNA_PARES].fillna(0).to_numpy(dtype=np.int64)
    med = completo[list(COLUMNAS_HORA)].to_numpy(dtype=np.float64)
    return _Medianas(m0, pares, med)


def medianas_mes_hora(h, valores, validos, umbrales) -> pd.DataFrame:
    """Medianas del estadístico por mes (mes2000, índice «mes») y hora UTC (columnas ``h00`` … ``h23``) en las horas
    válidas (``validos`` y valor finito; ``validos`` None: sólo finito), con ≥ ``K4_MIN_MES_HORA`` valores, y los
    pares de cada mes (``pares``). Meses consecutivos del primero al último con algún par; ``h`` creciente y sin
    repetir (HOM-2). Sólo en memoria."""
    hh = _horas(h)
    _creciente(hh, "medianas_mes_hora")
    x = np.asarray(valores, dtype=np.float64)
    if x.shape != hh.shape:
        raise ValueError("valores y h deben tener el mismo largo")
    ok = np.isfinite(x)
    if validos is not None:
        v = np.asarray(validos)
        if v.dtype != bool or v.shape != hh.shape:
            raise ValueError("validos debe ser booleano y del largo de h")
        ok &= v
    return _a_tabla(_construir(hh[ok], x[ok], umbrales))


# ---------------------------------------------------------------------------
# H*(k), D(k) y segmentación (MC-06)
# ---------------------------------------------------------------------------
def _lados(t: _Medianas, k: int, umbrales) -> tuple[np.ndarray, np.ndarray]:
    """Índices (en ``t``) de los meses de las ventanas de antes y de después de k, recortadas a la tabla."""
    w = umbrales.a("K4_VENTANA")
    antes = np.arange(max(k - w, t.mes0), min(k - 1, t.ultimo) + 1) - t.mes0
    despues = np.arange(max(k, t.mes0), min(k + w - 1, t.ultimo) + 1) - t.mes0
    return antes, despues


def _estables(t: _Medianas, k: int, umbrales) -> tuple[np.ndarray, list[np.ndarray]]:
    """Paso 1 de HOM-3: H*(k) como máscara de 24 horas y los candidatos de cada lado."""
    estable = np.ones(HORAS_DIA, dtype=bool)
    candidatos = []
    for lado in _lados(t, k, umbrales):
        cand = lado[t.pares[lado] >= umbrales.a("K4_MIN_PARES")]
        candidatos.append(cand)
        if len(cand) == 0:
            estable[:] = False
            continue
        n_h = np.isfinite(t.med[cand]).sum(axis=0)
        estable &= n_h * PORCIENTO >= umbrales.a("K4_HORAS_PCT") * len(cand)
    return estable, candidatos


def horas_estables(medianas, k: int, umbrales) -> frozenset[int]:
    """H*(k) (MC-06, HOM-3): horas UTC con mediana en ≥ 80 % de los meses candidatos de cada lado."""
    estable, _ = _estables(_desde_tabla(medianas), int(k), umbrales)
    return frozenset(int(i) for i in np.flatnonzero(estable))


def _salto(t: _Medianas, k: int, umbrales) -> float | None:
    estable, candidatos = _estables(t, k, umbrales)
    if not estable.any():
        return None
    medias = []
    for cand in candidatos:
        filas = t.med[cand][:, estable]
        validos = np.isfinite(filas).all(axis=1)          # paso 2 de HOM-3
        if int(validos.sum()) < umbrales.a("K4_MIN_LADO"):
            return None
        medias.append(filas[validos].mean(axis=1))        # M(j; k)
    antes, despues = medias
    return float(np.median(despues) - np.median(antes))


def salto(medianas, k: int, umbrales) -> float | None:
    """D(k) = mediana de M en los meses válidos de después − la de antes; None si no se define (HOM-3)."""
    return _salto(_desde_tabla(medianas), int(k), umbrales)


def _k_del_maximo(ks: list[int], ds: list[float]) -> tuple[int, float] | None:
    """HOM-5 (D39): el k del mayor |D|; con empates exactos, el central (el más tardío de los dos centrales)."""
    if not ks:
        return None
    absd = [abs(d) for d in ds]
    tope = max(absd)
    empatados = [i for i, v in enumerate(absd) if v == tope]
    i = empatados[len(empatados) // 2]
    return ks[i], ds[i]


def _mejor_en_tramo(t: _Medianas, a: int, b: int, umbral: float, umbrales) -> tuple[int, float] | None:
    """El corte de mayor |D| ≥ umbral en el tramo [a, b] (HOM-4, HOM-5), o None."""
    minimo = umbrales.a("K4_TRAMO_MIN")
    sub = t.recortar(a, b)
    ks, ds = [], []
    for k in range(a + minimo, b - minimo + 2):         # k − a ≥ 12 y b − k + 1 ≥ 12
        d = _salto(sub, k, umbrales)
        if d is not None and abs(d) >= umbral:
            ks.append(k)
            ds.append(d)
    return _k_del_maximo(ks, ds)


def _segmentar(t: _Medianas, umbral: float, umbrales) -> list[tuple[int, float, int, int]]:
    """Segmentación binaria codiciosa (HOM-4): [(k, D, a, b)] en el orden de detección, con [a, b] el tramo partido."""
    extremos = t.con_datos()
    if extremos is None:
        return []
    tramos = [extremos]
    mejores: dict[tuple[int, int], tuple[int, float] | None] = {}
    quiebres: list[tuple[int, float, int, int]] = []
    while len(quiebres) < umbrales.a("K4_MAX_QUIEBRES"):
        elegido = None
        for tramo in sorted(tramos):
            if tramo not in mejores:
                mejores[tramo] = _mejor_en_tramo(t, tramo[0], tramo[1], umbral, umbrales)
            mejor = mejores[tramo]
            if mejor is not None and (elegido is None or abs(mejor[1]) > abs(elegido[1])):
                elegido = (mejor[0], mejor[1], tramo[0], tramo[1])
        if elegido is None:
            break
        k, _, a, b = elegido
        quiebres.append(elegido)
        tramos.remove((a, b))
        tramos.extend([(a, k - 1), (k, b)])
    return quiebres


def segmentar(medianas, umbral: float, umbrales) -> list[tuple[int, float]]:
    """Quiebres [(k, D)] en orden de k: hasta ``K4_MAX_QUIEBRES``, con tramos de ≥ ``K4_TRAMO_MIN`` meses (HOM-4)."""
    quiebres = _segmentar(_desde_tabla(medianas), float(umbral), umbrales)
    return sorted((int(k), float(d)) for k, d, _, _ in quiebres)


# ---------------------------------------------------------------------------
# K4 (§2.5)
# ---------------------------------------------------------------------------
def _columna(tabla, nombre: str) -> np.ndarray:
    if nombre not in tabla:
        raise ValueError(f"tabla_estacion sin la columna «{nombre}» (A4)")
    return np.asarray(tabla[nombre], dtype=np.float64)


def k4(tabla_estacion, p_F, z_cat: float, umbrales, *, codigo: str) -> ResultadoK4:
    """``tipos.ResultadoK4`` de una estación (§2.5, A4): quiebres de T2a y T2b, su clase, el último traslado y el
    último quiebre de barómetro (mes2000 del primer mes del tramo nuevo) y ``sin_prueba`` (HOM-6 a HOM-9). ``codigo``
    es obligatorio (HOM-9)."""
    if not isinstance(codigo, str):
        raise TypeError(f"codigo debe ser texto, no {type(codigo).__name__} (HOM-9)")
    if not codigo.strip():
        raise ValueError("k4 sin código de estación: el ResultadoK4 no se casaría con su estación (HOM-9, A5)")
    if "h" not in tabla_estacion:
        raise ValueError("tabla_estacion sin la columna «h» (A4)")
    h = _horas(np.asarray(tabla_estacion["h"]))
    _creciente(h, "tabla_estacion")
    ts, qfe, qff = (_columna(tabla_estacion, c) for c in ("Ts", "QFE", "QFF"))
    pf = np.asarray(p_F, dtype=np.float64)
    if pf.shape != h.shape:
        raise ValueError("p_F debe ir alineado con las filas de tabla_estacion (A2)")
    z = float(z_cat)
    if not np.isfinite(qfe).any():
        return ResultadoK4(codigo, (), None, None, True)

    tbar = ts + _KELVIN + _GAMMA_TBAR * z / _DIVISOR_TBAR          # NaN sin Ts o sin z_cat
    ok_a = np.isfinite(tbar) & np.isfinite(qfe) & np.isfinite(qff) & (qfe > 0) & (qff > 0)
    t2a = np.full(len(h), np.nan)
    t2a[ok_a] = _Z_IMPL * tbar[ok_a] * np.log(qff[ok_a] / qfe[ok_a])
    t2b = qfe - pf
    ok_b = np.isfinite(t2b)

    medias_a = _construir(h[ok_a], t2a[ok_a], umbrales)
    medias_b = _construir(h[ok_b], t2b[ok_b], umbrales)
    q_a = _segmentar(medias_a, umbrales.a(UMBRAL_K4[Estadistico.T2A]), umbrales)
    q_b = _segmentar(medias_b, umbrales.a(UMBRAL_K4[Estadistico.T2B]), umbrales)

    meses = mes2000(h)
    coinc = umbrales.a("K4_COINC_MESES")
    umbral_a = umbrales.a(UMBRAL_K4[Estadistico.T2A])
    umbral_b = umbrales.a(UMBRAL_K4[Estadistico.T2B])
    quiebres = []
    for k_b, d_b, a, b in q_b:
        en_tramo = ok_b & (meses >= a) & (meses <= b)
        p_media = float(qfe[en_tramo].mean())
        con_t = en_tramo & np.isfinite(tbar)
        t_media = float(tbar[con_t].mean()) if con_t.any() else float("nan")
        dz_b = -d_b * _R_SECO * t_media / (_GRAVEDAD * p_media)
        # EMC2-1 (HOM-7): el D(k) de T2a en el mes del quiebre de T2b, con las ventanas en el tramo que ese quiebre partió.
        dz_a = _salto(medias_a.recortar(a, b), k_b, umbrales)
        traslado = (bool(np.isfinite(dz_b)) and dz_a is not None and abs(dz_a) >= umbral_a
                    and abs(dz_a - dz_b) <= max(umbrales.a("K4_COINC_M"), umbrales.a("K4_COINC_FRAC") * abs(dz_b)))
        clase = ClaseQuiebre.TRASLADO if traslado else ClaseQuiebre.BAROMETRO
        quiebres.append(Quiebre(Estadistico.T2B.value, int(k_b), float(d_b), clase))
    for k_a, d_a, a, b in q_a:
        # EMC2-1 (HOM-7): «sin T2b» es sin quiebre de T2b a ≤ K4_COINC_MESES y sin D(k) de T2b que llegue a su umbral en
        # el mes de este quiebre, con las ventanas en el tramo que este quiebre de T2a partió.
        cerca = any(abs(k_a - k_b) <= coinc for k_b, _, _, _ in q_b)
        salto_b = _salto(medias_b.recortar(a, b), k_a, umbrales)
        con_t2b = cerca or (salto_b is not None and abs(salto_b) >= umbral_b)
        clase = None if con_t2b else ClaseQuiebre.METODO_REDUCCION
        quiebres.append(Quiebre(Estadistico.T2A.value, int(k_a), float(d_a), clase))
    quiebres.sort(key=lambda q: (q.mes, q.estadistico))

    def _ultimo(clase: ClaseQuiebre) -> int | None:
        meses_clase = [q.mes for q in quiebres if q.clase is clase]
        return max(meses_clase) if meses_clase else None

    return ResultadoK4(codigo, tuple(quiebres), _ultimo(ClaseQuiebre.TRASLADO), _ultimo(ClaseQuiebre.BAROMETRO),
                       False)


# ---------------------------------------------------------------------------
# Tramos homogéneos de los residuos (§4.8)
# ---------------------------------------------------------------------------
def _umbral_tramos(variable, umbrales) -> float:
    try:
        var = Variable(variable)
    except ValueError:
        raise ValueError(f"variable {variable!r}: §4.8 segmenta sólo T y Td") from None
    if var not in UMBRAL_TRAMOS:
        raise ValueError(f"variable {var.value!r}: viento y presión no se segmentan (§4.8)")
    return float(umbrales.a(UMBRAL_TRAMOS[var]))


def _residuo(h, residuo, nombre: str) -> tuple[np.ndarray, np.ndarray]:
    hh = _horas(h)
    _creciente(hh, nombre)
    r = np.asarray(residuo, dtype=np.float64)
    if r.shape != hh.shape:
        raise ValueError(f"{nombre}: residuo y h deben tener el mismo largo")
    return hh, r


def tramos_homogeneos(h, residuo, variable, umbrales) -> list[tuple[int, int]]:
    """Tramos [(desde_mes, hasta_mes)] en mes2000, inclusivos, del residuo de T o Td (§4.8; HOM-10)."""
    umbral = _umbral_tramos(variable, umbrales)
    hh, r = _residuo(h, residuo, "tramos_homogeneos")
    ok = np.isfinite(r)
    t = _construir(hh[ok], r[ok], umbrales)
    extremos = t.con_datos()
    if extremos is None:
        return []
    cortes = sorted(int(k) for k, _, _, _ in _segmentar(t, umbral, umbrales))
    desde = [extremos[0], *cortes]
    hasta = [k - 1 for k in cortes] + [extremos[1]]
    return list(zip(desde, hasta))


def _validar_tramos(tramos) -> list[tuple[int, int]]:
    salida = []
    for par in tramos:
        a, b = (int(x) for x in par)
        if a != par[0] or b != par[1] or b < a:
            raise ValueError(f"tramo inválido: {par!r}")
        if salida and a != salida[-1][1] + 1:
            raise ValueError("los tramos deben ir en orden y contiguos (HOM-10)")
        salida.append((a, b))
    return salida


def desplazamientos(h, residuo, tramos, umbrales) -> dict[int, float]:
    """{g: δ_s(g)} en las unidades del residuo (§4.8; HOM-11): δ = 0 sin quiebres; NaN si H*_δ queda vacío."""
    hh, r = _residuo(h, residuo, "desplazamientos")
    lista = _validar_tramos(tramos)
    if not lista:
        return {}
    if len(lista) == 1:
        return {0: 0.0}
    ok = np.isfinite(r)
    hv, rv = hh[ok], r[ok]
    t = _construir(hv, rv, umbrales)
    estable = np.ones(HORAS_DIA, dtype=bool)
    for a, b in lista:
        sub = t.recortar(a, b)
        cand = np.flatnonzero(sub.pares >= umbrales.a("K4_MIN_PARES"))
        if len(cand) == 0:
            estable[:] = False
            break
        n_h = np.isfinite(sub.med[cand]).sum(axis=0)
        estable &= n_h * PORCIENTO >= umbrales.a("K4_HORAS_PCT") * len(cand)
    if not estable.any():
        return {g: float("nan") for g in range(len(lista))}
    horas = np.flatnonzero(estable)
    hora = hora_utc(hv)
    meses = mes2000(hv)
    total = np.array([np.median(rv[hora == x]) for x in horas])
    salida = {}
    for g, (a, b) in enumerate(lista):
        en_g = (meses >= a) & (meses <= b)
        del_tramo = np.array([np.median(rv[en_g & (hora == x)]) for x in horas])
        salida[g] = float(np.mean(del_tramo - total))
    return salida


__all__: tuple[str, ...] = (
    "COLUMNA_PARES", "COLUMNAS_HORA", "HORAS_DIA", "UMBRAL_K4", "UMBRAL_TRAMOS", "desplazamientos", "hora_utc",
    "horas_estables", "k4", "medianas_mes_hora", "mes2000", "salto", "segmentar", "tramos_homogeneos",
)
