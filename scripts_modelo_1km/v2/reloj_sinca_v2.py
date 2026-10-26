#!/usr/bin/env python3
"""Reloj SINCA de la red ampliada: verificación estructural con las dos convenciones de etiqueta y paso a UTC (R7).

Es la copia versionada de ``scripts_modelo_1km/verificar_reloj_sinca.py`` (sha256 a93a1eab…), que **no se modifica**:
el reloj DMC la fija por su huella y extrae su ``transiciones`` por AST (§1.10 del reloj; ``reloj_dmc/fijados.py``).
Este módulo no importa ``_comun_modelo`` (que termina con SystemExit si el disco de datos no está montado), así que
sus funciones puras se prueban sin datos.

**Las dos convenciones de etiqueta de un exportador en hora civil.** Con reloj fijo (UTC−4) la etiqueta al fin del
intervalo es la misma se lea como «hora del reloj al terminar la hora» o como «hora de inicio + 1 h». Con un reloj
civil las dos lecturas se separan en los días de cambio de hora:

* ``fin``: la etiqueta es la hora civil del reloj al terminar el intervalo. En el adelanto (primer domingo de
  septiembre, 24:00 → 01:00) falta la etiqueta **00:00 del domingo**; en el atraso (primer domingo de abril,
  24:00 → 23:00) se repite la **23:00 del sábado**;
* ``inicio_mas_1h``: la etiqueta es la hora civil de inicio más una hora. Falta la **01:00 del domingo** y se repite
  la **00:00 del domingo**. Es lo que supone el verificador original.

El tablero señaló que el original «ubica las horas especiales una hora tarde»: es cierto bajo ``fin`` y falso bajo
``inicio_mas_1h``. **Cuál usa SINCA no está documentado.** Lo guardado en disco (sin red):
``docs/SINCA_SEMANTICA_PENDIENTE.md`` (consulta del 2026-09-15) cita el D.S. 61/2008, art. 2(i), con la etiqueta 17
para 17:01-18:00 (al inicio), y la R.E. 1449/2023, glosario «Hora», con la etiqueta 18 para el mismo intervalo (al
término), y concluye que no se encontró una especificación del exportador; ``config/sinca/politica_temporal.json``
declara «hora_local_civil_sinca_sin_offset» como hipótesis; su README no dice nada de la etiqueta. Las dos normas
suponen además el reloj fijo GMT−4, donde las dos lecturas coinciden. Por eso ``verificar_serie`` da el veredicto con
las dos convenciones, y la elección la hace una regla del autor (**T4**, ``decisiones_autor_traduccion_20261025.md``,
2026-10-26), ``elegir_convencion``: una sola convención para todo SINCA, decidida antes del paso a UTC y sólo con las
etiquetas de los días de cambio de hora (qué hora falta y cuál se repite; el reloj no lee ningún valor de contaminante,
sólo ``ts_local`` y ``hora_repetida_en_fuente``). Votan las unidades del veredicto de R7, estación × contaminante ×
año local (**T9**): se cuentan las que dan ``hora_civil`` con una convención y no con la otra; gana la que tiene más y,
si empatan (también en cero), ``inicio_mas_1h``, la que supone el verificador original. Los dos conteos y la elegida
van en ``resumen.json`` y al anexo. El reloj que escribe la elección corre sobre todo SINCA (2000-2026, los tres
contaminantes y el conjunto estación × contaminante de la red 2 en un derivado completo, o se niega), registra las
raíces, cada serie con su huella, la política temporal leída y la región y la zona de cada serie, y se escribe una
sola vez (``ejecutar_reloj``). Efecto de cada opción, si la regla eligiera la equivocada:

* si se adopta ``fin`` y un exportador usa ``inicio_mas_1h``, ese estación-año no se detecta («reloj fijo parcial») y
  sus horas de verano quedan una hora corridas; y al revés;
* en los años detectados, las dos conversiones difieren sólo en las horas contiguas a cada cambio de hora.

**Veredicto** por estación × contaminante × año local de la etiqueta y por convención: ``reloj_fijo``,
``reloj_fijo_parcial``, ``sin_evidencia``, ``sin_transiciones`` (zonas sin cambio de hora ese año) u ``hora_civil``.
Las reglas de ``evaluar_dia`` y ``veredicto`` son las del original; ``evaluar_dia`` acepta además las etiquetas
repetidas **dentro de un mismo archivo fuente** (``hora_repetida_en_fuente`` del derivado), porque el derivado deja
una sola fila ``seleccionada`` por etiqueta y la repetición queda en ``solapamientos.parquet``. Límite (R7): un año en
hora civil sin días de cambio en sus datos no se detecta y queda en UTC−4 fijo. Eso incluye los años sin cambio de hora
en su zona (``anios_sin_cambio_de_hora``: 2015 en todas; America/Punta_Arenas, RXII, de 2017 a 2026; America/Coyhaique,
RXI, en 2025 y 2026): dan ``sin_transiciones`` y siguen la regla general, y si el exportador estaba en hora civil, que
esos años es −03 todo el año, sus horas quedan con 1 h de error **todo el año**, no sólo en verano. No votan en T4.
``sin_transiciones_junto_a_civil`` cuenta las unidades así cuyo año anterior o siguiente da ``hora_civil`` con la
convención elegida; van al ``resumen.json``, al json del panel y al anexo (quinta revisión, menor 4). Tratarlas de otro
modo (convertir 2015, por ejemplo) sería una regla nueva, del autor.

**Base de zonas horarias.** La elección de T4 y el paso a UTC dependen de la base de zonas del entorno. El reloj que
escribe y el panel exigen que dé las 132 horas especiales de 2000-2026 con la huella fijada (``HORAS_ESPECIALES``,
96a7b7cb…, la de ``amb_v2``): otra base se detiene (``exigir_base_de_zonas``; quinta revisión, menor 3).

**Paso a UTC** (``config/sinca/politica_temporal.json``, 41018e4c…): UTC−4 fijo con la etiqueta al fin (inicio UTC =
etiqueta + 3 h), salvo los años con veredicto ``hora_civil`` (P9), que se convierten con la zona IANA y la convención
elegida: la hora repetida toma la ocurrencia **estándar** y registra la otra; la inexistente se desplaza hacia
adelante y se marca; dos etiquetas en la misma hora UTC se promedian aguas abajo, con conteo y bandera
(``panel_red2_v2``). ``utc_candidato_1`` del derivado es la ocurrencia más temprana, no la estándar; aquí no se usa.

Uso (en el armado, R22 paso 3, después de confirmar la traducción en git)::

    python -B scripts_modelo_1km/v2/reloj_sinca_v2.py --derivado <raíz del derivado red 2> [--anios 2000-2026]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[1]
RUTA_POLITICA = REPO / "config" / "sinca" / "politica_temporal.json"
SHA_POLITICA = "41018e4c066d9e30b5ba0b1ff92d47eeb47bab1984b5b8c45a778939359ac61c"
RUTA_ORIGINAL = REPO / "scripts_modelo_1km" / "verificar_reloj_sinca.py"
SHA_ORIGINAL = "a93a1eab928d032b1d83c0e32702f2f2b73fa6d9a0b228b47ef9abb3f632d446"

SCHEMA = "airpollution.modelo-1km-v2.reloj-sinca-red2.v1"
OFFSET_FIJO_H = 4                      # UTC−4 fijo (D.S. 61/2008; R.E. 1449/2023), _comun_modelo.py:81
DESPLAZAMIENTO_FIJO_H = OFFSET_FIJO_H - 1   # etiqueta al fin del intervalo: inicio UTC = etiqueta + 3 h
MINIMO_ETIQUETAS_ANIO = 24 * 30        # como el original (verificar_reloj_sinca.py:148)
ANIOS_POR_OMISION = (2000, 2026)       # período R4
VEREDICTOS = ("reloj_fijo", "reloj_fijo_parcial", "sin_evidencia", "sin_transiciones", "hora_civil")
CONVENCIONES = ("fin", "inicio_mas_1h")          # lecturas de la etiqueta de un reloj civil; no documentada (M4)
DESEMPATE = "inicio_mas_1h"                       # T4: empate, también en cero
DECISION_T4 = {"archivo": "auditoria/20261024/sinca_al_modelo/decisiones_autor_traduccion_20261025.md "
                          "(repositorio de salud, secciones del 2026-10-26: T4 y T9)",
               "regla": "una sola convención para todo SINCA, con las etiquetas de los días de cambio de hora y sin "
                        "valores de contaminante; votan las unidades del veredicto de R7 (estación × contaminante × "
                        "año local, T9): gana la que da hora_civil en más unidades en que la otra no; empate (también "
                        "en cero) → inicio_mas_1h"}
CONTAMINANTES_SINCA = ("pm25", "no2", "o3")      # «todo SINCA» para la elección de T4
NOMBRE_SALIDA = "verificacion_reloj_sinca_red2"
FUENTE_CONVENCION = ("docs/SINCA_SEMANTICA_PENDIENTE.md (2026-09-15): D.S. 61/2008 art. 2(i) etiqueta al inicio; "
                     "R.E. 1449/2023 glosario «Hora» etiqueta al término; sin especificación del exportador")
CIVIL = "hora_civil"
QC_HORA = ("fijo", "civil_univoca", "civil_ambigua_estandar", "civil_inexistente_desplazada")
UTC = timezone.utc
# Las horas civiles especiales de 2000-2026 de las tres zonas de la política temporal (America/Santiago,
# America/Punta_Arenas y America/Coyhaique) con la base de amb_v2 (tzdata de conda 2026c; America/Santiago fd006953…),
# iguales a las de la base del sistema que usó la v1 (d020f0d7…). Con otra base (America/Santiago copiada de
# America/Punta_Arenas, por ejemplo) son 112 y otra huella: el reloj no escribe y el panel no arma.
HORAS_ESPECIALES = {"anios": ANIOS_POR_OMISION, "horas": 132,
                    "sha256": "96a7b7cb6862d58d1f38f83e986063c9cce0d2fa44cf436a9d2d7de361cd95fb"}


# ---------------------------------------------------------------------------
# Política temporal
# ---------------------------------------------------------------------------
def leer_politica_con_huella(ruta: Path = RUTA_POLITICA, exigir_sha: bool = True) -> tuple[dict, str]:
    """Bloque ``sinca`` de la política temporal y el sha256 de los bytes leídos; con ``exigir_sha``, comprueba que sea
    el que cita el bloque R7 (41018e4c…)."""
    datos = Path(ruta).read_bytes()
    sha = hashlib.sha256(datos).hexdigest()
    if exigir_sha and sha != SHA_POLITICA:
        raise SystemExit(f"{Path(ruta).name} no tiene la huella que cita el bloque R7 ({SHA_POLITICA[:8]}…)")
    return json.loads(datos.decode("utf-8"))["sinca"], sha


def leer_politica(ruta: Path = RUTA_POLITICA, exigir_sha: bool = True) -> dict:
    """Bloque ``sinca`` de la política temporal; con ``exigir_sha``, comprueba su huella (41018e4c…)."""
    return leer_politica_con_huella(ruta, exigir_sha)[0]


def zona_de(region: str, politica: dict) -> str:
    """Zona IANA de la región SINCA (Aysén y Magallanes con la suya; el resto, America/Santiago)."""
    return politica["zonas_iana_por_region"].get(str(region), politica["zona_iana_default"])


# ---------------------------------------------------------------------------
# Transiciones (corregidas)
# ---------------------------------------------------------------------------
def horas_civiles_especiales(zona: str, anio: int) -> list[tuple[datetime, str]]:
    """Horas civiles (de reloj) que no existen o que se repiten en ``anio``: [(hora civil, tipo)].

    Avanza hora a hora en UTC: en cada instante T con un desfase distinto del de T − 1 h, las horas civiles de
    ``[T + anterior, T + nuevo)`` no existen (si el reloj se adelanta) y las de ``[T + nuevo, T + anterior)`` se
    repiten (si se atrasa). Un cambio de varias horas da una entrada por hora."""
    tz = ZoneInfo(zona)
    t = datetime(anio - 1, 12, 30, tzinfo=UTC)
    fin = datetime(anio + 1, 1, 2, tzinfo=UTC)
    paso = timedelta(hours=1)
    previo = t.astimezone(tz).utcoffset()
    out: list[tuple[datetime, str]] = []
    while t < fin:
        t = t + paso
        actual = t.astimezone(tz).utcoffset()
        if actual != previo:
            delta_h = int(round((actual - previo).total_seconds() / 3600.0))
            if delta_h > 0:
                inicio, tipo = (t + previo).replace(tzinfo=None), "inexistente"
            else:
                inicio, tipo = (t + actual).replace(tzinfo=None), "ambigua"
            out += [(inicio + timedelta(hours=k), tipo) for k in range(abs(delta_h))]
            previo = actual
    return [(c, tipo) for c, tipo in out if c.year in (anio - 1, anio, anio + 1)]


def transiciones(zona: str, anio: int, convencion: str) -> list[tuple[date, str, int]]:
    """Etiquetas especiales de ``anio`` según la convención: (fecha, tipo, hora) con tipo ``inexistente`` (la
    etiqueta que un exportador civil no puede emitir) o ``ambigua`` (la que emite dos veces).

    ``fin``: la etiqueta es la hora civil al terminar el intervalo, así que las especiales son las horas civiles que
    no existen o se repiten. ``inicio_mas_1h``: la etiqueta es la hora civil de inicio + 1 h, así que son esas mismas
    horas más una hora (lo que devuelve el verificador original)."""
    if convencion not in CONVENCIONES:
        raise ValueError(f"convención de etiqueta desconocida: {convencion!r} (una de {CONVENCIONES})")
    corrimiento = timedelta(hours=0 if convencion == "fin" else 1)
    out = []
    for civil, tipo in horas_civiles_especiales(zona, anio):
        etiqueta = civil + corrimiento
        if etiqueta.year == anio:
            out.append((etiqueta.date(), tipo, etiqueta.hour))
    return out


def evaluar_dia(etiquetas: pd.DatetimeIndex, fecha: date, tipo: str, hora: int,
                repetidas: pd.DatetimeIndex | None = None) -> dict:
    """Estado de un día de cambio de hora; la regla es la del original (``verificar_reloj_sinca.py:76-89``).

    ``etiquetas``: las etiquetas locales de la serie (las filas ``seleccionada`` del derivado). ``repetidas``: las
    etiquetas que su archivo fuente trae repetidas (``hora_repetida_en_fuente``); una hora ambigua que el exportador
    emitió dos veces cuenta como repetida aunque el derivado haya dejado una sola fila."""
    etiquetas = pd.DatetimeIndex(etiquetas)
    dia = etiquetas[etiquetas.normalize() == pd.Timestamp(fecha)]
    horas = dia.hour.to_numpy()
    n, unicas = int(len(horas)), int(len(np.unique(horas)))
    presente = bool((horas == hora).any())
    repetida = int((horas == hora).sum()) > 1
    if repetidas is not None and len(repetidas):
        rep = pd.DatetimeIndex(repetidas)
        repetida = repetida or bool((rep == pd.Timestamp(fecha) + pd.Timedelta(hours=int(hora))).any())
    if n == 0:
        estado = "sin_etiquetas"
    elif tipo == "inexistente":
        estado = "reloj_fijo" if (presente and unicas == 24) else (
            "hora_civil" if (not presente and unicas == 23) else "sin_evidencia")
    else:
        estado = "hora_civil" if (repetida or unicas == 23 and n == 24) else (
            "reloj_fijo" if (unicas == 24 and n == 24) else "sin_evidencia")
    return {"fecha": fecha.isoformat(), "tipo": tipo, "hora_civil": int(hora), "etiquetas": n,
            "horas_unicas": unicas, "hora_presente": presente, "hora_repetida": bool(repetida), "estado": estado}


def veredicto(estados: list[str]) -> str:
    """Veredicto de un estación-año; la regla del original (``verificar_reloj_sinca.py:92-99``)."""
    if not estados:
        return "sin_transiciones"
    if "hora_civil" in estados:
        return "hora_civil"
    if estados.count("reloj_fijo") >= 1 and "sin_evidencia" not in estados:
        return "reloj_fijo"
    if "reloj_fijo" in estados:
        return "reloj_fijo_parcial"
    return "sin_evidencia"


def verificar_serie(ts_local, zona: str, repetida_en_fuente=None, anios: tuple[int, int] = ANIOS_POR_OMISION,
                    minimo: int = MINIMO_ETIQUETAS_ANIO) -> tuple[list[dict], list[dict]]:
    """Veredictos de una serie por año local de la etiqueta, con las dos convenciones (``veredicto_fin`` y
    ``veredicto_inicio_mas_1h``). Devuelve (filas, detalle de los días de cambio).

    Como el original, un año con menos de ``minimo`` etiquetas no se evalúa (no aparece en las filas) y queda,
    por lo tanto, en la regla general."""
    etiquetas = pd.DatetimeIndex(pd.to_datetime(pd.Series(ts_local)))
    rep_mask = None if repetida_en_fuente is None else np.asarray(repetida_en_fuente, dtype=bool)
    filas, detalle = [], []
    for anio in range(int(anios[0]), int(anios[1]) + 1):
        en_anio = etiquetas.year == anio
        del_anio = etiquetas[en_anio]
        if len(del_anio) < minimo:
            continue
        repetidas = None if rep_mask is None else etiquetas[en_anio & rep_mask]
        fila = {"anio": anio, "zona_iana": zona}
        for conv in CONVENCIONES:
            estados = []
            for fecha, tipo, hora in transiciones(zona, anio, conv):
                r = evaluar_dia(del_anio, fecha, tipo, hora, repetidas)
                r.update({"anio": anio, "zona_iana": zona, "convencion": conv})
                detalle.append(r)
                estados.append(r["estado"])
            fila[f"n_transiciones_{conv}"] = len(estados)
            fila[f"estados_{conv}"] = "|".join(estados)
            fila[f"veredicto_{conv}"] = veredicto(estados)
        filas.append(fila)
    return filas, detalle


# ---------------------------------------------------------------------------
# Paso a UTC
# ---------------------------------------------------------------------------
def utc_fijo(ts_local) -> pd.Series:
    """Inicio del bin horario UTC (naive) con UTC−4 fijo y la etiqueta al fin: etiqueta + 3 h."""
    return pd.to_datetime(pd.Series(ts_local)).reset_index(drop=True) + pd.Timedelta(hours=DESPLAZAMIENTO_FIJO_H)


def utc_civil(ts_local, zona: str, convencion: str) -> pd.DataFrame:
    """Inicio del bin UTC (naive) de etiquetas en hora civil de ``zona`` con la ``convencion`` dada.

    ``fin``: la etiqueta es la hora civil al terminar; se lleva a UTC y se resta 1 h. ``inicio_mas_1h``: la hora civil
    de inicio es la etiqueta − 1 h y se lleva a UTC. Columnas: ``ts_utc`` (inicio), ``ts_utc_alternativo`` (la
    ocurrencia de verano de una hora repetida; NaT en el resto) y ``qc_hora`` (``civil_univoca``,
    ``civil_ambigua_estandar`` o ``civil_inexistente_desplazada``).

    La zona se pasa como ``ZoneInfo`` (no como texto, que pandas resolvería con pytz y su propia base): así el paso a
    UTC usa la misma base de zonas que el veredicto. La tabla devuelta dice en ``attrs["biblioteca_zona"]`` qué tipo de
    zona usó de verdad la conversión (el módulo del ``tz`` de pandas: «zoneinfo»); eso es lo que registra
    ``base_de_zonas`` y lo que el panel compara (cuarta revisión, menor 13)."""
    if convencion not in CONVENCIONES:
        raise ValueError(f"convención de etiqueta desconocida: {convencion!r} (una de {CONVENCIONES})")
    una_hora = pd.Timedelta(hours=1)
    loc = pd.to_datetime(pd.Series(ts_local)).reset_index(drop=True)
    civil = loc if convencion == "fin" else loc - una_hora
    tz = ZoneInfo(zona)
    estandar = civil.dt.tz_localize(tz, ambiguous=False, nonexistent="shift_forward")
    verano = civil.dt.tz_localize(tz, ambiguous=True, nonexistent="shift_forward")
    sin_desplazar = civil.dt.tz_localize(tz, ambiguous=False, nonexistent="NaT")
    ambigua = estandar.notna() & verano.notna() & (estandar != verano)
    inexistente = civil.notna() & sin_desplazar.isna()
    resta = una_hora if convencion == "fin" else pd.Timedelta(0)
    ts = estandar.dt.tz_convert("UTC").dt.tz_localize(None) - resta
    alt = verano.dt.tz_convert("UTC").dt.tz_localize(None) - resta
    qc = pd.Series("civil_univoca", index=loc.index, dtype=object)
    qc[ambigua] = "civil_ambigua_estandar"
    qc[inexistente] = "civil_inexistente_desplazada"
    out = pd.DataFrame({"ts_utc": ts, "ts_utc_alternativo": alt.where(ambigua), "qc_hora": qc})
    out.attrs["biblioteca_zona"] = type(estandar.dt.tz).__module__
    return out


def convertir(ts_local, veredicto_por_anio: dict[int, str], zona: str, convencion: str | None = None) -> pd.DataFrame:
    """Paso a UTC de una serie: la regla general (UTC−4 fijo) salvo en los años con veredicto ``hora_civil``, que
    se convierten con la zona IANA (P9) y la ``convencion`` de etiqueta, obligatoria si hay algún año civil.
    Devuelve ``ts_utc``, ``ts_utc_alternativo``, ``qc_hora`` y ``reloj``."""
    loc = pd.to_datetime(pd.Series(ts_local)).reset_index(drop=True)
    out = pd.DataFrame({"ts_utc": utc_fijo(loc), "ts_utc_alternativo": pd.Series(pd.NaT, index=loc.index,
                                                                                 dtype="datetime64[ns]"),
                        "qc_hora": "fijo", "reloj": "fijo"})
    civiles = sorted(int(a) for a, v in (veredicto_por_anio or {}).items() if v == CIVIL)
    if civiles:
        m = loc.dt.year.isin(civiles).to_numpy()
        if m.any():
            if convencion is None:
                raise SystemExit("hay años con veredicto hora_civil y falta la convención de la etiqueta civil "
                                 f"({CONVENCIONES}); la elige elegir_convencion (T4)")
            c = utc_civil(loc[m], zona, convencion)
            out.loc[m, "ts_utc"] = c["ts_utc"].to_numpy()
            out.loc[m, "ts_utc_alternativo"] = c["ts_utc_alternativo"].to_numpy()
            out.loc[m, "qc_hora"] = c["qc_hora"].to_numpy()
            out.loc[m, "reloj"] = "civil"
    out["ts_utc"] = pd.to_datetime(out["ts_utc"])
    return out


# ---------------------------------------------------------------------------
# Lectura del derivado (varias raíces) y verificación de la red
# ---------------------------------------------------------------------------
def _inv(texto: str) -> tuple:
    return tuple(-ord(ch) for ch in texto) + (1,)


def version_sinca(carpeta: Path) -> Path | None:
    """Réplica de ``_comun_modelo.version_sinca`` (``_comun_modelo.py:602-643``): la versión con ``since`` más
    temprano, luego ``until`` más tardío, luego ``created_utc`` más reciente; sin manifiesto, la de más filas."""
    candidatas = []
    for obs in Path(carpeta).glob("version=*/observaciones.parquet"):
        mani = obs.parent / "manifest.json"
        since, until, creado, filas = "9999", "0000", "", 0
        if mani.exists():
            try:
                m = json.loads(mani.read_text(encoding="utf-8"))
                inp = m.get("inputs", {}) if isinstance(m.get("inputs"), dict) else {}
                since = str(inp.get("since") or m.get("since") or since)
                until = str(inp.get("until") or m.get("until") or until)
                creado = str(m.get("created_utc") or "")
                filas = int(next((f.get("rows", 0) for f in m.get("files", [])
                                  if f.get("name") == "observaciones.parquet"), 0))
            except (ValueError, TypeError, AttributeError):
                pass
        if filas == 0:
            try:
                import pyarrow.parquet as pq
                filas = int(pq.read_metadata(obs).num_rows)
            except Exception:  # noqa: BLE001
                filas = 0
        candidatas.append((since, until, creado, filas, obs))
    if not candidatas:
        return None
    candidatas.sort(key=lambda c: (c[0], _inv(c[1]), _inv(c[2]), -c[3]))
    return candidatas[0][4]


def series_del_derivado(raices, contaminantes) -> list[dict]:
    """Series (estación, contaminante, ruta) de una o varias raíces del derivado; una estación × contaminante que
    aparece en dos raíces es un error (la red 2 tiene un solo derivado por serie)."""
    vistas: dict[tuple[str, str], dict] = {}
    for raiz in raices:
        for pol in contaminantes:
            for carpeta in sorted(Path(raiz).glob(f"estacion=*/contaminante={pol}")):
                est = carpeta.parent.name.split("=", 1)[1]
                ruta = version_sinca(carpeta)
                if ruta is None:
                    continue
                clave = (est, pol)
                if clave in vistas:
                    raise SystemExit(f"{est} {pol} aparece en dos raíces del derivado; la red 2 usa una sola")
                vistas[clave] = {"estacion": est, "contaminante": pol, "ruta": ruta, "raiz": str(raiz)}
    return [vistas[k] for k in sorted(vistas)]


def huellas_de(registro: dict) -> dict[tuple[str, str], str]:
    """{(estación, contaminante): sha256 de su ``observaciones.parquet``} de un registro de ``series_con_huella``."""
    return {(str(s["estacion"]), str(s["contaminante"])): str(s["sha256"]) for s in registro["series"]}


def leer_serie(s: dict, columnas, huellas: dict | None = None, quien: str = "reloj_sinca_v2") -> pd.DataFrame:
    """Las ``columnas`` del ``observaciones.parquet`` de una serie. Con ``huellas`` (``huellas_de`` del registro de
    ``series_con_huella``; ronda 5 de la traducción, menor 3) lee los bytes del archivo una sola vez, calcula su sha256,
    lo compara con el registrado y lee la tabla desde esos mismos bytes: lo que se lee es lo que se registró, aunque el
    archivo cambie entre el registro y la lectura. Si no calza, o la serie no está registrada, se detiene antes de
    escribir nada con lo leído."""
    import io

    if huellas is None:
        return pd.read_parquet(s["ruta"], columns=list(columnas))
    clave = (str(s["estacion"]), str(s["contaminante"]))
    registrada = huellas.get(clave)
    if registrada is None:
        raise SystemExit(f"{quien}: {clave[0]}:{clave[1]} no está entre las series registradas con su huella")
    datos = Path(s["ruta"]).read_bytes()
    real = hashlib.sha256(datos).hexdigest()
    if real != registrada:
        raise SystemExit(f"{quien}: {clave[0]}:{clave[1]}: su observaciones.parquet cambió después de registrar su huella "
                         f"(registrada {registrada[:8]}…, el archivo que se lee {real[:8]}…): no se lee ni se escribe "
                         f"nada con él")
    return pd.read_parquet(io.BytesIO(datos), columns=list(columnas))


def verificar_red(series: list[dict], region_de: dict[str, str], politica: dict,
                  anios: tuple[int, int] = ANIOS_POR_OMISION, huellas: dict | None = None,
                  quien: str = "reloj_sinca_v2") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Veredictos de todas las series. ``region_de``: región SINCA por estación (de los maestros de R8); una serie
    cuya estación no está en los maestros no se evalúa (como el original, ``:137``). Con ``huellas`` cada serie se lee
    desde los bytes cuyo sha256 es el registrado (``leer_serie``)."""
    filas, detalle = [], []
    for s in series:
        est = s["estacion"]
        if est not in region_de:
            continue
        cols = ["ts_local", "hora_repetida_en_fuente"]
        df = leer_serie(s, cols, huellas, quien)
        zona = zona_de(region_de[est], politica)
        f, d = verificar_serie(df["ts_local"], zona, df["hora_repetida_en_fuente"].fillna(False).to_numpy(bool),
                               anios)
        for x in f:
            x.update({"estacion": est, "contaminante": s["contaminante"]})
        for x in d:
            x.update({"estacion": est, "contaminante": s["contaminante"]})
        filas += f
        detalle += d
    cols = ["estacion", "contaminante", "anio", "zona_iana"] + [f"{c}_{v}" for v in CONVENCIONES for c in
                                                                 ("n_transiciones", "estados", "veredicto")]
    return pd.DataFrame(filas, columns=cols), pd.DataFrame(detalle)


def convencion_requerida(tabla: pd.DataFrame) -> bool:
    """¿Hay algún estación-año con veredicto ``hora_civil`` en alguna de las dos convenciones?"""
    return bool(any((tabla.get(f"veredicto_{c}", pd.Series(dtype=object)) == CIVIL).any() for c in CONVENCIONES))


def elegir_convencion(tabla: pd.DataFrame) -> dict:
    """T4 con la unidad de T9: la convención de la etiqueta civil para todo SINCA. Votan las unidades del veredicto de
    R7, estación × contaminante × año local (una fila de ``verificar_red``). Se cuentan las que dan ``hora_civil`` con
    una convención y no con la otra; gana la de más y, si empatan (también en cero), ``inicio_mas_1h``. Usa sólo los
    veredictos, que salen de las etiquetas de los días de cambio de hora. Devuelve la elegida y los dos conteos."""
    if len(tabla) and tabla.duplicated(["estacion", "contaminante", "anio"]).any():
        raise ValueError("la tabla de veredictos repite una unidad estación × contaminante × año")
    a, b = CONVENCIONES
    if not len(tabla):
        civil = {c: pd.Series(dtype=bool) for c in CONVENCIONES}
    else:
        civil = {c: tabla[f"veredicto_{c}"].astype(str) == CIVIL for c in CONVENCIONES}
    conteos = {f"solo_{a}": int((civil[a] & ~civil[b]).sum()), f"solo_{b}": int((civil[b] & ~civil[a]).sum())}
    if conteos[f"solo_{a}"] == conteos[f"solo_{b}"]:
        elegida, empate = DESEMPATE, True
    else:
        elegida, empate = (a, False) if conteos[f"solo_{a}"] > conteos[f"solo_{b}"] else (b, False)
    return {"regla": "T4 (unidad de T9)", "decision": DECISION_T4,
            "unidad": "estación × contaminante × año local (el veredicto de R7)",
            "conteos": conteos, "empate": empate, "elegida": elegida, "unidades": int(len(tabla))}


def veredictos_por_serie(tabla: pd.DataFrame, convencion: str | None) -> dict[tuple[str, str], dict[int, str]]:
    """{(estación, contaminante): {año: veredicto}} con la convención elegida. Sin convención sólo se puede seguir si
    ningún estación-año da ``hora_civil`` en ninguna de las dos (todo queda en la regla general)."""
    if convencion is None:
        if convencion_requerida(tabla):
            raise SystemExit("hay estación-años con veredicto hora_civil y falta la convención de la etiqueta civil "
                             f"({CONVENCIONES}); la elige elegir_convencion (T4)")
        return {}
    if convencion not in CONVENCIONES:
        raise ValueError(f"convención de etiqueta desconocida: {convencion!r}")
    out: dict[tuple[str, str], dict[int, str]] = {}
    for est, pol, anio, v in zip(tabla["estacion"], tabla["contaminante"], tabla["anio"], tabla[f"veredicto_{convencion}"]):
        out.setdefault((str(est), str(pol)), {})[int(anio)] = str(v)
    return out


def raiz_portable(raiz, datos) -> str:
    """Raíz del derivado relativa a la carpeta que contiene la raíz de datos (``derived/…``), sin rutas absolutas."""
    p, base = Path(raiz).resolve(), Path(datos).resolve().parent
    return p.relative_to(base).as_posix() if p.is_relative_to(base) else p.name


def sha256_archivo(ruta) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 22), b""):
            h.update(bloque)
    return h.hexdigest()


def series_con_huella(raices, datos, contaminantes=CONTAMINANTES_SINCA) -> tuple[dict, list[dict]]:
    """Las series del derivado (``series_del_derivado``) con su identidad: estación, contaminante, versión y sha256 de
    su ``observaciones.parquet``, más las raíces (portables) y los contaminantes. Es lo que registra el reloj y lo que
    el panel exige idéntico. T8: el ``manifest.json`` de cada versión tiene que declarar el contrato del preparador,
    el ``afg_lib.py`` de la v1 y el preparador sellado (``derivado_red2_v2.contrato_de_la_version``); cada serie
    registra además la sintaxis de ``afg_lib`` con la versión de Python con que se armó. Devuelve (registro, series)."""
    import derivado_red2_v2 as dr

    series = series_del_derivado(raices, contaminantes)
    lista = []
    for s in series:
        sha = sha256_archivo(s["ruta"])
        lista.append({"estacion": s["estacion"], "contaminante": s["contaminante"],
                      "version": Path(s["ruta"]).parent.name.split("=", 1)[1], "sha256": sha,
                      # T8 y la publicación del preparador: files[].sha256, version y digest(inputs) (cuarta revisión,
                      # menor 4)
                      "procedencia_afg": dr.contrato_de_la_version(s["ruta"], sha)})
    registro = {"raices": [raiz_portable(x, datos) for x in raices], "contaminantes": sorted(contaminantes),
                "series": lista,
                "huella_series": hashlib.sha256(json.dumps(lista, sort_keys=True).encode("utf-8")).hexdigest()}
    return registro, series


def origen_portable(carpeta) -> str:
    """La carpeta de una base de zonas sin rutas de usuario: dentro del entorno de Python, «<entorno NOMBRE>/…» (su
    prefijo con el nombre); dentro de la carpeta personal, «~/…»; si no, la ruta completa (``/usr/share/zoneinfo``)."""
    d = Path(carpeta).resolve()
    for base, nombre in ((Path(sys.prefix).resolve(), f"<entorno {Path(sys.prefix).name}>"), (Path.home().resolve(), "~")):
        if d == base or d.is_relative_to(base):
            return "/".join([nombre, *d.relative_to(base).parts])
    return d.as_posix()


def exigir_base_de_zonas(base: dict, quien: str = "reloj_sinca_v2") -> dict:
    """Quinta revisión, menor 3: la base de zonas con que se elige T4 y se pasa a UTC tiene que dar las horas civiles
    especiales fijadas (``HORAS_ESPECIALES``: 132 en 2000-2026, 96a7b7cb…); si no, se detiene. Devuelve lo fijado."""
    if (base.get("horas_especiales"), base.get("huella_horas_especiales")) != \
            (HORAS_ESPECIALES["horas"], HORAS_ESPECIALES["sha256"]):
        raise SystemExit(f"{quien}: la base de zonas horarias de este entorno da {base.get('horas_especiales')} horas "
                         f"especiales en {ANIOS_POR_OMISION[0]}-{ANIOS_POR_OMISION[1]} (huella "
                         f"{str(base.get('huella_horas_especiales'))[:8]}…), no las {HORAS_ESPECIALES['horas']} fijadas "
                         f"({HORAS_ESPECIALES['sha256'][:8]}…, la base de amb_v2): con otra base cambian la elección de T4 "
                         f"y el paso a UTC")
    return {"horas": HORAS_ESPECIALES["horas"], "sha256": HORAS_ESPECIALES["sha256"],
            "anios": list(HORAS_ESPECIALES["anios"])}


def anios_sin_cambio_de_hora(zonas, anios: tuple[int, int] = ANIOS_POR_OMISION) -> dict[str, list[int]]:
    """Los años del período sin ningún cambio de hora en cada zona (con la base de zonas del entorno): los que dan
    ``sin_transiciones`` (con amb_v2: 2015 en las tres zonas; America/Punta_Arenas, 2017-2026; America/Coyhaique,
    2025-2026)."""
    return {z: [a for a in range(int(anios[0]), int(anios[1]) + 1)
                if not any(transiciones(z, a, c) for c in CONVENCIONES)] for z in sorted(set(zonas))}


def sin_transiciones_junto_a_civil(tabla: pd.DataFrame, convencion: str | None) -> list[dict]:
    """Límite de R7 (quinta revisión, menor 4): las unidades estación × contaminante × año con veredicto
    ``sin_transiciones`` (un año sin cambio de hora en su zona) cuyo año anterior o siguiente da ``hora_civil`` con la
    convención elegida. Siguen la regla general (UTC−4 fijo); si su exportador seguía en hora civil, que esos años es
    −03 todo el año, sus horas quedan con 1 h de error todo el año. Sólo se cuentan: la regla no cambia."""
    if convencion is None or not len(tabla):
        return []
    col = f"veredicto_{convencion}"
    v = {(str(e), str(p), int(a)): (str(x), str(z)) for e, p, a, x, z in
         zip(tabla["estacion"], tabla["contaminante"], tabla["anio"], tabla[col], tabla["zona_iana"])}
    out = []
    for (e, p, a), (x, z) in sorted(v.items()):
        vecinos = [b for b in (a - 1, a + 1) if v.get((e, p, b), ("",))[0] == CIVIL]
        if x == "sin_transiciones" and vecinos:
            out.append({"estacion": e, "contaminante": p, "anio": a, "zona_iana": z, "vecinos_hora_civil": vecinos})
    return out


def limite_sin_transiciones(tabla: pd.DataFrame, convencion: str | None, zonas,
                            anios: tuple[int, int] = ANIOS_POR_OMISION) -> dict:
    """Lo que el reloj declara del límite de R7: los años sin cambio de hora por zona y las unidades de
    ``sin_transiciones_junto_a_civil`` con la convención elegida (van al resumen, al json del panel y al anexo)."""
    unidades = sin_transiciones_junto_a_civil(tabla, convencion)
    return {"regla": "R7: un año sin cambio de hora en su zona da sin_transiciones y sigue la regla general (UTC−4 "
                     "fijo); si el exportador estaba en hora civil (−03 todo ese año), sus horas quedan con 1 h de error "
                     "todo el año. No votan en T4. Se cuentan las de año anterior o siguiente hora_civil con la "
                     "convención elegida; la regla no cambia",
            "convencion": convencion, "anios_sin_cambio_de_hora": anios_sin_cambio_de_hora(zonas, anios),
            "unidades_junto_a_civil": unidades, "n": len(unidades)}


def base_de_zonas(zonas, anios: tuple[int, int] = ANIOS_POR_OMISION) -> dict:
    """Procedencia de la base de zonas horarias: de dónde salió cada zona (carpeta de ``zoneinfo.TZPATH``, con su ruta
    completa sin rutas de usuario, ``origen_portable``, o el paquete ``tzdata``), el sha256 de su archivo (lo único que
    distingue dos bases con el mismo nombre de carpeta), la versión de ``tzdata`` si está instalado, y las horas civiles
    especiales
    del período con su huella (dos bases distintas dan el mismo paso a UTC si esa huella coincide). ``conversion``
    dice con qué biblioteca convierte ``utc_civil``: la que de verdad usó una conversión de prueba con ``utc_civil``
    (``attrs["biblioteca_zona"]``; «zoneinfo», la misma base del veredicto), no una muestra aparte; y, si pytz está
    instalado, su versión y la de su base, que ya no se usa."""
    import importlib.metadata
    import importlib.resources
    import zoneinfo

    archivos = {}
    for z in sorted(set(zonas)):
        origen, datos = "desconocido", None
        for d in zoneinfo.TZPATH:
            q = Path(d) / z
            if q.is_file():
                origen, datos = "TZPATH: " + origen_portable(d), q.read_bytes()
                break
        if datos is None:
            try:
                datos = importlib.resources.files("tzdata.zoneinfo").joinpath(*z.split("/")).read_bytes()
                origen = "paquete tzdata"
            except Exception:  # noqa: BLE001
                datos = None
        archivos[z] = {"origen": origen, "sha256": hashlib.sha256(datos).hexdigest() if datos else None}
    try:
        version = importlib.metadata.version("tzdata")
    except importlib.metadata.PackageNotFoundError:
        version = None
    horas = [[z, c.isoformat(), tipo] for z in sorted(set(zonas)) for a in range(anios[0], anios[1] + 1)
             for c, tipo in horas_civiles_especiales(z, a) if c.year == a]
    prueba = utc_civil(pd.Series(pd.to_datetime(["2023-01-01 12:00"])), sorted(set(zonas))[0], CONVENCIONES[0]) \
        if zonas else None
    conversion = {"utc_civil": "ZoneInfo(zona) pasado a pandas.Series.dt.tz_localize",
                  "biblioteca": None if prueba is None else prueba.attrs.get("biblioteca_zona"),
                  "pandas": pd.__version__}
    try:
        import pytz
        conversion["pytz_no_se_usa"] = {"version": getattr(pytz, "__version__", None),
                                        "olson": getattr(pytz, "OLSON_VERSION", None)}
    except ImportError:
        conversion["pytz_no_se_usa"] = None
    return {"archivos": archivos, "tzdata": version, "horas_especiales": len(horas),
            "huella_horas_especiales": hashlib.sha256(json.dumps(horas).encode("utf-8")).hexdigest(),
            "conversion": conversion}


def ejecutar_reloj(r, raices, anios: tuple[int, int] = ANIOS_POR_OMISION, contaminantes=CONTAMINANTES_SINCA,
                   escribir: bool = True, cfg=None, estado=None, region_de: dict | None = None,
                   politica: dict | None = None) -> tuple[dict, pd.DataFrame, str]:
    """Verificación del reloj sobre el derivado de la red 2 y elección de T4. Devuelve (resumen, veredictos, estado).

    Para escribir exige, antes de leer ninguna serie: la traducción confirmada en git (R22); todo SINCA (2000-2026 y
    los tres contaminantes); la política temporal por su huella y las regiones de los maestros de R8 (``region_de`` y
    ``politica`` sólo se pueden dar sin escribir); la base de zonas con las horas especiales fijadas
    (``exigir_base_de_zonas``); la lista cerrada antes de leer los maestros; y que el derivado sea el de la red 2
    completo (``derivado_red2_v2.exigir_derivado_completo``: una raíz, la de ``destino_por_omision``; su última
    corrida terminada, con el ``plan.json`` y la huella rastreada de ``derivado_red2_v2.py``; el conjunto estación ×
    contaminante de R2; las versiones de esa corrida; y cada versión sin ventana y con exactamente sus fuentes de los tres
    manifiestos de la lista cerrada). Cada serie se lee desde los bytes cuyo sha256 registró (``leer_serie``). El
    resumen declara el límite de R7
    (``limite_sin_transiciones``) y, al escribirse, su procedencia (``red_ampliada_v2.traza_red2``: commit, código,
    bibliotecas, hilos y la traducción). Se escribe una sola vez: con las mismas series y los mismos veredictos no
    toca nada; con otros, se detiene; con archivos sin su ``resumen.json``, también."""
    import _rutas_v2 as rv
    import derivado_red2_v2 as dr
    import red_ampliada_v2 as ra

    anios = (int(anios[0]), int(anios[1]))
    if escribir:
        if anios != ANIOS_POR_OMISION or sorted(contaminantes) != sorted(CONTAMINANTES_SINCA):
            raise SystemExit(f"el reloj que escribe la elección de T4 corre sobre todo SINCA: años {ANIOS_POR_OMISION} y "
                             f"contaminantes {CONTAMINANTES_SINCA}, no {anios} y {tuple(contaminantes)}")
        if region_de is not None or politica is not None:
            raise SystemExit("el reloj que escribe lee la política temporal por su huella y las regiones de los maestros "
                             "de R8: region_de y politica sólo sirven sin escribir")
    compuerta = ra.exigir_traduccion_confirmada(r, cfg, estado) if escribir else None
    if politica is None:
        politica, sha_politica = leer_politica_con_huella(RUTA_POLITICA)   # por su huella (menor 17)
    else:
        sha_politica = None                                   # dada a mano (sólo sin escribir): no se registra
    zonas = [politica["zona_iana_default"], *politica["zonas_iana_por_region"].values()]
    zonas_horarias = base_de_zonas(zonas, anios)
    if escribir:                                              # antes de leer los maestros y las series (menor 3)
        zonas_horarias["fijadas"] = exigir_base_de_zonas(zonas_horarias)
    if region_de is None:
        ra.verificar_lista_cerrada(r.datos)                   # antes de leer los maestros
        maestro = ra.maestro_red2(r.datos)
        region_de = dict(zip(maestro["estacion"], maestro["region_sinca"]))
    registro, series = series_con_huella(raices, r.datos, contaminantes)
    derivado = dr.exigir_derivado_completo(raices, series, r.datos, "reloj_sinca_v2") if escribir else None
    tabla, detalle = verificar_red(series, region_de, politica, anios, huellas=huellas_de(registro))
    con_veredicto = tabla.groupby(["estacion", "contaminante"]).size().to_dict() if len(tabla) else {}
    evaluacion = [{"estacion": s["estacion"], "contaminante": s["contaminante"],
                   "evaluada": s["estacion"] in region_de,
                   "region_sinca": region_de.get(s["estacion"]),
                   "zona_iana": zona_de(region_de[s["estacion"]], politica) if s["estacion"] in region_de else None,
                   "anios_con_veredicto": int(con_veredicto.get((s["estacion"], s["contaminante"]), 0))}
                  for s in registro["series"]]
    eleccion = elegir_convencion(tabla)
    resumen = {"schema": SCHEMA, "regla": "UTC−4 fijo salvo veredicto hora_civil (P9)",
               "convenciones": {"evaluadas": list(CONVENCIONES), "decision": "T4 con la unidad de T9 (elegir_convencion)",
                                "fuente": FUENTE_CONVENCION},
               "original": {"archivo": "scripts_modelo_1km/verificar_reloj_sinca.py", "sha256": SHA_ORIGINAL},
               "politica_temporal_sha256": sha_politica, "anios": list(anios),
               "derivado": derivado, "minimo_etiquetas_anio": MINIMO_ETIQUETAS_ANIO,
               "contaminantes": registro["contaminantes"], "raices": registro["raices"],
               "series_registradas": registro["series"], "huella_series": registro["huella_series"],
               "evaluacion_por_serie": evaluacion, "zonas_horarias": zonas_horarias,
               "series": len(series), "unidades_con_veredicto": int(len(tabla)),
               "resumen_veredictos": {c: tabla[f"veredicto_{c}"].value_counts().to_dict() for c in CONVENCIONES}
               if len(tabla) else {},
               "hora_civil": {c: tabla.loc[tabla[f"veredicto_{c}"] == CIVIL, ["estacion", "contaminante", "anio"]]
                              .to_dict("records") for c in CONVENCIONES} if len(tabla) else {},
               "convencion_requerida": convencion_requerida(tabla),
               "convencion_civil": eleccion,
               "limite_sin_transiciones": limite_sin_transiciones(tabla, eleccion["elegida"], zonas, anios),
               "huella_veredictos_contenido": hashlib.sha256(tabla.to_csv(index=False).encode("utf-8")).hexdigest()}
    if not escribir:
        return resumen, tabla, "sin_escribir"
    salida = r.raiz_v2 / NOMBRE_SALIDA
    destinos = [salida / "veredictos.parquet", salida / "detalle_transiciones.csv", salida / "resumen.json"]
    with rv.candado_artefactos(destinos, r):
        previo = rv.leer_json(destinos[2])
        if previo is not None:
            iguales = (previo.get("huella_series"), previo.get("huella_veredictos_contenido")) == \
                (resumen["huella_series"], resumen["huella_veredictos_contenido"])
            if not iguales:
                raise SystemExit(f"{NOMBRE_SALIDA}/resumen.json ya existe con otras series u otros veredictos: el reloj "
                                 f"se escribe una sola vez")
            return previo, tabla, "sin_cambios"
        if destinos[0].exists() or destinos[1].exists():
            raise SystemExit(f"{NOMBRE_SALIDA} tiene archivos sin su resumen.json: revisa a mano antes de seguir")
        # §0 del contrato: commit, código, bibliotecas, hilos y traducción (no entra en la comparación de arriba)
        resumen["traza"] = ra.traza_red2(r, compuerta, {"politica_temporal": RUTA_POLITICA,
                                                        "maestro_actuales": Path(r.datos) / ra.MAESTRO_ACTUALES,
                                                        "maestro_nuevas": Path(r.datos) / ra.MAESTRO_NUEVAS},
                                         None, 1, programa="reloj_sinca_v2")
        resumen["sha256_veredictos"] = rv.publicar_parquet(tabla, destinos[0], r)
        resumen["sha256_detalle"] = rv.publicar_csv(detalle, destinos[1], r)
        rv.publicar_json(resumen, destinos[2], r)
    return resumen, tabla, "escrito"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verificación corregida del reloj SINCA sobre el derivado de la red 2.")
    ap.add_argument("--derivado", nargs="+", required=True, type=Path, help="raíz o raíces del derivado SINCA red 2")
    ap.add_argument("--anios", default=f"{ANIOS_POR_OMISION[0]}-{ANIOS_POR_OMISION[1]}",
                    help="sólo con --no-escribir: el reloj que escribe corre con 2000-2026")
    ap.add_argument("--contaminantes", default=",".join(CONTAMINANTES_SINCA),
                    help="sólo con --no-escribir: el reloj que escribe corre con los tres")
    ap.add_argument("--no-escribir", action="store_true", help="calcula y resume sin escribir")
    args = ap.parse_args(argv)
    import _rutas_v2 as rv

    a0, a1 = (int(x) for x in args.anios.split("-"))
    resumen, _, estado = ejecutar_reloj(rv.rutas_v2(), args.derivado, (a0, a1), args.contaminantes.split(","),
                                        escribir=not args.no_escribir)
    print(json.dumps({**{k: resumen[k] for k in ("series", "unidades_con_veredicto", "resumen_veredictos")},
                      "convencion_civil": {k: resumen["convencion_civil"][k] for k in ("conteos", "empate", "elegida")},
                      "estado": estado}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(AQUI))
    sys.exit(main())
