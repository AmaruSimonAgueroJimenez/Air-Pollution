"""Líneas de la familia «registro»: E1a, E1b, E1c y E2 (§4.1, §4.2). Ninguna es cuantitativa.

Entradas: el extracto horario ANOTADO (ESQUEMA_EXTRACTO_HORA + ESQUEMA_ANOTACION) o los meses
(ESQUEMA_MES), y un ContextoEstacion. Salida: tipos.ResultadoLinea con estados por evento, mes,
parte, año-régimen y año (ESQUEMA_ESTADOS), métricas de E2 (ESQUEMA_METRICAS_E2) y eventos
(ESQUEMA_EVENTOS). Ningún umbral está escrito aquí: salen de ``ctx.umbrales`` (Anexo B) o de
``constantes`` (cuerpo del texto).

Lecturas fijadas del diseño (DISENO_IMPLEMENTACION.md, §7):
- R-10. Para un evento (un cambio de la zona Z en su etiqueta especial), «C(Z)» = toda H de P bajo la
  cual esa etiqueta es especial (en un adelanto, inexistente; en el atraso de E1b, repetida) y «las
  fijas» = toda H bajo la cual es válida. Así C(Coyhaique) cuenta como fija en 2025 y cae junto a
  C(Santiago) antes de 2024. Varios eventos o zonas de un año (o de un mes, en E1c) se combinan con
  estados.combinar: incompatible > compatible > dudosa > sin información.
- R-18. ``E1A_P`` (ajustable) rige «p ≥ 0,8»; ``E1A_DIA_HABITUAL`` (fijo) rige la etiqueta habitual y el
  80 % del día; «ausentes ≥ 80 % de los evaluables» es la constante del cuerpo E1A_PATRON_AUSENTES_PCT.
- R-19. E1b: el día operativo empieza en la etiqueta que sigue al fin del bloque nocturno y las horas
  se desenrollan desde ahí (Copiapó, 11-00 h, da 11 … 24).
- R-44. El vecino con Ts es el más cercano en tiempo; en un empate, el anterior.
- R-11, lectura A. En E2, TX y TN se exigen sólo si ambas tienen ≥ E2_TXTN_MIN marcas y κ3 ≥ E2_TXTN_KAPPA.
- R-24 y R-08. E2 no usa las etiquetas especiales de Zs ni las astillas (régimen nulo).

Lecturas propias de este módulo (para el addendum de C1):
1. E1a. Un evento o placebo es «evaluable» si es presente o ausente. La tasa de placebos es
   ausentes / placebos evaluables; sin placebos evaluables no hay patrón. Un p14 o un pdom sin días con
   filas deja p indefinida (sin evidencia). Un día sin etiquetas habituales fuera de h0 no cumple el
   80 %. Si h0 trae Ts y ninguna otra etiqueta tiene Ts, no es presente. Un h0 con huella nula no es
   presente.
2. E1a. «Cualquier cambio» de los placebos de semana = todo cambio del Anexo A de las zonas de Zs, a
   ≥ 3 días de calendario de su fecha D. Un placebo de semana que cae en una fecha del Anexo A2 se cuenta
   una sola vez, como placebo del A2 (2012-08-19, 2016-09-04, 2019-08-11 y 2022-09-04 están a 7k días
   de un adelanto real). Del Anexo A2 entran sólo las fechas de adelanto.
3. E1b. D del cambio real = fecha de su etiqueta especial (``Cambio.fecha_D``); D de un placebo del A2 =
   el domingo; los placebos a ±42 y ±63 días se cuentan desde la D real y deben quedar a más de 21 días
   de calendario de todo cambio de Zs. Un placebo se evalúa igual que un cambio (ventanas con ≥ 10 días y
   Δs = Δe). Tasa = placebos con |Δ| ≥ 1 / placebos evaluados; sin placebos evaluados, no hay patrón. Un
   placebo usa el bloque nocturno del año de su cambio de origen, que debe ser diurno.
4. E1b. Bloque nocturno = la racha circular más larga con q_h ≤ E1B_Q_NOCHE (empate: la que empieza
   antes). s_d y e_d no miran las etiquetas medidas dentro del bloque nocturno («la primera después del
   bloque, la última antes de él»); el día cuenta si tiene ≥ E1B_FILAS_DIA filas medidas en total.
   q_h usa como denominador las fechas del año con alguna fila.
5. E1c. Sólo los meses que entran (``entra``), uno por mes. «Una casilla menos» = casillas =
   expected_hour_slots − 1. Sin expected_hour_slots el mes también queda sin información. «En ningún
   otro mes» incluye los meses de atraso y los del Anexo A2. El mes de un cambio es el de su etiqueta
   especial.
6. Fusiones. Si los miembros de una clase del año (``ctx.clases``) reciben estados distintos en un evento
   o mes de E1, ese evento o mes queda sin información para toda la clase (motivo «fusion»). Sólo pasa en
   un año con datos de un solo régimen en que decide una etiqueta especial; así estados.estado_de_clase
   no lanza ErrorFusion.
7. E2. El año es compatible si no es incompatible, tiene ≥ 2 partes informativas, tiene ≥ 1 año-régimen
   informativo y todos sus años-régimen informativos son compatibles. Si no, queda dudosa cuando algún
   año-régimen informativo es dudoso, y sin información en el resto. Con un empate de clases, j* queda
   indefinido (la unidad no puede ser informativa). Una hora modal de TX o TN con empate queda
   indefinida y entonces no se cumple la distancia de 12 h. Las métricas del año-régimen cuentan las
   marcas, el observador y TX/TN de sus partes válidas.
8. Reglas vencidas (§4.1.4), para el diagnóstico de orquestacion, según la Enmienda 1, punto E1-4 (adoptada y
   anclada en APH 81bb100). Cv(Z, y) se trata como cualquier H de P:
   - en E1 se clasifica por su etiqueta especial (el h0 real es válido bajo Cv). Los eventos siguen
     siendo los del Anexo A, y las fechas del Anexo A2 siguen siendo placebos;
   - en E2, c_H de cada unidad se calcula etiqueta por etiqueta. Si no es constante (una parte que no se
     cortó en las etiquetas de Cv, o un año-régimen que mezcla sus dos desfases), Cv queda sin
     información en esa unidad (motivo «desfase_no_constante»);
   - fuera de los años del Anexo A2, Cv queda sin información (motivo «fuera_anexo_A2»).
   E1-4 no fija la forma de los años-régimen con Cv: siguen siendo los de Zs (ORQ-3b de orquestacion).
9. [Enmienda 3, E3-2, opción A′, adoptada el 2026-10-24; implementación para el addendum] Eventos de regla
   vencida en E1a (§4.1.1, Anexo A3):
   - son las etiquetas de ``TablasCalendario.eventos_reglas_vencidas(Z, año)`` de cada zona de Zs y cada
     año con datos (h0 por zona; ver tablas); se evalúan con las mismas reglas «presente» y «ausente»
     (``_evaluar_h0``);
   - una etiqueta que ya es placebo de la zona (todas las fechas de adelanto del A2, y el 2022-10-09, que es
     D + 28 del adelanto real) va una sola vez en ``eventos``, con su clase de placebo; las demás van con la
     clase «regla_vencida». El papel de evento lo da la etiqueta, no la clase;
   - patrón de regla vencida(Z), POR REGLA VENCIDA (decisión del autor): la regla del patrón civil (mismos
     umbrales: E1A_PATRON_MIN_AUSENTES, E1A_P0, E1A_PATRON_AUSENTES_PCT y E1A_PLACEBO) con los eventos de
     UNA regla vencida, nombrada por su texto («octubre, domingo ≥ 9», que es la anterior a 2008;
     «agosto, domingo ≥ 16»; «septiembre, domingo ≥ 2»; «agosto, domingo ≥ 9») y, como placebos, sólo los
     del mismo día de la semana que no son eventos de regla vencida (no los del A2: ahí son eventos). Hay
     patrón si alguna regla lo tiene. Con los eventos de todas las reglas juntos (la letra del borrador) una
     hora civil con la regla anterior a 2008 nunca llega al 80 %: las 5 fechas que sólo da el A2 caen en
     agosto y septiembre, cuando esa regla aún está en invierno, y quedan «presentes» (15 ausentes de 20);
   - consecuencia: cada año con un evento ausente de una regla con el patrón, en esa zona, señala reloj
     anómalo en sus filas anuales (todas las H, porque es señal de la unidad). E1a no lo señala en ningún
     otro caso, así que «la estación tiene el patrón» = «E1a señala reloj anómalo en algún año»
     (``patron_regla_vencida``), que decision.rachas usa para la tercera condición de §5.3, punto 1;
   - en esos años el diagnóstico de §4.1.4 no pone la marca: con P ∪ {Cv} E1a sigue señalando reloj anómalo;
   - los estados por H (presente/ausente de los eventos reales) no cambian, y el patrón civil tampoco: sus
     placebos siguen siendo los del mismo día de la semana y los del A2 (red.py, RED-10, hace lo mismo).
10. E1c en Pascua: R-10 mes por mes [Enmienda 3; lectura para el addendum, corrige R-10 [D] sólo en E1c]. La
   unidad de E1c es el mes y su evidencia es un conteo: «una casilla menos» no dice qué etiqueta falta. Por
   eso, en la sub-evaluación de la zona Z (mes de adelanto de Z con una casilla menos y patrón de rejilla
   civil(Z)):
   - «C(Z)» = toda H bajo la cual la h0 de Z es inexistente: compatible;
   - «las fijas» = toda H bajo la cual ninguna etiqueta del mes es inexistente (ni la h0 de otra zona de Zs
     ni una fecha de adelanto del Anexo A2): incompatible;
   - una H con otra etiqueta inexistente en el mes (C(Z′) de otra zona de Zs cuyo adelanto cae en el mismo
     mes, o Cv con la fecha del A2 en ese mes) no es ni lo uno ni lo otro: sin información
     (MOTIVO_OTRA_ETIQUETA). La sub-evaluación de Z′, si Z′ tiene su patrón, la juzga.
   Las sub-evaluaciones de las zonas del mes se siguen combinando con estados.combinar; E1a y E1b no
   cambian. Con la lectura zona por zona (la anterior), en Pascua (Zs = Pacific/Easter y America/Santiago,
   adelantos el sábado 22:00 y el domingo 00:00 del mismo fin de semana) cada zona dejaba incompatible a la
   C de la otra, y E1c dejaba todas las H incompatibles. En las zonas continentales las h0 coinciden
   (domingo 00:00) y nada cambia, salvo Cv en 2022 en el diagnóstico de §4.1.4: la fecha del A2
   (2022-09-04) y el adelanto real (2022-09-11) caen en septiembre, y Cv(Z, 2022), que también pierde una
   casilla ese mes, pasa de incompatible a sin información (es la letra de §4.1.3, que sólo nombra a las
   fijas y a C(Z)). Es la formulación de la copia medida «E3_1_y_Pascua»; la copia combinada dejaba
   C_venc incompatible y no se usa.
Depende de: tipos, estados, umbrales (por ``ctx.umbrales``), constantes, numerico (redondeo con empates
hacia 0) y tablas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import math
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, estados, numerico, tablas
from reloj_dmc.tipos import (ESQUEMA_ANOTACION, ESQUEMA_ESTADOS, ESQUEMA_EVENTOS, ESQUEMA_EXTRACTO_HORA, ESQUEMA_MES,
                             ESQUEMA_METRICAS_E2, Cambio, ClaseEvento, ContextoEstacion, Estado, Hipotesis, Linea,
                             MotivoSinInfo, Nivel, Regimen, Regla, ResultadoEvento, ResultadoLinea, tabla_vacia,
                             validar_esquema)

_C = constantes.valor

ESQUEMA_EXTRACTO_ANOTADO = {**ESQUEMA_EXTRACTO_HORA, **ESQUEMA_ANOTACION}

UNA_HORA = timedelta(hours=1)
HORAS_DIA = 24
DIAS_SEMANA = 7
ADELANTO = "adelanto"

# Motivos cortos de la columna «motivo» que no están en tipos.MotivoSinInfo.
MOTIVO_SIN_EVENTOS = "sin_eventos"            # el año no tiene cambios de Zs (2015) ni meses evaluados
MOTIVO_SIN_PATRON = "sin_patron"              # evento ausente (E1a), δ (E1b) o casilla menos (E1c) sin patrón
MOTIVO_FUSION = "fusion"                      # lectura 6 del encabezado
MOTIVO_FUERA_A2 = "fuera_anexo_A2"            # Cv fuera de los años del Anexo A2 (lectura 8)
MOTIVO_NO_DIURNA = "no_diurna"                # E1b en un estación-año que no es diurno
MOTIVO_NO_EVALUABLE = "no_evaluable"          # E1b: ventana con pocos días o Δs ≠ Δe
MOTIVO_DELTA_CERO = "delta_no_informa"        # E1b: δ = 0 (o |δ| ≥ 2), que no informa
MOTIVO_REJILLA_COMPLETA = "rejilla_completa"  # E1c: «una rejilla completa no informa»
MOTIVO_SIN_ADELANTO = "sin_adelanto"          # E1c: mes sin adelanto de ninguna zona de Zs
MOTIVO_OTRA_ETIQUETA = "otra_etiqueta_del_mes"  # E1c: H con otra etiqueta inexistente en el mes (lectura 10)
MOTIVO_DESFASE = "desfase_no_constante"       # E2: c_H no es constante en la unidad (Cv, lectura 8)
MOTIVO_TXTN = "tx_tn"                         # E2: compatible que TX/TN dejan dudosa
MOTIVO_SIN_PARTES = "sin_partes"              # E2: año sin partes con etiquetas usables

# Resultados de E1b y E1c en eventos_transicion.csv (E1a usa tipos.ResultadoEvento).
E1B_EVALUADO = "evaluado"
E1B_NO_EVALUABLE = "no_evaluable"
E1B_NO_DIURNA = "no_diurna"
E1C_CASILLA_MENOS = "casilla_menos"
E1C_COMPLETA = "completa"
E1C_DISTINTA = "distinta"
E1C_SIN_CAMPOS = "campos_faltantes"
E1C_SIN_MES = "sin_mes"                       # el mes no está entre los que entran


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------
def _validar_extracto(extracto: pd.DataFrame) -> None:
    validar_esquema(extracto, ESQUEMA_EXTRACTO_ANOTADO, nombre="extracto anotado")
    L = extracto["L"]
    if L.isna().any():
        raise ValueError("extracto anotado: L con valores nulos")
    if not L.is_monotonic_increasing or L.duplicated().any():
        raise ValueError("extracto anotado: L debe venir ordenada y sin duplicados (§2.3 del diseño)")


def _ids(P: Sequence[Hipotesis]) -> list[str]:
    ids = [h.id for h in P]
    if len(set(ids)) != len(ids):
        raise ValueError(f"P con hipótesis repetidas: {ids}")
    return ids


def _anios_a2(cal) -> frozenset[int]:
    return frozenset(f.anio for f in cal.anexo_a2)


def _especial_bajo(h: Hipotesis, etiqueta: datetime, cal) -> bool | None:
    """True si la etiqueta es repetida o inexistente bajo H; None si H no está definida en ese año (Cv)."""
    if h.tipo == "F":
        return False
    if h.tipo == "Cv" and etiqueta.year not in _anios_a2(cal):
        return None
    return tablas.desfase_en_etiqueta(h, etiqueta, cal) is None


def _estados_evento(P: Sequence[Hipotesis], etiqueta: datetime, cal, *,
                    especiales_compatibles: bool, motivo: str | None = None) -> dict[str, tuple[Estado, str | None]]:
    """Sub-evaluación de un evento (R-10): las H bajo las que la etiqueta es especial frente a las demás.

    ``especiales_compatibles`` False (evento presente, patrón fijo): especiales incompatibles, el resto
    compatibles. True (ausente o rejilla con patrón civil): especiales compatibles, el resto incompatibles.
    """
    salida = {}
    for h in P:
        especial = _especial_bajo(h, etiqueta, cal)
        if especial is None:
            salida[h.id] = (Estado.SIN_INFORMACION, MOTIVO_FUERA_A2)
        elif especial == especiales_compatibles:
            salida[h.id] = (Estado.COMPATIBLE, motivo)
        else:
            salida[h.id] = (Estado.INCOMPATIBLE, motivo)
    return salida


def _sin_informacion(P: Sequence[Hipotesis], motivo: str) -> dict[str, tuple[Estado, str | None]]:
    return {h.id: (Estado.SIN_INFORMACION, motivo) for h in P}


def _coherente_con_clases(por_h: dict[str, tuple[Estado, str | None]], clases: Iterable) -> dict:
    """Lectura 6: si los miembros de una clase fusionada difieren, todos quedan sin información."""
    for clase in clases:
        miembros = [h.id for h in clase.miembros if h.id in por_h]
        if len({por_h[i][0] for i in miembros}) > 1:
            for i in miembros:
                por_h[i] = (Estado.SIN_INFORMACION, MOTIVO_FUSION)
    return por_h


def _fila(codigo: str, anio: int, linea: Linea, nivel: Nivel, unidad: str, h: str, estado: Estado,
          motivo: str | None = None, *, reloj_anomalo: bool = False, discordante: bool = False) -> dict:
    return {"codigo": codigo, "anio": int(anio), "linea": str(linea), "regla": str(Regla.UNICA),
            "nivel": str(nivel), "unidad": unidad, "H": h, "estado": str(Estado(estado)),
            "reloj_anomalo": bool(reloj_anomalo), "discordante": bool(discordante), "motivo": motivo}


def _marco(filas: list[dict], esquema: Mapping[str, str]) -> pd.DataFrame:
    if not filas:
        return tabla_vacia(esquema)
    return pd.DataFrame(filas, columns=list(esquema)).astype(dict(esquema))


def _combinar_con_motivo(sub: list[tuple[Estado, str | None]], vacio: str) -> tuple[Estado, str | None]:
    """estados.combinar con un motivo: el de las sub-evaluaciones que quedaron sin información."""
    if not sub:
        return Estado.SIN_INFORMACION, vacio
    estado = estados.combinar(e for e, _ in sub)
    if estados.es_informativo(estado):
        return estado, None
    motivos = sorted({m for e, m in sub if e == estado and m})
    return estado, (",".join(motivos) if motivos else None)


def _filas_e1(ctx: ContextoEstacion, linea: Linea, nivel: Nivel,
              unidades: list[tuple[int, str, dict[str, tuple[Estado, str | None]]]], vacio: str) -> pd.DataFrame:
    """Filas de las unidades (eventos reales o meses) y filas anuales combinadas para cada año con datos."""
    codigo, P = ctx.info.codigo, ctx.info.P
    ids = _ids(P)
    filas_unidad, por_anio = [], {}
    for anio, unidad, por_h in unidades:
        for h in ids:
            estado, motivo = por_h[h]
            filas_unidad.append(_fila(codigo, anio, linea, nivel, unidad, h, estado, motivo))
            por_anio.setdefault((anio, h), []).append((estado, motivo))
    filas_anio = []
    for anio in sorted(set(ctx.anios)):
        for h in ids:
            estado, motivo = _combinar_con_motivo(por_anio.get((anio, h), []), vacio)
            filas_anio.append(_fila(codigo, anio, linea, Nivel.ANIO, f"{anio:04d}", h, estado, motivo))
    return _marco(filas_anio + filas_unidad, ESQUEMA_ESTADOS)


def id_evento(zona: str, fecha_D: date, tipo: str, clase: ClaseEvento | str) -> str:
    """«<zona>|<AAAA-MM-DD>|<tipo>|<clase_evento>» (§2.1 del diseño)."""
    return f"{zona}|{fecha_D.isoformat()}|{tipo}|{ClaseEvento(clase)}"


def _texto_etiqueta(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M")


def _fila_evento(codigo: str, linea: Linea, zona: str, anio: int, tipo: str, clase: ClaseEvento, fecha_D: date,
                 etiqueta: datetime, resultado: str, *, p14=math.nan, pdom=math.nan, p=math.nan, delta_s=None,
                 delta_e=None, delta=None, casillas=None, esperadas=None) -> dict:
    return {"codigo": codigo, "linea": str(linea), "zona": zona, "anio": int(anio), "tipo": tipo,
            "clase_evento": str(clase), "fecha_D": fecha_D.isoformat(), "etiqueta": _texto_etiqueta(etiqueta),
            "p14": p14, "pdom": pdom, "p": p, "resultado": resultado, "delta_s": delta_s, "delta_e": delta_e,
            "delta": delta, "casillas": casillas, "esperadas": esperadas}


def _fraccion(n: int, d: int) -> float:
    return n / d if d else math.nan


# ---------------------------------------------------------------------------
# E1a, adelanto (§4.1.1)
# ---------------------------------------------------------------------------
class _Filas:
    """Consultas por etiqueta sobre el extracto: fila, H(L), huella, Ts y días con alguna fila."""

    def __init__(self, extracto: pd.DataFrame):
        L = extracto["L"].to_numpy(dtype="datetime64[ns]")
        self._ns = L.astype("int64")
        self._pos = dict(zip(self._ns.tolist(), range(len(self._ns))))
        self._medida = extracto["medida"].to_numpy(dtype=bool)
        self._huella = extracto["huella"].to_numpy(dtype=object)
        self._ts_filas = extracto["ts"].to_numpy(dtype="float64")
        con_ts = np.isfinite(self._ts_filas)
        self._ns_ts, self._ts = self._ns[con_ts], self._ts_filas[con_ts]
        self._dias = set(L.astype("datetime64[D]").astype("int64").tolist())

    @staticmethod
    def _a_ns(t: datetime) -> int:
        return int(np.datetime64(t, "ns").astype("int64"))

    def fila(self, t: datetime) -> int | None:
        return self._pos.get(self._a_ns(t))

    def medida(self, t: datetime) -> bool:
        i = self.fila(t)
        return i is not None and bool(self._medida[i])

    def huella(self, t: datetime):
        i = self.fila(t)
        return None if i is None else self._huella[i]

    def dia_con_filas(self, t: datetime) -> bool:
        return int(np.datetime64(t.date(), "D").astype("int64")) in self._dias

    def presencia(self, etiquetas: Iterable[datetime]) -> float:
        """Fracción con H = 1 entre las etiquetas cuyo día tiene alguna fila; NaN si ninguna cuenta."""
        n = d = 0
        for t in etiquetas:
            if self.dia_con_filas(t):
                d += 1
                n += self.medida(t)
        return _fraccion(n, d)

    def ts(self, t: datetime) -> float:
        i = self.fila(t)
        return math.nan if i is None else float(self._ts_filas[i])

    def ts_vecino(self, t: datetime) -> float:
        """Ts del vecino más cercano en tiempo con Ts (sin contar t); en un empate, el anterior (R-44)."""
        x = self._a_ns(t)
        k = int(np.searchsorted(self._ns_ts, x, side="left"))
        antes = k - 1 if k - 1 >= 0 else None
        despues = k if k < len(self._ns_ts) else None
        if despues is not None and self._ns_ts[despues] == x:
            despues = despues + 1 if despues + 1 < len(self._ns_ts) else None
        if antes is None and despues is None:
            return math.nan
        if despues is None or (antes is not None and x - self._ns_ts[antes] <= self._ns_ts[despues] - x):
            return float(self._ts[antes])
        return float(self._ts[despues])


def _distinta(a, b) -> bool:
    """Huella de h0 distinta de la de un vecino (vacío si el vecino no tiene fila)."""
    if b is None:
        return True
    if pd.isna(b):
        return True
    return a != b


@dataclass(frozen=True)
class _EventoE1a:
    zona: str
    anio: int
    clase: ClaseEvento
    fecha_D: date
    etiqueta: datetime
    p14: float
    pdom: float
    p: float
    resultado: ResultadoEvento

    @property
    def id(self) -> str:
        return id_evento(self.zona, self.fecha_D, ADELANTO, self.clase)


def _desplazamientos(n_total: int, paso_dias: int) -> list[timedelta]:
    """±paso, ±2·paso, … (n_total/2 a cada lado), sin el 0."""
    mitad = int(n_total) // 2
    return [timedelta(days=paso_dias * k) for k in range(-mitad, mitad + 1) if k]


def _evaluar_h0(filas: _Filas, h0: datetime, U) -> tuple[float, float, float, ResultadoEvento]:
    """(p14, pdom, p, resultado) de la regla de §4.1.1 en la etiqueta h0 (evento real o placebo)."""
    dias14 = _desplazamientos(U.f("E1A_DIAS_P14"), 1)
    semana = _desplazamientos(U.f("E1A_FECHAS_PDOM"), DIAS_SEMANA)
    p14 = filas.presencia(h0 + d for d in dias14)
    pdom = filas.presencia(h0 + d for d in semana)
    p = min(p14, pdom) if math.isfinite(p14) and math.isfinite(pdom) else math.nan
    t_menos, t_mas = h0 - UNA_HORA, h0 + UNA_HORA

    if filas.fila(h0) is not None:
        huella = filas.huella(h0)
        presente = (filas.medida(h0) and huella is not None and not pd.isna(huella)
                    and _distinta(huella, filas.huella(t_menos)) and _distinta(huella, filas.huella(t_mas)))
        ts0 = filas.ts(h0)
        if presente and math.isfinite(ts0):
            vecino = filas.ts_vecino(h0)
            presente = math.isfinite(vecino) and abs(ts0 - vecino) <= U.f("E1A_DTS_MAX")
        return p14, pdom, p, ResultadoEvento.PRESENTE if presente else ResultadoEvento.SIN_EVIDENCIA

    ausente = math.isfinite(p) and p >= U.a("E1A_P") and filas.medida(t_menos) and filas.medida(t_mas)
    if ausente:
        umbral = U.f("E1A_DIA_HABITUAL")
        dia = h0.date()
        habituales = [hora for hora in range(HORAS_DIA)
                      if hora != h0.hour
                      and filas.presencia(datetime.combine(dia, time(hora)) + d for d in dias14) >= umbral]
        presentes = sum(filas.medida(datetime.combine(dia, time(hora))) for hora in habituales)
        ausente = bool(habituales) and _fraccion(presentes, len(habituales)) >= umbral
    return p14, pdom, p, ResultadoEvento.AUSENTE if ausente else ResultadoEvento.SIN_EVIDENCIA


def _lejos_de_cambios(fecha: date, fechas_cambio: Sequence[date], dias: int, *, estricto: bool) -> bool:
    """True si la fecha está a ≥ ``dias`` (o a más de ``dias`` si ``estricto``) de toda fecha de cambio."""
    for f in fechas_cambio:
        d = abs((fecha - f).days)
        if d < dias or (estricto and d == dias):
            return False
    return True


def _eventos_e1a(extracto: pd.DataFrame, ctx: ContextoEstacion) -> list[_EventoE1a]:
    _validar_extracto(extracto)
    cal, U, zs = ctx.tablas, ctx.umbrales, tuple(ctx.info.zs)
    anios = sorted(set(ctx.anios))
    filas = _Filas(extracto)
    fechas_cambio = sorted({c.fecha_D for z in zs for c in cal.cambios(z)})
    semana = _desplazamientos(U.f("E1A_FECHAS_PDOM"), DIAS_SEMANA)
    distancia = _C("E1A_PLACEBO_DIAS_CAMBIO")
    eventos: list[_EventoE1a] = []
    for zona in zs:
        reales = [c for c in cal.cambios(zona) if c.tipo == ADELANTO and c.etiqueta.year in anios]
        placebos: dict[datetime, ClaseEvento] = {}
        for anio in anios:
            for c in cal.placebos_a2(zona, anio):
                if c.tipo == ADELANTO:
                    placebos[c.etiqueta] = ClaseEvento.PLACEBO_A2
        for c in reales:
            eventos.append(_EventoE1a(zona, c.etiqueta.year, ClaseEvento.REAL, c.fecha_D, c.etiqueta,
                                      *_evaluar_h0(filas, c.etiqueta, U)))
            for d in semana:
                t = c.etiqueta + d
                if t not in placebos and _lejos_de_cambios(t.date(), fechas_cambio, distancia, estricto=False):
                    placebos[t] = ClaseEvento.PLACEBO_SEMANA
        for t in sorted(placebos):
            eventos.append(_EventoE1a(zona, t.year, placebos[t], t.date(), t, *_evaluar_h0(filas, t, U)))
        # Enmienda 3, E3-2 (A′; lectura 9): eventos de regla vencida que no son ya placebos de la zona.
        reales_et = {c.etiqueta for c in reales}
        for t in sorted(_etiquetas_reglas_vencidas(cal, zona, anios)):
            if t not in placebos and t not in reales_et:
                eventos.append(_EventoE1a(zona, t.year, ClaseEvento.REGLA_VENCIDA, t.date(), t,
                                          *_evaluar_h0(filas, t, U)))
    return eventos


def _etiquetas_reglas_vencidas(cal, zona: str, anios: Iterable[int]) -> dict[datetime, str]:
    """h0 → regla vencida de los eventos de regla vencida de la zona en los años (Anexo A3; Enmienda 3, E3-2;
    lectura 9)."""
    return {c.etiqueta: regla for a in anios for c, regla in cal.eventos_reglas_vencidas(zona, a)}


@dataclass(frozen=True)
class _PatronE1a:
    n_evaluables: int
    n_ausentes: int
    P0: float
    n_placebos: int
    n_placebos_ausentes: int
    civil: bool


_EVALUABLES = (ResultadoEvento.PRESENTE, ResultadoEvento.AUSENTE)
_PLACEBOS_CIVIL = (ClaseEvento.PLACEBO_SEMANA, ClaseEvento.PLACEBO_A2)


def _patron(eventos: Sequence[_EventoE1a], placebos: Sequence[_EventoE1a], U) -> _PatronE1a:
    """Regla del patrón de §4.1.1 sobre eventos y placebos ya elegidos (se descartan los no evaluables):
    ≥ E1A_PATRON_MIN_AUSENTES ausentes con P0 ≤ E1A_P0, ausentes ≥ 80 % de los evaluables y placebos
    ausentes ≤ E1A_PLACEBO (sin placebos evaluables no hay patrón, lectura 1)."""
    evaluables = [e for e in eventos if e.resultado in _EVALUABLES]
    ausentes = [e for e in evaluables if e.resultado == ResultadoEvento.AUSENTE]
    placebos = [e for e in placebos if e.resultado in _EVALUABLES]
    n_pl_aus = sum(e.resultado == ResultadoEvento.AUSENTE for e in placebos)
    P0 = math.prod(1 - e.p for e in ausentes) if ausentes else math.nan
    pct = _C("E1A_PATRON_AUSENTES_PCT") / 100   # no-umbral: de porcentaje a fracción
    civil = (len(ausentes) >= _C("E1A_PATRON_MIN_AUSENTES") and P0 <= U.a("E1A_P0")
             and _fraccion(len(ausentes), len(evaluables)) >= pct
             and bool(placebos) and _fraccion(n_pl_aus, len(placebos)) <= U.a("E1A_PLACEBO"))
    return _PatronE1a(len(evaluables), len(ausentes), P0, len(placebos), n_pl_aus, civil)


def _patron_e1a(eventos: Sequence[_EventoE1a], U) -> _PatronE1a:
    """Patrón civil(Z) de la estación con los eventos y placebos de una zona (§4.1.1). Placebos: los del
    mismo día de la semana y los del A2 (no los eventos de regla vencida de la Enmienda 3)."""
    return _patron([e for e in eventos if e.clase == ClaseEvento.REAL],
                   [e for e in eventos if e.clase in _PLACEBOS_CIVIL], U)


def _patrones_regla_vencida(eventos: Sequence[_EventoE1a], etiquetas_rv: Mapping[datetime, str],
                            U) -> dict[str, _PatronE1a]:
    """Enmienda 3, E3-2 (A′; lectura 9): patrón de regla vencida(Z) POR REGLA VENCIDA (por su texto), con los
    eventos de esa regla en una zona y, como placebos, los del mismo día de la semana que no son eventos de
    ninguna regla vencida."""
    placebos = [e for e in eventos if e.clase == ClaseEvento.PLACEBO_SEMANA and e.etiqueta not in etiquetas_rv]
    candidatos = [e for e in eventos if e.clase != ClaseEvento.REAL and e.etiqueta in etiquetas_rv]
    return {r: _patron([e for e in candidatos if etiquetas_rv[e.etiqueta] == r], placebos, U)
            for r in sorted(set(etiquetas_rv.values()))}


def _marco_eventos_e1a(eventos: Sequence[_EventoE1a], codigo: str) -> pd.DataFrame:
    filas = [_fila_evento(codigo, Linea.E1A, e.zona, e.anio, ADELANTO, e.clase, e.fecha_D, e.etiqueta,
                          str(e.resultado), p14=e.p14, pdom=e.pdom, p=e.p) for e in eventos]
    return _marco(filas, ESQUEMA_EVENTOS)


def e1a(extracto: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea:
    """E1a, adelanto (§4.1.1): presencia esperada p = mín(p14, pdom), presente/ausente/sin evidencia,
    placebos (mismo día de la semana a ≥ 3 días de un cambio, y Anexo A2 con 2015), patrón civil(Z)
    por estación (≥ 2 ausentes, P0 ≤ E1A_P0, ausentes ≥ 80 % de los evaluables, placebos ≤ E1A_PLACEBO)
    y estado anual. En Pascua h0 es el sábado 22:00.

    Estados: una fila por evento real y H (nivel «evento»; la unidad es el id del evento) y una por año
    con datos y H (nivel «anio»), que combina los eventos del año. Los placebos van sólo en ``eventos``.

    Enmienda 3, E3-2 (opción A′; lectura 9): con el patrón de regla vencida(Z) de alguna regla, las filas
    anuales de cada año con un evento ausente de esa regla en Z llevan ``reloj_anomalo`` (todas las H).
    """
    eventos = _eventos_e1a(extracto, ctx)
    P, cal = ctx.info.P, ctx.tablas
    patrones = {z: _patron_e1a([e for e in eventos if e.zona == z], ctx.umbrales) for z in ctx.info.zs}
    anios_rv: set[int] = set()
    for z in ctx.info.zs:
        etiquetas_rv = _etiquetas_reglas_vencidas(cal, z, sorted(set(ctx.anios)))
        de_z = [e for e in eventos if e.zona == z]
        con_patron = {r for r, p in _patrones_regla_vencida(de_z, etiquetas_rv, ctx.umbrales).items() if p.civil}
        anios_rv.update(e.anio for e in de_z if e.clase != ClaseEvento.REAL and e.resultado == ResultadoEvento.AUSENTE
                        and etiquetas_rv.get(e.etiqueta) in con_patron)
    unidades = []
    for e in eventos:
        if e.clase != ClaseEvento.REAL:
            continue
        if e.resultado == ResultadoEvento.PRESENTE:
            por_h = _estados_evento(P, e.etiqueta, cal, especiales_compatibles=False)
        elif e.resultado == ResultadoEvento.AUSENTE and patrones[e.zona].civil:
            por_h = _estados_evento(P, e.etiqueta, cal, especiales_compatibles=True)
        elif e.resultado == ResultadoEvento.AUSENTE:
            por_h = _sin_informacion(P, MOTIVO_SIN_PATRON)
        else:
            por_h = _sin_informacion(P, str(MotivoSinInfo.SIN_EVIDENCIA))
        unidades.append((e.anio, e.id, _coherente_con_clases(por_h, ctx.clases.get(e.anio, ()))))
    estados_e1a = _filas_e1(ctx, Linea.E1A, Nivel.EVENTO, unidades, MOTIVO_SIN_EVENTOS)
    if anios_rv:
        marca = (estados_e1a["nivel"] == str(Nivel.ANIO)) & estados_e1a["anio"].isin(sorted(anios_rv))
        estados_e1a.loc[marca, "reloj_anomalo"] = True
    return ResultadoLinea(linea=Linea.E1A, estados=estados_e1a, metricas=None,
                          eventos=_marco_eventos_e1a(eventos, ctx.info.codigo))


def eventos_e1a(extracto: pd.DataFrame, ctx: ContextoEstacion) -> pd.DataFrame:
    """Los eventos reales, los placebos y los de regla vencida (Enmienda 3) con p14, pdom, p y resultado
    (para eventos_transicion.csv)."""
    return _marco_eventos_e1a(_eventos_e1a(extracto, ctx), ctx.info.codigo)


def patron_regla_vencida(estados: pd.DataFrame) -> bool:
    """Enmienda 3, E3-2 (A′; lectura 9): la estación tiene el patrón de regla vencida de §4.1.1 si E1a
    señala reloj anómalo en algún año (E1a sólo lo señala con ese patrón). ``estados``: ESQUEMA_ESTADOS de
    la estación (todas las líneas)."""
    if estados is None or not len(estados):
        return False
    return bool(((estados["linea"] == str(Linea.E1A)) & estados["reloj_anomalo"].astype(bool)).any())


# ---------------------------------------------------------------------------
# E1b, ventanas diurnas (§4.1.2)
# ---------------------------------------------------------------------------
def _bloques_circulares(mascara: np.ndarray) -> list[tuple[int, int]]:
    """(inicio, largo) de cada racha circular maximal de True."""
    n = len(mascara)
    if mascara.all():
        return [(0, n)]
    if not mascara.any():
        return []
    giro = int(np.flatnonzero(~mascara)[0])
    rotada = np.roll(mascara, -giro)
    bloques, i = [], 0
    while i < n:
        if rotada[i]:
            j = i
            while j < n and rotada[j]:
                j += 1
            bloques.append(((i + giro) % n, j - i))
            i = j
        else:
            i += 1
    return bloques


def _q_por_hora(L: np.ndarray, medida: np.ndarray) -> np.ndarray:
    """q_h: fracción de fechas (con alguna fila) con H = 1 en la etiqueta h, h = 0 … 23."""
    fechas = L.astype("datetime64[D]")
    n_fechas = len(np.unique(fechas))
    if n_fechas == 0:
        return np.zeros(HORAS_DIA)
    horas = ((L - fechas) // np.timedelta64(1, "h")).astype(int)
    return np.bincount(horas[medida], minlength=HORAS_DIA) / n_fechas


@dataclass(frozen=True)
class _Diurno:
    corte: int                 # primera etiqueta del día operativo: la que sigue al fin del bloque nocturno
    noche: frozenset[int]      # etiquetas del bloque nocturno


def _parametros_diurnos(q: np.ndarray, U) -> _Diurno | None:
    noches = [b for b in _bloques_circulares(q <= U.f("E1B_Q_NOCHE")) if b[1] >= U.f("E1B_ETIQ_NOCHE")]
    dias = [b for b in _bloques_circulares(q >= U.f("E1B_Q_DIA")) if b[1] >= U.f("E1B_ETIQ_DIA")]
    if not noches or not dias:
        return None
    inicio, largo = max(noches, key=lambda b: (b[1], -b[0]))
    fin = (inicio + largo - 1) % HORAS_DIA
    return _Diurno(corte=(fin + 1) % HORAS_DIA,
                   noche=frozenset((inicio + k) % HORAS_DIA for k in range(largo)))


def _diurno_del_anio(extracto_anio: pd.DataFrame, U) -> _Diurno | None:
    L = extracto_anio["L"].to_numpy(dtype="datetime64[ns]")
    return _parametros_diurnos(_q_por_hora(L, extracto_anio["medida"].to_numpy(dtype=bool)), U)


def es_estacion_diurna(extracto_anio: pd.DataFrame, ctx: ContextoEstacion) -> bool:
    """§4.1.2: bloque circular de ≥ 4 etiquetas con q_h ≤ 0,10 y otro de ≥ 8 con q_h ≥ 0,50."""
    for columna in ("L", "anio", "medida"):
        if columna not in extracto_anio.columns:
            raise ValueError(f"es_estacion_diurna necesita la columna {columna!r}")
    if extracto_anio["anio"].nunique() > 1:
        raise ValueError("es_estacion_diurna recibe un solo año de etiqueta")
    return _diurno_del_anio(extracto_anio, ctx.umbrales) is not None


def _tabla_dias(L: np.ndarray, medida: np.ndarray, diurno: _Diurno) -> pd.DataFrame:
    """Por día operativo (índice: días desde 1970, int): filas medidas, s_d y e_d desenrolladas (R-19)."""
    fechas = L.astype("datetime64[D]")
    horas = ((L - fechas) // np.timedelta64(1, "h")).astype(int)
    antes = horas < diurno.corte
    dia = fechas.astype("int64") - antes
    desenrollada = (horas + HORAS_DIA * antes).astype("float64")
    usa = medida & ~np.isin(horas, sorted(diurno.noche))
    marco = pd.DataFrame({"dia": dia, "n": medida.astype("int64"), "h": np.where(usa, desenrollada, np.nan)})
    g = marco.groupby("dia", sort=True)
    return pd.DataFrame({"n": g["n"].sum(), "s": g["h"].min(), "e": g["h"].max()})


def _escalon(dias: pd.DataFrame, D: date, U) -> tuple[int, int, int | None, int | None]:
    """(días de B, días de A, Δs, Δe); Δs y Δe None si alguna ventana tiene menos días que el mínimo."""
    validos = dias[(dias["n"] >= U.f("E1B_FILAS_DIA")) & dias["s"].notna()]
    d0 = int(np.datetime64(D, "D").astype("int64"))
    desde, hasta = int(U.f("E1B_VENTANA_DESDE_D")), int(U.f("E1B_VENTANA_HASTA_D"))
    B = validos.loc[d0 - hasta:d0 - desde]
    A = validos.loc[d0 + desde:d0 + hasta]
    minimo = U.f("E1B_DIAS_VENTANA")
    if len(B) < minimo or len(A) < minimo:
        return len(B), len(A), None, None
    ds = numerico.redondear_empate_hacia_cero(float(np.median(A["s"])) - float(np.median(B["s"])))
    de = numerico.redondear_empate_hacia_cero(float(np.median(A["e"])) - float(np.median(B["e"])))
    return len(B), len(A), ds, de


@dataclass(frozen=True)
class _EventoE1b:
    zona: str
    anio: int                  # año de etiqueta cuyo bloque nocturno se usa (el de su cambio de origen)
    tipo: str
    clase: ClaseEvento
    fecha_D: date
    etiqueta: datetime
    resultado: str
    delta_s: int | None
    delta_e: int | None
    delta: int | None

    @property
    def id(self) -> str:
        return id_evento(self.zona, self.fecha_D, self.tipo, self.clase)


class _DiasPorAnio:
    """Bloque nocturno y tabla de días operativos de cada año (con margen para las ventanas y placebos)."""

    def __init__(self, extracto: pd.DataFrame, U):
        self._L = extracto["L"].to_numpy(dtype="datetime64[ns]")
        self._medida = extracto["medida"].to_numpy(dtype=bool)
        self._anio = extracto["anio"].to_numpy()
        self._U = U
        self._margen = np.timedelta64(int(U.f("E1B_PLACEBO_2_D") + U.f("E1B_VENTANA_HASTA_D")) + 1, "D")
        self._cache: dict[int, tuple[_Diurno | None, pd.DataFrame | None]] = {}

    def de(self, anio: int) -> tuple[_Diurno | None, pd.DataFrame | None]:
        if anio not in self._cache:
            del_anio = self._anio == anio
            diurno = None
            if del_anio.any():
                diurno = _parametros_diurnos(_q_por_hora(self._L[del_anio], self._medida[del_anio]), self._U)
            dias = None
            if diurno is not None:
                desde = np.datetime64(f"{anio:04d}-01-01", "ns") - self._margen
                hasta = np.datetime64(f"{anio + 1:04d}-01-01", "ns") + self._margen
                a, b = np.searchsorted(self._L, [desde, hasta])
                dias = _tabla_dias(self._L[a:b], self._medida[a:b], diurno)
            self._cache[anio] = (diurno, dias)
        return self._cache[anio]


def _evaluar_cambio_e1b(dias_por_anio: _DiasPorAnio, zona: str, anio: int, tipo: str, clase: ClaseEvento,
                        D: date, etiqueta: datetime, U) -> _EventoE1b:
    diurno, dias = dias_por_anio.de(anio)
    if diurno is None:
        return _EventoE1b(zona, anio, tipo, clase, D, etiqueta, E1B_NO_DIURNA, None, None, None)
    _, _, ds, de = _escalon(dias, D, U)
    if ds is None or ds != de:
        return _EventoE1b(zona, anio, tipo, clase, D, etiqueta, E1B_NO_EVALUABLE, ds, de, None)
    return _EventoE1b(zona, anio, tipo, clase, D, etiqueta, E1B_EVALUADO, ds, de, ds if tipo == ADELANTO else -ds)


def _eventos_e1b(extracto: pd.DataFrame, ctx: ContextoEstacion) -> list[_EventoE1b]:
    _validar_extracto(extracto)
    cal, U, zs = ctx.tablas, ctx.umbrales, tuple(ctx.info.zs)
    anios = sorted(set(ctx.anios))
    dias_por_anio = _DiasPorAnio(extracto, U)
    fechas_cambio = sorted({c.fecha_D for z in zs for c in cal.cambios(z)})
    separacion = _C("E1B_PLACEBO_SEPARACION_D")
    saltos = [s * int(U.f(i)) for i in ("E1B_PLACEBO_1_D", "E1B_PLACEBO_2_D") for s in (-1, 1)]
    eventos: list[_EventoE1b] = []
    for zona in zs:
        reales = [c for c in cal.cambios(zona) if c.etiqueta.year in anios]
        placebos: dict[date, tuple[ClaseEvento, int, str, datetime]] = {}
        for anio in anios:
            for c in cal.placebos_a2(zona, anio):
                placebos[c.domingo] = (ClaseEvento.PLACEBO_A2, anio, c.tipo, c.etiqueta)
        for c in reales:
            eventos.append(_evaluar_cambio_e1b(dias_por_anio, zona, c.etiqueta.year, c.tipo, ClaseEvento.REAL,
                                               c.fecha_D, c.etiqueta, U))
            for salto in saltos:
                D = c.fecha_D + timedelta(days=salto)
                if D not in placebos and _lejos_de_cambios(D, fechas_cambio, separacion, estricto=True):
                    placebos[D] = (ClaseEvento.PLACEBO_DESPLAZADO, c.etiqueta.year, c.tipo,
                                   c.etiqueta + timedelta(days=salto))
        for D in sorted(placebos):
            clase, anio, tipo, etiqueta = placebos[D]
            eventos.append(_evaluar_cambio_e1b(dias_por_anio, zona, anio, tipo, clase, D, etiqueta, U))
    return eventos


@dataclass(frozen=True)
class _PatronE1b:
    n_evaluables: int
    n_menos: int
    n_mas: int
    n_placebos: int
    n_placebos_con_delta: int
    fijo: bool
    civil: bool


def _patron_e1b(eventos: Sequence[_EventoE1b], U) -> _PatronE1b:
    """Patrones fijo(Z) y civil(Z) con los cambios y placebos de una zona (§4.1.2)."""
    reales = [e for e in eventos if e.clase == ClaseEvento.REAL and e.resultado == E1B_EVALUADO]
    placebos = [e for e in eventos if e.clase != ClaseEvento.REAL and e.resultado == E1B_EVALUADO]
    n_menos = sum(e.delta == -1 for e in reales)
    n_mas = sum(e.delta == 1 for e in reales)
    con_delta = sum(abs(e.delta_s) >= U.f("E1B_PLACEBO_DELTA") for e in placebos)
    placebos_ok = bool(placebos) and _fraccion(con_delta, len(placebos)) <= U.frac("E1B_PLACEBO_PCT")
    fraccion, minimo = U.a("E1B_PATRON")

    def cumple(n: int) -> bool:
        return placebos_ok and n >= minimo and _fraccion(n, len(reales)) >= fraccion

    return _PatronE1b(len(reales), n_menos, n_mas, len(placebos), con_delta, cumple(n_menos), cumple(n_mas))


def e1b(extracto: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea:
    """E1b, ventanas diurnas (§4.1.2): s_d y e_d por día (≥ 6 filas medidas), escalón δ en cada cambio
    con ventanas B = [D−21, D−2] y A = [D+2, D+21] de ≥ 10 días, placebos a ±42 y ±63 días y del
    Anexo A2, patrones fijo(Z) y civil(Z) (E1B_PATRON) y estado anual. Horas desenrolladas respecto
    del fin del bloque nocturno (R-19).

    Estados: una fila por cambio real (adelanto o atraso) y H (nivel «evento») y una por año con datos y
    H (nivel «anio»). Los placebos van sólo en ``eventos``.
    """
    eventos = _eventos_e1b(extracto, ctx)
    P, cal = ctx.info.P, ctx.tablas
    patrones = {z: _patron_e1b([e for e in eventos if e.zona == z], ctx.umbrales) for z in ctx.info.zs}
    unidades = []
    for e in eventos:
        if e.clase != ClaseEvento.REAL:
            continue
        patron = patrones[e.zona]
        if e.resultado == E1B_NO_DIURNA:
            por_h = _sin_informacion(P, MOTIVO_NO_DIURNA)
        elif e.resultado != E1B_EVALUADO:
            por_h = _sin_informacion(P, MOTIVO_NO_EVALUABLE)
        elif patron.fijo and e.delta == -1:
            por_h = _estados_evento(P, e.etiqueta, cal, especiales_compatibles=False)
        elif patron.civil and e.delta == 1:
            por_h = _estados_evento(P, e.etiqueta, cal, especiales_compatibles=True)
        elif e.delta in (-1, 1):
            por_h = _sin_informacion(P, MOTIVO_SIN_PATRON)
        else:
            por_h = _sin_informacion(P, MOTIVO_DELTA_CERO)
        unidades.append((e.anio, e.id, _coherente_con_clases(por_h, ctx.clases.get(e.anio, ()))))
    filas = [_fila_evento(ctx.info.codigo, Linea.E1B, e.zona, e.anio, e.tipo, e.clase, e.fecha_D, e.etiqueta,
                          e.resultado, delta_s=e.delta_s, delta_e=e.delta_e, delta=e.delta) for e in eventos]
    return ResultadoLinea(linea=Linea.E1B, estados=_filas_e1(ctx, Linea.E1B, Nivel.EVENTO, unidades,
                                                             MOTIVO_SIN_EVENTOS),
                          metricas=None, eventos=_marco(filas, ESQUEMA_EVENTOS))


# ---------------------------------------------------------------------------
# E1c, rejilla del portal (§4.1.3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Mes:
    resultado: str
    casillas: int | None
    esperadas: int | None


def _meses_e1c(meses: pd.DataFrame, codigo: str) -> dict[tuple[int, int], _Mes]:
    validar_esquema(meses, ESQUEMA_MES, nombre="meses")
    entran = meses[(meses["codigo"] == codigo).fillna(False).to_numpy(dtype=bool)
                   & meses["entra"].to_numpy(dtype=bool)]
    claves = list(zip(entran["anio"].astype(int), entran["mes"].astype(int)))
    if len(set(claves)) != len(claves):
        raise ValueError(f"E1c: más de un manifiesto que entra en un mismo mes de {codigo}")
    salida = {}
    for clave, filas, vacias, esperadas in zip(claves, entran["row_count"], entran["source_empty_slots"],
                                               entran["expected_hour_slots"]):
        esperadas = None if pd.isna(esperadas) else int(esperadas)
        if pd.isna(filas) or pd.isna(vacias):
            salida[clave] = _Mes(E1C_SIN_CAMPOS, None, esperadas)
            continue
        casillas = int(filas) + int(vacias)
        if esperadas is None:
            resultado = E1C_SIN_CAMPOS
        elif casillas == esperadas:
            resultado = E1C_COMPLETA
        elif casillas == esperadas - 1:
            resultado = E1C_CASILLA_MENOS
        else:
            resultado = E1C_DISTINTA
        salida[clave] = _Mes(resultado, casillas, esperadas)
    return salida


def _mes_de(c: Cambio) -> tuple[int, int]:
    return c.etiqueta.year, c.etiqueta.month


def _patron_e1c(por_mes: Mapping[tuple[int, int], _Mes], cambios_zona: Sequence[Cambio], U) -> bool:
    """Patrón de rejilla civil(Z) (§4.1.3)."""
    con_cambio = {_mes_de(c) for c in cambios_zona}
    de_adelanto = {_mes_de(c) for c in cambios_zona if c.tipo == ADELANTO}
    evaluables = {k: m for k, m in por_mes.items() if m.resultado != E1C_SIN_CAMPOS}
    sin_cambio = [m for k, m in evaluables.items() if k not in con_cambio]
    completas = sum(m.resultado == E1C_COMPLETA for m in sin_cambio)
    menos_adelanto = sum(m.resultado == E1C_CASILLA_MENOS for k, m in evaluables.items() if k in de_adelanto)
    menos_otros = sum(m.resultado == E1C_CASILLA_MENOS for k, m in evaluables.items() if k not in de_adelanto)
    return (bool(sin_cambio) and _fraccion(completas, len(sin_cambio)) >= U.a("E1C_COMPLETO")
            and menos_adelanto >= _C("E1C_MIN_MESES") and menos_otros == 0)


def _etiquetas_adelanto_del_mes(cal, zs: Sequence[str], anio: int, mes: int) -> tuple[datetime, ...]:
    """Etiquetas de adelanto (inexistentes bajo alguna H) que caen en el mes: las del Anexo A de cada zona de
    Zs y las fechas de adelanto del Anexo A2 (las de Cv). Son las únicas que pueden faltar en la rejilla."""
    etiquetas = {c.etiqueta for z in zs for c in cal.cambios(z) if c.tipo == ADELANTO}
    etiquetas |= {c.etiqueta for z in zs for c in cal.placebos_a2(z, anio) if c.tipo == ADELANTO}
    return tuple(sorted(e for e in etiquetas if (e.year, e.month) == (anio, mes)))


def _estados_mes_e1c(P: Sequence[Hipotesis], etiqueta: datetime, del_mes: Sequence[datetime],
                     cal) -> dict[str, tuple[Estado, str | None]]:
    """Sub-evaluación de E1c para la zona Z de ``etiqueta`` en un mes con una casilla menos y con el patrón
    de Z (lectura 10 del encabezado: R-10 mes por mes). «C(Z)» = H bajo la que h0 de Z es inexistente
    (compatible); «las fijas» = H sin ninguna etiqueta inexistente en el mes (incompatibles); una H con
    otra etiqueta inexistente en el mes no es ninguna de las dos: sin información (MOTIVO_OTRA_ETIQUETA)."""
    salida = _estados_evento(P, etiqueta, cal, especiales_compatibles=True)
    otras = [e for e in del_mes if e != etiqueta]
    for h in P:
        if salida[h.id][0] == Estado.INCOMPATIBLE and any(_especial_bajo(h, e, cal) for e in otras):
            salida[h.id] = (Estado.SIN_INFORMACION, MOTIVO_OTRA_ETIQUETA)
    return salida


def e1c(meses: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea:
    """E1c, rejilla (§4.1.3): casillas = row_count + source_empty_slots; patrón civil(Z) si casillas =
    expected_hour_slots en ≥ E1C_COMPLETO de los meses sin cambio de Z y una casilla menos en ≥ 2 meses
    con adelanto de Z y en ningún otro. Sin alguno de los dos campos, el mes queda sin información.
    Informa además la casilla menos en meses de adelanto del Anexo A2 (§4.1.4).

    Estados: una fila por mes que entra y H (nivel «mes», unidad «AAAA-MM») y una por año con datos y H.
    ``eventos`` trae los meses de adelanto reales y los de las fechas de adelanto del Anexo A2.
    """
    codigo, P, cal, U = ctx.info.codigo, ctx.info.P, ctx.tablas, ctx.umbrales
    por_mes = _meses_e1c(meses, codigo)
    adelantos = {z: {_mes_de(c): c for c in cal.cambios(z) if c.tipo == ADELANTO} for z in ctx.info.zs}
    patrones = {z: _patron_e1c(por_mes, cal.cambios(z), U) for z in ctx.info.zs}
    unidades = []
    for (anio, mes), m in sorted(por_mes.items()):
        sub: dict[str, list[tuple[Estado, str | None]]] = {h.id: [] for h in P}
        for z in ctx.info.zs:
            c = adelantos[z].get((anio, mes))
            if c is None:
                continue
            if m.resultado == E1C_CASILLA_MENOS and patrones[z]:
                por_z = _estados_mes_e1c(P, c.etiqueta, _etiquetas_adelanto_del_mes(cal, ctx.info.zs, anio, mes),
                                         cal)
            elif m.resultado == E1C_SIN_CAMPOS:
                por_z = _sin_informacion(P, str(MotivoSinInfo.CAMPOS))
            elif m.resultado == E1C_COMPLETA:
                por_z = _sin_informacion(P, MOTIVO_REJILLA_COMPLETA)
            else:
                por_z = _sin_informacion(P, MOTIVO_SIN_PATRON)
            for h, v in por_z.items():
                sub[h].append(v)
        vacio = str(MotivoSinInfo.CAMPOS) if m.resultado == E1C_SIN_CAMPOS else MOTIVO_SIN_ADELANTO
        por_h = {h: _combinar_con_motivo(v, vacio) for h, v in sub.items()}
        unidades.append((anio, f"{anio:04d}-{mes:02d}", _coherente_con_clases(por_h, ctx.clases.get(anio, ()))))

    filas_ev = []
    anios = sorted(set(ctx.anios))
    for z in ctx.info.zs:
        candidatos = [(ClaseEvento.REAL, c) for c in cal.cambios(z) if c.tipo == ADELANTO and c.etiqueta.year in anios]
        candidatos += [(ClaseEvento.PLACEBO_A2, c) for anio in anios for c in cal.placebos_a2(z, anio)
                       if c.tipo == ADELANTO]
        for clase, c in sorted(candidatos, key=lambda x: x[1].etiqueta):
            m = por_mes.get(_mes_de(c), _Mes(E1C_SIN_MES, None, None))
            filas_ev.append(_fila_evento(codigo, Linea.E1C, z, c.etiqueta.year, ADELANTO, clase, c.fecha_D,
                                         c.etiqueta, m.resultado, casillas=m.casillas, esperadas=m.esperadas))
    return ResultadoLinea(linea=Linea.E1C, estados=_filas_e1(ctx, Linea.E1C, Nivel.MES, unidades, MOTIVO_SIN_EVENTOS),
                          metricas=None, eventos=_marco(filas_ev, ESQUEMA_EVENTOS))


# ---------------------------------------------------------------------------
# E2, firma sinóptica módulo 3 (§4.2)
# ---------------------------------------------------------------------------
def clase_mod3(hora: int) -> int:
    """Clase de una etiqueta: hora mód E2_MODULO = 3 (Python: (−4) % 3 == 2)."""
    return hora % _C("E2_MODULO")


def _moda_unica(cuentas: np.ndarray) -> int | None:
    """Índice del máximo si es único y positivo; None si hay empate o no hay cuentas."""
    if cuentas.size == 0 or cuentas.max() <= 0:
        return None
    maximos = np.flatnonzero(cuentas == cuentas.max())
    return int(maximos[0]) if len(maximos) == 1 else None


@dataclass(frozen=True)
class _Marcas:
    n: int
    kappa: float
    j: int | None
    hora: int | None


def _marcas(horas: np.ndarray) -> _Marcas:
    modulo = _C("E2_MODULO")
    if horas.size == 0:
        return _Marcas(0, math.nan, None, None)
    por_clase = np.bincount(horas % modulo, minlength=modulo)
    return _Marcas(int(horas.size), float(por_clase.max() / horas.size), _moda_unica(por_clase),
                   _moda_unica(np.bincount(horas, minlength=HORAS_DIA)))


@dataclass(frozen=True)
class _UnidadE2:
    anio: int
    nivel: Nivel
    unidad: str
    regimen: str
    n_rr: int
    frac_observador: float
    valida: bool
    rr: _Marcas
    tx: _Marcas
    tn: _Marcas
    informativa: bool
    motivo: str | None          # por qué no es informativa (None si lo es)


def _unidad_e2(anio: int, nivel: Nivel, unidad: str, regimen: str, horas: np.ndarray, rr: np.ndarray,
               observador: np.ndarray, tx: np.ndarray, tn: np.ndarray, valida: bool | None, U) -> _UnidadE2:
    n_rr = int(rr.sum())
    frac = _fraccion(int((rr & observador).sum()), n_rr)
    if valida is None:                                  # una parte: §4.2, «Validez»
        valida = n_rr > 0 and frac >= U.f("E2_OBSERVADOR")
    marcas_rr = _marcas(horas[rr])
    if not valida:
        informativa, motivo = False, str(MotivoSinInfo.SIN_OBSERVADOR)
    elif n_rr < U.a("E2_MIN_RR"):
        informativa, motivo = False, str(MotivoSinInfo.MINIMOS)
    elif marcas_rr.j is None or marcas_rr.kappa < U.a("E2_KAPPA"):
        informativa, motivo = False, str(MotivoSinInfo.NO_INFORMATIVA)
    else:
        informativa, motivo = True, None
    return _UnidadE2(anio, nivel, unidad, regimen, n_rr, frac, bool(valida), marcas_rr, _marcas(horas[tx]),
                     _marcas(horas[tn]), informativa, motivo)


def _txtn_cumple(u: _UnidadE2, U) -> bool:
    """§4.2 con la lectura A de R-11: si TX y TN alcanzan sus mínimos, deben caer en j* y distar 12 h."""
    minimo, kappa = U.f("E2_TXTN_MIN"), U.f("E2_TXTN_KAPPA")
    exigible = all(m.n >= minimo and m.kappa >= kappa for m in (u.tx, u.tn))
    if not exigible:
        return True
    if u.tx.j != u.rr.j or u.tn.j != u.rr.j or u.tx.hora is None or u.tn.hora is None:
        return False
    return numerico.distancia_circular(u.tx.hora, u.tn.hora, HORAS_DIA) == _C("E2_TXTN_DIST_H")


def _regimen(ctx: ContextoEstacion, anio: int, ident: str) -> Regimen | None:
    regs = ctx.regimenes.get(anio) if ctx.regimenes else None
    if not regs:
        regs = tablas.regimenes_del_anio(ctx.info.zs, anio, ctx.tablas)
    return next((r for r in regs if r.id == ident), None)


def _desfase_unidad(h: Hipotesis, anio: int, regimen: str, etiquetas: np.ndarray,
                    ctx: ContextoEstacion) -> tuple[int | None, str | None]:
    """(c_H en la unidad, None) si es constante; (None, motivo) si no lo es o si H no está definida ese año.

    F: su c. C(Z) con Z ∈ Zs: c_H(R) del régimen, porque las partes se cortan en las etiquetas especiales
    de Zs. Cv (y una C fuera de Zs): etiqueta por etiqueta (lectura 8).
    """
    if h.tipo == "F":
        return int(h.desfase), None
    zs = tuple(ctx.info.zs)
    if h.tipo == "C" and h.zona in zs:
        reg = _regimen(ctx, anio, regimen)
        if reg is not None:
            return tablas.desfase(h, reg, zs), None
    if h.tipo == "Cv" and anio not in _anios_a2(ctx.tablas):
        return None, MOTIVO_FUERA_A2
    valores = {tablas.desfase_en_etiqueta(h, pd.Timestamp(t).to_pydatetime(), ctx.tablas) for t in etiquetas}
    if len(valores) == 1 and None not in valores:
        return valores.pop(), None
    return None, MOTIVO_DESFASE


def _estados_unidad_e2(u: _UnidadE2, desfases: Mapping[str, tuple[int | None, str]], U) -> tuple[dict, bool]:
    """Estado de la unidad por H y señal de reloj anómalo (§4.2, «Estado de la unidad»).

    ``desfases``: H → (c_H en la unidad o None, motivo si es None).
    """
    if not u.informativa:
        return {h: (Estado.SIN_INFORMACION, u.motivo) for h in desfases}, False
    modulo = _C("E2_MODULO")
    clases_P = {c % modulo for c, _ in desfases.values() if c is not None}
    anomalo = u.rr.j not in clases_P
    txtn = _txtn_cumple(u, U)
    salida = {}
    for h, (c, motivo) in desfases.items():
        if c is None:
            salida[h] = (Estado.SIN_INFORMACION, motivo)
        elif c % modulo == u.rr.j:
            salida[h] = (Estado.COMPATIBLE, None) if txtn else (Estado.DUDOSA, MOTIVO_TXTN)
        else:
            salida[h] = (Estado.INCOMPATIBLE, None)
    return salida, anomalo


def e2(extracto: pd.DataFrame, ctx: ContextoEstacion) -> ResultadoLinea:
    """E2, firma sinóptica módulo 3 (§4.2): validez por parte (observador en ≥ 0,50 de las filas con RR),
    j* y κ3 por parte y por año-régimen (marcas de sus partes válidas), informativa con ≥ E2_MIN_RR marcas
    y κ3 ≥ E2_KAPPA; compatible si j* = c_H(R) mód 3; reloj anómalo si ninguna H de P tiene esa clase;
    TX/TN pasan una compatible a dudosa; estado anual por estados.anual_por_partes más la regla de
    compatibilidad anual (≥ 2 partes informativas y todos los años-régimen informativos compatibles).
    Métricas en ESQUEMA_METRICAS_E2.
    """
    _validar_extracto(extracto)
    U, P, codigo = ctx.umbrales, ctx.info.P, ctx.info.codigo
    ids = _ids(P)
    usa = ~extracto["especial"].to_numpy(dtype=bool) & extracto["regimen"].notna().to_numpy(dtype=bool)
    x = extracto.loc[usa, ["L", "anio", "parte", "regimen", "rr", "tx", "tn", "observador"]].reset_index(drop=True)
    L = x["L"].to_numpy(dtype="datetime64[ns]")
    horas = ((L - L.astype("datetime64[D]")) // np.timedelta64(1, "h")).astype(int)
    rr, tx, tn, observador = (x[c].to_numpy(dtype=bool) for c in ("rr", "tx", "tn", "observador"))
    anio_x = x["anio"].to_numpy(dtype=int)
    regimen_x = x["regimen"].to_numpy(dtype=object)

    unidades: list[tuple[_UnidadE2, np.ndarray]] = []       # (unidad, posiciones en x de sus etiquetas)
    partes_validas: dict[tuple[int, str], list[np.ndarray]] = {}
    grupos = x.groupby(["anio", "parte"], sort=False).indices if len(x) else {}
    for (anio, parte), pos in sorted(grupos.items(), key=lambda kv: kv[1][0]):    # en orden de etiqueta
        reg = str(regimen_x[pos[0]])
        u = _unidad_e2(int(anio), Nivel.PARTE, str(parte), reg, horas[pos], rr[pos], observador[pos], tx[pos],
                       tn[pos], None, U)
        unidades.append((u, pos))
        if u.valida:
            partes_validas.setdefault((int(anio), reg), []).append(pos)
    for anio in sorted(set(anio_x.tolist())):
        for reg in sorted({str(r) for r in regimen_x[anio_x == anio]}):
            validas = partes_validas.get((anio, reg), [])
            pos = np.sort(np.concatenate(validas)) if validas else np.array([], dtype=int)
            todas = np.flatnonzero((anio_x == anio) & (regimen_x == reg))
            u = _unidad_e2(anio, Nivel.REGIMEN, reg, reg, horas[pos], rr[pos], observador[pos], tx[pos], tn[pos],
                           bool(validas), U)
            unidades.append((u, todas))

    filas, metricas = [], []
    for u, pos in unidades:
        desfases = {h.id: _desfase_unidad(h, u.anio, u.regimen, L[pos], ctx) for h in P}
        por_h, anomalo = _estados_unidad_e2(u, desfases, U)
        for h in ids:
            estado, motivo = por_h[h]
            filas.append(_fila(codigo, u.anio, Linea.E2, u.nivel, u.unidad, h, estado, motivo, reloj_anomalo=anomalo))
        metricas.append({
            "codigo": codigo, "anio": u.anio, "nivel": str(u.nivel), "unidad": u.unidad, "regimen": u.regimen,
            "n_rr": u.n_rr, "frac_observador": u.frac_observador, "valida": u.valida, "informativa": u.informativa,
            "j_estrella": u.rr.j, "kappa3": u.rr.kappa,
            "n_tx": u.tx.n, "kappa3_tx": u.tx.kappa, "j_tx": u.tx.j, "hora_modal_tx": u.tx.hora,
            "n_tn": u.tn.n, "kappa3_tn": u.tn.kappa, "j_tn": u.tn.j, "hora_modal_tn": u.tn.hora,
        })

    estados_unidades = _marco(filas, ESQUEMA_ESTADOS)
    anual = estados.anual_por_partes(estados_unidades, linea=Linea.E2, min_partes=_C("ANUAL_MIN_PARTES"))
    anual = _compatibilidad_anual_e2(anual, unidades, U)
    faltan = [_fila(codigo, a, Linea.E2, Nivel.ANIO, f"{a:04d}", h, Estado.SIN_INFORMACION, MOTIVO_SIN_PARTES)
              for a in sorted(set(ctx.anios) - set(anio_x.tolist())) for h in ids]
    salida = pd.concat([anual, _marco(faltan, ESQUEMA_ESTADOS)], ignore_index=True)
    es_anio = salida["nivel"] == str(Nivel.ANIO)
    salida = pd.concat([salida[es_anio].sort_values("anio", kind="mergesort"), salida[~es_anio]], ignore_index=True)
    return ResultadoLinea(linea=Linea.E2, estados=salida.astype(ESQUEMA_ESTADOS),
                          metricas=_marco(metricas, ESQUEMA_METRICAS_E2), eventos=None)


def _compatibilidad_anual_e2(anual: pd.DataFrame, unidades: Sequence[tuple[_UnidadE2, np.ndarray]], U) -> pd.DataFrame:
    """Regla de compatibilidad anual de E2 sobre la salida de estados.anual_por_partes (lectura 7)."""
    if anual.empty:
        return anual
    salida = anual.copy()
    es_anio = (salida["nivel"] == str(Nivel.ANIO)).to_numpy()
    estado_de = {(r.anio, r.nivel, r.unidad, r.H): r.estado for r in salida[~es_anio].itertuples(index=False)}
    minimo = _C("E2_MIN_PARTES_COMPAT")
    for i in np.flatnonzero(es_anio):
        if salida.at[i, "estado"] == str(Estado.INCOMPATIBLE):
            continue
        anio, h = int(salida.at[i, "anio"]), salida.at[i, "H"]
        partes = [u for u, _ in unidades if u.anio == anio and u.nivel == Nivel.PARTE and u.informativa]
        regimenes = [u for u, _ in unidades if u.anio == anio and u.nivel == Nivel.REGIMEN and u.informativa]
        de_regimen = [estado_de[(anio, str(Nivel.REGIMEN), u.unidad, h)] for u in regimenes]
        if len(partes) >= minimo and de_regimen and all(e == str(Estado.COMPATIBLE) for e in de_regimen):
            estado, motivo = Estado.COMPATIBLE, None
        elif any(e == str(Estado.DUDOSA) for e in de_regimen):
            estado, motivo = Estado.DUDOSA, MOTIVO_TXTN
        elif len(partes) < minimo:
            estado, motivo = Estado.SIN_INFORMACION, f"{len(partes)} partes informativas"
        elif not de_regimen:
            estado, motivo = Estado.SIN_INFORMACION, "sin año-régimen informativo"
        else:
            estado, motivo = Estado.SIN_INFORMACION, "año-régimen informativo sin compatibilidad"
        salida.at[i, "estado"] = str(estado)
        salida.at[i, "motivo"] = motivo
    return salida.astype(ESQUEMA_ESTADOS)
