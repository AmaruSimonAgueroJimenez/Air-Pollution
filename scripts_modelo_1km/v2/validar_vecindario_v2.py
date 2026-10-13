#!/usr/bin/env python3
"""Validación del vecindario v2 (``vecindario_v2.py``): reproducción de la v1, exactitud del descuento y tiempos.

Las tres pruebas de la pieza «vecindario_v2»:

**(a) Sin exclusiones adicionales** (sólo la propia estación), el vecindario v2 reproduce las columnas
``obs_vec``, ``peso_vec`` y ``dist_est_km`` del panel v1 en todas las filas. Se mide con dos fuentes de valores:

* a1, los valores del panel (``obs`` en float32), que son la fuente por omisión de la v2. ``peso_vec`` y
  ``dist_est_km`` no dependen de los valores y deben salir bit a bit. ``obs_vec`` puede diferir en 1 ULP de
  float32: si ``V₃₂ = V₆₄·(1 + δ)`` con ``|δ| ≤ 2⁻²⁴``, entonces ``|obs_vec(V₃₂) − obs_vec(V₆₄)| ≤ 2⁻²⁴·obs_vec``,
  porque ``V ≥ 0``. Eso es menos de 1 ULP antes de redondear, y como mucho 1 ULP después. La cota se verifica
  fila a fila contra a2;
* a2, las observaciones float64 reconstruidas desde las fuentes de la v1, en sólo lectura: el derivado SINCA
  (``_comun_modelo.py:593-669``) y la red SNIFA (``_red_adicional.py:59-121``), con las rachas
  (``produccion.py:78-110``) y el período del panel (``qmd:2004-2010``). Antes de usarlas se comprueba que
  dan exactamente las filas del panel y su mismo float32. Con ellas la reproducción tiene que ser bit a bit;
  cada diferencia que quede se lista con su distancia al borde de redondeo de float32.

**(b) Con un conjunto excluido**, el descuento coincide con el cálculo directo ingenuo, que es la réplica
literal de ``obs_vecinas_para`` y ``ajuste_por_red`` de la v1 sin el atajo (``vecindario_v2.recalculo_directo_v1``).
Se compara en una muestra con semilla de filas de entrenamiento, de prueba, «difíciles» (lo excluido pesa
≥ 99,9 %, donde actúa la guarda de cancelación) y cercanas al umbral de 1e-6, en pliegues elegidos de cada
protocolo y en conjuntos al azar. Además, en **todos** los pliegues y todas las filas, el descuento se compara
con la suma directa matricial (``metodo="directo"``).

**(c) Tiempo de un recálculo completo por pliegue**: todas las filas, entrenamiento y prueba, con las huellas
sha256 de las tres columnas, en los cinco protocolos.

Escribe, con candado y escritura atómica:

* ``output_files/modelo_1km_v2/vecindario_v2_validacion.json``: resultados, explicaciones y traza;
* ``output_files/modelo_1km_v2/vecindario_v2_tiempos.csv``: un renglón por pliegue (tiempo, filas, guardas y
  comparación con la suma directa);
* ``<raíz v2>/vecindario/registro_recalculos_<pol>.json``: el registro de cada recálculo (huellas de las
  tres columnas por pliegue), para que los motores comprueben que reciben exactamente lo mismo.

Uso::

    python -B scripts_modelo_1km/v2/validar_vecindario_v2.py --hilos 8
    python -B scripts_modelo_1km/v2/validar_vecindario_v2.py --contaminantes no2 --no-escribir
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _traza_v2 import fijar_hilos  # noqa: E402  (antes de numpy: fija el tope de hilos de BLAS)

if __name__ == "__main__":
    _pre = argparse.ArgumentParser(add_help=False)
    _pre.add_argument("--hilos", type=int, default=None)
    _n = _pre.parse_known_args()[0].hilos
    if _n:
        fijar_hilos(min(int(_n), 12))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import pliegues_v2 as pv  # noqa: E402
from _rutas_v2 import (  # noqa: E402
    RutasV2, ahora_utc, candado_escritura, cargar_config, leer_json, publicar_csv, publicar_json, rutas_v2,
)
from _traza_v2 import sha256_archivo, traza  # noqa: E402
from vecindario_v2 import VARIABLES, Recalculo, Vecindario, recalculo_directo_v1  # noqa: E402

log = logging.getLogger("modelo_1km_v2.validar_vecindario")

SCHEMA = "airpollution.modelo-1km-v2.vecindario-validacion.v1"
CONTAMINANTES = ("pm25", "no2")
PROTOCOLOS = ("LOSO-D", "LBO-10", "BLQ-75", "LRO", "LPO")
TOLERANCIA_REL = 1e-9
SEMILLA = 42

# --- Constantes de la v1 para reconstruir sus observaciones float64 (sólo lectura) -------------------------
RANGO_VALIDO = {"pm25": (0.0, 1500.0), "no2": (0.0, 1000.0)}       # _comun_modelo.py:78
OFFSET_UTC_H = 4                                                    # _comun_modelo.py:81
DESPLAZAMIENTO_SINCA_H = OFFSET_UTC_H - 1                           # etiqueta = fin (_comun_modelo.py:82, 105)
OFFSET_UTC_H_SNIFA = 4                                              # _red_adicional.py:37
PPB_POR_UG_M3N_NO2 = 22.414 / 46.0055                               # _red_adicional.py:38
ESTACIONES_ADICIONALES = {                                          # _red_adicional.py:42-46
    "charrua": ("SNIFA-CHARRUA", 1.0),
    "progreso": ("SNIFA-PROGRESO", 1.0),
    "el_penon": ("SNIFA-ELPENON", PPB_POR_UG_M3N_NO2),
}
CONTAMINANTES_ADICIONALES = ("no2",)                                # _red_adicional.py:49
UNIDADES_ACEPTADAS = ("ppb", "ppbv", "ug/m3N")                      # _red_adicional.py:50
QC_RACHA = 24                                                       # produccion.py:43
DESDE, HASTA = "2000-01-01", "2026-09-13"                           # qmd:297-298


# ---------------------------------------------------------------------------
# Observaciones float64 de la v1 (réplica en sólo lectura)
# ---------------------------------------------------------------------------
def raiz_derivado_sinca(r: RutasV2) -> Path:
    """``SINCA_DERIVADO`` de ``_comun_modelo.py:66-67``: ``AIR_POLLUTION_DERIVED_ROOT`` o ``<datos>/../derived``."""
    base = os.environ.get("AIR_POLLUTION_DERIVED_ROOT")
    derivado = Path(base).expanduser().resolve() if base else (r.datos.parent / "derived").resolve()
    return derivado / "modelado" / "SINCA" / "v1"


def _inv(texto: str) -> tuple:
    """Réplica de ``_comun_modelo.py:641-643``."""
    return tuple(-ord(ch) for ch in texto) + (1,)


def version_sinca(carpeta: Path) -> Path | None:
    """Réplica de ``_comun_modelo.py:602-638``: la versión de ventana más amplia (since ascendente, luego until,
    creación y filas descendentes, todo del ``manifest.json``)."""
    import pyarrow.parquet as pq

    candidatas = []
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
                filas = int(pq.read_metadata(obs).num_rows)
            except Exception:  # noqa: BLE001
                filas = 0
        candidatas.append((since, until, creado, filas, obs))
    if not candidatas:
        return None
    candidatas.sort(key=lambda c: (c[0], _inv(c[1]), _inv(c[2]), -c[3]))
    return candidatas[0][4]


def series_sinca_v1(pol: str, r: RutasV2) -> tuple[pd.DataFrame, list[Path]]:
    """Réplica de ``series_sinca`` (``_comun_modelo.py:646-669``) y de ``sinca_local_a_bin_utc``
    (``_comun_modelo.py:97-106``, UTC−4 fijo con etiqueta de fin: +3 h). Devuelve también los archivos leídos."""
    raiz = raiz_derivado_sinca(r)
    if not raiz.exists():
        raise SystemExit(f"No está el derivado SINCA v1 ({raiz.name}); la reconstrucción float64 no es posible")
    lo, hi = RANGO_VALIDO[pol]
    filas, leidos = [], []
    for carpeta in sorted(raiz.glob(f"estacion=*/contaminante={pol}")):
        est = carpeta.parent.name.split("=", 1)[1]
        p = version_sinca(carpeta)
        if p is None:
            continue
        leidos.append(p)
        df = pd.read_parquet(p, columns=["ts_local", "obs", "qc_observacion", "seleccionada"])
        df = df[df["seleccionada"].astype(bool) & df["obs"].notna()]
        df = df[df["obs"].between(lo, hi)]
        df["estacion"] = est
        df["version"] = p.parent.name.split("=", 1)[1]
        filas.append(df[["estacion", "ts_local", "obs", "qc_observacion", "version"]])
    out = pd.concat(filas, ignore_index=True)
    out["ts_utc"] = pd.to_datetime(out["ts_local"]) + pd.Timedelta(hours=DESPLAZAMIENTO_SINCA_H)
    out = out.groupby(["estacion", "ts_utc"], as_index=False).agg(
        obs=("obs", "mean"), n=("obs", "size"), version=("version", "first"))
    return out, leidos


def series_snifa_v1(pol: str, r: RutasV2) -> pd.DataFrame:
    """Réplica de ``series_adicionales`` (``_red_adicional.py:96-121``), con ``_crudo`` (59-62) y ``hora_local``
    (65-69): la convención horaria se decide por documento, sobre las filas ya filtradas, como en la v1."""
    vacio = pd.DataFrame(columns=["estacion", "ts_utc", "obs", "n", "version"])
    if pol not in CONTAMINANTES_ADICIONALES:
        return vacio
    o = pd.read_parquet(r.snifa, columns=["station_id", "pollutant", "numeric_usable", "date_local", "hour_index",
                                          "value", "unit", "document_id", "latitude", "longitude"])
    o = o[o["station_id"].isin(ESTACIONES_ADICIONALES) & o["numeric_usable"].astype(bool)]
    o = o[o["pollutant"] == pol].copy()
    if o.empty:
        return vacio
    o = o[o["unit"].isin(UNIDADES_ACEPTADAS)]
    factor = o["station_id"].map(lambda s: ESTACIONES_ADICIONALES[s][1]).to_numpy()
    o["obs"] = np.where(o["unit"].to_numpy() == "ug/m3N", o["value"].to_numpy() * factor, o["value"].to_numpy())
    lo, hi = RANGO_VALIDO[pol]
    o = o[o["obs"].between(lo, hi)]
    rango = o.groupby("document_id")["hour_index"].max()
    desplaza = (rango == 24).astype("int8")
    hora = o["hour_index"].to_numpy() - desplaza.reindex(o["document_id"]).to_numpy()
    o["ts_utc"] = pd.to_datetime(o["date_local"]) + pd.to_timedelta(hora + OFFSET_UTC_H_SNIFA, unit="h")
    o["estacion"] = o["station_id"].map(lambda s: ESTACIONES_ADICIONALES[s][0])
    out = o.groupby(["estacion", "ts_utc"], as_index=False).agg(obs=("obs", "mean"), n=("obs", "size"))
    out["version"] = "snifa"
    return out


def marcar_rachas_v1(obs: pd.DataFrame, minimo: int) -> pd.DataFrame:
    """Réplica de ``marcar_rachas`` (``produccion.py:78-88``): corridas de ``minimo`` o más valores idénticos
    consecutivos de una estación, sin que los huecos corten la corrida."""
    o = obs.sort_values(["estacion", "ts_utc"]).reset_index(drop=True)
    if minimo <= 0 or o.empty:
        o["racha"] = False
        return o
    cambio = (o["estacion"] != o["estacion"].shift()) | (o["obs"] != o["obs"].shift())
    corrida = cambio.cumsum()
    o["racha"] = corrida.groupby(corrida).transform("size").to_numpy() >= minimo
    return o


def observaciones_v1_float64(pol: str, r: RutasV2) -> tuple[pd.DataFrame, dict]:
    """Las observaciones con que la v1 armó su matriz de vecindario (``qmd:2004-2020``), en float64:
    ``observaciones`` (``produccion.py:104-110``: redes activas, estaciones usables y rachas sobre el registro
    completo) recortadas como ``observaciones_panel`` (``qmd:2004-2010``)."""
    s, leidos = series_sinca_v1(pol, r)
    a = series_snifa_v1(pol, r)
    o = pd.concat([s, a], ignore_index=True) if len(a) else s                    # produccion.py:59-67
    sinca = pv.leer_estaciones_sinca(r)
    usables = set(sinca["estacion"]) | set(pv.leer_estaciones_snifa(r, sinca)["estacion"])  # produccion.py:50-56
    o = marcar_rachas_v1(o[o["estacion"].isin(usables)], QC_RACHA)              # produccion.py:109
    info = {"filas_validas": int(len(o)), "filas_en_racha": int(o["racha"].sum()),
            "estaciones_con_racha": int(o.loc[o["racha"], "estacion"].nunique())}
    local = o["ts_utc"] - pd.Timedelta(hours=OFFSET_UTC_H)
    t0, t1 = pd.Timestamp(DESDE), pd.Timestamp(HASTA) + pd.Timedelta(days=1)
    con_celda = set(pv.estaciones_con_celda(r)["estacion"])
    o = o[~o["racha"] & o["estacion"].isin(con_celda) & (local >= t0) & (local < t1)]
    o = o[["estacion", "ts_utc", "obs"]].reset_index(drop=True)
    o["ts_utc"] = o["ts_utc"].astype("datetime64[ns]")
    raiz = raiz_derivado_sinca(r)
    huellas = sorted((p.relative_to(raiz).as_posix(), sha256_archivo(p)) for p in leidos)
    info["derivado_sinca"] = {"raiz": "<datos>/../derived/modelado/SINCA/v1", "archivos": len(huellas),
                              "sha256_conjunto": hashlib.sha256(json.dumps(huellas).encode("utf-8")).hexdigest()}
    return o, info


def alinear_con_panel(vec: Vecindario, o: pd.DataFrame, obs32: np.ndarray) -> tuple[np.ndarray, dict]:
    """Valores float64 de ``o`` en el orden de las filas del vecindario, tras comprobar que ``o`` tiene
    exactamente las mismas (estación, ts_utc) que el panel y el mismo float32."""
    S = len(vec.estaciones)
    js = pd.Index(vec.estaciones).get_indexer(o["estacion"].astype(str))
    it = vec.tiempos.get_indexer(pd.DatetimeIndex(o["ts_utc"]))
    ajenas = int(((js < 0) | (it < 0)).sum())
    flat = it.astype(np.int64) * S + js
    mismas = ajenas == 0 and len(o) == vec.n and np.array_equal(np.sort(flat), np.sort(vec.flat))
    if not mismas:
        raise SystemExit(f"{vec.pol}: las observaciones v1 reconstruidas no son las filas del panel "
                         f"({len(o):,} frente a {vec.n:,}; {ajenas} ajenas)")
    V = np.full(len(vec.tiempos) * S, np.nan)
    V[flat] = o["obs"].to_numpy(dtype="float64")
    obs64 = V[vec.flat]
    igual32 = obs64.astype("float32") == obs32
    if not igual32.all():
        raise SystemExit(f"{vec.pol}: {int((~igual32).sum()):,} filas con float32(obs v1) distinto del panel")
    return obs64, {"filas": int(len(o)), "mismas_filas_que_el_panel": True, "float32_igual_al_panel": True,
                   "filas_no_representables_en_float32": int((obs64 != obs32.astype("float64")).sum())}


# ---------------------------------------------------------------------------
# Comparaciones
# ---------------------------------------------------------------------------
def _ulps(a32: np.ndarray, b32: np.ndarray) -> np.ndarray:
    return np.abs(a32.view(np.int32).astype(np.int64) - b32.view(np.int32).astype(np.int64))


def comparar_float32(a: np.ndarray, b32: np.ndarray) -> dict:
    """``a`` (float32 o float64, que se redondea) frente a una columna float32 del panel."""
    a32 = np.asarray(a).astype("float32")
    na, nb = np.isnan(a32), np.isnan(b32)
    ok = ~(na | nb)
    u = _ulps(a32[ok], b32[ok])
    rel = np.abs(a32[ok].astype("float64") - b32[ok]) / np.maximum(np.abs(b32[ok].astype("float64")), 1e-300)
    return {"filas": int(len(b32)), "nan_iguales": bool(np.array_equal(na, nb)), "nan": int(nb.sum()),
            "bit_a_bit": int((u == 0).sum()), "a_1_ulp": int((u == 1).sum()), "a_mas_de_1_ulp": int((u > 1).sum()),
            "dif_rel_max": float(rel.max(initial=0.0)), "dif_abs_max": float(np.abs(a32[ok] - b32[ok]).max(initial=0.0))}


def explicar_diferencias(x64: np.ndarray, b32: np.ndarray, vec: Vecindario, nombre: str, limite: int = 200) -> list[dict]:
    """Para cada fila cuyo float32 difiere del panel: valor float64, los dos float32 vecinos y la distancia
    relativa del valor al borde de redondeo entre ellos. Una distancia del orden de 1e-15 significa que la
    diferencia viene del orden de suma en float64 y no del cálculo."""
    a32 = x64.astype("float32")
    ok = ~(np.isnan(a32) | np.isnan(b32))
    filas = np.flatnonzero(ok)[a32[ok] != b32[ok]]
    out = []
    for i in filas[:limite]:
        p, q = float(b32[i]), float(a32[i])
        borde = (p + q) / 2.0
        out.append({"variable": nombre, "fila": int(i), "estacion": str(vec.estaciones[vec.js[i]]),
                    "ts_utc": str(vec.tiempos[vec.it[i]]), "v2_float64": float(x64[i]), "v2_float32": q, "panel": p,
                    "distancia_rel_al_borde": abs(float(x64[i]) - borde) / max(abs(float(x64[i])), 1e-300)})
    return out


def comparar_float64(a: np.ndarray, b: np.ndarray) -> dict:
    """Dos cálculos float64 del mismo predictor: NaN, diferencia relativa máxima y float32 iguales."""
    na, nb = np.isnan(a), np.isnan(b)
    ok = ~(na | nb)
    den = np.abs(b[ok])
    cero = den == 0
    rel = np.abs(a[ok][~cero] - b[ok][~cero]) / den[~cero]
    return {"filas": int(len(a)), "nan_iguales": bool(np.array_equal(na, nb)),
            "dif_rel_max": float(rel.max(initial=0.0)),
            "ceros_iguales": bool(np.array_equal(a[ok][cero], b[ok][cero])),
            "float32_distintas": int((a.astype("float32")[ok] != b.astype("float32")[ok]).sum())}


def pasa(c: dict) -> bool:
    return c["nan_iguales"] and c.get("ceros_iguales", True) and c["dif_rel_max"] <= TOLERANCIA_REL


# ---------------------------------------------------------------------------
# (b) Muestra frente al cálculo ingenuo de la v1
# ---------------------------------------------------------------------------
def elegir_pliegues_b(m: dict, pol: str, vec: Vecindario) -> list[tuple[str, dict]]:
    """Pliegues de la muestra: de una estación, conglomerados con gemelos, el mayor de LBO-10 y BLQ-75, las
    regiones con más filas en suma directa y la mayor, y tres conjuntos al azar (con semilla)."""
    p = m["contaminantes"][pol]["protocolos"]
    elegidos: list[tuple[str, dict]] = []

    def agregar(prot, f):
        if f is not None and all(not (a == prot and b["k"] == f["k"]) for a, b in elegidos):
            elegidos.append((prot, f))

    loso = p["LOSO-D"]["pliegues"]
    agregar("LOSO-D", next((f for f in loso if len(f["excluidas"]) == 1), None))
    for marca in ("309", "B03", "503"):
        agregar("LOSO-D", next((f for f in loso if marca in f["estaciones_prueba"]), None))
    agregar("LBO-10", max(p["LBO-10"]["pliegues"], key=lambda f: len(f["excluidas"])))
    agregar("BLQ-75", max(p["BLQ-75"]["pliegues"], key=lambda f: len(f["excluidas"])))
    lro = p["LRO"]["pliegues"]
    agregar("LRO", max(lro, key=lambda f: len(f["excluidas"])))
    for grupo in ("RII", "RXI", "RXII"):
        agregar("LRO", next((f for f in lro if f["grupo"] == grupo), None))
    rng = np.random.default_rng([SEMILLA, 0])
    nombres = [str(s) for s in vec.estaciones]
    for j, tam in enumerate((3, 10, max(2, len(nombres) // 3))):
        excl = sorted(rng.choice(nombres, size=tam, replace=False).tolist())
        prueba = excl[: max(1, tam // 2)]
        elegidos.append(("LRO", {"k": 1000 + j, "grupo": f"azar_{tam}", "estaciones_prueba": prueba, "excluidas": excl,
                                 "nota": f"conjunto al azar de {tam} estaciones, semilla [42, 0]"}))
    return elegidos


def muestra_filas(rec: Recalculo, base: Recalculo, k: int, n: int, umbral: float, kappa: float) -> tuple[np.ndarray, dict]:
    """Filas de entrenamiento, de prueba, difíciles (lo excluido pesa ≥ 1 − κ) y cercanas al umbral."""
    rng = np.random.default_rng([SEMILLA, int(k)])
    pf, pb = rec.peso_vec.astype("float64"), base.peso_vec.astype("float64")
    grupos = {
        "entrenamiento": np.flatnonzero(rec.entrenamiento),
        "prueba": np.flatnonzero(rec.prueba),
        "dificiles": np.flatnonzero((pb > 0) & (pf <= kappa * pb)),
        "cerca_del_umbral": np.flatnonzero((pf > 0.5 * umbral) & (pf < 2.0 * umbral)),
    }
    partes, conteo = [], {}
    for nombre, idx in grupos.items():
        tomar = idx if len(idx) <= n else rng.choice(idx, n, replace=False)
        partes.append(tomar)
        conteo[nombre] = {"disponibles": int(len(idx)), "en_muestra": int(len(tomar))}
    return np.unique(np.concatenate(partes)), conteo


def prueba_b(vec: Vecindario, O: pd.DataFrame, elegidos, n: int) -> list[dict]:
    base = vec.recalcular((), precision="float64", registrar=False, huellas=False)
    salida = []
    for prot, f in elegidos:
        t0 = time.perf_counter()
        ent, pru, excl = vec.mascaras(f, prot)
        rec = vec.recalcular(excl, precision="float64", entrenamiento=ent, prueba=pru, registrar=False, huellas=False)
        filas, conteo = muestra_filas(rec, base, f["k"], n, vec.umbral, vec.kappa)
        js = vec.js[filas]
        ov, pw, dist = recalculo_directo_v1(O, vec.lat, vec.lon, vec.estaciones[js], vec.tiempos[vec.it[filas]].to_numpy(),
                                            vec.lat[js], vec.lon[js], excl, h_km=vec.h_km, precision="float64")
        c_obs, c_peso = comparar_float64(rec.obs_vec[filas], ov), comparar_float64(rec.peso_vec[filas], pw)
        dist_iguales = bool(np.array_equal(rec.dist_est_km[filas], dist))
        salida.append({"protocolo": prot, "k": f["k"], "grupo": f["grupo"], "n_excluidas": len(excl),
                       "nota": f.get("nota"), "muestra": conteo, "filas_muestra": int(len(filas)),
                       "obs_vec": c_obs, "peso_vec": c_peso, "dist_est_km_iguales": dist_iguales,
                       "pasa": pasa(c_obs) and pasa(c_peso) and dist_iguales,
                       "segundos": round(time.perf_counter() - t0, 2)})
        log.info("(b) %s %s %s: obs_vec rel %.2e, peso_vec rel %.2e, dist %s, %d filas", vec.pol, prot, f["grupo"],
                 c_obs["dif_rel_max"], c_peso["dif_rel_max"], "=" if dist_iguales else "≠", len(filas))
    return salida


# ---------------------------------------------------------------------------
# (b, todas las filas) y (c): todos los pliegues
# ---------------------------------------------------------------------------
def todos_los_pliegues(vec: Vecindario, m: dict, comparar: bool = True) -> list[dict]:
    """Por pliegue: el recálculo de producción (float32, con huellas, registrado y cronometrado) y, si se pide,
    la comparación del descuento con la suma directa matricial en todas las filas."""
    filas = []
    for prot in PROTOCOLOS:
        for f in m["contaminantes"][vec.pol]["protocolos"][prot]["pliegues"]:
            t0 = time.perf_counter()
            rec = vec.para_pliegue(f, prot)
            pared = time.perf_counter() - t0
            g = rec.registro
            fila = {"contaminante": vec.pol, "protocolo": prot, "k": f["k"], "grupo": f["grupo"],
                    "n_excluidas": g["n_excluidas"], "filas_entrenamiento": g["filas_entrenamiento"],
                    "filas_prueba": g["filas_prueba"], "filas_con_descuento": g["filas_con_descuento"],
                    "filas_suma_directa": g["filas_suma_directa"], "filas_sin_vecinas": g["filas_sin_vecinas"],
                    "obs_vec_nan_entrenamiento": g["obs_vec_nan_entrenamiento"], "obs_vec_nan_prueba": g["obs_vec_nan_prueba"],
                    "segundos_recalculo": g["segundos"], "segundos_pared": round(pared, 4)}
            if comparar and prot != "LPO":
                excl = f["excluidas"]
                d = vec.recalcular(excl, precision="float64", registrar=False, huellas=False)
                t1 = time.perf_counter()
                x = vec.recalcular(excl, metodo="directo", precision="float64", registrar=False, huellas=False)
                fila["segundos_directo"] = round(time.perf_counter() - t1, 4)
                co, cp = comparar_float64(d.obs_vec, x.obs_vec), comparar_float64(d.peso_vec, x.peso_vec)
                fila.update({"obs_vec_rel_max_vs_directo": co["dif_rel_max"], "peso_vec_rel_max_vs_directo": cp["dif_rel_max"],
                             "nan_iguales_vs_directo": co["nan_iguales"] and cp["nan_iguales"],
                             "ceros_iguales_vs_directo": cp["ceros_iguales"] and co["ceros_iguales"],
                             "float32_distintas_vs_directo": co["float32_distintas"] + cp["float32_distintas"],
                             "dist_iguales_vs_directo": bool(np.array_equal(d.dist_est_km, x.dist_est_km)),
                             "float32_igual_al_de_produccion": bool(np.array_equal(d.obs_vec.astype("float32"), rec.obs_vec, equal_nan=True)
                                                                    and np.array_equal(d.peso_vec.astype("float32"), rec.peso_vec))})
            filas.append(fila)
        log.info("(c) %s %s: %d pliegues", vec.pol, prot, len(m["contaminantes"][vec.pol]["protocolos"][prot]["pliegues"]))
    return filas


def resumen_tiempos(df: pd.DataFrame) -> dict:
    """Tiempos por protocolo y, de paso, la fracción de filas de prueba que quedan sin vecindario (obs_vec NaN)."""
    out = {}
    for prot, g in df.groupby("protocolo", sort=False):
        s = g["segundos_pared"]
        out[prot] = {"pliegues": int(len(g)), "min_s": round(float(s.min()), 3), "mediana_s": round(float(s.median()), 3),
                     "max_s": round(float(s.max()), 3), "total_s": round(float(s.sum()), 2),
                     "obs_vec_nan_prueba_fraccion": round(float(g["obs_vec_nan_prueba"].sum() / g["filas_prueba"].sum()), 5),
                     "pliegues_con_mas_de_10pct_de_prueba_sin_vecindario": sorted(
                         str(x) for x in g.loc[g["obs_vec_nan_prueba"] > 0.1 * g["filas_prueba"], "grupo"])}
    return out


def tipos_tabla(df: pd.DataFrame) -> pd.DataFrame:
    """Enteros y booleanos con faltantes (las filas de LPO no se comparan) como tipos anulables de pandas."""
    df = df.copy()
    for c in ("float32_distintas_vs_directo",):
        if c in df:
            df[c] = df[c].astype("Int64")
    for c in ("nan_iguales_vs_directo", "ceros_iguales_vs_directo", "dist_iguales_vs_directo",
              "float32_igual_al_de_produccion"):
        if c in df:
            df[c] = df[c].astype("boolean")
    return df


def resumen_vs_directo(df: pd.DataFrame) -> dict:
    g = df[df["protocolo"] != "LPO"]
    return {"pliegues": int(len(g)), "filas_por_pliegue": "todas las del panel",
            "obs_vec_rel_max": float(g["obs_vec_rel_max_vs_directo"].max()),
            "peso_vec_rel_max": float(g["peso_vec_rel_max_vs_directo"].max()),
            "nan_iguales_en_todos": bool(g["nan_iguales_vs_directo"].all()),
            "ceros_iguales_en_todos": bool(g["ceros_iguales_vs_directo"].all()),
            "dist_iguales_en_todos": bool(g["dist_iguales_vs_directo"].all()),
            "float32_distintas_total": int(g["float32_distintas_vs_directo"].sum()),
            "produccion_float32_igual_al_float64_redondeado": bool(g["float32_igual_al_de_produccion"].all()),
            "filas_suma_directa_total": int(g["filas_suma_directa"].sum()),
            "pasa": bool(g["nan_iguales_vs_directo"].all() and g["ceros_iguales_vs_directo"].all()
                         and g["dist_iguales_vs_directo"].all()
                         and max(g["obs_vec_rel_max_vs_directo"].max(), g["peso_vec_rel_max_vs_directo"].max()) <= TOLERANCIA_REL)}


# ---------------------------------------------------------------------------
# Por contaminante
# ---------------------------------------------------------------------------
def validar_contaminante(pol: str, r: RutasV2, cfg: dict, m: dict, hilos: int, n_muestra: int,
                         fuentes_v1: bool, comparar: bool) -> tuple[dict, pd.DataFrame, Vecindario, dict]:
    import pyarrow.parquet as pq

    t0 = time.perf_counter()
    vec = Vecindario.desde_panel(pol, r, manifiesto=m, cfg=cfg, hilos=hilos)
    construccion = round(time.perf_counter() - t0, 3)
    panel = pq.read_table(r.panel(pol), columns=["obs", *VARIABLES]).to_pandas()
    meta = leer_json(r.panel_meta(pol)) or {}
    res: dict = {"vecindario": vec.huella(), "construccion_s": construccion,
                 "construccion_interna_s": vec.segundos_construccion}
    insumos_extra: dict = {}

    # (a1) valores del panel
    b32 = vec.base(precision="float64", registrar=False)
    a1 = {c: comparar_float32(getattr(b32, c), panel[c].to_numpy()) for c in VARIABLES}
    a1["explicacion"] = ("peso_vec y dist_est_km no dependen de los valores: bit a bit. obs_vec: el panel guarda obs en "
                         "float32 y la v1 promedió los valores float64; |Δ| ≤ 2^-24·obs_vec (V ≥ 0), menos de 1 ULP antes "
                         "de redondear y como mucho 1 ULP después.")
    rec_base = vec.base()                                     # el de producción, registrado con sus huellas
    a1["produccion_float32_igual"] = bool(np.array_equal(rec_base.obs_vec, b32.obs_vec.astype("float32"), equal_nan=True))
    res["a1_fuente_panel_float32"] = a1

    # (a2) observaciones float64 de la v1
    if fuentes_v1:
        esperado = {"desde": DESDE, "hasta": HASTA, "qc_racha_minima": QC_RACHA, "reloj_sinca": "UTC-4 fijo; etiqueta=fin",
                    "redes": ["sinca", "snifa"]}
        dif = {k: meta.get(k) for k, v in esperado.items() if meta.get(k) != v}
        if dif:
            raise SystemExit(f"{pol}: el panel v1 declara otra configuración que la replicada: {dif}")
        t1 = time.perf_counter()
        o, info = observaciones_v1_float64(pol, r)
        qc = meta.get("qc_descriptivo", {})
        info["qc_del_panel_frente_a_la_reconstruccion"] = {k: {"reconstruccion": info[k], "panel": qc.get(k)}
                                                           for k in ("filas_validas", "filas_en_racha", "estaciones_con_racha")}
        info["qc_nota"] = ("El QC descriptivo del panel (qc_descriptivo) cuenta sólo SINCA; la reconstrucción suma la red "
                           "SNIFA en NO2 (como el panel y el vecindario de la v1). En PM2,5 deben coincidir; en NO2 la "
                           "reconstrucción tiene además las filas SNIFA (el mapa v1 da 39.071 filas en racha con SNIFA).")
        obs64, alin = alinear_con_panel(vec, o, panel["obs"].to_numpy())
        coords = dict(zip(vec.estaciones, zip(vec.lat, vec.lon)))
        estacion = pd.Categorical.from_codes(vec.js, categories=[str(s) for s in vec.estaciones])
        vec64 = Vecindario(pol, estacion, vec.tiempos[vec.it].to_numpy(), obs64, coords, hilos=hilos,
                           origen="observaciones v1 float64 reconstruidas (sólo validación)")
        b64 = vec64.base(precision="float64", registrar=False)
        a2 = {"reconstruccion": {**info, **alin, "segundos": round(time.perf_counter() - t1, 1)}}
        a2.update({c: comparar_float32(getattr(b64, c), panel[c].to_numpy()) for c in VARIABLES})
        a2["diferencias"] = [d for c in ("obs_vec", "peso_vec") for d in
                             explicar_diferencias(getattr(b64, c), panel[c].to_numpy(), vec, c)]
        x32, x64 = b32.obs_vec, b64.obs_vec
        ok = np.isfinite(x64) & (x64 > 0)
        razon = np.abs(x32[ok] - x64[ok]) / (2.0 ** -24 * x64[ok])
        cero = np.isfinite(x64) & (x64 == 0)
        a2["cota_redondeo_V"] = {"razon_max": float(razon.max(initial=0.0)), "filas": int(ok.sum()),
                                 "filas_obs_vec_cero": int(cero.sum()),
                                 "dif_max_en_ceros": float(np.abs(x32[cero]).max(initial=0.0)),
                                 "a1_diferentes_que_a2_reproduce": int(((x32.astype("float32") != panel["obs_vec"].to_numpy())
                                                                        & (x64.astype("float32") == panel["obs_vec"].to_numpy())).sum()),
                                 "lectura": "razón ≤ 1 en todas las filas: cada diferencia de a1 es el redondeo de V a float32"}
        res["a2_fuente_v1_float64"] = a2
        insumos_extra = {"catalogo_sinca": r.catalogo_sinca, "snifa": r.snifa,
                         **{f"grilla_{Path(nm).stem}": r.grilla_v1 / nm for nm in pv.INSUMOS_GRILLA}}
        res["a2_fuente_v1_float64"]["reconstruccion"]["insumos_extra"] = sorted(insumos_extra)
        del vec64, b64, o, obs64

    # (b) muestra frente al cálculo ingenuo
    O = vec.matriz_O()
    res["b_muestra_vs_ingenuo"] = prueba_b(vec, O, elegir_pliegues_b(m, pol, vec), n_muestra)
    fb = np.sort(np.random.default_rng([SEMILLA, 999]).choice(vec.n, min(4 * n_muestra, vec.n), replace=False))
    jb = vec.js[fb]
    base_ingenua = recalculo_directo_v1(O, vec.lat, vec.lon, vec.estaciones[jb], vec.tiempos[vec.it[fb]].to_numpy(),
                                        vec.lat[jb], vec.lon[jb], (), h_km=vec.h_km, precision="float64")
    res["b_base_vs_ingenuo"] = {"filas": int(len(fb)), "semilla": [SEMILLA, 999],
                                "obs_vec": comparar_float64(b32.obs_vec[fb], base_ingenua[0]),
                                "peso_vec": comparar_float64(b32.peso_vec[fb], base_ingenua[1]),
                                "dist_est_km_iguales": bool(np.array_equal(b32.dist_est_km[fb], base_ingenua[2]))}
    del O

    # (b, todas las filas) y (c)
    tiempos = pd.DataFrame(todos_los_pliegues(vec, m, comparar=comparar))
    res["c_tiempos"] = {"por_protocolo": resumen_tiempos(tiempos), "total_s": round(float(tiempos["segundos_pared"].sum()), 2),
                        "construccion_s": construccion,
                        "nota": "recálculo completo: las tres columnas en todas las filas (entrenamiento, prueba y "
                                "entorno), en float32, con las huellas sha256; un tiempo no es un resultado (§10)"}
    if comparar:
        res["b_todos_vs_directo"] = resumen_vs_directo(tiempos)
    return res, tiempos, vec, insumos_extra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Valida el vecindario v2: reproducción de la v1, descuento y tiempos.")
    ap.add_argument("--contaminantes", nargs="+", default=list(CONTAMINANTES), choices=CONTAMINANTES)
    ap.add_argument("--hilos", type=int, default=None, help="tope de hilos de BLAS (≤ 12; config por omisión)")
    ap.add_argument("--muestra", type=int, default=40_000, help="filas por grupo en la muestra de (b)")
    ap.add_argument("--sin-fuentes-v1", action="store_true", help="omite a2 (no lee el derivado SINCA)")
    ap.add_argument("--sin-directo", action="store_true", help="omite la comparación con la suma directa en todos los pliegues")
    ap.add_argument("--no-escribir", action="store_true", help="calcula y resume sin escribir nada")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    r = rutas_v2()
    cfg = cargar_config(r)
    hilos = min(int(args.hilos or cfg["operacion"]["hilos_maximos"]), int(cfg["operacion"]["hilos_maximos"]))
    m = leer_json(r.manifiesto_pliegues)
    if m is None:
        raise SystemExit("Falta el manifiesto de pliegues; corre pliegues_v2.py")
    carga0 = os.getloadavg() if hasattr(os, "getloadavg") else None
    informe = {"schema": SCHEMA, "creado_utc": ahora_utc(),
               "descripcion": ("Validación del vecindario v2 (vecindario_v2.py): (a) reproducción de las columnas del "
                               "panel v1 sin exclusiones adicionales; (b) descuento frente al cálculo directo ingenuo y "
                               "a la suma directa matricial; (c) tiempo de un recálculo completo por pliegue."),
               "criterios": {"tolerancia_relativa": TOLERANCIA_REL, "semilla_muestra": [SEMILLA, "k"],
                             "filas_por_grupo_en_muestra": args.muestra},
               "huella_pliegues": m["huella_pliegues"], "contaminantes": {}}
    tablas, vecs, insumos = [], {}, {"manifiesto_pliegues": r.manifiesto_pliegues}
    for pol in args.contaminantes:
        res, tiempos, vec, extra = validar_contaminante(pol, r, cfg, m, hilos, args.muestra,
                                                        not args.sin_fuentes_v1, not args.sin_directo)
        informe["contaminantes"][pol] = res
        tablas.append(tiempos)
        vecs[pol] = vec
        insumos.update(vec.insumos)
        insumos.update(extra)
    carga1 = os.getloadavg() if hasattr(os, "getloadavg") else None
    informe["entorno"] = {"hilos_blas": hilos, "cpu_count": os.cpu_count(), "maquina": platform.machine(),
                          "carga_1_5_15_min_inicio": carga0, "carga_1_5_15_min_fin": carga1}
    tiempos = tipos_tabla(pd.concat(tablas, ignore_index=True))
    informe["veredicto"] = veredicto(informe)
    print(resumen_texto(informe))
    if args.no_escribir:
        return 0
    with candado_escritura("vecindario", rutas=r):
        sha_csv = publicar_csv(tiempos, r.salidas_v2 / "vecindario_v2_tiempos.csv", r)
        registros = {}
        for pol, vec in vecs.items():
            destino = r.raiz_v2 / "vecindario" / f"registro_recalculos_{pol}.json"
            registros[pol] = {**r.relativa(destino), "sha256": vec.publicar_registro(
                destino, r, extra={"huella_pliegues": m["huella_pliegues"],
                                   "nota": "un renglón por recálculo de producción: base y cada pliegue de los cinco protocolos"})}
        informe["salidas"] = {"tiempos_csv": {**r.relativa(r.salidas_v2 / "vecindario_v2_tiempos.csv"), "sha256": sha_csv},
                              "registros": registros}
        informe["traza"] = traza(insumos, {"muestra": [SEMILLA, "k"], "azar": [SEMILLA, 0]}, hilos, rutas=r,
                                 parametros={"tolerancia_relativa": TOLERANCIA_REL, "muestra": args.muestra})
        publicar_json(informe, r.salidas_v2 / "vecindario_v2_validacion.json", r)
    log.info("Escrito: output_files/modelo_1km_v2/vecindario_v2_validacion.json, vecindario_v2_tiempos.csv y "
             "<raíz v2>/vecindario/registro_recalculos_<pol>.json")
    return 0


def veredicto(informe: dict) -> dict:
    out = {}
    for pol, res in informe["contaminantes"].items():
        a1 = res["a1_fuente_panel_float32"]
        v = {"a1_peso_y_dist_bit_a_bit": all(a1[c]["bit_a_bit"] == a1[c]["filas"] - a1[c]["nan"] for c in ("peso_vec", "dist_est_km"))
             and all(a1[c]["nan_iguales"] for c in VARIABLES),
             "a1_obs_vec_a_lo_mas_1_ulp": a1["obs_vec"]["a_mas_de_1_ulp"] == 0 and a1["obs_vec"]["nan_iguales"]}
        if "a2_fuente_v1_float64" in res:
            a2 = res["a2_fuente_v1_float64"]
            v["a2_bit_a_bit"] = all(a2[c]["bit_a_bit"] == a2[c]["filas"] - a2[c]["nan"] and a2[c]["nan_iguales"] for c in VARIABLES)
            v["a2_cota_redondeo_V_cumplida"] = a2["cota_redondeo_V"]["razon_max"] <= 1.0 + 1e-9
        v["b_muestra_pasa"] = all(x["pasa"] for x in res["b_muestra_vs_ingenuo"])
        bb = res["b_base_vs_ingenuo"]
        v["b_base_pasa"] = pasa(bb["obs_vec"]) and pasa(bb["peso_vec"]) and bb["dist_est_km_iguales"]
        if "b_todos_vs_directo" in res:
            v["b_todos_vs_directo_pasa"] = res["b_todos_vs_directo"]["pasa"]
        out[pol] = v
    return out


def resumen_texto(inf: dict) -> str:
    lineas = []
    for pol, res in inf["contaminantes"].items():
        a1 = res["a1_fuente_panel_float32"]
        lineas.append(f"== {pol}: construcción {res['construccion_s']} s; vecindario {res['vecindario']['huella'][:16]}")
        for c in VARIABLES:
            x = a1[c]
            lineas.append(f"  (a1 panel) {c}: NaN iguales {x['nan_iguales']}; bit a bit {x['bit_a_bit']:,}; 1 ULP {x['a_1_ulp']:,}; "
                          f">1 ULP {x['a_mas_de_1_ulp']}; rel máx {x['dif_rel_max']:.2e}")
        if "a2_fuente_v1_float64" in res:
            a2 = res["a2_fuente_v1_float64"]
            for c in VARIABLES:
                x = a2[c]
                lineas.append(f"  (a2 v1 f64) {c}: NaN iguales {x['nan_iguales']}; bit a bit {x['bit_a_bit']:,} de "
                              f"{x['filas'] - x['nan']:,}; rel máx {x['dif_rel_max']:.2e}")
            lineas.append(f"  (a2) cota del redondeo de V: razón máx {a2['cota_redondeo_V']['razon_max']:.4f}; diferencias "
                          f"listadas {len(a2['diferencias'])}")
        for x in res["b_muestra_vs_ingenuo"]:
            lineas.append(f"  (b) {x['protocolo']:<7} {x['grupo']:<26} excl {x['n_excluidas']:>2}  filas {x['filas_muestra']:>7,}  "
                          f"obs rel {x['obs_vec']['dif_rel_max']:.1e}  peso rel {x['peso_vec']['dif_rel_max']:.1e}  "
                          f"dist {'=' if x['dist_est_km_iguales'] else '≠'}  {'pasa' if x['pasa'] else 'NO PASA'}")
        if "b_todos_vs_directo" in res:
            t = res["b_todos_vs_directo"]
            lineas.append(f"  (b todos) {t['pliegues']} pliegues: obs rel máx {t['obs_vec_rel_max']:.1e}, peso rel máx "
                          f"{t['peso_vec_rel_max']:.1e}, NaN iguales {t['nan_iguales_en_todos']}, float32 distintas "
                          f"{t['float32_distintas_total']}, suma directa {t['filas_suma_directa_total']:,} filas")
        for prot, t in res["c_tiempos"]["por_protocolo"].items():
            lineas.append(f"  (c) {prot:<7} {t['pliegues']:>3} pliegues: mediana {t['mediana_s']:.3f} s, máx {t['max_s']:.3f} s, "
                          f"total {t['total_s']:.1f} s")
    lineas.append(f"Veredicto: {json.dumps(inf['veredicto'], ensure_ascii=False)}")
    return "\n".join(lineas)


if __name__ == "__main__":
    sys.exit(main())
