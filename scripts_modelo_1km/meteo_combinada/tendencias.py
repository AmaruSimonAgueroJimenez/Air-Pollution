"""Prueba de tendencias falsas (§5.7) y TF de contaminantes (Anexo B).

Los Δ_c y Δτ_c por comuna se calculan en memoria; no hay tablas ni mapas por comuna (§0.4.3). El módulo es puro: recibe
tablas, arreglos, ``tipos.DatosCompetencia`` y los umbrales (un objeto con ``.a`` y ``.frac``) y devuelve tablas y
diccionarios; no lee ni escribe archivos (§0, regla 8). El producto de cada candidato se arma aquí, con ``candidatos`` y
``fondo_era5l`` (acuerdo A20: no se importa ``producto``).

Qué hace cada parte (y para qué compuerta):
- Redes (§5.7): ``red_historica`` (TF1), ``red_constante`` (TF2, con las tres reglas y «ninguna», EMC1-2) y
  ``escenarios_tf`` (``EscenariosTF``: qué red rige en cada escenario y año).
- Medias comunales por lotes (PED-6, MC-37): ``medias_comuna_anio`` (las sumas de un lote de un mes UTC y de celdas),
  ``AcumuladorComunas`` y ``MediasComunaAnio``.
- El producto de cada candidato por lotes (M3-4, paso 9; S6): ``CeldasTF``, ``celdas_tf``, ``PasadaTF`` (``sumas_mes``,
  ``acumular`` y ``correr``) y ``producto_tf``.
- La prueba: ``delta_tf1``, ``delta_tf2``, ``media_p95_ponderados``, ``tf1``, ``tf2``, ``comprobar_cero``,
  ``resultados_tf``, ``tf_por_uso`` y ``filas_tf`` (``tipos.ESQUEMA_TF``, la tabla que lee ``decision``).
- S6 y la compuerta de deriva (M1): ``combinaciones_nucleo``, ``etiqueta_hiper``, ``compuerta_deriva`` y
  ``contenido_deriva_s6`` (el contenido de ``deriva_s6.json``, clase resumen; lo escribe ``salidas``).
- Anexo B (M6; S16): ``dias_tf_contaminantes``, ``muestra_tf_contaminantes`` y ``tf_contaminantes``.

Dueño: I15 (ola 4).
Lecturas propias (TEN-n), para el addendum de M1:
- TEN-1. **Horas válidas** (§5.7: «horas válidas de v»). ``horas_validas_anio`` es año → tabla con ``codigo`` y
  ``horas`` (las horas válidas de v ese año: la forma de ``estaciones_por_anio`` de ``validacion.pi_poblacion``) o año →
  {código: horas}. v es T, Td, rapidez o p: las horas con ``valido_T``, ``valido_Td``, ``valido_viento`` y ``valido_p``
  de la tabla ancha, que cuenta quien llama. Un año que la regla mira y no viene es un error (no se supone 0); un
  código que no viene en un año tiene 0 horas ese año.
- TEN-2. **Red histórica** (§5.7: «las estaciones con ≥ 2.000 horas válidas de v en 2000-2009»): la suma de las horas
  válidas de los diez años ≥ 2.000 (``TF1_RED_HISTORICA``).
- TEN-3. **Red constante** (§5.7 y MC-47: «≥ 50 % de horas válidas de v en ≥ 22 de los 26 años 2000-2025. Con < 10
  estaciones: en ≥ 80 % de los años 2003-2025. Con < 10 todavía: en ≥ 80 % de los años 2010-2025, con la misma cota
  por década»). Un año cuenta si 100·horas ≥ 50·(horas UTC del año: 8.760 u 8.784; MC-47). r2000_2025: ≥ 22 años de
  los 26; r2003_2025: 100·k ≥ 80·23 (k ≥ 19); r2010_2025: 100·k ≥ 80·16 (k ≥ 13); todo en enteros. Rige la primera,
  en ese orden, con ≥ 10 estaciones. «Con la misma cota por década» se lee como las cotas de TF2, que van por década y
  no cambian con un período más corto («cota» es, en §5.7, siempre la de la tabla de TF; pregunta P-TEN-2). Si
  ninguna alcanza 10: regla «ninguna», y la red que se devuelve es la de r2010_2025 (< 10 estaciones), cuyo tamaño va a
  ``n_red`` (EMC1-2 y DEC-5 exigen ``n_red`` < 10 con «ninguna»).
- TEN-4. **Escenarios** (§5.7; S6-5 de la coordinación, TEN-16). A, r̄, δ, las filas y los coeficientes de C y C_est
  son los del producto con la red completa (los de ``DatosCompetencia``, con todas las estaciones de entrenamiento), y
  la lista de 30 vecinos de cada celda es la de la red completa. Un escenario sólo cambia qué estaciones están
  disponibles: s ∈ red(año) y q_s(u) definido. «completo»: todas; «cambio»: la red histórica en 2015-2019 y todas en
  2020-2024 (en esos años es idéntico a «completo»: el cálculo se hace una vez y se comparte); «constante»: la red
  constante en los años de su regla. Dos escenarios con la misma red efectiva en un mes (la red ∩ las estaciones con
  algún q en el mes) dan el mismo cálculo, que se hace una vez (en S6, «completo» y «constante» en 2000-2009). A, C y
  C_est no miran la red, pero su producto se calcula aparte en cada escenario (TEN-10).
- TEN-5. **El producto de v** (§4.1, §5.7: «sobre el producto de cada candidato, no sobre R»): T = T_F + R_T;
  Td = mín(Td_F + R_Td, T_F + R_T); rapidez = √((u_F + R_u)² + (v_F + R_v)²); p = p_F·exp(R_p): las fórmulas de
  ``fondo_era5l.producto_desde``, copiadas por costo con su prueba de paridad (A20). Todas las R del producto de v usan
  la red del escenario de v; también R_T en el de Td (pregunta P-TEN-3).
- TEN-6. **Medias comunales** (§5.7: «resumido por comuna y año con medias ponderadas»; MC-37). La media de un año es la
  media ponderada por w_ghs de 2020 sobre las celda-horas del año con producto finito. Lote: un mes UTC y
  ``LOTE_PUNTOS_TF`` celdas; sumas en float64; orden fijo de agregación: mes, lote de celdas y comuna (``np.bincount`` en
  el orden de las celdas). Las celdas con w_ghs ≤ 0 o con ``cod_comuna`` ≤ 0 no entran: sin población, o sin comuna
  que las resuma (D9, D20).
- TEN-7. **TF1** (MC-47: «Δ_c es la diferencia de las medias de las medias anuales»): Δ_c = [media de las medias anuales
  2020-24 − ídem 2015-19]_cambio − [ídem]_completo, sobre los años con media finita en los dos escenarios. Una comuna
  sin ningún año en uno de los dos períodos queda fuera, y se cuenta.
- TEN-8. **TF2** (§5.7: «la pendiente MCO de las medias anuales (por década) en los dos escenarios; Δτ_c es su
  diferencia»; MC-47: «sobre los años de la regla que rigió»): la pendiente contra el año (entero) por 10, en los años
  de la regla con media finita en los dos escenarios (al menos 2; en S6, 2000-2024, porque S6 no tiene horas de
  2025); Δτ_c = pendiente(constante) − pendiente(completo).
- TEN-9. **Media y P95** (MC-48): sobre las comunas con Δ finito, con el peso Σ w_ghs de 2020 de la comuna (de todas sus
  celdas pobladas); P95 = ``numerico.cuantil_ponderado(|Δ|, W, 0,95)``, el menor valor cuyo peso acumulado alcanza 0,95,
  sin interpolar. «Pasa» si media ≤ cota y P95 ≤ cota, con las cotas de ``constantes.TF_COTAS_*``, tal como las compara
  DEC-5.
- TEN-10. **A, C y C_est** (§5.7: «dan artefacto 0 por construcción. Se calcula igual, y un valor > 10⁻⁶ es un error de
  código»): su TF se calcula con el mismo camino que la de B y AB; «un valor» se lee como cualquiera: la media, el P95
  o el máximo de |Δ_c| (o |Δτ_c|) sobre las comunas > ``TF_CERO_TOL`` lanza ``ErrorTendencias`` (errata de §10) antes
  de armar ninguna fila. El borde exacto no es error (como DEC-5). La comprobación de A es estructural: Φ de A no
  depende de la red (sólo de r̄ y de la lista fija de vecinos), así que su producto es, bit a bit, el mismo en los dos
  escenarios; lo que vigila es el resto del camino (el fondo, las medias y las diferencias), no el método de A.
- TEN-11. **TF2 no evaluable** (EMC1-2, D4): filas de TF2 «no_evaluable» para todos los candidatos de la variable, con
  media y P95 NaN, las cotas de §5.7, la red «ninguna» y el ``n_red`` de TEN-3. TF1 se calcula igual y nunca es «no
  evaluable». Las filas de TF1 llevan la red y el ``n_red`` de TF2 de su variable (``ESQUEMA_TF``: «la de TF2 que
  rigió»), como ``sintetico.tablas_metricas``.
- TEN-12. **Usos** (MC-04, MC-55; DEC-1). Ambiental: A, B, AB y C en T, Td, rapidez y p, con z_media. Agudo: A, B, AB y
  C en T y Td, con z_poblada. Crónico: A, B y AB en T, que son las mismas filas del agudo (mismos hiperparámetros y z
  poblada: se calcula una vez), y C_est en T. Son dos pasadas, la ambiental y la de salud (``tf_por_uso``).
- TEN-13. **A, B y AB por lotes.** A: Φ(r̄) de 12 × 24 por celda con ``candidatos.sumas_nucleo`` sobre las filas (mes,
  hora) que el lote usa (su mes y los vecinos) y la interpolación de MC-41 (CAN-5) copiada de ``candidatos``: la prueba
  de paridad exige igualdad bit a bit con ``candidatos.correccion_a``. B y AB: ``candidatos.matriz_q`` y
  ``sumas_nucleo`` una vez por (L, λ), con κ al final (lo mismo que ``campo``, bit a bit). AB = A (con sus
  hiperparámetros) + Φ′ (con los suyos).
- TEN-14. **C y C_est por lotes.** R = X·(T·coef), con X = ``candidatos.diseno_c`` de cada celda y
  T = ``candidatos.diseno_estandarizado(I)``: es la cuenta de ``predecir_c``, (X·T)·coef, asociada al revés por costo
  (paridad ≤ 10⁻⁹ K). Estado de C en la celda (§4.6): T_F, T_F − Td_F, √(u_F² + v_F²) y la amplitud de T_F en su día
  UTC (``fondo_era5l.amplitud_dia_utc`` sobre el lote, que trae días enteros). C_est (§4.7): el clima del estado de la
  celda (``CeldasTF.clima_estado``, que arma quien llama con ``fondo_era5l.clima_en_puntos`` y el operador de la celda,
  D29). El diseño se arma celda por celda: hacerlo para todas las celdas del lote en una llamada a ``diseno_c`` (una fila
  de estáticos por hora) da los mismos números pero hoy es más lento, 1,05 frente a 0,54 ms por celda-mes (89 de 158 ms
  son las indicadoras de macrozona, fila por fila; el resto, los monomios, cuesta lo mismo de las dos formas; H7).
- TEN-15. **S6-4** (coordinación, D15): «cada afirmación de S6 y la compuerta se evalúan en las 60 combinaciones de
  §4.2, y B o AB pasan la compuerta sólo si cumplen las dos cotas de TF2 en las 60». En AB las 60 son las de Φ′, y A va
  con la misma (L, λ, κ): A es el mismo en los dos escenarios y se cancela en Δ_c y en Δτ_c (una prueba lo comprueba con
  otra A). C y C_est, que no tienen (L, λ, κ), se evalúan en sus 5 α (``C_ALFAS``).
- TEN-16. **S6-5** (coordinación, D15): «A, las climatologías r̄, los δ y los coeficientes de C y de C_est son los del
  producto con la red completa, en TF1 […] y en TF2 […]. En B y AB la lista de 30 vecinos es la de la red completa, fija
  por punto (§4.2), y el escenario sólo cambia qué estaciones están disponibles en cada hora». Es lo de TEN-4.
- TEN-17. **«AB pasa con sesgos estacionarios»** (§9, S6): AB pasa TF1 y TF2 sin deriva, en las 60 (la lectura más
  estricta: el texto no dice cuál de las dos).
- TEN-18. **Compuerta de deriva** (§5.7, S6): TF2 de B y AB con la red de S6 y una deriva del fondo de
  ``DERIVA_K_DECADA`` por década; cada uno pasa si su TF2 «pasa» en las 60 (S6-4). Una TF2 no evaluable en S6 lanza
  ``ErrorTendencias`` (EMC1-2: «debe dar TF2 evaluable (si no, S6 falla)»). ``contenido_deriva_s6`` da el contenido de
  ``deriva_s6.json``: media y P95 de TF2 frente a sus cotas por candidato y combinación, la peor, el resultado y la red.
- TEN-19. **Muestra de contaminantes** (Anexo B: «hasta 50 celdas por comuna, con probabilidad proporcional a w_ghs
  (semilla 20261023), y los días con mód 11 = 3»; MC-44). Por comuna (``cod_comuna`` > 0), entre sus celdas con
  w_ghs > 0 en orden de celda: todas si son ≤ ``M6_CELDAS_COMUNA``; si no, ésas sin reposición con ``Generator.choice``
  (p = w_ghs/Σ w_ghs) y ``numerico.generador(SEMILLA, "tf_contaminantes", <cod_comuna>)``, cuya etiqueta exacta es
  «tf_contaminantes/<cod_comuna>» (por ejemplo «tf_contaminantes/13101»): la subsecuencia de la etiqueta
  «tf_contaminantes» de MC-44, una por comuna, para que ninguna muestra dependa del orden. «Con probabilidad
  proporcional a w_ghs» se lee como el sorteo sucesivo de ``choice``: en cada extracción, la probabilidad de una celda
  que queda es proporcional a su w_ghs. La probabilidad de inclusión no es proporcional a w_ghs (con 50 de 70 celdas,
  la de mayor peso entra ≈ 6,8 veces más que la de menor aunque pesa 20 veces más; revisor de la ola 4): pregunta
  P-TEN-6, junto a P-TEN-1. Días: d2000 mód ``SEL_MOD`` = ``SEL_RESTO`` (los ids de la fila M6), con d2000 el día de la
  predicción de la fábrica.
- TEN-20. **TF de contaminantes** (Anexo B: «TF1 aplicada a la predicción del contaminante, en una muestra fija»): la TF1
  de TEN-7 sobre la predicción en la muestra y en los días de 2015-2024, con las medias comunales ponderadas por w_ghs
  como en §5.7 (pregunta P-TEN-1); «cambio» en 2020-2024 es «completo» y no se pide otra vez a la fábrica. Cotas:
  ``U.frac("M6_TF_MEDIA_PCT")`` y ``U.frac("M6_TF_P95_PCT")`` por la media nacional ponderada 2015-2024 del escenario
  completo, Σ_c W_c·m̄_c / Σ_c W_c, con m̄_c la media de las medias anuales y W_c el peso de MC-48. Por lotes de un mes.
  La fábrica recibe el nombre del escenario y arma sus columnas con la red de cada variable (TEN-4; ``ambiental``).
  Supuesto: la fábrica no usa rezagos de la meteorología (la predicción de un día depende sólo de las columnas de ese
  día). Si los usara, «cambio» en los primeros días de 2020 dependería de 2019, que no es «completo», y no podría
  tomarse de «completo»; quien conecte la fábrica de v2 debe comprobarlo.
- TEN-21. **Verificación de un mes** (Anexo B: «con A o C es 0 por construcción y se verifica en un mes»; DEC-14): la TF
  de I con ganadores A o C se verifica en el primer mes de 2015-2019 con días de la muestra (desde ese mes difieren
  los escenarios): «pasa» si máx |predicción(cambio) − predicción(completo)| ≤ ``TF_CERO_TOL``; si no, es un error de
  código y lanza ``ErrorTendencias`` (pregunta P-TEN-4).
- TEN-22. **Reproducibilidad** (MC-37, S9). Los lotes son fijos (un mes UTC y ``LOTE_PUNTOS_TF`` celdas);
  ``PasadaTF.sumas_mes`` depende sólo de su mes y ``acumular`` suma los meses en su orden: con 1 u 8 procesos (repartidos
  por meses) el resultado es el mismo, bit a bit.
Preguntas abiertas (P-TEN-n; con su cita, problema y propuesta en el informe de la ola 4): P-TEN-1, el doble peso de
w_ghs en la TF de contaminantes (rige la literal, TEN-20); P-TEN-2, «con la misma cota por década» (rige TEN-3);
P-TEN-3, la red de R_T en el producto de Td (rige TEN-5); P-TEN-4, el mes y la tolerancia de la verificación (rige
TEN-21); P-TEN-5, AB fuera de E0 por la compuerta de deriva con S6-4 (rige S6-4); P-TEN-6, la probabilidad de
inclusión del sorteo sucesivo de la muestra de contaminantes (rige TEN-19).
Depende de: tipos, constantes, numerico, candidatos y fondo_era5l. Los umbrales llegan como objeto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from meteo_combinada import candidatos, constantes, fondo_era5l, numerico, tipos
from meteo_combinada.tipos import Candidato, Hiper, Prueba, ReglaRedConstante, ResultadoTF, Uso, VariableMetrica

HORAS_DIA = 24
MESES_ANIO = 12
ANIOS_POR_DECADA = 10            # no-umbral: años de una década, la unidad de la pendiente de TF2 (§5.7)
LOTE_PUNTOS_TF = 4096            # celdas por lote (PED-6, MC-37): fijo, para que la suma no dependa de los procesos
_CITADOS = 5                     # no-umbral: elementos citados en un mensaje de error
_EPOCA_H = np.datetime64("2000-01-01T00", "h")       # h = 0 (tipos.EPOCA_H)
_EPOCA_D = np.datetime64("2000-01-01", "D")          # d2000 = 0 (MC-44)
_EPOCA_M = np.datetime64("2000-01", "M")
_EPOCA_Y = np.datetime64("2000", "Y")
_ANIO_EPOCA = int(str(_EPOCA_Y))

V_T, V_TD, V_RAPIDEZ, V_P = (VariableMetrica.T.value, VariableMetrica.TD.value, VariableMetrica.RAPIDEZ.value,
                             VariableMetrica.P.value)
VARIABLES_TF = (V_T, V_TD, V_RAPIDEZ, V_P)                          # §5.7: «en T, Td, rapidez y p»
# Variables del producto (tipos.Variable) que hacen falta para el producto de cada variable de TF (TEN-5).
PRODUCTO_DE: Mapping[str, tuple[str, ...]] = {V_T: ("T",), V_TD: ("T", "Td"), V_RAPIDEZ: ("u", "v"), V_P: ("p",)}
VARIABLES_PRODUCTO = tuple(v.value for v in tipos.Variable)
COTAS_TF: Mapping[str, str] = {V_T: "TF_COTAS_T", V_TD: "TF_COTAS_TD", V_RAPIDEZ: "TF_COTAS_RAPIDEZ",
                               V_P: "TF_COTAS_P"}
CAMBIO, COMPLETO, CONSTANTE = "cambio", "completo", "constante"
ESCENARIOS = (CAMBIO, COMPLETO, CONSTANTE)
PRUEBAS = (Prueba.TF1.value, Prueba.TF2.value)
NINGUNA = ReglaRedConstante.NINGUNA.value
A, B, AB, C, C_EST = (c.value for c in (Candidato.A, Candidato.B, Candidato.AB, Candidato.C, Candidato.C_EST))
CERO_POR_CONSTRUCCION = (A, C, C_EST)          # §5.7: «A, C y C_est dan artefacto 0 por construcción»
CON_DERIVA = (B, AB)                           # §5.7: la compuerta de deriva
DE_C = (C, C_EST)
# §6.1 y MC-04 (DEC-1): candidatos y variables de TF de cada uso; una prueba los compara con ``decision``.
CANDIDATOS_USO: Mapping[str, tuple[str, ...]] = {Uso.AMBIENTAL.value: (A, B, AB, C), Uso.AGUDO.value: (A, B, AB, C),
                                                 Uso.CRONICO.value: (A, B, AB, C_EST)}
VARIABLES_USO: Mapping[str, tuple[str, ...]] = {Uso.AMBIENTAL.value: VARIABLES_TF, Uso.AGUDO.value: (V_T, V_TD),
                                                Uso.CRONICO.value: (V_T,)}
ESQUEMA_DERIVA_S6 = "meteo-combinada-deriva-s6/1"
# TEN-19: la muestra fija de la TF de contaminantes (un arreglo estructurado, una fila por celda).
DTYPE_MUESTRA = np.dtype([("celda", "i8"), ("cod_comuna", "i4"), ("w_ghs", "f8"), ("peso_comuna", "f8")])


class ErrorTendencias(ValueError):
    """Entrada mal formada o un error de código de la TF (TEN-10: A, C o C_est con artefacto > 10⁻⁶)."""


# ---------------------------------------------------------------------------
# Tiempo
# ---------------------------------------------------------------------------
def _horas(h, nombre: str = "h") -> np.ndarray:
    arr = np.asarray(h)
    if arr.ndim != 1:
        raise ErrorTendencias(f"{nombre} debe ser de una dimensión")
    if arr.dtype == bool or not np.issubdtype(arr.dtype, np.integer):
        raise ErrorTendencias(f"{nombre} debe ser entero (horas desde 2000-01-01T00Z), no {arr.dtype}")
    return arr.astype(np.int64)


def _crecientes(h: np.ndarray, nombre: str) -> None:
    if h.size > 1 and not bool(np.all(np.diff(h) > 0)):
        raise ErrorTendencias(f"{nombre}: las horas deben ir crecientes y sin repetir")


def anio_de(h) -> np.ndarray:
    """Año UTC de cada hora (horas desde 2000-01-01T00Z)."""
    hh = _horas(h)
    return ((_EPOCA_H + hh.astype("timedelta64[h]")).astype("datetime64[Y]") - _EPOCA_Y).astype(np.int64) + _ANIO_EPOCA


def mes2000(h) -> np.ndarray:
    """Meses desde enero de 2000 del instante UTC de cada hora (como ``homogeneidad.mes2000``, HOM-1)."""
    hh = _horas(h)
    return ((_EPOCA_H + hh.astype("timedelta64[h]")).astype("datetime64[M]") - _EPOCA_M).astype(np.int64)


def horas_del_anio(anio: int) -> int:
    """Horas UTC del año (8.760 u 8.784; MC-47)."""
    a = int(anio)
    return int((np.datetime64(f"{a + 1}-01-01T00", "h") - np.datetime64(f"{a}-01-01T00", "h")).astype(np.int64))


def _d2000_de_fecha(anio: int, mes: int = 1, dia: int = 1) -> int:
    return int((np.datetime64(f"{int(anio):04d}-{int(mes):02d}-{int(dia):02d}", "D") - _EPOCA_D).astype(np.int64))


def _anio_de_dia(d: np.ndarray) -> np.ndarray:
    return ((_EPOCA_D + d.astype("timedelta64[D]")).astype("datetime64[Y]") - _EPOCA_Y).astype(np.int64) + _ANIO_EPOCA


def _mes_de_dia(d: np.ndarray) -> np.ndarray:
    return ((_EPOCA_D + d.astype("timedelta64[D]")).astype("datetime64[M]") - _EPOCA_M).astype(np.int64)


def _variable_tf(variable) -> str:
    v = VariableMetrica(variable).value
    if v not in VARIABLES_TF:
        raise ErrorTendencias(f"{v!r} no es una variable de TF; son {VARIABLES_TF} (§5.7)")
    return v


# ---------------------------------------------------------------------------
# Redes (§5.7; TEN-1 a TEN-3)
# ---------------------------------------------------------------------------
def _entero_no_negativo(x, donde: str) -> int:
    if isinstance(x, bool):
        raise ErrorTendencias(f"{donde}: horas booleanas")
    try:
        valor = float(x)
    except (TypeError, ValueError):
        raise ErrorTendencias(f"{donde}: horas no numéricas: {x!r}") from None
    if not (math.isfinite(valor) and valor >= 0 and valor == int(valor)):
        raise ErrorTendencias(f"{donde}: las horas válidas son un entero ≥ 0, no {x!r}")
    return int(valor)


def _horas_validas(horas_validas_anio, anios: Iterable[int]) -> dict[int, dict[str, int]]:
    """TEN-1: {año: {código: horas válidas}} de los años pedidos (todos deben venir)."""
    if not isinstance(horas_validas_anio, Mapping):
        raise ErrorTendencias("horas_validas_anio: año → tabla (codigo, horas) o año → {código: horas} (TEN-1)")
    por_anio = {int(k): v for k, v in horas_validas_anio.items()}
    salida: dict[int, dict[str, int]] = {}
    for anio in anios:
        if anio not in por_anio:
            raise ErrorTendencias(f"horas_validas_anio: falta el año {anio} (TEN-1: no se supone 0)")
        tabla = por_anio[anio]
        if isinstance(tabla, pd.DataFrame):
            faltan = [c for c in ("codigo", "horas") if c not in tabla.columns]
            if faltan:
                raise ErrorTendencias(f"horas_validas_anio[{anio}]: faltan {faltan}")
            pares = list(zip(tabla["codigo"].astype(str), tabla["horas"].tolist()))
        elif isinstance(tabla, Mapping):
            pares = [(str(c), n) for c, n in tabla.items()]
        else:
            raise ErrorTendencias(f"horas_validas_anio[{anio}]: tabla o mapa, no {type(tabla).__name__}")
        d: dict[str, int] = {}
        tope = horas_del_anio(anio)
        for c, n in pares:
            if not tipos.PATRON_CODIGO.fullmatch(c):
                raise ErrorTendencias(f"horas_validas_anio[{anio}]: código inválido {c!r}")
            if c in d:
                raise ErrorTendencias(f"horas_validas_anio[{anio}]: {c} repetido")
            n = _entero_no_negativo(n, f"horas_validas_anio[{anio}][{c}]")
            if n > tope:
                raise ErrorTendencias(f"horas_validas_anio[{anio}][{c}] = {n} > {tope} horas del año")
            d[c] = n
        salida[anio] = d
    return salida


def red_historica(horas_validas_anio, variable, umbrales) -> frozenset[str]:
    """Red histórica de v (§5.7, TF1; TEN-2): las estaciones con ≥ 2.000 horas válidas de v en 2000-2009."""
    _variable_tf(variable)
    minimo, desde, hasta = constantes.valor("TF1_RED_HISTORICA")
    hv = _horas_validas(horas_validas_anio, range(desde, hasta + 1))
    total: dict[str, int] = {}
    for anio in range(desde, hasta + 1):
        for c, n in hv[anio].items():
            total[c] = total.get(c, 0) + n
    return frozenset(c for c, n in total.items() if n >= minimo)


def _reglas_red() -> tuple[tuple[str, int, int, Callable[[int, int], bool]], ...]:
    """Las tres reglas de la red constante, en su orden (TEN-3): (regla, desde, hasta, cumple(k, años))."""
    _, min_anios, n_anios, d0, h0 = constantes.valor("TF2_RED_R2000_2025")
    if h0 - d0 + 1 != n_anios:
        raise ErrorTendencias("TF2_RED_R2000_2025: el período no tiene los años que dice el texto")
    p3, d3, h3 = constantes.valor("TF2_RED_R2003_2025")
    p10, d10, h10 = constantes.valor("TF2_RED_R2010_2025")
    return ((ReglaRedConstante.R2000_2025.value, d0, h0, lambda k, n: k >= min_anios),
            (ReglaRedConstante.R2003_2025.value, d3, h3, lambda k, n: 100 * k >= p3 * n),
            (ReglaRedConstante.R2010_2025.value, d10, h10, lambda k, n: 100 * k >= p10 * n))


def anios_regla(regla) -> tuple[int, int]:
    """(desde, hasta) de una regla de la red constante (MC-47: la pendiente se toma sobre esos años)."""
    regla = ReglaRedConstante(regla).value
    for r, desde, hasta, _ in _reglas_red():
        if r == regla:
            return int(desde), int(hasta)
    raise ErrorTendencias("la regla «ninguna» no tiene años: TF2 no es evaluable (EMC1-2)")


def red_constante(horas_validas_anio, variable, umbrales) -> tuple[frozenset[str], str]:
    """(red, regla que rigió) de la red constante de v (§5.7, TF2; TEN-3). Con TF2 no evaluable, la regla «ninguna» y
    la red de r2010_2025 (< 10 estaciones; EMC1-2)."""
    _variable_tf(variable)
    pct = constantes.valor("TF2_RED_R2000_2025")[0]
    minimo = constantes.valor("TF2_RED_MIN_ESTACIONES")
    reglas = _reglas_red()
    desde = min(r[1] for r in reglas)
    hasta = max(r[2] for r in reglas)
    hv = _horas_validas(horas_validas_anio, range(desde, hasta + 1))
    codigos = sorted(set().union(*(set(d) for d in hv.values())))
    califica = {a: {c for c, n in hv[a].items() if 100 * n >= pct * horas_del_anio(a)} for a in hv}
    red: frozenset[str] = frozenset()
    for regla, d, h, cumple in reglas:
        n_anios = h - d + 1
        red = frozenset(c for c in codigos if cumple(sum(c in califica[a] for a in range(d, h + 1)), n_anios))
        if len(red) >= minimo:
            return red, regla
    return red, NINGUNA


@dataclass(frozen=True)
class EscenariosTF:
    """Las redes de los escenarios de TF1 y TF2 de una variable (§5.7; TEN-4). ``red`` da None para «todas»."""
    variable: str
    historica: frozenset[str]
    constante: frozenset[str]
    regla: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable", _variable_tf(self.variable))
        object.__setattr__(self, "regla", ReglaRedConstante(self.regla).value)
        for nombre in ("historica", "constante"):
            if not isinstance(getattr(self, nombre), frozenset):
                raise ErrorTendencias(f"EscenariosTF.{nombre} debe ser un frozenset de códigos")

    @property
    def evaluable(self) -> bool:
        return self.regla != NINGUNA

    @property
    def n_red(self) -> int:
        return len(self.constante)

    def anios(self, escenario: str, pruebas: Sequence[str] = PRUEBAS) -> tuple[int, ...]:
        """Años en que se calcula cada escenario para las ``pruebas`` pedidas."""
        if escenario not in ESCENARIOS:
            raise ErrorTendencias(f"escenario {escenario!r}; son {ESCENARIOS}")
        c0, c1, c2, c3 = constantes.valor("TF1_ESCENARIO_CAMBIO")
        k0, k1 = constantes.valor("TF1_ESCENARIO_COMPLETO")
        con_tf1 = Prueba.TF1.value in pruebas
        con_tf2 = Prueba.TF2.value in pruebas and self.evaluable
        anios: set[int] = set()
        if escenario == CAMBIO and con_tf1:
            anios |= set(range(c0, c1 + 1)) | set(range(c2, c3 + 1))
        if escenario == CONSTANTE and con_tf2:
            anios |= set(range(*_rango(anios_regla(self.regla))))
        if escenario == COMPLETO:
            if con_tf1:
                anios |= set(range(k0, k1 + 1))
            if con_tf2:
                anios |= set(range(*_rango(anios_regla(self.regla))))
        return tuple(sorted(anios))

    def red(self, escenario: str, anio: int) -> frozenset[str] | None:
        """La red del escenario en el año (None: todas las de entrenamiento)."""
        c0, c1, _, _ = constantes.valor("TF1_ESCENARIO_CAMBIO")
        if escenario == COMPLETO:
            return None
        if escenario == CAMBIO:
            return self.historica if c0 <= anio <= c1 else None
        if escenario == CONSTANTE:
            return self.constante
        raise ErrorTendencias(f"escenario {escenario!r}; son {ESCENARIOS}")


def _rango(par: tuple[int, int]) -> tuple[int, int]:
    return par[0], par[1] + 1


def escenarios_tf(horas_validas_anio, variable, umbrales) -> EscenariosTF:
    """Las redes histórica y constante de v y la regla que rigió (§5.7; TEN-2 a TEN-4)."""
    v = _variable_tf(variable)
    constante, regla = red_constante(horas_validas_anio, v, umbrales)
    return EscenariosTF(variable=v, historica=red_historica(horas_validas_anio, v, umbrales), constante=constante,
                        regla=regla)


# ---------------------------------------------------------------------------
# Medias comunales por lotes (TEN-6; PED-6, MC-37)
# ---------------------------------------------------------------------------
def _sumas_comuna(x: np.ndarray, w: np.ndarray, indice: np.ndarray, n_comunas: int) -> np.ndarray:
    """(Σ w·x, Σ w) por comuna sobre los valores finitos de x (tiempo × punto), en el orden de los puntos."""
    finito = np.isfinite(x)
    suma = np.where(finito, x, 0.0).sum(axis=0)
    cuenta = finito.sum(axis=0).astype(np.float64)
    return np.vstack([np.bincount(indice, weights=w * suma, minlength=n_comunas),
                      np.bincount(indice, weights=w * cuenta, minlength=n_comunas)])


def _indice_comunas(comunas, orden) -> tuple[np.ndarray, np.ndarray]:
    com = np.asarray(comunas)
    if com.ndim != 1 or not np.issubdtype(com.dtype, np.integer):
        raise ErrorTendencias("comunas: un código entero por punto")
    orden = np.unique(com) if orden is None else np.asarray(orden)
    if orden.ndim != 1 or (orden.size > 1 and not bool(np.all(np.diff(orden) > 0))):
        raise ErrorTendencias("orden de comunas: códigos crecientes y sin repetir")
    j = np.searchsorted(orden, com)
    if com.size and (j.max() >= orden.size or not bool(np.all(orden[np.minimum(j, orden.size - 1)] == com))):
        raise ErrorTendencias("comunas: un código de punto que no está en el orden de comunas")
    return j.astype(np.int64), orden


def medias_comuna_anio(campo_lote, h, pesos_2020, comunas, *, orden=None) -> np.ndarray:
    """Sumas de la media comunal ponderada de un lote (un mes UTC × un lote de celdas; TEN-6): fila 0 Σ w·x y fila 1
    Σ w sobre las celda-horas con valor finito, por comuna en el ``orden`` dado (por omisión, los códigos de ``comunas``
    ordenados). La media del año es el cociente de las sumas de todos sus lotes. ``campo_lote`` es hora × celda,
    ``pesos_2020`` el w_ghs de 2020 (> 0) y ``comunas`` el código de comuna de cada celda."""
    x = np.asarray(campo_lote, dtype=np.float64)
    hh = _horas(h)
    w = np.asarray(pesos_2020, dtype=np.float64)
    if x.ndim != 2 or w.ndim != 1 or x.shape != (hh.size, w.size):
        raise ErrorTendencias(f"medias_comuna_anio: el campo es hora × celda ({hh.size} × {w.size}), no {x.shape}")
    if not (np.isfinite(w).all() and (w > 0).all()):
        raise ErrorTendencias("medias_comuna_anio: w_ghs de 2020 finito y > 0 (TEN-6)")
    if hh.size and np.unique(anio_de(hh)).size > 1:
        raise ErrorTendencias("medias_comuna_anio: un lote es de un solo año (un mes UTC, MC-37)")
    indice, orden = _indice_comunas(comunas, orden)
    if indice.size != w.size:
        raise ErrorTendencias("medias_comuna_anio: una comuna por celda")
    return _sumas_comuna(x, w, indice, orden.size)


@dataclass(frozen=True, eq=False)
class MediasComunaAnio:
    """Medias anuales por comuna de un escenario (en memoria; §0.4.3): comuna × año, NaN sin dato."""
    comunas: np.ndarray
    anios: np.ndarray
    media: np.ndarray

    def en(self, anios) -> np.ndarray:
        """Comuna × año en los ``anios`` pedidos (NaN en un año sin dato)."""
        pedidos = np.asarray(list(anios), dtype=np.int64)
        salida = np.full((self.comunas.size, pedidos.size), np.nan)
        j = np.searchsorted(self.anios, pedidos)
        ok = (j < self.anios.size) & (self.anios[np.minimum(j, max(self.anios.size - 1, 0))] == pedidos) \
            if self.anios.size else np.zeros(pedidos.shape, bool)
        salida[:, ok] = self.media[:, j[ok]]
        return salida


class AcumuladorComunas:
    """Suma, por clave y año, las sumas comunales de los lotes en el orden en que llegan (MC-37; TEN-22)."""

    def __init__(self, comunas) -> None:
        self.comunas = np.asarray(comunas)
        self._sumas: dict[Any, dict[int, np.ndarray]] = {}

    def sumar(self, clave, anio: int, sumas: np.ndarray) -> None:
        s = np.asarray(sumas, dtype=np.float64)
        if s.shape != (2, self.comunas.size):
            raise ErrorTendencias(f"sumas comunales de forma {s.shape}; se espera (2, {self.comunas.size})")
        por_anio = self._sumas.setdefault(clave, {})
        a = int(anio)
        por_anio[a] = por_anio[a] + s if a in por_anio else s.copy()

    def claves(self) -> tuple:
        return tuple(self._sumas)

    def medias(self, clave) -> MediasComunaAnio:
        por_anio = self._sumas.get(clave, {})
        anios = np.array(sorted(por_anio), dtype=np.int64)
        media = np.full((self.comunas.size, anios.size), np.nan)
        for k, a in enumerate(anios):
            num, den = por_anio[int(a)]
            with np.errstate(invalid="ignore", divide="ignore"):
                media[:, k] = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
        return MediasComunaAnio(comunas=self.comunas, anios=anios, media=media)


# ---------------------------------------------------------------------------
# TF1, TF2, media y P95 (TEN-7 a TEN-11)
# ---------------------------------------------------------------------------
def media_p95_ponderados(x, w) -> tuple[float, float]:
    """Media ponderada y P95 ponderado de x (MC-48: el menor valor cuyo peso acumulado alcanza 0,95, sin interpolar;
    ``numerico.cuantil_ponderado``). Quien llama pasa |Δ| y los pesos de las comunas (TEN-9)."""
    x = np.asarray(x, dtype=np.float64).ravel()
    w = np.asarray(w, dtype=np.float64).ravel()
    if x.shape != w.shape or x.size == 0:
        raise ErrorTendencias("media_p95_ponderados: x y w del mismo largo, al menos uno")
    if not (np.isfinite(x).all() and np.isfinite(w).all()) or (w < 0).any() or not w.sum() > 0:
        raise ErrorTendencias("media_p95_ponderados: valores finitos y pesos finitos ≥ 0 con suma > 0")
    q = constantes.valor("TF_PERCENTIL") / 100
    return float(np.sum(w * x) / np.sum(w)), numerico.cuantil_ponderado(x, w, q)


def _mismas_comunas(*medias: MediasComunaAnio) -> np.ndarray:
    base = medias[0].comunas
    for m in medias[1:]:
        if not np.array_equal(m.comunas, base):
            raise ErrorTendencias("los dos escenarios deben tener las mismas comunas, en el mismo orden")
    return base


def _media_en(M: np.ndarray, ok: np.ndarray) -> np.ndarray:
    n = ok.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, np.where(ok, M, 0.0).sum(axis=1) / np.where(n > 0, n, 1), np.nan)


def delta_tf1(cambio: MediasComunaAnio, completo: MediasComunaAnio) -> np.ndarray:
    """Δ_c por comuna (§5.7, MC-47; TEN-7): [media 2020-24 − media 2015-19]_cambio − [lo mismo]_completo, con las
    medias de las medias anuales sobre los años con media finita en los dos escenarios."""
    _mismas_comunas(cambio, completo)
    c0, c1, c2, c3 = constantes.valor("TF1_ESCENARIO_CAMBIO")
    antes, despues = range(c0, c1 + 1), range(c2, c3 + 1)
    Ca, Cd, Ka, Kd = cambio.en(antes), cambio.en(despues), completo.en(antes), completo.en(despues)
    ok_a = np.isfinite(Ca) & np.isfinite(Ka)
    ok_d = np.isfinite(Cd) & np.isfinite(Kd)
    return (_media_en(Cd, ok_d) - _media_en(Ca, ok_a)) - (_media_en(Kd, ok_d) - _media_en(Ka, ok_a))


def _pendientes(Y: np.ndarray, M: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """Pendiente MCO por fila (por año) de M contra Y en los años ``ok``; NaN con < 2 años."""
    n = ok.sum(axis=1)
    Yb = np.broadcast_to(Y.astype(np.float64), M.shape)
    with np.errstate(invalid="ignore", divide="ignore"):
        ym = np.where(ok, Yb, 0.0).sum(axis=1) / np.where(n > 0, n, 1)
        mm = np.where(ok, M, 0.0).sum(axis=1) / np.where(n > 0, n, 1)
        dt = np.where(ok, Yb - ym[:, None], 0.0)
        sxx = (dt * dt).sum(axis=1)
        sxy = (dt * np.where(ok, M - mm[:, None], 0.0)).sum(axis=1)
        return np.where((n >= 2) & (sxx > 0), sxy / np.where(sxx > 0, sxx, 1.0), np.nan)


def delta_tf2(constante: MediasComunaAnio, completo: MediasComunaAnio, anios) -> np.ndarray:
    """Δτ_c por comuna (§5.7; TEN-8): pendiente MCO de las medias anuales por década, constante − completo, en los
    ``anios`` de la regla con media finita en los dos escenarios."""
    _mismas_comunas(constante, completo)
    Y = np.asarray(list(anios), dtype=np.int64)
    K, M = constante.en(Y), completo.en(Y)
    ok = np.isfinite(K) & np.isfinite(M)
    return (_pendientes(Y, K, ok) - _pendientes(Y, M, ok)) * ANIOS_POR_DECADA


def _pesos_alineados(pesos_comuna, comunas: np.ndarray) -> np.ndarray:
    if isinstance(pesos_comuna, Mapping) or isinstance(pesos_comuna, pd.Series):
        mapa = {int(k): float(v) for k, v in pesos_comuna.items()}
        faltan = [int(c) for c in comunas if int(c) not in mapa]
        if faltan:
            raise ErrorTendencias(f"pesos_comuna: faltan las comunas {faltan[:_CITADOS]}")
        w = np.array([mapa[int(c)] for c in comunas], dtype=np.float64)
    else:
        w = np.asarray(pesos_comuna, dtype=np.float64)
        if w.shape != comunas.shape:
            raise ErrorTendencias("pesos_comuna: un peso por comuna, en el orden de las comunas")
    if not (np.isfinite(w).all() and (w > 0).all()):
        raise ErrorTendencias("pesos_comuna: Σ w_ghs de 2020 de cada comuna, finito y > 0 (MC-48)")
    return w


def _cotas(variable: str, prueba: str) -> tuple[float, float]:
    t1m, t1p, t2m, t2p = constantes.valor(COTAS_TF[variable])          # (TF1 media, TF1 P95, TF2 media, TF2 P95)
    return (t1m, t1p) if prueba == Prueba.TF1.value else (t2m, t2p)


def _cumple(media: float, p95: float, cota_media: float, cota_p95: float) -> bool:
    """«Pasa si se cumplen las dos cotas» (§5.7, Anexo B): media ≤ cota y P95 ≤ cota; el borde pasa (TEN-9)."""
    return bool(media <= cota_media and p95 <= cota_p95)


def _resumen(prueba: str, variable: str, delta: np.ndarray, w: np.ndarray) -> dict:
    cota_media, cota_p95 = _cotas(variable, prueba)
    ok = np.isfinite(delta)
    if not ok.any():
        raise ErrorTendencias(f"{prueba} de {variable}: ninguna comuna con Δ finito")
    media, p95 = media_p95_ponderados(np.abs(delta[ok]), w[ok])
    pasa = _cumple(media, p95, cota_media, cota_p95)
    return {"prueba": prueba, "variable": variable, "media_pond": media, "p95_pond": p95,
            "cota_media": cota_media, "cota_p95": cota_p95,
            "resultado": (ResultadoTF.PASA if pasa else ResultadoTF.FALLA).value,
            "max_abs": float(np.max(np.abs(delta[ok]))),          # TEN-10: el mayor |Δ| (sólo en memoria)
            "n_comunas": int(ok.sum()), "n_comunas_sin_dato": int((~ok).sum())}


def tf1(cambio, completo, pesos_comuna, umbrales, variable) -> dict:
    """TF1 de una variable (§5.7; TEN-7, TEN-9): media y P95 ponderados de |Δ_c| frente a sus cotas y el resultado.
    ``umbrales`` no se usa: las cotas son del A2 (``constantes``)."""
    v = _variable_tf(variable)
    w = _pesos_alineados(pesos_comuna, _mismas_comunas(cambio, completo))
    return _resumen(Prueba.TF1.value, v, delta_tf1(cambio, completo), w)


def tf2(constante, completo, pesos_comuna, umbrales, variable, regla: str) -> dict:
    """TF2 de una variable (§5.7; TEN-8, TEN-9, TEN-11): con la regla «ninguna», «no_evaluable» (EMC1-2)."""
    v = _variable_tf(variable)
    regla = ReglaRedConstante(regla).value
    if regla == NINGUNA:
        cota_media, cota_p95 = _cotas(v, Prueba.TF2.value)
        return {"prueba": Prueba.TF2.value, "variable": v, "media_pond": float("nan"), "p95_pond": float("nan"),
                "cota_media": cota_media, "cota_p95": cota_p95, "resultado": ResultadoTF.NO_EVALUABLE.value,
                "max_abs": float("nan"), "n_comunas": 0, "n_comunas_sin_dato": 0, "regla": regla}
    w = _pesos_alineados(pesos_comuna, _mismas_comunas(constante, completo))
    salida = _resumen(Prueba.TF2.value, v, delta_tf2(constante, completo, range(*_rango(anios_regla(regla)))), w)
    salida["regla"] = regla
    return salida


def comprobar_cero(candidato, resultado: Mapping) -> None:
    """TEN-10: en A, C y C_est la media, el P95 o el máximo de |Δ| > ``TF_CERO_TOL`` es un error de código (§5.7:
    «un valor > 10⁻⁶»; errata de §10)."""
    cand = Candidato(candidato).value
    if cand not in CERO_POR_CONSTRUCCION or resultado["resultado"] == ResultadoTF.NO_EVALUABLE.value:
        return
    if "max_abs" not in resultado:
        raise ErrorTendencias(f"{resultado['prueba']} de {cand}: falta el máximo de |Δ| (TEN-10)")
    tol = constantes.valor("TF_CERO_TOL")
    valores = {"media": float(resultado["media_pond"]), "P95": float(resultado["p95_pond"]),
               "máximo": float(resultado["max_abs"])}
    malos = {k: v for k, v in valores.items() if not v <= tol}
    if malos:
        raise ErrorTendencias(f"{resultado['prueba']} de {cand} en {resultado['variable']}: {malos} > 10⁻⁶; A, C y "
                              "C_est dan 0 por construcción: es un error de código (§5.7, errata de §10)")


# ---------------------------------------------------------------------------
# El producto de cada candidato por lotes (TEN-4, TEN-5, TEN-13, TEN-14)
# ---------------------------------------------------------------------------
def producto_tf(variable, F: Mapping, R: Mapping) -> np.ndarray:
    """El producto de una variable de TF desde el fondo y la corrección (TEN-5): las fórmulas de
    ``fondo_era5l.producto_desde`` (y la rapidez de §3). ``R`` va por variable del producto («T», «Td», «u», «v», «p»)."""
    v = _variable_tf(variable)
    if v == V_T:
        return F["T_F"] + R["T"]
    if v == V_TD:
        return np.minimum(F["Td_F"] + R["Td"], F["T_F"] + R["T"])
    if v == V_RAPIDEZ:
        return np.hypot(F["u_F"] + R["u"], F["v_F"] + R["v"])
    return F["p_F"] * np.exp(R["p"])


@dataclass(frozen=True, eq=False)
class CeldasTF:
    """Las celdas pobladas de una pasada de TF (TEN-6, TEN-12): ids, lat, lon, la z del uso (z_media en lo ambiental,
    z_poblada en salud), la comuna, el w_ghs de 2020 y, para C y C_est, sus estáticos (``ESQUEMA_ESTATICAS_CELDA_C``,
    una fila por celda en el orden de ``ids``) y el clima del estado (variable → celda × 12 × 24; TEN-14)."""
    ids: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    z: np.ndarray
    cod_comuna: np.ndarray
    w_ghs: np.ndarray
    estaticos: pd.DataFrame | None = None
    clima_estado: Mapping[str, np.ndarray] | None = None

    def __post_init__(self) -> None:
        ids = np.asarray(self.ids)
        if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer):
            raise ErrorTendencias("CeldasTF.ids: enteros, uno por celda")
        n = ids.size
        if np.unique(ids).size != n:
            raise ErrorTendencias("CeldasTF.ids: sin repetir")
        for nombre in ("lat", "lon", "z", "w_ghs"):
            x = np.asarray(getattr(self, nombre), dtype=np.float64)
            if x.shape != (n,) or not np.isfinite(x).all():
                raise ErrorTendencias(f"CeldasTF.{nombre}: un valor finito por celda")
            object.__setattr__(self, nombre, x)
        if not (self.w_ghs > 0).all():
            raise ErrorTendencias("CeldasTF.w_ghs: > 0 (sólo celdas pobladas; TEN-6)")
        com = np.asarray(self.cod_comuna)
        if com.shape != (n,) or not np.issubdtype(com.dtype, np.integer) or not (com > 0).all():
            raise ErrorTendencias("CeldasTF.cod_comuna: un código > 0 por celda (TEN-6)")
        object.__setattr__(self, "ids", ids.astype(np.int64))
        object.__setattr__(self, "cod_comuna", com.astype(np.int64))
        if self.estaticos is not None:
            est = self.estaticos
            if not isinstance(est, pd.DataFrame) or len(est) != n or \
                    not np.array_equal(est["celda"].to_numpy(np.int64), self.ids):
                raise ErrorTendencias("CeldasTF.estaticos: una fila por celda, en el orden de ids")
        if self.clima_estado is not None:
            for v in candidatos.ESTADO_C:
                x = np.asarray(self.clima_estado.get(v), dtype=np.float64) if v in self.clima_estado else None
                if x is None or x.shape != (n, MESES_ANIO, HORAS_DIA):
                    raise ErrorTendencias(f"CeldasTF.clima_estado[{v}]: celda × 12 × 24")

    @property
    def n(self) -> int:
        return int(self.ids.size)

    def puntos(self) -> dict:
        return {"ids": self.ids, "lat": self.lat, "lon": self.lon, "z": self.z}


def celdas_tf(tabla, z, *, estaticos=None, clima_estado=None) -> CeldasTF:
    """``CeldasTF`` desde una tabla con ``celda``, ``lat``, ``lon``, ``cod_comuna`` y ``w_ghs`` (de 2020) y la z del uso,
    alineada con la tabla. Quedan fuera las celdas con w_ghs ≤ 0 o ``cod_comuna`` ≤ 0 (TEN-6); ``estaticos`` (por celda)
    y ``clima_estado`` (variable → fila × 12 × 24, alineado con la tabla) se filtran igual."""
    faltan = [c for c in ("celda", "lat", "lon", "cod_comuna", "w_ghs") if c not in tabla.columns]
    if faltan:
        raise ErrorTendencias(f"celdas_tf: faltan {faltan}")
    z = np.asarray(z, dtype=np.float64)
    if z.shape != (len(tabla),):
        raise ErrorTendencias("celdas_tf: una z por fila de la tabla")
    w = tabla["w_ghs"].to_numpy(np.float64)
    com = tabla["cod_comuna"].to_numpy(np.int64)
    m = (w > 0) & (com > 0)
    ids = tabla["celda"].to_numpy(np.int64)[m]
    est = None
    if estaticos is not None:
        idx = pd.Index(estaticos["celda"].to_numpy(np.int64))
        if not idx.is_unique:
            raise ErrorTendencias("celdas_tf: estáticos con celdas repetidas")
        pos = idx.get_indexer(ids)
        if (pos < 0).any():
            raise ErrorTendencias("celdas_tf: celdas pobladas sin estáticos (C y C_est los necesitan)")
        est = estaticos.iloc[pos].reset_index(drop=True)
    clima = None if clima_estado is None else {v: np.asarray(clima_estado[v], dtype=np.float64)[m]
                                               for v in candidatos.ESTADO_C}
    return CeldasTF(ids=ids, lat=tabla["lat"].to_numpy(np.float64)[m], lon=tabla["lon"].to_numpy(np.float64)[m],
                    z=z[m], cod_comuna=com[m], w_ghs=w[m], estaticos=est, clima_estado=clima)


def combinaciones_nucleo(umbrales) -> tuple[Hiper, ...]:
    """Las 60 combinaciones (L, λ, κ) de §4.2, en el orden del texto (S6-4)."""
    return tuple(Hiper(float(L), float(lam), float(k)) for L in umbrales.a("NUC_L") for lam in umbrales.a("NUC_LAMBDA")
                 for k in umbrales.a("NUC_KAPPA"))


def etiqueta_hiper(hiper) -> str:
    """Etiqueta de una configuración: «L=…,lam=…,kappa=…» (núcleo), la de Φ′ en AB, o «alfa=…» (C y C_est)."""
    if isinstance(hiper, tuple):
        return etiqueta_hiper(hiper[1])
    if isinstance(hiper, Hiper):
        return f"L={float(hiper.L_km):g},lam={float(hiper.lam):g},kappa={float(hiper.kappa):g}"
    return f"alfa={float(hiper):g}"


def _comprobar_hiper(h, donde: str) -> tuple[float, float, float]:
    if not isinstance(h, Hiper):
        raise ErrorTendencias(f"{donde}: se espera tipos.Hiper, no {h!r}")
    L, lam, kappa = float(h.L_km), float(h.lam), float(h.kappa)
    if not (math.isfinite(L) and L > 0 and math.isfinite(lam) and lam >= 0 and math.isfinite(kappa) and kappa > 0):
        raise ErrorTendencias(f"{donde}: hiperparámetros inválidos {h!r}")
    return L, lam, kappa


def _normalizar_configuraciones(configuraciones) -> tuple[tuple[str, str, Mapping[str, Any]], ...]:
    """(candidato, etiqueta, {variable del producto: hiperparámetro}) en el orden de tipos.Candidato y de las
    etiquetas dadas. A y B: Hiper; AB: (Hiper de A, Hiper de Φ′); C y C_est: α."""
    if not isinstance(configuraciones, Mapping):
        raise ErrorTendencias("configuraciones: {candidato: {etiqueta: {variable del producto: hiperparámetro}}}")
    salida = []
    for cand in (A, B, AB, C, C_EST):
        if cand not in {Candidato(k).value for k in configuraciones}:
            continue
        por = next(v for k, v in configuraciones.items() if Candidato(k).value == cand)
        if not isinstance(por, Mapping) or not por:
            raise ErrorTendencias(f"configuraciones[{cand}]: {{etiqueta: {{variable: hiperparámetro}}}}")
        for etiqueta, cfg in por.items():
            if not isinstance(etiqueta, str) or not isinstance(cfg, Mapping) or not cfg:
                raise ErrorTendencias(f"configuraciones[{cand}][{etiqueta!r}]: {{variable del producto: hiper}}")
            norm = {}
            for pv, h in cfg.items():
                if pv not in VARIABLES_PRODUCTO:
                    raise ErrorTendencias(f"configuraciones[{cand}][{etiqueta}]: {pv!r} no es variable del producto")
                donde = f"configuraciones[{cand}][{etiqueta}][{pv}]"
                if cand in (A, B):
                    _comprobar_hiper(h, donde)
                elif cand == AB:
                    if not (isinstance(h, tuple) and len(h) == 2):
                        raise ErrorTendencias(f"{donde}: (Hiper de A, Hiper de Φ′)")
                    _comprobar_hiper(h[0], donde)
                    _comprobar_hiper(h[1], donde)
                else:
                    if isinstance(h, bool) or not isinstance(h, (int, float)) or not (math.isfinite(h) and h > 0):
                        raise ErrorTendencias(f"{donde}: α finito > 0")
                    h = float(h)
                norm[pv] = h
            salida.append((cand, etiqueta, norm))
    extras = {Candidato(k).value for k in configuraciones} - {A, B, AB, C, C_EST}
    if extras:
        raise ErrorTendencias(f"configuraciones: candidatos desconocidos {extras}")
    return tuple(salida)


def _rbar12(clima: pd.DataFrame, codigos: tuple[str, ...], variable: str) -> np.ndarray:
    """r̄ mes × hora × estación, NaN donde no califica (la cuenta de ``candidatos`` para A; TEN-13)."""
    tipos.validar_esquema(clima, tipos.ESQUEMA_CLIMA_A, nombre="clima_a")
    sub = clima[clima["variable"] == variable]
    salida = np.full((MESES_ANIO, HORAS_DIA, len(codigos)), np.nan)
    if not len(sub) or not len(codigos):
        return salida
    j = pd.Index(list(codigos)).get_indexer(sub["codigo"].astype(object))
    en = j >= 0
    mes = sub["mes"].to_numpy(np.int64)[en] - 1
    hora = sub["hora"].to_numpy(np.int64)[en]
    valor = np.where(sub["califica"].to_numpy(bool)[en], sub["rbar"].to_numpy(np.float64)[en], np.nan)
    salida[mes, hora, j[en]] = valor
    return salida


def _inicio_mes_h(m2000: np.ndarray) -> np.ndarray:
    meses = _EPOCA_M + np.asarray(m2000, dtype=np.int64).astype("timedelta64[M]")
    return (meses.astype("datetime64[h]") - _EPOCA_H).astype(np.int64)


def _centro_mes(m2000: np.ndarray) -> np.ndarray:
    """MC-41: el punto medio entre la primera y la última hora UTC del mes (copia de ``candidatos``, TEN-13)."""
    return (_inicio_mes_h(m2000) + _inicio_mes_h(np.asarray(m2000) + 1) - 1) / 2


def _interpolacion_mensual(h: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Índices de mes (0-11) de los dos centros que rodean cada hora y el peso t del segundo (CAN-5; TEN-13)."""
    m = mes2000(h)
    antes = h < _centro_mes(m)
    m_a = np.where(antes, m - 1, m)
    c_a, c_b = _centro_mes(m_a), _centro_mes(m_a + 1)
    t = (h - c_a) / (c_b - c_a)
    return np.mod(m_a, MESES_ANIO), np.mod(m_a + 1, MESES_ANIO), t


class _Lote:
    """Lo que se calcula una vez por (mes, lote de celdas) y se comparte entre configuraciones y escenarios."""

    def __init__(self, pasada: "PasadaTF", h: np.ndarray, sl: slice, F: Mapping[str, np.ndarray]) -> None:
        self.p = pasada
        self.h = h
        self.sl = sl
        self.F = F
        self._sumas: dict = {}
        self._campo_a: dict = {}
        self._r_c: dict = {}
        self._interp = None
        self._amp = None

    # --- núcleo (B, Φ′ de AB) ---
    def phi(self, clase: str, pv: str, hiper: Hiper, efectiva: frozenset) -> np.ndarray:
        L, lam, kappa = _comprobar_hiper(hiper, "núcleo")
        clave = (clase, pv, L, lam, efectiva)
        if clave not in self._sumas:
            Q = self.p._q(clase, pv)
            disponible = np.isfinite(Q) & self.p._mascara(efectiva)[None, :]
            self._sumas[clave] = candidatos.sumas_nucleo(self.p._vecinos(hiper, self.sl), Q, disponible)
        num, den = self._sumas[clave]
        return num / (kappa + den)

    # --- A (y la parte A de AB) ---
    def a(self, pv: str, hiper: Hiper) -> np.ndarray:
        L, lam, kappa = _comprobar_hiper(hiper, "A")
        if self._interp is None:
            i_a, i_b, t = _interpolacion_mensual(self.h)
            meses = np.unique(np.concatenate([i_a, i_b]))
            self._interp = (meses, np.searchsorted(meses, i_a), np.searchsorted(meses, i_b), t,
                            np.mod(self.h, HORAS_DIA))
        meses, k_a, k_b, t, hora = self._interp
        clave = (pv, L, lam)
        if clave not in self._campo_a:
            rbar = self.p._rbar(pv)[meses].reshape(meses.size * HORAS_DIA, -1)
            num, den = candidatos.sumas_nucleo(self.p._vecinos(hiper, self.sl), rbar, np.isfinite(rbar))
            forma = (meses.size, HORAS_DIA, num.shape[1])
            self._campo_a[clave] = (num.reshape(forma), den.reshape(forma))
        num12, den12 = self._campo_a[clave]
        phi12 = num12 / (kappa + den12)
        t2 = t[:, None]
        return (1.0 - t2) * phi12[k_a, hora] + t2 * phi12[k_b, hora]

    # --- C y C_est ---
    def _estado_c(self, i: int) -> dict:
        if self._amp is None:
            self._amp = fondo_era5l.amplitud_dia_utc(self.F["T_F"], self.h)
        T, Td, u, v = (self.F[c][:, i] for c in ("T_F", "Td_F", "u_F", "v_F"))
        return dict(zip(candidatos.ESTADO_C, (T, T - Td, np.hypot(u, v), self._amp[:, i])))

    def r_c(self, cand: str, pv: str, clave_red) -> np.ndarray:
        """R de todas las α de ``cand`` en ``pv`` (hora × celda × configuración), calculada en cada red pedida."""
        if (cand, pv, clave_red) not in self._r_c:
            claves = self.p._claves_c_del_mes
            pvs = self.p._pvs_c[cand]
            n_h, n_s = self.h.size, self.sl.stop - self.sl.start
            salida = {(x, k): np.empty((n_h, n_s, self.p._W[(cand, x)].shape[1])) for x in pvs
                      for k in claves.get(x, ())}
            celdas = self.p.celdas
            climatologico = cand == C_EST
            for j, i in enumerate(range(self.sl.start, self.sl.stop)):
                fila = self.p._fila_estaticos(i)
                estado = ({v: celdas.clima_estado[v][i] for v in candidatos.ESTADO_C} if climatologico
                          else self._estado_c(j))
                X = candidatos.diseno_c(fila, self.h, estado, climatologico=climatologico)
                for x in pvs:
                    for k in claves.get(x, ()):                       # TEN-10: aparte en cada red
                        salida[(x, k)][:, j, :] = np.matmul(X, self.p._W[(cand, x)])
            for (x, k), arr in salida.items():
                self._r_c[(cand, x, k)] = arr
        return self._r_c[(cand, pv, clave_red)]

    def correccion(self, cand: str, cfg: Mapping, pv: str, red, efectiva) -> np.ndarray:
        h = cfg[pv]
        if cand == A:
            return self.a(pv, h)
        if cand == B:
            return self.phi(B, pv, h, efectiva)
        if cand == AB:
            return self.a(pv, h[0]) + self.phi(AB, pv, h[1], efectiva)
        k = self.p._indice_cfg[(cand, id(cfg))]
        return self.r_c(cand, pv, ("red", red))[:, :, k]


class PasadaTF:
    """Una pasada de TF por mes UTC (M3-4, paso 9; S6): medias comunales del producto de cada candidato × configuración ×
    variable × escenario × año (TEN-4 a TEN-6, TEN-13, TEN-14, TEN-22).

    ``datos``: la ``DatosCompetencia`` de producción (todas las estaciones). ``celdas``: ``CeldasTF`` del uso.
    ``escenarios``: {variable de TF: ``EscenariosTF``}. ``configuraciones``: {candidato: {etiqueta: {variable del
    producto: hiperparámetro}}} (A y B: Hiper; AB: (Hiper de A, Hiper de Φ′); C y C_est: α); una variable de TF se calcula
    para una configuración si trae todas las variables de su producto (``PRODUCTO_DE``). ``fondo(h, indices)`` da los
    campos ``fondo_era5l.CAMPOS_F`` (hora × celda) del lote; lo arma quien llama (``campos_fondo`` con el operador de las
    celdas del uso)."""

    def __init__(self, datos, celdas: CeldasTF, escenarios: Mapping[str, EscenariosTF], configuraciones, umbrales, *,
                 variables: Sequence[str] = VARIABLES_TF, pruebas: Sequence[str] = PRUEBAS, entrenamiento=None,
                 lote_puntos: int = LOTE_PUNTOS_TF) -> None:
        if not isinstance(datos, tipos.DatosCompetencia):
            raise ErrorTendencias("datos debe ser tipos.DatosCompetencia")
        if not isinstance(celdas, CeldasTF):
            raise ErrorTendencias("celdas debe ser CeldasTF")
        self.datos, self.celdas, self.U = datos, celdas, umbrales
        self.variables = tuple(_variable_tf(v) for v in variables)
        self.pruebas = tuple(Prueba(p).value for p in pruebas)
        if not self.pruebas:
            raise ErrorTendencias("pruebas: TF1, TF2 o las dos")
        self.escenarios = {}
        for v in self.variables:
            e = escenarios.get(v) if isinstance(escenarios, Mapping) else None
            if not isinstance(e, EscenariosTF) or e.variable != v:
                raise ErrorTendencias(f"escenarios[{v}]: el EscenariosTF de {v}")
            self.escenarios[v] = e
        if entrenamiento is None:
            entrenamiento = [c for c, info in datos.estaciones.items() if not info.excluida]
        faltan = [c for c in entrenamiento if c not in datos.estaciones]
        if faltan:
            raise ErrorTendencias(f"entrenamiento: sin InfoEstacion {faltan[:_CITADOS]}")
        self.entrenamiento = {c: datos.estaciones[c] for c in sorted(set(entrenamiento))}
        self.codigos = tuple(self.entrenamiento)
        self._pos = {c: j for j, c in enumerate(self.codigos)}
        if isinstance(lote_puntos, bool) or not isinstance(lote_puntos, int) or lote_puntos < 1:
            raise ErrorTendencias("lote_puntos: entero ≥ 1")
        self.lotes = tuple(slice(i, min(celdas.n, i + lote_puntos)) for i in range(0, celdas.n, lote_puntos))
        self.comunas, self._indice_comuna = np.unique(celdas.cod_comuna, return_inverse=True)
        self.pesos_comuna = np.bincount(self._indice_comuna, weights=celdas.w_ghs, minlength=self.comunas.size)
        self.configuraciones = _normalizar_configuraciones(configuraciones)
        self.tareas = tuple((cand, et, v) for cand, et, cfg in self.configuraciones for v in self.variables
                            if all(pv in cfg for pv in PRODUCTO_DE[v]))
        self._vec: dict = {}
        self._rbar_cache: dict = {}
        self._W: dict = {}
        self._pvs_c: dict = {}
        self._indice_cfg: dict = {}
        self._filas_est: dict = {}
        self._preparar_c()
        self._q_mes: dict = {}
        self._claves_c_del_mes: dict = {}

    # --- preparación ---
    def _preparar_c(self) -> None:
        """Los modelos de C y C_est con todas las estaciones (S6-5) y W = T·coef por variable (TEN-14)."""
        m = len(candidatos.MONOMIOS_C)
        identidad = np.eye(m)
        por_cand: dict = {}
        for cand, et, cfg in self.configuraciones:
            if cand not in DE_C:
                continue
            if self.celdas.estaticos is None or (cand == C_EST and self.celdas.clima_estado is None):
                raise ErrorTendencias(f"{cand} necesita los estáticos de las celdas (y C_est su clima del estado)")
            filas = self.datos.filas_c.get(cand) if isinstance(self.datos.filas_c, Mapping) else None
            if filas is None:
                raise ErrorTendencias(f"datos.filas_c no trae {cand}")
            lista = por_cand.setdefault(cand, [])
            self._indice_cfg[(cand, id(cfg))] = len(lista)
            lista.append(cfg)
        for cand, lista in por_cand.items():
            pvs = tuple(sorted({pv for cfg in lista for pv in cfg}, key=VARIABLES_PRODUCTO.index))
            self._pvs_c[cand] = pvs
            for pv in pvs:
                columnas = []
                for cfg in lista:
                    if pv not in cfg:
                        columnas.append(np.full(m, np.nan))
                        continue
                    modelo = candidatos.ajustar_c(self.datos.filas_c[cand][pv], self.codigos, cfg[pv])
                    T = candidatos.diseno_estandarizado(identidad, modelo)
                    columnas.append(np.matmul(T, modelo.coef))
                self._W[(cand, pv)] = np.column_stack(columnas)

    def _vecinos(self, hiper: Hiper, sl: slice):
        L, lam, _ = _comprobar_hiper(hiper, "vecinos")
        if (L, lam) not in self._vec:
            self._vec[(L, lam)] = candidatos.vecinos(self.celdas.puntos(), self.entrenamiento, hiper, self.U)
        vec = self._vec[(L, lam)]
        return replace(vec, puntos=vec.puntos[sl], est=vec.est[sl], d_ef=vec.d_ef[sl], grupo_de=vec.grupo_de[sl])

    def _rbar(self, pv: str) -> np.ndarray:
        if pv not in self._rbar_cache:
            self._rbar_cache[pv] = _rbar12(self.datos.climatologias, self.codigos, pv)
        return self._rbar_cache[pv]

    def _fila_estaticos(self, i: int) -> pd.DataFrame:
        if len(self.lotes) == 1:                     # una sola tanda de celdas: se guardan las filas (memoria chica)
            if i not in self._filas_est:
                self._filas_est[i] = self.celdas.estaticos.iloc[[i]]
            return self._filas_est[i]
        return self.celdas.estaticos.iloc[[i]]

    def _mascara(self, efectiva: frozenset) -> np.ndarray:
        m = np.zeros(len(self.codigos), dtype=bool)
        for c in efectiva:
            m[self._pos[c]] = True
        return m

    def _q(self, clase: str, pv: str) -> np.ndarray:
        if (clase, pv) not in self._q_mes:
            self._q_mes[(clase, pv)] = candidatos.matriz_q(self.datos, self.codigos, clase, pv, self._h_mes, self.U)
        return self._q_mes[(clase, pv)]

    def _activas(self, clase: str, pv: str) -> frozenset:
        clave = ("activas", clase, pv)
        if clave not in self._q_mes:
            Q = self._q(clase, pv)
            self._q_mes[clave] = frozenset(c for c, ok in zip(self.codigos, np.isfinite(Q).any(axis=0)) if ok)
        return self._q_mes[clave]

    def _efectiva(self, cand: str, v: str, red) -> tuple:
        """La clave del cálculo de un escenario (TEN-4): la red efectiva en B y AB; la red misma en A, C y C_est."""
        if cand in (B, AB):
            return tuple(self._activas(cand, pv) if red is None else (red & self._activas(cand, pv))
                         for pv in PRODUCTO_DE[v])
        return ("red", red)

    # --- un mes ---
    def anios(self) -> tuple[int, ...]:
        """Los años que hace falta recorrer (todos los escenarios de todas las variables)."""
        return tuple(sorted({a for e in self.escenarios.values() for x in ESCENARIOS for a in e.anios(x, self.pruebas)}))

    def sumas_mes(self, h_mes, fondo: Callable) -> dict:
        """Sumas comunales de un mes UTC (TEN-22): {(candidato, etiqueta, variable, escenario): (año, sumas 2 × comuna)}.
        Pura en su mes: los meses se pueden repartir entre procesos y sumar después en su orden (``acumular``)."""
        h = _horas(h_mes, "h_mes")
        _crecientes(h, "h_mes")
        if h.size == 0:
            return {}
        if np.unique(mes2000(h)).size != 1:
            raise ErrorTendencias("sumas_mes: las horas de un solo mes UTC (MC-37)")
        anio = int(anio_de(h[:1])[0])
        redes = {v: {e: self.escenarios[v].red(e, anio) for e in ESCENARIOS
                     if anio in self.escenarios[v].anios(e, self.pruebas)} for v in self.variables}
        if not any(redes.values()):
            return {}
        self._h_mes, self._q_mes = h, {}
        claves_c: dict = {}
        for v in self.variables:                     # las redes en que se pide cada variable del producto (C, C_est)
            for pv in PRODUCTO_DE[v]:
                for r in redes[v].values():
                    claves_c.setdefault(pv, dict())[("red", r)] = None
        self._claves_c_del_mes = {pv: tuple(k) for pv, k in claves_c.items()}
        acumulado: dict = {}
        for sl in self.lotes:
            indices = np.arange(sl.start, sl.stop)
            F = _fondo_del_lote(fondo, h, indices)
            lote = _Lote(self, h, sl, F)
            w = self.celdas.w_ghs[sl]
            idx = self._indice_comuna[sl]
            for cand, et, cfg in self.configuraciones:
                for v in self.variables:
                    if (cand, et, v) not in self._tareas_set:
                        continue
                    grupos: dict = {}
                    for e, red in redes[v].items():
                        grupos.setdefault(self._efectiva(cand, v, red), []).append((e, red))
                    for efectiva, escenarios in grupos.items():
                        red = escenarios[0][1]
                        R = {pv: lote.correccion(cand, cfg, pv, red, efectiva[k] if cand in (B, AB) else None)
                             for k, pv in enumerate(PRODUCTO_DE[v])}
                        s = _sumas_comuna(producto_tf(v, F, R), w, idx, self.comunas.size)
                        for e, _ in escenarios:
                            clave = (cand, et, v, e)
                            acumulado[clave] = acumulado[clave] + s if clave in acumulado else s
        self._q_mes = {}
        return {k: (anio, s) for k, s in acumulado.items()}

    def correccion_mes(self, h_mes, fondo: Callable, candidato, etiqueta: str, variable_producto: str, *,
                       red: frozenset[str] | None = None) -> np.ndarray:
        """La corrección R de una configuración en un mes, en todas las celdas (hora × celda), con la red ``red`` (None:
        todas). En memoria (§0.4.3); sirve a las pruebas de paridad con ``candidatos`` (TEN-13, TEN-14)."""
        h = _horas(h_mes, "h_mes")
        _crecientes(h, "h_mes")
        if h.size == 0 or np.unique(mes2000(h)).size != 1:
            raise ErrorTendencias("correccion_mes: las horas de un solo mes UTC")
        cand = Candidato(candidato).value
        cfg = next((c for k, e, c in self.configuraciones if k == cand and e == etiqueta), None)
        if cfg is None or variable_producto not in cfg:
            raise ErrorTendencias(f"correccion_mes: no hay {cand}/{etiqueta} en {variable_producto}")
        self._h_mes, self._q_mes = h, {}
        self._claves_c_del_mes = {variable_producto: (("red", red),)}
        partes = []
        for sl in self.lotes:
            lote = _Lote(self, h, sl, _fondo_del_lote(fondo, h, np.arange(sl.start, sl.stop)))
            efectiva = None
            if cand in (B, AB):
                activas = self._activas(cand, variable_producto)
                efectiva = activas if red is None else red & activas
            partes.append(lote.correccion(cand, cfg, variable_producto, red, efectiva))
        self._q_mes = {}
        return np.concatenate(partes, axis=1)

    @property
    def _tareas_set(self) -> frozenset:
        if not hasattr(self, "_tareas_cache"):
            self._tareas_cache = frozenset(self.tareas)
        return self._tareas_cache

    def acumular(self, meses: Iterable[Mapping]) -> "MediasTF":
        """Suma los resultados de ``sumas_mes`` en el orden dado (el de los meses; TEN-22) y da las medias."""
        acc = AcumuladorComunas(self.comunas)
        for por_mes in meses:
            for clave, (anio, s) in por_mes.items():
                acc.sumar(clave, anio, s)
        return MediasTF(comunas=self.comunas, pesos_comuna=self.pesos_comuna, tareas=self.tareas,
                        escenarios=dict(self.escenarios), pruebas=self.pruebas,
                        medias={k: acc.medias(k) for k in acc.claves()})

    def meses(self, horas) -> list[np.ndarray]:
        """Las horas de ``horas`` en los años de la pasada, partidas por mes UTC (MC-37), en orden."""
        h = _horas(horas, "horas")
        _crecientes(h, "horas")
        h = h[np.isin(anio_de(h), np.array(self.anios(), dtype=np.int64))] if h.size else h
        if h.size == 0:
            return []
        m = mes2000(h)
        return np.split(h, np.flatnonzero(np.diff(m)) + 1)

    def correr(self, horas, fondo: Callable) -> "MediasTF":
        """La pasada entera en un proceso: los meses en orden (TEN-22)."""
        return self.acumular(self.sumas_mes(hm, fondo) for hm in self.meses(horas))


def _fondo_del_lote(fondo: Callable, h: np.ndarray, indices: np.ndarray) -> dict:
    F = fondo(h, indices)
    if not isinstance(F, Mapping):
        raise ErrorTendencias("fondo(h, indices) debe dar {campo: hora × celda}")
    salida = {}
    for c in fondo_era5l.CAMPOS_F:
        if c not in F:
            raise ErrorTendencias(f"fondo(h, indices): falta {c}")
        x = np.asarray(F[c], dtype=np.float64)
        if x.shape != (h.size, indices.size):
            raise ErrorTendencias(f"fondo(h, indices)[{c}]: hora × celda ({h.size} × {indices.size}), no {x.shape}")
        salida[c] = x
    return salida


@dataclass(frozen=True, eq=False)
class MediasTF:
    """Medias anuales por comuna de una pasada (en memoria): (candidato, etiqueta, variable, escenario) →
    ``MediasComunaAnio``."""
    comunas: np.ndarray
    pesos_comuna: np.ndarray
    tareas: tuple
    escenarios: Mapping[str, EscenariosTF]
    pruebas: tuple
    medias: Mapping[tuple, MediasComunaAnio]


def resultados_tf(medias: MediasTF, umbrales, *, comprobar: bool = True) -> dict:
    """TF1 y TF2 de cada (candidato, etiqueta, variable) de una pasada: {(c, e, v): {"TF1": …, "TF2": …}}. Con
    ``comprobar`` (por omisión), A, C y C_est con artefacto > 10⁻⁶ lanzan ``ErrorTendencias`` (TEN-10)."""
    if not isinstance(medias, MediasTF):
        raise ErrorTendencias("resultados_tf recibe las MediasTF de una pasada")
    salida = {}
    for cand, et, v in medias.tareas:
        esc = medias.escenarios[v]
        por = {}
        if Prueba.TF1.value in medias.pruebas:
            por[Prueba.TF1.value] = tf1(_medias(medias, cand, et, v, CAMBIO), _medias(medias, cand, et, v, COMPLETO),
                                        medias.pesos_comuna, umbrales, v)
        if Prueba.TF2.value in medias.pruebas:
            if esc.evaluable:
                por[Prueba.TF2.value] = tf2(_medias(medias, cand, et, v, CONSTANTE),
                                            _medias(medias, cand, et, v, COMPLETO), medias.pesos_comuna, umbrales, v,
                                            esc.regla)
            else:
                por[Prueba.TF2.value] = tf2(None, None, medias.pesos_comuna, umbrales, v, NINGUNA)
        if comprobar:
            for r in por.values():
                comprobar_cero(cand, r)
        salida[(cand, et, v)] = por
    return salida


def _medias(medias: MediasTF, cand, et, v, escenario) -> MediasComunaAnio:
    clave = (cand, et, v, escenario)
    if clave not in medias.medias:
        raise ErrorTendencias(f"sin medias de {clave}: la pasada no recorrió los años del escenario")
    return medias.medias[clave]


def tf_por_uso(ambiental: Mapping | None = None, salud: Mapping | None = None) -> dict:
    """Los resultados de las dos pasadas, por uso (MC-04, MC-55; TEN-12): {uso: {(candidato, variable): {"TF1", "TF2"}}}.
    Cada pasada trae una sola configuración por candidato (la de producción). Lo crónico de A, B y AB en T son los mismos
    resultados de lo agudo (se calcula una vez)."""
    def por_candidato(res: Mapping, nombre: str) -> dict:
        salida: dict = {}
        for (cand, _, v), r in res.items():
            if (cand, v) in salida:
                raise ErrorTendencias(f"{nombre}: más de una configuración de {cand} en {v}")
            salida[(cand, v)] = r
        return salida
    salida: dict = {}
    if ambiental is not None:
        amb = por_candidato(ambiental, "ambiental")
        salida[Uso.AMBIENTAL.value] = {k: r for k, r in amb.items() if k[0] in CANDIDATOS_USO[Uso.AMBIENTAL.value]}
    if salud is not None:
        sal = por_candidato(salud, "salud")
        salida[Uso.AGUDO.value] = {k: r for k, r in sal.items() if k[0] in CANDIDATOS_USO[Uso.AGUDO.value]
                                   and k[1] in VARIABLES_USO[Uso.AGUDO.value]}
        salida[Uso.CRONICO.value] = {k: r for k, r in sal.items() if k[0] in CANDIDATOS_USO[Uso.CRONICO.value]
                                     and k[1] in VARIABLES_USO[Uso.CRONICO.value]}
    return salida


def filas_tf(por_uso: Mapping, escenarios: Mapping[str, EscenariosTF]) -> pd.DataFrame:
    """La tabla ``tipos.ESQUEMA_TF`` (``tendencias/resumen_tf.parquet``): candidato × uso × variable × prueba, en el
    orden de ``CANDIDATOS_USO``, ``VARIABLES_USO`` y TF1, TF2 (MC-04; TEN-11, TEN-12). Cada uso que viene debe traer todos
    sus candidatos y variables, con las dos pruebas."""
    filas = []
    for uso in (u.value for u in Uso):
        if uso not in por_uso:
            continue
        res = por_uso[uso]
        for cand in CANDIDATOS_USO[uso]:
            for v in VARIABLES_USO[uso]:
                if (cand, v) not in res:
                    raise ErrorTendencias(f"filas_tf: falta la TF de {cand} en {v} (lo {uso}; MC-04)")
                esc = escenarios.get(v)
                if not isinstance(esc, EscenariosTF):
                    raise ErrorTendencias(f"filas_tf: falta la red de {v}")
                for prueba in PRUEBAS:
                    r = res[(cand, v)].get(prueba)
                    if r is None or r["variable"] != v or r["prueba"] != prueba:
                        raise ErrorTendencias(f"filas_tf: falta {prueba} de {cand} en {v} (lo {uso})")
                    if prueba == Prueba.TF2.value and r.get("regla") != esc.regla:
                        raise ErrorTendencias(f"filas_tf: la regla de TF2 de {cand} en {v} no es la de su red")
                    comprobar_cero(cand, r)
                    filas.append({"candidato": cand, "uso": uso, "variable": v, "prueba": prueba,
                                  "media_pond": float(r["media_pond"]), "p95_pond": float(r["p95_pond"]),
                                  "cota_media": float(r["cota_media"]), "cota_p95": float(r["cota_p95"]),
                                  "resultado": ResultadoTF(r["resultado"]).value, "regla_red": esc.regla,
                                  "n_red": int(esc.n_red)})
    esquema = tipos.ESQUEMA_TF
    df = (pd.DataFrame(filas, columns=list(esquema)) if filas else tipos.tabla_vacia(esquema)).astype(dict(esquema))
    tipos.validar_esquema(df, esquema, nombre="resumen_tf")
    df.attrs["esquema"] = esquema.version
    return df


# ---------------------------------------------------------------------------
# S6 y la compuerta de deriva (TEN-15 a TEN-18)
# ---------------------------------------------------------------------------
def compuerta_deriva(resultados_s6: dict, *, umbrales) -> dict[str, bool]:
    """{«B»: bool, «AB»: bool}: cada uno pasa si su TF2 «pasa» en las 60 combinaciones de §4.2 (S6-4; TEN-18).
    ``resultados_s6``: {«B» y «AB»: {etiqueta: resultado de ``tf2``}}, con las 60 etiquetas de ``combinaciones_nucleo``;
    cada resultado debe ser de TF2, de T (S6-6) y con las cotas de TF2 de T. Una TF2 no evaluable lanza
    ``ErrorTendencias`` (EMC1-2: la red de S6 debe darla evaluable)."""
    if not isinstance(resultados_s6, Mapping) or {Candidato(k).value for k in resultados_s6} != set(CON_DERIVA) \
            or len(resultados_s6) != len(CON_DERIVA):
        raise ErrorTendencias("compuerta_deriva: {«B»: …, «AB»: …} (§5.7: B y AB)")
    esperadas = {etiqueta_hiper(h) for h in combinaciones_nucleo(umbrales)}
    cota_media, cota_p95 = _cotas(V_T, Prueba.TF2.value)
    salida = {}
    for k, por in resultados_s6.items():
        cand = Candidato(k).value
        if not isinstance(por, Mapping) or set(por) != esperadas:
            raise ErrorTendencias(f"compuerta_deriva[{cand}]: se exigen las 60 combinaciones de §4.2 (S6-4)")
        for et, r in por.items():
            if not isinstance(r, Mapping) or r.get("prueba") != Prueba.TF2.value:
                raise ErrorTendencias(f"compuerta_deriva[{cand}][{et}]: la compuerta es TF2, no {r!r:.40}")
            if r.get("variable") != V_T or r.get("cota_media") != cota_media or r.get("cota_p95") != cota_p95:
                raise ErrorTendencias(f"compuerta_deriva[{cand}][{et}]: TF2 de T con las cotas de §5.7 (S6-6)")
            if r["resultado"] == ResultadoTF.NO_EVALUABLE.value:
                raise ErrorTendencias("la red de S6 da TF2 no evaluable: S6 falla (EMC1-2)")
            if r["resultado"] != ResultadoTF(r["resultado"]).value or \
                    (r["resultado"] == ResultadoTF.PASA.value) != _cumple(float(r["media_pond"]),
                                                                          float(r["p95_pond"]), cota_media, cota_p95):
                raise ErrorTendencias(f"compuerta_deriva[{cand}][{et}]: el resultado no es el de sus cotas")
        salida[cand] = all(r["resultado"] == ResultadoTF.PASA.value for r in por.values())
    return {c: salida[c] for c in CON_DERIVA}


def _combinacion(et: str) -> dict:
    partes = dict(p.split("=") for p in et.split(","))
    return {"L_km": float(partes["L"]), "lam": float(partes["lam"]), "kappa": float(partes["kappa"])}


def contenido_deriva_s6(resultados_s6: dict, compuerta: Mapping[str, bool], *, regla: str, n_red: int,
                        parametros: Mapping | None = None) -> dict:
    """El contenido de ``deriva_s6.json`` (clase resumen; TEN-18): por candidato, la media y el P95 de TF2 frente a sus
    cotas en cada combinación, la peor de cada una, cuántas pasan y el resultado; la red de TF2 y los parámetros de la
    red de S6 (D15). Números de Python, sin NaN; lo escribe ``salidas``."""
    if set(compuerta) != set(CON_DERIVA) or not all(isinstance(compuerta[c], bool) for c in CON_DERIVA):
        raise ErrorTendencias("contenido_deriva_s6: la compuerta es {«B»: bool, «AB»: bool}")
    candidatos_ = {}
    cotas = None
    for cand in CON_DERIVA:
        por = resultados_s6[cand]
        combinaciones = []
        for et in sorted(por, key=lambda e: tuple(_combinacion(e).values())):
            r = por[et]
            if cotas is None:
                cotas = {"variable": r["variable"], "media": float(r["cota_media"]), "p95": float(r["cota_p95"])}
            combinaciones.append({**_combinacion(et), "media_pond": float(r["media_pond"]),
                                  "p95_pond": float(r["p95_pond"]), "resultado": str(r["resultado"])})
        peor_media = max(combinaciones, key=lambda x: x["media_pond"])
        peor_p95 = max(combinaciones, key=lambda x: x["p95_pond"])
        candidatos_[cand] = {"pasa": bool(compuerta[cand]), "n_combinaciones": len(combinaciones),
                             "n_pasan": sum(x["resultado"] == ResultadoTF.PASA.value for x in combinaciones),
                             "peor_media": peor_media, "peor_p95": peor_p95, "combinaciones": combinaciones}
    salida = {"esquema": ESQUEMA_DERIVA_S6, "prueba": "S6", "compuerta": tipos.Compuerta.DERIVA.value,
              "tf": Prueba.TF2.value, "deriva_k_decada": float(constantes.valor("DERIVA_K_DECADA")),
              "anio_nuevas": int(constantes.valor("DERIVA_ANIO")),
              "red_tf2": {"regla": ReglaRedConstante(regla).value, "n_red": int(n_red)}, "cotas": cotas,
              "candidatos": candidatos_}
    if parametros is not None:
        salida["parametros_red_s6"] = {str(k): (list(v) if isinstance(v, tuple) else v) for k, v in parametros.items()}
    for x in _numeros(salida):
        if not math.isfinite(x):
            raise ErrorTendencias("contenido_deriva_s6: un número no finito")
    return salida


def _numeros(obj) -> Iterable[float]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, Mapping):
        for v in obj.values():
            yield from _numeros(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _numeros(v)


# ---------------------------------------------------------------------------
# TF de contaminantes (Anexo B; TEN-19 a TEN-21)
# ---------------------------------------------------------------------------
def dias_tf_contaminantes(d2000, umbrales) -> np.ndarray:
    """Los días de la TF de contaminantes: d2000 mód SEL_MOD = SEL_RESTO (Anexo B, fila M6 del Anexo A; TEN-19)."""
    d = np.asarray(d2000)
    if d.dtype == bool or not np.issubdtype(d.dtype, np.integer):
        raise ErrorTendencias("dias_tf_contaminantes: d2000 entero (días desde 2000-01-01)")
    return np.mod(d.astype(np.int64), umbrales.a("SEL_MOD")) == umbrales.a("SEL_RESTO")


def muestra_tf_contaminantes(celdas_pobladas, pesos, umbrales) -> np.ndarray:
    """La muestra fija de la TF de contaminantes (Anexo B; TEN-19): hasta ``M6_CELDAS_COMUNA`` celdas por comuna, con
    probabilidad ∝ w_ghs y la semilla de MC-44. ``celdas_pobladas``: tabla con ``celda`` y ``cod_comuna``; ``pesos``: el
    w_ghs de 2020 de cada fila. Devuelve un arreglo ``DTYPE_MUESTRA`` (celda, cod_comuna, w_ghs y el peso de la comuna,
    Σ w_ghs de todas sus celdas pobladas; MC-48), en orden de comuna y de celda."""
    faltan = [c for c in ("celda", "cod_comuna") if c not in celdas_pobladas.columns]
    if faltan:
        raise ErrorTendencias(f"muestra_tf_contaminantes: faltan {faltan}")
    celda = celdas_pobladas["celda"].to_numpy(np.int64)
    com = celdas_pobladas["cod_comuna"].to_numpy(np.int64)
    w = np.asarray(pesos, dtype=np.float64)
    if w.shape != celda.shape or not np.isfinite(w).all() or (w < 0).any():
        raise ErrorTendencias("muestra_tf_contaminantes: un w_ghs finito ≥ 0 por celda")
    if np.unique(celda).size != celda.size:
        raise ErrorTendencias("muestra_tf_contaminantes: celdas repetidas")
    n_max = int(umbrales.a("M6_CELDAS_COMUNA"))
    semilla = int(umbrales.a("SEMILLA"))
    m = (w > 0) & (com > 0)
    celda, com, w = celda[m], com[m], w[m]
    filas = []
    for c in np.unique(com):
        en = np.flatnonzero(com == c)
        en = en[np.argsort(celda[en], kind="stable")]
        if en.size > n_max:
            rng = numerico.generador(semilla, "tf_contaminantes", str(int(c)))
            elegidas = rng.choice(en.size, size=n_max, replace=False, p=w[en] / w[en].sum())
            sel = en[np.sort(elegidas)]
        else:
            sel = en
        peso = float(w[en].sum())
        filas += [(int(celda[i]), int(c), float(w[i]), peso) for i in sel]
    return np.array(filas, dtype=DTYPE_MUESTRA)


def _comprobar_muestra(muestra) -> np.ndarray:
    arr = np.asarray(muestra)
    if arr.dtype != DTYPE_MUESTRA or arr.ndim != 1 or arr.size == 0:
        raise ErrorTendencias("la muestra es la de muestra_tf_contaminantes (DTYPE_MUESTRA)")
    return arr


def _predicciones(fabrica, modelo, variante, escenario, celdas, dias) -> np.ndarray:
    P = np.asarray(fabrica(modelo, variante, escenario, celdas, dias), dtype=np.float64)
    if P.shape != (dias.size, celdas.size):
        raise ErrorTendencias(f"fabrica: predicción día × celda ({dias.size} × {celdas.size}), no {P.shape}")
    return P


def tf_contaminantes(fabrica, modelo, variante, muestra, umbrales, *, verificacion_un_mes: bool = False) -> dict:
    """TF de contaminantes de una variante (Anexo B; TEN-20, TEN-21).

    ``fabrica(modelo, variante, escenario, celdas, dias) -> día × celda``: la predicción del contaminante con la fábrica
    de producción en el escenario «cambio» o «completo» (arma sus columnas ``mc_*`` o ``fe_*`` y ``dmc_R_*`` con la red
    del escenario de cada variable), en las ``celdas`` de la muestra y los ``dias`` (d2000) de un mes. Con
    ``verificacion_un_mes`` (DEC-14: la de I con ganadores A o C), sólo el primer mes de 2015-2019 con días."""
    variante = tipos.Variante(variante).value
    arr = _comprobar_muestra(muestra)
    celdas = arr["celda"].astype(np.int64)
    w = arr["w_ghs"].astype(np.float64)
    comunas, idx = np.unique(arr["cod_comuna"].astype(np.int64), return_inverse=True)
    W = np.array([arr["peso_comuna"][idx == k][0] for k in range(comunas.size)], dtype=np.float64)
    c0, c1, c2, c3 = constantes.valor("TF1_ESCENARIO_CAMBIO")
    desde, hasta = umbrales.a("M6_TF_DESDE"), umbrales.a("M6_TF_HASTA")
    if not (desde <= c0 and c3 <= hasta):
        raise ErrorTendencias("los períodos de TF1 deben caer en 2015-2024 (Anexo B)")
    d = np.arange(_d2000_de_fecha(desde), _d2000_de_fecha(hasta + 1), dtype=np.int64)
    d = d[dias_tf_contaminantes(d, umbrales)]
    meses = np.split(d, np.flatnonzero(np.diff(_mes_de_dia(d))) + 1)
    if verificacion_un_mes:
        dm = next((m for m in meses if m.size and c0 <= int(_anio_de_dia(m[:1])[0]) <= c1), None)
        if dm is None:
            raise ErrorTendencias("TF de contaminantes: ningún mes de 2015-2019 con días de la muestra")
        dif = np.abs(_predicciones(fabrica, modelo, variante, CAMBIO, celdas, dm)
                     - _predicciones(fabrica, modelo, variante, COMPLETO, celdas, dm))
        dif_max = float(np.nanmax(dif)) if np.isfinite(dif).any() else 0.0
        if np.isnan(dif).any() or dif_max > constantes.valor("TF_CERO_TOL"):
            raise ErrorTendencias(f"TF de contaminantes de {variante} con ganadores A o C: la predicción cambia entre "
                                  "escenarios en el mes de verificación; es 0 por construcción: error de código "
                                  "(Anexo B; DEC-14)")
        mes = str((_EPOCA_D + dm[:1].astype("timedelta64[D]")).astype("datetime64[M]")[0])
        return {"variante": variante, "resultado": ResultadoTF.PASA.value, "verificacion_un_mes": True, "mes": mes,
                "dif_max": dif_max, "n_celdas": int(celdas.size), "n_dias": int(dm.size)}
    acc = AcumuladorComunas(comunas)
    for dm in meses:
        anio = int(_anio_de_dia(dm[:1])[0])
        completo = _predicciones(fabrica, modelo, variante, COMPLETO, celdas, dm)
        s_completo = _sumas_comuna(completo, w, idx, comunas.size)
        acc.sumar(COMPLETO, anio, s_completo)
        if c0 <= anio <= c1:
            acc.sumar(CAMBIO, anio, _sumas_comuna(_predicciones(fabrica, modelo, variante, CAMBIO, celdas, dm), w,
                                                  idx, comunas.size))
        elif c2 <= anio <= c3:
            acc.sumar(CAMBIO, anio, s_completo)                       # TEN-20: 2020-2024 «con todas»
    m_completo, m_cambio = acc.medias(COMPLETO), acc.medias(CAMBIO)
    delta = delta_tf1(m_cambio, m_completo)
    M = m_completo.en(range(desde, hasta + 1))
    nacional_c = _media_en(M, np.isfinite(M))
    ok_n = np.isfinite(nacional_c)
    if not ok_n.any():
        raise ErrorTendencias("TF de contaminantes: sin media nacional 2015-2024")
    media_nacional = float(np.sum(W[ok_n] * nacional_c[ok_n]) / np.sum(W[ok_n]))
    if not media_nacional > 0:
        raise ErrorTendencias("TF de contaminantes: la media nacional del escenario completo debe ser > 0 (cotas "
                              "relativas del Anexo B)")
    cota_media = umbrales.frac("M6_TF_MEDIA_PCT") * media_nacional
    cota_p95 = umbrales.frac("M6_TF_P95_PCT") * media_nacional
    ok = np.isfinite(delta)
    if not ok.any():
        raise ErrorTendencias("TF de contaminantes: ninguna comuna con Δ finito")
    media, p95 = media_p95_ponderados(np.abs(delta[ok]), W[ok])
    pasa = _cumple(media, p95, cota_media, cota_p95)
    return {"variante": variante, "resultado": (ResultadoTF.PASA if pasa else ResultadoTF.FALLA).value,
            "verificacion_un_mes": False, "media_pond": media, "p95_pond": p95, "cota_media": cota_media,
            "cota_p95": cota_p95, "media_nacional": media_nacional, "n_comunas": int(ok.sum()),
            "n_celdas": int(celdas.size), "n_dias": int(d.size)}


__all__ = (
    "AcumuladorComunas", "CANDIDATOS_USO", "CERO_POR_CONSTRUCCION", "CON_DERIVA", "CeldasTF", "DTYPE_MUESTRA",
    "ESCENARIOS", "ErrorTendencias", "EscenariosTF", "LOTE_PUNTOS_TF", "MediasComunaAnio", "MediasTF", "PRODUCTO_DE",
    "PasadaTF", "VARIABLES_TF", "VARIABLES_USO", "anio_de", "anios_regla", "celdas_tf", "combinaciones_nucleo",
    "comprobar_cero", "compuerta_deriva", "contenido_deriva_s6", "delta_tf1", "delta_tf2", "dias_tf_contaminantes",
    "escenarios_tf", "etiqueta_hiper", "filas_tf", "horas_del_anio", "media_p95_ponderados", "medias_comuna_anio",
    "mes2000", "muestra_tf_contaminantes", "producto_tf", "red_constante", "red_historica", "resultados_tf", "tf1",
    "tf2", "tf_contaminantes", "tf_por_uso",
)
