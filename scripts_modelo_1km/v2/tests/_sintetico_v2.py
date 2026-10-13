"""Datos sintéticos pequeños para las pruebas de motores, pérdidas, métricas y del orquestador v2.

Nueve estaciones sobre un meridiano (la distancia haversine es exacta en km): gemelas A1–A2 a 100 m (un
conglomerado de LOSO-D), B a 8 km de A1 (entorno de LBO-10, a más de 2 km), y C … H más lejos, en tres regiones
(RA, RB, RC), cuatro bloques y tres macrozonas. 120 días horarios que cruzan el cambio de año 2019/2020 (dos
cuatrienios de LPO), con faltantes en las observaciones y en los predictores (GEOS-CF sólo en 2020, CAMS ausente al
principio, ERA5-Land con huecos). El manifiesto tiene los cinco protocolos con la misma forma que
``pliegues_v2.json``. Nada aquí escribe fuera de una carpeta temporal.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))
import _rutas_v2 as rv  # noqa: E402
import pliegues_v2 as plv  # noqa: E402
from vecindario_v2 import Vecindario  # noqa: E402

KM_POR_GRADO = plv.RADIO_TIERRA_KM * np.pi / 180.0
LAT0, LON0 = -33.0, -70.6
# estación: (km al norte, región, bloque, macrozona, nivel base)
ESTACIONES = {
    "A1": (0.0, "RA", "E000N000", 2, 35.0), "A2": (0.1, "RA", "E000N000", 2, 33.0),
    "B": (8.0, "RA", "E000N000", 2, 28.0), "C": (100.0, "RA", "E000N001", 2, 22.0),
    "D": (250.0, "RB", "E000N001", 3, 18.0), "E": (400.0, "RB", "E000N002", 3, 15.0),
    "F": (600.0, "RC", "E000N002", 0, 12.0), "G": (800.0, "RC", "E000N003", 0, 10.0),
    "H": (1000.0, "RC", "E000N003", 0, 9.0),
}
PREDICTORES = ["hora_local", "hora_sin", "hora_cos", "doy_sin", "doy_cos", "dow", "mes", "anio", "lat", "lon",
               "macrozona_cod", "elev_m", "el_t2m", "el_rh", "el_wind", "inv_blh", "m2_t2m", "m2_u10m", "m2_v10m",
               "m2_pm25", "m2_aod_pblh", "cams_pm25", "gcf_pm25", "acag_pm25", "pob_dens", "obs_vec", "peso_vec",
               "dist_est_km"]
INICIO = pd.Timestamp("2019-11-01 04:00")       # inicio de bin UTC = 00:00 del 1-nov en UTC−4


def lat_de(km: float) -> float:
    return LAT0 + km / KM_POR_GRADO


def panel_sintetico(dias: int = 120, semilla: int = 3, p_falta: float = 0.08, perturbar: dict | None = None) -> pd.DataFrame:
    """Panel horario con las columnas que usa la v2. ``perturbar`` = ``{estación: factor}`` multiplica sus
    observaciones (para las pruebas de exclusión) sin tocar ningún predictor."""
    rng = np.random.default_rng(semilla)
    ts = INICIO + pd.to_timedelta(np.arange(dias * 24), unit="h")
    local = ts - pd.Timedelta(hours=4)
    h = local.hour.to_numpy()
    doy = local.dayofyear.to_numpy()
    comun = rng.normal(0.0, 0.35, size=len(ts))                  # episodio regional compartido
    filas = []
    for s, (km, region, bloque, mz, nivel) in ESTACIONES.items():
        diario = 1.0 + 0.45 * np.cos(2 * np.pi * (h - 21) / 24)
        estacional = 1.0 + 0.25 * np.cos(2 * np.pi * (doy - 172) / 365.25)
        ruido = rng.normal(0.0, 0.25, size=len(ts))
        verdad = nivel * diario * estacional * np.exp(comun * (1.0 if km < 500 else 0.4) + ruido)
        obs = np.round(verdad, 2)
        obs[rng.random(len(ts)) < 0.01] = 0.0
        medido = rng.random(len(ts)) >= p_falta
        d = pd.DataFrame({"estacion": s, "ts_utc": ts, "obs": obs, "region_sinca": region, "bloque": bloque,
                          "macrozona_cod": np.int8(mz)})
        d["hora_local"] = h.astype("int8")
        d["hora_sin"], d["hora_cos"] = np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)
        d["doy_sin"], d["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
        d["dow"], d["mes"], d["anio"] = local.dayofweek.to_numpy(), local.month.to_numpy(), local.year.to_numpy()
        d["fecha_local"] = local.normalize()
        d["lat"], d["lon"] = lat_de(km), LON0
        d["elev_m"] = 500.0 + km * 0.3
        t2m = 15 + 8 * np.cos(2 * np.pi * (h - 15) / 24) + rng.normal(0, 1, len(ts))
        d["el_t2m"] = np.where(rng.random(len(ts)) < 0.1, np.nan, t2m)
        d["m2_t2m"] = t2m + rng.normal(0, 0.5, len(ts))
        d["el_rh"] = 60 + rng.normal(0, 10, len(ts))
        u, v = rng.normal(1, 2, len(ts)), rng.normal(0, 2, len(ts))
        d["m2_u10m"], d["m2_v10m"] = u, v
        d["el_wind"] = np.where(rng.random(len(ts)) < 0.1, np.nan, np.sqrt(u ** 2 + v ** 2) + rng.normal(0, .2, len(ts)))
        blh = np.exp(rng.normal(6.5, 0.5, len(ts)))
        d["inv_blh"] = 1.0 / np.clip(blh, 50, None)
        d["m2_pm25"] = verdad * np.exp(rng.normal(0, 0.4, len(ts)))
        d["m2_aod_pblh"] = d["m2_pm25"] / 100.0
        cams = verdad * np.exp(rng.normal(0, 0.5, len(ts)))
        d["cams_pm25"] = np.where(np.arange(len(ts)) < len(ts) * 0.2, np.nan, cams)
        gcf = verdad * np.exp(rng.normal(0, 0.3, len(ts)))
        d["gcf_pm25"] = np.where(d["anio"].to_numpy() >= 2020, gcf, np.nan)
        d["acag_pm25"] = nivel * 0.9
        d["pob_dens"] = 1000.0 * (1.0 + (km < 200)) + (d["anio"].to_numpy() - 2019) * 10.0
        if perturbar and s in perturbar:
            d["obs"] = d["obs"] * float(perturbar[s])
        filas.append(d[medido])
    panel = pd.concat(filas, ignore_index=True)
    panel = panel.sort_values(["ts_utc", "estacion"], kind="stable").reset_index(drop=True)
    for c in panel.columns:
        if panel[c].dtype == "float64":
            panel[c] = panel[c].astype("float32")
    panel["obs"] = panel["obs"].astype("float32")
    vec = Vecindario("pm25", panel["estacion"], panel["ts_utc"].to_numpy(), panel["obs"].to_numpy(), coordenadas(),
                     anio=panel["anio"].to_numpy(), hilos=1)
    b = vec.base(registrar=False)
    panel["obs_vec"], panel["peso_vec"], panel["dist_est_km"] = b.obs_vec, b.peso_vec, b.dist_est_km
    return panel


def coordenadas() -> dict:
    return {s: (lat_de(v[0]), LON0) for s, v in ESTACIONES.items()}


def _pliegue(k, grupo, prueba, excluidas, filas_por_est, **extra):
    total = sum(filas_por_est.values())
    fp = sum(filas_por_est.get(s, 0) for s in prueba)
    fe = sum(filas_por_est.get(s, 0) for s in excluidas)
    return {"k": k, "semilla": [42, k], "grupo": grupo, "estaciones_prueba": sorted(prueba),
            "excluidas": sorted(excluidas), **extra, "filas_prueba": int(fp),
            "filas_entrenamiento_disponibles": int(total - fe), "filas_fuera_del_pliegue": int(fe - fp)}


def manifiesto_sintetico(panel: pd.DataFrame) -> dict:
    filas = panel.groupby("estacion").size().to_dict()
    nombres = sorted(ESTACIONES)
    congl = [("A1", "A2")] + [(s,) for s in nombres if s not in ("A1", "A2")]
    congl = sorted(congl, key=lambda c: "+".join(c))
    loso = [_pliegue(k, "+".join(c), c, c, filas) for k, c in enumerate(congl)]
    km = {s: v[0] for s, v in ESTACIONES.items()}
    lbo = []
    for k, c in enumerate(congl):
        cerca = sorted(s for s in nombres if any(abs(km[s] - km[x]) <= 10.0 for x in c))
        lbo.append(_pliegue(k, "+".join(c), c, cerca, filas, radio_incluye_fuera_del_panel=[]))
    bloques = {}
    for s, v in ESTACIONES.items():
        bloques.setdefault(v[2], []).append(s)
    blq = [_pliegue(k, b, bloques[b], bloques[b], filas) for k, b in enumerate(sorted(bloques))]
    regiones = {}
    for s, v in ESTACIONES.items():
        regiones.setdefault(v[1], []).append(s)
    lro = [_pliegue(k, g, regiones[g], regiones[g], filas) for k, g in enumerate(sorted(regiones))]
    anios = panel["anio"].astype(int)
    ventanas = plv.ventana_de(anios.to_numpy(), 2000, 2026, 4)
    lpo = []
    for k, v in enumerate(sorted(set(ventanas))):
        ini, fin = (int(x) for x in v.split("–"))
        dentro = (anios >= ini) & (anios <= fin)
        fp = int(dentro.sum())
        lpo.append({"k": k, "semilla": [42, k], "grupo": v,
                    "estaciones_prueba": sorted(panel.loc[dentro, "estacion"].unique().tolist()), "excluidas": [],
                    "exclusion_temporal": {"anio_desde": ini, "anio_hasta": fin}, "filas_prueba": fp,
                    "filas_entrenamiento_disponibles": int(len(panel) - fp), "filas_fuera_del_pliegue": 0})
    prot = {"LOSO-D": loso, "LBO-10": lbo, "BLQ-75": blq, "LRO": lro, "LPO": lpo}
    m = {"schema": plv.SCHEMA, "parametros": {"sintetico": True},
         "estaciones": [{"estacion": s, "lat": lat_de(v[0]), "lon": LON0} for s, v in sorted(ESTACIONES.items())],
         "contaminantes": {"pm25": {"estaciones": nombres, "panel": {"sha256": "sintetico"},
                                    "protocolos": {p: {"n_pliegues": len(v), "pliegues": v} for p, v in prot.items()}}}}
    m["huella_pliegues"] = plv.huella_pliegues(m)
    m["conteos"] = {"pm25": {p: len(v) for p, v in prot.items()}}
    return m


def _vigente(item: dict) -> str:
    """Clave del valor que lee el código en un objeto de la configuración: «valor» si una enmienda lo ratificó,
    «provisional» si sigue pendiente (``_rutas_v2.valor_vigente``)."""
    return "valor" if rv.estado_vigente(item) == "ratificado" else "provisional"


def config_pequena(n_comun: int = 1200, internos: int = 2) -> dict:
    """La configuración real con recetas diminutas (mismas claves y valores vigentes), para que todo corra en segundos."""
    cfg = json.loads((V2 / rv.NOMBRE_CONFIG).read_text(encoding="utf-8"))
    cfg = copy.deepcopy(cfg)
    a = cfg["motores"]["eje_A"]
    a["predictores"]["pm25"] = list(PREDICTORES)
    a["lightgbm"].update({"num_boost_round": 12, "num_leaves": 7, "min_data_in_leaf": 10})
    a["xgboost"].update({"num_boost_round": 12, "max_leaves": 7})
    mcw = a["xgboost"]["min_child_weight"]
    mcw[_vigente(mcw)] = 10
    a["random_forest"].update({"n_estimators": 8, "min_samples_leaf": 10})
    a["mlp"].update({"hidden_layer_sizes": [8], "max_iter": 6})
    rec = cfg["motores"]["alertas"]["receta"]
    rec[_vigente(rec)].update({"num_boost_round": 10, "num_leaves": 7, "min_data_in_leaf": 10})
    topes = cfg["motores"]["eje_B"]["topes_de_filas"]
    topes[_vigente(topes)].update({"gp": 120, "lme": 1500})
    pint = cfg["motores"]["apilado_anidado"]["pliegues_internos"]
    pint[_vigente(pint)]["n"] = internos
    f = cfg["filas_entrenamiento"]
    f["N_comun_eje_A"] = n_comun
    f["curvas_de_aprendizaje"] = {"protocolos": ["LRO", "BLQ-75"], "lightgbm": [500, n_comun, 2400, "todas"],
                                  "xgboost": [500, n_comun, 2400, "todas"], "random_forest": [500, n_comun, 2400]}
    return cfg


@contextmanager
def raices_temporales(prefijo: str = "v2-prueba-"):
    """RutasV2 en una carpeta temporal (raíz v2, v1, datos y un repositorio vacío)."""
    with tempfile.TemporaryDirectory(prefix=prefijo) as tmp:
        base = Path(tmp).resolve()
        scripts = base / "repo" / "scripts_modelo_1km" / "v2"
        scripts.mkdir(parents=True)
        (base / "v1").mkdir()
        (base / "datos").mkdir()
        yield rv.RutasV2(raiz_v2=base / "v2", raiz_v1=base / "v1", datos=base / "datos", repo=base / "repo",
                         scripts_v2=scripts)
