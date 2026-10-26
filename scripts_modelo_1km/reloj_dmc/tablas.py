"""Calendario y territorio: Anexos A y A2, Zs y P, regímenes, partes, fusiones y rivales (§2, §3.3, §3.5).

Todo es puro y depende sólo de zoneinfo (paquete tzdata), del catálogo de píxeles y del texto.
- ``transiciones_utc`` reproduce el Anexo A (huella 8ea58b78…) avanzando hora a hora en UTC.
- ``reglas_anteriores`` reproduce el Anexo A2 desde sus reglas («marzo, domingo ≥ 9» …).
- ``territorio_y_P`` aplica §3.3 y la tabla de §2.2. La latitud nunca decide en territorio incierto.
- Las partes se cortan en ETIQUETAS: en la etiqueta civil especial de cada cambio de cada zona de Zs
  (lectura R-08). Las etiquetas repetidas e inexistentes de Zs se marcan ``especial``.
- Fusiones (§2.3) por la regla general: mismas c_H(R) en todos los regímenes con datos (incluye
  C(Coyhaique) ≡ C(Santiago) hasta 2024 y C(Punta_Arenas) ≡ C(Santiago) hasta 2016; R-30).
- ``TablasCalendario.con_cortes`` (y ``con_cortes_reglas_vencidas``, para el diagnóstico de §4.1.4, ORQ-3b)
  da una copia del calendario cuyas partes se cortan además en otros intervalos de etiquetas; sólo cambia
  ``especiales_en``, y el calendario base no se toca. Es la interfaz pública desde la ola 4b.
- [Enmienda 3, E3-2, opción A′, adoptada el 2026-10-24] Anexo A3, eventos de regla vencida (§4.1.1):
  ``fechas_reglas_vencidas`` genera, desde la regla anterior a 2008 («octubre, domingo ≥ 9») y desde las
  filas de adelanto del Anexo A2, los domingos de America/Santiago con la regla vencida de cada uno (su texto,
  sin el año que la nombra). ``TablasCalendario.eventos_reglas_vencidas(zona, año)`` da sus h0 en la zona,
  cada uno con su regla, y ``anexo_a3`` la tabla por zona de 2000-2026. ``serializar_anexo_a3`` es la única
  serialización (por zona, con h0 y regla) y su sha256 es ``SHA_ANEXO_A3``, que ``verificar_tablas`` exige
  como las del A y el A2 y que red.a2 informa en el control A2.
Depende de: entorno (carpeta de la base del sistema), tipos, constantes (cortes de §3.3) y zoneinfo.
``MACROZONA_REGION`` llega por argumento (lo copia fijados.macrozona_region); así este módulo no lee
código ajeno.

Lecturas propias de este módulo (van al addendum de C1 junto con las del diseño):
- Las etiquetas especiales no pertenecen a ninguna parte ni a ningún régimen: ``anotar_partes`` les
  pone ``parte`` y ``regimen`` nulos y ``especial = True``. ``ParteDef.desde``/``hasta`` son la primera y
  la última etiqueta horaria del tramo entre dos etiquetas especiales (o bordes de mes).
- Un año-régimen es una tupla de desfases de Zs que existe en UTC (en algún instante del año todas las
  zonas la tienen a la vez). Una parte cuya tupla no existe en UTC es una astilla (R-08): ``regimen`` None.
- «Base del sistema» (§8.A.2) es la del sistema operativo, ``/usr/share/zoneinfo``, leída archivo por
  archivo con ``ZoneInfo.from_file`` para que no haya recaída silenciosa en el paquete tzdata.
- Cv(Z, y) usa la PRIMERA regla de la fila del Anexo A2. En 2012 hay dos («marzo, domingo ≥ 9; y la
  de 2011, mayo, domingo ≥ 2»): la segunda sólo queda como placebo (``placebos_a2``). Parte de R-09.
"""
from __future__ import annotations

import bisect
import calendar
import copy
import hashlib
import json
import math
import re
import zoneinfo
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from reloj_dmc import constantes, entorno
from reloj_dmc.tipos import (ESQUEMA_ANOTACION, Cambio, ClaseH, FilaA2, Hipotesis, InfoEstacion, ParteDef,
                             Regimen, Territorio)

SHA_ANEXO_A = "8ea58b788ad6d8e236c5dae5f749a7fc7fe837cb2e34cb947e9904cf8f345a33"
SHA_ANEXO_A2 = "b0727bee798f651e87e811340b2c384a138bd676e6224c23efc7c1838551a46e"
CAMBIOS_POR_ZONA_ANEXO_A = {"America/Santiago": 52, "America/Punta_Arenas": 32,
                            "America/Coyhaique": 48, "Pacific/Easter": 52}
ANIOS_ANEXO_A = (2000, 2026)

# Anexo A, «Cálculo»: zonas en el orden de c0/anexo_a_cambios_hora.py y recorrido hora a hora en UTC.
ZONAS_ANEXO_A = ("America/Santiago", "America/Punta_Arenas", "America/Coyhaique", "Pacific/Easter")
INICIO_UTC = datetime(ANIOS_ANEXO_A[0], 1, 1, tzinfo=timezone.utc)
FIN_UTC = datetime(ANIOS_ANEXO_A[1] + 1, 1, 1, tzinfo=timezone.utc)   # «hasta antes de 2027-01-01T00:00Z»
FORMATO_UTC = "%Y-%m-%dT%H:%MZ"
UNA_HORA = timedelta(hours=1)

BASE_TZDATA = "tzdata"          # paquete tzdata del intérprete (reset_tzpath(to=[]))
BASE_SISTEMA = "sistema"        # base del sistema operativo
CARPETA_BASE_SISTEMA = Path(entorno.BASE_ZONAS_SISTEMA)   # /usr/share/zoneinfo

# Anexo A2: la zona cuyas fechas reales da la tabla («Las horas son las del Anexo A: … la 23:00 del sábado»).
ZONA_REFERENCIA_A2 = "America/Santiago"
# Las reglas del Anexo A2, en el orden del texto. Las fechas se CALCULAN desde estas reglas
# (``fechas_de_regla``) y desde el Anexo A (fecha real); no se copian.
REGLAS_A2: tuple[tuple[int, str, str], ...] = (
    (2008, "atraso", "marzo, domingo ≥ 9"),
    (2010, "atraso", "marzo, domingo ≥ 9"),
    (2011, "atraso", "marzo, domingo ≥ 9"),
    (2011, "adelanto", "octubre, domingo ≥ 9"),
    (2012, "atraso", "marzo, domingo ≥ 9; y la de 2011, mayo, domingo ≥ 2"),
    (2012, "adelanto", "octubre, domingo ≥ 9; y la de 2011, agosto, domingo ≥ 16"),
    (2015, "sin atraso", "abril, domingo ≥ 23"),
    (2015, "sin adelanto", "septiembre, domingo ≥ 2"),
    (2016, "atraso", "abril, domingo ≥ 23"),
    (2016, "adelanto", "septiembre, domingo ≥ 2"),
    (2019, "atraso", "mayo, domingo ≥ 9"),
    (2019, "adelanto", "agosto, domingo ≥ 9"),
    (2022, "adelanto", "septiembre, domingo ≥ 2"),
)
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")
_PATRON_REGLA = re.compile(r"(?:y la de (?P<desde>\d{4}), )?(?P<mes>[a-z]+), domingo ≥ (?P<dia>\d{1,2})")

# §3.3: «la región es `cod_comuna // 1000` del píxel». Constante del cuerpo del texto (R-17).
DIVISOR_REGION = int(constantes.POR_NOMBRE["REGION_DIVISOR"].valor)
COLUMNAS_CELDA = ("pixel_id", "cell_west", "cell_east", "cell_south", "cell_north", "cod_comuna")

# §2.2: territorio → (Zs, P). Los ids de P son los de tipos.Hipotesis.
ZS_Y_P: Mapping[Territorio, tuple[tuple[str, ...], tuple[str, ...]]] = {
    Territorio.CONTINENTAL: (("America/Santiago",), ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")),
    Territorio.JUAN_FERNANDEZ_DESVENTURADAS: (("America/Santiago",), ("F(0)", "F(-3)", "F(-4)", "C(Santiago)")),
    Territorio.AYSEN: (("America/Coyhaique", "America/Santiago"),
                       ("F(0)", "F(-3)", "F(-4)", "C(Coyhaique)", "C(Santiago)")),
    Territorio.MAGALLANES: (("America/Punta_Arenas", "America/Santiago"),
                            ("F(0)", "F(-3)", "F(-4)", "C(Punta_Arenas)", "C(Santiago)")),
    Territorio.ANTARTICA: (("America/Punta_Arenas", "America/Santiago"),
                           ("F(0)", "F(-3)", "F(-4)", "C(Punta_Arenas)", "C(Santiago)")),
    Territorio.PASCUA_SALA_Y_GOMEZ: (("Pacific/Easter", "America/Santiago"),
                                     ("F(0)", "F(-3)", "F(-4)", "F(-5)", "F(-6)", "C(Pacific/Easter)", "C(Santiago)")),
    Territorio.INCIERTO: (("America/Santiago", "America/Coyhaique", "America/Punta_Arenas"),
                          ("F(0)", "F(-3)", "F(-4)", "C(Santiago)", "C(Coyhaique)", "C(Punta_Arenas)")),
}
MACROZONA_INSULAR = "insular"
MACROZONA_INCIERTA = "sin_region"
TERRITORIOS_INSULARES = (Territorio.PASCUA_SALA_Y_GOMEZ, Territorio.JUAN_FERNANDEZ_DESVENTURADAS)


class ErrorTablas(RuntimeError):
    """La tabla calculada no reproduce la huella anclada (consecuencia: A2, §5.4)."""


def _c(nombre: str):
    """Valor de una constante del cuerpo del texto (constantes.py, con su fragmento literal)."""
    return constantes.POR_NOMBRE[nombre].valor


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _horas(minutos: int) -> int:
    if minutos % 60:
        raise ValueError(f"desfase de {minutos} min no es un número entero de horas")
    return minutos // 60


def _ingenua(etiqueta) -> datetime:
    """datetime ingenuo desde datetime, pd.Timestamp o numpy.datetime64; error si trae zona."""
    t = pd.Timestamp(etiqueta)
    if t is pd.NaT or pd.isna(t):
        raise ValueError("etiqueta nula")
    if t.tzinfo is not None:
        raise ValueError(f"la etiqueta debe ser ingenua (hora de pared): {etiqueta!r}")
    return t.to_pydatetime()


def _verificar_anio(anio: int) -> None:
    if not ANIOS_ANEXO_A[0] <= anio <= ANIOS_ANEXO_A[1]:
        raise ValueError(f"año {anio} fuera del Anexo A ({ANIOS_ANEXO_A[0]}-{ANIOS_ANEXO_A[1]})")


def _domingo_de(fecha: date) -> date:
    """El mismo día si es domingo; si no, el domingo siguiente."""
    return fecha + timedelta(days=(calendar.SUNDAY - fecha.weekday()) % 7)


# --- Anexo A ---------------------------------------------------------------
def _zonas_de_base(base: str) -> dict[str, zoneinfo.ZoneInfo]:
    """Las cuatro zonas desde el paquete tzdata, desde la base del sistema o desde una carpeta absoluta."""
    if base == BASE_TZDATA:
        zoneinfo.reset_tzpath(to=[])          # §8.A.2: sólo el paquete tzdata del intérprete
        zoneinfo.ZoneInfo.clear_cache()
        if zoneinfo.TZPATH:
            raise ErrorTablas(f"TZPATH no quedó vacío: {zoneinfo.TZPATH}")
        return {nombre: zoneinfo.ZoneInfo(nombre) for nombre in ZONAS_ANEXO_A}
    carpeta = CARPETA_BASE_SISTEMA if base == BASE_SISTEMA else Path(base)
    if not carpeta.is_absolute():
        raise ValueError(f"base desconocida: {base!r} (use «tzdata», «sistema» o una carpeta absoluta)")
    zonas = {}
    for nombre in ZONAS_ANEXO_A:
        ruta = carpeta / nombre
        if not ruta.is_file():
            raise ErrorTablas(f"la base {carpeta} no trae {nombre}")
        with ruta.open("rb") as f:          # sin TZPATH: no puede recaer en el paquete tzdata
            zonas[nombre] = zoneinfo.ZoneInfo.from_file(f, key=nombre)
    return zonas


def version_de_base(base: str = BASE_TZDATA) -> str:
    """Versión IANA de la base («2026c»), para el informe y los mensajes de prueba."""
    if base == BASE_TZDATA:
        import tzdata
        return str(tzdata.IANA_VERSION)
    carpeta = CARPETA_BASE_SISTEMA if base == BASE_SISTEMA else Path(base)
    version = carpeta / "+VERSION"
    if version.is_file():
        return version.read_text(encoding="utf-8").strip()
    zi = carpeta / "tzdata.zi"
    if zi.is_file():
        with zi.open(encoding="utf-8") as f:
            primera = f.readline().strip()
        if primera.startswith("# version"):
            return primera.split()[-1]
    return "desconocida"


def transiciones_utc(base: str = BASE_TZDATA) -> dict[str, list[list]]:
    """{zona: [["AAAA-MM-DDTHH:MMZ", minutos antes, minutos después], …]} para las cuatro zonas.

    Algoritmo de c0/anexo_a_cambios_hora.py: hora a hora en UTC desde 2000-01-01T00:00Z hasta antes de
    2027-01-01T00:00Z; registra la primera u con desfase distinto del de u − 1 h.
    ``base``: «tzdata» (paquete, con reset_tzpath(to=[]) y clear_cache), «sistema» (/usr/share/zoneinfo)
    o una carpeta absoluta de archivos TZif. Las dos últimas no tocan TZPATH.
    """
    zonas = _zonas_de_base(base)
    salida: dict[str, list[list]] = {}
    for nombre in ZONAS_ANEXO_A:
        z = zonas[nombre]
        u, cambios = INICIO_UTC, []
        previo = (u - UNA_HORA).astimezone(z).utcoffset()
        while u < FIN_UTC:
            actual = u.astimezone(z).utcoffset()
            if actual != previo:
                cambios.append([u.strftime(FORMATO_UTC), int(previo.total_seconds() // 60),
                                int(actual.total_seconds() // 60)])
            previo, u = actual, u + UNA_HORA
        salida[nombre] = cambios
    return salida


def serializar_anexo_a(tabla: Mapping[str, list[list]]) -> bytes:
    """Claves ordenadas, separadores «,» y «:», UTF-8, sin salto de línea final."""
    return json.dumps(dict(tabla), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _cambios_desde_filas(zona: str, filas: Sequence[Sequence]) -> tuple[Cambio, ...]:
    """Filas del Anexo A de una zona → Cambio con sus etiquetas especiales en hora de pared de la zona."""
    cambios = []
    for texto, antes, despues in filas:
        antes, despues = int(antes), int(despues)
        if antes == despues:
            raise ValueError(f"{zona} {texto}: cambio sin cambio de desfase")
        if cambios and cambios[-1].despues_min != antes:
            raise ValueError(f"{zona} {texto}: el desfase anterior no encadena con el cambio previo")
        u = datetime.strptime(texto, FORMATO_UTC).replace(tzinfo=timezone.utc)
        if cambios and u <= cambios[-1].u:
            raise ValueError(f"{zona} {texto}: cambios fuera de orden")
        cambios.append(_cambio(zona, u, antes, despues))
    return tuple(cambios)


def _cambio(zona: str, u: datetime, antes: int, despues: int) -> Cambio:
    """Adelanto: ``etiqueta`` es h0, la primera inexistente; atraso: la primera repetida (ingenuas)."""
    etiqueta = u.replace(tzinfo=None) + timedelta(minutes=min(antes, despues))
    return Cambio(zona=zona, u=u, antes_min=antes, despues_min=despues,
                  tipo="adelanto" if despues > antes else "atraso", etiqueta=etiqueta,
                  fecha_D=etiqueta.date(), domingo=_domingo_de(etiqueta.date()))


def intervalo_especial(c: Cambio) -> tuple[datetime, datetime]:
    """[desde, hasta) de las etiquetas especiales del cambio, en hora de pared de su zona."""
    u = c.u.replace(tzinfo=None)
    return (u + timedelta(minutes=min(c.antes_min, c.despues_min)),
            u + timedelta(minutes=max(c.antes_min, c.despues_min)))


_intervalo = intervalo_especial


# --- Anexo A2 ----------------------------------------------------------------
def fechas_de_regla(anio: int, cambio: str, regla: str) -> tuple[date, ...]:
    """Fechas que da cada regla «<mes>, domingo ≥ d» del texto, en su orden.

    Atraso (también «sin atraso»): el sábado anterior a ese domingo, día de la etiqueta repetida.
    Adelanto: el domingo. «y la de AAAA, …» sólo nombra de qué año es la regla; la fecha es de ``anio``.
    """
    fechas = []
    for trozo in regla.split("; "):
        m = _PATRON_REGLA.fullmatch(trozo)
        if m is None or m.group("mes") not in MESES:
            raise ValueError(f"regla no interpretable: {trozo!r}")
        domingo = _domingo_de(date(anio, MESES.index(m.group("mes")) + 1, int(m.group("dia"))))
        fechas.append(domingo - timedelta(days=1) if "atraso" in cambio else domingo)
    return tuple(fechas)


def _tipo_de_fila(cambio: str) -> str:
    if cambio in ("atraso", "sin atraso"):
        return "atraso"
    if cambio in ("adelanto", "sin adelanto"):
        return "adelanto"
    raise ValueError(f"cambio desconocido en el Anexo A2: {cambio!r}")


def reglas_anteriores(anexo_a: Mapping[str, list[list]] | None = None) -> list[FilaA2]:
    """Anexo A2 calculado desde sus reglas (domingo ≥ d del mes; atraso → sábado anterior).

    La fecha real sale del Anexo A (``anexo_a``; si falta, se calcula con el paquete tzdata): el sábado de
    la etiqueta repetida en el atraso y el domingo de h0 en el adelanto, en America/Santiago.
    """
    tabla = transiciones_utc(BASE_TZDATA) if anexo_a is None else anexo_a
    referencia = _cambios_desde_filas(ZONA_REFERENCIA_A2, tabla[ZONA_REFERENCIA_A2])
    filas = []
    for anio, cambio, regla in REGLAS_A2:
        tipo = _tipo_de_fila(cambio)
        reales = [c for c in referencia if c.tipo == tipo and c.etiqueta.year == anio]
        if cambio.startswith("sin "):
            if reales:
                raise ErrorTablas(f"Anexo A2 dice «{cambio}» en {anio}, pero el Anexo A trae {len(reales)}")
            fecha_real = None
        else:
            if len(reales) != 1:
                raise ErrorTablas(f"Anexo A2 {anio} {cambio}: el Anexo A trae {len(reales)} cambios de ese tipo")
            fecha_real = reales[0].fecha_D
        filas.append(FilaA2(anio=anio, cambio=cambio, fecha_real=fecha_real, regla=regla,
                            fechas_placebo=fechas_de_regla(anio, cambio, regla)))
    return filas


def serializar_anexo_a2(filas: Sequence[FilaA2]) -> bytes:
    """[[año, cambio, fecha_real|null, regla, [placebos]], …] con separadores «,» y «:», ensure_ascii=False."""
    lista = [[f.anio, f.cambio, None if f.fecha_real is None else f.fecha_real.isoformat(), f.regla,
              [p.isoformat() for p in f.fechas_placebo]] for f in filas]
    return json.dumps(lista, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


# --- Anexo A3: eventos de regla vencida (Enmienda 3, E3-2, opción A′) -------------------------------------
# §4.1.1 (Enmienda 3): «el adelanto de la regla anterior a 2008 (octubre, domingo ≥ 9; en Pascua, la 22:00 del
# sábado anterior) en cada año en que no coincide con el Anexo A, y las fechas de adelanto del Anexo A2», cada
# evento con la regla vencida que lo da, nombrada por su texto. «La tabla de esas fechas se genera desde la
# regla y desde el Anexo A2, como el A2, y su huella va al anclaje.» La regla anterior a 2008 es la de la fila
# 2011/adelanto del Anexo A2 (y la de los adelantos 2000-2010 del Anexo A).
REGLA_ANTERIOR_2008_ADELANTO = "octubre, domingo ≥ 9"
ORIGEN_REGLA_ANTERIOR_2008 = "regla anterior a 2008"
ORIGEN_ANEXO_A2 = "Anexo A2"
FORMATO_H0 = "%Y-%m-%dT%H:%M"     # h0 del Anexo A3, en hora de pared de su zona
# Lectura de implementación (Anexo A3; va al addendum): por zona (las cuatro del Anexo A) y año (2000-2026),
# h0 es el adelanto real de la zona movido en días enteros a cada domingo de la tabla (el del año o, si no
# hubo, el último anterior: 2015, Punta_Arenas desde 2017, Coyhaique desde 2025), o el placebo del A2 de esa
# zona (``placebos_a2``: ninguno si la zona no tuvo ese cambio, como Punta_Arenas en 2019 y 2022), y sólo si
# existe bajo la vigente. 21 eventos en Santiago, Coyhaique y Pascua y 19 en Punta_Arenas, en 4 reglas:
# «octubre, domingo ≥ 9» (de 2011 a 2026; 2011 y 2012 también son del A2), «agosto, domingo ≥ 16»
# (2012-08-19), «septiembre, domingo ≥ 2» (2015-09-06, 2016-09-04 y 2022-09-04) y «agosto, domingo ≥ 9»
# (2019-08-11). Ninguno en 2008-2010. Calculada con tzdata 2026c el 2026-10-24; va al anclaje con la enmienda.
SHA_ANEXO_A3 = "d7cd33e1363edb17f3fe5df9d59cf978bf6b522f218f9be82b59e73bb29ed092"


def _regla_normal(trozo: str) -> str:
    """«y la de 2011, agosto, domingo ≥ 16» → «agosto, domingo ≥ 16»: la regla, sin el año que la nombra."""
    m = _PATRON_REGLA.fullmatch(trozo)
    if m is None:
        raise ValueError(f"regla no interpretable: {trozo!r}")
    return f"{m.group('mes')}, domingo ≥ {int(m.group('dia'))}"


def fechas_reglas_vencidas(anexo_a: Mapping[str, list[list]] | None = None, anexo_a2: Sequence[FilaA2] | None = None
                           ) -> list[tuple[date, str, tuple[str, ...]]]:
    """Domingos de los eventos de regla vencida (America/Santiago, como el Anexo A2), con la regla vencida que
    da cada uno (su texto, sin el año que la nombra) y sus orígenes.

    - Regla anterior a 2008: en cada año del Anexo A (2000-2026), el domingo de «octubre, domingo ≥ 9»
      si no es el domingo de un adelanto real de America/Santiago («no coincide con el Anexo A»).
    - Anexo A2: cada fecha placebo de sus filas de adelanto («adelanto» y «sin adelanto»), con la regla de
      su trozo («…; y la de 2011, agosto, domingo ≥ 16» da «agosto, domingo ≥ 16»).
    Una fecha que sale de los dos lleva las dos procedencias (2011-10-09 y 2012-10-14) y una sola regla: dos
    reglas distintas para un mismo domingo darían ErrorTablas, porque el patrón va por regla. Orden por fecha.
    ``anexo_a`` y ``anexo_a2`` se calculan con el paquete tzdata si faltan.
    """
    tabla = transiciones_utc(BASE_TZDATA) if anexo_a is None else anexo_a
    filas_a2 = reglas_anteriores(tabla) if anexo_a2 is None else anexo_a2
    referencia = _cambios_desde_filas(ZONA_REFERENCIA_A2, tabla[ZONA_REFERENCIA_A2])
    reales = {c.domingo for c in referencia if c.tipo == "adelanto"}
    reglas: dict[date, str] = {}
    origenes: dict[date, list[str]] = {}

    def agregar(fecha: date, regla: str, origen: str) -> None:
        if reglas.setdefault(fecha, regla) != regla:
            raise ErrorTablas(f"Anexo A3: {fecha} con dos reglas vencidas («{reglas[fecha]}» y «{regla}»)")
        if origen not in origenes.setdefault(fecha, []):
            origenes[fecha].append(origen)

    for anio in range(ANIOS_ANEXO_A[0], ANIOS_ANEXO_A[1] + 1):
        for fecha in fechas_de_regla(anio, "adelanto", REGLA_ANTERIOR_2008_ADELANTO):
            if fecha not in reales:
                agregar(fecha, _regla_normal(REGLA_ANTERIOR_2008_ADELANTO), ORIGEN_REGLA_ANTERIOR_2008)
    for fila in filas_a2:
        if _tipo_de_fila(fila.cambio) != "adelanto":
            continue
        trozos = fila.regla.split("; ")
        if len(trozos) != len(fila.fechas_placebo):
            raise ErrorTablas(f"Anexo A2 {fila.anio}: {len(trozos)} reglas y {len(fila.fechas_placebo)} fechas")
        for trozo, fecha in zip(trozos, fila.fechas_placebo):
            if fecha in reales:
                raise ErrorTablas(f"Anexo A2 {fila.anio}: la fecha placebo {fecha} es un adelanto real")
            agregar(fecha, _regla_normal(trozo), ORIGEN_ANEXO_A2)
    return [(f, reglas[f], tuple(origenes[f])) for f in sorted(reglas)]


def serializar_anexo_a3(tabla: Mapping[str, Sequence[tuple[datetime, str]]]) -> bytes:
    """Anexo A3, la única serialización: {zona: [[h0 «AAAA-MM-DDTHH:MM», regla], …]} con las zonas como claves
    ordenadas, los eventos de cada zona en orden UTC, separadores «,» y «:», ensure_ascii=False, UTF-8 y sin
    salto final. ``tabla`` es la de ``anexo_a3``.

    Cómo se compara con otro archivo (p. ej. anexo_a3_reglas_vencidas.json, generado aparte): sus bytes,
    sin un salto de línea final si lo trae, deben ser idénticos a éstos (misma sha256); si el archivo se
    escribió con otro espaciado, ``json.loads`` de ambos debe dar el mismo objeto."""
    lista = {z: [[h0.strftime(FORMATO_H0), regla] for h0, regla in eventos] for z, eventos in tabla.items()}
    return json.dumps(lista, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


# --- Desfases en hora de pared y en UTC -----------------------------------------
class _Pared:
    """Cambios de una zona como intervalos de etiquetas especiales ordenados (consultas por bisección)."""

    def __init__(self, cambios: Sequence[Cambio]):
        if not cambios:
            raise ValueError("una zona sin cambios no tiene desfase inicial en el Anexo A")
        self.cambios = tuple(cambios)
        self.desde = [_intervalo(c)[0] for c in cambios]
        self.hasta = [_intervalo(c)[1] for c in cambios]
        self.u = [c.u.replace(tzinfo=None) for c in cambios]
        for k in range(1, len(cambios)):
            if self.desde[k] < self.hasta[k - 1]:
                raise ValueError(f"{cambios[k].zona}: etiquetas especiales solapadas en {cambios[k].etiqueta}")
            if cambios[k].antes_min != cambios[k - 1].despues_min:
                raise ValueError(f"{cambios[k].zona}: cambios que no encadenan en {cambios[k].etiqueta}")

    def en_etiqueta(self, etiqueta: datetime) -> int | None:
        """Desfase (h) de la zona en la etiqueta; None si es repetida o inexistente."""
        k = bisect.bisect_right(self.hasta, etiqueta)
        if k == len(self.cambios):
            return _horas(self.cambios[-1].despues_min)
        if etiqueta >= self.desde[k]:
            return None
        return _horas(self.cambios[k].antes_min)

    def en_utc(self, u: datetime) -> int:
        """Desfase (h) de la zona en el instante UTC ``u`` (ingenuo)."""
        k = bisect.bisect_right(self.u, u)
        return _horas(self.cambios[0].antes_min if k == 0 else self.cambios[k - 1].despues_min)

    def especiales_en(self, desde: datetime, hasta: datetime) -> list[tuple[datetime, datetime]]:
        """Intervalos [desde, hasta) de etiquetas especiales que tocan [desde, hasta)."""
        k = bisect.bisect_right(self.hasta, desde)
        salida = []
        while k < len(self.cambios) and self.desde[k] < hasta:
            salida.append((self.desde[k], self.hasta[k]))
            k += 1
        return salida


class _ParedConCortes(_Pared):
    """Pared de una zona con intervalos extra de etiquetas especiales que sólo cortan partes
    (``TablasCalendario.con_cortes``). Cambios, desfases e instantes son los de la pared base: sólo
    ``especiales_en`` suma los cortes."""

    def __init__(self, base: _Pared, cortes: Sequence[tuple[datetime, datetime]]):
        self.cambios, self.desde, self.hasta, self.u = base.cambios, base.desde, base.hasta, base.u
        self._base = base
        self.cortes = tuple(sorted(cortes))

    def especiales_en(self, desde: datetime, hasta: datetime) -> list[tuple[datetime, datetime]]:
        salida = set(self._base.especiales_en(desde, hasta))
        salida.update((a, b) for a, b in self.cortes if a < hasta and b > desde)
        return sorted(salida)


class TablasCalendario:
    """Anexos A y A2 verificados contra sus huellas; consultas por zona y año.

    El constructor no verifica las huellas (lo hace ``cargar_tablas``); deja calculadas
    ``sha256_anexo_a`` y ``sha256_anexo_a2`` para A2 (red.a2) y el informe.
    """

    def __init__(self, anexo_a: Mapping[str, list[list]], anexo_a2: Sequence[FilaA2]):
        self.anexo_a = {z: tuple(tuple(f) for f in filas) for z, filas in anexo_a.items()}
        self.anexo_a2 = tuple(anexo_a2)
        self.sha256_anexo_a = _sha256(serializar_anexo_a(anexo_a))
        self.sha256_anexo_a2 = _sha256(serializar_anexo_a2(self.anexo_a2))
        self._cambios = {z: _cambios_desde_filas(z, filas) for z, filas in self.anexo_a.items()}
        self._pared = {z: _Pared(c) for z, c in self._cambios.items()}
        self._regimenes: dict[tuple, tuple[Regimen, ...]] = {}
        self._vencidas: dict[tuple, _Pared] = {}
        self._fechas_rv: list[tuple[date, str, tuple[str, ...]]] | None = None   # Anexo A3 (Enmienda 3)

    @property
    def reglas_vencidas(self) -> list[tuple[date, str, tuple[str, ...]]]:
        """Domingos de los eventos de regla vencida (``fechas_reglas_vencidas``), calculados una vez desde el
        Anexo A y el Anexo A2 de este calendario."""
        if self._fechas_rv is None:
            self._fechas_rv = fechas_reglas_vencidas(self.anexo_a, self.anexo_a2)
        return self._fechas_rv

    @property
    def sha256_anexo_a3(self) -> str:
        """sha256 de ``serializar_anexo_a3(anexo_a3(self))`` (control A2, §5.4, con la Enmienda 3)."""
        return _sha256(serializar_anexo_a3(anexo_a3(self)))

    @property
    def zonas(self) -> tuple[str, ...]:
        return tuple(self._cambios)

    def _de(self, zona: str) -> _Pared:
        if zona not in self._pared:
            raise KeyError(f"zona sin Anexo A: {zona!r}")
        return self._pared[zona]

    def cambios(self, zona: str, anio: int | None = None) -> tuple[Cambio, ...]:
        """Cambios de la zona (todos, o los de un año de etiqueta)."""
        cambios = self._de(zona).cambios
        return cambios if anio is None else tuple(c for c in cambios if c.etiqueta.year == anio)

    def etiquetas_especiales(self, zona: str, anio: int) -> tuple[frozenset[datetime], frozenset[datetime]]:
        """(repetidas, inexistentes) de la zona en el año, en hora de pared de esa zona."""
        repetidas, inexistentes = set(), set()
        for c in self.cambios(zona, anio):
            desde, hasta = _intervalo(c)
            destino = inexistentes if c.tipo == "adelanto" else repetidas
            while desde < hasta:
                destino.add(desde)
                desde += UNA_HORA
        return frozenset(repetidas), frozenset(inexistentes)

    def desfase_civil(self, zona: str, etiqueta) -> int | None:
        """c de C(zona) en la etiqueta (h); None si la etiqueta es repetida o inexistente en la zona."""
        L = _ingenua(etiqueta)
        _verificar_anio(L.year)
        return self._de(zona).en_etiqueta(L)

    def desfase_civil_utc(self, zona: str, u) -> int:
        """Desfase (h) de la zona en el instante UTC ``u`` (consciente en UTC o ingenuo en UTC)."""
        t = pd.Timestamp(u)
        if t.tzinfo is not None:
            t = t.tz_convert("UTC").tz_localize(None)
        return self._de(zona).en_utc(t.to_pydatetime())

    def _filas_a2(self, anio: int) -> tuple[FilaA2, ...]:
        filas = tuple(f for f in self.anexo_a2 if f.anio == anio)
        if not filas:
            raise ValueError(f"Cv sólo existe en los años del Anexo A2; {anio} no está (§4.1.4)")
        return filas

    def _cambio_desplazado(self, zona: str, fila: FilaA2, fecha_placebo: date) -> Cambio | None:
        """El cambio que la regla de ``fila`` habría dado en la zona en ``fecha_placebo``.

        Se desplaza, en días enteros, el cambio real de ese tipo y año (mismos instante UTC del día y
        desfases: «las horas son las del Anexo A»). En una fila «sin …» se desplaza el último cambio real
        de ese tipo de un año anterior. None si la zona no tuvo ese cambio (p. ej. Punta_Arenas en 2019).
        """
        tipo = _tipo_de_fila(fila.cambio)
        delmismo = [c for c in self.cambios(zona, fila.anio) if c.tipo == tipo]
        if fila.fecha_real is None:
            if delmismo:
                raise ErrorTablas(f"{zona} {fila.anio}: Anexo A2 dice «{fila.cambio}», pero hay cambio real")
            previos = [c for c in self.cambios(zona) if c.tipo == tipo and c.etiqueta.year < fila.anio]
            if not previos:
                return None
            base = previos[-1]
        else:
            domingo_real = _domingo_de(fila.fecha_real)
            coinciden = [c for c in delmismo if c.domingo == domingo_real]
            if not coinciden:
                return None
            base = coinciden[0]
        dias = timedelta(days=(_domingo_de(fecha_placebo) - base.domingo).days)
        return _cambio(zona, base.u + dias, base.antes_min, base.despues_min)

    def placebos_a2(self, zona: str, anio: int) -> tuple[Cambio, ...]:
        """Cambios que darían TODAS las fechas placebo del Anexo A2 en la zona y el año (E1a, E1b, E1c).

        Incluye las dos reglas de 2012 y las de 2015 (2015-09-06 00:00; en Pascua, 2015-09-05 22:00).
        Vacío si el año no está en el Anexo A2 o si la zona no tuvo esos cambios.
        """
        salida = []
        for fila in (f for f in self.anexo_a2 if f.anio == anio):
            for fecha in fila.fechas_placebo:
                c = self._cambio_desplazado(zona, fila, fecha)
                if c is not None:
                    salida.append(c)
        return tuple(sorted(salida, key=lambda c: c.u))

    def _adelanto_desplazado(self, zona: str, domingo: date) -> Cambio | None:
        """El adelanto de la zona movido, en días enteros, al ``domingo`` (mismo instante UTC del día y mismos
        desfases: «las horas son las del Anexo A»). Base: el adelanto real de ese año (el primero, si hay
        varios); si no hay, el último de un año anterior (Punta_Arenas desde 2017, Coyhaique desde 2025, 2015);
        si tampoco, el primero. None si la zona no tiene adelantos."""
        adelantos = [c for c in self.cambios(zona) if c.tipo == "adelanto"]
        if not adelantos:
            return None
        del_anio = [c for c in adelantos if c.etiqueta.year == domingo.year]
        previos = [c for c in adelantos if c.etiqueta.year < domingo.year]
        base = del_anio[0] if del_anio else previos[-1] if previos else adelantos[0]
        return _cambio(zona, base.u + timedelta(days=(domingo - base.domingo).days), base.antes_min, base.despues_min)

    def eventos_reglas_vencidas(self, zona: str, anio: int) -> tuple[tuple[Cambio, str], ...]:
        """Anexo A3 (Enmienda 3, E3-2): los adelantos de las reglas vencidas de la zona en el año, con
        h0 = ``etiqueta`` (domingo 00:00; en Pascua, sábado 22:00), que existen bajo la vigente C(Z), y la
        regla vencida de cada uno, como en ``fechas_reglas_vencidas``.

        - Fechas de la «regla anterior a 2008»: el adelanto de la zona movido a ese domingo
          (``_adelanto_desplazado``).
        - Fechas del Anexo A2: las de ``placebos_a2`` (el mismo h0 que el placebo del A2; ninguno si la zona no
          tuvo ese cambio, p. ej. Punta_Arenas en 2019).
        Una etiqueta que sale de los dos orígenes va una vez. Vacío si el año no tiene fechas. Orden UTC.
        """
        _verificar_anio(anio)
        salida: dict[datetime, tuple[Cambio, str]] = {}
        placebos = None
        for domingo, regla, origenes in self.reglas_vencidas:
            if domingo.year != anio:
                continue
            candidatos = []
            if ORIGEN_ANEXO_A2 in origenes:
                if placebos is None:
                    placebos = [c for c in self.placebos_a2(zona, anio) if c.tipo == "adelanto"]
                candidatos += [c for c in placebos if c.domingo == domingo]
            if ORIGEN_REGLA_ANTERIOR_2008 in origenes:
                c = self._adelanto_desplazado(zona, domingo)
                if c is not None:
                    candidatos.append(c)
            for c in candidatos:
                if self._de(zona).en_etiqueta(c.etiqueta) is not None:     # «no lo son bajo la vigente»
                    salida.setdefault(c.etiqueta, (c, regla))
        return tuple(sorted(salida.values(), key=lambda par: par[0].u))

    def cambios_reglas_vencidas(self, zona: str, anio: int) -> tuple[Cambio, ...]:
        """Cambios de Cv(Z, y): los del año reemplazados por las fechas del Anexo A2 (§4.1.4).

        Se usa la primera regla de cada fila (2012: ver el encabezado del módulo). Un cambio real que el
        Anexo A2 no nombra (el atraso de 2022) se conserva. Error si el año no está en el Anexo A2.
        """
        filas = self._filas_a2(anio)
        cambios = list(self.cambios(zona, anio))
        for fila in filas:
            nuevo = self._cambio_desplazado(zona, fila, fila.fechas_placebo[0])
            if nuevo is None:
                continue
            tipo = _tipo_de_fila(fila.cambio)
            if fila.fecha_real is not None:
                cambios = [c for c in cambios if not (c.tipo == tipo and c.domingo == _domingo_de(fila.fecha_real))]
            cambios.append(nuevo)
        resultado = tuple(sorted(cambios, key=lambda c: c.u))
        clave = (zona, anio)
        if clave not in self._vencidas:
            # Cv(Z, y) = los cambios reales de los demás años más éstos; _Pared exige que encadenen.
            otros = [c for c in self.cambios(zona) if c.etiqueta.year != anio]
            self._vencidas[clave] = _Pared(sorted(otros + list(resultado), key=lambda c: c.u))
        return resultado

    def _pared_vencida(self, zona: str, anio: int) -> _Pared:
        if (zona, anio) not in self._vencidas:
            self.cambios_reglas_vencidas(zona, anio)
        return self._vencidas[(zona, anio)]

    def desfase_vencido(self, zona: str, etiqueta) -> int | None:
        """c de Cv(zona, año de la etiqueta) en la etiqueta (h); None si es especial bajo Cv."""
        L = _ingenua(etiqueta)
        return self._pared_vencida(zona, L.year).en_etiqueta(L)

    def con_cortes(self, cortes: Mapping[str, Sequence[tuple[datetime, datetime]]]) -> "TablasCalendario":
        """Este calendario con las partes cortadas además en ``cortes`` (zona → intervalos [desde, hasta) de
        etiquetas, en hora de pared de esa zona). Las etiquetas de un corte quedan especiales:
        ``anotar_partes`` les pone ``especial = True`` y ninguna parte ni régimen (como en R-08).

        Sólo cambia ``especiales_en``, que usan ``partes_del_mes``, ``anotar_partes`` y los regímenes.
        Cambios, desfases (civiles y vencidos), Anexo A2 y huellas son los de este calendario, que no se
        modifica; la copia lleva su propia memoria de regímenes. Una zona sin intervalos no se corta."""
        desconocidas = sorted(set(cortes) - set(self._pared))
        if desconocidas:
            raise KeyError(f"zonas sin Anexo A: {desconocidas}")
        for zona, intervalos in cortes.items():
            for desde, hasta in intervalos:
                if not desde < hasta:
                    raise ValueError(f"{zona}: corte vacío o invertido [{desde}, {hasta})")
        copia = copy.copy(self)
        copia._pared = {z: _ParedConCortes(p, cortes[z]) if cortes.get(z) else p for z, p in self._pared.items()}
        copia._regimenes = {}
        return copia

    def con_cortes_reglas_vencidas(self, zonas: Iterable[str], anios: Iterable[int]) -> "TablasCalendario":
        """§4.1.4 (lectura ORQ-3b): las partes se cortan además en las etiquetas especiales de Cv(Z, y)
        (``cambios_reglas_vencidas``) para cada Z de ``zonas`` y cada y de ``anios``, que deben ser años
        del Anexo A2 (si no, ValueError). Ver ``con_cortes``."""
        anios = tuple(anios)
        return self.con_cortes({z: [intervalo_especial(c) for a in anios for c in self.cambios_reglas_vencidas(z, a)]
                                for z in zonas})


def anexo_a3(cal: TablasCalendario) -> dict[str, list[tuple[datetime, str]]]:
    """Anexo A3 (Enmienda 3, E3-2): zona → [(h0, regla), …] de las cuatro zonas del Anexo A en 2000-2026,
    en orden UTC (``TablasCalendario.eventos_reglas_vencidas``). Se serializa con ``serializar_anexo_a3``."""
    return {z: [(c.etiqueta, regla) for a in range(ANIOS_ANEXO_A[0], ANIOS_ANEXO_A[1] + 1)
                for c, regla in cal.eventos_reglas_vencidas(z, a)] for z in ZONAS_ANEXO_A}


def verificar_tablas(anexo_a: Mapping[str, list[list]], anexo_a2: Sequence[FilaA2]) -> tuple[str, str]:
    """sha256 de ambas tablas; ErrorTablas (→ A2, §5.4) si alguna no reproduce su huella anclada."""
    sha_a = _sha256(serializar_anexo_a(anexo_a))
    sha_a2 = _sha256(serializar_anexo_a2(anexo_a2))
    problemas = []
    conteos = {z: len(f) for z, f in anexo_a.items()}
    if conteos != CAMBIOS_POR_ZONA_ANEXO_A:
        problemas.append(f"cambios por zona {conteos} ≠ {CAMBIOS_POR_ZONA_ANEXO_A}")
    if sha_a != SHA_ANEXO_A:
        problemas.append(f"Anexo A: sha256 {sha_a} ≠ {SHA_ANEXO_A}")
    if sha_a2 != SHA_ANEXO_A2:
        problemas.append(f"Anexo A2: sha256 {sha_a2} ≠ {SHA_ANEXO_A2}")
    if not problemas:     # Enmienda 3, E3-2: el Anexo A3, generado desde las reglas, el A y el A2
        sha_a3 = TablasCalendario(anexo_a, anexo_a2).sha256_anexo_a3
        if sha_a3 != SHA_ANEXO_A3:
            problemas.append(f"Anexo A3: sha256 {sha_a3} ≠ {SHA_ANEXO_A3}")
    if problemas:
        raise ErrorTablas("; ".join(problemas))
    return sha_a, sha_a2


def cargar_tablas(*, verificar: bool = True) -> TablasCalendario:
    """Calcula ambas tablas con el paquete tzdata; si ``verificar``, exige las huellas (si no, ErrorTablas)."""
    anexo_a = transiciones_utc(BASE_TZDATA)
    anexo_a2 = reglas_anteriores(anexo_a)
    if verificar:
        verificar_tablas(anexo_a, anexo_a2)
    return TablasCalendario(anexo_a, anexo_a2)


# --- Coordenadas, territorio, P ---------------------------------------------
_NUMERO = r"\d+(?:[.,]\d+)?"
_DECIMAL = re.compile(rf"(?P<signo>[+-]?)\s*(?P<valor>{_NUMERO})")
_SEXAGESIMAL = re.compile(
    rf"(?P<signo>[+-]?)\s*(?P<g>{_NUMERO})\s*[°º˚]?\s*"
    rf"(?:(?P<m>{_NUMERO})\s*['′’]?\s*)?"
    rf"(?:(?P<s>{_NUMERO})\s*(?:\"|″|”|''|′′|’’)?\s*)?"
    r"(?P<letra>[NSEWnsew])?")
_LETRAS = {"lat": {"S": -1, "N": 1}, "lon": {"W": -1, "E": 1}}


def _numero(texto: str | None) -> float | None:
    return None if texto is None else float(texto.replace(",", "."))


def interpretar_coordenada(texto: str | None, eje: str) -> float | None:
    """Decimal con punto o coma, o sexagesimal con signo o letra S/W (§3.3). Nunca invierte un signo.

    ``eje`` ∈ {"lat", "lon", "alt"}. Devuelve None si no se puede interpretar. La altitud sólo admite
    decimal. Una letra N o E deja el valor positivo (no se invierte) y una letra que contradice el signo
    escrito, o que no es del eje, da None. Minutos y segundos deben quedar en [0, 60).
    """
    if eje not in ("lat", "lon", "alt"):
        raise ValueError(f"eje desconocido: {eje!r}")
    if texto is None:
        return None
    t = str(texto).strip().replace("−", "-")
    if not t:
        return None
    m = _DECIMAL.fullmatch(t)
    if m:
        valor = float(m.group("valor").replace(",", "."))
        return -valor if m.group("signo") == "-" else valor
    if eje == "alt":
        return None
    m = _SEXAGESIMAL.fullmatch(t)
    if m is None:
        return None
    g, mi, s = _numero(m.group("g")), _numero(m.group("m")), _numero(m.group("s"))
    if (mi is not None and not 0 <= mi < 60) or (s is not None and not 0 <= s < 60):
        return None
    if (mi is not None and not float(g).is_integer()) or (s is not None and not float(mi).is_integer()):
        return None      # grados decimales con minutos, o minutos decimales con segundos
    valor = g + (mi or 0.0) / 60 + (s or 0.0) / 3600
    signo_escrito = {"-": -1, "+": 1, "": 0}[m.group("signo")]
    letra = m.group("letra")
    signo_letra = 0
    if letra is not None:
        signo_letra = _LETRAS[eje].get(letra.upper(), 0)
        if signo_letra == 0:
            return None
    if signo_escrito and signo_letra and signo_escrito != signo_letra:
        return None
    return -valor if -1 in (signo_escrito, signo_letra) else valor


def _fila_celda(lat: float, lon: float, catalogo_pixeles: pd.DataFrame) -> pd.Series | None:
    """La fila del catálogo cuya celda (cell_west a cell_north) contiene la estación.

    Bordes cerrados; si dos celdas vecinas la contienen (la estación cae en un borde común), gana la
    de bordes semiabiertos [oeste, este) × [sur, norte) y, si aún empatan, la de menor ``pixel_id``.
    """
    faltan = [c for c in COLUMNAS_CELDA if c not in catalogo_pixeles.columns]
    if faltan:
        raise KeyError(f"al catálogo de píxeles le faltan {faltan}")
    cat = catalogo_pixeles
    cerrada = ((cat["cell_west"] <= lon) & (lon <= cat["cell_east"])
               & (cat["cell_south"] <= lat) & (lat <= cat["cell_north"]))
    candidatas = cat[cerrada]
    if candidatas.empty:
        return None
    if len(candidatas) > 1:
        semiabierta = (candidatas["cell_west"] <= lon) & (lon < candidatas["cell_east"]) \
            & (candidatas["cell_south"] <= lat) & (lat < candidatas["cell_north"])
        if semiabierta.any():
            candidatas = candidatas[semiabierta]
    return candidatas.sort_values("pixel_id", kind="mergesort").iloc[0]


def celda_que_contiene(lat: float, lon: float, catalogo_pixeles: pd.DataFrame) -> int | None:
    """``pixel_id`` de la celda propia de la estación (§3.3), con la misma regla de bordes que el territorio."""
    fila = _fila_celda(lat, lon, catalogo_pixeles)
    return None if fila is None else int(fila["pixel_id"])


def coordenadas_en_rango(lat: float | None, lon: float | None) -> bool:
    """§3.3: −90 ≤ lat ≤ −17 y −110 ≤ lon ≤ −55 (si no, E3 y E4 quedan sin información)."""
    if lat is None or lon is None or not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    (lat_min, lat_max), (lon_min, lon_max) = _c("COORD_LAT"), _c("COORD_LON")
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def territorio_y_P(lat: float | None, lon: float | None, catalogo_pixeles: pd.DataFrame,
                   macrozona_region: Mapping[int, str]) -> tuple[Territorio, int | None, str, tuple[str, ...],
                                                                  tuple[Hipotesis, ...]]:
    """(territorio, región, macrozona, Zs, P) según §3.3 y §2.2.

    Orden: lat < −60 → Antártica; lon < −100 → Pascua; −100 ≤ lon < −77 → Juan Fernández/Desventuradas;
    si no, región = cod_comuna // 1000 de la celda (cell_west…cell_north) que contiene la estación:
    11 → Aysén, 12 → Magallanes, otra → continental. Sin celda o cod_comuna = 0 → incierto.
    Islas → macrozona «insular»; incierto → «sin_region». Coordenadas fuera de rango → incierto
    (E3 y E4 quedan sin información por coordenadas; R-38 para la macrozona de la Antártica).
    """
    region_aysen, region_magallanes = _c("REGIONES_AUSTRALES")
    lon_jf_desde, lon_jf_hasta = _c("LON_JUAN_FERNANDEZ")
    region: int | None = None
    if not coordenadas_en_rango(lat, lon):
        territorio = Territorio.INCIERTO
    elif lat < _c("LAT_ANTARTICA"):
        territorio, region = Territorio.ANTARTICA, region_magallanes      # R-38: «austral» (región 12)
    elif lon < _c("LON_PASCUA"):
        territorio = Territorio.PASCUA_SALA_Y_GOMEZ
    elif lon_jf_desde <= lon < lon_jf_hasta:
        territorio = Territorio.JUAN_FERNANDEZ_DESVENTURADAS
    else:
        fila = _fila_celda(lat, lon, catalogo_pixeles)
        cod = None if fila is None else int(fila["cod_comuna"])
        if not cod:                                   # sin celda o cod_comuna = 0: la latitud no decide
            territorio = Territorio.INCIERTO
        else:
            region = cod // DIVISOR_REGION
            territorio = (Territorio.AYSEN if region == region_aysen
                          else Territorio.MAGALLANES if region == region_magallanes
                          else Territorio.CONTINENTAL)
    zs, ids = ZS_Y_P[territorio]
    return territorio, region, macrozona(territorio, region, macrozona_region), zs, hipotesis_de_P(ids)


def hipotesis_de_P(ids: Sequence[str]) -> tuple[Hipotesis, ...]:
    if len(set(ids)) != len(ids):
        raise ValueError(f"P con ids repetidos: {ids}")
    return tuple(Hipotesis.desde_id(i) for i in ids)


# --- Regímenes, partes y desfases --------------------------------------------
def _segmentos(zs: Sequence[str], desde: datetime, hasta: datetime,
               tablas: TablasCalendario) -> list[tuple[datetime, datetime, tuple[int, ...]]]:
    """Tramos [a, b) de etiquetas sin especiales de Zs dentro de [desde, hasta), con su tupla de desfases."""
    intervalos = sorted({i for z in zs for i in tablas._de(z).especiales_en(desde, hasta)})
    fundidos: list[tuple[datetime, datetime]] = []
    for a, b in intervalos:
        if fundidos and a <= fundidos[-1][1]:
            fundidos[-1] = (fundidos[-1][0], max(fundidos[-1][1], b))
        else:
            fundidos.append((a, b))
    tramos, cursor = [], desde
    for a, b in fundidos:
        if a > cursor:
            tramos.append((cursor, min(a, hasta)))
        cursor = max(cursor, b)
    if cursor < hasta:
        tramos.append((cursor, hasta))
    salida = []
    for a, b in tramos:
        if b - a < UNA_HORA:
            raise ValueError(f"tramo de menos de una hora entre {a} y {b}")
        vector = tuple(tablas._de(z).en_etiqueta(a) for z in zs)
        if None in vector or vector != tuple(tablas._de(z).en_etiqueta(b - UNA_HORA) for z in zs):
            raise ValueError(f"desfases no constantes en el tramo {a} – {b}")
        salida.append((a, b, vector))
    return salida


def regimenes_del_anio(zs: Sequence[str], anio: int, tablas: TablasCalendario) -> tuple[Regimen, ...]:
    """R0 (contiene el 1 de enero) y R1 (si existe). Error si aparecen más de dos tuplas de desfases.

    Una tupla de las partes es un año-régimen si existe en UTC (todas las zonas de Zs la tienen en un
    mismo instante del año); si no, es una astilla de borde (R-08) y no cuenta.
    """
    _verificar_anio(anio)
    zs = tuple(zs)
    clave = (zs, anio)
    if clave in tablas._regimenes:
        return tablas._regimenes[clave]
    inicio, fin = datetime(anio, 1, 1), datetime(anio + 1, 1, 1)
    margen = timedelta(days=2)
    instantes = [inicio - margen] + [u for z in zs for u in tablas._de(z).u if inicio - margen <= u < fin + margen]
    en_utc = {tuple(tablas._de(z).en_utc(u) for z in zs) for u in instantes}
    vectores: list[tuple[int, ...]] = []
    for _, _, vector in _segmentos(zs, inicio, fin, tablas):
        if vector in en_utc and vector not in vectores:
            vectores.append(vector)
    r0 = tuple(tablas._de(z).en_etiqueta(inicio) for z in zs)
    if not vectores or vectores[0] != r0:
        raise ValueError(f"{zs} {anio}: el 1 de enero no abre un año-régimen")
    if len(vectores) > 2:
        raise ValueError(f"{zs} {anio}: más de dos tuplas de desfases en Zs: {vectores}")
    regimenes = tuple(Regimen(anio=anio, id=f"R{i}", desfases_zs=v) for i, v in enumerate(vectores))
    tablas._regimenes[clave] = regimenes
    return regimenes


def partes_del_mes(zs: Sequence[str], anio: int, mes: int, tablas: TablasCalendario) -> tuple[ParteDef, ...]:
    """Partes «AAAA-MM-n» del mes cortadas en las etiquetas especiales de cada zona de Zs."""
    inicio = datetime(anio, mes, 1)
    fin = datetime(anio + 1, 1, 1) if mes == len(MESES) else datetime(anio, mes + 1, 1)
    por_vector = {r.desfases_zs: r.id for r in regimenes_del_anio(zs, anio, tablas)}
    return tuple(ParteDef(id=f"{anio:04d}-{mes:02d}-{n}", anio=anio, mes=mes, n=n, desde=a, hasta=b - UNA_HORA,
                          regimen=por_vector.get(vector))
                 for n, (a, b, vector) in enumerate(_segmentos(zs, inicio, fin, tablas), start=1))


def anotar_partes(extracto: pd.DataFrame, info: InfoEstacion, tablas: TablasCalendario) -> pd.DataFrame:
    """Agrega las columnas de ESQUEMA_ANOTACION (parte, regimen, especial) al extracto horario.

    Una etiqueta especial de alguna zona de Zs queda con ``especial = True`` y sin parte ni régimen;
    una astilla de borde, con parte y sin régimen (R-08). Devuelve una copia; no reordena filas.
    """
    repetidas = [c for c in ESQUEMA_ANOTACION if c in extracto.columns]
    if repetidas:
        raise ValueError(f"el extracto ya trae {repetidas}")
    L = pd.DatetimeIndex(extracto["L"])
    if L.tz is not None:
        raise ValueError("L debe ser ingenua (timestamp_source)")
    if L.hasnans:
        raise ValueError("L con valores nulos")
    n = len(extracto)
    parte = np.full(n, None, dtype=object)
    regimen = np.full(n, None, dtype=object)
    dentro_total = np.zeros(n, dtype=bool)
    valores = L.values.astype("datetime64[ns]")
    anios, meses = L.year.to_numpy(), L.month.to_numpy()
    for anio, mes in sorted(set(zip(anios.tolist(), meses.tolist()))):
        filas = np.flatnonzero((anios == anio) & (meses == mes))
        partes = partes_del_mes(info.zs, anio, mes, tablas)
        desde = np.array([p.desde for p in partes], dtype="datetime64[ns]")
        fin = np.array([p.hasta + UNA_HORA for p in partes], dtype="datetime64[ns]")
        x = valores[filas]
        k = np.searchsorted(desde, x, side="right") - 1
        dentro = (k >= 0) & (x < fin[np.clip(k, 0, None)])
        ids = np.array([p.id for p in partes], dtype=object)
        regs = np.array([p.regimen for p in partes], dtype=object)
        parte[filas[dentro]] = ids[k[dentro]]
        regimen[filas[dentro]] = regs[k[dentro]]
        dentro_total[filas[dentro]] = True
    salida = extracto.copy()
    salida["parte"] = pd.array(parte, dtype=ESQUEMA_ANOTACION["parte"])
    salida["regimen"] = pd.array(regimen, dtype=ESQUEMA_ANOTACION["regimen"])
    salida["especial"] = pd.Series(~dentro_total, index=extracto.index, dtype=ESQUEMA_ANOTACION["especial"])
    return salida


def desfase(h: Hipotesis, regimen: Regimen, zs: Sequence[str]) -> int:
    """c_H(R): F → su c; C(Z) → el desfase de Z en el régimen. Error si Z ∉ Zs.

    Cv no tiene desfase por régimen (R-09): se consulta por etiqueta con ``desfase_en_etiqueta``.
    """
    if h.tipo == "F":
        return int(h.desfase)
    if h.tipo == "C":
        zs = tuple(zs)
        if h.zona not in zs:
            raise ValueError(f"{h.zona} no está en Zs = {zs}")
        if len(regimen.desfases_zs) != len(zs):
            raise ValueError("el régimen no corresponde a estas Zs")
        return regimen.desfases_zs[zs.index(h.zona)]
    raise ValueError(f"hipótesis sin desfase por régimen: tipo {h.tipo!r} (R-09)")


def desfase_en_etiqueta(h: Hipotesis, etiqueta, tablas: TablasCalendario) -> int | None:
    """c_H(L); None si L es repetida o inexistente bajo una C(Z) (o bajo Cv(Z) del año de L)."""
    if h.tipo == "F":
        return int(h.desfase)
    if h.tipo == "C":
        return tablas.desfase_civil(h.zona, etiqueta)
    if h.tipo == "Cv":
        return tablas.desfase_vencido(h.zona, etiqueta)
    raise ValueError(f"tipo de hipótesis desconocido: {h.tipo!r}")


def fusionar(P: Sequence[Hipotesis], regimenes_con_datos: Sequence[Regimen], zs: Sequence[str]) -> tuple[ClaseH, ...]:
    """Clases de §2.3: hipótesis con la misma c_H(R) en todos los regímenes con datos del año.

    «Régimen con datos» = con alguna etiqueta con datos que no sea especial (R-30).
    Miembros y clases van en orden canónico (``Hipotesis.orden``). Sin regímenes con datos, todo P es
    una sola clase (la definición se cumple en vacío).
    """
    regs = sorted(regimenes_con_datos, key=lambda r: r.id)
    if len({r.id for r in regs}) != len(regs) or len({r.anio for r in regs}) > 1:
        raise ValueError("regímenes repetidos o de años distintos")
    ids = [h.id for h in P]
    if len(set(ids)) != len(ids):
        raise ValueError(f"P con hipótesis repetidas: {ids}")
    grupos: dict[tuple[int, ...], list[Hipotesis]] = {}
    for h in P:
        grupos.setdefault(tuple(desfase(h, r, zs) for r in regs), []).append(h)
    clases = [ClaseH(miembros=tuple(sorted(miembros, key=lambda h: h.orden())),
                     desfases={r.id: vector[i] for i, r in enumerate(regs)})
              for vector, miembros in grupos.items()]
    return tuple(sorted(clases, key=lambda c: c.miembros[0].orden()))


def d_estrella(a: ClaseH, b: ClaseH) -> int:
    """máx |c_a(R) − c_b(R)| sobre los regímenes con datos (§2.1)."""
    if set(a.desfases) != set(b.desfases):
        raise ValueError("clases con regímenes distintos")
    return max((abs(a.desfases[r] - b.desfases[r]) for r in a.desfases), default=0)


def rivales_mas_cercanas(clase: ClaseH, clases: Sequence[ClaseH]) -> tuple[ClaseH, ...]:
    """R_min: las otras clases con el menor d* (§2.1)."""
    otras = [c for c in clases if c.ids_miembros != clase.ids_miembros]
    if not otras:
        return ()
    distancias = [d_estrella(clase, c) for c in otras]
    minima = min(distancias)
    return tuple(c for c, d in zip(otras, distancias) if d == minima)


def macrozona(territorio: Territorio, region: int | None, macrozona_region: Mapping[int, str]) -> str:
    """Islas → «insular»; incierto → «sin_region»; Antártica → la de la región 12 (R-38); otra → la de su región."""
    if territorio in TERRITORIOS_INSULARES:
        return MACROZONA_INSULAR
    if territorio == Territorio.INCIERTO:
        return MACROZONA_INCIERTA
    if territorio == Territorio.ANTARTICA and region is None:
        region = _c("REGIONES_AUSTRALES")[1]
    if region is None:
        raise ValueError(f"territorio {territorio} sin región")
    if region not in macrozona_region:
        raise KeyError(f"región {region} sin macrozona en MACROZONA_REGION")
    return macrozona_region[region]


def fecha_de(etiqueta: datetime) -> date:
    return etiqueta.date()
