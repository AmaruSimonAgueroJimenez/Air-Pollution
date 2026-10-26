#!/usr/bin/env python3
"""Manifiesto de pliegues de la v2: grupos, exclusiones, k y semillas, fijados antes de estimar.

Traduce §1 del contrato ``DISENO_AMBIENTAL_V2.md`` (protocolos externos) y lo deja en
``<raíz v2>/pliegues_v2.json``, por contaminante, con las estaciones del panel v1
(``paneles/panel_<pol>.parquet``, sólo lectura) y las coordenadas que usa el modelo:
``estaciones_con_celda()``, es decir, el catálogo SINCA georreferenciado más los 3 monitores SNIFA, con
su celda de la grilla v1. Esa función vive en el documento de la v1 (``qmd:1968-1970``) y no en una
librería importable, así que aquí se replica citando cada pieza; ``_comun_modelo`` no se importa para no
heredar su raíz de datos.

Protocolos:

* **LOSO-D**: conglomerado de estaciones a ≤ 2 km (componentes conexas, distancia haversine) o que
  comparten celda. Retira juntas, por ejemplo, 309/310/330/333 (Huasco), B03/B04 (Coyhaique) y 503/548.
* **LBO-10**: el mismo conglomerado; además sale del entrenamiento y del vecindario toda estación a
  ≤ 10 km de alguna estación del conglomerado. Como en la v1 (``qmd:2775-2786``), la comparación es ``<=``
  y el radio se mide sobre las estaciones con celda de las dos redes; las que no están en el panel del
  contaminante se registran aparte, porque no aportan filas ni vecindario.
* **BLQ-75**: bloque de una rejilla fija de 75 km en UTM 19S (EPSG:32719) con al menos una estación, con el
  origen falso de la proyección (0, 0), ratificado por la Enmienda 1 (punto 1.1); se registran el origen y los
  límites de cada bloque. **Amortiguador** (Enmienda 1, punto 8): como la rejilla parte Gran Santiago, Gran
  Concepción y Quintero-Puchuncaví, se excluyen además del entrenamiento y del vecindario las estaciones a
  ≤ 10 km (haversine) de cualquier estación del bloque de prueba, con el mismo universo y la misma comparación
  que LBO-10. Cada bloque informa la distancia mínima de prueba a entrenamiento, con el amortiguador y sin él.
* **LRO**: región SINCA. Ñuble va como RVIII, como en la v1 (SINCA ya rotula así a sus estaciones).
* **LPO**: cuatrienio del año local, con las ventanas de la v1 (2000–2003 … 2024–2026). El vecindario de
  prueba usa la red concurrente; se declara así.

Todas las distancias son haversine con R = 6.371 km, como la v1 (Enmienda 1, punto 13). Los conglomerados de
LOSO-D encadenados (diámetro mayor que el umbral de 2 km) quedan listados en los diagnósticos.

Cada pliegue lleva su grupo, las estaciones de prueba, el conjunto excluido, k, la semilla [42, k] de la
permutación común (§4), las filas de prueba y de entrenamiento disponibles y, en los protocolos espaciales, la
distancia mínima de una estación de prueba a una de entrenamiento. El conjunto excluido es uno solo y se aplica a
las filas de entrenamiento, al vecindario de entrenamiento y de prueba y a los residuos de la retransformación
(§1). En LPO la exclusión es temporal (las filas del cuatrienio) y no se excluye ninguna estación del vecindario.

El manifiesto no se reescribe en silencio. Si ya existe con la misma huella, no se toca; si la huella
difiere, el programa se detiene, porque el contrato fija los pliegues antes de estimar. ``--reemplazar``
(con ``--motivo``, p. ej. la enmienda) lo reemplaza: el anterior queda intacto como respaldo con fecha y su
sha256, y la bitácora nueva empieza con el evento «reemplazo», que guarda la huella, el respaldo, el motivo y la
bitácora anterior; los eventos de la bitácora de primer nivel se refieren siempre a los pliegues vigentes.
``--refijar`` (con ``--motivo``) vuelve a fijar el manifiesto vigente bajo el contrato, la configuración y el código
actuales **sin cambiar los pliegues**: exige la misma huella, deja el anterior como respaldo (mismos bytes y fechas)
y sigue la bitácora con un evento «fijado» que cita el contrato anterior y el vigente y el respaldo.
``--anotar`` agrega un evento a la bitácora (por ejemplo, un recorte del presupuesto, §10) sin tocar los pliegues.
Después del último «fijado» sólo puede haber eventos que no tocan los pliegues: los recortes del presupuesto
(``EVENTOS_TRAS_FIJAR``).

En ``output_files/modelo_1km_v2/`` quedan cuatro tablas pequeñas (resumen por protocolo, un renglón por
pliegue, conglomerados de LOSO-D con más de una estación y bloques de BLQ-75) y
``pliegues_v2_tablas.json``, con la huella del manifiesto, el sha256 de cada tabla y su traza.

Uso::

    python -B scripts_modelo_1km/v2/pliegues_v2.py                 # fija o verifica el manifiesto
    python -B scripts_modelo_1km/v2/pliegues_v2.py --no-escribir   # sólo calcula y resume
    python -B scripts_modelo_1km/v2/pliegues_v2.py --reemplazar --motivo "Enmienda 1, punto 8" --hilos 8
    python -B scripts_modelo_1km/v2/pliegues_v2.py --refijar --motivo "contrato vigente" --sin-tablas --hilos 8
    python -B scripts_modelo_1km/v2/pliegues_v2.py --anotar recorte --nota "semillas sólo en LRO"
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _traza_v2 import fijar_hilos  # noqa: E402  (antes de numpy: fija el tope de hilos de BLAS y OpenMP)

if __name__ == "__main__":
    from _rutas_v2 import hilos_de_la_linea  # noqa: E402
    fijar_hilos(hilos_de_la_linea())

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from _rutas_v2 import (  # noqa: E402
    RutasV2, ahora_utc, candado_escritura, cargar_config, copiar_artefacto, estado_vigente, leer_json, publicar_bytes,
    publicar_json, renombrar, ruta_de_respaldo, rutas_v2, valor_vigente,
)
from _traza_v2 import sha256_archivo, sha256_json, traza  # noqa: E402

log = logging.getLogger("modelo_1km_v2.pliegues")

SCHEMA = "airpollution.modelo-1km-v2.pliegues.v2"          # v2: BLQ-75 con amortiguador (Enmienda 1, punto 8)
SCHEMA_TABLAS = "airpollution.modelo-1km-v2.pliegues-tablas.v1"
NOMBRE_LATERAL = "pliegues_v2_tablas.json"
CONTAMINANTES = ("pm25", "no2")
PROTOCOLOS = ("LOSO-D", "LBO-10", "BLQ-75", "LRO", "LPO")
RADIO_TIERRA_KM = 6371.0
DECIMALES_KM = 4                    # distancias registradas al décimo de metro
DECIMALES_M = 3                     # coordenadas proyectadas al milímetro
TOLERANCIA_COORD_GRADOS = 1e-5      # el panel guarda lat_est/lon_est en float32 (qmd:2058-2060)
COLUMNAS_PANEL = ["estacion", "celda", "region_sinca", "lat_est", "lon_est", "anio"]
CLAVES_HUELLA = ("schema", "parametros", "estaciones", "contaminantes")
EVENTO_FIJADO = "fijado"
EVENTOS_TRAS_FIJAR = ("recorte_presupuesto",)   # §10: los recortes del presupuesto se anotan después de fijar

# Red adicional SNIFA: réplica de _red_adicional.py:42-46 (sólo aporta NO2).
ESTACIONES_SNIFA = {
    "charrua": ("SNIFA-CHARRUA", "Charrúa (SNIFA)"),
    "progreso": ("SNIFA-PROGRESO", "Progreso (SNIFA)"),
    "el_penon": ("SNIFA-ELPENON", "El Peñón (SNIFA)"),
}
INSUMOS_GRILLA = ("celdas.parquet", "estaciones_enlaces.parquet", "estaciones_enlaces_adicional.parquet")


# ---------------------------------------------------------------------------
# Geometría
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia de gran círculo en km; réplica exacta de ``_features.py:330-334`` (R = 6371 km)."""
    a1, a2 = np.radians(lat1), np.radians(lat2)
    da, do = a2 - a1, np.radians(lon2 - lon1)
    x = np.sin(da / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin(do / 2) ** 2
    return 2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(x, 0, 1)))


def matriz_distancias(lat, lon, lat2=None, lon2=None) -> np.ndarray:
    """Distancias haversine (km) entre los puntos (lat, lon) y (lat2, lon2); sin estos, entre los primeros."""
    lat, lon = np.asarray(lat, dtype="float64"), np.asarray(lon, dtype="float64")
    lat2 = lat if lat2 is None else np.asarray(lat2, dtype="float64")
    lon2 = lon if lon2 is None else np.asarray(lon2, dtype="float64")
    return haversine_km(lat[:, None], lon[:, None], lat2[None, :], lon2[None, :])


def proyectar(lon, lat, crs: str) -> tuple[np.ndarray, np.ndarray]:
    """(lon, lat) WGS84 → (este, norte) en ``crs``."""
    from pyproj import Transformer

    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    este, norte = t.transform(np.asarray(lon, dtype="float64"), np.asarray(lat, dtype="float64"))
    return np.asarray(este, dtype="float64"), np.asarray(norte, dtype="float64")


def a_lonlat(este, norte, crs: str) -> tuple[np.ndarray, np.ndarray]:
    from pyproj import Transformer

    t = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = t.transform(np.asarray(este, dtype="float64"), np.asarray(norte, dtype="float64"))
    return np.asarray(lon, dtype="float64"), np.asarray(lat, dtype="float64")


# ---------------------------------------------------------------------------
# Agrupamientos (funciones puras)
# ---------------------------------------------------------------------------
def etiqueta_conglomerado(miembros) -> str:
    return "+".join(sorted(str(m) for m in miembros))


def conglomerados(nombres, D: np.ndarray, celdas, umbral_km: float) -> list[tuple[str, ...]]:
    """Componentes conexas del grafo en que dos estaciones se unen si están a ``<= umbral_km`` o comparten
    celda. Devuelve cada conglomerado como tupla ordenada, en el orden lexicográfico de su etiqueta."""
    nombres = [str(x) for x in nombres]
    padre = list(range(len(nombres)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    celdas = np.asarray(celdas)
    unir = (np.asarray(D, dtype="float64") <= umbral_km) | (celdas[:, None] == celdas[None, :])
    for i, j in zip(*np.nonzero(np.triu(unir, 1))):
        ri, rj = raiz(int(i)), raiz(int(j))
        if ri != rj:
            padre[max(ri, rj)] = min(ri, rj)
    grupos: dict[int, list[str]] = {}
    for i, nombre in enumerate(nombres):
        grupos.setdefault(raiz(i), []).append(nombre)
    return sorted((tuple(sorted(g)) for g in grupos.values()), key=etiqueta_conglomerado)


def aristas(miembros, indice: dict, D: np.ndarray, celdas, umbral_km: float) -> list[dict]:
    """Pares del conglomerado que lo unen: a ``<= umbral_km`` o en la misma celda."""
    celdas = np.asarray(celdas)
    out = []
    for pos, a in enumerate(miembros):
        for b in miembros[pos + 1:]:
            i, j = indice[a], indice[b]
            d, misma = float(D[i, j]), bool(celdas[i] == celdas[j])
            if d <= umbral_km or misma:
                out.append({"a": a, "b": b, "km": round(d, DECIMALES_KM), "misma_celda": misma})
    return out


def excluidas_por_radio(D_grupo_universo: np.ndarray, nombres_universo, radio_km: float) -> list[str]:
    """Estaciones del universo a ``<= radio_km`` de alguna estación del grupo (filas de la matriz), con la
    misma comparación que la v1 (``qmd:2785``)."""
    cerca = (np.asarray(D_grupo_universo, dtype="float64") <= radio_km).any(axis=0)
    return sorted(str(x) for x in np.asarray(nombres_universo, dtype=object)[cerca])


def distancia_minima_km(D: np.ndarray, desde, hasta) -> float | None:
    """Menor distancia (km, al décimo de metro) entre las estaciones ``desde`` y ``hasta`` (índices de ``D``); None
    si alguno de los dos conjuntos está vacío."""
    desde, hasta = list(desde), list(hasta)
    if not desde or not hasta:
        return None
    return round(float(np.asarray(D, dtype="float64")[np.ix_(desde, hasta)].min()), DECIMALES_KM)


def indices_bloque(este, norte, origen, lado_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Índices (ix, iy) de la celda de la rejilla fija: ``floor((coordenada − origen) / lado)``."""
    ix = np.floor((np.asarray(este, dtype="float64") - float(origen[0])) / float(lado_m)).astype("int64")
    iy = np.floor((np.asarray(norte, dtype="float64") - float(origen[1])) / float(lado_m)).astype("int64")
    return ix, iy


def etiqueta_bloque(ix: int, iy: int) -> str:
    if ix < 0 or iy < 0:
        raise ValueError(f"bloque con índice negativo ({ix}, {iy}): revisa el origen de la rejilla")
    return f"E{int(ix):03d}N{int(iy):03d}"


def limites_bloque(ix: int, iy: int, origen, lado_m: float) -> dict:
    e0 = float(origen[0]) + int(ix) * float(lado_m)
    n0 = float(origen[1]) + int(iy) * float(lado_m)
    return {"este_min_m": e0, "norte_min_m": n0, "este_max_m": e0 + float(lado_m), "norte_max_m": n0 + float(lado_m)}


def ventana_de(anio, anio_desde: int, anio_hasta: int, largo: int = 4) -> np.ndarray:
    """Etiqueta «AAAA–AAAA» del cuatrienio de cada año; réplica de ``qmd:347-351`` con las anclas de la v1."""
    a = np.asarray(anio, dtype="int64")
    ini = anio_desde + largo * ((a - anio_desde) // largo)
    return np.array([f"{i}–{min(i + largo - 1, anio_hasta)}" for i in ini], dtype=object)


# ---------------------------------------------------------------------------
# Estaciones con celda (réplica de la v1) y panel
# ---------------------------------------------------------------------------
def leer_estaciones_sinca(r: RutasV2) -> pd.DataFrame:
    """Catálogo SINCA georreferenciado, sólo ``usable_geoespacial``; réplica de ``_comun_modelo.py:593-599``."""
    est = pd.read_csv(r.catalogo_sinca, dtype={"estacion": str})
    usable = est["usable_geoespacial"].astype(str).str.lower().isin(["true", "1"])
    est = est[usable].copy()
    est["cod_comuna"] = pd.to_numeric(est["cod_comuna_geografica"], errors="coerce").astype("Int64")
    est = est[["estacion", "nombre", "region_sinca", "lat", "lon", "cod_comuna"]].reset_index(drop=True)
    est["red"] = "sinca"
    return est


def leer_estaciones_snifa(r: RutasV2, sinca: pd.DataFrame) -> pd.DataFrame:
    """Los tres monitores SNIFA; réplica de ``_red_adicional.py:59-62`` y ``72-96``: coordenadas del primer
    registro numérico utilizable de cada uno; comuna y región, de la celda de la grilla más cercana."""
    if not r.snifa.exists():
        raise SystemExit(f"Falta la red adicional SNIFA ({r.relativa(r.snifa)}); los paneles v1 la incluyen")
    o = pd.read_parquet(r.snifa, columns=["station_id", "numeric_usable", "latitude", "longitude"])
    o = o[o["station_id"].isin(list(ESTACIONES_SNIFA)) & o["numeric_usable"].astype(bool)]
    o = o.groupby("station_id").agg(lat=("latitude", "first"), lon=("longitude", "first")).reset_index()
    celdas = pd.read_parquet(r.grilla_v1 / "celdas.parquet", columns=["celda", "lat", "lon", "cod_comuna"])
    region_de = (sinca.assign(rr=sinca["cod_comuna"].astype("float64") // 1000).dropna(subset=["rr"])
                 .groupby("rr")["region_sinca"].first().to_dict())
    filas = []
    for f in o.itertuples(index=False):
        d = haversine_km(f.lat, f.lon, celdas["lat"].to_numpy(), celdas["lon"].to_numpy())
        cod = celdas["cod_comuna"].iloc[int(np.argmin(d))]
        codigo, nombre = ESTACIONES_SNIFA[f.station_id]
        filas.append({"estacion": codigo, "nombre": nombre,
                      "region_sinca": region_de.get(float(cod) // 1000, "sin_region") if pd.notna(cod) else "sin_region",
                      "lat": float(f.lat), "lon": float(f.lon),
                      "cod_comuna": pd.NA if pd.isna(cod) else int(cod), "red": "snifa"})
    est = pd.DataFrame(filas, columns=["estacion", "nombre", "region_sinca", "lat", "lon", "cod_comuna", "red"])
    est["cod_comuna"] = est["cod_comuna"].astype("Int64")
    return est


def estaciones_con_celda(r: RutasV2) -> pd.DataFrame:
    """Réplica de ``estaciones_con_celda()`` (``qmd:1968-1970``): ``leer_estaciones()`` de
    ``produccion.py:50-56`` (SINCA más la red adicional SNIFA, como los paneles v1, que registran
    redes = [sinca, snifa]) unido a la celda de los enlaces de la grilla v1 (``qmd:1608`` y ``1610-1630``)."""
    sinca = leer_estaciones_sinca(r)
    est = pd.concat([sinca, leer_estaciones_snifa(r, sinca)], ignore_index=True)
    enl = pd.concat([pd.read_parquet(r.grilla_v1 / nombre, columns=["estacion", "celda"])
                     for nombre in INSUMOS_GRILLA[1:]], ignore_index=True)
    est = est.merge(enl, on="estacion", how="inner")
    est = est[est["celda"] >= 0].drop_duplicates("estacion").reset_index(drop=True)
    est["celda"] = est["celda"].astype("int64")
    return est


def preparar_universo(r: RutasV2, cfg: dict) -> pd.DataFrame:
    """Estaciones con celda, proyectadas a la rejilla de BLQ-75 y con su región de LRO."""
    return completar_universo(estaciones_con_celda(r), cfg)


def completar_universo(est: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Agrega a las estaciones (estacion, lat, lon, celda, region_sinca, …) sus coordenadas en la rejilla de
    BLQ-75, su bloque y su región de LRO. Función pura."""
    p = cfg["protocolos"]
    blq = p["BLQ-75"]
    origen = [float(x) for x in valor_vigente(blq["origen_m"], "protocolos.BLQ-75.origen_m")]
    est = est.copy()
    este, norte = proyectar(est["lon"], est["lat"], blq["crs"])
    est["este_m"], est["norte_m"] = np.round(este, DECIMALES_M), np.round(norte, DECIMALES_M)
    ix, iy = indices_bloque(est["este_m"], est["norte_m"], origen, blq["lado_m"])
    est["bloque_ix"], est["bloque_iy"] = ix, iy
    est["bloque_blq75"] = [etiqueta_bloque(a, b) for a, b in zip(ix, iy)]
    equivalencias = p["LRO"].get("equivalencias", {})
    est["region_lro"] = [equivalencias.get(str(x), str(x)) for x in est["region_sinca"]]
    return est.sort_values("estacion", kind="stable").reset_index(drop=True)


def leer_panel(r: RutasV2, pol: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Estaciones del panel v1 (sólo lectura) con su celda, región y coordenadas, y filas por estación × año
    local. Lee sólo seis columnas; el panel no se modifica."""
    import pyarrow.parquet as pq

    ruta = r.panel(pol)
    if not ruta.exists():
        raise SystemExit(f"Falta el panel v1 {r.relativa(ruta)}")
    df = pq.read_table(ruta, columns=COLUMNAS_PANEL, read_dictionary=["estacion", "region_sinca"]).to_pandas()
    g = df.groupby("estacion", observed=True, sort=True)
    por_est = pd.DataFrame({
        "celda": g["celda"].first(), "n_celdas": g["celda"].nunique(),
        "region_sinca": g["region_sinca"].first().astype(str), "n_regiones": g["region_sinca"].nunique(),
        "lat_est": g["lat_est"].first(), "lon_est": g["lon_est"].first(),
        "n_coordenadas": g["lat_est"].nunique() + g["lon_est"].nunique() - 1,
        "filas": g.size(),
    })
    por_est.index = por_est.index.astype(str)
    por_est.index.name = "estacion"
    raras = por_est[(por_est["n_celdas"] > 1) | (por_est["n_regiones"] > 1) | (por_est["n_coordenadas"] > 1)]
    if len(raras):
        raise SystemExit(f"{pol}: estaciones con más de una celda, región o coordenada en el panel: {list(raras.index)}")
    conteos = df.groupby(["estacion", "anio"], observed=True, sort=True).size().rename("filas").reset_index()
    conteos["estacion"] = conteos["estacion"].astype(str)
    conteos["anio"] = conteos["anio"].astype("int64")
    if int(por_est["filas"].sum()) != len(df):
        raise SystemExit(f"{pol}: los conteos por estación no suman las filas del panel")
    meta = leer_json(r.panel_meta(pol)) or {}
    return por_est.drop(columns=["n_celdas", "n_regiones", "n_coordenadas"]), conteos, meta


# ---------------------------------------------------------------------------
# Pliegues
# ---------------------------------------------------------------------------
def _pliegue(k: int, grupo: str, prueba, excluidas, filas_est: dict, total: int, semilla0: int, **extra) -> dict:
    """Pliegue espacial: el conjunto excluido contiene a las estaciones de prueba y, en LBO-10 y BLQ-75, su entorno."""
    prueba, excluidas = sorted(prueba), sorted(excluidas)
    faltan = set(prueba) - set(excluidas)
    if faltan:
        raise ValueError(f"pliegue {grupo}: estaciones de prueba fuera del conjunto excluido: {sorted(faltan)}")
    filas_prueba = sum(filas_est[s] for s in prueba)
    filas_excluidas = sum(filas_est[s] for s in excluidas)
    return {"k": k, "semilla": [semilla0, k], "grupo": grupo, "estaciones_prueba": prueba, "excluidas": excluidas,
            **extra,
            "vecindario": "recalculado sin las excluidas, en entrenamiento y en prueba",
            "filas_prueba": int(filas_prueba),
            "filas_entrenamiento_disponibles": int(total - filas_excluidas),
            "filas_fuera_del_pliegue": int(filas_excluidas - filas_prueba),
            "estaciones_entrenamiento": len(filas_est) - len(excluidas)}


def radio_amortiguador_blq(cfg: dict) -> float | None:
    """Radio (km) del amortiguador de BLQ-75 (Enmienda 1, punto 8); None si la configuración no lo trae."""
    ex = cfg["protocolos"]["BLQ-75"].get("exclusion_adicional")
    if not isinstance(ex, dict) or "radio_km" not in ex:
        return None
    if ex.get("comparacion", "<=") != "<=":
        raise ValueError("el amortiguador de BLQ-75 se mide con <=, como LBO-10")
    return float(ex["radio_km"])


def construir_contaminante(pol: str, universo: pd.DataFrame, por_est: pd.DataFrame, conteos: pd.DataFrame,
                           cfg: dict, panel_info: dict) -> dict:
    """Los cinco protocolos de un contaminante, con su registro de conglomerados y bloques y diagnósticos."""
    p = cfg["protocolos"]
    semilla0 = int(p["semilla"]["regla"][0])
    blq_cfg = p["BLQ-75"]
    origen = [float(x) for x in valor_vigente(blq_cfg["origen_m"], "protocolos.BLQ-75.origen_m")]
    lado = float(blq_cfg["lado_m"])
    radio_blq = radio_amortiguador_blq(cfg)
    equivalencias = p["LRO"].get("equivalencias", {})

    # Estaciones del panel con las coordenadas, la celda y el bloque del modelo.
    cols_u = ["estacion", "lat", "lon", "celda", "cod_comuna", "region_sinca", "este_m", "norte_m",
              "bloque_ix", "bloque_iy", "bloque_blq75"]
    est = (por_est.reset_index()
           .merge(universo[cols_u].rename(columns={"celda": "celda_modelo", "region_sinca": "region_modelo"}),
                  on="estacion", how="left", validate="one_to_one"))
    faltan = est.loc[est["lat"].isna(), "estacion"].tolist()
    if faltan:
        raise SystemExit(f"{pol}: estaciones del panel sin celda en estaciones_con_celda(): {faltan}")
    dif = float(max((est["lat_est"].astype("float64") - est["lat"]).abs().max(),
                    (est["lon_est"].astype("float64") - est["lon"]).abs().max()))
    if dif > TOLERANCIA_COORD_GRADOS:
        raise SystemExit(f"{pol}: las coordenadas del panel difieren de las del modelo en {dif:.2e}°")
    if (est["celda"].astype("int64") != est["celda_modelo"].astype("int64")).any():
        raise SystemExit(f"{pol}: la celda del panel no coincide con la de estaciones_con_celda()")
    if (est["region_sinca"] != est["region_modelo"]).any():
        raise SystemExit(f"{pol}: la región del panel no coincide con la de estaciones_con_celda()")
    est["region_lro"] = [equivalencias.get(x, x) for x in est["region_sinca"]]
    est = est.sort_values("estacion", kind="stable").reset_index(drop=True)

    nombres = est["estacion"].tolist()
    indice = {s: i for i, s in enumerate(nombres)}
    filas_est = {s: int(n) for s, n in zip(nombres, est["filas"])}
    total = int(sum(filas_est.values()))
    lat, lon, celdas = est["lat"].to_numpy(float), est["lon"].to_numpy(float), est["celda"].to_numpy("int64")
    D = matriz_distancias(lat, lon)
    en_panel = set(nombres)
    u_nombres = universo["estacion"].to_numpy(dtype=object)
    u_lat, u_lon = universo["lat"].to_numpy(float), universo["lon"].to_numpy(float)

    def entorno(miembros, radio_km: float) -> tuple[list[str], list[str]]:
        """Estaciones con celda (dos redes) a <= radio de algún miembro: (las del panel, las de fuera del panel)."""
        idx = [indice[s] for s in miembros]
        cerca = excluidas_por_radio(matriz_distancias(lat[idx], lon[idx], u_lat, u_lon), u_nombres, radio_km)
        return [s for s in cerca if s in en_panel], [s for s in cerca if s not in en_panel]

    def a_entrenamiento(prueba, excluidas) -> float | None:
        """Distancia mínima de una estación de prueba a una de entrenamiento (del panel, fuera del excluido)."""
        fuera = set(excluidas)
        return distancia_minima_km(D, [indice[s] for s in prueba], [i for i, s in enumerate(nombres) if s not in fuera])

    # LOSO-D: conglomerados a <= 2 km o en la misma celda.
    umbral = float(p["LOSO-D"]["umbral_km"])
    congl = conglomerados(nombres, D, celdas, umbral)
    etiquetas = [etiqueta_conglomerado(c) for c in congl]
    loso = [_pliegue(k, etq, c, c, filas_est, total, semilla0, distancia_minima_entrenamiento_km=a_entrenamiento(c, c))
            for k, (etq, c) in enumerate(zip(etiquetas, congl))]

    # LBO-10: el mismo conglomerado y toda estación con celda (dos redes) a <= 10 km de él.
    radio = float(p["LBO-10"]["exclusion_adicional"]["radio_km"])
    lbo = []
    for k, (etq, c) in enumerate(zip(etiquetas, congl)):
        excl, fuera = entorno(c, radio)
        lbo.append(_pliegue(k, etq, c, excl, filas_est, total, semilla0, radio_incluye_fuera_del_panel=fuera,
                            distancia_minima_entrenamiento_km=a_entrenamiento(c, excl)))

    # BLQ-75: bloque de la rejilla fija que contiene a cada estación, con el amortiguador de 10 km (punto 8).
    bloques: dict[str, list] = {}
    for s, etq, ix, iy in zip(nombres, est["bloque_blq75"], est["bloque_ix"], est["bloque_iy"]):
        bloques.setdefault(etq, [int(ix), int(iy), []])[2].append(s)
    orden_bloques = sorted(bloques)
    centros = np.array([[origen[0] + (bloques[b][0] + 0.5) * lado, origen[1] + (bloques[b][1] + 0.5) * lado]
                        for b in orden_bloques]).reshape(-1, 2)
    c_lon, c_lat = a_lonlat(centros[:, 0], centros[:, 1], blq_cfg["crs"])
    blq, registro_bloques = [], []
    for k, etq in enumerate(orden_bloques):
        ix, iy, miembros = bloques[etq]
        miembros = sorted(miembros)
        lim = limites_bloque(ix, iy, origen, lado)
        if radio_blq is not None:
            cerca, fuera = entorno(miembros, radio_blq)
            excl = sorted(set(miembros) | set(cerca))
        else:
            excl, fuera = list(miembros), []
        por_amortiguador = sorted(set(excl) - set(miembros))
        d_con, d_sin = a_entrenamiento(miembros, excl), a_entrenamiento(miembros, miembros)
        amortiguador = {"radio_km": radio_blq, "excluidas_por_amortiguador": por_amortiguador,
                        "radio_incluye_fuera_del_panel": fuera}
        blq.append(_pliegue(k, etq, miembros, excl, filas_est, total, semilla0, bloque={"ix": ix, "iy": iy, **lim},
                            amortiguador=amortiguador, distancia_minima_entrenamiento_km=d_con,
                            distancia_minima_sin_amortiguador_km=d_sin))
        registro_bloques.append({"grupo": etq, "k": k, "ix": ix, "iy": iy, **lim,
                                 "centro_lonlat": [round(float(c_lon[k]), 5), round(float(c_lat[k]), 5)],
                                 "estaciones": miembros, "filas": sum(filas_est[s] for s in miembros),
                                 "excluidas_por_amortiguador": por_amortiguador,
                                 "radio_incluye_fuera_del_panel": fuera,
                                 "distancia_minima_entrenamiento_km": d_con,
                                 "distancia_minima_sin_amortiguador_km": d_sin})

    # LRO: región SINCA (Ñuble como RVIII).
    regiones: dict[str, list] = {}
    for s, reg in zip(nombres, est["region_lro"]):
        regiones.setdefault(str(reg), []).append(s)
    lro = [_pliegue(k, reg, regiones[reg], regiones[reg], filas_est, total, semilla0,
                    distancia_minima_entrenamiento_km=a_entrenamiento(regiones[reg], regiones[reg]))
           for k, reg in enumerate(sorted(regiones))]

    # LPO: cuatrienio del año local; exclusión temporal, vecindario con la red concurrente.
    v = p["LPO"]["ventanas"]
    a0, a1, largo = int(v["anio_desde"]), int(v["anio_hasta"]), int(v["largo_anios"])
    cont = conteos[conteos["filas"] > 0].copy()
    if (cont["anio"] < a0).any() or (cont["anio"] > a1).any():
        raise SystemExit(f"{pol}: hay años del panel fuera de las ventanas {a0}–{a1}")
    cont["ventana"] = ventana_de(cont["anio"], a0, a1, largo)
    lpo = []
    for k, etq in enumerate(sorted(cont["ventana"].unique())):
        dentro = cont["ventana"] == etq
        filas_prueba = int(cont.loc[dentro, "filas"].sum())
        ini, fin = (int(x) for x in etq.split("–"))
        lpo.append({"k": k, "semilla": [semilla0, k], "grupo": etq,
                    "estaciones_prueba": sorted(cont.loc[dentro, "estacion"].unique().tolist()),
                    "excluidas": [], "exclusion_temporal": {"anio_desde": ini, "anio_hasta": fin},
                    "vecindario": "red concurrente, sin recálculo (se declara así, §1)",
                    "filas_prueba": filas_prueba, "filas_entrenamiento_disponibles": total - filas_prueba,
                    "filas_fuera_del_pliegue": 0,
                    "estaciones_entrenamiento": int(cont.loc[~dentro, "estacion"].nunique())})

    def_blq = f"bloque de {lado / 1000:g} km de la rejilla fija en {blq_cfg['crs']} con al menos una estación"
    if radio_blq is not None:
        def_blq += f"; se excluye además toda estación a <= {radio_blq:g} km de alguna estación del bloque"
    protocolos = {
        "LOSO-D": {"definicion": f"conglomerado de estaciones a <= {umbral:g} km o en la misma celda (componentes conexas)",
                   "recalcula_vecindario": True, "n_pliegues": len(loso), "pliegues": loso},
        "LBO-10": {"definicion": f"el conglomerado de LOSO-D; se excluye además toda estación a <= {radio:g} km de él",
                   "recalcula_vecindario": True, "n_pliegues": len(lbo), "pliegues": lbo},
        "BLQ-75": {"definicion": def_blq, "recalcula_vecindario": True, "n_pliegues": len(blq), "pliegues": blq},
        "LRO": {"definicion": "región SINCA (Ñuble como RVIII)",
                "recalcula_vecindario": True, "n_pliegues": len(lro), "pliegues": lro},
        "LPO": {"definicion": "cuatrienio del año local (UTC−4); el vecindario de prueba usa la red concurrente",
                "recalcula_vecindario": False, "n_pliegues": len(lpo), "pliegues": lpo},
    }

    registro_congl = []
    for k, (etq, c) in enumerate(zip(etiquetas, congl)):
        if len(c) < 2:
            continue
        idx = [indice[s] for s in c]
        diametro = round(float(D[np.ix_(idx, idx)].max()), DECIMALES_KM)
        registro_congl.append({"grupo": etq, "k": k, "estaciones": list(c),
                               "celdas": sorted({int(celdas[i]) for i in idx}),
                               "diametro_km": diametro, "encadenado": bool(diametro > umbral),
                               "aristas": aristas(list(c), indice, D, celdas, umbral),
                               "filas": sum(filas_est[s] for s in c)})

    bloque_de = dict(zip(nombres, est["bloque_blq75"]))
    ejemplos = []
    for ej in p["LOSO-D"].get("retira_juntos_ejemplos", []):
        presentes = [s for s in ej if s in en_panel]
        grupos = sorted({etq for etq, c in zip(etiquetas, congl) if set(c) & set(presentes)})
        ejemplos.append({"estaciones": ej, "presentes_en_panel": presentes,
                         "juntas": len(grupos) <= 1, "grupos": grupos})
    sin = [b for b in registro_bloques if b["distancia_minima_sin_amortiguador_km"] is not None]
    con = [b["distancia_minima_entrenamiento_km"] for b in registro_bloques
           if b["distancia_minima_entrenamiento_km"] is not None]
    diagnosticos = {
        "coordenadas_panel_vs_modelo_dif_max_grados": float(f"{dif:.3e}"),
        "celdas_panel_iguales_a_modelo": True,
        "pliegues_loso_v1_por_celda": int(len(set(celdas.tolist()))),
        "conglomerados_partidos_entre_bloques": [etq for etq, c in zip(etiquetas, congl)
                                                 if len({bloque_de[s] for s in c}) > 1],
        "conglomerados_encadenados": [{"grupo": c["grupo"], "diametro_km": c["diametro_km"],
                                       "arista_max_km": max(a["km"] for a in c["aristas"])}
                                      for c in registro_congl if c["encadenado"]],
        "lbo10_pliegues_iguales_a_loso_d": sum(1 for f in lbo if f["excluidas"] == f["estaciones_prueba"]),
        "blq75_amortiguador": {
            "radio_km": radio_blq,
            "bloques_con_exclusion_adicional": sum(1 for b in registro_bloques if b["excluidas_por_amortiguador"]),
            "bloques_con_entrenamiento_a_radio_o_menos_sin_amortiguador": [
                {"grupo": b["grupo"], "km": b["distancia_minima_sin_amortiguador_km"]} for b in sin
                if radio_blq is not None and b["distancia_minima_sin_amortiguador_km"] <= radio_blq],
            "distancia_minima_tras_amortiguador_km": min(con) if con else None},
        "lro_regiones_de_una_estacion": sorted(reg for reg, m in regiones.items() if len(m) == 1),
        "ejemplos_del_contrato": ejemplos,
        "nuble_como_rviii": sorted(
            s for s, cod, reg in zip(nombres, est["cod_comuna"], est["region_lro"])
            if pd.notna(cod) and int(cod) // 1000 == 16 and reg == "RVIII"),
    }
    return {"panel": panel_info, "estaciones": nombres, "protocolos": protocolos,
            "conglomerados_loso_d": registro_congl, "bloques_blq75": registro_bloques, "diagnosticos": diagnosticos}


def parametros_de(cfg: dict) -> tuple[dict, list]:
    """Parámetros de los pliegues tomados de la configuración, y los valores de la configuración que no fija el
    contrato (ratificados por una enmienda o todavía provisionales) con su estado."""
    p = cfg["protocolos"]
    d, b, blq, lpo = p["LOSO-D"], p["LBO-10"]["exclusion_adicional"], p["BLQ-75"], p["LPO"]["ventanas"]
    origen = [float(x) for x in valor_vigente(blq["origen_m"], "protocolos.BLQ-75.origen_m")]
    orden_k = valor_vigente(p["semilla"]["k"], "protocolos.semilla.k")
    distancias = p.get("distancias", {"formula": d["distancia"]["formula"],
                                      "radio_tierra_km": d["distancia"]["radio_tierra_km"]})
    if distancias["formula"] != "haversine" or float(distancias["radio_tierra_km"]) != RADIO_TIERRA_KM:
        raise ValueError(f"todas las distancias son haversine con R = {RADIO_TIERRA_KM} km (Enmienda 1, punto 13)")
    parametros = {
        "distancias": {"formula": distancias["formula"], "radio_tierra_km": float(distancias["radio_tierra_km"])},
        "LOSO-D": {"umbral_km": float(d["umbral_km"]), "comparacion": d["comparacion"],
                   "une_celdas_compartidas": bool(d["une_celdas_compartidas"]),
                   "distancia": d["distancia"]["formula"], "radio_tierra_km": float(d["distancia"]["radio_tierra_km"]),
                   "etiqueta": "códigos de las estaciones ordenados y unidos por «+»",
                   "encadenamiento": "se mantiene la regla de componentes conexas; los conglomerados con diámetro "
                                     "mayor que el umbral se listan en diagnosticos.conglomerados_encadenados"},
        "LBO-10": {"radio_km": float(b["radio_km"]), "comparacion": b["comparacion"],
                   "medida_desde": b["medida_desde"], "universo": b["universo"]},
        "BLQ-75": {"crs": blq["crs"], "lado_m": float(blq["lado_m"]), "origen_m": origen,
                   "indices": "ix = floor((este − origen_este) / lado); iy = floor((norte − origen_norte) / lado)",
                   "etiqueta": "E{ix:03d}N{iy:03d}", "asignacion": blq["asignacion"]},
        "LRO": {"grupo": "region_sinca", "equivalencias": dict(p["LRO"].get("equivalencias", {}))},
        "LPO": {"anio_desde": int(lpo["anio_desde"]), "anio_hasta": int(lpo["anio_hasta"]),
                "largo_anios": int(lpo["largo_anios"]), "anio": p["LPO"]["anio_local"]},
        "semilla": {"regla": p["semilla"]["regla"], "orden_k": orden_k},
    }
    radio_blq = radio_amortiguador_blq(cfg)
    if radio_blq is not None:
        ex = blq["exclusion_adicional"]
        parametros["BLQ-75"]["amortiguador"] = {"radio_km": radio_blq, "comparacion": ex.get("comparacion", "<="),
                                                "medida_desde": ex.get("medida_desde"), "universo": ex.get("universo"),
                                                "fuente": "Enmienda 1, punto 8"}
    valores = [{"campo": campo, "estado": estado_vigente(item), "valor": valor, "nota": item.get("nota")}
               for campo, item, valor in (("protocolos.BLQ-75.origen_m", blq["origen_m"], origen),
                                          ("protocolos.semilla.k", p["semilla"]["k"], orden_k))
               if isinstance(item, dict) and estado_vigente(item) != "contrato"]
    return parametros, valores


def registro_estaciones(universo: pd.DataFrame, filas_por_pol: dict) -> list[dict]:
    out = []
    for f in universo.itertuples(index=False):
        out.append({"estacion": f.estacion, "nombre": str(f.nombre), "red": f.red, "region_sinca": f.region_sinca,
                    "region_lro": f.region_lro, "cod_comuna": None if pd.isna(f.cod_comuna) else int(f.cod_comuna),
                    "lat": float(f.lat), "lon": float(f.lon), "celda": int(f.celda),
                    "utm19s_este_m": float(f.este_m), "utm19s_norte_m": float(f.norte_m),
                    "bloque_blq75": f.bloque_blq75,
                    "filas_panel": {pol: int(filas.get(f.estacion, 0)) for pol, filas in filas_por_pol.items()}})
    return out


def huella_pliegues(manifiesto: dict) -> str:
    """sha256 canónico de lo que define los pliegues (parámetros, estaciones y protocolos por contaminante);
    excluye la traza, las fechas y la bitácora, de modo que volver a calcular lo mismo da la misma huella."""
    return sha256_json({k: manifiesto.get(k) for k in CLAVES_HUELLA})


def construir_manifiesto(r: RutasV2, cfg: dict, contaminantes=CONTAMINANTES, hilos: int | None = None) -> dict:
    """Calcula el manifiesto completo (no escribe nada). ``hilos``: tope de hilos (por omisión, el de la
    configuración); los programas de línea de órdenes ya lo fijaron antes de importar numpy."""
    hilos_cfg = int(cfg["operacion"]["hilos_maximos"]) if hilos is None else min(int(hilos), int(cfg["operacion"]["hilos_maximos"]))
    fijar_hilos(hilos_cfg)
    parametros, valores_cfg = parametros_de(cfg)
    provisionales = [v for v in valores_cfg if v["estado"] == "pendiente"]
    universo = preparar_universo(r, cfg)
    insumos = {"catalogo_sinca": r.catalogo_sinca, "snifa": r.snifa,
               **{f"grilla_{Path(n).stem}": r.grilla_v1 / n for n in INSUMOS_GRILLA}}
    por_pol, filas_por_pol = {}, {}
    for pol in contaminantes:
        por_est, conteos, meta = leer_panel(r, pol)
        sha = sha256_archivo(r.panel(pol))
        declarado = meta.get("sha256")
        if declarado and declarado != sha:
            raise SystemExit(f"{pol}: el panel en disco (sha256 {sha[:16]}) no es el que publicó la v1 "
                             f"({declarado[:16]}); la v2 se ata al panel v1 publicado")
        insumos[f"panel_{pol}"] = r.panel(pol)
        if r.panel_meta(pol).exists():
            insumos[f"panel_{pol}_json"] = r.panel_meta(pol)
        panel_info = {**r.relativa(r.panel(pol)), "sha256": sha, "sha256_declarado_v1": declarado,
                      "filas": int(por_est["filas"].sum()), "estaciones": int(len(por_est)),
                      "redes_v1": meta.get("redes"), "codigo_v1": meta.get("codigo")}
        por_pol[pol] = construir_contaminante(pol, universo, por_est, conteos, cfg, panel_info)
        filas_por_pol[pol] = {s: int(n) for s, n in por_est["filas"].items()}
        log.info("%s: %s filas, %d estaciones; pliegues %s", pol, f"{panel_info['filas']:,}", panel_info["estaciones"],
                 ", ".join(f"{k} {v['n_pliegues']}" for k, v in por_pol[pol]["protocolos"].items()))
    semillas = {"regla": parametros["semilla"]["regla"], "semilla_base": int(parametros["semilla"]["regla"][0])}
    manifiesto = {
        "schema": SCHEMA,
        "descripcion": ("Pliegues externos de la v2 (DISENO_AMBIENTAL_V2.md §1, con la Enmienda 1), fijados antes de "
                        "ajustar ningún motor. Cada pliegue trae su grupo, las estaciones de prueba, el conjunto "
                        "excluido, k, la semilla [42, k] de la permutación común (§4), las filas disponibles y, en los "
                        "protocolos espaciales, la distancia mínima de prueba a entrenamiento."),
        "reglas": {
            "excluidas": ("estaciones del panel que el pliegue saca de las filas de entrenamiento, del vecindario de "
                          "entrenamiento y de prueba y de los residuos de la retransformación (regla única, §1)"),
            "radio_incluye_fuera_del_panel": ("LBO-10 y BLQ-75: estaciones con celda a <= 10 km que no están en el panel "
                                              "del contaminante; no aportan filas ni vecindario (como la v1)"),
            "amortiguador": ("BLQ-75 (Enmienda 1, punto 8): se excluyen además del entrenamiento y del vecindario las "
                             "estaciones a <= 10 km (haversine) de cualquier estación del bloque de prueba, como en LBO-10"),
            "distancia_minima_entrenamiento_km": ("menor distancia haversine de una estación de prueba a una de "
                                                  "entrenamiento (del panel y fuera del conjunto excluido); en BLQ-75 "
                                                  "también sin el amortiguador (distancia_minima_sin_amortiguador_km)"),
            "exclusion_temporal": "LPO: años locales cuyas filas salen del entrenamiento y forman la prueba",
            "filas_entrenamiento_disponibles": "filas del panel fuera del conjunto excluido (en LPO, fuera del cuatrienio), antes de topes",
            "filas_fuera_del_pliegue": ("filas excluidas que tampoco son de prueba (el entorno de LBO-10 y el "
                                        "amortiguador de BLQ-75): ni entrenan ni se predicen"),
            "semilla": "[42, k]: semilla de la permutación común del pliegue (§4); los topes son prefijos",
        },
        "parametros": parametros,
        "valores_de_la_configuracion": valores_cfg,
        "provisionales_usados": provisionales,
        "conteos": {pol: {prot: d["protocolos"][prot]["n_pliegues"] for prot in PROTOCOLOS} for pol, d in por_pol.items()},
        "estaciones": registro_estaciones(universo, filas_por_pol),
        "contaminantes": por_pol,
        "traza": traza(insumos, semillas, hilos_cfg, rutas=r),
    }
    manifiesto["huella_pliegues"] = huella_pliegues(manifiesto)
    return manifiesto


# ---------------------------------------------------------------------------
# Tablas pequeñas para el repositorio
# ---------------------------------------------------------------------------
def tablas(m: dict) -> dict[str, pd.DataFrame]:
    huella = m["huella_pliegues"][:16]
    resumen, pliegues, congl, bloques = [], [], [], []
    for pol, d in m["contaminantes"].items():
        for prot in PROTOCOLOS:
            pl = d["protocolos"][prot]["pliegues"]
            fp = np.array([f["filas_prueba"] for f in pl])
            fe = np.array([f["filas_entrenamiento_disponibles"] for f in pl])
            dmin = [f["distancia_minima_entrenamiento_km"] for f in pl if f.get("distancia_minima_entrenamiento_km") is not None]
            resumen.append({"contaminante": pol, "protocolo": prot, "pliegues": len(pl),
                            "estaciones_panel": d["panel"]["estaciones"], "filas_panel": d["panel"]["filas"],
                            "filas_prueba_min": int(fp.min()), "filas_prueba_mediana": float(np.median(fp)),
                            "filas_prueba_max": int(fp.max()), "filas_entrenamiento_min": int(fe.min()),
                            "filas_entrenamiento_mediana": float(np.median(fe)), "filas_entrenamiento_max": int(fe.max()),
                            "pliegues_con_exclusion_adicional": sum(1 for f in pl if len(f["excluidas"]) > len(f["estaciones_prueba"])),
                            "distancia_minima_entrenamiento_km_min": min(dmin) if dmin else None,
                            "distancia_minima_entrenamiento_km_mediana": round(float(np.median(dmin)), DECIMALES_KM) if dmin else None,
                            "huella_pliegues": huella})
            for f in pl:
                pliegues.append({"contaminante": pol, "protocolo": prot, "k": f["k"], "semilla": f"{f['semilla'][0]},{f['semilla'][1]}",
                                 "grupo": f["grupo"], "n_prueba": len(f["estaciones_prueba"]), "n_excluidas": len(f["excluidas"]),
                                 "estaciones_prueba": ";".join(f["estaciones_prueba"]), "excluidas": ";".join(f["excluidas"]),
                                 "filas_prueba": f["filas_prueba"], "filas_entrenamiento_disponibles": f["filas_entrenamiento_disponibles"],
                                 "filas_fuera_del_pliegue": f["filas_fuera_del_pliegue"],
                                 "distancia_minima_entrenamiento_km": f.get("distancia_minima_entrenamiento_km"),
                                 "distancia_minima_sin_amortiguador_km": f.get("distancia_minima_sin_amortiguador_km")})
        for c in d["conglomerados_loso_d"]:
            congl.append({"contaminante": pol, "grupo": c["grupo"], "k": c["k"], "n_estaciones": len(c["estaciones"]),
                          "estaciones": ";".join(c["estaciones"]), "celdas": ";".join(map(str, c["celdas"])),
                          "diametro_km": c["diametro_km"], "arista_max_km": max(a["km"] for a in c["aristas"]),
                          "encadenado": bool(c.get("encadenado", False)), "filas": c["filas"]})
        for b in d["bloques_blq75"]:
            bloques.append({"contaminante": pol, "grupo": b["grupo"], "k": b["k"], "ix": b["ix"], "iy": b["iy"],
                            "este_min_m": b["este_min_m"], "norte_min_m": b["norte_min_m"],
                            "este_max_m": b["este_max_m"], "norte_max_m": b["norte_max_m"],
                            "centro_lon": b["centro_lonlat"][0], "centro_lat": b["centro_lonlat"][1],
                            "n_estaciones": len(b["estaciones"]), "estaciones": ";".join(b["estaciones"]), "filas": b["filas"],
                            "excluidas_por_amortiguador": ";".join(b.get("excluidas_por_amortiguador", [])),
                            "radio_incluye_fuera_del_panel": ";".join(b.get("radio_incluye_fuera_del_panel", [])),
                            "distancia_minima_entrenamiento_km": b.get("distancia_minima_entrenamiento_km"),
                            "distancia_minima_sin_amortiguador_km": b.get("distancia_minima_sin_amortiguador_km")})
    return {"pliegues_v2_resumen.csv": pd.DataFrame(resumen), "pliegues_v2_pliegues.csv": pd.DataFrame(pliegues),
            "pliegues_v2_conglomerados_loso_d.csv": pd.DataFrame(congl), "pliegues_v2_bloques_blq75.csv": pd.DataFrame(bloques)}


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------
def refijar_manifiesto(previo: dict, nuevo: dict, r: RutasV2, motivo: str | None = None) -> dict:
    """Vuelve a fijar el manifiesto vigente ``previo`` con ``nuevo`` (calculado bajo el contrato, la configuración y el
    código actuales) **sin cambiar los pliegues**: exige la misma huella y que ``previo`` calce con la suya. El
    anterior queda como respaldo junto a él (``pliegues_v2_reemplazado_<sello>.json``, copia con los mismos bytes y
    fechas, comprobada por su sha256) y la bitácora sigue —sus eventos se refieren a los mismos pliegues— con un
    evento «fijado» que cita el motivo, el contrato, la configuración y el código anteriores y vigentes, y el
    respaldo. Conserva ``fijado_utc`` (los pliegues se fijaron entonces) y agrega ``refijado_utc``. Exige el candado
    «pliegues». Devuelve el manifiesto publicado."""
    if huella_pliegues(previo) != previo.get("huella_pliegues"):
        raise SystemExit("El manifiesto vigente no calza con su propia huella: se editó a mano; no se vuelve a fijar")
    if previo["huella_pliegues"] != nuevo["huella_pliegues"]:
        raise SystemExit(f"--refijar no cambia los pliegues, pero la huella recalculada ({nuevo['huella_pliegues'][:16]}) "
                         f"no es la vigente ({previo['huella_pliegues'][:16]}). Si los pliegues deben cambiar "
                         f"(enmienda), usa --reemplazar.")
    destino = ruta_de_respaldo(r.manifiesto_pliegues, "reemplazado")
    sha_previo = copiar_artefacto(r.manifiesto_pliegues, destino, r)
    ahora = ahora_utc()

    def de(traza_: dict, clave: str, campo: str = "sha256"):
        return ((traza_ or {}).get(clave) or {}).get(campo)

    tp, tn = previo.get("traza") or {}, nuevo["traza"]
    evento = {"utc": ahora, "evento": EVENTO_FIJADO, "huella_pliegues": nuevo["huella_pliegues"],
              "nota": ("vuelto a fijar bajo el contrato, la configuración y el código vigentes, con los mismos pliegues "
                       "(misma huella): sólo cambian la traza y los valores de la configuración que cita"),
              "motivo": motivo or "vuelto a fijar con --refijar",
              "refijado": {"pliegues_identicos": True, "huella_anterior": previo["huella_pliegues"],
                           "fijado_utc_anterior": previo.get("fijado_utc"),
                           "contrato": {"anterior": de(tp, "contrato"), "vigente": de(tn, "contrato")},
                           "configuracion": {"anterior": de(tp, "config"), "vigente": de(tn, "config")},
                           "codigo": {"anterior": de(tp, "codigo", "hash"), "vigente": de(tn, "codigo", "hash")},
                           "commit": {"anterior": de(tp, "git", "commit"), "vigente": de(tn, "git", "commit")},
                           "respaldo": {**r.relativa(destino), "sha256": sha_previo}}}
    m = {**nuevo, "fijado_utc": previo.get("fijado_utc") or ahora, "refijado_utc": ahora,
         "bitacora": [*previo.get("bitacora", []), evento]}
    if huella_pliegues(m) != previo["huella_pliegues"]:
        raise RuntimeError("al volver a fijar cambió la huella de los pliegues")
    publicar_json(m, r.manifiesto_pliegues, r)
    return m


def ejecutar(r: RutasV2, cfg: dict, reemplazar: bool = False, escribir: bool = True,
             escribir_tablas: bool = True, contaminantes=CONTAMINANTES, motivo: str | None = None,
             hilos: int | None = None, refijar: bool = False) -> tuple[dict, str]:
    """Calcula el manifiesto y lo fija en la raíz v2 (con candado y escritura atómica). Devuelve el
    manifiesto vigente y el estado: «fijado», «sin_cambios», «reemplazado», «refijado» o «sin_escribir».

    Al reemplazar, el manifiesto anterior queda intacto como respaldo (se renombra, no se copia: mismos bytes y
    mismo sha256) y la bitácora nueva empieza con el evento «reemplazo»: huella anterior, respaldo con su sha256,
    motivo y la bitácora anterior completa. Así los eventos de primer nivel (recortes, anotaciones) se refieren
    siempre a los pliegues vigentes. Con ``refijar``, vuelve a fijar el vigente bajo el contrato actual sin cambiar
    los pliegues (``refijar_manifiesto``)."""
    if "red_de_monitores" in cfg:
        raise SystemExit("Con la Enmienda 2 (red ampliada, R13 a R16) los pliegues, los pesos, la E2 y el bloque más "
                         "influyente los fija pliegues_red2_v2.py en pliegues_v2_red2.json, la única fuente; este "
                         "programa calcula los de la red original y no corre bajo el contrato con la red ampliada")
    if reemplazar and refijar:
        raise SystemExit("--reemplazar y --refijar no van juntos: --refijar no cambia los pliegues")
    m = construir_manifiesto(r, cfg, contaminantes, hilos=hilos)
    if not escribir:
        return m, "sin_escribir"
    if tuple(sorted(contaminantes)) != tuple(sorted(CONTAMINANTES)):
        raise SystemExit("El manifiesto se fija con los dos contaminantes; --contaminantes sólo sirve con --no-escribir")
    with candado_escritura("pliegues", rutas=r):
        previo = leer_json(r.manifiesto_pliegues)
        ahora = ahora_utc()
        evento = {"utc": ahora, "evento": EVENTO_FIJADO, "huella_pliegues": m["huella_pliegues"],
                  "nota": "pliegues fijados antes de ajustar ningún motor (§1)"}
        if previo is not None and huella_pliegues(previo) != previo.get("huella_pliegues"):
            raise SystemExit(f"{r.manifiesto_pliegues.name} no calza con su propia huella: se editó a mano. "
                             f"Revísalo antes de seguir; no se sobrescribe.")
        if refijar:
            if previo is None:
                raise SystemExit(f"No hay {r.manifiesto_pliegues.name} que volver a fijar; fíjalo primero")
            final, estado = refijar_manifiesto(previo, m, r, motivo), "refijado"
        elif previo is not None and previo["huella_pliegues"] == m["huella_pliegues"]:
            final, estado = previo, "sin_cambios"
        elif previo is not None and not reemplazar:
            raise SystemExit(f"{r.manifiesto_pliegues.name} ya existe con otra huella "
                             f"({previo['huella_pliegues'][:16]} frente a {m['huella_pliegues'][:16]}). Los pliegues se "
                             f"fijan antes de estimar y no se reemplazan en silencio; si corresponde (enmienda), usa --reemplazar.")
        else:
            m["fijado_utc"] = ahora
            m["bitacora"] = []
            if previo is not None:
                sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                sha_previo = sha256_archivo(r.manifiesto_pliegues)
                respaldo = renombrar(r.manifiesto_pliegues, r.raiz_v2 / f"pliegues_v2_reemplazado_{sello}.json", r)
                if sha256_archivo(respaldo) != sha_previo:
                    raise RuntimeError("el respaldo del manifiesto no conserva sus bytes")
                m["bitacora"] = [{"utc": ahora, "evento": "reemplazo", "huella_anterior": previo["huella_pliegues"],
                                  "schema_anterior": previo.get("schema"), "fijado_utc_anterior": previo.get("fijado_utc"),
                                  "respaldo": {**r.relativa(respaldo), "sha256": sha_previo},
                                  "motivo": motivo or "reemplazo pedido con --reemplazar",
                                  "bitacora_anterior": list(previo.get("bitacora", []))}]
            m["bitacora"].append(evento)
            publicar_json(m, r.manifiesto_pliegues, r)
            final, estado = m, ("reemplazado" if previo is not None else "fijado")
        if escribir_tablas:
            publicar_tablas(final, r, int(cfg["operacion"]["hilos_maximos"]) if hilos is None else int(hilos))
    return final, estado


def publicar_tablas(m: dict, r: RutasV2, hilos_cfg: int) -> bool:
    """Tablas pequeñas en ``output_files/modelo_1km_v2`` más un JSON lateral con su traza (los CSV no la
    pueden llevar dentro). Sólo reescribe lo que cambió, para no ensuciar git con fechas. Exige el candado."""
    cambios = False
    shas = {}
    for nombre, df in tablas(m).items():
        datos = df.to_csv(index=False, lineterminator="\n").encode("utf-8")
        destino = r.salidas_v2 / nombre
        shas[nombre] = hashlib.sha256(datos).hexdigest()
        if destino.exists() and destino.read_bytes() == datos:
            continue
        publicar_bytes(datos, destino, r)
        cambios = True
    lateral = r.salidas_v2 / NOMBRE_LATERAL
    previo = leer_json(lateral)
    if cambios or previo is None or previo.get("huella_pliegues") != m["huella_pliegues"] or previo.get("tablas") != shas:
        semillas = {"regla": m["parametros"]["semilla"]["regla"]}
        publicar_json({"schema": SCHEMA_TABLAS,
                       "descripcion": "Tablas resumen del manifiesto de pliegues v2; la fuente es pliegues_v2.json de la raíz v2.",
                       "huella_pliegues": m["huella_pliegues"], "fijado_utc": m.get("fijado_utc"),
                       "tablas": shas,
                       "traza": traza({"manifiesto_pliegues": r.manifiesto_pliegues}, semillas, hilos_cfg, rutas=r)},
                      lateral, r)
        cambios = True
    return cambios


def anotar_bitacora(evento: dict, r: RutasV2 | None = None) -> dict:
    """Agrega un evento a la bitácora del manifiesto (p. ej., un recorte del presupuesto, §10) sin tocar los
    pliegues ni su huella."""
    r = r or rutas_v2()
    with candado_escritura("pliegues", rutas=r):
        m = leer_json(r.manifiesto_pliegues)
        if m is None:
            raise SystemExit(f"No hay manifiesto en {r.relativa(r.manifiesto_pliegues)}; fíjalo primero")
        if huella_pliegues(m) != m.get("huella_pliegues"):
            raise SystemExit("El manifiesto no calza con su propia huella; no se anota nada")
        m.setdefault("bitacora", []).append({"utc": ahora_utc(), **evento})
        publicar_json(m, r.manifiesto_pliegues, r)
    return m


def resumen_texto(m: dict, estado: str) -> str:
    lineas = [f"Manifiesto de pliegues v2: {estado}; huella {m['huella_pliegues'][:16]}"]
    for pol, d in m["contaminantes"].items():
        cuentas = ", ".join(f"{p} {d['protocolos'][p]['n_pliegues']}" for p in PROTOCOLOS)
        lineas.append(f"  {pol}: {d['panel']['estaciones']} estaciones, {d['panel']['filas']:,} filas; {cuentas}")
        for c in d["conglomerados_loso_d"]:
            lineas.append(f"    LOSO-D {c['grupo']} (k={c['k']}; diámetro {c['diametro_km']:.3f} km"
                          f"{'; encadenado' if c.get('encadenado') else ''})")
        am = d.get("diagnosticos", {}).get("blq75_amortiguador")
        if am and am.get("radio_km") is not None:
            cerca = am["bloques_con_entrenamiento_a_radio_o_menos_sin_amortiguador"]
            lineas.append(f"    BLQ-75: {len(cerca)} de {d['protocolos']['BLQ-75']['n_pliegues']} bloques tenían una "
                          f"estación de entrenamiento a <= {am['radio_km']:g} km; con el amortiguador, "
                          f"{am['bloques_con_exclusion_adicional']} excluyen más estaciones y la distancia mínima de prueba "
                          f"a entrenamiento es {am['distancia_minima_tras_amortiguador_km']} km")
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fija el manifiesto de pliegues v2 (DISENO_AMBIENTAL_V2.md §1).")
    ap.add_argument("--contaminantes", nargs="+", default=list(CONTAMINANTES), choices=CONTAMINANTES)
    ap.add_argument("--reemplazar", action="store_true",
                    help="reemplaza un manifiesto con otra huella (enmienda); el anterior queda como respaldo con fecha")
    ap.add_argument("--refijar", action="store_true",
                    help="vuelve a fijar el manifiesto vigente bajo el contrato actual sin cambiar los pliegues (misma "
                         "huella); el anterior queda como respaldo y la bitácora sigue con un evento «fijado»")
    ap.add_argument("--motivo", default=None, help="motivo del reemplazo o de volver a fijar, para la bitácora")
    ap.add_argument("--no-escribir", action="store_true", help="calcula y resume sin escribir nada")
    ap.add_argument("--sin-tablas", action="store_true", help="no escribe las tablas de output_files/modelo_1km_v2")
    ap.add_argument("--anotar", metavar="EVENTO", help="agrega EVENTO a la bitácora del manifiesto y termina")
    ap.add_argument("--nota", default="", help="texto que acompaña a --anotar")
    ap.add_argument("--hilos", type=int, default=None,
                    help="tope de hilos (por omisión, operacion.hilos_maximos); se fija antes de importar numpy")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    r = rutas_v2()
    if args.anotar:
        anotar_bitacora({"evento": args.anotar, "nota": args.nota}, r)
        log.info("Bitácora: «%s» anotado en %s", args.anotar, r.manifiesto_pliegues.name)
        return 0
    cfg = cargar_config(r)
    m, estado = ejecutar(r, cfg, reemplazar=args.reemplazar, escribir=not args.no_escribir,
                         escribir_tablas=not args.sin_tablas, contaminantes=tuple(args.contaminantes),
                         motivo=args.motivo, hilos=args.hilos, refijar=args.refijar)
    print(resumen_texto(m, estado))
    return 0


if __name__ == "__main__":
    sys.exit(main())
