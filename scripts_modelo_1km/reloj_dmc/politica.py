"""Salida que consume ``cargar_dmc``: bordes civiles, tramos, política, comprobaciones de §7.3 y validación
de uso (§7.1 a §7.3, §7.5).

- ``bordes_civiles``: los intervalos de desfase fijo de C(Z) de §7.2 («Hora civil confirmada»), en etiqueta
  ingenua e inclusivos, sin las etiquetas repetidas e inexistentes de Z (Anexo A, desde ``tablas``):
  en el atraso, el verano termina 1 h antes de la repetida y el invierno empieza 1 h después; en el
  adelanto, el invierno termina 1 h antes de h0 y el verano empieza 1 h después.
- ``tramos``: de la primera a la última etiqueta con dato de una sucesión de meses con regla, de una misma
  racha y con el mismo desfase; nunca cubre un mes sin etiquetas evaluadas. La hora civil sale como
  tramos fijos −180/−240 (Pascua −300/−360). Nunca ``timezone``.
- ``politica``: el JSON «dmc-reloj-politica/1» de §7.2, con ``clock`` de exactamente seis claves;
  ``escribir_politica`` lo escribe de forma atómica con ``entorno.json_canonico``.
- ``verificar_politica``: las siete comprobaciones de §7.3 sobre el JSON RELEÍDO desde disco; cualquier
  falla es A7. Usa ``_confirmado`` y ``_utc`` del adaptador fijado, ``policy_check`` de preflight_v3 y,
  en la muestra fijada, ``normalizar`` y ``cargar_dmc`` con sólo las reglas ``clock`` de la estación.
- ``validar_regla_reloj_dmc(regla, artefacto_sha256)``: la función de uso obligatorio desde un
  envoltorio (§7.5); repite las comprobaciones 1 y 5 y exige que el artefacto esté en
  ``artefactos_evaluados``. No se conecta dentro de cargar_dmc, policy_check ni el lector agudo.
El código fijado (adaptador, dmc_features, preflight_v3) no se modifica: llega ya cargado por
``fijados`` en ``ContextoVerificacion``.

Lecturas propias de este módulo (van al addendum de C1 junto con las del diseño):
- **Veredicto de una etiqueta:** la clase confirmada de su año (§5.1). Si esa clase contiene una C(Z),
  sola o fusionada, las etiquetas repetidas e inexistentes de Z del año quedan sin regla (§7.2), aunque
  la racha sea de un reloj fijo: no se presta evidencia entre años (§5.3, punto 5).
- **Cortes de un tramo:** cambia la racha o el desfase; se salta un mes (sin regla o sin etiquetas con
  dato: lectura conservadora de «nunca cubre un mes sin artefacto evaluado»); o queda dentro una etiqueta
  especial de una zona del veredicto de su año. Entre bordes civiles y etiquetas con dato manda la
  intersección (R-37). El id es «<racha>.<k>», con k contado dentro de la racha (R-25).
- **Veredicto de un tramo** (comprobaciones 1, 4 y 5): la intersección de las clases de sus años
  (``Tramo.clase``). Dentro de una racha nunca es vacía. Ejemplo de §5.3: 2014 C(Santiago), 2015
  {F(−3), C(Santiago)} y 2016 C(Santiago) dan un tramo −180 de 2014-09-07T01:00 a 2016-05-14T22:00 con
  veredicto C(Santiago).
- **«60·c del veredicto»:** con una C(Z), el tramo entero cae en un solo intervalo de ``bordes_civiles``
  de Z con ese desfase; con una F(c), 60·c. Con una clase fusionada, todos sus miembros.
- **Comprobación 5:** el «invierno de una C(Z) continental» es un tramo entero dentro de un intervalo
  −240 de Santiago, Coyhaique o Punta_Arenas. Un −240 decimal (−240.0) también cuenta como −240.
- **Comprobación 7:** un aborto es «por los datos» si ``normalizar`` (o ``cargar_dmc``) aborta también
  SIN política; si sólo aborta con las reglas ``clock`` de la estación, es por la política (A7). Los
  abortos por los datos van a ``ContextoVerificacion.no_normalizables`` (filas de no_normalizables.csv).
  ``meses_muestra_lector_real`` arma la muestra (R-48).
- **Esquema de ``estaciones``:** a cada estación con tramos se le agrega ``tramos`` = {id: veredicto del
  tramo}. Hace falta para que ``validar_regla_reloj_dmc`` repita la comprobación 5 con el veredicto que
  hay detrás de cada −240; el resto de la entrada llega hecho (veredicto, reloj, conjunto, marcas…).
- **«reloj» de una estación** (R-25): ``reloj_de_rachas`` es la regla única que usan orquestacion (ORQ-7)
  y salidas (SAL-11): clases de las rachas en orden, unidas por intersección mientras no sea vacía, y «→»
  sólo donde lo es (el cambio de §5.3.3). Vive aquí porque es un campo de ``estaciones`` (§7.2).
- **``artefactos_evaluados.json.gz``** (lo escribe salidas): una lista de objetos con, al menos,
  ``artefacto_sha256`` y ``codigo`` (también se acepta ``{"artefactos": [...]}``).
- **``validar_regla_reloj_dmc``** exige además que la regla sea, tal cual, la publicada para su estación y
  tramo, y que el artefacto sea de esa estación. Admite las claves que S6 une a la regla
  (``coordinates``, ``measurements``, ``quality``).
Depende de: entorno, fijados, tipos, constantes, tablas.
"""
from __future__ import annotations

import bisect
import copy
import gzip
import json
import re
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any, Callable, Iterable, Mapping, NamedTuple, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, entorno, fijados
from reloj_dmc import tablas as calendario
from reloj_dmc.tipos import ZONAS, Conjunto, Hipotesis, Tramo, VeredictoEstacion, interseccion_de_clases

ESQUEMA_POLITICA = "dmc-reloj-politica/1"
CLAVES_CLOCK = ("verified", "source", "valid_from", "valid_to", "timestamp_semantics", "fixed_offset_minutes")
CLAVES_TRAMO = ("station_code", "valid_from", "valid_to", "clock")
SEMANTICA = "instantaneous"
PATRON_SOURCE = (r"^reloj-dmc/v1 informe=(\S+) sha256=([0-9a-f]{64}) estacion=(\d{6}) "
                 r"tramo=(\d+\.\d+) protocolo=([0-9a-f]{64})$")
RUTA_PROTOCOLO_AP = "scripts_modelo_1km/reloj_dmc/PROTOCOLO_RELOJ_DMC.md"
RUTA_CONFIGURACION_AP = "config/meteorologia/reloj_dmc_v1.json"
RUTA_PUBLICACION_AP = "config/meteorologia/reloj_dmc/v1"
ARCHIVO_POLITICA = "politica_reloj_dmc.json"
ARCHIVO_INFORME = "informe_reloj_dmc.json"
ARCHIVO_INFORME_MD = "informe_reloj_dmc.md"
ARCHIVO_ARTEFACTOS = "artefactos_evaluados.json.gz"
ARCHIVOS_PUBLICADOS = (ARCHIVO_POLITICA, ARCHIVO_INFORME, ARCHIVO_INFORME_MD, ARCHIVO_ARTEFACTOS)
RUTA_INFORME_AP = f"{RUTA_PUBLICACION_AP}/{ARCHIVO_INFORME}"
RUTA_ARTEFACTOS_AP = f"{RUTA_PUBLICACION_AP}/{ARCHIVO_ARTEFACTOS}"
CLAVES_POLITICA = ("schema", "post_hoc", "errata_post_c4", "ajuste_documental", "protocolo", "configuracion",
                   "informe", "artefactos_evaluados", "adaptador_sha256", "interprete", "transiciones_sha256",
                   "politicas_reloj", "estaciones")
MARCAS_POLITICA = ("post_hoc", "errata_post_c4", "ajuste_documental")
# Claves que S6 une a una regla de reloj antes de usarla (§7.2: «después de unirle coordenadas,
# mediciones y calidad»); validar_regla_reloj_dmc las admite y no las mira.
CLAVES_UNIDAS_S6 = ("coordinates", "measurements", "quality")
CLAVE_TRAMOS_ESTACION = "tramos"

# §7.2: «Sólo se usa `fixed_offset_minutes` ∈ {0, −180, −240, −300, −360}, entero e igual a 60·c».
DESFASES = tuple(constantes.valor("DESFASES_PERMITIDOS"))
MINUTOS_POR_HORA = 60
# §7.3, comprobación 5: «Falla todo −240 que no tenga detrás un veredicto F(−4) o el invierno de una C(Z)
# continental». El −240 se deriva de F(−4) para no escribirlo a mano.
HIPOTESIS_PLANTILLA = "F(-4)"
MINUTOS_PLANTILLA = MINUTOS_POR_HORA * Hipotesis.desde_id(HIPOTESIS_PLANTILLA).desfase
ZONA_INSULAR = "Pacific/Easter"
ZONAS_CONTINENTALES = tuple(z for z in ZONAS if z != ZONA_INSULAR)
SEPARADOR_RACHAS = "→"          # «F(-4)→F(0)» (R-25)
SEPARADOR_CLASE = "|"           # «F(-3)|C(Santiago)» (§2.1 del diseño)

UNA_HORA = timedelta(hours=1)
LIMITE_MENSAJES = 200           # no-umbral: tope de mensajes por comprobación en la lista de fallas
ABREVIATURA = 8                 # no-umbral: caracteres de una huella abreviada en los mensajes
# Números de las comprobaciones de §7.3 (prefijo «comprobación N: » de cada falla).
(C_ESQUEMA, C_COBERTURA, C_CONVERSION, C_ESPECIALES, C_PLANTILLAS, C_POLICY_CHECK,
 C_LECTOR_REAL) = range(1, 8)  # no-umbral: numeración de §7.3, no son umbrales

_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_CODIGO = re.compile(r"\d{6}")
_TRAMO_ID = re.compile(r"[1-9]\d*\.[1-9]\d*")
_ANIO = re.compile(r"\d{4}")
_MES = re.compile(r"(\d{4})-(\d{2})")
_INSTANTE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:00:00")
_PATRON_SOURCE = re.compile(PATRON_SOURCE)
_VEREDICTOS_ESTACION = tuple(v.value for v in VeredictoEstacion)
_CONJUNTOS = tuple(c.value for c in Conjunto)

_RUTA_POLITICA_PUBLICADA = Path(__file__).resolve().parents[2] / RUTA_PUBLICACION_AP / ARCHIVO_POLITICA


class FallaA7(Exception):
    """Una comprobación de §7.3 falló: no se publica y se trata como errata (§10)."""


# ---------------------------------------------------------------------------
# Etiquetas, meses y clases
# ---------------------------------------------------------------------------
def _dominio() -> tuple[datetime, datetime]:
    """Primera y última etiqueta del Anexo A (2000-01-01T00:00 a 2026-12-31T23:00)."""
    desde, hasta = calendario.ANIOS_ANEXO_A
    return datetime(desde, 1, 1), datetime(hasta + 1, 1, 1) - UNA_HORA


def _exigir_hora_exacta(d: datetime) -> datetime:
    if d.tzinfo is not None:
        raise ValueError(f"la etiqueta debe ser ingenua (hora de pared): {d!r}")
    if d.minute or d.second or d.microsecond:
        raise ValueError(f"la etiqueta no es una hora exacta: {d.isoformat()}")
    return d


def _etiqueta(x: Any) -> datetime:
    """datetime ingenuo en hora exacta desde datetime, pd.Timestamp, numpy.datetime64 o texto ISO."""
    if type(x) is datetime:
        return _exigir_hora_exacta(x)
    if isinstance(x, str):
        return _exigir_hora_exacta(datetime.fromisoformat(x))
    t = pd.Timestamp(x)
    if pd.isna(t):
        raise ValueError("etiqueta nula")
    if t.nanosecond:
        raise ValueError(f"la etiqueta no es una hora exacta: {t}")
    return _exigir_hora_exacta(t.to_pydatetime())


def _etiquetas(valores: Iterable, *, unicas: bool) -> list[datetime]:
    """Etiquetas ingenuas en hora exacta, ordenadas (y sin repetir si ``unicas``)."""
    if isinstance(valores, (np.ndarray, pd.Index, pd.Series)):
        indice = pd.DatetimeIndex(valores)
        if indice.tz is not None:
            raise ValueError("las etiquetas deben ser ingenuas (timestamp_source)")
        if indice.hasnans:
            raise ValueError("etiquetas nulas")
        lista = [_exigir_hora_exacta(d) for d in indice.to_pydatetime()]
    else:
        lista = [_etiqueta(x) for x in valores]
    return sorted(set(lista)) if unicas else sorted(lista)


def _texto(d: datetime) -> str:
    """«AAAA-MM-DDTHH:00:00», el formato de ``valid_from``/``valid_to``."""
    return _exigir_hora_exacta(d).isoformat()


def _instante(texto: Any) -> datetime:
    """Límite de una regla: texto «AAAA-MM-DDTHH:00:00» exacto, ingenuo."""
    if not isinstance(texto, str) or not _INSTANTE.fullmatch(texto):
        raise ValueError(f"límite de regla con formato distinto de «AAAA-MM-DDTHH:00:00»: {texto!r}")
    return _exigir_hora_exacta(datetime.fromisoformat(texto))


def _instante_laxo(texto: Any) -> datetime | None:
    """Como lo lee el adaptador (``datetime.fromisoformat``); None si no se entiende o trae zona."""
    try:
        d = datetime.fromisoformat(str(texto))
    except (TypeError, ValueError):
        return None
    return None if d.tzinfo is not None else d


def _clave_mes(d: datetime) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _mes(texto: str) -> tuple[int, int]:
    m = _MES.fullmatch(texto) if isinstance(texto, str) else None
    if m is None or not 1 <= int(m.group(2)) <= len(calendario.MESES):
        raise ValueError(f"mes con formato distinto de «AAAA-MM»: {texto!r}")
    return int(m.group(1)), int(m.group(2))


def _meses_entre(desde: datetime, hasta: datetime) -> list[str]:
    """Meses de calendario «AAAA-MM» que toca el intervalo [desde, hasta]."""
    salida, (a, m) = [], (desde.year, desde.month)
    while (a, m) <= (hasta.year, hasta.month):
        salida.append(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == len(calendario.MESES) else (a, m + 1)
    return salida


def _exigir_codigo(codigo: Any) -> str:
    if not isinstance(codigo, str) or not _CODIGO.fullmatch(codigo):
        raise ValueError(f"código de estación distinto de 6 dígitos: {codigo!r}")
    return codigo


def _id_de(clase: Any) -> str:
    """Id de clase desde un texto o desde un objeto con ``id`` (tipos.ClaseH)."""
    ident = getattr(clase, "id", clase)
    if not isinstance(ident, str):
        raise ValueError(f"clase sin id de texto: {clase!r}")
    return ident


def _miembros(clase: Any) -> tuple[Hipotesis, ...]:
    """Hipótesis de una clase «F(-3)|C(Santiago)», en orden canónico. Error con Cv o miembros repetidos."""
    partes = _id_de(clase).split(SEPARADOR_CLASE)
    hipotesis = [Hipotesis.desde_id(p) for p in partes]
    if len({h.id for h in hipotesis}) != len(hipotesis):
        raise ValueError(f"clase con miembros repetidos: {clase!r}")
    if any(h.tipo not in ("F", "C") for h in hipotesis):
        raise ValueError(f"una clase con reglas vencidas (Cv) nunca recibe regla: {clase!r}")
    return tuple(sorted(hipotesis, key=lambda h: h.orden()))


def _misma_clase(a: Any, b: Any) -> bool:
    """True si a y b son la misma clase (ids en cualquier orden de miembros)."""
    try:
        return _id_canonico(_miembros(a)) == _id_canonico(_miembros(b))
    except ValueError:
        return False


def _id_canonico(miembros: Iterable[Hipotesis]) -> str:
    lista = sorted(miembros, key=lambda h: h.orden())
    if not lista:
        raise ValueError("clase vacía")
    return SEPARADOR_CLASE.join(h.id for h in lista)


def reloj_de_rachas(clases: Iterable[Any]) -> str:
    """El «reloj» de una estación en ``estaciones`` (§7.2; R-25): las clases de sus rachas, en orden,
    comparadas por intersección de miembros como en §5.3.1. Rachas consecutivas con intersección no vacía
    (separadas por un año discrepante o insuficiente, sin cambio de reloj) son un solo término, con su
    intersección; «→» va sólo donde la intersección es vacía, que es el cambio de §5.3.3 («F(-4)→F(0)»).

    Es la regla única de orquestacion (ORQ-7, con las rachas que tienen tramos) y de salidas (SAL-11, con
    las rachas aceptadas, cuando no hay política). Sin clases da «»."""
    terminos: list[frozenset[str]] = []
    for clase in clases:
        miembros = frozenset(h.id for h in _miembros(clase))
        comun = interseccion_de_clases(terminos[-1], miembros) if terminos else frozenset()
        if comun:
            terminos[-1] = comun
        else:
            terminos.append(miembros)
    return SEPARADOR_RACHAS.join(_id_canonico(Hipotesis.desde_id(h) for h in t) for t in terminos)


# ---------------------------------------------------------------------------
# Bordes civiles (§7.2) desde el Anexo A
# ---------------------------------------------------------------------------
class _Civil:
    """Intervalos de C(Z) en etiqueta: [inicio, fin] inclusivos y su desfase en minutos (sin especiales)."""

    def __init__(self, zona: str, segmentos: Sequence[tuple[datetime, datetime, int]], especiales: Sequence[datetime]):
        self.zona = zona
        self.segmentos = tuple(segmentos)
        self.inicios = [s[0] for s in self.segmentos]
        self.especiales = tuple(especiales)        # ordenadas: repetidas e inexistentes de Z

    def indice(self, etiqueta: datetime) -> int | None:
        """Índice del intervalo que contiene la etiqueta; None si es especial. Error fuera del Anexo A."""
        if not self.segmentos[0][0] <= etiqueta <= self.segmentos[-1][1]:
            raise ValueError(f"etiqueta {etiqueta.isoformat()} fuera del Anexo A ({calendario.ANIOS_ANEXO_A})")
        k = bisect.bisect_right(self.inicios, etiqueta) - 1
        return k if etiqueta <= self.segmentos[k][1] else None

    def minutos(self, etiqueta: datetime) -> int | None:
        k = self.indice(etiqueta)
        return None if k is None else self.segmentos[k][2]

    def especial_entre(self, a: datetime, b: datetime) -> list[datetime]:
        """Etiquetas especiales s con a < s < b."""
        i = bisect.bisect_right(self.especiales, a)
        salida = []
        while i < len(self.especiales) and self.especiales[i] < b:
            salida.append(self.especiales[i])
            i += 1
        return salida


_CIVILES: "weakref.WeakKeyDictionary[object, dict[str, _Civil]]" = weakref.WeakKeyDictionary()


def _construir_civil(zona: str, tablas: object) -> _Civil:
    if zona not in ZONAS:
        raise ValueError(f"zona fuera de {ZONAS}: {zona!r}")
    cambios = tablas.cambios(zona)
    if not cambios:
        raise ValueError(f"{zona} sin cambios en el Anexo A")
    inicio, fin_dominio = _dominio()
    segmentos, minutos = [], cambios[0].antes_min
    for c in cambios:
        if c.antes_min != minutos:
            raise ValueError(f"{zona}: el cambio de {c.etiqueta} no encadena con el anterior")
        u = c.u.astimezone(timezone.utc).replace(tzinfo=None)
        primera = u + timedelta(minutes=min(c.antes_min, c.despues_min))   # repetida o h0 inexistente
        siguiente = u + timedelta(minutes=max(c.antes_min, c.despues_min))
        if primera - UNA_HORA < inicio:
            raise ValueError(f"{zona}: intervalo vacío antes de {c.etiqueta}")
        segmentos.append((inicio, primera - UNA_HORA, minutos))
        inicio, minutos = siguiente, c.despues_min
    segmentos.append((inicio, fin_dominio, minutos))
    especiales: set[datetime] = set()
    for anio in range(calendario.ANIOS_ANEXO_A[0], calendario.ANIOS_ANEXO_A[1] + 1):
        repetidas, inexistentes = tablas.etiquetas_especiales(zona, anio)
        especiales |= repetidas | inexistentes
    # Las etiquetas que quedan entre dos intervalos son exactamente las especiales del Anexo A.
    huecos = set()
    for (_, fin, _), (siguiente, _, _) in zip(segmentos, segmentos[1:]):
        t = fin + UNA_HORA
        while t < siguiente:
            huecos.add(t)
            t += UNA_HORA
    if huecos != especiales:
        raise RuntimeError(f"{zona}: los bordes civiles no calzan con las etiquetas especiales del Anexo A")
    return _Civil(zona, segmentos, sorted(especiales))


def _civil(zona: str, tablas: object) -> _Civil:
    try:
        por_zona = _CIVILES.setdefault(tablas, {})
    except TypeError:                    # objeto sin referencias débiles: sin caché
        return _construir_civil(zona, tablas)
    if zona not in por_zona:
        por_zona[zona] = _construir_civil(zona, tablas)
    return por_zona[zona]


def bordes_civiles(zona: str, desde: datetime, hasta: datetime, tablas: object) -> list[tuple[datetime, datetime, int]]:
    """Intervalos [inicio, fin] (etiquetas ingenuas, inclusivos) con su desfase fijo en minutos para C(Z):
    atraso: verano hasta 1 h antes de la repetida, invierno desde 1 h después; adelanto: invierno hasta
    1 h antes de h0, verano desde 1 h después (Santiago 2019-2020: [2019-04-07T00:00, 2019-09-07T23:00]
    −240 y [2019-09-08T01:00, 2020-04-04T22:00] −180).

    Recortados a [desde, hasta]; las etiquetas repetidas e inexistentes de Z quedan fuera. ``tablas`` es un
    tablas.TablasCalendario. Error si el rango sale del Anexo A (2000-2026).
    """
    d, h = _etiqueta(desde), _etiqueta(hasta)
    civil = _civil(zona, tablas)
    primero, ultimo = civil.segmentos[0][0], civil.segmentos[-1][1]
    if d < primero or h > ultimo:
        raise ValueError(f"[{d.isoformat()}, {h.isoformat()}] sale del Anexo A ({calendario.ANIOS_ANEXO_A})")
    if d > h:
        return []
    salida = []
    for inicio, fin, minutos in civil.segmentos[max(bisect.bisect_right(civil.inicios, d) - 1, 0):]:
        if inicio > h:
            break
        a, b = max(inicio, d), min(fin, h)
        if a <= b:
            salida.append((a, b, minutos))
    return salida


def _minutos_en(miembros: Sequence[Hipotesis], etiqueta: datetime, tablas: object) -> int | None:
    """60·c de la clase en la etiqueta; None si es especial para una C(Z) de la clase.

    Error si los miembros no coinciden: una fusión sólo vale en las etiquetas con datos de su año (§2.3).
    """
    valores = set()
    for h in miembros:
        if h.tipo == "F":
            valores.add(MINUTOS_POR_HORA * h.desfase)
        else:
            m = _civil(h.zona, tablas).minutos(etiqueta)
            if m is None:
                return None
            valores.add(m)
    if len(valores) != 1:
        raise ValueError(f"los miembros de {_id_canonico(miembros)} no coinciden en {etiqueta.isoformat()}: "
                         "no es una fusión válida para esa etiqueta")
    return valores.pop()


def _minutos_en_intervalo(miembros: Sequence[Hipotesis], desde: datetime, hasta: datetime,
                          tablas: object) -> set[int] | None:
    """Desfases de los miembros sobre [desde, hasta]; None si una C(Z) no es constante allí."""
    valores = set()
    for h in miembros:
        if h.tipo == "F":
            valores.add(MINUTOS_POR_HORA * h.desfase)
            continue
        civil = _civil(h.zona, tablas)
        k = civil.indice(desde)
        if k is None or hasta > civil.segmentos[k][1]:
            return None
        valores.add(civil.segmentos[k][2])
    return valores


# ---------------------------------------------------------------------------
# Tramos
# ---------------------------------------------------------------------------
class _Previa(NamedTuple):
    """La última etiqueta con regla vista al recorrer una estación."""
    etiqueta: datetime
    ordinal: int            # año·12 + mes
    racha: int
    minutos: int
    anio: int


def _clases_por_anio(clases: Mapping[str, object]) -> dict[int, tuple[int, str, tuple[Hipotesis, ...]]]:
    por_anio = {}
    for clave, valor in clases.items():
        if not isinstance(clave, str) or not _ANIO.fullmatch(clave):
            raise ValueError(f"clave de año distinta de «AAAA»: {clave!r}")
        if not isinstance(valor, (tuple, list)) or len(valor) != 2:
            raise ValueError(f"{clave}: se espera (racha, clase), no {valor!r}")
        racha, clase = valor
        if isinstance(racha, bool) or not isinstance(racha, (int, np.integer)) or racha < 1:
            raise ValueError(f"{clave}: número de racha inválido {racha!r}")
        miembros = _miembros(clase)
        por_anio[int(clave)] = (int(racha), _id_canonico(miembros), miembros)
    anios = sorted(por_anio)
    for a, b in zip(anios, anios[1:]):
        if por_anio[b][0] < por_anio[a][0]:
            raise ValueError(f"rachas fuera de orden: {a} en la racha {por_anio[a][0]}, {b} en la {por_anio[b][0]}")
    return por_anio


def tramos(codigo: str, meses_con_regla: Mapping[str, str], clases: Mapping[str, object],
           etiquetas_por_mes: Mapping[str, Sequence[datetime]], tablas: object) -> list[Tramo]:
    """Tramos de una estación; id «<racha>.<k>» (R-25). Entre bordes civiles y etiquetas con dato manda
    la intersección (R-37).

    - ``meses_con_regla``: «AAAA-MM» → id de la clase confirmada de su año (§5.3, punto 5;
      ResultadoRachas.meses_con_regla).
    - ``clases``: «AAAA» → (racha, clase): el número de racha (1, 2, … en orden de años, como en
      ESQUEMA_RACHAS) y la clase confirmada del año (id o tipos.ClaseH). Debe coincidir con
      ``meses_con_regla`` en cada mes.
    - ``etiquetas_por_mes``: «AAAA-MM» → etiquetas con dato de los artefactos evaluados del mes.
    - ``tablas``: tablas.TablasCalendario.
    Cada etiqueta recibe el desfase de la clase de su año (todos los miembros deben coincidir en ella);
    las especiales de una C(Z) de esa clase quedan sin regla. Los cortes están en el encabezado.
    """
    _exigir_codigo(codigo)
    por_anio = _clases_por_anio(clases)
    salida: list[Tramo] = []
    contador: dict[int, int] = {}
    actual: dict | None = None
    previo: _Previa | None = None

    def cerrar(t: dict) -> Tramo:
        comunes = set.intersection(*(set(h.id for h in por_anio[a][2]) for a in t["anios"]))
        if not comunes:
            raise ValueError(f"{codigo}: tramo {t['racha']}.{t['k']} sin clase común entre sus años; "
                             "rachas mal formadas")
        return Tramo(codigo=codigo, id=f"{t['racha']}.{t['k']}", valid_from=t["desde"], valid_to=t["hasta"],
                     fixed_offset_minutes=t["minutos"], clase=_id_canonico(Hipotesis.desde_id(i) for i in comunes),
                     meses=tuple(t["meses"]))

    def especial_entre(a: datetime, anio_a: int, b: datetime, anio_b: int) -> bool:
        if b - a <= UNA_HORA:
            return False
        zonas = {h.zona for x in (anio_a, anio_b) for h in por_anio[x][2] if h.tipo == "C"}
        for zona in sorted(zonas):
            for s in _civil(zona, tablas).especial_entre(a, b):
                if s.year in por_anio and any(h.tipo == "C" and h.zona == zona for h in por_anio[s.year][2]):
                    return True
        return False

    for mes in sorted(meses_con_regla):
        anio, numero = _mes(mes)
        if anio not in por_anio:
            raise ValueError(f"{codigo}: el mes {mes} tiene regla, pero su año no está en ``clases``")
        racha, id_clase, miembros = por_anio[anio]
        if _id_canonico(_miembros(meses_con_regla[mes])) != id_clase:
            raise ValueError(f"{codigo}: {mes} con clase {meses_con_regla[mes]!r} y su año con {id_clase!r}")
        etiquetas = _etiquetas(etiquetas_por_mes.get(mes, ()), unicas=True)
        if any((L.year, L.month) != (anio, numero) for L in etiquetas):
            raise ValueError(f"{codigo}: etiquetas fuera de su mes {mes}")
        fijos = {MINUTOS_POR_HORA * h.desfase for h in miembros if h.tipo == "F"}
        civiles = [_civil(h.zona, tablas) for h in miembros if h.tipo == "C"]
        ordinal = anio * len(calendario.MESES) + numero
        for L in etiquetas:
            if civiles:
                minutos = _minutos_en(miembros, L, tablas)
                if minutos is None:
                    continue
            elif len(fijos) == 1:
                minutos = next(iter(fijos))
            else:
                raise ValueError(f"{codigo}: clase {id_clase} con desfases fijos distintos")
            if minutos not in DESFASES:
                raise ValueError(f"{codigo}: desfase {minutos} min fuera de {DESFASES} (§7.2)")
            corta = (previo is None or racha != previo.racha or minutos != previo.minutos
                     or ordinal - previo.ordinal > 1 or especial_entre(previo.etiqueta, previo.anio, L, anio))
            if corta:
                if actual is not None:
                    salida.append(cerrar(actual))
                contador[racha] = contador.get(racha, 0) + 1
                actual = {"racha": racha, "k": contador[racha], "desde": L, "hasta": L, "minutos": minutos,
                          "meses": [mes], "anios": [anio]}
            else:
                actual["hasta"] = L
                if actual["meses"][-1] != mes:
                    actual["meses"].append(mes)
                if actual["anios"][-1] != anio:
                    actual["anios"].append(anio)
            previo = _Previa(L, ordinal, racha, minutos, anio)
    if actual is not None:
        salida.append(cerrar(actual))
    return salida


def veredictos_de(tramos_por_estacion: Mapping[str, Sequence[Tramo]]) -> dict[str, dict[str, str]]:
    """código → {id de tramo: veredicto del tramo}, para ``ContextoVerificacion.veredictos``."""
    return {codigo: {t.id: t.clase for t in lista} for codigo, lista in tramos_por_estacion.items() if lista}


# ---------------------------------------------------------------------------
# Política (§7.2)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HuellasPolitica:
    protocolo_sha256: str
    commit_ap: str
    configuracion_sha256: str
    informe_sha256: str
    artefactos_evaluados_sha256: str
    adaptador_sha256: str
    python: str
    tzdata: str
    transiciones_sha256: str


def _validar_huellas(h: HuellasPolitica) -> None:
    for nombre in ("protocolo_sha256", "configuracion_sha256", "informe_sha256", "artefactos_evaluados_sha256",
                   "adaptador_sha256", "transiciones_sha256"):
        valor = getattr(h, nombre)
        if not isinstance(valor, str) or not _SHA.fullmatch(valor):
            raise ValueError(f"{nombre} no es un sha256 de 64 hexadecimales en minúscula")
    if not isinstance(h.commit_ap, str) or not _COMMIT.fullmatch(h.commit_ap):
        raise ValueError("commit_ap no es un commit de 40 hexadecimales en minúscula")
    for nombre in ("python", "tzdata"):
        if not isinstance(getattr(h, nombre), str) or not getattr(h, nombre):
            raise ValueError(f"{nombre} vacío")


def source_de(informe_ruta: str, informe_sha256: str, codigo: str, tramo_id: str, protocolo_sha256: str) -> str:
    """Cadena ``source`` que cumple PATRON_SOURCE."""
    texto = (f"reloj-dmc/v1 informe={informe_ruta} sha256={informe_sha256} estacion={codigo} "
             f"tramo={tramo_id} protocolo={protocolo_sha256}")
    m = _PATRON_SOURCE.fullmatch(texto)
    if m is None or m.groups() != (informe_ruta, informe_sha256, codigo, tramo_id, protocolo_sha256):
        raise ValueError(f"``source`` fuera del patrón de §7.2: {texto!r}")
    if not _TRAMO_ID.fullmatch(tramo_id):
        raise ValueError(f"id de tramo inválido: {tramo_id!r}")
    if not entorno.sin_datos_privados(texto):
        raise ValueError("``source`` con «/Users/» o «@»")
    return texto


def politica(tramos_por_estacion: Mapping[str, Sequence[Tramo]], estaciones: Mapping[str, dict],
             huellas: HuellasPolitica, *, post_hoc: bool = False, errata_post_c4: bool = False,
             ajuste_documental: bool = False) -> dict:
    """Nombre de §9: el JSON de §7.2 (sin escribirlo).

    ``estaciones``: código → entrada de §7.2 («veredicto», «reloj», «conjunto», «marcas» o «motivo» y
    «detalle»), hecha por la decisión. Se copia y, a cada estación con tramos, se le agrega ``tramos`` =
    {id: veredicto del tramo}. Toda estación con tramos debe estar «confirmada».
    """
    _validar_huellas(huellas)
    marcas = {"post_hoc": post_hoc, "errata_post_c4": errata_post_c4, "ajuste_documental": ajuste_documental}
    for nombre, valor in marcas.items():
        if not isinstance(valor, bool):
            raise ValueError(f"{nombre} debe ser booleano")
    salida_estaciones: dict[str, dict] = {}
    for codigo, entrada in estaciones.items():
        _exigir_codigo(codigo)
        if not isinstance(entrada, Mapping) or entrada.get("veredicto") not in _VEREDICTOS_ESTACION:
            raise ValueError(f"{codigo}: entrada de estación sin veredicto {_VEREDICTOS_ESTACION}")
        salida_estaciones[codigo] = copy.deepcopy(dict(entrada))
    reglas = []
    for codigo in sorted(tramos_por_estacion):
        lista = sorted(tramos_por_estacion[codigo], key=lambda t: t.valid_from)
        if not lista:
            continue
        _exigir_codigo(codigo)
        entrada = salida_estaciones.get(codigo)
        if entrada is None or entrada["veredicto"] != VeredictoEstacion.CONFIRMADA:
            raise ValueError(f"{codigo}: tiene tramos, pero no está «confirmada» en ``estaciones``")
        por_tramo: dict[str, str] = {}
        fin_previo: datetime | None = None
        for t in lista:
            if t.codigo != codigo:
                raise ValueError(f"tramo {t.id} de {t.codigo} bajo la estación {codigo}")
            if not isinstance(t.id, str) or not _TRAMO_ID.fullmatch(t.id) or t.id in por_tramo:
                raise ValueError(f"{codigo}: id de tramo inválido o repetido: {t.id!r}")
            minutos = t.fixed_offset_minutes
            if isinstance(minutos, bool) or not isinstance(minutos, (int, np.integer)) or minutos not in DESFASES:
                raise ValueError(f"{codigo} {t.id}: desfase {minutos!r} fuera de {DESFASES} o no entero")
            desde, hasta = _texto(t.valid_from), _texto(t.valid_to)
            if t.valid_from > t.valid_to:
                raise ValueError(f"{codigo} {t.id}: intervalo invertido")
            if fin_previo is not None and t.valid_from <= fin_previo:
                raise ValueError(f"{codigo} {t.id}: se solapa con el tramo anterior")
            fin_previo = t.valid_to
            por_tramo[t.id] = _id_canonico(_miembros(t.clase))
            reglas.append({"station_code": codigo, "valid_from": desde, "valid_to": hasta,
                           "clock": {"verified": True,
                                     "source": source_de(RUTA_INFORME_AP, huellas.informe_sha256, codigo, t.id,
                                                         huellas.protocolo_sha256),
                                     "valid_from": desde, "valid_to": hasta,
                                     "timestamp_semantics": SEMANTICA, "fixed_offset_minutes": int(minutos)}})
        previos = entrada.get(CLAVE_TRAMOS_ESTACION)
        if previos is not None and dict(previos) != por_tramo:
            raise ValueError(f"{codigo}: ``tramos`` de la entrada no coincide con los tramos")
        entrada[CLAVE_TRAMOS_ESTACION] = por_tramo
    return {"schema": ESQUEMA_POLITICA, **marcas,
            "protocolo": {"ruta": RUTA_PROTOCOLO_AP, "sha256": huellas.protocolo_sha256,
                          "commit_ap": huellas.commit_ap},
            "configuracion": {"ruta": RUTA_CONFIGURACION_AP, "sha256": huellas.configuracion_sha256},
            "informe": {"ruta": RUTA_INFORME_AP, "sha256": huellas.informe_sha256},
            "artefactos_evaluados": {"ruta": RUTA_ARTEFACTOS_AP, "sha256": huellas.artefactos_evaluados_sha256},
            "adaptador_sha256": huellas.adaptador_sha256,
            "interprete": {"python": huellas.python, "tzdata": huellas.tzdata},
            "transiciones_sha256": huellas.transiciones_sha256,
            "politicas_reloj": reglas,
            "estaciones": dict(sorted(salida_estaciones.items()))}


def escribir_politica(politica_: dict, ruta: Path) -> str:
    """Escritura atómica con entorno.json_canonico; devuelve sha256. No escribe si A5 dio alto.

    Con A5 alto la política es None (ResultadoRed.politica) y se lanza ValueError sin escribir (§5.4).
    Como ``entorno.escribir_atomico``, nunca escribe bajo /Volumes ni en los repositorios (R-49).
    """
    if politica_ is None:
        raise ValueError("A5 dio alto: no se escribe politica_reloj_dmc.json (§5.4)")
    if not isinstance(politica_, Mapping) or politica_.get("schema") != ESQUEMA_POLITICA:
        raise ValueError(f"no es una política «{ESQUEMA_POLITICA}»")
    return entorno.escribir_atomico(Path(ruta), entorno.json_canonico(politica_))


# ---------------------------------------------------------------------------
# Lectura estricta y reglas
# ---------------------------------------------------------------------------
def _pares_sin_repetir(pares: list[tuple[str, Any]]) -> dict:
    claves = [k for k, _ in pares]
    if len(set(claves)) != len(claves):
        repetidas = sorted({k for k in claves if claves.count(k) > 1})
        raise ValueError(f"claves repetidas en el JSON: {repetidas}")
    return dict(pares)


def _sin_constantes(texto: str):
    raise ValueError(f"constante no admitida en el JSON: {texto}")


def _leer_json(datos: bytes) -> Any:
    """JSON en UTF-8 sin claves repetidas ni NaN/Infinity."""
    return json.loads(datos.decode("utf-8"), object_pairs_hook=_pares_sin_repetir, parse_constant=_sin_constantes)


@dataclass
class _Regla:
    """Una entrada de ``politicas_reloj`` leída de forma laxa (para las comprobaciones 2 a 7)."""
    indice: int
    entrada: Mapping
    codigo: str | None
    clock: Mapping | None
    desde: datetime | None
    hasta: datetime | None
    tramo: str | None

    @property
    def nombre(self) -> str:
        if self.tramo:
            return f"{self.codigo} tramo {self.tramo}"
        return f"{self.codigo} regla n.º {self.indice}" if self.codigo else f"regla n.º {self.indice}"


def _regla_laxa(indice: int, entrada: Any) -> _Regla:
    if not isinstance(entrada, Mapping):
        return _Regla(indice, {}, None, None, None, None, None)
    codigo = entrada.get("station_code") if isinstance(entrada.get("station_code"), str) else None
    clock = entrada.get("clock") if isinstance(entrada.get("clock"), Mapping) else None
    desde = _instante_laxo(entrada.get("valid_from"))
    hasta = _instante_laxo(entrada.get("valid_to"))
    partes = _partes_source(clock.get("source")) if clock is not None else None
    return _Regla(indice, entrada, codigo, clock, desde, hasta, None if partes is None else partes.tramo)


class _Source(NamedTuple):
    informe: str
    sha256: str
    estacion: str
    tramo: str
    protocolo: str


def _partes_source(texto: Any) -> _Source | None:
    """Los cinco grupos de PATRON_SOURCE; None si el texto no lo cumple."""
    m = _PATRON_SOURCE.fullmatch(texto) if isinstance(texto, str) else None
    return None if m is None else _Source(*m.groups())


def _fallas_regla(entrada: Any) -> list[str]:
    """Comprobación 1 sobre una entrada de ``politicas_reloj``, sin el veredicto."""
    if not isinstance(entrada, Mapping):
        return ["la regla no es un objeto"]
    fallas = []
    if set(entrada) != set(CLAVES_TRAMO):
        fallas.append(f"claves {sorted(entrada)} distintas de {sorted(CLAVES_TRAMO)}")
    codigo = entrada.get("station_code")
    if not isinstance(codigo, str) or not _CODIGO.fullmatch(codigo):
        fallas.append(f"station_code {codigo!r} no es un código de 6 dígitos")
    desde = hasta = None
    try:
        desde, hasta = _instante(entrada.get("valid_from")), _instante(entrada.get("valid_to"))
        if desde > hasta:
            fallas.append("intervalo invertido")
    except ValueError as e:
        fallas.append(str(e))
    clock = entrada.get("clock")
    if not isinstance(clock, Mapping):
        return fallas + ["sin ``clock``"]
    if "timezone" in clock:
        fallas.append("``clock`` usa ``timezone`` (§7.2: nunca)")
    if set(clock) != set(CLAVES_CLOCK):
        fallas.append(f"``clock`` con claves {sorted(clock)}, no exactamente {sorted(CLAVES_CLOCK)}")
    if clock.get("verified") is not True:
        fallas.append("``verified`` no es true")
    if clock.get("timestamp_semantics") != SEMANTICA:
        fallas.append(f"``timestamp_semantics`` distinto de «{SEMANTICA}»")
    minutos = clock.get("fixed_offset_minutes")
    if isinstance(minutos, bool) or not isinstance(minutos, int):
        fallas.append(f"``fixed_offset_minutes`` = {minutos!r} no es un entero")
    elif minutos not in DESFASES:
        fallas.append(f"``fixed_offset_minutes`` = {minutos} fuera de {DESFASES}")
    for clave in ("valid_from", "valid_to"):
        if clock.get(clave) != entrada.get(clave):
            fallas.append(f"``clock.{clave}`` distinto del intervalo externo")
    partes = _partes_source(clock.get("source"))
    if partes is None:
        fallas.append("``source`` fuera del patrón de §7.2")
    elif partes.estacion != codigo:
        fallas.append(f"``source`` nombra la estación {partes.estacion}, no {codigo}")
    return fallas


def _fallas_veredicto(entrada: Mapping, veredicto: Any, tablas: object) -> list[str]:
    """Comprobación 1, segunda mitad: el desfase es 60·c del veredicto del tramo en todo su intervalo."""
    if veredicto is None:
        return ["sin veredicto de tramo"]
    try:
        miembros = _miembros(veredicto)
        desde, hasta = _instante(entrada.get("valid_from")), _instante(entrada.get("valid_to"))
        minutos = entrada["clock"]["fixed_offset_minutes"]
        valores = _minutos_en_intervalo(miembros, desde, hasta, tablas)
    except (KeyError, TypeError, ValueError) as e:
        return [f"veredicto {veredicto!r} no evaluable: {e}"]
    if valores is None:
        return [f"el veredicto {_id_de(veredicto)} no tiene un desfase constante en el tramo"]
    if valores != {minutos} or isinstance(minutos, bool) or not isinstance(minutos, int):
        return [f"desfase {minutos!r} ≠ 60·c del veredicto {_id_de(veredicto)} ({sorted(valores)})"]
    return []


# ---------------------------------------------------------------------------
# Comprobación 5
# ---------------------------------------------------------------------------
def es_plantilla_sospechosa(regla: Mapping, veredicto: str | None, *, tablas: object | None = None) -> bool:
    """Comprobación 5: −240 sin veredicto F(−4) ni invierno de una C(Z) continental, o source fuera de patrón.

    ``regla`` es una entrada de ``politicas_reloj`` (o su ``clock``); ``veredicto``, el del tramo (id de
    clase o None). ``tablas`` hace falta sólo si el veredicto tiene una C(Z) continental; por omisión se
    calculan con el paquete tzdata y se exigen sus huellas. Nunca lanza: lo que no se entiende es sospechoso.
    """
    try:
        clock = regla.get("clock", regla) if isinstance(regla, Mapping) else None
        if not isinstance(clock, Mapping):
            return True
        source = clock.get("source")
        if not isinstance(source, str) or _PATRON_SOURCE.fullmatch(source) is None:
            return True
        minutos = clock.get("fixed_offset_minutes")
        if isinstance(minutos, bool) or minutos != MINUTOS_PLANTILLA:
            return False
        if veredicto is None:
            return True
        miembros = _miembros(veredicto)
        if any(h.id == HIPOTESIS_PLANTILLA for h in miembros):
            return False
        continentales = [h for h in miembros if h.tipo == "C" and h.zona in ZONAS_CONTINENTALES]
        if not continentales:
            return True
        desde, hasta = _instante_laxo(clock.get("valid_from")), _instante_laxo(clock.get("valid_to"))
        if desde is None or hasta is None or desde > hasta:
            return True
        tablas = _tablas_por_omision() if tablas is None else tablas
        for h in continentales:
            civil = _civil(h.zona, tablas)
            k = civil.indice(_exigir_hora_exacta(desde))
            if k is not None and hasta <= civil.segmentos[k][1] and civil.segmentos[k][2] == MINUTOS_PLANTILLA:
                return False
        return True
    except Exception:  # noqa: BLE001 - una guardia no se cae: lo que no entiende lo rechaza
        return True


_TABLAS: list = []


def _tablas_por_omision() -> object:
    """Anexos A y A2 con el paquete tzdata, verificados contra sus huellas (una sola vez por proceso)."""
    if not _TABLAS:
        _TABLAS.append(calendario.cargar_tablas(verificar=True))
    return _TABLAS[0]


# ---------------------------------------------------------------------------
# Verificación (§7.3)
# ---------------------------------------------------------------------------
@dataclass
class ContextoVerificacion:
    adaptador: ModuleType
    adaptador_sha256: str
    preflight: ModuleType
    dmc_features: ModuleType
    artefactos_evaluados: Mapping[str, tuple[str, str]]        # sha256 → (código, «AAAA-MM»)
    etiquetas_de_artefacto: Callable[[str], Sequence[datetime]]
    veredictos: Mapping[str, Mapping[str, object]]             # código → {tramo_id: clase, …}
    meses_con_regla: Mapping[str, frozenset[str]]
    muestra_lector_real: Mapping[str, Sequence[Path]]          # código → manifiestos (comprobación 7)
    tablas: object
    # Salida de la comprobación 7: abortos por los datos (filas de no_normalizables.csv; no son A7).
    no_normalizables: list[dict] = field(default_factory=list)


class _Fallas:
    def __init__(self):
        self._por: dict[int, list[str]] = {}
        self._extra: dict[int, int] = {}

    def agregar(self, n: int, texto: str) -> None:
        lista = self._por.setdefault(n, [])
        if len(lista) < LIMITE_MENSAJES:
            lista.append(f"comprobación {n}: {texto}")
        else:
            self._extra[n] = self._extra.get(n, 0) + 1

    def lista(self) -> list[str]:
        salida = []
        for n in sorted(self._por):
            salida += self._por[n]
            if self._extra.get(n):
                salida.append(f"comprobación {n}: … y {self._extra[n]} fallas más")
        return salida


def _sha_seccion(pol: Mapping, clave: str, ruta: str, extra: Sequence[str] = ()) -> list[str]:
    seccion = pol.get(clave)
    if not isinstance(seccion, Mapping):
        return [f"«{clave}» no es un objeto"]
    fallas = []
    if set(seccion) != {"ruta", "sha256", *extra}:
        fallas.append(f"«{clave}» con claves {sorted(seccion)}")
    if seccion.get("ruta") != ruta:
        fallas.append(f"«{clave}.ruta» = {seccion.get('ruta')!r}, no {ruta!r}")
    if not isinstance(seccion.get("sha256"), str) or not _SHA.fullmatch(seccion["sha256"]):
        fallas.append(f"«{clave}.sha256» no es un sha256")
    return fallas


def _comprobacion_1(pol: Any, reglas: Sequence[_Regla], ctx: ContextoVerificacion, f: _Fallas) -> None:
    if not isinstance(pol, Mapping):
        f.agregar(C_ESQUEMA, "la política no es un objeto JSON")
        return
    if set(pol) != set(CLAVES_POLITICA):
        f.agregar(C_ESQUEMA, f"claves de primer nivel {sorted(pol)} distintas de {sorted(CLAVES_POLITICA)}")
    if pol.get("schema") != ESQUEMA_POLITICA:
        f.agregar(C_ESQUEMA, f"schema {pol.get('schema')!r} distinto de «{ESQUEMA_POLITICA}»")
    for clave in MARCAS_POLITICA:
        if not isinstance(pol.get(clave), bool):
            f.agregar(C_ESQUEMA, f"«{clave}» no es booleano")
    for texto in (_sha_seccion(pol, "protocolo", RUTA_PROTOCOLO_AP, ("commit_ap",))
                  + _sha_seccion(pol, "configuracion", RUTA_CONFIGURACION_AP)
                  + _sha_seccion(pol, "informe", RUTA_INFORME_AP)
                  + _sha_seccion(pol, "artefactos_evaluados", RUTA_ARTEFACTOS_AP)):
        f.agregar(C_ESQUEMA, texto)
    protocolo = pol.get("protocolo") if isinstance(pol.get("protocolo"), Mapping) else {}
    if not isinstance(protocolo.get("commit_ap"), str) or not _COMMIT.fullmatch(protocolo.get("commit_ap", "")):
        f.agregar(C_ESQUEMA, "«protocolo.commit_ap» no es un commit de 40 hexadecimales")
    if pol.get("adaptador_sha256") != ctx.adaptador_sha256 or ctx.adaptador_sha256 != fijados.SHA_ADAPTADOR:
        f.agregar(C_ESQUEMA, "«adaptador_sha256» no es el del adaptador fijado")
    sha_tablas = getattr(ctx.tablas, "sha256_anexo_a", None)
    if pol.get("transiciones_sha256") != calendario.SHA_ANEXO_A or sha_tablas != calendario.SHA_ANEXO_A:
        f.agregar(C_ESQUEMA, "«transiciones_sha256» no es la huella del Anexo A")
    interprete = pol.get("interprete")
    if (not isinstance(interprete, Mapping) or set(interprete) != {"python", "tzdata"}
            or not all(isinstance(v, str) and v for v in interprete.values())):
        f.agregar(C_ESQUEMA, "«interprete» debe tener exactamente «python» y «tzdata» (textos)")
    if not isinstance(pol.get("politicas_reloj"), list):
        f.agregar(C_ESQUEMA, "«politicas_reloj» no es una lista")
    estaciones = pol.get("estaciones")
    if not isinstance(estaciones, Mapping):
        f.agregar(C_ESQUEMA, "«estaciones» no es un objeto")
        estaciones = {}
    for codigo, entrada in estaciones.items():
        if not isinstance(codigo, str) or not _CODIGO.fullmatch(codigo):
            f.agregar(C_ESQUEMA, f"estación con código inválido {codigo!r}")
        if not isinstance(entrada, Mapping) or entrada.get("veredicto") not in _VEREDICTOS_ESTACION:
            f.agregar(C_ESQUEMA, f"{codigo}: veredicto de estación fuera de {_VEREDICTOS_ESTACION}")
            continue
        if entrada.get("conjunto") not in _CONJUNTOS:
            f.agregar(C_ESQUEMA, f"{codigo}: conjunto fuera de {_CONJUNTOS}")
        if entrada["veredicto"] == VeredictoEstacion.CONFIRMADA:
            reloj = entrada.get("reloj")
            try:
                for parte in str(reloj).split(SEPARADOR_RACHAS):
                    _miembros(parte)
            except ValueError:
                f.agregar(C_ESQUEMA, f"{codigo}: «reloj» {reloj!r} no es una sucesión de clases")
    informe = pol.get("informe") if isinstance(pol.get("informe"), Mapping) else {}
    vistos: set[tuple] = set()
    for r in reglas:
        for texto in _fallas_regla(r.entrada if r.entrada else None):
            f.agregar(C_ESQUEMA, f"{r.nombre}: {texto}")
        partes = _partes_source(r.clock.get("source")) if r.clock is not None else None
        if partes is None:
            continue
        informe_ruta, informe_sha, _, tramo, protocolo_sha = partes
        if informe_ruta != informe.get("ruta") or informe_sha != informe.get("sha256"):
            f.agregar(C_ESQUEMA, f"{r.nombre}: ``source`` no cita el informe de la política")
        if protocolo_sha != protocolo.get("sha256"):
            f.agregar(C_ESQUEMA, f"{r.nombre}: ``source`` no cita el protocolo de la política")
        if (r.codigo, tramo) in vistos:
            f.agregar(C_ESQUEMA, f"{r.nombre}: id de tramo repetido")
        vistos.add((r.codigo, tramo))
        veredicto = ctx.veredictos.get(r.codigo, {}).get(tramo)
        for texto in _fallas_veredicto(r.entrada, veredicto, ctx.tablas):
            f.agregar(C_ESQUEMA, f"{r.nombre}: {texto}")
        entrada_estacion = estaciones.get(r.codigo)
        publicada = entrada_estacion.get(CLAVE_TRAMOS_ESTACION) if isinstance(entrada_estacion, Mapping) else None
        if not isinstance(publicada, Mapping) or veredicto is None or not _misma_clase(publicada.get(tramo), veredicto):
            f.agregar(C_ESQUEMA, f"{r.nombre}: «estaciones.{r.codigo}.tramos» no da el veredicto del tramo")


def _artefactos_por_estacion(ctx: ContextoVerificacion) -> dict[str, list[tuple[str, str]]]:
    por: dict[str, list[tuple[str, str]]] = {}
    for sha, (codigo, mes) in ctx.artefactos_evaluados.items():
        por.setdefault(codigo, []).append((mes, sha))
    return {c: sorted(v) for c, v in por.items()}


def _comprobacion_2(pol: Any, reglas: Sequence[_Regla], ctx: ContextoVerificacion, f: _Fallas) -> None:
    estaciones = pol.get("estaciones") if isinstance(pol, Mapping) else None
    estaciones = estaciones if isinstance(estaciones, Mapping) else {}
    meses_artefacto = {c: {m for m, _ in v} for c, v in _artefactos_por_estacion(ctx).items()}
    por_estacion: dict[str, list[_Regla]] = {}
    for r in reglas:
        if r.codigo is None or r.desde is None or r.hasta is None:
            f.agregar(C_COBERTURA, f"{r.nombre}: sin estación o intervalo legible")
            continue
        por_estacion.setdefault(r.codigo, []).append(r)
    for codigo, lista in sorted(por_estacion.items()):
        entrada = estaciones.get(codigo)
        if not isinstance(entrada, Mapping) or entrada.get("veredicto") != VeredictoEstacion.CONFIRMADA:
            f.agregar(C_COBERTURA, f"{codigo}: tiene reglas, pero no está «confirmada» en «estaciones»")
        lista.sort(key=lambda r: (r.desde, r.hasta))
        for a, b in zip(lista, lista[1:]):
            if b.desde <= a.hasta:
                f.agregar(C_COBERTURA, f"{codigo}: {a.nombre} y {b.nombre} se solapan")
        con_regla = ctx.meses_con_regla.get(codigo, frozenset())
        con_artefacto = meses_artefacto.get(codigo, set())
        for r in lista:
            if r.desde > r.hasta:
                continue
            for mes in _meses_entre(r.desde, r.hasta):
                if mes not in con_artefacto:
                    f.agregar(C_COBERTURA, f"{r.nombre}: cubre {mes}, un mes sin artefacto evaluado")
                elif mes not in con_regla:
                    f.agregar(C_COBERTURA, f"{r.nombre}: cubre {mes}, que no recibe regla según §5.3")
        publicados = {r.tramo for r in lista}
        for tramo in sorted(set(ctx.veredictos.get(codigo, {})) - publicados):
            f.agregar(C_COBERTURA, f"{codigo}: el tramo {tramo} tiene veredicto, pero no regla publicada")
    for codigo in sorted(set(ctx.veredictos) - set(por_estacion)):
        if ctx.veredictos[codigo]:
            f.agregar(C_COBERTURA, f"{codigo}: tiene tramos con veredicto, pero ninguna regla publicada")


def _comprobacion_3(reglas: Sequence[_Regla], ctx: ContextoVerificacion, f: _Fallas) -> None:
    adaptador = ctx.adaptador
    por_estacion: dict[str, list[_Regla]] = {}
    for r in reglas:
        if r.codigo is None or r.clock is None:
            continue
        try:   # una regla que no pasa _confirmado en ningún caso se informa una sola vez
            adaptador._confirmado(r.clock, r.desde or _dominio()[0])
        except Exception as e:  # noqa: BLE001 - toda excepción del adaptador es A7
            f.agregar(C_CONVERSION, f"{r.nombre}: _confirmado lanza «{e}»")
            continue
        if r.desde is not None:
            por_estacion.setdefault(r.codigo, []).append(r)
    artefactos = _artefactos_por_estacion(ctx)
    for codigo, lista in sorted(por_estacion.items()):
        lista.sort(key=lambda r: r.desde)
        inicios = [r.desde for r in lista]
        vistas: dict[datetime, datetime] = {}
        for _, sha in artefactos.get(codigo, []):
            try:
                etiquetas = _etiquetas(ctx.etiquetas_de_artefacto(sha), unicas=False)
            except Exception as e:  # noqa: BLE001
                f.agregar(C_CONVERSION,
                          f"{codigo}: etiquetas del artefacto {sha[:ABREVIATURA]}… no interpretables: {e}")
                continue
            for L in etiquetas:
                k = bisect.bisect_right(inicios, L) - 1
                if k < 0:
                    continue
                r = lista[k]
                try:
                    if not adaptador._confirmado(r.clock, L):
                        continue
                    u = adaptador._utc(L, r.clock)
                except Exception as e:  # noqa: BLE001
                    f.agregar(C_CONVERSION, f"{r.nombre}: {L.isoformat()} falla en el adaptador: «{e}»")
                    continue
                if u in vistas:
                    f.agregar(C_CONVERSION, f"{codigo}: hora UTC repetida {u.isoformat()} ({vistas[u].isoformat()} y "
                                            f"{L.isoformat()})")
                else:
                    vistas[u] = L


def _comprobacion_4(reglas: Sequence[_Regla], ctx: ContextoVerificacion, f: _Fallas) -> None:
    for r in reglas:
        if r.codigo is None or r.desde is None or r.hasta is None or r.tramo is None:
            continue
        veredicto = ctx.veredictos.get(r.codigo, {}).get(r.tramo)
        if veredicto is None:
            continue
        try:
            miembros = _miembros(veredicto)
        except ValueError as e:
            f.agregar(C_ESPECIALES, f"{r.nombre}: veredicto ilegible: {e}")
            continue
        for h in miembros:
            if h.tipo != "C":
                continue
            civil = _civil(h.zona, ctx.tablas)
            dentro = civil.especial_entre(r.desde - UNA_HORA, r.hasta + UNA_HORA)
            for s in dentro:
                f.agregar(C_ESPECIALES, f"{r.nombre}: el veredicto {_id_de(veredicto)} incluye {h.id} y el tramo "
                                        f"contiene su etiqueta especial {s.isoformat()}")


def _comprobacion_5(reglas: Sequence[_Regla], ctx: ContextoVerificacion, f: _Fallas) -> None:
    for r in reglas:
        veredicto = ctx.veredictos.get(r.codigo, {}).get(r.tramo) if r.codigo and r.tramo else None
        if es_plantilla_sospechosa(r.entrada, None if veredicto is None else _id_de(veredicto), tablas=ctx.tablas):
            f.agregar(C_PLANTILLAS, f"{r.nombre}: −240 sin veredicto F(−4) ni invierno continental, o ``source`` fuera "
                                    "de patrón")


def _comprobacion_6(reglas: Sequence[_Regla], ctx: ContextoVerificacion, f: _Fallas) -> None:
    for r in reglas:
        try:
            regla = {k: r.entrada[k] for k in CLAVES_TRAMO}
            ctx.preflight.policy_check(regla, "clock", None, ctx.adaptador_sha256)
        except Exception as e:  # noqa: BLE001
            f.agregar(C_POLICY_CHECK, f"{r.nombre}: policy_check lanza «{e}»")


def _reglas_clock(reglas: Sequence[_Regla], codigo: str) -> list[dict]:
    salida = []
    for r in reglas:
        if r.codigo == codigo and all(k in r.entrada for k in CLAVES_TRAMO):
            salida.append({k: r.entrada[k] for k in CLAVES_TRAMO})
    return sorted(salida, key=lambda p: str(p["valid_from"]))


def _no_normalizable(ctx: ContextoVerificacion, codigo: str, manifiesto: Path, sha: str | None, motivo: str) -> None:
    ctx.no_normalizables.append({"codigo": codigo, "manifiesto": Path(manifiesto).name,
                                 "artefacto_sha256": sha, "motivo": motivo})


def _comprobacion_7(reglas: Sequence[_Regla], ctx: ContextoVerificacion, f: _Fallas) -> None:
    adaptador, dmc = ctx.adaptador, ctx.dmc_features
    for codigo in sorted(ctx.muestra_lector_real):
        politicas = _reglas_clock(reglas, codigo)
        utiles: list[Path] = []
        for manifiesto in ctx.muestra_lector_real[codigo]:
            try:
                payload, meta = adaptador.leer_artefacto(manifiesto)
            except Exception as e:  # noqa: BLE001 - el artefacto, no la política
                _no_normalizable(ctx, codigo, manifiesto, None, f"lectura: {e}")
                continue
            sha = meta["content_sha256"]
            if ctx.artefactos_evaluados.get(sha, (None,))[0] != codigo:
                f.agregar(C_LECTOR_REAL, f"{codigo}: el artefacto {sha[:ABREVIATURA]}… de la muestra no es un "
                                         "artefacto evaluado de la estación")
                continue
            try:
                adaptador.normalizar(payload, politica=None, content_sha256=sha)
            except Exception as e:  # noqa: BLE001 - aborta sin política: son los datos (§7.3, 7)
                _no_normalizable(ctx, codigo, manifiesto, sha, str(e))
                continue
            try:
                dmc.cargar_dmc([manifiesto], [], adapter_sha256=ctx.adaptador_sha256)
            except Exception as e:  # noqa: BLE001
                _no_normalizable(ctx, codigo, manifiesto, sha, f"cargar_dmc sin política: {e}")
                continue
            utiles.append(manifiesto)
            for p in politicas:
                desde, hasta = _instante_laxo(p["valid_from"]), _instante_laxo(p["valid_to"])
                if desde is None or hasta is None:
                    f.agregar(C_LECTOR_REAL, f"{codigo}: regla con intervalo ilegible")
                    continue
                filas = [row for row in payload["rows"]
                         if desde <= datetime.fromisoformat(str(row["timestamp_source"])) <= hasta]
                if not filas:
                    continue
                try:
                    d = adaptador.normalizar({**payload, "rows": filas}, politica={"station_code": codigo,
                                                                                  "clock": p["clock"]},
                                             content_sha256=sha)
                except Exception as e:  # noqa: BLE001 - sólo aborta con la política: A7
                    f.agregar(C_LECTOR_REAL, f"{codigo}: normalizar aborta con la regla "
                                             f"{p['valid_from']}…{p['valid_to']}: «{e}»")
                    continue
                if not bool(d["clock_verified"].all()) or bool(d["timestamp_utc"].isna().any()):
                    f.agregar(C_LECTOR_REAL,
                              f"{codigo}: normalizar deja horas sin reloj dentro de la regla {p['valid_from']}")
        if not utiles:
            continue
        try:
            largo, _ = dmc.cargar_dmc(utiles, politicas, adapter_sha256=ctx.adaptador_sha256)
        except Exception as e:  # noqa: BLE001
            f.agregar(C_LECTOR_REAL, f"{codigo}: cargar_dmc aborta con sus reglas ``clock``: «{e}»")
            continue
        con_reloj = largo[largo["clock_verified"].astype(bool)]
        if bool(con_reloj["timestamp_utc"].isna().any()):
            f.agregar(C_LECTOR_REAL, f"{codigo}: cargar_dmc deja horas confirmadas sin UTC")


def verificar_politica(ruta: Path, ctx: ContextoVerificacion) -> list[str]:
    """Nombre de §9. Las siete comprobaciones de §7.3 sobre el JSON releído; lista de fallas (A7).

    3: cada etiqueta de los artefactos evaluados dentro de cada tramo pasa por ``_confirmado`` y ``_utc``
    y ninguna estación repite una hora UTC. 7: un aborto por los datos va a no_normalizables.csv (no es A7);
    un aborto por la política sí es A7.

    Cada falla empieza con «comprobación N: ». Los abortos por los datos se agregan a
    ``ctx.no_normalizables``. No escribe nada.
    """
    f = _Fallas()
    try:
        pol = _leer_json(Path(ruta).read_bytes())
    except (OSError, ValueError) as e:
        return [f"comprobación {C_ESQUEMA}: la política no se puede releer como JSON: {e}"]
    crudas = pol.get("politicas_reloj") if isinstance(pol, Mapping) else None
    reglas = [_regla_laxa(i, e) for i, e in enumerate(crudas)] if isinstance(crudas, list) else []
    _comprobacion_1(pol, reglas, ctx, f)
    _comprobacion_2(pol, reglas, ctx, f)
    _comprobacion_3(reglas, ctx, f)
    _comprobacion_4(reglas, ctx, f)
    _comprobacion_5(reglas, ctx, f)
    _comprobacion_6(reglas, ctx, f)
    _comprobacion_7(reglas, ctx, f)
    return f.lista()


def meses_muestra_lector_real(politica_: Mapping, macrozonas: Mapping[str, str],
                              tablas: object) -> dict[str, tuple[str, ...]]:
    """Muestra fijada de la comprobación 7: código → meses «AAAA-MM» que entran.

    - Toda estación con un tramo de veredicto civil (con una C(Z), sola o fusionada), en sus meses con
      regla que contienen un cambio de hora de esas zonas (Anexo A).
    - La estación confirmada (con reglas) de menor código de cada macrozona, con todos sus meses con
      regla (R-48). ``macrozonas``: código → macrozona.
    Los meses con regla son los que tocan sus tramos. El llamador pasa sus manifiestos a
    ``ContextoVerificacion.muestra_lector_real``.
    """
    estaciones = politica_.get("estaciones", {})
    meses: dict[str, set[str]] = {}
    for entrada in politica_.get("politicas_reloj", []):
        meses.setdefault(entrada["station_code"], set()).update(
            _meses_entre(_instante(entrada["valid_from"]), _instante(entrada["valid_to"])))
    salida: dict[str, set[str]] = {}
    for codigo, del_codigo in meses.items():
        zonas = {h.zona for clase in estaciones.get(codigo, {}).get(CLAVE_TRAMOS_ESTACION, {}).values()
                 for h in _miembros(clase) if h.tipo == "C"}
        con_cambio = {_clave_mes(c.etiqueta) for z in zonas for c in tablas.cambios(z)}
        if del_codigo & con_cambio:
            salida.setdefault(codigo, set()).update(del_codigo & con_cambio)
    por_macrozona: dict[str, str] = {}
    for codigo in sorted(meses):
        if codigo not in macrozonas:
            raise KeyError(f"{codigo}: sin macrozona")
        por_macrozona.setdefault(macrozonas[codigo], codigo)
    for codigo in por_macrozona.values():
        salida.setdefault(codigo, set()).update(meses[codigo])
    return {c: tuple(sorted(v)) for c, v in sorted(salida.items())}


# ---------------------------------------------------------------------------
# Validación de uso (§7.3, §7.5)
# ---------------------------------------------------------------------------
@dataclass
class _Publicada:
    clave: tuple
    politica: Mapping
    reglas: dict[tuple[str, str], Mapping]       # (código, tramo) → entrada publicada
    artefactos: dict[str, str]                   # sha256 → código


_PUBLICADAS: dict[Path, _Publicada] = {}


def _artefactos_desde_json(obj: Any) -> dict[str, str]:
    lista = obj.get("artefactos") if isinstance(obj, Mapping) else obj
    if not isinstance(lista, list):
        raise ValueError("artefactos_evaluados no es una lista")
    salida = {}
    for item in lista:
        sha = item.get("artefacto_sha256") if isinstance(item, Mapping) else None
        codigo = item.get("codigo") if isinstance(item, Mapping) else None
        if not isinstance(sha, str) or not _SHA.fullmatch(sha) or not isinstance(codigo, str):
            raise ValueError("cada artefacto evaluado necesita «artefacto_sha256» y «codigo»")
        if salida.get(sha, codigo) != codigo:
            raise ValueError(f"el artefacto {sha[:ABREVIATURA]}… figura en dos estaciones")
        salida[sha] = codigo
    return salida


def _publicada(ruta: Path) -> _Publicada:
    """Política publicada y sus artefactos evaluados (verificados por sha256), con caché por archivo."""
    ruta = Path(ruta).resolve()
    archivo = ruta.parent / PurePosixPath(RUTA_ARTEFACTOS_AP).name
    clave = tuple((e.st_mtime_ns, e.st_size) for e in (ruta.stat(), archivo.stat()))
    previa = _PUBLICADAS.get(ruta)
    if previa is not None and previa.clave == clave:
        return previa
    pol = _leer_json(ruta.read_bytes())
    if not isinstance(pol, Mapping) or pol.get("schema") != ESQUEMA_POLITICA:
        raise ValueError(f"{ruta.name} no es una política «{ESQUEMA_POLITICA}»")
    if pol.get("transiciones_sha256") != calendario.SHA_ANEXO_A:
        raise ValueError("la política publicada no es la de la tabla de cambios del Anexo A")
    if pol.get("adaptador_sha256") != fijados.SHA_ADAPTADOR:
        raise ValueError("la política publicada no es la del adaptador fijado")
    ref = pol.get("artefactos_evaluados")
    if not isinstance(ref, Mapping) or ref.get("ruta") != RUTA_ARTEFACTOS_AP:
        raise ValueError("la política publicada no cita artefactos_evaluados")
    comprimido = archivo.read_bytes()
    if entorno.sha256_bytes(comprimido) != ref.get("sha256"):
        raise ValueError("artefactos_evaluados.json.gz no tiene la sha256 que cita la política")
    artefactos = _artefactos_desde_json(_leer_json(gzip.decompress(comprimido)))
    reglas = {}
    for entrada in pol.get("politicas_reloj", []):
        r = _regla_laxa(0, entrada)
        if r.codigo is not None and r.tramo is not None:
            reglas[(r.codigo, r.tramo)] = entrada
    publicada = _Publicada(clave, pol, reglas, artefactos)
    _PUBLICADAS[ruta] = publicada
    return publicada


def validar_regla_reloj_dmc(regla: Mapping, artefacto_sha256: str, *, politica_ruta: Path | None = None) -> None:
    """§7.3 «Validación de uso». Lanza ValueError si la regla no pasa las comprobaciones 1 y 5 o si el
    artefacto no está en artefactos_evaluados. ``politica_ruta`` por omisión: la publicada en
    AP/config/meteorologia/reloj_dmc/v1/politica_reloj_dmc.json (relativa a este archivo).

    ``artefactos_evaluados.json.gz`` se busca junto a la política y se exige su sha256. La regla debe ser,
    tal cual, la publicada para su estación y tramo (puede traer además ``coordinates``, ``measurements`` y
    ``quality``), y el artefacto, de esa estación. El veredicto de las comprobaciones 1 y 5 es
    ``estaciones[código].tramos[tramo]`` de la política publicada.
    """
    try:
        publicada = _publicada(_RUTA_POLITICA_PUBLICADA if politica_ruta is None else Path(politica_ruta))
    except OSError as e:
        raise ValueError(f"validar_regla_reloj_dmc: no se puede leer la política publicada: {e}") from e
    if not isinstance(regla, Mapping):
        raise ValueError("la regla no es un objeto")
    motivos = []
    ajenas = set(regla) - set(CLAVES_TRAMO) - set(CLAVES_UNIDAS_S6)
    if ajenas:
        motivos.append(f"claves ajenas a la regla: {sorted(ajenas)}")
    nucleo = {k: regla[k] for k in CLAVES_TRAMO if k in regla}
    motivos += [f"comprobación {C_ESQUEMA}: {t}" for t in _fallas_regla(nucleo)]
    r = _regla_laxa(0, nucleo)
    if r.codigo is None or r.tramo is None or publicada.reglas.get((r.codigo, r.tramo)) != nucleo:
        motivos.append("no es una regla publicada en la política")
    estacion = publicada.politica.get("estaciones", {}).get(r.codigo) if r.codigo else None
    veredicto = None
    if isinstance(estacion, Mapping) and estacion.get("veredicto") == VeredictoEstacion.CONFIRMADA:
        veredicto = (estacion.get(CLAVE_TRAMOS_ESTACION) or {}).get(r.tramo)
    tablas = None
    if veredicto is None:
        motivos.append(f"comprobación {C_ESQUEMA}: la política publicada no da el veredicto del tramo")
    else:
        try:
            if any(h.tipo == "C" for h in _miembros(veredicto)):
                tablas = _tablas_por_omision()
        except ValueError:
            pass
        if not any(m.startswith(f"comprobación {C_ESQUEMA}:") for m in motivos):
            motivos += [f"comprobación {C_ESQUEMA}: {t}" for t in _fallas_veredicto(nucleo, veredicto, tablas)]
    if es_plantilla_sospechosa(nucleo, veredicto, tablas=tablas):
        motivos.append(f"comprobación {C_PLANTILLAS}: −240 sin veredicto F(−4) ni invierno continental, o "
                       "``source`` fuera de patrón")
    if not isinstance(artefacto_sha256, str) or not _SHA.fullmatch(artefacto_sha256):
        motivos.append("el sha256 del artefacto no es un sha256")
    elif artefacto_sha256 not in publicada.artefactos:
        motivos.append("el artefacto no está en artefactos_evaluados: no recibe regla (§7.5)")
    elif publicada.artefactos[artefacto_sha256] != r.codigo:
        motivos.append("el artefacto es de otra estación")
    if motivos:
        raise ValueError("validar_regla_reloj_dmc: " + "; ".join(motivos))
