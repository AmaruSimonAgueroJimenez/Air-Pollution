"""Red adicional SNIFA: monitores de calidad del aire que no pertenecen a SINCA.

El derivado de origen (``snifa_adicional/processed/observaciones_horarias.parquet``) se publica
deliberadamente **sin** reloj UTC: ``clock_status`` es ``unverified`` y ``ready_for_utc_join`` es falso,
porque las fuentes mezclan etiquetas horarias y no declaran si la hora es inicio o fin del intervalo.
Este módulo resuelve las dos semánticas que faltan, con la evidencia levantada el 22 de septiembre de
2026, y deja las observaciones en la misma forma que ``series_sinca``.

**Reloj.** La convención se decide por documento: si el ``hour_index`` de un documento llega a 24, ese
documento etiqueta 1–24 y la hora local de inicio es ``hour_index - 1``; si parte en 0, etiqueta 0–23 y la
hora local es ``hour_index``. Con esa corrección, el ciclo diurno de O₃ observado se alinea con el de
GEOS-CF en la misma celda con ``ts_utc = hora_local + 4`` en las tres estaciones que miden O₃ (r entre
0,986 y 0,990) y el máximo de ozono cae a las 15:00 locales. En noviembre–febrero el ajuste es aún más
nítido (r 0,976–0,997) y sigue dando +4, lo que descarta el horario de verano oficial: el reloj es
**UTC−4 fijo**, la misma convención que el derivado SINCA de este proyecto.

**Unidad.** El preparador normaliza la escritura de las unidades pero no convierte entre ellas, y ninguna
hora aparece con dos unidades, así que no hay factor empírico directo. Contrastando cada período contra
el NO₂ de CAMS en la misma celda (escala común), la razón observado/CAMS no cambia al pasar de µg/m³N a
ppb en Charrúa (0,87 → 0,99) ni en Progreso (0,69 → 0,67): sus valores rotulados µg/m³N ya vienen en
escala de ppb. En El Peñón sí salta (3,60 → 1,51, un factor de 2,4) y la conversión teórica a 0 °C y
1 atm lo explica (3,60 × 0,4872 = 1,75). Quinel y SAPU **no se incluyen**: sólo reportan µg/m³N, no
tienen período en ppb con qué contrastarse y su escala queda indeterminada por un factor de dos.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from _comun_modelo import DATA, RANGO_VALIDO, leer_estaciones

log = logging.getLogger("modelo_1km")

RED = "snifa"
OFFSET_UTC_H_SNIFA = 4                      # UTC−4 fijo, verificado con el ciclo de O₃
PPB_POR_UG_M3N_NO2 = 22.414 / 46.0055       # 0 °C y 1 atm: 0,4872 ppb por µg/m³N

# Estación de origen -> identificador en el panel, nombre y factor por unidad. El factor de ``ug/m3N``
# sale del contraste contra CAMS descrito arriba; 1,0 significa que los números ya estaban en ppb.
ESTACIONES_ADICIONALES = {
    "charrua":  {"estacion": "SNIFA-CHARRUA",  "nombre": "Charrúa (SNIFA)",   "factor_ug": 1.0},
    "progreso": {"estacion": "SNIFA-PROGRESO", "nombre": "Progreso (SNIFA)",  "factor_ug": 1.0},
    "el_penon": {"estacion": "SNIFA-ELPENON",  "nombre": "El Peñón (SNIFA)",  "factor_ug": PPB_POR_UG_M3N_NO2},
}
# Excluidas a propósito: sólo miden en µg/m³N y su escala no se pudo verificar (ver docstring).
ESTACIONES_PENDIENTES = ("quinel", "sapu")
CONTAMINANTES_ADICIONALES = ("no2",)        # la red no aporta PM₂.₅
UNIDADES_ACEPTADAS = ("ppb", "ppbv", "ug/m3N")

RUTA = DATA / "snifa_adicional" / "processed" / "observaciones_horarias.parquet"


def disponible() -> bool:
    return RUTA.exists()


def _crudo() -> pd.DataFrame:
    o = pd.read_parquet(RUTA, columns=["station_id", "pollutant", "numeric_usable", "date_local",
                                       "hour_index", "value", "unit", "document_id", "latitude", "longitude"])
    return o[o["station_id"].isin(ESTACIONES_ADICIONALES) & o["numeric_usable"].astype(bool)]


def hora_local(o: pd.DataFrame) -> np.ndarray:
    """Hora local de inicio del intervalo, con la convención resuelta documento a documento."""
    rango = o.groupby("document_id")["hour_index"].max()
    desplaza = (rango == 24).astype("int8")                 # etiquetas 1–24: la hora es el fin del intervalo
    return o["hour_index"].to_numpy() - desplaza.reindex(o["document_id"]).to_numpy()


def estaciones_adicionales() -> pd.DataFrame:
    """Metadatos en el mismo esquema que ``leer_estaciones`` (estacion, nombre, region_sinca, lat, lon,
    cod_comuna). La comuna y la región salen de la grilla, no de un supuesto."""
    from _comun_modelo import GRILLA_DIR
    o = _crudo().groupby("station_id").agg(lat=("latitude", "first"), lon=("longitude", "first")).reset_index()
    celdas = pd.read_parquet(GRILLA_DIR / "celdas.parquet", columns=["celda", "lat", "lon", "cod_comuna", "codregion"])
    from _features import haversine_km
    filas = []
    sin = leer_estaciones()
    region_de = (sin.assign(r=(sin["cod_comuna"].astype("float64") // 1000))
                 .dropna(subset=["r"]).groupby("r")["region_sinca"].first().to_dict())
    for _, r in o.iterrows():
        d = haversine_km(r.lat, r.lon, celdas["lat"].to_numpy(), celdas["lon"].to_numpy())
        c = celdas.iloc[int(np.argmin(d))]
        cfg = ESTACIONES_ADICIONALES[r.station_id]
        filas.append({"estacion": cfg["estacion"], "nombre": cfg["nombre"],
                      "region_sinca": region_de.get(float(c["cod_comuna"]) // 1000, "sin_region"),
                      "lat": float(r.lat), "lon": float(r.lon), "cod_comuna": pd.NA if pd.isna(c["cod_comuna"])
                      else int(c["cod_comuna"]), "red": RED})
    est = pd.DataFrame(filas)
    est["cod_comuna"] = est["cod_comuna"].astype("Int64")
    return est


def series_adicionales(pol: str) -> pd.DataFrame:
    """Observaciones horarias de ``pol`` en la misma forma que ``series_sinca``: estacion, ts_utc, obs, n."""
    vacio = pd.DataFrame(columns=["estacion", "ts_utc", "obs", "n", "version"])
    if pol not in CONTAMINANTES_ADICIONALES or not disponible():
        return vacio
    o = _crudo()
    o = o[o["pollutant"] == pol].copy()
    if o.empty:
        return vacio
    fuera = o[~o["unit"].isin(UNIDADES_ACEPTADAS)]
    if len(fuera):
        log.warning("red adicional %s: %d filas descartadas por unidad no contemplada (%s)", pol, len(fuera),
                    sorted(fuera["unit"].unique()))
    o = o[o["unit"].isin(UNIDADES_ACEPTADAS)]
    factor = o["station_id"].map(lambda s: ESTACIONES_ADICIONALES[s]["factor_ug"]).to_numpy()
    o["obs"] = np.where(o["unit"].to_numpy() == "ug/m3N", o["value"].to_numpy() * factor, o["value"].to_numpy())
    lo, hi = RANGO_VALIDO[pol]
    o = o[o["obs"].between(lo, hi)]
    o["ts_utc"] = (pd.to_datetime(o["date_local"])
                   + pd.to_timedelta(hora_local(o) + OFFSET_UTC_H_SNIFA, unit="h"))
    o["estacion"] = o["station_id"].map(lambda s: ESTACIONES_ADICIONALES[s]["estacion"])
    out = o.groupby(["estacion", "ts_utc"], as_index=False).agg(obs=("obs", "mean"), n=("obs", "size"))
    out["version"] = RED
    log.info("red adicional %s: %s filas horarias, %d estaciones, %s a %s", pol, f"{len(out):,}",
             out["estacion"].nunique(), out["ts_utc"].min().date(), out["ts_utc"].max().date())
    return out
