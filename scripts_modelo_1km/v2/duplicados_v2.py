"""Series duplicadas de la red ampliada: una copia por hora (bloque R9, decisión P8 por omisión).

Regla: dos códigos a ≤ 2 km (haversine, R = 6.371 km) son la misma serie si tienen el mismo valor en ≥ 95 % de sus
horas comunes, con ≥ 720 horas comunes. Se conserva una sola copia por hora, la del código con más horas, y se registra
el par. Vale para todos los pares (actuales, nuevos y SNIFA) y se calcula antes de cualquier ajuste.

Lectura fijada aquí:

* «mismo valor»: los dos valores del modelo (ya convertidos a su unidad) iguales con una tolerancia relativa de
  1e-6, que sólo absorbe el redondeo binario de un mismo número decimal;
* «horas comunes»: estación × hora UTC con observación en los dos códigos, sobre las observaciones que ya pasaron
  R4 a R8 (lo que entraría al panel);
* un grupo de más de dos códigos (A~B y B~C) se trata como un conglomerado: en cada hora queda la observación del
  código con más horas entre los que la tienen (empate: el código menor en orden lexicográfico); las horas en que sólo
  un código del grupo tiene dato se conservan.

Funciones puras (numpy y pandas).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RADIO_KM = 2.0
COINCIDENCIA = 0.95
MINIMO_HORAS_COMUNES = 720
RTOL = 1e-6
RADIO_TIERRA_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    """Réplica de ``_features.haversine_km`` (``_features.py:330-334``)."""
    a1, a2 = np.radians(lat1), np.radians(lat2)
    da, do = a2 - a1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    x = np.sin(da / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin(do / 2) ** 2
    return 2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(x, 0, 1)))


def orden_de_conservacion(codigos, horas) -> list[str]:
    """R9 y T1(2): el orden en que los códigos de un par o de un grupo duplicado conservan sus horas: primero el de más
    horas; en el empate, el código menor en orden lexicográfico. Es la única regla de desempate: la usan el registro
    (``pares_duplicados.conserva``) y la que quita las copias (``quitar_copias``), así que no pueden diferir."""
    return sorted((str(c) for c in codigos), key=lambda e: (-int(horas.get(e, 0)), e))


def pares_cercanos(coords: pd.DataFrame, radio_km: float = RADIO_KM) -> list[tuple[str, str, float]]:
    """Pares de estaciones (a < b) a ``<= radio_km``."""
    c = coords.drop_duplicates("estacion").sort_values("estacion", kind="stable").reset_index(drop=True)
    est = c["estacion"].astype(str).to_numpy()
    lat, lon = c["lat"].to_numpy(float), c["lon"].to_numpy(float)
    D = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    i, j = np.nonzero(np.triu(D <= radio_km, 1))
    return [(str(est[a]), str(est[b]), float(D[a, b])) for a, b in zip(i, j)]


def pares_duplicados(obs: pd.DataFrame, coords: pd.DataFrame, radio_km: float = RADIO_KM,
                     coincidencia: float = COINCIDENCIA, minimo: int = MINIMO_HORAS_COMUNES,
                     rtol: float = RTOL) -> pd.DataFrame:
    """Pares de códigos que son la misma serie. ``obs``: ``estacion``, ``ts_utc``, ``obs`` (una fila por estación ×
    hora); ``coords``: ``estacion``, ``lat``, ``lon``. Devuelve todos los pares cercanos evaluados, con
    ``duplicado`` y, en los duplicados, el código que conserva sus horas (``conserva``) y el que las cede."""
    horas = obs.groupby("estacion").size()
    filas = []
    por_est = {e: g.set_index("ts_utc")["obs"] for e, g in obs.groupby("estacion", sort=False)}
    for a, b, km in pares_cercanos(coords[coords["estacion"].isin(por_est)], radio_km):
        sa, sb = por_est[a], por_est[b]
        comun = sa.index.intersection(sb.index)
        n = int(len(comun))
        iguales = int(np.isclose(sa.loc[comun].to_numpy(float), sb.loc[comun].to_numpy(float), rtol=rtol,
                                 atol=0.0).sum()) if n else 0
        frac = iguales / n if n else float("nan")
        dup = n >= minimo and frac >= coincidencia
        ha, hb = int(horas[a]), int(horas[b])
        conserva = orden_de_conservacion((a, b), horas)[0] if dup else ""
        filas.append({"a": a, "b": b, "km": round(km, 4), "horas_a": ha, "horas_b": hb, "horas_comunes": n,
                      "horas_iguales": iguales, "fraccion_iguales": frac, "duplicado": bool(dup),
                      "conserva": conserva, "cede": (b if conserva == a else a) if dup else ""})
    return pd.DataFrame(filas, columns=["a", "b", "km", "horas_a", "horas_b", "horas_comunes", "horas_iguales",
                                        "fraccion_iguales", "duplicado", "conserva", "cede"])


def _grupos(pares: pd.DataFrame) -> list[list[str]]:
    """Componentes conexas de los pares duplicados."""
    padre: dict[str, str] = {}

    def raiz(x: str) -> str:
        padre.setdefault(x, x)
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for a, b in zip(pares["a"], pares["b"]):
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)
    grupos: dict[str, list[str]] = {}
    for x in list(padre):
        grupos.setdefault(raiz(x), []).append(x)
    return [sorted(g) for g in sorted(grupos.values(), key=lambda g: sorted(g)[0])]


def quitar_copias(obs: pd.DataFrame, pares: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Deja una copia por hora en cada grupo de códigos duplicados (la del código con más horas). Devuelve las
    observaciones sin las copias y un registro por grupo (filas quitadas por código)."""
    dup = pares[pares["duplicado"]] if len(pares) else pares
    if dup is None or len(dup) == 0:
        return obs.reset_index(drop=True), []
    horas = obs.groupby("estacion").size().to_dict()
    quitar = np.zeros(len(obs), dtype=bool)
    registro = []
    o = obs.reset_index(drop=True)
    for grupo in _grupos(dup):
        rango = orden_de_conservacion(grupo, horas)                 # la misma regla que pares_duplicados.conserva
        prioridad = {e: k for k, e in enumerate(rango)}
        en = o["estacion"].isin(grupo).to_numpy()
        sub = o.loc[en, ["estacion", "ts_utc"]].copy()
        sub["p"] = sub["estacion"].map(prioridad)
        mejor = sub.groupby("ts_utc")["p"].transform("min")
        fuera = (sub["p"] != mejor).to_numpy()
        idx = np.flatnonzero(en)[fuera]
        quitar[idx] = True
        registro.append({"grupo": grupo, "orden_por_horas": rango,
                         "filas_quitadas": {e: int((sub["estacion"].to_numpy()[fuera] == e).sum()) for e in grupo},
                         "pares": dup[dup["a"].isin(grupo)][["a", "b", "km", "horas_comunes",
                                                             "fraccion_iguales"]].to_dict("records")})
    return o.loc[~quitar].reset_index(drop=True), registro
