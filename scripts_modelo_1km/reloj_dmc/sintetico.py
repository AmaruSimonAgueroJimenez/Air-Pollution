"""Generadores sintéticos independientes de §8, batería D y fabricación con el formato real.

Regla de independencia (§8 «Reglas comunes»): la etiqueta se fabrica por un camino propio a partir de
u consciente de UTC, nunca con funciones del paquete:
  C(Z): ``u.astimezone(ZoneInfo(Z)).replace(tzinfo=None)``;  F(c): ``(u + timedelta(hours=c)).replace(tzinfo=None)``.
Por eso este módulo NO importa nada del paquete ``reloj_dmc`` (lo verifica una prueba por AST): sólo la
biblioteca estándar, numpy y pandas. El descargador y el adaptador fijados llegan como argumento
(``ModuleType``), cargados por quien llama con ``fijados``. Los esquemas del extracto y de los meses se
escriben aquí por un camino propio, y una prueba los compara con ``tipos``.
- Grupos A a C: ``fabricar_descarga`` corre ``descargar_meteo_chile_horaria.run_download`` con
  ``ClienteFalso`` (sin red) y ``GuardaFalsa`` (``defer_heavy_checks = True``), como
  scripts_pipeline/tests, siempre en una carpeta temporal. Con ``http_workers=1`` el descargador no
  importa ``_meteo_http_parallel``.
- Batería D: ``entrada_en_memoria`` da el extracto y los meses con el esquema de ``extraer_dmc``, sin
  pasar por el descargador (R-43); ``serie_era5_de_casos`` da la referencia en memoria;
  ``especificacion_bateria`` y ``caso_de_fila`` dan bateria_v1.csv y sus estaciones (R-29).
- La verdad de cada etiqueta: ``u_de_etiqueta``, ``equivalentes_en_P`` y ``comprobar_ida_y_vuelta``
  (``_utc(L, regla emitida) == u`` para toda etiqueta con regla, §8).

Modelo físico (§8.D, común a todas las estaciones). Todo se genera sobre un eje horario UTC global
(``EJE_T0`` … ``EJE_FIN``), así que un mismo u da siempre el mismo valor, se pida como se pida:
- verdad regional por sitio y réplica, compartida por la estación y su píxel: ruido sinóptico de
  temperatura, presión, punto de rocío y viento (proceso gaussiano suavizado), y uno de mesoescala;
- ciclo diario físico en hora solar aparente (Spencer, implementación propia): Ts con máximo a las 15 h
  solares; S2 = 1,16·cos³(lat) hPa con máximo a las 9,75 h solares y modulación semestral de ±20 %; S1
  de 0,6 hPa con máximo a las 7 h; brisa diurna;
- la estación agrega su propio ruido (local suave y blanco) y las perturbaciones de D2; la referencia
  «ERA5» lleva su propio ruido, la amplitud térmica al 92 % y, si se pide, el sesgo de fase de la red.
Las magnitudes del modelo (amplitudes, tiempos de correlación, ruidos) son del generador, no umbrales
del protocolo; la prueba AST de literales excluye este archivo (test_umbrales.EXCLUIDOS).

Lecturas propias, para el addendum de C1:
- R-29 (DISENO §7.2): diseño factorial de la batería. La Enmienda 1 (adoptada y anclada en APH 81bb100) la
  deja como lectura de implementación que va al addendum de C1; si el autor la considera un cambio de regla,
  pasa a una enmienda nueva. Ver ``especificacion_bateria``.
- R-43: los extractos de D no pasan por el descargador ni por el control propio de §3.2 (el generador no
  produce centinelas ni valores fuera de rango, y lo comprueba); el formato real lo cubren A a C.
- El portal sintético muestra la rejilla completa del mes en su propio reloj: una casilla por etiqueta
  que el reloj produce (sin la inexistente y con una sola repetida), tenga o no dato, y cada fila dos
  veces. De la repetida se conserva la observación del primer instante u (la del horario de verano).
- La base de zonas es la que deja quien llama (``entorno`` la reinicia al paquete tzdata). Según el punto
  E1-7 de la Enmienda 1 (adoptada), la base del sistema da la misma tabla de cambios.
- SIN-1. Cv(Z) es «la regla anterior a 2008 aplicada en todos los años» (§8.D): marzo y octubre, domingo ≥ 9, a
  las 03:00 y a las 04:00 UTC (Anexo A2). Coincide con C(Z) en 2009. En 2008 y en 2010 difiere sólo en el atraso,
  durante tres semanas (del sábado placebo del A2 al atraso real). Lo fija test_sintetico.
- SIN-2. Tipo d: la ventana civil de 08-20 h pasa a 09-21 h el 2016-07-01. Es un cambio administrativo de una
  hora, fuera de las fechas de cambio de hora.
- Con SIN-1 y SIN-2, los riesgos 1 y 3 de «Ola 4a cerrada» (COORDINACION_C1.md) no son errores del generador.
  Eran propiedades del texto v1.0.2: puntos E3-1 y E3-2 de PROPUESTA_ENMIENDA_3.md, que la Enmienda 3
  (adoptada el 2026-10-24) resolvió en el código de las líneas (E3-1 en lineas_fisicas; A′ en lineas_registro y
  decision; R en lineas_fisicas, LF-17). El generador no cambia.
"""
from __future__ import annotations

import functools
import hashlib
import html
import json
import math
import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

UTC = timezone.utc

TIPOS_ESTACION = ("a", "b", "c", "d", "e", "f", "g")
# a: automática 24 h (marcas en su propio reloj); b: sinóptica con observador; c: aeródromo diurno 11-23 h;
# d: aeródromo con cambio administrativo de horario; e: sólo Ts; f: cada 6 h; g: Ts en C(Santiago) y QFE en F(0).
ESCENARIOS = ("completo", "faltante30", "ralo2008")
VARIABLES_RELOJ = ("Ts", "QFE", "marcas")     # RelojVerdadero.variable; None = toda la fila
PASCUA_PROPIO = "F0-Pascua"                   # UTC con el calendario propio de Pascua (03/09/15/21)

# Eje horario UTC global del generador (incluye márgenes para 2000-2026 con desfases de ±15 h).
EJE_T0 = np.datetime64("1999-12-01T00", "h")
EJE_FIN = np.datetime64("2027-02-01T00", "h")                  # excluido
N_EJE = int((EJE_FIN - EJE_T0) // np.timedelta64(1, "h"))
_EJE_T0_DT = datetime(1999, 12, 1, tzinfo=UTC)
# ERA5-Land (§3.4): eje global desde 2000-01-01T00Z; el último dato es del 2026-09-15 a las 23:00 UTC.
ERA5_T0 = np.datetime64("2000-01-01T00", "h")
ERA5_ULTIMA = np.datetime64("2026-09-15T23", "h")
VARIABLES_ERA5 = ("t2m", "sp", "u10", "v10")                   # °C, hPa, m/s, m/s (= tipos.VARIABLES_ERA5)
# Última etiqueta del portal sintético: meses completos hasta septiembre de 2026 (después de ERA5, §6).
FIN_DATOS = datetime(2026, 9, 30, 23)
INICIO_TRAMOS = datetime(1900, 1, 1, tzinfo=UTC)               # desde del primer tramo de un reloj

# Formato del descargador. html_informe comprueba que el descargador recibido tenga estas columnas.
COLUMNAS_CRUDAS = (
    "day", "hour", "wind_direction_instant", "wind_speed_instant", "Ts", "Td",
    "TMin", "TMax", "relative_humidity", "WW", "VV", "visibility_reigning",
    "visibility_minimum", "QFE", "QFF", "QNH", "N", "Nh", "CL", "CM", "CH",
    "Hs1", "RR06",
)
COLUMNAS_HUELLA = COLUMNAS_CRUDAS[2:]                           # los 21 textos sin día ni hora (§3.2, R-13)
# Las VARIABLES del descargador: una fila sin ninguna es una casilla vacía (source_empty_slots).
VARIABLES_DESCARGADOR = ("wind_direction_instant", "wind_speed_instant", "Ts", "Td", "relative_humidity",
                         "QFE", "QFF", "QNH", "RR06")
METADATOS_CAUTELA = {"coordinates_valid_for_historical_dates": "unconfirmed",
                     "historical_station_moves_not_resolved": True}   # METADATA_CAUTIONS del descargador
CABECERAS_CATALOGO = ("Código Nacional", "Nombre", "Latitud", "Longitud", "Altitud (Mts)", "Fecha Creación",
                      "Tipo", "Región")
# script_sha256 de los meses en memoria: el descargador vigente (Anexo C, admitido en C0).
SCRIPT_SHA256_VIGENTE = "578fa26eea5b4ac4733c56aaf08e9b7b8904595fb8447dd54feb838642612120"
URL_FALSA = "https://example.invalid/sintetico"

# Esquemas, escritos por un camino propio (la prueba los compara con tipos.ESQUEMA_EXTRACTO_HORA y ESQUEMA_MES).
ESQUEMA_EXTRACTO = {
    "L": "datetime64[ns]", "anio": "int16", "mes": "int8", "id_artefacto": "int32", "medida": "bool",
    "ts": "float64", "motivo_ts": "int8", "qfe": "float64", "motivo_qfe": "int8", "td": "float64",
    "hr": "float64", "ff_kt": "float64", "dd_grados": "float64", "viento_valido": "bool",
    "qff_numerica": "bool", "rr": "bool", "tx": "bool", "tn": "bool", "observador": "bool", "huella": "string",
}
ESQUEMA_MESES = {
    "codigo": "string", "anio": "int16", "mes": "int8", "manifiesto": "string", "manifiesto_sha256": "string",
    "artefacto_sha256": "string", "id_artefacto": "Int32", "script_sha256": "string", "entra": "bool",
    "motivo_exclusion": "string", "row_count": "Int32", "source_empty_slots": "Int32",
    "expected_hour_slots": "Int32", "n_available_hours": "Int32", "duplicate_display_rows_removed": "Int32",
    "source_sha256": "string", "requested_start": "string", "requested_end": "string",
    "campos_faltantes": "object", "p_ts": "Int16", "p_qfe": "Int16", "lat_txt": "string", "lon_txt": "string",
    "alt_txt": "string",
}
ESQUEMA_ISD_PROPIO = {"codigo": "string", "u": "datetime64[ns]", "tipo_parte": "string", "tmp": "float64"}
# Un mes sin filas deja un manifiesto «pending_no_artifact» con verification_status «failed» (final_verify).
MOTIVO_MES_SIN_FILAS = "failed"
# Valores que el generador nunca debe producir (centinelas y rangos de §3.2): si aparecen, es un error suyo.
_TS_IMPOSIBLE, _QFE_IMPOSIBLE = (-60.0, 50.0), (400.0, 1100.0)
_CENTINELAS = {"ts": -40.0, "qfe": 500.0}

# --- Territorio y P (copia propia de §3.3 y §2.2, con nombres IANA completos) ---------------------
_ABREVIATURA = {"America/Santiago": "Santiago", "America/Coyhaique": "Coyhaique",
                "America/Punta_Arenas": "Punta_Arenas", "Pacific/Easter": "Pacific/Easter"}
_P_POR_TERRITORIO = {
    "continental": ("F(0)", "F(-3)", "F(-4)", "C(America/Santiago)"),
    "juan_fernandez_desventuradas": ("F(0)", "F(-3)", "F(-4)", "C(America/Santiago)"),
    "aysen": ("F(0)", "F(-3)", "F(-4)", "C(America/Coyhaique)", "C(America/Santiago)"),
    "magallanes": ("F(0)", "F(-3)", "F(-4)", "C(America/Punta_Arenas)", "C(America/Santiago)"),
    "antartica": ("F(0)", "F(-3)", "F(-4)", "C(America/Punta_Arenas)", "C(America/Santiago)"),
    "pascua_sala_y_gomez": ("F(0)", "F(-3)", "F(-4)", "F(-5)", "F(-6)", "C(Pacific/Easter)", "C(America/Santiago)"),
    "incierto": ("F(0)", "F(-3)", "F(-4)", "C(America/Santiago)", "C(America/Coyhaique)", "C(America/Punta_Arenas)"),
}
_ZONA_CIVIL = {"continental": "America/Santiago", "juan_fernandez_desventuradas": "America/Santiago",
               "aysen": "America/Coyhaique", "magallanes": "America/Punta_Arenas",
               "antartica": "America/Punta_Arenas", "pascua_sala_y_gomez": "Pacific/Easter",
               "incierto": "America/Santiago"}
# Regla anterior a 2008 (Anexo A2): (desfase de invierno, de verano) por zona.
_CV_DESFASES = {"America/Santiago": (-4, -3), "America/Coyhaique": (-4, -3), "America/Punta_Arenas": (-4, -3),
                "Pacific/Easter": (-6, -5)}

# --- Horarios por tipo de estación ----------------------------------------------------------------
VENTANA_AERODROMO = (8, 20)        # horas civiles con observación (inclusive): 11-23 h UTC en verano
CAMBIO_ADMINISTRATIVO = np.datetime64("2016-07-01T00", "h")    # tipo d: la ventana pasa a 9-21 h civiles
HORAS_RR = (0, 6, 12, 18)          # horas UTC de RR06 en el calendario normal (§1.1)
HORAS_RR_PASCUA = (3, 9, 15, 21)   # calendario propio de Pascua (§1.1, §6)
HORA_TX, HORA_TN = 0, 12           # TMax a las 00 h y TMin a las 12 h UTC (§1.1)
HORA_TX_PASCUA, HORA_TN_PASCUA = 3, 15

# --- Modelo físico --------------------------------------------------------------------------------
S2_AMPLITUD_HPA = 1.16             # §8.D: S2 = 1,16·cos³(lat) hPa
S2_HORA_MAX = 9.75                 # §8.D y §4.4: máximo a las 9,75 h solares
S2_MODULACION = 0.20               # ±20 % semestral, máximos en los equinoccios
S1_AMPLITUD_HPA = 0.6
S1_HORA_MAX = 7.0
FASE_TERMICA_H = 15.0              # máximo de Ts en hora solar
COCIENTE_AMPLITUD_ERA5 = 0.92
SESGO_MEDIO_T2M = -0.3
P_REFERENCIA = 1013.25
_KT_POR_MS = 1.943844
_DIA_15_ENE, _DIA_20_MAR, _DIA_15_JUL = 14.0, 79.0, 195.0     # días del año (0 = 1 de enero)
_COMPONENTES_REGION = {            # nombre → (tiempo de correlación en h, desviación)
    "t_syn": (72.0, 2.5), "t_meso": (4.0, 0.6), "td_syn": (60.0, 1.6), "p_meso": (4.0, 0.25),
    "wu_syn": (36.0, 2.0), "wv_syn": (36.0, 2.0),
}
_PROB_SIN_PRECIPITACION = 0.85     # RR06 «s/p»
_PROB_FALTA_ISD, _PROB_TRANSCRIPCION_ISD = 0.05, 0.02

PERTURBACIONES_ADMITIDAS = (
    "desfase_termico_estacion",    # h; máximo de Ts de la estación corrido respecto de la referencia
    "sesgo_termico_referencia",    # h; máximo de t2m de la referencia corrido (común a la red)
    "s1_local_amplitud", "s1_local_desfase",   # hPa y h; S1 local de la estación
    "fase_s2_estacion",            # h; máximo de S2 de la estación corrido
    "semantica",                   # Δc en h: el valor de L corresponde a u − Δc (+1/6: obs. a −10 min; +0,5: media de la hora que termina en L)
    "sin_marcas",                  # 1: sin RR06, TMax, TMin ni observador (C3b)
    "costera",                     # 1: la celda propia no tiene dato; las vecinas sí
    "dz",                          # m: z_cat − altitud del píxel
)


@dataclass(frozen=True)
class Sitio:
    nombre: str
    lat: float
    lon: float
    alt_m: float
    cod_comuna: int
    con_pixel: bool


# Sitios de la batería (§8.D). Altitudes y comunas son del generador; el píxel se fabrica con la misma
# altitud que la estación (Δz = 0) salvo la perturbación «dz».
SITIOS: Mapping[str, Sitio] = {
    "santiago": Sitio("santiago", -33.4, -70.6, 520.0, 13101, True),
    "punta_arenas": Sitio("punta_arenas", -53.0, -70.9, 37.0, 12101, True),
    "coyhaique": Sitio("coyhaique", -45.6, -72.1, 310.0, 11101, True),
    "pascua": Sitio("pascua", -27.15, -109.4, 51.0, 5201, False),
    "arica": Sitio("arica", -18.5, -70.3, 58.0, 15101, True),
    "valdivia": Sitio("valdivia", -39.8, -73.2, 19.0, 14101, True),
    "juan_fernandez": Sitio("juan_fernandez", -33.6, -78.8, 30.0, 5104, False),
    "incierto": Sitio("incierto", -49.5, -73.5, 300.0, 0, True),
}
_REGION_NOMBRE = {13: "Metropolitana", 12: "Magallanes", 11: "Aysén", 5: "Valparaíso", 15: "Arica y Parinacota",
                  14: "Los Ríos"}
_TIPO_NOMBRE = {"a": "Automática", "b": "Sinóptica", "c": "Aeródromo", "d": "Aeródromo", "e": "Automática",
                "f": "Sinóptica", "g": "Automática"}


@dataclass(frozen=True)
class RelojVerdadero:
    """Reloj verdadero por tramos de u: ((desde_utc, «F(-4)»), (2018-07-01T00Z, «F(0)»), …).

    Especificaciones propias del generador: «F(<c>)», «C(<zona IANA>)», «Cv(<zona IANA>)» (regla
    anterior a 2008 en todos los años) y «F0-Pascua» (UTC con el calendario propio 03/09/15/21).
    ``variable``: None (toda la fila), «Ts» (Ts, Td y HR), «QFE» (QFE, QFF y viento) o «marcas» (RR06,
    TMax, TMin y observador; si falta, siguen al reloj de QFE). El tipo (g) lleva un reloj para Ts y
    otro para QFE.
    """
    tramos: tuple[tuple[datetime, str], ...]
    variable: str | None = None


@dataclass(frozen=True)
class CasoSintetico:
    codigo: str
    relojes: tuple[RelojVerdadero, ...]
    tipo: str
    escenario: str
    lat: float
    lon: float
    alt_m: float
    con_pixel: bool
    cod_comuna: int
    perturbaciones: Mapping[str, float] = field(default_factory=dict)
    replica: int = 0
    semilla: int = 0
    anios: tuple[int, int] = (2008, 2026)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
_BASE_SEMILLA = "reloj-dmc-sintetico/v1"


def _semilla(*partes) -> int:
    texto = "|".join((_BASE_SEMILLA,) + tuple(str(p) for p in partes))
    return int.from_bytes(hashlib.sha256(texto.encode("utf-8")).digest()[:8], "big")


def _rng(*partes) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(_semilla(*partes)))


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class _Cache:
    """Caché LRU pequeña con clave explícita (CasoSintetico no es hashable por su diccionario)."""

    def __init__(self, tamano: int):
        self.tamano = tamano
        self._d: OrderedDict = OrderedDict()

    def obtener(self, clave, fabricar: Callable[[], object]):
        if clave in self._d:
            self._d.move_to_end(clave)
            return self._d[clave]
        valor = fabricar()
        self._d[clave] = valor
        while len(self._d) > self.tamano:
            self._d.popitem(last=False)
        return valor

    def vaciar(self) -> None:
        self._d.clear()


def _a_utc(u: datetime) -> datetime:
    if not isinstance(u, datetime) or u.tzinfo is None or u.utcoffset() is None:
        raise ValueError(f"u debe ser un datetime consciente de zona (UTC): {u!r}")
    return u.astimezone(UTC)


def _hora64(d: datetime) -> np.datetime64:
    """datetime consciente → datetime64[h] UTC ingenuo (exige hora en punto)."""
    d = _a_utc(d)
    if d.minute or d.second or d.microsecond:
        raise ValueError(f"instante que no está en la hora en punto: {d.isoformat()}")
    return np.datetime64(d.replace(tzinfo=None), "h")


def _indice_eje(instantes: np.ndarray) -> np.ndarray:
    """datetime64 UTC ingenuo (en punto) → índice del eje global; error fuera del eje."""
    seg = np.asarray(instantes).astype("datetime64[s]")
    if np.isnat(seg).any():
        raise ValueError("instante NaT")
    d = (seg - EJE_T0.astype("datetime64[s]")).astype(np.int64)
    if (d % 3600).any():
        raise ValueError("instantes fuera de la hora en punto")
    k = d // 3600
    if k.size and (k.min() < 0 or k.max() >= N_EJE):
        raise ValueError("instantes fuera del eje del generador (1999-12 … 2027-01)")
    return k


def _instantes(u) -> np.ndarray:
    """Secuencia de datetimes conscientes o datetime64 UTC ingenuos → datetime64[h]."""
    if isinstance(u, np.ndarray) and np.issubdtype(u.dtype, np.datetime64):
        return u.astype("datetime64[h]")
    if isinstance(u, pd.DatetimeIndex):
        if u.tz is not None:
            u = u.tz_convert("UTC").tz_localize(None)
        return u.to_numpy().astype("datetime64[h]")
    return np.array([_hora64(x) for x in u], dtype="datetime64[h]")


def _eje(k: np.ndarray) -> np.ndarray:
    return EJE_T0 + np.asarray(k, dtype=np.int64).astype("timedelta64[h]")


def _a_datetimes(arr64: np.ndarray, consciente: bool) -> list[datetime]:
    lista = arr64.astype("datetime64[us]").tolist()
    return [d.replace(tzinfo=UTC) for d in lista] if consciente else lista


# ---------------------------------------------------------------------------
# Relojes: camino propio de §8 (u consciente de UTC → etiqueta ingenua)
# ---------------------------------------------------------------------------
_RE_F = re.compile(r"F\((0|[+-][1-9][0-9]*)\)")
_RE_C = re.compile(r"(Cv|C)\(([A-Za-z_]+(?:/[A-Za-z_]+)+)\)")


def _especificacion(reloj: str) -> tuple[str, object]:
    """«F(c)» → ("F", c); «C(Z)» → ("C", Z); «Cv(Z)» → ("Cv", Z); «F0-Pascua» → ("F", 0)."""
    if reloj == PASCUA_PROPIO:
        return "F", 0
    m = _RE_F.fullmatch(reloj)
    if m:
        return "F", int(m.group(1))
    m = _RE_C.fullmatch(reloj)
    if m:
        if m.group(1) == "Cv" and m.group(2) not in _CV_DESFASES:
            raise ValueError(f"Cv sólo para {tuple(_CV_DESFASES)}: {reloj!r}")
        return m.group(1), m.group(2)
    raise ValueError(f"especificación de reloj inválida: {reloj!r}")


def _domingo_desde(anio: int, mes: int, dia: int) -> date:
    d = date(anio, mes, dia)
    return d + timedelta(days=(6 - d.weekday()) % 7)


def _cambios_regla_anterior(anio: int) -> tuple[datetime, datetime]:
    """(atraso, adelanto) de la regla anterior a 2008 en ``anio`` (Anexo A2: marzo y octubre, domingo ≥ 9;
    el atraso a las 03:00 UTC y el adelanto a las 04:00 UTC del domingo, en todas las zonas)."""
    atraso, adelanto = _domingo_desde(anio, 3, 9), _domingo_desde(anio, 10, 9)
    return (datetime(atraso.year, atraso.month, atraso.day, 3, tzinfo=UTC),
            datetime(adelanto.year, adelanto.month, adelanto.day, 4, tzinfo=UTC))


def _desfase_regla_anterior(zona: str, u: datetime) -> int:
    invierno, verano = _CV_DESFASES[zona]
    atraso, adelanto = _cambios_regla_anterior(u.year)
    return invierno if atraso <= u < adelanto else verano


def etiqueta_desde_utc(u: datetime, reloj: str) -> datetime:
    """Camino propio de §8 (u consciente de UTC → etiqueta ingenua).

    F(c) y «F0-Pascua»: ``(u + timedelta(hours=c)).replace(tzinfo=None)``. C(Z):
    ``u.astimezone(ZoneInfo(Z)).replace(tzinfo=None)``. Cv(Z): hora civil de Z con la regla anterior a
    2008 en todos los años, con transiciones propias (``_cambios_regla_anterior``), sin ZoneInfo.
    Cv sirve al diagnóstico de reglas vencidas (§4.1.4), cuyo cálculo precisa el punto E1-4 de la Enmienda 1
    (adoptada; está al final de §4.1.4 del v1.0.1); el generador no depende de esa precisión.
    """
    u = _a_utc(u)
    tipo, valor = _especificacion(reloj)
    if tipo == "F":
        return (u + timedelta(hours=valor)).replace(tzinfo=None)
    if tipo == "C":
        return u.astimezone(ZoneInfo(valor)).replace(tzinfo=None)
    return (u + timedelta(hours=_desfase_regla_anterior(valor, u))).replace(tzinfo=None)


def horas_utc(desde: datetime, hasta: datetime) -> list[datetime]:
    """Instantes UTC conscientes de hora en hora, de ``desde`` a ``hasta`` inclusive (en punto)."""
    a, b = _hora64(desde), _hora64(hasta)
    if b < a:
        raise ValueError("hasta es anterior a desde")
    n = int((b - a) // np.timedelta64(1, "h"))
    a_dt = _a_utc(desde)
    return [a_dt + timedelta(hours=k) for k in range(n + 1)]


@functools.lru_cache(maxsize=None)
def _etiquetas_eje(reloj: str) -> np.ndarray:
    """Etiqueta (datetime64[h]) de cada instante del eje global bajo ``reloj``, por el camino propio.

    Para C(Z) se aplica la fórmula de §8 a cada instante (una vez por zona y proceso).
    """
    tipo, valor = _especificacion(reloj)
    k = np.arange(N_EJE, dtype=np.int64)
    if tipo == "F":
        salida = _eje(k) + np.timedelta64(valor, "h")
    elif tipo == "C":
        zona = ZoneInfo(valor)
        uno = timedelta(hours=1)
        lista, u = [], _EJE_T0_DT
        for _ in range(N_EJE):
            lista.append(u.astimezone(zona).replace(tzinfo=None))
            u = u + uno
        minutos = np.array(lista, dtype="datetime64[m]")
        if (minutos.astype(np.int64) % 60).any():
            raise ValueError(f"la zona {valor} tiene desfases que no son de horas enteras")
        salida = minutos.astype("datetime64[h]")
    else:
        invierno, verano = _CV_DESFASES[valor]
        eje = _eje(k)
        desfase = np.full(N_EJE, verano, dtype=np.int64)
        anio0 = int(str(EJE_T0)[:4])
        for anio in range(anio0, anio0 + 30):
            atraso, adelanto = (_hora64(d) for d in _cambios_regla_anterior(anio))
            desfase[(eje >= atraso) & (eje < adelanto)] = invierno
        salida = eje + desfase.astype("timedelta64[h]")
    salida.flags.writeable = False
    return salida


def _desdes(reloj: RelojVerdadero) -> list[np.datetime64]:
    return [_hora64(d) for d, _ in reloj.tramos]


def _etiquetas_de_reloj(reloj: RelojVerdadero, k: np.ndarray) -> np.ndarray:
    """Etiquetas de los instantes del eje ``k`` bajo un reloj con tramos."""
    eje = _eje(k)
    salida = np.empty(len(k), dtype="datetime64[h]")
    desdes = _desdes(reloj)
    if len(k) and eje.min() < desdes[0]:
        raise ValueError("instantes anteriores al primer tramo del reloj")
    for i, (_, spec) in enumerate(reloj.tramos):
        m = eje >= desdes[i]
        if i + 1 < len(desdes):
            m &= eje < desdes[i + 1]
        salida[m] = _etiquetas_eje(spec)[k[m]]
    return salida


def _calendario_pascua(reloj: RelojVerdadero, k: np.ndarray) -> np.ndarray:
    eje = _eje(k)
    salida = np.zeros(len(k), dtype=bool)
    desdes = _desdes(reloj)
    for i, (_, spec) in enumerate(reloj.tramos):
        if spec != PASCUA_PROPIO:
            continue
        m = eje >= desdes[i]
        if i + 1 < len(desdes):
            m &= eje < desdes[i + 1]
        salida |= m
    return salida


def relojes_desde_texto(texto: str) -> tuple[RelojVerdadero, ...]:
    """Gramática de bateria_v1.csv: «F(0)»; «F(-4);F(0)@2018-07-01T00:00Z» (tramos por u);
    «Ts:C(America/Santiago)|QFE:F(0)» (un reloj por variable)."""
    relojes = []
    for parte in texto.split("|"):
        variable = None
        if ":" in parte.split("@")[0].split(";")[0]:
            variable, parte = parte.split(":", 1)
            if variable not in VARIABLES_RELOJ:
                raise ValueError(f"variable de reloj desconocida: {variable!r}")
        tramos = []
        for i, tramo in enumerate(parte.split(";")):
            if "@" in tramo:
                spec, desde = tramo.split("@", 1)
                if i == 0 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:00Z", desde):
                    raise ValueError(f"tramo inválido: {tramo!r}")
                inicio = datetime.fromisoformat(desde[:-1]).replace(tzinfo=UTC)
            elif i == 0:
                spec, inicio = tramo, INICIO_TRAMOS
            else:
                raise ValueError(f"tramo sin fecha de inicio: {tramo!r}")
            _especificacion(spec)
            tramos.append((inicio, spec))
        relojes.append(RelojVerdadero(tuple(tramos), variable))
    return tuple(relojes)


def texto_de_relojes(relojes: Sequence[RelojVerdadero]) -> str:
    partes = []
    for r in relojes:
        tramos = []
        for i, (desde, spec) in enumerate(r.tramos):
            if i == 0 and desde == INICIO_TRAMOS:
                tramos.append(spec)
            else:
                tramos.append(f"{spec}@{_a_utc(desde).strftime('%Y-%m-%dT%H:00Z')}")
        texto = ";".join(tramos)
        partes.append(texto if r.variable is None else f"{r.variable}:{texto}")
    return "|".join(partes)


def _id_tipos(spec: str) -> str:
    """Especificación propia → id de tipos.Hipotesis («C(America/Santiago)» → «C(Santiago)»)."""
    tipo, valor = _especificacion(spec)
    if tipo == "F":
        return "F(0)" if valor == 0 else f"F({valor:+d})"
    return f"{tipo}({_ABREVIATURA[valor]})"


def territorio_sintetico(lat: float, lon: float, cod_comuna: int) -> str:
    """§3.3 por un camino propio, con la celda propia de cod_comuna conocido."""
    if lat < -60:
        return "antartica"
    if lon < -100:
        return "pascua_sala_y_gomez"
    if -100 <= lon < -77:
        return "juan_fernandez_desventuradas"
    if not cod_comuna:
        return "incierto"
    region = cod_comuna // 1000
    return "aysen" if region == 11 else "magallanes" if region == 12 else "continental"


def _especificaciones(caso_o_relojes) -> list[str]:
    relojes = caso_o_relojes.relojes if isinstance(caso_o_relojes, CasoSintetico) else caso_o_relojes
    return [spec for r in relojes for _, spec in r.tramos]


def fuera_de_P(relojes: Sequence[RelojVerdadero], territorio: str) -> bool:
    """Algún tramo del reloj verdadero no es una H de P (§2.2); «F0-Pascua» es F(0) y Cv nunca está en P."""
    P = set(_P_POR_TERRITORIO[territorio])
    return any(("F(0)" if s == PASCUA_PROPIO else s) not in P for s in _especificaciones(relojes))


# ---------------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------------
def _validar_caso(caso: CasoSintetico) -> None:
    if not re.fullmatch(r"\d{6}", str(caso.codigo)):
        raise ValueError(f"código de estación inválido: {caso.codigo!r}")
    if caso.tipo not in TIPOS_ESTACION or caso.escenario not in ESCENARIOS:
        raise ValueError(f"tipo o escenario desconocido: {caso.tipo!r}, {caso.escenario!r}")
    if not caso.relojes:
        raise ValueError("el caso no tiene reloj")
    variables = [r.variable for r in caso.relojes]
    if len(set(variables)) != len(variables) or any(v not in VARIABLES_RELOJ + (None,) for v in variables):
        raise ValueError(f"variables de reloj repetidas o desconocidas: {variables}")
    if None in variables and len(variables) > 1:
        raise ValueError("un reloj de toda la fila no se combina con relojes por variable")
    if caso.tipo == "g" and not {"Ts", "QFE"} <= set(variables):
        raise ValueError("el tipo g lleva un reloj para Ts y otro para QFE")
    for r in caso.relojes:
        if not r.tramos:
            raise ValueError("reloj sin tramos")
        desdes = _desdes(r)
        if any(b <= a for a, b in zip(desdes, desdes[1:])):
            raise ValueError("tramos de reloj fuera de orden")
        for _, spec in r.tramos:
            tipo, valor = _especificacion(spec)
            if tipo == "C":
                ZoneInfo(valor)                         # «America/Easter» no existe: error (§2.2)
    desconocidas = set(caso.perturbaciones) - set(PERTURBACIONES_ADMITIDAS)
    if desconocidas:
        raise ValueError(f"perturbaciones desconocidas: {sorted(desconocidas)}")
    a0, a1 = caso.anios
    if not (2000 <= a0 <= a1 <= 2026):
        raise ValueError(f"años fuera de 2000-2026: {caso.anios}")


def _clave(caso: CasoSintetico) -> tuple:
    _validar_caso(caso)
    return (caso.codigo, caso.relojes, caso.tipo, caso.escenario, float(caso.lat), float(caso.lon),
            float(caso.alt_m), bool(caso.con_pixel), int(caso.cod_comuna),
            tuple(sorted((k, float(v)) for k, v in caso.perturbaciones.items())), int(caso.replica),
            int(caso.semilla), tuple(int(a) for a in caso.anios))


def caso_simple(codigo: str = "900001", reloj: str = "F(0)", tipo: str = "a", escenario: str = "completo",
                sitio: str = "santiago", *, anios: tuple[int, int] = (2019, 2019),
                perturbaciones: Mapping[str, float] | None = None, replica: int = 0,
                semilla: int = 0) -> CasoSintetico:
    """Un caso en un sitio de ``SITIOS`` con un reloj en la gramática de ``relojes_desde_texto``."""
    s = SITIOS[sitio]
    caso = CasoSintetico(codigo=codigo, relojes=relojes_desde_texto(reloj), tipo=tipo, escenario=escenario,
                         lat=s.lat, lon=s.lon, alt_m=s.alt_m, con_pixel=s.con_pixel, cod_comuna=s.cod_comuna,
                         perturbaciones=dict(perturbaciones or {}), replica=replica, semilla=semilla,
                         anios=anios)
    _validar_caso(caso)
    return caso


def _relojes_por_familia(caso: CasoSintetico) -> dict[str, RelojVerdadero]:
    """T: Ts, Td, HR; P: QFE, QFF, viento; M: RR06, TMax, TMin y observador."""
    por_variable = {r.variable: r for r in caso.relojes}
    general = por_variable.get(None)
    t = por_variable.get("Ts", general)
    p = por_variable.get("QFE", general)
    if t is None or p is None:
        raise ValueError("faltan relojes para Ts o para QFE")
    return {"T": t, "P": p, "M": por_variable.get("marcas", p)}


# ---------------------------------------------------------------------------
# Modelo físico
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _calendario_eje() -> dict[str, np.ndarray]:
    k = np.arange(N_EJE, dtype=np.int64)
    eje = _eje(k)
    dias = eje.astype("datetime64[D]")
    dia_del_anio = (dias - dias.astype("datetime64[Y]").astype("datetime64[D]")).astype(np.int64) + 1
    hora = (eje.astype(np.int64) % 24).astype(np.float64)
    b = 2 * np.pi * (dia_del_anio - 1) / 365
    # Ecuación del tiempo de Spencer (minutos), implementación propia (§4.4).
    eot = 229.18 * (0.000075 + 0.001868 * np.cos(b) - 0.032077 * np.sin(b) - 0.014615 * np.cos(2 * b)
                    - 0.040849 * np.sin(2 * b))
    return {"dia": dia_del_anio.astype(np.float64), "hora": hora, "eot": eot}


def _base(kf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    k = np.clip(np.floor(kf).astype(np.int64), 0, N_EJE - 1)
    return k, kf - k


def _hora_solar(kf: np.ndarray, lon: float) -> np.ndarray:
    """Hora solar aparente en el instante fraccionario ``kf`` del eje (§4.4)."""
    cal = _calendario_eje()
    k, frac = _base(kf)
    return (cal["hora"][k] + frac + lon / 15.0 + cal["eot"][k] / 60.0) % 24.0


def _angulo_anual(kf: np.ndarray) -> np.ndarray:
    cal = _calendario_eje()
    k, frac = _base(kf)
    return 2 * np.pi * (cal["dia"][k] - 1 + (cal["hora"][k] + frac) / 24.0) / 365.25


def _ang(dia: float) -> float:
    return 2 * np.pi * dia / 365.25


def _ruido_suave(rng: np.random.Generator, n: int, tau_h: float, sigma: float) -> np.ndarray:
    """Ruido gaussiano filtrado con un núcleo gaussiano de desviación ``tau_h`` horas, de desviación ``sigma``.

    La convolución es circular sobre un largo potencia de 2 (N_EJE tiene el factor primo 827, que haría
    lenta la FFT) y se recorta a ``n``.
    """
    largo = 1 << int(math.ceil(math.log2(n)))
    blanco = rng.standard_normal(largo)
    f = np.fft.rfftfreq(largo)
    x = np.fft.irfft(np.fft.rfft(blanco) * np.exp(-0.5 * (2 * np.pi * f * tau_h) ** 2), largo)[:n]
    return x * (sigma / x.std())


def _sigma_presion(lat: float) -> float:
    return float(min(max(1.5 + 0.17 * (abs(lat) - 15.0), 1.5), 9.0))


_CACHE_REGION = _Cache(8)


def _region(lat: float, lon: float, replica: int) -> dict[str, np.ndarray]:
    """Verdad regional de un sitio y una réplica, compartida por sus estaciones y sus píxeles."""
    clave = (f"{lat:.4f}", f"{lon:.4f}", int(replica))

    def fabricar():
        comps = dict(_COMPONENTES_REGION, p_syn=(60.0, _sigma_presion(lat)))
        return {nombre: _ruido_suave(_rng("region", *clave, nombre), N_EJE, tau, sigma)
                for nombre, (tau, sigma) in comps.items()}
    return _CACHE_REGION.obtener(clave, fabricar)


def _temperatura_media(lat: float, alt: float, ang: np.ndarray) -> np.ndarray:
    return 31.0 - 0.45 * abs(lat) - 0.0065 * alt + (1.5 + 0.12 * abs(lat)) * np.cos(ang - _ang(_DIA_15_ENE))


def _amplitud_termica(lat: float, lon: float, ang: np.ndarray) -> np.ndarray:
    insular = 0.4 if lon < -77 else 1.0
    return (2.0 + 4.5 * np.cos(np.radians(lat)) ** 2) * (1 + 0.25 * np.cos(ang - _ang(_DIA_15_ENE))) * insular


def _ciclo_termico(tsol: np.ndarray, fase_h: float, a1: np.ndarray) -> np.ndarray:
    """Ciclo diario con primer armónico de fase ``fase_h`` (h solares) y amplitud ``a1``."""
    x = 2 * np.pi * (tsol - fase_h) / 24.0
    return a1 * (np.cos(x) + 0.2 * np.cos(2 * x + 0.6))


def _presion_nivel(alt: float) -> float:
    """Inversa de z_pix (§3.3): p tal que 44.330,8·[1 − (p/1.013,25)^0,190263] = alt."""
    return P_REFERENCIA * (1 - alt / 44330.8) ** (1 / 0.190263)


def _s2(lat: float, ang: np.ndarray, tsol: np.ndarray, hora_max: float) -> np.ndarray:
    amplitud = S2_AMPLITUD_HPA * np.cos(np.radians(lat)) ** 3 * (1 + S2_MODULACION * np.cos(2 * (ang - _ang(_DIA_20_MAR))))
    return amplitud * np.cos(2 * np.pi * (tsol - hora_max) / 12.0)


def _s1(tsol: np.ndarray, amplitud: float, hora_max: float) -> np.ndarray:
    return amplitud * np.cos(2 * np.pi * (tsol - hora_max) / 24.0)


def _presion_estacional(ang: np.ndarray) -> np.ndarray:
    return 3.0 * np.cos(ang - _ang(_DIA_15_JUL))


def _viento_verdadero(reg: Mapping[str, np.ndarray], mover, tsol: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    brisa = 1.0 + 1.5 * np.cos(2 * np.pi * (tsol - FASE_TERMICA_H) / 24.0)
    angulo = np.radians(45.0)
    return mover(reg["wu_syn"]) + brisa * np.cos(angulo), mover(reg["wv_syn"]) + brisa * np.sin(angulo)


_CACHE_SENALES = _Cache(2)


def _senales_eje(caso: CasoSintetico) -> dict[str, np.ndarray]:
    """Valores de la estación en todo el eje (incluye las perturbaciones de D2 y la semántica)."""
    clave = _clave(caso)

    def fabricar():
        p = caso.perturbaciones
        lat, lon, alt = float(caso.lat), float(caso.lon), float(caso.alt_m)
        reg = _region(lat, lon, caso.replica)
        k = np.arange(N_EJE, dtype=np.float64)
        corrimiento = -float(p.get("semantica", 0.0))         # u efectivo = u − Δc
        kf = k + corrimiento
        mover = (lambda a: np.interp(kf, k, a)) if corrimiento else (lambda a: a)

        def ruido(nombre: str) -> np.random.Generator:
            return _rng("estacion", caso.codigo, caso.semilla, nombre)
        tsol, ang = _hora_solar(kf, lon), _angulo_anual(kf)
        tm = _temperatura_media(lat, alt, ang)
        a1 = _amplitud_termica(lat, lon, ang)
        fase = FASE_TERMICA_H + float(p.get("desfase_termico_estacion", 0.0))
        ts = (tm + mover(reg["t_syn"]) + mover(reg["t_meso"]) + _ciclo_termico(tsol, fase, a1)
              + mover(_ruido_suave(ruido("t_local"), N_EJE, 4.0, 0.5)) + 0.25 * ruido("t_blanco").standard_normal(N_EJE))
        td = (tm - 7.0 + 0.6 * (mover(reg["t_syn"]) + mover(reg["t_meso"])) + mover(reg["td_syn"])
              + 0.6 * np.cos(2 * np.pi * (tsol - 13.0) / 24.0)
              + 0.3 * ruido("td_blanco").standard_normal(N_EJE))
        td = np.minimum(td, ts - 0.3)
        hr = 100 * np.exp(17.625 * td / (243.04 + td) - 17.625 * ts / (243.04 + ts))
        p0 = _presion_nivel(alt)
        s2 = _s2(lat, ang, tsol, S2_HORA_MAX + float(p.get("fase_s2_estacion", 0.0)))
        s1 = _s1(tsol, float(p.get("s1_local_amplitud", S1_AMPLITUD_HPA)),
                 S1_HORA_MAX + float(p.get("s1_local_desfase", 0.0)))
        qfe = (p0 + (p0 / P_REFERENCIA) * (mover(reg["p_syn"]) + mover(reg["p_meso"])) + _presion_estacional(ang)
               + s2 + s1 + mover(_ruido_suave(ruido("p_local"), N_EJE, 3.0, 0.15))
               + 0.08 * ruido("p_blanco").standard_normal(N_EJE))
        qff = qfe * (P_REFERENCIA / p0) + 0.1 * ruido("qff_blanco").standard_normal(N_EJE)
        wu, wv = _viento_verdadero(reg, mover, tsol)
        wu = wu + 0.8 * ruido("wu_blanco").standard_normal(N_EJE)
        wv = wv + 0.8 * ruido("wv_blanco").standard_normal(N_EJE)
        r = ruido("marcas")
        sorteo_rr = r.random(N_EJE)
        mm = np.round(r.exponential(2.0, N_EJE), 1) + 0.1
        digitos = r.integers(0, 10, size=(5, N_EJE), dtype=np.int8)
        digitos[:2] %= 9                                          # N y Nh en octas
        return {"ts": ts, "td": td, "hr": hr, "qfe": qfe, "qff": qff, "viento_u": wu, "viento_v": wv,
                "sorteo_rr": sorteo_rr, "rr_mm": mm, "digitos": digitos}
    return _CACHE_SENALES.obtener(clave, fabricar)


def senales(caso: CasoSintetico, u: Sequence[datetime]) -> pd.DataFrame:
    """Ts, QFE, Td, HR, viento verdaderos en u: ciclo diario físico, ruido sinóptico, S2 = 1,16·cos³(lat) hPa
    con máximo a las 9,75 h solares y ±20 % semestral, y las perturbaciones de D2.

    ``u``: datetimes conscientes o datetime64 UTC ingenuos, en punto y dentro del eje. Son los valores que la
    estación informa para el instante nominal u (con la semántica perturbada, si la hay).
    """
    k = _indice_eje(_instantes(u))
    s = _senales_eje(caso)
    return pd.DataFrame({c: s[c][k] for c in ("ts", "td", "hr", "qfe", "qff", "viento_u", "viento_v")},
                        index=pd.DatetimeIndex(_eje(k).astype("datetime64[ns]"), name="u"))


_CACHE_REFERENCIA = _Cache(16)


def _referencia_eje(pixel_id: int, sitio: tuple[float, float], replica: int, lat: float, lon: float, alt: float,
                    sesgo: float) -> dict[str, np.ndarray]:
    """t2m, sp, u10, v10 de un píxel en todo el eje, NaN fuera de la ventana de ERA5-Land."""
    clave = (int(pixel_id), sitio, int(replica), float(lat), float(lon), float(alt), float(sesgo))

    def fabricar():
        reg = _region(sitio[0], sitio[1], replica)
        k = np.arange(N_EJE, dtype=np.float64)
        tsol, ang = _hora_solar(k, lon), _angulo_anual(k)

        def mover(a):
            return a

        def ruido(nombre: str) -> np.random.Generator:
            return _rng("era5", pixel_id, replica, nombre)
        t2m = (_temperatura_media(lat, alt, ang) + reg["t_syn"] + reg["t_meso"]
               + COCIENTE_AMPLITUD_ERA5 * _ciclo_termico(tsol, FASE_TERMICA_H + sesgo, _amplitud_termica(lat, lon, ang))
               + _ruido_suave(ruido("t_local"), N_EJE, 4.0, 0.4) + 0.15 * ruido("t_blanco").standard_normal(N_EJE)
               + SESGO_MEDIO_T2M)
        p0 = _presion_nivel(alt)
        sp = (p0 + (p0 / P_REFERENCIA) * (reg["p_syn"] + reg["p_meso"]) + _presion_estacional(ang)
              + _s2(lat, ang, tsol, S2_HORA_MAX) + _s1(tsol, S1_AMPLITUD_HPA, S1_HORA_MAX)
              + _ruido_suave(ruido("p_local"), N_EJE, 3.0, 0.1) + 0.05 * ruido("p_blanco").standard_normal(N_EJE))
        wu, wv = _viento_verdadero(reg, mover, tsol)
        u10 = 0.8 * wu + 0.4 * ruido("u_blanco").standard_normal(N_EJE)
        v10 = 0.8 * wv + 0.4 * ruido("v_blanco").standard_normal(N_EJE)
        eje = _eje(np.arange(N_EJE))
        fuera = (eje < ERA5_T0) | (eje > ERA5_ULTIMA)
        salida = {}
        for nombre, valores in (("t2m", t2m), ("sp", sp), ("u10", u10), ("v10", v10)):
            valores = valores.copy()
            valores[fuera] = np.nan
            salida[nombre] = valores
        return salida
    return _CACHE_REFERENCIA.obtener(clave, fabricar)


def referencia_era5(caso: CasoSintetico, u: Sequence[datetime], *, sesgo_termico_h: float = 0.0) -> pd.DataFrame:
    """t2m, sp, u10, v10 «ERA5» con su propio ruido (y el sesgo de fase de D2) en el píxel propio del caso.

    ``sesgo_termico_h`` > 0 atrasa el máximo térmico de la referencia. NaN fuera de 2000-01 … 2026-09-15T23Z.
    """
    k = _indice_eje(_instantes(u))
    pid, lat_c, lon_c = _pixel_de(caso.lat, caso.lon)[:3]
    alt = float(caso.alt_m) - float(caso.perturbaciones.get("dz", 0.0))
    ref = _referencia_eje(pid, (round(float(caso.lat), 4), round(float(caso.lon), 4)), caso.replica, lat_c, lon_c,
                          alt, sesgo_termico_h)
    return pd.DataFrame({v: ref[v][k] for v in VARIABLES_ERA5},
                        index=pd.DatetimeIndex(_eje(k).astype("datetime64[ns]"), name="u"))


def _faltantes_eje(caso: CasoSintetico) -> np.ndarray:
    """Horas en que la estación no transmite: bloques de 1 a 10 días (UTC) según el escenario."""
    if caso.escenario == "completo":
        return np.zeros(N_EJE, dtype=bool)
    n_dias = N_EJE // 24 + 1
    r = _rng("faltantes", caso.codigo, caso.semilla, caso.escenario)
    largos = r.integers(1, 11, size=n_dias)
    sorteo = r.random(n_dias)
    if caso.escenario == "faltante30":
        falta_dia = np.repeat(sorteo < 0.30, largos)[:n_dias]
    else:                                               # ralo2008: 2008-2009 al 10 % de cobertura
        dia_2010 = int((np.datetime64("2010-01-01", "D") - EJE_T0.astype("datetime64[D]")).astype(np.int64))
        falta_dia = np.repeat(sorteo < 0.90, largos)[:n_dias] & (np.arange(n_dias) < dia_2010)
    return np.repeat(falta_dia, 24)[:N_EJE]


# ---------------------------------------------------------------------------
# Tabla de la estación: rejilla del portal y valores por etiqueta
# ---------------------------------------------------------------------------
@dataclass
class _Tabla:
    codigo: str
    L: np.ndarray                     # datetime64[h], rejilla del portal ordenada y sin repetidas
    mes: np.ndarray                   # datetime64[M] de L
    u: dict[str, np.ndarray]          # familia (T, P, M) → índice del eje del u de esa etiqueta, o −1
    fila: np.ndarray                  # bool: la fila trae alguna de las VARIABLES del descargador
    num: dict[str, np.ndarray]        # dd, ff, ts, td, tmin, tmax, hr, qfe, qff, rr (NaN = casilla vacía)
    rr_sp: np.ndarray                 # bool: RR06 «s/p»
    observador: np.ndarray            # bool: dígitos en N, Nh, CL, CM y CH
    digitos: np.ndarray               # int8 (5, n): N, Nh, CL, CM, CH
    u_isd: np.ndarray                 # índices del eje con Ts observada y etiqueta en el rango (ISD)


def _rango_etiquetas(caso: CasoSintetico) -> tuple[np.datetime64, np.datetime64]:
    a0, a1 = caso.anios
    fin = min(datetime(a1, 12, 31, 23), FIN_DATOS)
    return np.datetime64(datetime(a0, 1, 1), "h"), np.datetime64(fin, "h")


def _tomar(valores: np.ndarray, pos: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    salida = np.full(len(pos), np.nan)
    ok = pos >= 0
    ok[ok] = mascara[pos[ok]]
    salida[ok] = valores[pos[ok]]
    return salida


def _construir_tabla(caso: CasoSintetico, s: Mapping[str, np.ndarray]) -> _Tabla:
    L0, L1 = _rango_etiquetas(caso)
    i0 = int(_indice_eje(np.array([L0]))[0]) - 15
    i1 = int(_indice_eje(np.array([L1]))[0]) + 16
    if i0 < 0 or i1 > N_EJE:
        raise ValueError("rango de etiquetas fuera del eje del generador")
    k = np.arange(i0, i1, dtype=np.int64)
    n = len(k)
    hora = k % 24                                                 # EJE_T0 es 00 h UTC
    falta = _faltantes_eje(caso)[k]
    territorio = territorio_sintetico(caso.lat, caso.lon, caso.cod_comuna)
    relojes = _relojes_por_familia(caso)
    tipo = caso.tipo

    # Horario de observación en u, por tipo.
    if tipo in ("c", "d"):
        civil = _etiquetas_eje(f"C({_ZONA_CIVIL[territorio]})")[k].astype(np.int64) % 24
        desde, hasta = VENTANA_AERODROMO
        corrido = (_eje(k) >= CAMBIO_ADMINISTRATIVO).astype(np.int64) if tipo == "d" else 0
        observa = (civil >= desde + corrido) & (civil <= hasta + corrido)
    elif tipo == "f":
        observa = hora % 6 == 0
    else:
        observa = np.ones(n, dtype=bool)
    presente = observa & ~falta
    presente_p = presente if tipo != "e" else np.zeros(n, dtype=bool)

    # Etiquetas por familia: sin la inexistente y, de la repetida, sólo el primer u.
    por_familia = {}
    for familia, reloj in relojes.items():
        etiquetas = _etiquetas_de_reloj(reloj, k)
        dentro = np.flatnonzero((etiquetas >= L0) & (etiquetas <= L1))
        unicas, primero = np.unique(etiquetas[dentro], return_index=True)
        por_familia[familia] = (unicas, dentro[primero])
    L = np.unique(np.concatenate([v[0] for v in por_familia.values()]))
    pos = {}
    for familia, (unicas, locales) in por_familia.items():
        j = np.minimum(np.searchsorted(unicas, L), len(unicas) - 1)
        pos[familia] = np.where(unicas[j] == L, locales[j], -1)

    # Valores T y P.
    ts_loc = s["ts"][k]
    num = {"ts": _tomar(ts_loc, pos["T"], presente)}
    for v in ("td", "hr"):
        num[v] = _tomar(s[v][k], pos["T"], presente_p)
    num["hr"] = np.clip(np.round(num["hr"]), 1, 100)
    for v in ("qfe", "qff"):
        num[v] = _tomar(s[v][k], pos["P"], presente_p)
    rapidez = np.hypot(s["viento_u"][k], s["viento_v"][k]) * _KT_POR_MS
    ff = np.round(rapidez)
    dd = np.round(np.degrees(np.arctan2(-s["viento_u"][k], -s["viento_v"][k])) % 360.0)
    dd = np.where(dd == 0, 360.0, dd)
    dd = np.where(ff == 0, 0.0, dd)
    num["ff"] = _tomar(ff, pos["P"], presente_p)
    num["dd"] = _tomar(dd, pos["P"], presente_p)

    # Marcas (familia M).
    pm = pos["M"]
    sin_marcas = bool(caso.perturbaciones.get("sin_marcas", 0)) or tipo in ("e", "g")
    vacio = np.zeros(n, dtype=bool)
    if sin_marcas:
        rr_l = tx_l = tn_l = obs_l = vacio
        en_etiqueta = None
    elif tipo == "a":                                           # marcas en la rejilla de su propio reloj
        rr_l = tx_l = tn_l = obs_l = vacio
        hora_L = L.astype(np.int64) % 24
        ok = pm >= 0
        presente_m = np.zeros(len(L), dtype=bool)
        presente_m[ok] = presente[pm[ok]]
        en_etiqueta = (presente_m & (hora_L % 6 == 0), presente_m & (hora_L == 0), presente_m & (hora_L == 12))
    else:                                                       # b, c, d, f: calendario sinóptico en UTC
        pascua = _calendario_pascua(relojes["M"], k)
        rr_l = np.where(pascua, np.isin(hora, HORAS_RR_PASCUA), np.isin(hora, HORAS_RR)) & ~falta
        tx_l = (hora == np.where(pascua, HORA_TX_PASCUA, HORA_TX)) & ~falta
        tn_l = (hora == np.where(pascua, HORA_TN_PASCUA, HORA_TN)) & ~falta
        if tipo == "b":
            obs_l = (hora % 3 == 0) & ~falta
        elif tipo == "f":
            obs_l = presente
        else:
            obs_l = (hora % 3 == 0) & presente
        en_etiqueta = None
    serie_ts = pd.Series(ts_loc)
    tmax_l = serie_ts.rolling(12, min_periods=1).max().to_numpy()
    tmin_l = serie_ts.rolling(12, min_periods=1).min().to_numpy()
    if en_etiqueta is None:
        rr = ~np.isnan(_tomar(np.ones(n), pm, rr_l))
        tx = ~np.isnan(_tomar(np.ones(n), pm, tx_l))
        tn = ~np.isnan(_tomar(np.ones(n), pm, tn_l))
        observador = ~np.isnan(_tomar(np.ones(n), pm, obs_l))
    else:
        rr, tx, tn = en_etiqueta
        observador = np.zeros(len(L), dtype=bool)
    todas = np.ones(n, dtype=bool)
    num["tmax"] = np.where(tx, _tomar(tmax_l, pm, todas), np.nan)
    num["tmin"] = np.where(tn, _tomar(tmin_l, pm, todas), np.nan)
    num["rr"] = np.where(rr, _tomar(s["rr_mm"][k], pm, todas), np.nan)
    rr_sp = rr & (_tomar(s["sorteo_rr"][k], pm, todas) < _PROB_SIN_PRECIPITACION)
    digitos = np.zeros((5, len(L)), dtype=np.int8)
    okm = pm >= 0
    digitos[:, okm] = s["digitos"][:, k[pm[okm]]]

    fila = np.zeros(len(L), dtype=bool)
    for v in ("ts", "td", "hr", "qfe", "qff", "dd", "ff"):
        fila |= ~np.isnan(num[v])
    fila |= rr
    # El generador no fabrica centinelas ni valores fuera de rango (R-43: el control propio no se ejerce en D).
    for v, (lo, hi) in (("ts", _TS_IMPOSIBLE), ("qfe", _QFE_IMPOSIBLE)):
        x = num[v][~np.isnan(num[v])]
        if x.size and (x.min() <= lo or x.max() >= hi):
            raise RuntimeError(f"el generador produjo {v} fuera de rango en {caso.codigo}")

    etiquetas_t = _etiquetas_de_reloj(relojes["T"], k)
    isd = k[presente & (etiquetas_t >= L0) & (etiquetas_t <= L1)]
    u_global = {f: np.where(p >= 0, k[np.maximum(p, 0)], -1) for f, p in pos.items()}
    return _Tabla(codigo=caso.codigo, L=L, mes=L.astype("datetime64[M]"), u=u_global, fila=fila, num=num,
                  rr_sp=rr_sp, observador=observador, digitos=digitos, u_isd=isd)


_CACHE_TABLAS = _Cache(2)


def _tabla(caso: CasoSintetico) -> _Tabla:
    return _CACHE_TABLAS.obtener(_clave(caso), lambda: _construir_tabla(caso, _senales_eje(caso)))


def vaciar_caches() -> None:
    """Libera la memoria de las cachés del generador (las etiquetas por zona se conservan)."""
    for cache in (_CACHE_TABLAS, _CACHE_SENALES, _CACHE_REFERENCIA, _CACHE_REGION):
        cache.vaciar()


# ---------------------------------------------------------------------------
# Textos crudos (los 23 del portal)
# ---------------------------------------------------------------------------
def _decimal1(x: np.ndarray) -> list[str]:
    salida = []
    for v in x.tolist():
        if v != v:
            salida.append("")
        else:
            t = f"{v:.1f}"
            salida.append("0.0" if t == "-0.0" else t)
    return salida


def _entero(x: np.ndarray, ancho: int = 0) -> list[str]:
    formato = f"{{:0{ancho}d}}" if ancho else "{:d}"
    return ["" if v != v else formato.format(int(v)) for v in x.tolist()]


def _columnas_texto(t: _Tabla, j: np.ndarray) -> dict[str, list[str]]:
    indice = pd.DatetimeIndex(t.L[j].astype("datetime64[ns]"))
    vacio = [""] * len(j)
    obs = t.observador[j].tolist()
    digitos = [[str(d) if o else "" for d, o in zip(fila.tolist(), obs)] for fila in t.digitos[:, j]]
    rr = []
    for v, sp in zip(t.num["rr"][j].tolist(), t.rr_sp[j].tolist()):
        rr.append("" if v != v else "s/p" if sp else f"{v:.1f}")
    return {
        "day": [f"{d:02d}" for d in indice.day], "hour": [f"{h:02d}:00" for h in indice.hour],
        "wind_direction_instant": _entero(t.num["dd"][j], 3), "wind_speed_instant": _entero(t.num["ff"][j], 3),
        "Ts": _decimal1(t.num["ts"][j]), "Td": _decimal1(t.num["td"][j]), "TMin": _decimal1(t.num["tmin"][j]),
        "TMax": _decimal1(t.num["tmax"][j]), "relative_humidity": _entero(t.num["hr"][j]), "WW": vacio,
        "VV": vacio, "visibility_reigning": vacio, "visibility_minimum": vacio,
        "QFE": _decimal1(t.num["qfe"][j]), "QFF": _decimal1(t.num["qff"][j]), "QNH": vacio,
        "N": digitos[0], "Nh": digitos[1], "CL": digitos[2], "CM": digitos[3], "CH": digitos[4], "Hs1": vacio,
        "RR06": rr,
    }


def _filas_del_mes(t: _Tabla, anio: int, mes: int) -> np.ndarray:
    return np.flatnonzero(t.mes == np.datetime64(f"{anio:04d}-{mes:02d}", "M"))


def textos_crudos(caso: CasoSintetico, anio: int, mes: int) -> list[list[str]]:
    """Filas de 23 textos como el portal (día, hora, …, RR06), etiquetadas con el reloj verdadero y con
    las marcas RR/TX/TN y de observador según el tipo; sin la etiqueta inexistente y con una sola
    repetida en relojes civiles.

    Es la rejilla completa del mes en el reloj del portal: las etiquetas sin dato van con día y hora y el
    resto vacío (son las ``source_empty_slots`` del descargador).
    """
    t = _tabla(caso)
    cols = _columnas_texto(t, _filas_del_mes(t, anio, mes))
    return [list(fila) for fila in zip(*(cols[c] for c in COLUMNAS_CRUDAS))]


def _huellas(cols: Mapping[str, list[str]]) -> list[str]:
    """sha256 de ``json.dumps(textos, ensure_ascii=False, separators=(",", ":"))`` (R-13). Los textos del
    generador no llevan comillas, barras inversas ni caracteres de control, así que la unión es idéntica."""
    return [hashlib.sha256(('["' + '","'.join(textos) + '"]').encode("utf-8")).hexdigest()
            for textos in zip(*(cols[c] for c in COLUMNAS_HUELLA))]


def html_informe(caso: CasoSintetico, anio: int, mes: int, descargador: ModuleType) -> str:
    """Hoja mensual sintética con GROUP_COLUMNS y LEAF_COLUMNS del descargador (como tests.report).

    La tabla va dos veces, porque el portal muestra cada fila dos veces (§1.1).
    """
    if tuple(descargador.RAW_COLUMNS) != COLUMNAS_CRUDAS:
        raise ValueError("RAW_COLUMNS del descargador distintas de las del generador")
    filas = textos_crudos(caso, anio, mes)
    e = html.escape
    cabecera = "<tr>" + "".join(f"<th>{e(x)}</th>" for x in descargador.GROUP_COLUMNS) + "</tr>"
    cabecera += "<tr>" + "".join(f"<td>{e(x)}</td>" for x in descargador.LEAF_COLUMNS) + "</tr>"
    cuerpo = "".join("<tr>" + "".join(f"<td>{e(x)}</td>" for x in fila) + "</tr>" for fila in filas)
    tabla = "<table>" + cabecera + cuerpo + "</table>"
    titulo = (f'<div id="cabezera">Hoja Mensual de Datos Estación ({caso.codigo}) '
              f"{descargador.MONTH_NAMES[mes - 1]} de {anio}</div>")
    return titulo + tabla + tabla


# ---------------------------------------------------------------------------
# Catálogo, inventario, cliente y guarda falsos; run_download
# ---------------------------------------------------------------------------
def _texto_numero(x: float) -> str:
    t = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


def _metadatos(caso: CasoSintetico) -> dict[str, str]:
    return {"Código Nacional": caso.codigo, "Nombre": f"Estación sintética {caso.codigo}",
            "Latitud": _texto_numero(caso.lat), "Longitud": _texto_numero(caso.lon),
            "Altitud (Mts)": _texto_numero(caso.alt_m), "Fecha Creación": "01-01-2000",
            "Tipo": _TIPO_NOMBRE[caso.tipo], "Región": _REGION_NOMBRE.get(int(caso.cod_comuna) // 1000, "")}


def _por_codigo(casos: Sequence[CasoSintetico]) -> dict[str, CasoSintetico]:
    salida: dict[str, CasoSintetico] = {}
    for caso in casos:
        _validar_caso(caso)
        if caso.codigo in salida:
            raise ValueError(f"código repetido entre los casos: {caso.codigo}")
        salida[caso.codigo] = caso
    return salida


def catalogo_dmc_sintetico(casos: Sequence[CasoSintetico]) -> list[dict]:
    """Las estaciones como las deja ``parse_catalog`` en catalogo_nacional.json.gz (camino propio)."""
    return [{"code": c.codigo, "source_metadata": _metadatos(c), **METADATOS_CAUTELA}
            for _, c in sorted(_por_codigo(casos).items())]


def html_catalogo(casos: Sequence[CasoSintetico]) -> str:
    e = html.escape
    filas = "".join("<tr>" + "".join(f"<td>{e(_metadatos(c)[h])}</td>" for h in CABECERAS_CATALOGO) + "</tr>"
                    for _, c in sorted(_por_codigo(casos).items()))
    return "<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in CABECERAS_CATALOGO) + "</tr>" + filas + "</table>"


def inventario_sintetico(caso: CasoSintetico) -> list[dict]:
    """Elementos de la ficha: Ts (26) en el tipo e; además viento (28), QFE (64), QFF (65) y HR (66)."""
    elementos = (26,) if caso.tipo == "e" else (26, 28, 64, 65, 66)
    a0, a1 = caso.anios
    return [{"element_id": e, "first_year": a0, "last_year": a1, "source_count": 8760 * (a1 - a0 + 1)}
            for e in elementos]


class ClienteFalso:
    """Cliente del descargador sin red: catalog(), inventory(code), report(code, year, month, start, end)."""

    def __init__(self, casos: Sequence[CasoSintetico], descargador: ModuleType):
        self.casos = _por_codigo(casos)
        self.descargador = descargador
        self.llamadas = {"catalog": 0, "inventory": 0, "report": 0}

    def catalog(self):
        self.llamadas["catalog"] += 1
        return self.descargador.parse_catalog(html_catalogo(list(self.casos.values())))

    def inventory(self, code):
        self.llamadas["inventory"] += 1
        return inventario_sintetico(self.casos[code])

    def report(self, code, year, month, start=None, end=None):
        self.llamadas["report"] += 1
        texto = html_informe(self.casos[code], year, month, self.descargador)
        url = f"{URL_FALSA}/hojaMensualDatos/{code}/{year}/{month}"
        return self.descargador.parse_report(texto, code, year, month, start, end), url


def _bajo(ruta: Path, raiz: Path) -> bool:
    return ruta == raiz or raiz in ruta.parents


def _lexica(ruta: Path | str) -> Path:
    return Path(os.path.normpath(os.path.abspath(os.fspath(ruta))))


def _repositorios() -> tuple[Path, Path]:
    ap = Path(__file__).resolve().parents[2]
    return ap, ap.parent / "Air-Pollution-Health-Chile"


def _en_volumes(ruta: Path) -> bool:
    """/Volumes o debajo, sin distinguir mayúsculas (APFS), como entorno.prohibido_volumes."""
    return len(ruta.parts) >= 2 and ruta.parts[0] == "/" and ruta.parts[1].casefold() == "volumes"


def _exigir_fuera(r: Path) -> None:
    if _en_volumes(r):
        raise ValueError("los datos sintéticos nunca se escriben bajo /Volumes")
    for repo in _repositorios():
        if _bajo(r, repo) or _bajo(r, Path(os.path.realpath(repo))):
            raise ValueError("los datos sintéticos nunca se escriben en los repositorios")


def _exigir_destino_temporal(ruta: Path) -> Path:
    """Nunca bajo /Volumes ni dentro de los repositorios (comparación léxica y resuelta). La léxica va primero
    y no toca el disco: una ruta bajo /Volumes se rechaza sin consultarla (§8, prueba 27). Sólo si la léxica
    pasa se resuelve, para atrapar un enlace que lleve a /Volumes o a un repositorio."""
    lexica = _lexica(ruta)
    _exigir_fuera(lexica)
    _exigir_fuera(Path(os.path.realpath(lexica)))
    return lexica


class GuardaFalsa:
    """Guarda mínima con ``defer_heavy_checks = True`` (check, ensure_directory, write_atomic_bytes).

    Con ``raiz`` rechaza toda escritura fuera de ella; nunca escribe bajo /Volumes.
    """
    defer_heavy_checks = True

    def __init__(self, raiz: Path | None = None):
        self.raiz = None if raiz is None else Path(os.path.realpath(_exigir_destino_temporal(raiz)))
        self.checks = 0
        self.escrituras: list[Path] = []

    def check(self, *args, **kwargs):
        self.checks += 1

    def _permitida(self, ruta: Path) -> Path:
        ruta = _exigir_destino_temporal(ruta)
        if self.raiz is not None and not _bajo(Path(os.path.realpath(ruta)), self.raiz):
            raise ValueError("escritura fuera de la carpeta temporal de la guarda")
        return ruta

    def ensure_directory(self, path):
        self.check()
        self._permitida(Path(path)).mkdir(parents=True, exist_ok=True)

    def write_atomic_bytes(self, path, body):
        self.check()
        ruta = self._permitida(Path(path))
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(f".{ruta.name}.tmp-sintetico")
        temporal.write_bytes(body)
        os.replace(temporal, ruta)
        self.escrituras.append(ruta)


def fabricar_descarga(casos: Sequence[CasoSintetico], raiz_temporal: Path, descargador: ModuleType,
                      desde: str, hasta: str, *, crear_candado: bool = True) -> Path:
    """Corre run_download en ``raiz_temporal`` (nunca bajo /Volumes) y devuelve la raíz DMC sintética,
    con manifiestos verified_operational, artefactos, catalogo_nacional.json.gz y progreso.json.

    La raíz DMC es ``raiz_temporal/DMC`` (la de ``entorno.rutas_sinteticas``). ``crear_candado`` deja
    ``.meteo_download.lock`` vacío, como lo deja ``meteo_lock`` al terminar (§3.1, C2).
    """
    raiz = Path(os.path.realpath(_exigir_destino_temporal(Path(raiz_temporal))))   # como run_download (resolve)
    dmc = raiz / "DMC"
    dmc.mkdir(parents=True, exist_ok=True)
    guarda = GuardaFalsa(dmc)
    resumen = descargador.run_download(dmc, desde, hasta, guarda, client=ClienteFalso(casos, descargador),
                                       http_workers=1)
    if resumen.get("phase") != "finished" or resumen.get("status") not in ("finished", "finished_with_pending"):
        raise RuntimeError(f"run_download no terminó: {resumen.get('status')!r}")
    if crear_candado:
        (dmc / ".meteo_download.lock").touch()
    return dmc


# ---------------------------------------------------------------------------
# Batería D: extractos en memoria con el esquema de extraer_dmc (R-43)
# ---------------------------------------------------------------------------
def _numeros(textos: list[str]) -> np.ndarray:
    return np.array([float(x) if x else np.nan for x in textos], dtype=np.float64)


def _paso_nativo(etiquetas: np.ndarray) -> int | None:
    """Diferencia más frecuente (h) entre etiquetas consecutivas con valor; empate → la menor (§3.2)."""
    if len(etiquetas) < 2:
        return None
    d = np.diff(etiquetas).astype(np.int64)
    valores, cuentas = np.unique(d, return_counts=True)
    paso = int(valores[cuentas == cuentas.max()].min())
    return paso if paso <= np.iinfo(np.int16).max else None


def _textos_coordenadas(caso: CasoSintetico) -> tuple[str, str, str]:
    m = _metadatos(caso)
    return m["Latitud"], m["Longitud"], m["Altitud (Mts)"]


def _senales_dadas_en_eje(caso: CasoSintetico, senales_dadas: pd.DataFrame) -> dict[str, np.ndarray]:
    base = dict(_senales_eje(caso))
    k = _indice_eje(_instantes(pd.DatetimeIndex(senales_dadas.index)))
    for c in ("ts", "td", "hr", "qfe", "qff", "viento_u", "viento_v"):
        arreglo = np.full(N_EJE, np.nan)
        if c in senales_dadas.columns:
            arreglo[k] = senales_dadas[c].to_numpy(dtype=np.float64)
        base[c] = arreglo
    return base


def entrada_en_memoria(caso: CasoSintetico, *, senales_dadas: pd.DataFrame | None = None
                       ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(extracto ESQUEMA_EXTRACTO_HORA, meses ESQUEMA_MES) del caso, sin pasar por el descargador.

    Mismas filas que dejaría el descargador (las que traen alguna de sus VARIABLES), mismos textos y la
    huella de §3.2. ``id_artefacto`` numera los meses con filas de la estación (0, 1, …). Un mes sin
    filas queda en los meses con ``entra = False`` (su manifiesto no tendría artefacto). Los sha256 de
    manifiesto, artefacto y página son identificadores propios (no hay archivos). ``senales_dadas``
    (índice u horario UTC; columnas ts, qfe, td, hr, qff, viento_u, viento_v) reemplaza las señales del
    modelo, por ejemplo series de ERA5-Land real con ruido (C3b).
    """
    if senales_dadas is None:
        t = _tabla(caso)
    else:
        t = _construir_tabla(caso, _senales_dadas_en_eje(caso, senales_dadas))
    lat_txt, lon_txt, alt_txt = _textos_coordenadas(caso)
    partes: list[dict[str, np.ndarray]] = []
    meses: list[dict] = []
    id_artefacto = 0
    for mes64 in np.unique(t.mes):
        anio, mes = int(str(mes64)[:4]), int(str(mes64)[5:7])
        j = np.flatnonzero(t.mes == mes64)
        jd = j[t.fila[j]]
        dias = (mes64 + 1).astype("datetime64[D]") - mes64.astype("datetime64[D]")
        dias = int(dias.astype(np.int64))
        manifiesto = f"DMC/estaciones/{caso.codigo}/{anio:04d}-{mes:02d}.manifest.json"
        fila_mes = {"codigo": caso.codigo, "anio": anio, "mes": mes, "manifiesto": manifiesto,
                    "script_sha256": SCRIPT_SHA256_VIGENTE, "expected_hour_slots": 24 * dias,
                    "requested_start": f"{anio:04d}-{mes:02d}-01", "requested_end": f"{anio:04d}-{mes:02d}-{dias:02d}",
                    "campos_faltantes": [], "lat_txt": lat_txt, "lon_txt": lon_txt, "alt_txt": alt_txt,
                    "source_empty_slots": len(j) - len(jd)}
        if not len(jd):
            fila_mes.update(artefacto_sha256=None, id_artefacto=None, entra=False,
                            motivo_exclusion=MOTIVO_MES_SIN_FILAS, row_count=0, n_available_hours=0,
                            duplicate_display_rows_removed=0, p_ts=None, p_qfe=None,
                            source_sha256=_sha256_texto(f"sintetico|pagina|{manifiesto}|vacia|{len(j)}"))
        else:
            cols = _columnas_texto(t, jd)
            huellas = _huellas(cols)
            L = t.L[jd]
            v = {c: _numeros(cols[nombre]) for c, nombre in (
                ("ts", "Ts"), ("td", "Td"), ("hr", "relative_humidity"), ("ff_kt", "wind_speed_instant"),
                ("dd_grados", "wind_direction_instant"), ("qfe", "QFE"), ("qff", "QFF"))}
            medida = np.zeros(len(jd), dtype=bool)
            for c, x in v.items():
                medida |= np.isfinite(x) & (x != _CENTINELAS.get(c, np.nan))
            observador = np.array([any(len(x) == 1 and x.isdigit() for x in textos)
                                   for textos in zip(cols["CL"], cols["CM"], cols["CH"])], dtype=bool)
            partes.append({
                "L": L, "anio": np.full(len(jd), anio), "mes": np.full(len(jd), mes),
                "id_artefacto": np.full(len(jd), id_artefacto), "medida": medida,
                "ts": v["ts"], "motivo_ts": np.where(np.isfinite(v["ts"]), 0, 1),
                "qfe": v["qfe"], "motivo_qfe": np.where(np.isfinite(v["qfe"]), 0, 1),
                "td": v["td"], "hr": v["hr"], "ff_kt": v["ff_kt"], "dd_grados": v["dd_grados"],
                "viento_valido": (np.isfinite(v["dd_grados"]) & np.isfinite(v["ff_kt"]) & (v["dd_grados"] >= 0)
                                  & (v["dd_grados"] <= 360) & (v["ff_kt"] >= 0)),
                "qff_numerica": np.isfinite(v["qff"]),
                "rr": np.array([x != "" for x in cols["RR06"]], dtype=bool),
                "tx": np.array([x != "" for x in cols["TMax"]], dtype=bool),
                "tn": np.array([x != "" for x in cols["TMin"]], dtype=bool),
                "observador": observador, "huella": np.array(huellas, dtype=object),
            })
            artefacto = _sha256_texto(f"sintetico|artefacto|{manifiesto}|" + "".join(huellas))
            fila_mes.update(artefacto_sha256=artefacto, id_artefacto=id_artefacto, entra=True,
                            motivo_exclusion=None, row_count=len(jd), n_available_hours=len(jd),
                            duplicate_display_rows_removed=len(jd),
                            p_ts=_paso_nativo(L[np.isfinite(v["ts"])]), p_qfe=_paso_nativo(L[np.isfinite(v["qfe"])]),
                            source_sha256=_sha256_texto(f"sintetico|pagina|{artefacto}|{len(j)}"))
            id_artefacto += 1
        fila_mes["manifiesto_sha256"] = _sha256_texto(json.dumps(
            {k: fila_mes[k] for k in sorted(fila_mes) if k != "campos_faltantes"}, sort_keys=True, default=str))
        meses.append(fila_mes)

    if partes:
        datos = {c: np.concatenate([p[c] for p in partes]) for c in ESQUEMA_EXTRACTO}
    else:
        datos = {c: np.array([], dtype=object if c == "huella" else "datetime64[h]" if c == "L" else float)
                 for c in ESQUEMA_EXTRACTO}
    datos["L"] = datos["L"].astype("datetime64[ns]")
    extracto = pd.DataFrame({c: pd.Series(datos[c]).astype(tipo) for c, tipo in ESQUEMA_EXTRACTO.items()})
    tabla_meses = pd.DataFrame(meses, columns=list(ESQUEMA_MESES))
    for c, tipo in ESQUEMA_MESES.items():
        tabla_meses[c] = tabla_meses[c].astype(tipo)
    return extracto, tabla_meses


def isd_sintetico(caso: CasoSintetico) -> pd.DataFrame:
    """Partes FM-12 (décimas) y FM-15 (grados enteros) en UTC, ESQUEMA_ISD.

    FM-12 a las horas UTC múltiplo de 3 con la misma Ts que informa la DMC (2 % con un error de
    transcripción de 0,1 a 0,3 °C); FM-15 cada hora con la Ts redondeada al grado (mitades hacia arriba).
    Cada parte falta con probabilidad 5 %. Sólo donde la estación observó Ts.
    """
    t = _tabla(caso)
    k = t.u_isd
    base = _numeros(_decimal1(_senales_eje(caso)["ts"][k]))
    r = _rng("isd", caso.codigo, caso.semilla)
    n = len(k)
    con12 = (k % 24 % 3 == 0) & (r.random(n) >= _PROB_FALTA_ISD)
    transcripcion = r.random(n) < _PROB_TRANSCRIPCION_ISD
    error = r.choice(np.array([-0.3, -0.2, -0.1, 0.1, 0.2, 0.3]), size=n)
    tmp12 = np.where(transcripcion, np.round(base + error, 1), base)
    con15 = r.random(n) >= _PROB_FALTA_ISD
    tmp15 = np.floor(base + 0.5)
    u = _eje(k).astype("datetime64[ns]")
    tabla = pd.DataFrame({
        "codigo": caso.codigo,
        "u": np.concatenate([u[con12], u[con15]]),
        "tipo_parte": ["FM-12"] * int(con12.sum()) + ["FM-15"] * int(con15.sum()),
        "tmp": np.concatenate([tmp12[con12], tmp15[con15]]),
    }).sort_values(["u", "tipo_parte"], kind="mergesort").reset_index(drop=True)
    return pd.DataFrame({c: tabla[c].astype(tipo) for c, tipo in ESQUEMA_ISD_PROPIO.items()})


# ---------------------------------------------------------------------------
# Verdad por etiqueta e ida y vuelta
# ---------------------------------------------------------------------------
_FAMILIA_DE_VARIABLE = {"Ts": "T", "QFE": "P", "marcas": "M"}


def _mapa(caso: CasoSintetico, variable: str) -> tuple[np.ndarray, np.ndarray]:
    t = _tabla(caso)
    ui = t.u[_FAMILIA_DE_VARIABLE[variable]]
    ok = t.fila & (ui >= 0)
    return t.L[ok], ui[ok]


def u_de_etiqueta(caso: CasoSintetico, variable: str = "Ts") -> Mapping[datetime, datetime]:
    """Etiqueta → u que la generó (para la ida y vuelta); excluye la repetida descartada.

    Sólo las etiquetas de filas que existen (con alguna VARIABLE del descargador), con el reloj de
    ``variable`` («Ts», «QFE» o «marcas»; en un caso de un solo reloj, los tres coinciden).
    """
    L, ui = _mapa(caso, variable)
    return dict(zip(_a_datetimes(L, False), _a_datetimes(_eje(ui), True)))


@functools.lru_cache(maxsize=None)
def _inversa_civil(zona: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Para C(zona): etiquetas únicas, primer instante del eje y cuántos instantes dan cada etiqueta."""
    etiquetas = _etiquetas_eje(f"C({zona})")
    unicas, primero, cuentas = np.unique(etiquetas, return_index=True, return_counts=True)
    return unicas, primero, cuentas


def _u_bajo_hipotesis(spec: str, L: np.ndarray) -> np.ndarray:
    """Índice del eje que H asigna a cada etiqueta; −1 donde H no está definida (repetida o inexistente)."""
    tipo, valor = _especificacion(spec)
    if tipo == "F":
        return _indice_eje(L - np.timedelta64(valor, "h"))
    if tipo != "C":
        raise ValueError(f"sólo F y C están en P: {spec}")
    unicas, primero, cuentas = _inversa_civil(valor)
    j = np.minimum(np.searchsorted(unicas, L), len(unicas) - 1)
    definida = (unicas[j] == L) & (cuentas[j] == 1)
    return np.where(definida, primero[j], -1)


def equivalentes_en_P(caso: CasoSintetico, anio: int, variable: str = "Ts") -> tuple[str, ...]:
    """Ids (de tipos) de las H de P que dan el mismo u que el reloj verdadero en todas las etiquetas con
    datos del año donde H está definida (las repetidas e inexistentes de C(Z) nunca reciben regla, §7.2).

    Vacío si el año no tiene datos o si el reloj verdadero no coincide con ninguna H de P ese año (por
    ejemplo F(+1), o Cv en un año en que la regla anterior difiere de la vigente).
    """
    L, ui = _mapa(caso, variable)
    m = L.astype("datetime64[Y]") == np.datetime64(f"{anio:04d}", "Y")
    L, ui = L[m], ui[m]
    if not len(L):
        return ()
    salida = []
    for spec in _P_POR_TERRITORIO[territorio_sintetico(caso.lat, caso.lon, caso.cod_comuna)]:
        uh = _u_bajo_hipotesis(spec, L)
        definida = uh >= 0
        if definida.any() and np.array_equal(uh[definida], ui[definida]):
            salida.append(_id_tipos(spec))
    return tuple(salida)


def comprobar_ida_y_vuelta(politica: Mapping, casos: Sequence[CasoSintetico], adaptador: ModuleType, *,
                           maximo_por_estacion: int = 20) -> list[str]:
    """Fallas de ``_utc(L, regla emitida) == u`` para toda etiqueta con regla (debe volver vacía).

    ``politica`` es el JSON de §7.2 (o su ruta). Para cada regla ``clock`` de una estación de ``casos``,
    cada etiqueta con datos dentro del intervalo y ``_confirmado`` verdadero se convierte con ``_utc`` del
    adaptador fijado y se compara con el u que la generó, con el reloj de Ts y con el de QFE (si difieren).
    """
    if isinstance(politica, (str, Path)):
        politica = json.loads(Path(politica).read_text(encoding="utf-8"))
    por_codigo = _por_codigo(casos)
    reglas: dict[str, list[dict]] = {}
    for entrada in politica.get("politicas_reloj", []):
        reglas.setdefault(str(entrada.get("station_code")), []).append(entrada)
    fallas: list[str] = []
    for codigo, caso in sorted(por_codigo.items()):
        propias = reglas.get(codigo, [])
        if not propias:
            continue
        variables = ("Ts",) if len(caso.relojes) == 1 else ("Ts", "QFE")
        n_fallas = 0
        for variable in variables:
            mapa = u_de_etiqueta(caso, variable)
            for entrada in propias:
                regla = entrada.get("clock")
                desde = datetime.fromisoformat(str(entrada.get("valid_from")))
                hasta = datetime.fromisoformat(str(entrada.get("valid_to")))
                for L, u in mapa.items():
                    if not (desde <= L <= hasta):
                        continue
                    try:
                        if not adaptador._confirmado(regla, L):
                            continue
                        obtenido = adaptador._utc(L, regla)
                        motivo = None if obtenido == u else f"da {obtenido.isoformat()}"
                    except Exception as exc:          # una excepción del adaptador también es falla
                        motivo = f"{type(exc).__name__}: {exc}"
                    if motivo is not None:
                        n_fallas += 1
                        if n_fallas <= maximo_por_estacion:
                            fallas.append(f"{codigo} {variable} {L.isoformat()}: esperado {u.isoformat()}, {motivo}")
        if n_fallas > maximo_por_estacion:
            fallas.append(f"{codigo}: {n_fallas - maximo_por_estacion} fallas más")
    return fallas


# ---------------------------------------------------------------------------
# Píxeles y referencia en memoria
# ---------------------------------------------------------------------------
RESOLUCION_GRADOS = 0.1
_COLUMNAS_LON_GLOBAL = 3600


def _pixel_de(lat: float, lon: float) -> tuple[int, float, float, int, int]:
    """(pixel_id, lat del centro, lon del centro, índice global de lat, de lon) de la rejilla de 0,1°."""
    i = int(math.floor(round((90.0 - lat) / RESOLUCION_GRADOS, 6) + 0.5))
    j = int(math.floor(round((lon % 360.0) / RESOLUCION_GRADOS, 6) + 0.5)) % _COLUMNAS_LON_GLOBAL
    return _pixel_por_indices(i, j)


def _pixel_por_indices(i: int, j: int) -> tuple[int, float, float, int, int]:
    j %= _COLUMNAS_LON_GLOBAL
    lat = round(90.0 - i * RESOLUCION_GRADOS, 6)
    lon = round(j * RESOLUCION_GRADOS, 6)
    if lon > 180:
        lon = round(lon - 360.0, 6)
    return i * _COLUMNAS_LON_GLOBAL + j, lat, lon, i, j


def _pixeles(casos: Sequence[CasoSintetico]) -> dict[int, dict]:
    """Celdas 3 × 3 alrededor de cada caso; la celda propia de un caso tiene prioridad sobre la vecina de otro."""
    salida: dict[int, dict] = {}
    lista = list(_por_codigo(casos).values())
    for prioridad_centro in (True, False):
        for caso in lista:
            _, _, _, i0, j0 = _pixel_de(caso.lat, caso.lon)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    centro = di == 0 and dj == 0
                    if centro != prioridad_centro:
                        continue
                    pid, lat, lon, i, j = _pixel_por_indices(i0 + di, j0 + dj)
                    costera = bool(caso.perturbaciones.get("costera", 0))
                    valido = bool(caso.con_pixel) and not (centro and costera)
                    sitio = (round(float(caso.lat), 4), round(float(caso.lon), 4))
                    previo = salida.get(pid)
                    if previo is not None:
                        if centro and (previo["cod_comuna"] != caso.cod_comuna or previo["valido"] != valido
                                       or previo["sitio"] != sitio or previo["replica"] != caso.replica):
                            raise ValueError(f"dos casos con la misma celda propia y distinto sitio o réplica: {pid}")
                        continue
                    salida[pid] = {
                        "pixel_id": pid, "latitude": lat, "longitude": lon,
                        "cell_west": round(lon - RESOLUCION_GRADOS / 2, 6), "cell_east": round(lon + RESOLUCION_GRADOS / 2, 6),
                        "cell_south": round(lat - RESOLUCION_GRADOS / 2, 6), "cell_north": round(lat + RESOLUCION_GRADOS / 2, 6),
                        "cod_comuna": int(caso.cod_comuna),
                        "territorio": territorio_sintetico(caso.lat, caso.lon, caso.cod_comuna),
                        "lat_index_global": i, "lon_index_global": j, "valido": valido,
                        "sitio": sitio, "replica": int(caso.replica),
                        "alt_m": float(caso.alt_m) - float(caso.perturbaciones.get("dz", 0.0)),
                    }
    return salida


def catalogo_pixeles_sintetico(casos: Sequence[CasoSintetico]) -> pd.DataFrame:
    """Celdas de 0,1° alrededor de cada caso con cod_comuna (0 en territorio incierto) y sin dato donde
    ``con_pixel`` es falso.

    Columnas del catálogo real (pixel_id, latitude, longitude, cell_west…cell_north, cod_comuna,
    territorio, lat_index_global, lon_index_global) más ``valido``, propia del generador: el conjunto de
    píxeles válidos es ``set(cat.pixel_id[cat.valido])``.
    """
    filas = sorted(_pixeles(casos).values(), key=lambda f: f["pixel_id"])
    columnas = ("pixel_id", "latitude", "longitude", "cell_west", "cell_east", "cell_south", "cell_north",
                "cod_comuna", "territorio", "lat_index_global", "lon_index_global", "valido")
    tabla = pd.DataFrame([{c: f[c] for c in columnas} for f in filas], columns=list(columnas))
    tipos = {"pixel_id": "int64", "cod_comuna": "int64", "lat_index_global": "int64", "lon_index_global": "int64",
             "territorio": "string", "valido": "bool"}
    return tabla.astype({c: tipos.get(c, "float64") for c in columnas})


class SerieEra5Memoria:
    """Implementación en memoria de tipos.SerieEra5 para la batería y las pruebas.

    ``por_pixel``: pixel_id → DataFrame con t2m (°C), sp (hPa), u10 y v10 (m/s), una fila por hora desde
    ``t0``. Puede ser un Mapping perezoso (``serie_era5_de_casos``). ``valores`` da NaN fuera del eje, en
    instantes que no están en punto y en píxeles sin dato.
    """

    def __init__(self, t0: np.datetime64, por_pixel: Mapping[int, pd.DataFrame], *, n_horas: int | None = None):
        self.t0 = np.datetime64(t0, "h")
        self._por_pixel = por_pixel
        self._arreglos: dict[int, dict[str, np.ndarray]] = {}
        if n_horas is None:
            n_horas = max((len(df) for df in por_pixel.values()), default=0)
        self.n_horas = int(n_horas)

    def tiene(self, pixel_id: int) -> bool:
        return int(pixel_id) in self._por_pixel

    def _de(self, pixel_id: int) -> dict[str, np.ndarray]:
        pid = int(pixel_id)
        if pid not in self._arreglos:
            df = self._por_pixel[pid]
            arreglos = {}
            for v in VARIABLES_ERA5:
                a = np.full(self.n_horas, np.nan)
                x = df[v].to_numpy(dtype=np.float64)[: self.n_horas]
                a[: len(x)] = x
                arreglos[v] = a
            self._arreglos[pid] = arreglos
        return self._arreglos[pid]

    def valores(self, pixel_id: int, variable: str, u: np.ndarray) -> np.ndarray:
        if variable not in VARIABLES_ERA5:
            raise ValueError(f"variable ERA5 desconocida: {variable!r}")
        u = np.asarray(u)
        salida = np.full(u.shape, np.nan)
        if not self.tiene(pixel_id) or u.size == 0:
            return salida
        seg = u.astype("datetime64[s]")
        valido = ~np.isnat(seg)
        d = np.zeros(u.shape, dtype=np.int64)
        d[valido] = (seg[valido] - self.t0.astype("datetime64[s]")).astype(np.int64)
        valido &= d % 3600 == 0
        k = d // 3600
        valido &= (k >= 0) & (k < self.n_horas)
        salida[valido] = self._de(pixel_id)[variable][k[valido]]
        return salida

    def media(self, pixel_id: int, variable: str) -> float:
        if variable not in VARIABLES_ERA5:
            raise ValueError(f"variable ERA5 desconocida: {variable!r}")
        if not self.tiene(pixel_id):
            return float("nan")
        return float(np.nanmean(self._de(pixel_id)[variable]))


class _PixelesPerezosos(Mapping):
    """pixel_id → DataFrame de la referencia sintética, fabricado al pedirlo."""

    def __init__(self, definiciones: Mapping[int, dict], sesgo: float):
        self._definiciones = dict(definiciones)
        self._sesgo = float(sesgo)
        self._k0 = int(_indice_eje(np.array([ERA5_T0]))[0])
        self.n_horas = int((ERA5_ULTIMA - ERA5_T0) // np.timedelta64(1, "h")) + 1

    def __getitem__(self, pixel_id):
        d = self._definiciones[int(pixel_id)]
        ref = _referencia_eje(d["pixel_id"], d["sitio"], d["replica"], d["latitude"], d["longitude"], d["alt_m"],
                              self._sesgo)
        tramo = slice(self._k0, self._k0 + self.n_horas)
        return pd.DataFrame({v: ref[v][tramo] for v in VARIABLES_ERA5})

    def __contains__(self, pixel_id) -> bool:          # sin fabricar la serie (Mapping usaría __getitem__)
        return int(pixel_id) in self._definiciones

    def __iter__(self) -> Iterator[int]:
        return iter(sorted(self._definiciones))

    def __len__(self) -> int:
        return len(self._definiciones)


def serie_era5_de_casos(casos: Sequence[CasoSintetico], *, sesgo_termico_h: float | None = None) -> SerieEra5Memoria:
    """Referencia «ERA5» en memoria para los píxeles válidos de ``casos`` (una red de la batería).

    El sesgo térmico es común a la red (§8.D): por omisión se toma de la perturbación
    «sesgo_termico_referencia» de los casos, que debe ser la misma en todos (0 si ninguno la lleva).
    """
    if sesgo_termico_h is None:
        sesgos = {float(c.perturbaciones.get("sesgo_termico_referencia", 0.0)) for c in casos}
        if len(sesgos) > 1:
            raise ValueError(f"una red con sesgos de referencia distintos: {sorted(sesgos)}")
        sesgo_termico_h = sesgos.pop() if sesgos else 0.0
    validos = {pid: d for pid, d in _pixeles(casos).items() if d["valido"]}
    perezosos = _PixelesPerezosos(validos, sesgo_termico_h)
    return SerieEra5Memoria(ERA5_T0, perezosos, n_horas=perezosos.n_horas)


# ---------------------------------------------------------------------------
# Batería D: bateria_v1.csv y sus estaciones (§8.D; lectura R-29)
# ---------------------------------------------------------------------------
COLUMNAS_BATERIA = ("caso", "bloque", "celda", "reloj_verdadero", "fuera_de_P", "tipo", "escenario", "territorio",
                    "lat", "lon", "con_pixel", "cod_comuna", "perturbacion", "valor_perturbacion", "red", "replica",
                    "semilla")
ANIOS_BATERIA = (2008, 2026)
REPLICAS_BATERIA = {"D1": 20, "D2": 10, "D3": 10}
REPLICAS_REDUCIDAS = 5                         # §8.D «Tiempo»: D2 y D3; el núcleo nunca baja
SESGOS_RED = (0.0, -2.0, 1.0, 2.5)             # sesgo térmico de la referencia de cada red (h)
_RELOJES_D1 = (                                 # (reloj, sitio, tipos), en el orden de §8.D
    ("F(0)", "santiago", "abcdef"), ("F(-3)", "santiago", "abcdef"), ("F(-4)", "santiago", "abcdef"),
    ("C(America/Santiago)", "santiago", "abcdef"),
    ("C(America/Punta_Arenas)", "punta_arenas", "abcdef"),
    ("C(America/Coyhaique)", "coyhaique", "abcdef"),
    ("C(Pacific/Easter)", "pascua", "abe"), (PASCUA_PROPIO, "pascua", "abe"),
    ("F(+1)", "santiago", "abcdef"), ("F(-1)", "santiago", "abcdef"), ("F(-2)", "santiago", "abcdef"),
    ("F(-5)", "santiago", "abcdef"),
    ("Cv(America/Santiago)", "santiago", "abcdef"),
    ("F(-4);F(0)@2018-07-01T00:00Z", "santiago", "abcdef"),
    ("Ts:C(America/Santiago)|QFE:F(0)", "santiago", "g"),
)
_RELOJES_D2, _TIPOS_D2 = ("F(0)", "F(-3)", "F(-4)", "C(America/Santiago)"), "abe"
_RELOJES_D3, _TIPOS_D3 = ("F(0)", "F(-3)", "F(-4)"), "be"
_PERTURBACIONES_D2 = (                          # (perturbación, valor, sitio)
    ("desfase_termico_estacion", -2.5, "santiago"), ("desfase_termico_estacion", -1.0, "santiago"),
    ("desfase_termico_estacion", 1.5, "santiago"),
    ("sesgo_termico_referencia", -2.0, "santiago"), ("sesgo_termico_referencia", 1.0, "santiago"),
    ("sesgo_termico_referencia", 2.5, "santiago"),
    ("s1_local_desfase_0h", 1.0, "santiago"), ("s1_local_desfase_0h", 2.0, "santiago"),
    ("s1_local_desfase_4h", 1.0, "santiago"), ("s1_local_desfase_4h", 2.0, "santiago"),
    ("fase_s2_estacion", -0.75, "santiago"), ("fase_s2_estacion", 0.75, "santiago"),
    ("semantica", 1 / 6, "santiago"), ("semantica", 0.5, "santiago"), ("semantica", -0.5, "santiago"),
    ("latitud", -18.5, "arica"), ("latitud", -39.8, "valdivia"), ("latitud", -45.6, "coyhaique"),
    ("latitud", -53.0, "punta_arenas"),
    ("juan_fernandez", float("nan"), "juan_fernandez"), ("territorio_incierto", float("nan"), "incierto"),
)


def _semilla_bateria(celda: str, replica: int) -> int:
    texto = f"20261022|bateria_v1|{celda}|{replica}"
    return int.from_bytes(hashlib.sha256(texto.encode("utf-8")).digest()[:8], "big") >> 1   # cabe en int64


def _texto_valor(v: float) -> str:
    return "" if v != v else repr(float(v))


def _celdas_bateria() -> Iterator[tuple[str, str, str, str, str, float, str]]:
    """(bloque, reloj, tipo, escenario, perturbación, valor, sitio) en orden determinista."""
    for reloj, sitio, tipos in _RELOJES_D1:
        for tipo in tipos:
            for escenario in ESCENARIOS:
                yield "D1", reloj, tipo, escenario, "ninguna", float("nan"), sitio
    for reloj in _RELOJES_D2:
        for tipo in _TIPOS_D2:
            for perturbacion, valor, sitio in _PERTURBACIONES_D2:
                yield "D2", reloj, tipo, "completo", perturbacion, valor, sitio
    for reloj in _RELOJES_D3:
        for tipo in _TIPOS_D3:
            yield "D3", reloj, tipo, "completo", "isd_sintetico", float("nan"), "santiago"


def especificacion_bateria(replicas_d2_d3: int | None = None) -> pd.DataFrame:
    """bateria_v1.csv en orden determinista (COLUMNAS_BATERIA). ``replicas_d2_d3`` = 5 tras la reducción.

    Lectura R-29 (DISENO §7.2; va al addendum de C1 como lectura de implementación, según la Enmienda 1, adoptada):
    - D1: cruce completo de relojes × tipos a-f × escenarios; el tipo g sólo con su par de relojes (Ts en
      C(Santiago), QFE en F(0)) y los tres escenarios; Pascua sólo con a, b y e; 20 réplicas.
    - D2: F(0), F(−3), F(−4) y C(Santiago) × tipos a, b y e × una perturbación a la vez, datos completos,
      10 réplicas. «semantica» lleva Δc: +1/6 (observación a −10 min), +0,5 (media de la hora que termina
      en la etiqueta) y −0,5; «s1_local_desfase_<d>h» lleva la amplitud del S1 local en hPa; «latitud»,
      la latitud del sitio.
    - D3: F(0), F(−3) y F(−4) × tipos b y e con ISD sintético (perturbación «isd_sintetico»), 10 réplicas.
    - Red = sesgo de referencia × réplica, «s<sesgo>_r<réplica>»; las de D2 sin sesgo y las de D3 van a la
      red de sesgo 0. Sitio, altitud y comuna salen de ``SITIOS``. ``fuera_de_P`` es por estación (algún
      tramo fuera de P); el juicio por año, etiqueta a etiqueta, es ``equivalentes_en_P``.
    - Código de estación «9nnnnn» por orden de fila; semilla = sha256 de «20261022|bateria_v1|celda|réplica».
    """
    if replicas_d2_d3 is not None and replicas_d2_d3 not in (REPLICAS_REDUCIDAS,):
        raise ValueError(f"sólo se admite la reducción a {REPLICAS_REDUCIDAS} réplicas (§8.D)")
    filas = []
    for bloque, reloj, tipo, escenario, perturbacion, valor, nombre_sitio in _celdas_bateria():
        sitio = SITIOS[nombre_sitio]
        celda = "|".join((bloque, reloj, tipo, escenario, perturbacion, _texto_valor(valor)))
        territorio = territorio_sintetico(sitio.lat, sitio.lon, sitio.cod_comuna)
        fuera = fuera_de_P(relojes_desde_texto(reloj), territorio)
        n = REPLICAS_BATERIA[bloque] if bloque == "D1" or replicas_d2_d3 is None else replicas_d2_d3
        sesgo = valor if perturbacion == "sesgo_termico_referencia" else 0.0
        for replica in range(1, n + 1):
            filas.append({"caso": f"9{len(filas):05d}", "bloque": bloque, "celda": celda, "reloj_verdadero": reloj,
                          "fuera_de_P": fuera, "tipo": tipo, "escenario": escenario, "territorio": territorio,
                          "lat": sitio.lat, "lon": sitio.lon, "con_pixel": sitio.con_pixel,
                          "cod_comuna": sitio.cod_comuna, "perturbacion": perturbacion, "valor_perturbacion": valor,
                          "red": f"s{sesgo:+.1f}_r{replica:02d}", "replica": replica,
                          "semilla": _semilla_bateria(celda, replica)})
    if len(filas) > 100000:
        raise RuntimeError("la batería no cabe en los códigos de seis dígitos")
    tabla = pd.DataFrame(filas, columns=list(COLUMNAS_BATERIA))
    return tabla.astype({"fuera_de_P": "bool", "con_pixel": "bool", "cod_comuna": "int64", "replica": "int64",
                         "semilla": "int64", "lat": "float64", "lon": "float64", "valor_perturbacion": "float64"})


def _valor_canonico(perturbacion: str, valor: float) -> float:
    """El valor de la especificación más cercano (a 1e-9): un CSV releído con el analizador rápido de pandas
    puede perder el último dígito de 1/6."""
    for nombre, canonico, _ in _PERTURBACIONES_D2:
        if nombre == perturbacion and abs(canonico - valor) < 1e-9:
            return canonico
    return valor


def _perturbaciones_de(perturbacion: str, valor: float) -> dict[str, float]:
    valor = _valor_canonico(perturbacion, valor)
    if perturbacion in ("ninguna", "isd_sintetico", "latitud", "juan_fernandez", "territorio_incierto"):
        return {}
    if perturbacion in ("desfase_termico_estacion", "sesgo_termico_referencia", "fase_s2_estacion", "semantica"):
        return {perturbacion: float(valor)}
    m = re.fullmatch(r"s1_local_desfase_(\d+)h", perturbacion)
    if m:
        return {"s1_local_amplitud": float(valor), "s1_local_desfase": float(m.group(1))}
    raise ValueError(f"perturbación desconocida en la batería: {perturbacion!r}")


def caso_de_fila(fila: Mapping) -> CasoSintetico:
    """La estación sintética de una fila de bateria_v1.csv (también leída del CSV, con textos)."""
    lat, lon = float(fila["lat"]), float(fila["lon"])
    sitios = [s for s in SITIOS.values() if s.lat == lat and s.lon == lon]
    if len(sitios) != 1:
        raise ValueError(f"la fila no corresponde a un sitio de la batería: {lat}, {lon}")
    sitio = sitios[0]
    con_pixel = fila["con_pixel"]
    con_pixel = con_pixel if isinstance(con_pixel, (bool, np.bool_)) else str(con_pixel) == "True"
    if bool(con_pixel) != sitio.con_pixel or int(fila["cod_comuna"]) != sitio.cod_comuna:
        raise ValueError("píxel o comuna de la fila distintos de los del sitio")
    valor = fila["valor_perturbacion"]
    valor = float("nan") if valor is None or (isinstance(valor, str) and not valor) or pd.isna(valor) else float(valor)
    caso = CasoSintetico(codigo=str(fila["caso"]), relojes=relojes_desde_texto(str(fila["reloj_verdadero"])),
                         tipo=str(fila["tipo"]), escenario=str(fila["escenario"]), lat=sitio.lat, lon=sitio.lon,
                         alt_m=sitio.alt_m, con_pixel=sitio.con_pixel, cod_comuna=sitio.cod_comuna,
                         perturbaciones=_perturbaciones_de(str(fila["perturbacion"]), valor),
                         replica=int(fila["replica"]), semilla=int(fila["semilla"]), anios=ANIOS_BATERIA)
    _validar_caso(caso)
    return caso
