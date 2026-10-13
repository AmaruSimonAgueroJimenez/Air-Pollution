#!/usr/bin/env python3
"""Bandera de calidad del blanco v2: ``qc_observacion`` de SINCA y ``usable_native`` de SNIFA, fila a fila del panel.

Traduce la primera parte de §7 del contrato ``DISENO_AMBIENTAL_V2.md`` (calidad del blanco, etapa 9, sin descargas
nuevas): lleva al panel v2 la bandera de calidad de cada observación, uniendo por estación × hora UTC. Escribe
``<raíz v2>/paneles/calidad_<pol>.parquet`` con cuatro columnas, **alineado 1 a 1** con el panel v1
``<raíz v1>/paneles/panel_<pol>.parquet`` (sólo lectura): la fila i de la bandera es la fila i del panel, con la misma
``estacion`` y el mismo ``ts_utc``. Al lado queda ``calidad_<pol>.json``, con la conciliación, la distribución y la traza.

* ``qc``. En SINCA, ``validado``, ``preliminar`` o ``no_validado``: el ``qc_observacion`` del derivado
  ``derived/modelado/SINCA/v1``, el mismo que lee ``_comun_modelo.py:646-669``. Dice de cuál de las tres columnas del
  CSV original salió el valor (el primero finito entre validado, preliminar y no validado). En SNIFA,
  ``usable_native`` si la hora es ``numeric_usable`` y ``usable_native``, y ``solo_numeric_usable`` si es
  ``numeric_usable`` pero no ``usable_native`` (conflicto de valor o de código entre publicaciones). La v1 entrena
  con ``numeric_usable`` (``_red_adicional.py:62``), así que toda fila SNIFA del panel tiene una de las dos. Nulo
  sólo si la fila no se pudo conciliar; el motivo queda en el JSON y, por omisión, entonces no se escribe nada.
* ``fuente``: ``sinca`` o ``snifa``, las redes del panel v1 (``produccion.py:40-41``; columna ``version`` igual a
  ``snifa`` en las filas de la red adicional, ``_red_adicional.py:118``).

**Convención horaria.** La misma con que la v1 construyó el panel, verificada en el código y en los datos:

* SINCA: reloj UTC−4 fijo con la etiqueta al fin del intervalo (``_comun_modelo.py:81-82``). El inicio del bin UTC
  es ``ts_local + 3 h`` (``sinca_local_a_bin_utc``, ``_comun_modelo.py:97-106``, aplicada en ``:666``). El panel lo
  declara en ``reloj_sinca = "UTC-4 fijo; etiqueta=fin"`` (``qmd:2064``) y de ahí se lee. Además se mide con los
  datos: con +3 h todas las filas SINCA del panel encuentran su observación con el mismo valor; con +2, +4 o +5 h no.
* SNIFA: la convención se decide documento a documento (si la etiqueta máxima del documento es 24, la hora local de
  inicio es la etiqueta − 1) y se suman 4 h fijas (``_red_adicional.py:37``, ``65-69`` y ``114-115``). El máximo se
  toma sobre las filas ya filtradas (NO2, ``numeric_usable``, unidad y rango), como en la v1.

**Réplica y conciliación.** Se reconstruyen las series de la v1 con sus mismas reglas: versión del derivado por
``version_sinca``, ``seleccionada``, ``obs`` no nula y en rango, agregación por estación × hora; red SNIFA con
``numeric_usable``, unidad aceptada, factor y rango. Se marcan las rachas de 24 o más valores idénticos
(``produccion.py:78-88``) y se recorta al período y a las estaciones con celda (``qmd:2004-2010``). Una fila del panel
recibe la bandera de su observación sólo si coinciden el valor (``obs`` en float32, ``qmd:2058-2060``), el número de
registros promediados (``n``) y la red. La conciliación informa también lo que la réplica deja y el panel no tiene.
La versión SINCA que se lee es la que registra el panel (columna ``version``); si ya no fuera la que elige
``version_sinca``, se avisa.

**Horas agregadas.** El panel promedia los registros de una misma estación × hora (``_comun_modelo.py:667-668``,
``_red_adicional.py:117``). La bandera de una hora agregada es la peor de sus registros: ``validado`` < ``preliminar``
< ``no_validado`` y ``usable_native`` < ``solo_numeric_usable``. Así, una variante «sólo validado» no admite un
promedio que incluya un valor no validado. En los paneles vigentes sólo ocurre en 34 horas SNIFA de El Peñón.

**Inmutabilidad.** La bandera define las variantes de entrenamiento de §7, así que no se reescribe en silencio. Si ya
existe con la misma huella, no se toca; si la huella difiere, el programa se detiene. ``--reemplazar`` la reemplaza,
guarda la anterior con fecha y lo anota en la bitácora.

En ``output_files/modelo_1km_v2/`` quedan tres tablas: distribución por contaminante, red y año; por estación; y la
comparación con la auditoría del 2026-10-12. Las acompaña ``calidad_v2_tablas.json``, con el sha256 de cada tabla y
su traza.

Uso::

    python -B scripts_modelo_1km/v2/calidad_v2.py                 # calcula, concilia y fija las banderas
    python -B scripts_modelo_1km/v2/calidad_v2.py --no-escribir   # sólo calcula y resume
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rutas_v2 import (  # noqa: E402
    RutasV2, ahora_utc, candado_escritura, cargar_config, leer_json, publicar_bytes, publicar_json,
    publicar_parquet, renombrar, rutas_v2,
)
from _traza_v2 import fijar_hilos, sha256_archivo, sha256_json, traza  # noqa: E402
from pliegues_v2 import INSUMOS_GRILLA, estaciones_con_celda, leer_estaciones_sinca  # noqa: E402

log = logging.getLogger("modelo_1km_v2.calidad")

SCHEMA = "airpollution.modelo-1km-v2.calidad.v1"
SCHEMA_TABLAS = "airpollution.modelo-1km-v2.calidad-tablas.v1"
NOMBRE_LATERAL = "calidad_v2_tablas.json"
TABLA_DISTRIBUCION = "calidad_v2_distribucion_anual.csv"
TABLA_ESTACIONES = "calidad_v2_estaciones.csv"
TABLA_AUDITORIA = "calidad_v2_auditoria.csv"
CANDADO = "calidad"
CONTAMINANTES = ("pm25", "no2")
COLUMNAS = ["estacion", "ts_utc", "qc", "fuente"]
COLUMNAS_PANEL = ["estacion", "ts_utc", "obs", "n", "version", "anio"]

# Códigos de la bandera, de mejor a peor dentro de cada red. Los de SINCA son los valores de qc_observacion del
# derivado; los de SNIFA resumen sus dos banderas (en el panel v1, numeric_usable siempre es verdadera).
QC_SINCA = ("validado", "preliminar", "no_validado")
QC_SNIFA = ("usable_native", "solo_numeric_usable")
QC_TODOS = QC_SINCA + QC_SNIFA
CODIGO_QC = {c: i for i, c in enumerate(QC_TODOS)}
SIN_BANDERA = "sin_bandera"                  # sólo en conteos y tablas; en el parquet la bandera es nula
CATEGORIAS = QC_TODOS + (SIN_BANDERA,)
RED_SINCA, RED_SNIFA = "sinca", "snifa"
FUENTES = (RED_SINCA, RED_SNIFA)
QC_DE_FUENTE = {RED_SINCA: QC_SINCA, RED_SNIFA: QC_SNIFA}

# --- Reglas de la v1, replicadas (no se importa _comun_modelo para no heredar su raíz de datos) ---------------------
RANGO_VALIDO = {"pm25": (0.0, 1500.0), "no2": (0.0, 1000.0)}                  # _comun_modelo.py:78
COLUMNAS_SINCA = ["ts_local", "obs", "qc_observacion", "seleccionada"]           # _comun_modelo.py:656
PATRON_RELOJ = re.compile(r"UTC-(\d+) fijo; etiqueta=(fin|inicio)")              # qmd:2064 (_comun_modelo.py:81-82)
VAR_DERIVADOS = "AIR_POLLUTION_DERIVED_ROOT"                                      # _comun_modelo.py:66
SUBRUTA_SINCA = ("modelado", "SINCA", "v1")                                       # _comun_modelo.py:67

# Red adicional SNIFA: réplica de _red_adicional.py:37-38 y 42-50 (código del panel y factor de µg/m³N a ppb).
OFFSET_UTC_H_SNIFA = 4
PPB_POR_UG_M3N_NO2 = 22.414 / 46.0055
ESTACIONES_SNIFA = {"charrua": ("SNIFA-CHARRUA", 1.0), "progreso": ("SNIFA-PROGRESO", 1.0),
                    "el_penon": ("SNIFA-ELPENON", PPB_POR_UG_M3N_NO2)}
CONTAMINANTES_SNIFA = ("no2",)
UNIDADES_SNIFA = ("ppb", "ppbv", "ug/m3N")
COLUMNAS_SNIFA = ["station_id", "pollutant", "numeric_usable", "usable_native", "date_local", "hour_index", "value",
                  "unit", "document_id", "value_conflict", "quality_conflict"]

NS_POR_HORA = 3_600_000_000_000
BASE_CLAVE = 10_000_000          # clave = código de estación × BASE + horas desde 1970 (alcanza hasta el año 3110)
DESFASES_DE_PRUEBA = (2, 3, 4, 5)

# --- Auditoría del 2026-10-12 (sólo referencia para comparar; repositorio Air-Pollution-Health-Chile) --------------
AUDITORIA = {
    "referencia": "Air-Pollution-Health-Chile/auditoria/20261012",
    "sinca_antes_de_rachas": {
        "base": "filas SINCA válidas del período antes del filtro de rachas (seleccionada, obs no nula y en rango)",
        "referencia": ("ambiental_modelo.md:280 (AM-02) y :192; validadas y porcentajes: ambiental_modelo.json "
                       "(calidad_sinca_usada)"),
        "nota": ("El md redondea los porcentajes del JSON (37,75 y 67,59) a 37,8 % y 67,6 %. En PM2,5 el valor exacto "
                 "es 37,746 %: el 37,8 del md es un doble redondeo, no una diferencia de recuento."),
        "pm25": {"filas": 9_789_656, "validado": 6_094_454, "preliminar": 847_459, "no_validado": 2_847_743,
                 "pct_no_validado_o_preliminar": 37.75},
        "no2": {"filas": 5_594_887, "validado": 1_813_313, "preliminar": 1_461_473, "no_validado": 2_320_101,
                "pct_no_validado_o_preliminar": 67.59},
    },
    "sinca_panel": {
        "base": "filas SINCA del panel, después del filtro de rachas",
        "referencia": "ambiental_modelo.md:202 (verificación del 2026-10-12)",
        "pm25": {"pct_no_validado_o_preliminar": 37.55},
        "no2": {"pct_no_validado_o_preliminar": 67.62},
    },
    "snifa_antes_de_rachas": {
        "base": "horas SNIFA de NO2 con numeric_usable, unidad aceptada, factor, rango y reloj de la v1, antes de rachas",
        "referencia": "ambiental_datos.md:190 y :520",
        "no2": {"horas": 155_675, "SNIFA-CHARRUA": 60_096, "SNIFA-PROGRESO": 59_105, "SNIFA-ELPENON": 36_474,
                "registros_no_usable_native": 8_931, "conflicto_de_valor": 8_873, "conflicto_de_codigo": 58,
                "horas_promediadas": 34},
    },
    "sinca_anual": {
        "base": "como sinca_antes_de_rachas, por año de la etiqueta local (ts_local); fracciones con 3 decimales",
        "referencia": "ambiental_modelo.json → calidad_sinca_por_anio",
    },
}
AUDITORIA_JSON = Path("Air-Pollution-Health-Chile") / "auditoria" / "20261012" / "ambiental_modelo.json"
VAR_AUDITORIA = "AIR_POLLUTION_AUDITORIA_AMBIENTAL"


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
def raiz_derivados(r: RutasV2, entorno: Mapping[str, str] | None = None) -> Path:
    """Raíz de los derivados del pipeline de datos: ``AIR_POLLUTION_DERIVED_ROOT`` o, si no está, la carpeta
    ``derived`` junto a la de datos crudos; es la regla de ``_comun_modelo.py:66`` (``DATA.parent / "derived"``)."""
    e = os.environ if entorno is None else entorno
    return Path(e.get(VAR_DERIVADOS) or Path(r.datos).parent / "derived").expanduser().resolve()


def derivado_sinca(raiz: Path) -> Path:
    return Path(raiz).joinpath(*SUBRUTA_SINCA)


def ruta_calidad(r: RutasV2, pol: str) -> Path:
    return r.raiz_v2 / "paneles" / f"calidad_{pol}.parquet"


def ruta_meta(r: RutasV2, pol: str) -> Path:
    return ruta_calidad(r, pol).with_suffix(".json")


def ruta_auditoria(r: RutasV2, entorno: Mapping[str, str] | None = None) -> Path:
    """JSON de la auditoría ambiental: ``AIR_POLLUTION_AUDITORIA_AMBIENTAL`` o el repositorio hermano."""
    e = os.environ if entorno is None else entorno
    return Path(e.get(VAR_AUDITORIA) or Path(r.repo).parent / AUDITORIA_JSON).expanduser()


def relativa_a(ruta, raiz, nombre: str) -> dict:
    """Ruta portable respecto de una raíz que ``RutasV2.relativa`` no conoce (derivados, repositorio hermano)."""
    p, b = Path(ruta).resolve(), Path(raiz).resolve()
    try:
        return {"raiz": nombre, "ruta": p.relative_to(b).as_posix()}
    except ValueError:
        return {"raiz": None, "ruta": p.name}


# ---------------------------------------------------------------------------
# Tiempo (funciones puras)
# ---------------------------------------------------------------------------
def desplazamiento_sinca(offset_utc_h: int, etiqueta: str) -> int:
    """Horas que se suman a la etiqueta local SINCA para llegar al inicio del bin UTC; réplica de
    ``sinca_local_a_bin_utc`` (``_comun_modelo.py:97-106``). Con la etiqueta al fin del intervalo (R.E. 1449), la hora
    18 local cubre 17:01–18:00 y su bin es 17:00 local, o sea 21:00 UTC: +3 h."""
    if etiqueta not in ("fin", "inicio"):
        raise ValueError(f"etiqueta SINCA desconocida: {etiqueta!r}")
    return int(offset_utc_h) - (1 if etiqueta == "fin" else 0)


def reloj_del_panel(meta: dict) -> dict:
    """Reloj SINCA con que la v1 construyó el panel, leído de ``reloj_sinca`` (``qmd:2064``)."""
    texto = str(meta.get("reloj_sinca") or "")
    m = PATRON_RELOJ.fullmatch(texto.strip())
    if not m:
        raise SystemExit(f"El panel no declara un reloj SINCA reconocible (reloj_sinca = {texto!r}); la v1 escribe "
                         f"«UTC-4 fijo; etiqueta=fin» (qmd:2064)")
    offset, etiqueta = int(m.group(1)), m.group(2)
    return {"reloj_sinca": texto, "offset_utc_h": offset, "etiqueta": etiqueta,
            "desplazamiento_h": desplazamiento_sinca(offset, etiqueta)}


def a_bin_utc(ts_local, desplazamiento_h: int) -> pd.Series:
    """Etiqueta local SINCA → inicio del bin horario UTC (naive, ns)."""
    ts = pd.Series(pd.to_datetime(ts_local)).astype("datetime64[ns]")
    return ts + pd.Timedelta(hours=int(desplazamiento_h))


def periodo_del_panel(meta: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Período de calibración por día local, como ``observaciones_panel`` (``qmd:2007-2009``): [desde, hasta + 1 día)."""
    desde, hasta = meta.get("desde"), meta.get("hasta")
    if not desde or not hasta:
        raise SystemExit("El panel no declara su período (desde y hasta); no se puede replicar su recorte")
    return pd.Timestamp(desde), pd.Timestamp(hasta) + pd.Timedelta(days=1)


def hora_local_snifa(documento, hora_indice) -> np.ndarray:
    """Hora local de inicio del intervalo SNIFA, decidida documento a documento; réplica de ``_red_adicional.py:65-69``.
    Si la etiqueta máxima de un documento es 24, ese documento etiqueta 1–24 y la hora es la etiqueta − 1; si no, la
    etiqueta ya es la hora de inicio. Se calcula sobre las filas que se le pasan (las ya filtradas)."""
    doc = np.asarray(documento)
    h = np.asarray(hora_indice)
    rango = pd.Series(h).groupby(doc).max()
    desplaza = (rango == 24).astype("int8")
    return h - desplaza.reindex(doc).to_numpy()


def claves(codigos, ts) -> np.ndarray:
    """Clave entera estación × hora: ``código × BASE_CLAVE + horas desde 1970``. Exige horas enteras."""
    ns = np.asarray(ts, dtype="datetime64[ns]").view("int64")
    if len(ns) and (ns % NS_POR_HORA).any():
        raise ValueError("hay ts_utc que no caen en una hora entera; la unión estación × hora no sería exacta")
    horas = ns // NS_POR_HORA
    if len(horas) and (horas.min() < 0 or horas.max() >= BASE_CLAVE):
        raise ValueError("ts_utc fuera del rango de la clave (1970 a 3110)")
    return np.asarray(codigos, dtype="int64") * BASE_CLAVE + horas


# ---------------------------------------------------------------------------
# Agregación y rachas (funciones puras)
# ---------------------------------------------------------------------------
def agregar_por_hora(filas: pd.DataFrame, por=("ts_utc",)) -> pd.DataFrame:
    """Réplica de la agregación por estación × hora de la v1 (``_comun_modelo.py:667-668``, ``_red_adicional.py:117``):
    ``obs`` es la media de los registros y ``n`` cuántos son. La bandera ``qc`` (código entero) es la peor de los
    registros, el código mayor; ``mixta`` marca las horas cuyos registros no comparten bandera."""
    por = list(por)
    if not filas.duplicated(por).any():
        out = filas.sort_values(por, kind="stable").reset_index(drop=True)
        out["n"] = np.int64(1)
        out["mixta"] = False
        return out[por + ["obs", "n", "qc", "mixta"]]
    g = filas.groupby(por, sort=True)
    out = g.agg(obs=("obs", "mean"), n=("obs", "size"), qc=("qc", "max"), qc_min=("qc", "min")).reset_index()
    out["n"] = out["n"].astype("int64")
    out["mixta"] = out["qc"] != out["qc_min"]
    return out[por + ["obs", "n", "qc", "mixta"]]


def marcar_rachas(estacion, ts, obs, minimo: int) -> np.ndarray:
    """Réplica de ``marcar_rachas`` (``produccion.py:78-88``): verdadero si el registro pertenece a una corrida de
    ``minimo`` o más valores idénticos consecutivos de la misma estación, en orden de ``ts_utc``. Los huecos no cortan
    la corrida. Devuelve la bandera en el orden de entrada (las claves estación × hora deben ser únicas)."""
    n = len(obs)
    if minimo <= 0 or n == 0:
        return np.zeros(n, dtype=bool)
    cod = pd.Categorical(np.asarray(estacion)).codes
    t = np.asarray(ts, dtype="datetime64[ns]").view("int64")
    orden = np.lexsort((t, cod))
    c, v = cod[orden], np.asarray(obs, dtype="float64")[orden]
    cambio = np.ones(n, dtype=bool)
    cambio[1:] = (c[1:] != c[:-1]) | (v[1:] != v[:-1])
    corrida = np.cumsum(cambio)
    en_racha = np.bincount(corrida)[corrida] >= minimo
    out = np.empty(n, dtype=bool)
    out[orden] = en_racha
    return out


def huella_columnas(df: pd.DataFrame, columnas) -> str:
    """sha256 del contenido de ``columnas`` en su orden de filas (fechas como enteros ns; textos factorizados)."""
    h = hashlib.sha256(SCHEMA.encode("utf-8"))
    for col in columnas:
        h.update(f"|{col}|{len(df)}|".encode("utf-8"))
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s.dtype):
            h.update(s.to_numpy("datetime64[ns]").view("int64").tobytes())
        else:
            codigos, unicos = pd.factorize(s.astype(object), use_na_sentinel=True)
            h.update(json.dumps([str(u) for u in unicos], ensure_ascii=False).encode("utf-8"))
            h.update(np.asarray(codigos, dtype="int64").tobytes())
    return h.hexdigest()


def pct(parte, total, decimales: int = 4):
    return round(100.0 * float(parte) / float(total), decimales) if total else None


def coincide_redondeado(valor, referencia) -> bool | None:
    """¿``valor`` redondeado a los decimales con que se publicó ``referencia`` es igual a ella?"""
    if referencia is None or valor is None:
        return None
    texto = repr(float(referencia))
    decimales = len(texto.split(".")[1].rstrip("0")) if "." in texto else 0
    return round(float(valor), decimales) == round(float(referencia), decimales)


# ---------------------------------------------------------------------------
# Panel v1 (sólo lectura)
# ---------------------------------------------------------------------------
def leer_panel(r: RutasV2, pol: str) -> tuple[pd.DataFrame, dict, dict]:
    """Seis columnas del panel v1, su JSON y la huella del archivo (que debe ser la que publicó la v1)."""
    import pyarrow.parquet as pq

    ruta = r.panel(pol)
    if not ruta.exists():
        raise SystemExit(f"Falta el panel v1 {r.relativa(ruta)}")
    meta = leer_json(r.panel_meta(pol)) or {}
    sha = sha256_archivo(ruta)
    declarado = meta.get("sha256")
    if declarado and declarado != sha:
        raise SystemExit(f"{pol}: el panel en disco (sha256 {sha[:16]}) no es el que publicó la v1 ({declarado[:16]}); "
                         f"la v2 se ata al panel v1 publicado")
    df = pq.read_table(ruta, columns=COLUMNAS_PANEL, read_dictionary=["estacion", "version"]).to_pandas()
    for col in ("estacion", "version"):
        if not isinstance(df[col].dtype, pd.CategoricalDtype):
            df[col] = df[col].astype(str).astype("category")
    df["ts_utc"] = df["ts_utc"].astype("datetime64[ns]")
    versiones = df.groupby("estacion", observed=True)["version"].nunique()
    if (versiones > 1).any():
        raise SystemExit(f"{pol}: estaciones con más de una versión en el panel: {list(versiones[versiones > 1].index)}")
    info = {**r.relativa(ruta), "sha256": sha, "sha256_declarado_v1": declarado, "bytes": ruta.stat().st_size,
            "filas": int(len(df)), "estaciones": int(df["estacion"].nunique()),
            **{k: meta.get(k) for k in ("reloj_sinca", "desde", "hasta", "qc_racha_minima", "redes", "codigo")}}
    return df, meta, info


def versiones_del_panel(panel: pd.DataFrame) -> dict[str, str]:
    """Versión del derivado SINCA con que la v1 armó cada estación (columna ``version``; las SNIFA dicen «snifa»)."""
    v = panel.groupby("estacion", observed=True)["version"].first()
    return {str(e): str(x) for e, x in v.items() if str(x) != RED_SNIFA}


def coherencia_con_pliegues(r: RutasV2, pol: str, sha_panel: str) -> dict | None:
    """Si el manifiesto de pliegues ya está fijado, la bandera tiene que atarse al mismo panel."""
    m = leer_json(r.manifiesto_pliegues)
    if m is None:
        return None
    sha_pl = (((m.get("contaminantes") or {}).get(pol) or {}).get("panel") or {}).get("sha256")
    if sha_pl and sha_pl != sha_panel:
        raise SystemExit(f"{pol}: el panel ({sha_panel[:16]}) no es el del manifiesto de pliegues ({sha_pl[:16]}); "
                         f"la v2 tiene que trabajar sobre un solo panel")
    return {**r.relativa(r.manifiesto_pliegues), "huella_pliegues": m.get("huella_pliegues"),
            "panel_sha256": sha_pl, "mismo_panel": sha_pl == sha_panel}


# ---------------------------------------------------------------------------
# Derivado SINCA (sólo lectura): réplica de version_sinca y series_sinca
# ---------------------------------------------------------------------------
def _inv(texto: str) -> tuple:
    """Clave que invierte el orden lexicográfico de un texto ASCII; réplica de ``_comun_modelo.py:641-643``."""
    return tuple(-ord(ch) for ch in texto) + (1,)


def candidatas_sinca(carpeta: Path) -> list[dict]:
    """Versiones de una carpeta ``estacion=*/contaminante=*``, de la que elige ``version_sinca`` a la última; réplica de
    ``_comun_modelo.py:602-638``: ``since`` más temprano, luego ``until`` más tardío, luego ``created_utc`` más
    reciente (todo del ``manifest.json``) y, sin manifiesto, la de más filas."""
    cand = []
    for obs in carpeta.glob("version=*/observaciones.parquet"):
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
            except Exception:  # noqa: BLE001 (como la v1: un archivo ilegible cuenta 0 filas)
                filas = 0
        cand.append({"version": obs.parent.name.split("=", 1)[1], "since": since, "until": until,
                     "created_utc": creado, "filas": filas, "ruta": obs})
    cand.sort(key=lambda c: (c["since"], _inv(c["until"]), _inv(c["created_utc"]), -c["filas"]))
    return cand


def huella_version(ruta_obs: Path, raiz: Path) -> dict:
    """sha256 del ``observaciones.parquet`` leído, contrastado con el que declara el manifiesto de su versión."""
    mani = ruta_obs.parent / "manifest.json"
    declarado = sha_mani = None
    if mani.exists():
        sha_mani = sha256_archivo(mani)
        try:
            m = json.loads(mani.read_text(encoding="utf-8"))
            declarado = next((f.get("sha256") for f in m.get("files", []) if f.get("name") == ruta_obs.name), None)
        except (ValueError, TypeError, AttributeError):
            declarado = None
    sha = sha256_archivo(ruta_obs)
    if declarado and declarado != sha:
        raise SystemExit(f"{relativa_a(ruta_obs, raiz, 'derivados')['ruta']}: el sha256 ({sha[:16]}) no es el que "
                         f"declara su manifiesto ({declarado[:16]}); el derivado SINCA cambió o está dañado")
    return {**relativa_a(ruta_obs, raiz, "derivados"), "sha256": sha, "bytes": ruta_obs.stat().st_size,
            "sha256_declarado_manifiesto": declarado, "manifiesto_sha256": sha_mani}


def leer_serie_sinca(ruta: Path, estacion: str, pol: str, desplazamiento_h: int) -> tuple[pd.DataFrame, dict]:
    """Una versión del derivado como la lee ``series_sinca`` (``_comun_modelo.py:656-668``): filas ``seleccionada``
    con ``obs`` no nula y dentro de ``RANGO_VALIDO``, llevadas al bin UTC y agregadas por hora, con su
    ``qc_observacion``. Un código que no sea validado, preliminar o no validado en esas filas detiene la corrida."""
    import pyarrow.parquet as pq

    df = pq.read_table(ruta, columns=COLUMNAS_SINCA).to_pandas()
    leidas = len(df)
    lo, hi = RANGO_VALIDO[pol]
    sel = df["seleccionada"].astype(bool) & df["obs"].notna()
    sel &= df["obs"].between(lo, hi)
    df = df.loc[sel]
    qc = df["qc_observacion"]
    raros = ~qc.isin(QC_SINCA)
    if raros.any():
        conteo = qc[raros].astype(str).value_counts().to_dict()
        raise SystemExit(f"{estacion}/{pol}: códigos qc_observacion inesperados en filas seleccionadas con valor: "
                         f"{conteo}; se esperaban {list(QC_SINCA)}")
    filas = pd.DataFrame({"ts_utc": a_bin_utc(df["ts_local"], desplazamiento_h).to_numpy(),
                          "obs": df["obs"].to_numpy("float64"),
                          "qc": qc.map(CODIGO_QC).to_numpy("int8")})
    serie = agregar_por_hora(filas, por=("ts_utc",))
    serie.insert(0, "estacion", estacion)
    return serie, {"filas_leidas": int(leidas), "filas_seleccionadas": int(sel.sum()), "horas": int(len(serie)),
                   "horas_agregadas": int((serie["n"] > 1).sum())}


def reconstruir_sinca(derivado: Path, raiz: Path, pol: str, desplazamiento_h: int,
                      versiones_panel: Mapping[str, str]) -> tuple[pd.DataFrame, list[dict]]:
    """Series SINCA de ``pol`` de todas las estaciones del derivado, una versión por estación, con su bandera."""
    if not Path(derivado).is_dir():
        raise SystemExit(f"No está el derivado SINCA ({relativa_a(derivado, raiz, 'derivados')['ruta']}); "
                         f"¿está montado el disco de datos? Revisa {VAR_DERIVADOS}.")
    partes, registro = [], []
    for carpeta in sorted(Path(derivado).glob(f"estacion=*/contaminante={pol}")):
        est = carpeta.parent.name.split("=", 1)[1]
        cand = candidatas_sinca(carpeta)
        del_panel = versiones_panel.get(est)
        if not cand:
            registro.append({"estacion": est, "version_sinca": None, "version_panel": del_panel, "version_usada": None,
                             "nota": "carpeta sin versiones"})
            continue
        elegida = usada = cand[0]
        if del_panel is not None and del_panel != elegida["version"]:
            usada = next((c for c in cand if c["version"] == del_panel), None)
            if usada is None:
                registro.append({"estacion": est, "version_sinca": elegida["version"], "version_panel": del_panel,
                                 "version_usada": None, "nota": "la versión del panel ya no está en el derivado"})
                continue
            log.warning("%s %s: el panel usó la versión %s y version_sinca elegiría hoy %s; se lee la del panel",
                        pol, est, del_panel[:12], elegida["version"][:12])
        serie, info = leer_serie_sinca(usada["ruta"], est, pol, desplazamiento_h)
        partes.append(serie)
        registro.append({"estacion": est, "version_sinca": elegida["version"], "version_panel": del_panel,
                         "version_usada": usada["version"], "archivo": huella_version(usada["ruta"], raiz), **info,
                         "candidatas": [{k: c[k] for k in ("version", "since", "until", "created_utc", "filas")}
                                        for c in cand]})
    vacia = pd.DataFrame({"estacion": pd.Series(dtype=object), "ts_utc": pd.Series(dtype="datetime64[ns]"),
                          "obs": pd.Series(dtype="float64"), "n": pd.Series(dtype="int64"),
                          "qc": pd.Series(dtype="int8"), "mixta": pd.Series(dtype=bool)})
    serie = pd.concat(partes, ignore_index=True) if partes else vacia
    serie["fuente"] = RED_SINCA
    return serie, registro


# ---------------------------------------------------------------------------
# Red adicional SNIFA (sólo lectura): réplica de series_adicionales
# ---------------------------------------------------------------------------
def reconstruir_snifa(ruta: Path, pol: str) -> tuple[pd.DataFrame, dict]:
    """Horas SNIFA de ``pol`` como las arma ``series_adicionales`` (``_red_adicional.py:59-69`` y ``96-121``), con la
    bandera de cada hora: ``usable_native`` o ``solo_numeric_usable``."""
    columnas = ["estacion", "ts_utc", "obs", "n", "qc", "mixta"]
    if pol not in CONTAMINANTES_SNIFA:
        return pd.DataFrame(columns=columnas + ["fuente"]), {"aplica": False}
    if not Path(ruta).exists():
        raise SystemExit("Falta la red adicional SNIFA; el panel v1 la incluye (redes = sinca, snifa)")
    o = pd.read_parquet(ruta, columns=COLUMNAS_SNIFA)
    o = o[o["station_id"].isin(list(ESTACIONES_SNIFA)) & o["numeric_usable"].astype(bool)]
    o = o[o["pollutant"] == pol].copy()
    numericos = len(o)
    unidad_ok = o["unit"].isin(UNIDADES_SNIFA)
    fuera_unidad = int((~unidad_ok).sum())
    o = o[unidad_ok]
    factor = o["station_id"].map({k: v[1] for k, v in ESTACIONES_SNIFA.items()}).to_numpy("float64")
    o["obs"] = np.where(o["unit"].to_numpy() == "ug/m3N", o["value"].to_numpy() * factor, o["value"].to_numpy())
    lo, hi = RANGO_VALIDO[pol]
    en_rango = o["obs"].between(lo, hi)
    fuera_rango = int((~en_rango).sum())
    o = o[en_rango]
    hora = hora_local_snifa(o["document_id"].to_numpy(), o["hour_index"].to_numpy())
    ts = pd.to_datetime(o["date_local"]) + pd.to_timedelta(hora + OFFSET_UTC_H_SNIFA, unit="h")
    nativo = o["usable_native"].astype("boolean").fillna(False).to_numpy(dtype=bool)
    filas = pd.DataFrame({"estacion": o["station_id"].map({k: v[0] for k, v in ESTACIONES_SNIFA.items()}).to_numpy(),
                          "ts_utc": ts.astype("datetime64[ns]").to_numpy(),
                          "obs": o["obs"].to_numpy("float64"),
                          "qc": np.where(nativo, CODIGO_QC["usable_native"],
                                         CODIGO_QC["solo_numeric_usable"]).astype("int8")})
    serie = agregar_por_hora(filas, por=("estacion", "ts_utc"))
    serie["fuente"] = RED_SNIFA
    conflicto_valor = o["value_conflict"].astype("boolean").fillna(False).to_numpy(dtype=bool)
    conflicto_codigo = o["quality_conflict"].astype("boolean").fillna(False).to_numpy(dtype=bool)
    info = {"aplica": True, "registros_numeric_usable": int(numericos), "fuera_de_unidad": fuera_unidad,
            "fuera_de_rango": fuera_rango, "registros": int(len(o)),
            "registros_no_usable_native": int((~nativo).sum()),
            "conflicto_de_valor": int((~nativo & conflicto_valor).sum()),
            "conflicto_de_codigo": int((~nativo & conflicto_codigo & ~conflicto_valor).sum()),
            "horas": int(len(serie)), "horas_promediadas": int((serie["n"] > 1).sum()),
            "horas_mixtas": int(serie["mixta"].sum()),
            "por_estacion": {str(k): int(v) for k, v in serie.groupby("estacion").size().items()}}
    return serie, info


# ---------------------------------------------------------------------------
# Conciliación con el panel
# ---------------------------------------------------------------------------
def universo(r: RutasV2, redes) -> tuple[set, set]:
    """Estaciones usables (catálogo SINCA ``usable_geoespacial`` más los tres monitores SNIFA si la red adicional está
    activa: ``produccion.py:50-56``) y estaciones con celda (``estaciones_con_celda``, réplica de ``qmd:1968-1970``)."""
    snifa = {v[0] for v in ESTACIONES_SNIFA.values()}
    usables = set(leer_estaciones_sinca(r)["estacion"].astype(str))
    con_celda = set(estaciones_con_celda(r)["estacion"].astype(str))
    if RED_SNIFA in (redes or []):
        usables |= snifa
    else:
        con_celda -= snifa
    return usables, con_celda


def filtros_v1(recon: pd.DataFrame, usables: set, con_celda: set, periodo, offset_utc_h: int, minimo_racha: int) -> None:
    """Marca en la réplica lo que deja la v1: rachas sobre el registro completo de cada estación (``produccion.py:104-
    110``), estaciones usables y con celda y período por día local (``qmd:2004-2010``)."""
    recon["racha"] = marcar_rachas(recon["estacion"].to_numpy(), recon["ts_utc"].to_numpy(),
                                   recon["obs"].to_numpy(), minimo_racha)
    local = recon["ts_utc"] - pd.Timedelta(hours=int(offset_utc_h))
    recon["en_periodo"] = ((local >= periodo[0]) & (local < periodo[1])).to_numpy()
    recon["usable"] = recon["estacion"].isin(usables).to_numpy()
    recon["con_celda"] = recon["estacion"].isin(con_celda).to_numpy()
    recon["deja_v1"] = recon["usable"] & recon["con_celda"] & recon["en_periodo"] & ~recon["racha"]


def _por_estacion(estaciones: np.ndarray) -> dict:
    s = pd.Series(estaciones).value_counts()
    return {str(k): int(v) for k, v in sorted(s.items())}


def conciliar(panel: pd.DataFrame, recon: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """Une la réplica con el panel por estación × hora y decide qué filas reciben bandera.

    Devuelve la bandera en el orden del panel (estacion, ts_utc, qc, fuente), la marca de horas mixtas por fila y el
    informe de la conciliación, con el motivo de cada fila que se quede sin bandera."""
    est_panel = panel["estacion"].astype(str).to_numpy(dtype=object)
    est_recon = recon["estacion"].astype(str).to_numpy(dtype=object)
    categorias = sorted(set(pd.unique(est_panel)) | set(pd.unique(est_recon)))
    cp = pd.Categorical(est_panel, categories=categorias).codes
    cr = pd.Categorical(est_recon, categories=categorias).codes
    kp = claves(cp, panel["ts_utc"].to_numpy())
    kr = claves(cr, recon["ts_utc"].to_numpy())
    if not pd.Index(kp).is_unique:
        raise SystemExit("El panel tiene horas repetidas para una misma estación; no se puede alinear 1 a 1")
    indice = pd.Index(kr)
    if not indice.is_unique:
        raise ValueError("La réplica tiene horas repetidas para una misma estación después de agregar")
    pos = indice.get_indexer(kp)
    hay = pos >= 0
    p = np.where(hay, pos, 0)

    fuente_panel = np.where(panel["version"].astype(str).to_numpy() == RED_SNIFA, RED_SNIFA, RED_SINCA)
    obs_panel = panel["obs"].to_numpy(dtype="float32")
    obs_recon = recon["obs"].to_numpy(dtype="float64")[p].astype("float32")
    obs_ok = hay & (obs_panel == obs_recon)
    n_ok = hay & (panel["n"].to_numpy(dtype="int64") == recon["n"].to_numpy(dtype="int64")[p])
    fuente_ok = hay & (fuente_panel == recon["fuente"].to_numpy(dtype=object)[p])
    con_bandera = hay & obs_ok & n_ok & fuente_ok

    motivo = np.full(len(panel), None, dtype=object)
    motivo[~hay] = "sin_pareja_en_la_replica"
    motivo[hay & ~fuente_ok] = "red_distinta"
    motivo[hay & fuente_ok & ~obs_ok] = "obs_distinta"
    motivo[hay & fuente_ok & obs_ok & ~n_ok] = "n_distinto"
    sin = ~con_bandera
    por_motivo = {}
    for m in ("sin_pareja_en_la_replica", "red_distinta", "obs_distinta", "n_distinto"):
        sel = motivo == m
        if sel.any():
            por_motivo[m] = {"filas": int(sel.sum()), "por_estacion": _por_estacion(est_panel[sel])}

    qc_cod = np.where(con_bandera, recon["qc"].to_numpy(dtype="int64")[p], -1)
    etiquetas = np.array(list(QC_TODOS) + [None], dtype=object)
    out = pd.DataFrame({"estacion": est_panel, "ts_utc": panel["ts_utc"].to_numpy("datetime64[ns]"),
                        "qc": etiquetas[qc_cod], "fuente": fuente_panel.astype(object)})
    mixta = con_bandera & recon["mixta"].to_numpy(dtype=bool)[p]

    # Coherencia de la bandera con la red: SINCA sólo con códigos SINCA y SNIFA sólo con códigos SNIFA.
    for red, codigos in QC_DE_FUENTE.items():
        malos = con_bandera & (fuente_panel == red) & ~pd.Series(out["qc"]).isin(codigos).to_numpy()
        if malos.any():
            raise ValueError(f"{int(malos.sum())} filas {red} con una bandera de la otra red")

    # Lo que la v1 deja según la réplica y el panel no tiene, y lo que el panel tiene y la réplica excluiría.
    deja = recon["deja_v1"].to_numpy(dtype=bool)
    en_panel = np.isin(kr, kp, assume_unique=True)
    sobran = deja & ~en_panel
    excl = con_bandera & ~deja[p]
    motivos_excl = {}
    if excl.any():
        r_excl = recon.iloc[p[excl]]
        for nombre, col, valor in (("racha", "racha", True), ("fuera_del_periodo", "en_periodo", False),
                                   ("sin_celda", "con_celda", False), ("no_usable", "usable", False)):
            k = int((r_excl[col].to_numpy(dtype=bool) == valor).sum())
            if k:
                motivos_excl[nombre] = k
    informe = {
        "filas_panel": int(len(panel)), "con_bandera": int(con_bandera.sum()), "sin_bandera": int(sin.sum()),
        "sin_bandera_por_motivo": por_motivo,
        "obs_iguales_float32": int(obs_ok.sum()), "n_iguales": int(n_ok.sum()), "red_igual": int(fuente_ok.sum()),
        "horas_promediadas_en_el_panel": int((panel["n"].to_numpy() > 1).sum()),
        "horas_mixtas_con_bandera": int(mixta.sum()),
        "replica": {"horas": int(len(recon)), "en_racha": int(recon["racha"].sum()),
                    "fuera_del_periodo": int((~recon["en_periodo"]).sum()), "sin_celda": int((~recon["con_celda"]).sum()),
                    "no_usables": int((~recon["usable"]).sum()), "deja_la_v1": int(deja.sum())},
        "replica_que_el_panel_no_tiene": {"filas": int(sobran.sum()), "por_estacion": _por_estacion(est_recon[sobran])},
        "panel_que_la_replica_excluiria": {"filas": int(excl.sum()), "por_motivo": motivos_excl},
        "mismas_claves_que_la_replica": bool(not sobran.any() and hay.all() and not excl.any()),
    }
    return out, mixta, informe


def prueba_desfase(panel: pd.DataFrame, recon: pd.DataFrame, usado: int, desfases=DESFASES_DE_PRUEBA) -> dict:
    """Evidencia empírica del reloj SINCA: para cada desfase s, fracción de filas SINCA del panel que encuentran en la
    réplica una observación en ``ts_local + s`` con el mismo ``obs``. Sólo el desfase correcto da 1."""
    sp = panel["version"].astype(str).to_numpy() != RED_SNIFA
    sr = recon["fuente"].to_numpy(dtype=object) == RED_SINCA
    est_p = panel["estacion"].astype(str).to_numpy(dtype=object)[sp]
    est_r = recon["estacion"].astype(str).to_numpy(dtype=object)[sr]
    if not len(est_p):
        return {}
    categorias = sorted(set(pd.unique(est_p)) | set(pd.unique(est_r)))
    kp = claves(pd.Categorical(est_p, categories=categorias).codes, panel["ts_utc"].to_numpy()[sp])
    kr = claves(pd.Categorical(est_r, categories=categorias).codes, recon["ts_utc"].to_numpy()[sr])
    obs_p = panel["obs"].to_numpy(dtype="float32")[sp]
    obs_r = recon["obs"].to_numpy(dtype="float64")[sr]
    indice = pd.Index(kr)
    out = {}
    for s in desfases:
        pos = indice.get_indexer(kp - (int(s) - int(usado)))
        hay = pos >= 0
        iguales = np.zeros(len(kp), dtype=bool)
        iguales[hay] = obs_p[hay] == obs_r[pos[hay]].astype("float32")
        out[f"+{int(s)}h"] = {"claves": round(float(hay.mean()), 6), "obs_iguales": round(float(iguales.mean()), 6)}
    mejor = max(out, key=lambda k: out[k]["obs_iguales"])
    return {"filas_sinca_del_panel": int(sp.sum()), "por_desfase": out, "desfase_con_mas_coincidencias": mejor,
            "desfase_usado": f"+{int(usado)}h", "confirma_el_reloj": mejor == f"+{int(usado)}h"}


# ---------------------------------------------------------------------------
# Distribución y comparación con la auditoría
# ---------------------------------------------------------------------------
def _registros(df: pd.DataFrame, por: list[str], nombres: dict) -> list[dict]:
    """Conteos por ``por`` y bandera (códigos de CATEGORIAS) en registros con todas las categorías."""
    t = df.groupby(por + ["q"], sort=True).size().unstack("q", fill_value=0)
    t = t.reindex(columns=range(len(CATEGORIAS)), fill_value=0)
    out = []
    for idx, fila in zip(t.index, t.to_numpy()):
        idx = idx if isinstance(idx, tuple) else (idx,)
        reg = {nombre: nombres[nombre](v) for nombre, v in zip(por, idx)}
        reg["filas"] = int(fila.sum())
        reg.update({c: int(fila[i]) for i, c in enumerate(CATEGORIAS)})
        out.append(reg)
    return out


def distribuciones(out: pd.DataFrame, anio, version) -> dict:
    """Bandera por red y año local (columna ``anio`` del panel, UTC−4), por red y estación, y en total."""
    cq = pd.Categorical(out["qc"], categories=QC_TODOS).codes.astype("int64")
    cq[cq < 0] = len(QC_TODOS)
    est = pd.Categorical(out["estacion"])
    df = pd.DataFrame({"fuente": pd.Categorical(out["fuente"], categories=FUENTES).codes.astype("int64"),
                       "anio": np.asarray(anio, dtype="int64"), "e": est.codes.astype("int64"), "q": cq})
    nombres = {"fuente": lambda v: FUENTES[int(v)], "anio": int, "e": lambda v: str(est.categories[int(v)])}
    por_estacion = _registros(df, ["fuente", "e"], nombres)
    rango = df.groupby("e")["anio"].agg(["min", "max"])
    ver = pd.Series(np.asarray(version, dtype=object)).groupby(est.codes).first()
    for reg in por_estacion:
        e = int(est.categories.get_loc(reg["e"]))
        reg["estacion"] = reg.pop("e")
        reg["anio_desde"], reg["anio_hasta"] = int(rango.loc[e, "min"]), int(rango.loc[e, "max"])
        reg["version"] = str(ver.loc[e])
    return {"total": _registros(df, ["fuente"], nombres), "por_anio": _registros(df, ["fuente", "anio"], nombres),
            "por_estacion": por_estacion}


def filas_por_variante(dist: dict) -> dict:
    """Cuántas filas y estaciones quedan en cada variante de §7, por red. Es descriptivo: el cruce de SNIFA con las
    variantes SINCA está pendiente (config_v2.json → calidad_blanco.snifa.cruce_con_variantes_sinca)."""
    sinca = [e for e in dist["por_estacion"] if e["fuente"] == RED_SINCA]
    snifa = [e for e in dist["por_estacion"] if e["fuente"] == RED_SNIFA]

    def resumen(lista, campos):
        filas = [sum(e[c] for c in campos) for e in lista]
        return {"filas": int(sum(filas)), "estaciones": int(sum(1 for f in filas if f > 0))}

    return {"sinca": {"todo": resumen(sinca, QC_SINCA), "validado_y_preliminar": resumen(sinca, ("validado", "preliminar")),
                      "solo_validado": resumen(sinca, ("validado",)),
                      "estaciones_sin_filas_validadas": sorted(e["estacion"] for e in sinca if e["validado"] == 0)},
            "snifa": {"numeric_usable": resumen(snifa, QC_SNIFA), "usable_native": resumen(snifa, ("usable_native",))},
            "nota": "descriptivo; el cruce de SNIFA con las variantes SINCA está pendiente en config_v2.json"}


def leer_auditoria_anual(ruta: Path | None) -> tuple[dict | None, dict | None]:
    """Fracciones por año de la auditoría (``calidad_sinca_por_anio``), si su JSON está a mano; si no, (None, None)."""
    if ruta is None or not Path(ruta).exists():
        return None, None
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))

    def buscar(o):
        if isinstance(o, dict):
            if "calidad_sinca_por_anio" in o:
                return o["calidad_sinca_por_anio"]
            for v in o.values():
                hallado = buscar(v)
                if hallado is not None:
                    return hallado
        elif isinstance(o, list):
            for v in o:
                hallado = buscar(v)
                if hallado is not None:
                    return hallado
        return None

    anual = buscar(datos)
    huella = {"sha256": sha256_archivo(ruta), "bytes": Path(ruta).stat().st_size}
    return anual, huella


def comparar_auditoria(pol: str, out: pd.DataFrame, recon: pd.DataFrame, info_snifa: dict, desplazamiento_h: int,
                       anual: dict | None) -> dict:
    """Compara la distribución con la auditoría del 2026-10-12, en sus mismas bases."""
    res = {"referencia": AUDITORIA["referencia"]}
    # 1) Filas SINCA del panel (después de rachas).
    s = out["fuente"].to_numpy(dtype=object) == RED_SINCA
    cuenta = pd.Series(out["qc"].to_numpy(dtype=object)[s]).value_counts()
    v2 = {"filas": int(s.sum()), **{c: int(cuenta.get(c, 0)) for c in QC_SINCA}}
    v2["pct_no_validado_o_preliminar"] = pct(v2["preliminar"] + v2["no_validado"], v2["filas"])
    ref = AUDITORIA["sinca_panel"].get(pol)
    res["sinca_panel"] = {"base": AUDITORIA["sinca_panel"]["base"], "referencia": AUDITORIA["sinca_panel"]["referencia"],
                          "v2": v2, "auditoria": ref,
                          "coincide": None if not ref or v2["filas"] == 0 else
                          coincide_redondeado(v2["pct_no_validado_o_preliminar"], ref["pct_no_validado_o_preliminar"])}
    # 2) Filas SINCA válidas del período antes del filtro de rachas (base de AM-02).
    m = (recon["fuente"].to_numpy(dtype=object) == RED_SINCA) & recon["usable"].to_numpy() & recon["en_periodo"].to_numpy()
    cod = recon["qc"].to_numpy(dtype="int64")[m]
    v2 = {"filas": int(m.sum()), **{c: int((cod == CODIGO_QC[c]).sum()) for c in QC_SINCA}}
    v2["pct_no_validado_o_preliminar"] = pct(v2["preliminar"] + v2["no_validado"], v2["filas"])
    ref = AUDITORIA["sinca_antes_de_rachas"].get(pol)
    coincide = None
    if ref and v2["filas"]:
        coincide = (all(v2[k] == ref[k] for k in ("filas",) + QC_SINCA)
                    and coincide_redondeado(v2["pct_no_validado_o_preliminar"], ref["pct_no_validado_o_preliminar"]))
    res["sinca_antes_de_rachas"] = {"base": AUDITORIA["sinca_antes_de_rachas"]["base"],
                                    "referencia": AUDITORIA["sinca_antes_de_rachas"]["referencia"],
                                    "nota": AUDITORIA["sinca_antes_de_rachas"]["nota"],
                                    "v2": v2, "auditoria": ref, "coincide": coincide}
    # 3) Por año de la etiqueta local, en la misma base (si el JSON de la auditoría está a mano).
    if anual and pol in anual and v2["filas"]:
        anio = (recon["ts_utc"].to_numpy()[m] - np.timedelta64(int(desplazamiento_h), "h")).astype("datetime64[Y]")
        anios, inv = np.unique(anio.astype("int64") + 1970, return_inverse=True)
        k = len(QC_SINCA)
        cuentas = np.bincount(inv * k + cod, minlength=len(anios) * k).reshape(len(anios), k)
        fracciones = np.round(cuentas / cuentas.sum(axis=1, keepdims=True), 3)
        difs, distintos = {}, []
        for a, fila in zip(anios, fracciones):
            aud = anual[pol].get(str(int(a)))
            if aud is None:
                distintos.append(int(a))
                continue
            d = max(abs(float(fila[CODIGO_QC[c]]) - float(aud.get(c, 0.0))) for c in QC_SINCA)
            difs[str(int(a))] = round(d, 6)
            if d > 0.0005:
                distintos.append(int(a))
        faltan = sorted(set(anual[pol]) - set(difs))
        res["sinca_anual"] = {"base": AUDITORIA["sinca_anual"]["base"], "referencia": AUDITORIA["sinca_anual"]["referencia"],
                              "anios": len(difs), "dif_max": max(difs.values()) if difs else None,
                              "anios_distintos": distintos, "anios_solo_en_la_auditoria": faltan,
                              "coincide": not distintos and not faltan}
    else:
        res["sinca_anual"] = {"coincide": None, "nota": "sin el JSON de la auditoría o sin filas SINCA"}
    # 4) Red SNIFA antes de rachas (sólo NO2).
    ref = AUDITORIA["snifa_antes_de_rachas"].get(pol)
    if info_snifa.get("aplica"):
        ms = (recon["fuente"].to_numpy(dtype=object) == RED_SNIFA) & recon["usable"].to_numpy() & recon["en_periodo"].to_numpy()
        est = recon["estacion"].to_numpy(dtype=object)[ms]
        v2 = {"horas": int(ms.sum()), **{e: int((est == e).sum()) for e, _ in ESTACIONES_SNIFA.values()},
              "registros_no_usable_native": info_snifa["registros_no_usable_native"],
              "conflicto_de_valor": info_snifa["conflicto_de_valor"],
              "conflicto_de_codigo": info_snifa["conflicto_de_codigo"],
              "horas_promediadas": int((recon["n"].to_numpy()[ms] > 1).sum())}
        res["snifa_antes_de_rachas"] = {"base": AUDITORIA["snifa_antes_de_rachas"]["base"],
                                        "referencia": AUDITORIA["snifa_antes_de_rachas"]["referencia"],
                                        "v2": v2, "auditoria": ref,
                                        "coincide": None if not ref else all(v2[k] == ref[k] for k in ref)}
    return res


# ---------------------------------------------------------------------------
# Cálculo por contaminante
# ---------------------------------------------------------------------------
def parametros_de(reloj: dict, periodo, minimo_racha: int, redes) -> dict:
    return {
        "reloj_sinca": {"declarado_por_el_panel": reloj["reloj_sinca"], "offset_utc_h": reloj["offset_utc_h"],
                        "etiqueta": reloj["etiqueta"], "desplazamiento_h": reloj["desplazamiento_h"],
                        "codigo_v1": ["_comun_modelo.py:81-82", "_comun_modelo.py:97-106", "_comun_modelo.py:666",
                                      "qmd:2064"]},
        "reloj_snifa": {"offset_utc_h": OFFSET_UTC_H_SNIFA,
                        "regla": "por documento: si la etiqueta máxima (tras filtrar) es 24, hora = etiqueta − 1",
                        "codigo_v1": ["_red_adicional.py:37", "_red_adicional.py:65-69", "_red_adicional.py:114-115"]},
        "periodo_local": [str(periodo[0].date()), str((periodo[1] - pd.Timedelta(days=1)).date())],
        "qc_racha_minima": int(minimo_racha), "rango_valido": RANGO_VALIDO, "redes": list(redes or []),
        "codigos": {"sinca": list(QC_SINCA), "snifa": list(QC_SNIFA)},
        "hora_agregada": "la peor bandera de sus registros (orden de mejor a peor dentro de cada red)",
        "snifa": {"estaciones": {k: v[0] for k, v in ESTACIONES_SNIFA.items()}, "unidades": list(UNIDADES_SNIFA),
                  "factor_ug_m3N_a_ppb": {v[0]: v[1] for v in ESTACIONES_SNIFA.values()}},
        "union": "estacion × ts_utc (inicio del bin horario UTC); bandera sólo si coinciden obs (float32), n y red",
    }


def calidad_contaminante(r: RutasV2, pol: str, derivado: Path, raiz_der: Path,
                         anual: dict | None = None) -> tuple[pd.DataFrame, dict, dict]:
    """Bandera de un contaminante, alineada con su panel, y sus metadatos (sin traza ni escritura)."""
    panel, meta_panel, panel_info = leer_panel(r, pol)
    reloj = reloj_del_panel(meta_panel)
    periodo = periodo_del_panel(meta_panel)
    if meta_panel.get("qc_racha_minima") is None:
        raise SystemExit(f"{pol}: el panel no declara qc_racha_minima; no se puede replicar el filtro de rachas")
    minimo_racha = int(meta_panel["qc_racha_minima"])
    redes = meta_panel.get("redes") or [RED_SINCA]
    pliegues = coherencia_con_pliegues(r, pol, panel_info["sha256"])
    local = panel["ts_utc"] - pd.Timedelta(hours=reloj["offset_utc_h"])
    if not (local.dt.year.to_numpy() == panel["anio"].to_numpy()).all():
        raise SystemExit(f"{pol}: la columna anio del panel no es el año de ts_utc − {reloj['offset_utc_h']} h")
    log.info("%s: panel %s filas, %d estaciones; reloj SINCA %s (+%d h); período %s a %s", pol,
             f"{len(panel):,}", panel_info["estaciones"], reloj["reloj_sinca"], reloj["desplazamiento_h"],
             meta_panel.get("desde"), meta_panel.get("hasta"))

    versiones = versiones_del_panel(panel)
    sinca, registro = reconstruir_sinca(derivado, raiz_der, pol, reloj["desplazamiento_h"], versiones)
    if RED_SNIFA in redes and pol in CONTAMINANTES_SNIFA:
        snifa, info_snifa = reconstruir_snifa(r.snifa, pol)
    else:
        snifa, info_snifa = sinca.iloc[0:0].copy(), {"aplica": False}
    recon = pd.concat([sinca, snifa], ignore_index=True)
    recon["estacion"] = recon["estacion"].astype(str)
    usables, con_celda = universo(r, redes)
    filtros_v1(recon, usables, con_celda, periodo, reloj["offset_utc_h"], minimo_racha)
    log.info("%s: réplica %s horas (SINCA %s de %d estaciones, SNIFA %s); la v1 deja %s", pol, f"{len(recon):,}",
             f"{len(sinca):,}", sinca["estacion"].nunique(), f"{len(snifa):,}", f"{int(recon['deja_v1'].sum()):,}")

    out, mixta, informe = conciliar(panel, recon)
    informe["horas_mixtas_con_bandera_por_estacion"] = _por_estacion(out["estacion"].to_numpy(dtype=object)[mixta])
    desfase = prueba_desfase(panel, recon, reloj["desplazamiento_h"])
    dist = distribuciones(out, panel["anio"].to_numpy(), panel["version"].astype(str).to_numpy(dtype=object))
    auditoria = comparar_auditoria(pol, out, recon, info_snifa, reloj["desplazamiento_h"], anual)
    log.info("%s: con bandera %s de %s; sin bandera %s; desfase SINCA %s", pol, f"{informe['con_bandera']:,}",
             f"{informe['filas_panel']:,}", f"{informe['sin_bandera']:,}", desfase.get("desfase_con_mas_coincidencias"))

    sin_version = [x["estacion"] for x in registro if x.get("version_panel") and not x.get("version_usada")]
    distinta = [x["estacion"] for x in registro if x.get("version_panel") and x.get("version_usada")
                and x["version_sinca"] != x["version_panel"]]
    sin_carpeta = sorted(set(versiones) - {x["estacion"] for x in registro})
    parametros = parametros_de(reloj, periodo, minimo_racha, redes)
    totales = {t["fuente"]: t for t in dist["total"]}
    resumen = {"filas_panel": informe["filas_panel"], "con_bandera": informe["con_bandera"],
               "sin_bandera": informe["sin_bandera"]}
    if RED_SINCA in totales:
        t = totales[RED_SINCA]
        resumen["sinca"] = {"filas": t["filas"], **{c: t[c] for c in QC_SINCA},
                            "pct_validado": pct(t["validado"], t["filas"], 2),
                            "pct_preliminar": pct(t["preliminar"], t["filas"], 2),
                            "pct_no_validado": pct(t["no_validado"], t["filas"], 2),
                            "pct_no_validado_o_preliminar": pct(t["preliminar"] + t["no_validado"], t["filas"], 2)}
    if RED_SNIFA in totales:
        t = totales[RED_SNIFA]
        resumen["snifa"] = {"filas": t["filas"], **{c: t[c] for c in QC_SNIFA},
                            "pct_solo_numeric_usable": pct(t["solo_numeric_usable"], t["filas"], 2),
                            "horas_mixtas": informe["horas_mixtas_con_bandera"]}
    resumen["auditoria_coincide"] = {k: v.get("coincide") for k, v in auditoria.items() if isinstance(v, dict)}

    meta = {
        "schema": SCHEMA,
        "descripcion": ("Bandera de calidad del blanco (DISENO_AMBIENTAL_V2.md §7), fila a fila del panel v1: "
                        "qc_observacion de SINCA y usable_native de SNIFA, unidas por estación × hora UTC."),
        "contaminante": pol,
        "columnas": {"estacion": "código de la estación, como en el panel",
                     "ts_utc": "inicio del bin horario UTC (naive), como en el panel",
                     "qc": "validado | preliminar | no_validado (SINCA); usable_native | solo_numeric_usable (SNIFA); "
                           "nulo = sin bandera (motivo en conciliacion.sin_bandera_por_motivo)",
                     "fuente": "sinca | snifa"},
        "alineacion": {"regla": "la fila i de la bandera es la fila i del panel: mismas estacion y ts_utc",
                       "filas": int(len(out)), "huella_claves": huella_columnas(out, ["estacion", "ts_utc"])},
        "panel": {**panel_info, "pliegues": pliegues},
        "parametros": parametros,
        "convenciones": {"prueba_desfase_sinca": desfase,
                         "snifa": {"filas_snifa_del_panel": int((out["fuente"] == RED_SNIFA).sum()),
                                   "con_bandera": int(((out["fuente"] == RED_SNIFA) & out["qc"].notna()).sum())}},
        "reconstruccion": {
            "derivado_sinca": {**relativa_a(derivado, raiz_der, "derivados"), "estaciones": registro,
                               "estaciones_del_panel_sin_carpeta": sin_carpeta,
                               "estaciones_del_panel_sin_su_version": sin_version,
                               "version_del_panel_distinta_de_version_sinca": distinta},
            "snifa": info_snifa,
        },
        "conciliacion": informe,
        "resumen": resumen,
        "distribucion": dist,
        "filas_por_variante": filas_por_variante(dist),
        "auditoria": auditoria,
    }
    meta["huella_calidad"] = sha256_json({"schema": SCHEMA, "contaminante": pol, "panel_sha256": panel_info["sha256"],
                                          "parametros": parametros,
                                          "contenido": huella_columnas(out, COLUMNAS)})
    insumos = {f"panel_{pol}": r.panel(pol), f"panel_{pol}_json": r.panel_meta(pol), "catalogo_sinca": r.catalogo_sinca,
               "snifa": r.snifa, **{f"grilla_{Path(n).stem}": r.grilla_v1 / n for n in INSUMOS_GRILLA}}
    if pliegues is not None:
        insumos["manifiesto_pliegues"] = r.manifiesto_pliegues
    archivos = sorted((x["archivo"]["ruta"], x["archivo"]["sha256"]) for x in registro if x.get("archivo"))
    extra = {"derivado_sinca": {"raiz": "derivados", "archivos": len(archivos),
                                "sha256_conjunto": hashlib.sha256("\n".join(f"{a}  {s}" for a, s in archivos)
                                                                  .encode("utf-8")).hexdigest(),
                                "detalle": "reconstruccion.derivado_sinca.estaciones[].archivo"}}
    return out, meta, {"insumos": {k: v for k, v in insumos.items() if Path(v).exists()}, "extra": extra}


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------
def verificar_escrito(ruta: Path, out: pd.DataFrame) -> None:
    """Relee el Parquet publicado y comprueba que es exactamente la bandera calculada (orden y contenido)."""
    import pyarrow.parquet as pq

    leido = pq.read_table(ruta, columns=COLUMNAS).to_pandas()
    if len(leido) != len(out) or huella_columnas(leido, COLUMNAS) != huella_columnas(out, COLUMNAS):
        raise SystemExit(f"{ruta.name}: la relectura no coincide con la bandera calculada; no se sella el JSON")


def fijar(r: RutasV2, pol: str, out: pd.DataFrame, meta: dict, reemplazar: bool) -> tuple[str, dict]:
    """Publica la bandera y su JSON (el JSON va último y sella el Parquet). Exige el candado tomado."""
    ruta, ruta_j = ruta_calidad(r, pol), ruta_meta(r, pol)
    previo = leer_json(ruta_j)
    ahora = ahora_utc()
    if previo is not None and previo.get("huella_calidad") == meta["huella_calidad"]:
        if ruta.exists() and sha256_archivo(ruta) == (previo.get("archivo") or {}).get("sha256"):
            return "sin_cambios", previo
        log.warning("%s: misma huella, pero el Parquet no calza con su JSON; se vuelve a publicar", ruta.name)
        estado, bitacora = "republicado", list(previo.get("bitacora", []))
    elif previo is not None and not reemplazar:
        raise SystemExit(f"{ruta_j.name} ya existe con otra huella ({str(previo.get('huella_calidad'))[:16]} frente a "
                         f"{meta['huella_calidad'][:16]}). La bandera define las variantes de entrenamiento y no se "
                         f"reemplaza en silencio; si corresponde, usa --reemplazar.")
    else:
        bitacora = []
        if previo is not None:
            sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            respaldos = [r.relativa(renombrar(p, p.with_name(f"{p.stem}_reemplazado_{sello}{p.suffix}"), r))
                         for p in (ruta, ruta_j) if p.exists()]
            bitacora = list(previo.get("bitacora", [])) + [
                {"utc": ahora, "evento": "reemplazo", "huella_anterior": previo.get("huella_calidad"),
                 "respaldos": respaldos}]
        estado = "reemplazado" if previo is not None else "fijado"
    sha = publicar_parquet(out, ruta, r)
    verificar_escrito(ruta, out)
    meta["archivo"] = {**r.relativa(ruta), "sha256": sha, "bytes": ruta.stat().st_size, "filas": int(len(out)),
                       "columnas": COLUMNAS}
    meta["fijado_utc"] = ahora
    meta["bitacora"] = bitacora + [{"utc": ahora, "evento": estado, "huella_calidad": meta["huella_calidad"]}]
    publicar_json(meta, ruta_j, r)
    return estado, meta


def ejecutar(r: RutasV2, cfg: dict, contaminantes=CONTAMINANTES, escribir: bool = True, escribir_tablas: bool = True,
             reemplazar: bool = False, permitir_sin_bandera: bool = False, raiz_der: Path | None = None,
             auditoria: Path | None = None) -> tuple[dict, dict]:
    """Calcula la bandera de cada contaminante y, si corresponde, la fija en la raíz v2 (con candado y escritura
    atómica). ``raiz_der`` es la raíz de los derivados (por omisión, ``raiz_derivados``). Devuelve los metadatos
    vigentes y el estado de cada uno: «fijado», «sin_cambios», «reemplazado», «republicado» o «sin_escribir»."""
    hilos_cfg = int(cfg["operacion"]["hilos_maximos"])
    fijar_hilos(hilos_cfg)
    raiz_der = Path(raiz_der).resolve() if raiz_der is not None else raiz_derivados(r)
    derivado = derivado_sinca(raiz_der)
    ruta_aud = Path(auditoria) if auditoria is not None else ruta_auditoria(r)
    anual, huella_aud = leer_auditoria_anual(ruta_aud)
    semillas = {"usadas": None, "nota": "el proceso es determinista: no muestrea ni usa azar"}
    calculados = {}
    for pol in contaminantes:
        out, meta, extra = calidad_contaminante(r, pol, derivado, raiz_der, anual)
        t = traza(extra["insumos"], semillas, hilos_cfg, rutas=r, parametros=meta["parametros"])
        t["insumos_externos"] = dict(extra["extra"])
        if huella_aud is not None:
            t["insumos_externos"]["auditoria_ambiental_modelo"] = {
                **relativa_a(ruta_aud, Path(r.repo).parent, "repositorios"), **huella_aud}
        meta["traza"] = t
        calculados[pol] = (out, meta)
    sin = {pol: m["conciliacion"]["sin_bandera"] for pol, (_, m) in calculados.items()}
    if not escribir:
        return {pol: m for pol, (_, m) in calculados.items()}, {pol: "sin_escribir" for pol in calculados}
    if any(sin.values()) and not permitir_sin_bandera:
        detalle = {pol: calculados[pol][1]["conciliacion"]["sin_bandera_por_motivo"] for pol, k in sin.items() if k}
        raise SystemExit(f"Quedan filas del panel sin bandera {sin}; motivos: {json.dumps(detalle, ensure_ascii=False)[:2000]}. "
                         f"No se escribe nada; revisa el derivado o usa --permitir-sin-bandera.")
    estados, finales = {}, {}
    with candado_escritura(CANDADO, rutas=r):
        for pol, (out, meta) in calculados.items():
            estados[pol], finales[pol] = fijar(r, pol, out, meta, reemplazar)
            log.info("%s: bandera %s (%s)", pol, estados[pol], r.relativa(ruta_calidad(r, pol))["ruta"])
        if escribir_tablas:
            metas = {pol: finales.get(pol) or leer_json(ruta_meta(r, pol)) for pol in CONTAMINANTES}
            if all(metas.values()):
                publicar_tablas(metas, r, hilos_cfg)
            else:
                log.info("Tablas sin escribir: falta la bandera de %s", [p for p, m in metas.items() if not m])
    return finales, estados


# ---------------------------------------------------------------------------
# Tablas pequeñas para el repositorio
# ---------------------------------------------------------------------------
COLUMNAS_DISTRIBUCION = ["contaminante", "fuente", "anio", "filas", *CATEGORIAS, "pct_validado", "pct_preliminar",
                         "pct_no_validado", "pct_no_validado_o_preliminar", "pct_solo_numeric_usable", "pct_sin_bandera"]
COLUMNAS_ESTACIONES = ["contaminante", "estacion", "fuente", "version", "anio_desde", "anio_hasta", "filas", *CATEGORIAS,
                       "pct_validado", "pct_no_validado_o_preliminar", "pct_solo_numeric_usable"]
COLUMNAS_AUDITORIA = ["contaminante", "base", "medida", "v2", "auditoria", "coincide", "referencia"]


def _con_porcentajes(reg: dict) -> dict:
    n = reg["filas"]
    out = dict(reg)
    sinca = reg["fuente"] == RED_SINCA
    out["pct_validado"] = pct(reg["validado"], n, 2) if sinca else None
    out["pct_preliminar"] = pct(reg["preliminar"], n, 2) if sinca else None
    out["pct_no_validado"] = pct(reg["no_validado"], n, 2) if sinca else None
    out["pct_no_validado_o_preliminar"] = pct(reg["preliminar"] + reg["no_validado"], n, 2) if sinca else None
    out["pct_solo_numeric_usable"] = None if sinca else pct(reg["solo_numeric_usable"], n, 2)
    out["pct_sin_bandera"] = pct(reg[SIN_BANDERA], n, 2)
    return out


def filas_auditoria(pol: str, aud: dict) -> list[dict]:
    filas = []
    for base in ("sinca_panel", "sinca_antes_de_rachas", "snifa_antes_de_rachas"):
        b = aud.get(base)
        if not b or "v2" not in b:
            continue
        ref = b.get("auditoria") or {}
        for medida, v2 in b["v2"].items():
            r = ref.get(medida)
            if r is None:
                coincide = None
            elif medida.startswith("pct_"):
                coincide = coincide_redondeado(v2, r)
            else:
                coincide = v2 == r
            filas.append({"contaminante": pol, "base": base, "medida": medida, "v2": v2, "auditoria": r,
                          "coincide": coincide, "referencia": b.get("referencia")})
    anual = aud.get("sinca_anual") or {}
    if anual.get("coincide") is not None:
        filas.append({"contaminante": pol, "base": "sinca_anual", "medida": "dif_max_fraccion_por_anio",
                      "v2": anual.get("dif_max"), "auditoria": 0.0, "coincide": anual["coincide"],
                      "referencia": anual.get("referencia")})
    return filas


def tablas(metas: Mapping[str, dict]) -> dict[str, pd.DataFrame]:
    dist, est, aud = [], [], []
    for pol in CONTAMINANTES:
        m = metas[pol]
        d = m["distribucion"]
        orden = {f: i for i, f in enumerate(FUENTES)}
        for reg in sorted(d["por_anio"], key=lambda x: (orden[x["fuente"]], x["anio"])):
            dist.append(_con_porcentajes({"contaminante": pol, **reg}))
        for reg in sorted(d["total"], key=lambda x: orden[x["fuente"]]):
            dist.append(_con_porcentajes({"contaminante": pol, **reg, "anio": "total"}))
        for reg in sorted(d["por_estacion"], key=lambda x: (orden[x["fuente"]], x["estacion"])):
            est.append(_con_porcentajes({"contaminante": pol, **reg}))
        aud.extend(filas_auditoria(pol, m["auditoria"]))
    # En la comparación conviven recuentos y porcentajes: columnas de objetos, para que un recuento no salga «9740634.0».
    comparacion = pd.DataFrame({c: pd.Series([f.get(c) for f in aud], dtype=object) for c in COLUMNAS_AUDITORIA})
    return {TABLA_DISTRIBUCION: pd.DataFrame(dist).reindex(columns=COLUMNAS_DISTRIBUCION),
            TABLA_ESTACIONES: pd.DataFrame(est).reindex(columns=COLUMNAS_ESTACIONES),
            TABLA_AUDITORIA: comparacion}


def publicar_tablas(metas: Mapping[str, dict], r: RutasV2, hilos_cfg: int) -> bool:
    """Tablas pequeñas en ``output_files/modelo_1km_v2`` más un JSON lateral con su traza. Sólo reescribe lo que
    cambió, para no ensuciar git con fechas. Exige el candado."""
    cambios, shas = False, {}
    for nombre, df in tablas(metas).items():
        datos = df.to_csv(index=False, lineterminator="\n").encode("utf-8")
        destino = r.salidas_v2 / nombre
        shas[nombre] = hashlib.sha256(datos).hexdigest()
        if destino.exists() and destino.read_bytes() == datos:
            continue
        publicar_bytes(datos, destino, r)
        cambios = True
    huellas = {pol: metas[pol]["huella_calidad"] for pol in CONTAMINANTES}
    lateral = r.salidas_v2 / NOMBRE_LATERAL
    previo = leer_json(lateral)
    if cambios or previo is None or previo.get("huellas_calidad") != huellas or previo.get("tablas") != shas:
        publicar_json({"schema": SCHEMA_TABLAS,
                       "descripcion": ("Tablas resumen de la bandera de calidad del blanco v2 (§7); la fuente son "
                                       "paneles/calidad_<pol>.json de la raíz v2."),
                       "huellas_calidad": huellas, "tablas": shas,
                       "resumen": {pol: metas[pol]["resumen"] for pol in CONTAMINANTES},
                       "traza": traza({f"calidad_{pol}": ruta_meta(r, pol) for pol in CONTAMINANTES},
                                      {"usadas": None}, hilos_cfg, rutas=r)},
                      lateral, r)
        cambios = True
    return cambios


# ---------------------------------------------------------------------------
# Lectura para las etapas siguientes
# ---------------------------------------------------------------------------
def cargar_bandera(pol: str, panel: pd.DataFrame | None = None, r: RutasV2 | None = None) -> pd.DataFrame:
    """Lee ``calidad_<pol>.parquet`` y, si se pasa el panel (con ``estacion`` y ``ts_utc`` en su orden original),
    comprueba que está alineado 1 a 1 con él antes de devolverlo."""
    r = r or rutas_v2()
    df = pd.read_parquet(ruta_calidad(r, pol), columns=COLUMNAS)
    if panel is not None:
        iguales = (len(df) == len(panel)
                   and np.array_equal(df["ts_utc"].to_numpy("datetime64[ns]"), panel["ts_utc"].to_numpy("datetime64[ns]"))
                   and np.array_equal(df["estacion"].astype(str).to_numpy(), panel["estacion"].astype(str).to_numpy()))
        if not iguales:
            raise ValueError(f"calidad_{pol}.parquet no está alineado con el panel que se le pasó")
    return df


def resumen_texto(metas: Mapping[str, dict], estados: Mapping[str, str]) -> str:
    lineas = []
    for pol, m in metas.items():
        s = m["resumen"]
        lineas.append(f"Bandera de calidad {pol}: {estados.get(pol)}; huella {m['huella_calidad'][:16]}; "
                      f"{s['con_bandera']:,} de {s['filas_panel']:,} filas con bandera (sin bandera: {s['sin_bandera']:,})")
        if "sinca" in s:
            x = s["sinca"]
            lineas.append(f"  SINCA {x['filas']:,} filas: validado {x['pct_validado']} %, preliminar {x['pct_preliminar']} %, "
                          f"no validado {x['pct_no_validado']} % (no validado o preliminar {x['pct_no_validado_o_preliminar']} %)")
        if "snifa" in s:
            x = s["snifa"]
            lineas.append(f"  SNIFA {x['filas']:,} filas: solo_numeric_usable {x['solo_numeric_usable']:,} "
                          f"({x['pct_solo_numeric_usable']} %), horas mixtas {x['horas_mixtas']}")
        lineas.append(f"  Coincide con la auditoría: {s['auditoria_coincide']}")
        d = m["convenciones"]["prueba_desfase_sinca"]
        if d:
            lineas.append("  Desfase SINCA: " + ", ".join(f"{k} {v['obs_iguales']:.4f}" for k, v in d["por_desfase"].items()))
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bandera de calidad del blanco v2 (DISENO_AMBIENTAL_V2.md §7).")
    ap.add_argument("--contaminantes", nargs="+", default=list(CONTAMINANTES), choices=CONTAMINANTES)
    ap.add_argument("--no-escribir", action="store_true", help="calcula y resume sin escribir nada")
    ap.add_argument("--sin-tablas", action="store_true", help="no escribe las tablas de output_files/modelo_1km_v2")
    ap.add_argument("--reemplazar", action="store_true",
                    help="reemplaza una bandera fijada con otra huella; la anterior se guarda con fecha")
    ap.add_argument("--permitir-sin-bandera", action="store_true",
                    help="escribe aunque queden filas del panel sin bandera (el motivo queda en el JSON)")
    ap.add_argument("--auditoria", type=Path, default=None,
                    help=f"JSON de la auditoría ambiental del 2026-10-12 para comparar por año (por omisión, "
                         f"{VAR_AUDITORIA} o el repositorio hermano)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    r = rutas_v2()
    cfg = cargar_config(r)
    metas, estados = ejecutar(r, cfg, contaminantes=tuple(args.contaminantes), escribir=not args.no_escribir,
                              escribir_tablas=not args.sin_tablas, reemplazar=args.reemplazar,
                              permitir_sin_bandera=args.permitir_sin_bandera, auditoria=args.auditoria)
    print(resumen_texto(metas, estados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
