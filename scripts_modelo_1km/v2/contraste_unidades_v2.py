#!/usr/bin/env python3
"""Contraste de los rótulos de unidad SINCA contra CAMS, versionado para la segunda corrida (bloque R6).

Es el programa ``contraste_unidades_cams.py`` del repositorio de salud (sha256 82637d7b…, primera corrida
``contraste_unidades_cams.csv``, ca0805ae…), con **las mismas reglas**, escritas como funciones puras y probadas con
series sintéticas. Las reglas se fijaron antes de calcular (2026-10-25):

* estadístico de la v1 (``_red_adicional.py:17-23``): razón = media de la observación / media de CAMS en las horas
  emparejadas, en el píxel CAMS más cercano; CAMS en ppb (CO en ppm) desde la fracción de masa del nivel 60 con la
  masa molar del aire (28,9647); observación finita y ≥ 0, sin el 0,1 % superior de cada serie; ≥ 500 pares;
* emparejamiento: inicio UTC de la hora SINCA = etiqueta local + 3 h (UTC−4 fijo, etiqueta al fin), igual al
  instante CAMS (cada 3 h);
* referencia de red: las series del mismo gas rotuladas en la unidad de referencia (ppb; CO, ppm) con ≥ 500 pares;
  centro m = mediana de log(razón), dispersión s = 1,4826 × MAD;
* candidatos a 25 °C y 1 atm (24,4654 L/mol): NO2, O3 y SO2 ppb y µg/m³N; CO ppm, mg/m³N, ppb y µg/m³N;
  z_u = (log razón − log f_u − m) / s;
* decisión: el candidato b de menor |z|; indeterminado si |z_b| > 3; competidores, los candidatos cuyo factor difiere
  del de b en más de 1,5 veces; razón de verosimilitud LR = exp((z_k² − z_b²)/2) con el competidor más cercano; decide
  b si LR ≥ 20;
* indicio de vecina (no decide): la serie de referencia del mismo gas más cercana a ≤ 10 km con ≥ 500 horas comunes.

**Segunda corrida** (R6 y R22, paso 3): con el derivado de la red 2 cerrado (las 107 con su actualización y las nuevas,
``derivado_red2_v2``, completo) y **antes** de armar el panel, para que rija sobre él: es la lectura (a) de T12
([delegada]) de «al cerrar el panel» (R6) y de R22, paso 3. Va con las coordenadas de los dos maestros de R8 (las
nuevas con el maestro corregido), sobre NO2 y O3, los gases que trae el derivado de la red 2. R6 dice que rige la
segunda corrida, así que el armado (``panel_red2_v2.ejecutar``) la exige con ``--contraste`` (orden en
``red_de_monitores.orden`` de la configuración: derivado, reloj, segunda corrida, registro MAIAC y panel). Nada se lee antes de que la traducción esté confirmada en
git (R22, paso 2). La salida (CSV con las mismas columnas que la primera corrida y un JSON con su sha256) va a
``<raíz v2>/unidades_red2/`` y se escribe una sola vez; R6: «si una serie cambia de decisión, rige la segunda corrida
y el cambio se registra», así que para escribir la primera corrida es obligatoria (``--primera``, comprobada por su
huella, ca0805ae…) y los cambios (``cambios_frente_a``, aunque no haya ninguno) quedan en el lateral, con los archivos
CAMS leídos, cada uno con su sha256 (``exigir_cams``), y la procedencia de la corrida (``red_ampliada_v2.traza_red2``:
commit, huella del código, bibliotecas, hilos y la traducción con que se escribió).

Uso (en el armado; lee CAMS y los valores de las series, nunca métricas de modelo)::

    python -B scripts_modelo_1km/v2/contraste_unidades_v2.py --derivado <raíz red 2> --primera <csv de la 1.ª corrida>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import unidades_v2 as uv  # noqa: E402

SCHEMA = "airpollution.modelo-1km-v2.contraste-unidades.v1"
PROGRAMA_ORIGINAL = {"archivo": "auditoria/20261024/sinca_al_modelo/contraste_unidades_cams.py (repositorio de salud)",
                     "sha256": "82637d7b6b7dab2228eb34caa4efa28ef413a2728fdb0af6af0c0771429108e9"}
GASES = ("no2", "o3", "so2", "co")
# Las masas molares: las de la conversión de R6 (unidades_v2.MASA_MOLAR), las literales del bloque. T12 (corrección,
# [delegada]) fija O3 en 47,998 g/mol, la literal de R6, sin excepción para el contraste: es la única diferencia con el
# programa de la primera corrida (contraste_unidades_cams.py:39, O3 47,9982; diferencia relativa de unos 4·10⁻⁶), y
# MismoProgramaTests la acepta sólo a ella. NO2, SO2 y CO son las del programa original.
M = {"no2": 46.0055, "o3": 47.998, "so2": 64.064, "co": 28.0101}
M_AIRE = 28.9647
VM25 = uv.VM_25C_L_MOL
CANDIDATOS = {g: {"ppb": 1.0, "µg/m³N": M[g] / VM25} for g in ("no2", "o3", "so2")}
CANDIDATOS["co"] = {"ppm": 1.0, "mg/m³N": M["co"] / VM25, "ppb": 1000.0, "µg/m³N": 1000.0 * M["co"] / VM25}
REF = dict(uv.REFERENCIA)
MIN_PARES = 500
LR_MIN = 20.0
Z_MAX = 3.0
DIST_VECINA_KM = 10.0
CUANTIL_RECORTE = 0.999
DESPLAZAMIENTO_H = 3
COLUMNAS = ["serie", "estacion", "nombre", "region", "contaminante", "grupo", "rotulo", "unidad_que_indica",
            "estadistico", "decision", "razon_obs_cams", "pares_cams", "z_por_unidad", "razon_verosimilitud",
            "razon_anual_min", "razon_anual_max", "pixel_cams_dist_km", "horas_obs", "vecina_ref", "vecina_km",
            "vecina_horas", "razon_vecina"]


def hv(a1, o1, a2, o2):
    a1, o1, a2, o2 = map(np.radians, (a1, o1, a2, o2))
    d = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(d))


def preparar_serie(etiquetas_locales, valores) -> pd.Series:
    """Serie en inicio UTC de la hora (etiqueta + 3 h), finita y ≥ 0, sin etiquetas repetidas (la primera)."""
    s = pd.Series(np.asarray(valores, dtype="float64"), index=pd.DatetimeIndex(pd.to_datetime(etiquetas_locales)))
    s = s[np.isfinite(s.to_numpy()) & (s.to_numpy() >= 0)]
    s.index = s.index + pd.Timedelta(hours=DESPLAZAMIENTO_H)
    return s[~s.index.duplicated(keep="first")]


def razon(serie: pd.Series, cams_t: pd.DatetimeIndex, cams_v: np.ndarray | None) -> tuple:
    """(razón, pares, razón anual mínima, razón anual máxima) de una serie contra la columna CAMS de su píxel."""
    if cams_v is None:
        return np.nan, 0, np.nan, np.nan
    comun = serie.index.intersection(cams_t)
    if len(comun) == 0:
        return np.nan, 0, np.nan, np.nan
    o = serie.loc[comun].to_numpy()
    c = np.asarray(cams_v)[cams_t.get_indexer(comun)]
    ok = np.isfinite(o) & np.isfinite(c)
    o, c, tt = o[ok], c[ok], comun[ok]
    if len(o) == 0:
        return np.nan, 0, np.nan, np.nan
    tope = np.quantile(o, CUANTIL_RECORTE)
    keep = o <= tope
    o, c, tt = o[keep], c[keep], tt[keep]
    if len(o) < MIN_PARES or c.mean() <= 0:
        return (o.mean() / c.mean() if len(o) and c.mean() > 0 else np.nan), int(len(o)), np.nan, np.nan
    anual = pd.DataFrame({"o": o, "c": c, "a": tt.year}).groupby("a").agg(o=("o", "mean"), c=("c", "mean"),
                                                                         n=("o", "size"))
    anual = anual[anual.n >= 200]
    ra = (anual.o / anual.c) if len(anual) else pd.Series(dtype=float)
    return (float(o.mean() / c.mean()), int(len(o)), (float(ra.min()) if len(ra) else np.nan),
            (float(ra.max()) if len(ra) else np.nan))


def referencia(series: list[dict], gas: str) -> tuple[float, float, int]:
    """Centro y dispersión del log de la razón de las series de referencia del gas (≥ 500 pares)."""
    x = np.log([s["razon"] for s in series if s["gas"] == gas and s["rotulo"] == REF[gas]
                and s["pares"] >= MIN_PARES and np.isfinite(s["razon"]) and s["razon"] > 0])
    if len(x) == 0:
        return float("nan"), float("nan"), 0
    m = float(np.median(x))
    return m, float(1.4826 * np.median(np.abs(x - m))), int(len(x))


def decidir(s: dict, ref: tuple[float, float, int]) -> dict:
    """Unidad que indica el contraste para una serie (regla del programa original, sin cambios)."""
    g = s["gas"]
    m, sd, _ = ref
    out = {"z": {}, "unidad_indicada": "", "lr": np.nan, "motivo": ""}
    if s.get("pixel") is None:
        out["motivo"] = "sin coordenadas usables: no hay píxel CAMS"
        return out
    if s["pares"] < MIN_PARES or not np.isfinite(s["razon"]) or s["razon"] <= 0:
        out["motivo"] = (f"menos de {MIN_PARES} pares con CAMS ({s['pares']}); CAMS en disco cubre 2003-2025"
                         if s["pares"] < MIN_PARES else "razón no calculable")
        return out
    if not (np.isfinite(m) and np.isfinite(sd) and sd > 0):
        out["motivo"] = "sin referencia de red utilizable"
        return out
    x = math.log(s["razon"])
    z = {u: (x - math.log(f) - m) / sd for u, f in CANDIDATOS[g].items()}
    out["z"] = z
    b = min(z, key=lambda u: abs(z[u]))
    fb = CANDIDATOS[g][b]
    iguales = [u for u, f in CANDIDATOS[g].items() if max(f, fb) / min(f, fb) <= 1.5]
    comp = [u for u in CANDIDATOS[g] if u not in iguales]
    if abs(z[b]) > Z_MAX:
        out["motivo"] = f"ninguna escala compatible (|z| mínimo {abs(z[b]):.2f} > {Z_MAX})"
        return out
    k = min(comp, key=lambda u: z[u] ** 2)
    exponente = (z[k] ** 2 - z[b] ** 2) / 2
    lr = math.exp(exponente) if exponente < 700 else math.inf     # el original desbordaría; decide igual (LR ≥ 20)
    out["lr"] = lr
    if lr < LR_MIN:
        out["motivo"] = f"no distingue {b} de {k} (razón de verosimilitud {lr:.1f} < {LR_MIN:g})"
        return out
    out["unidad_indicada"] = " o ".join(iguales) if len(iguales) > 1 else b
    out["motivo"] = f"{out['unidad_indicada']} frente a {k}: razón de verosimilitud {lr:.3g}"
    return out


def decision_textual(rotulo: str, gas: str, indicada: str) -> str:
    """Texto de la columna ``decision`` (el del programa original; la regla I de unidades_v2 lo reinterpreta)."""
    if rotulo == REF[gas]:
        return "referencia (rótulo de referencia; no se decide)"
    if not indicada:
        return "fuera: unidad indeterminada"
    posibles = indicada.split(" o ")
    if rotulo in posibles and len(posibles) == 1:
        return "rótulo confirmado" + (": convertir a ppb a 25 °C" if rotulo == "µg/m³N" else
                                      (": convertir a ppm" if rotulo in ("mg/m³N", "ppb") and gas == "co" else ""))
    if rotulo in posibles:
        return f"rótulo compatible (no se distingue de {', '.join(p for p in posibles if p != rotulo)})"
    if rotulo == uv.SIN_UNIDAD and len(posibles) == 1:
        return f"entra en {posibles[0]}" + (" (convertir)" if posibles[0] not in ("ppb",) and gas != "co" else "")
    if rotulo == uv.SIN_UNIDAD:
        return f"fuera: escala conocida pero unidad no distinguible ({indicada})"
    return f"rótulo contradicho: los valores vienen en {indicada}"


def pixel_mas_cercano(lat, lon, plat, plon) -> tuple[int | None, float]:
    if not (np.isfinite(lat) and np.isfinite(lon)) or (lat == 0 and lon == 0):
        return None, float("nan")
    d = hv(lat, lon, plat, plon)
    k = int(np.argmin(d))
    return k, float(d[k])


def vecina(s: dict, i: int, series: list[dict], obs: dict[int, pd.Series]) -> tuple:
    """Indicio de vecina: (código, km, horas, razón de medias) de la referencia más cercana a ≤ 10 km."""
    g = s["gas"]
    if s["rotulo"] == REF[g] or not np.isfinite(s["lat"]) or (s["lat"] == 0 and s["lon"] == 0):
        return "", "", "", ""
    mejor = None
    for j, t in enumerate(series):
        if t["gas"] != g or t["rotulo"] != REF[g] or t["estacion"] == s["estacion"] or not np.isfinite(t["lat"]):
            continue
        dkm = float(hv(s["lat"], s["lon"], t["lat"], t["lon"]))
        if dkm > DIST_VECINA_KM:
            continue
        comun = obs[i].index.intersection(obs[j].index)
        if len(comun) < MIN_PARES:
            continue
        a, b = obs[i].loc[comun].to_numpy(), obs[j].loc[comun].to_numpy()
        ok = (a <= np.quantile(a, CUANTIL_RECORTE)) & (b <= np.quantile(b, CUANTIL_RECORTE))
        if b[ok].mean() <= 0:
            continue
        cand = (dkm, t["estacion"], int(ok.sum()), float(a[ok].mean() / b[ok].mean()))
        if mejor is None or cand[0] < mejor[0]:
            mejor = cand
    if mejor is None:
        return "", "", "", ""
    return mejor[1], round(mejor[0], 2), mejor[2], round(mejor[3], 3)


def asignar_pixeles(series: list[dict], plat: np.ndarray, plon: np.ndarray) -> list[int]:
    """Píxel CAMS más cercano de cada serie (None sin coordenadas usables); devuelve los píxeles usados, ordenados."""
    for s in series:
        s["pixel"], s["dist_pixel_km"] = pixel_mas_cercano(s["lat"], s["lon"], plat, plon)
    return sorted({s["pixel"] for s in series if s["pixel"] is not None})


def contrastar(series: list[dict], obs: dict[int, pd.Series], cams_t: pd.DatetimeIndex,
               cams: dict[str, np.ndarray], col: dict[int, int]) -> tuple[pd.DataFrame, dict]:
    """El contraste completo. ``series``: dicts con ``estacion``, ``gas``, ``grupo``, ``rotulo``, ``lat``, ``lon``,
    ``nombre``, ``region`` y el ``pixel`` de ``asignar_pixeles``; ``obs[i]``: la serie i ya preparada
    (``preparar_serie``); ``cams[gas]``: matriz tiempo × píxel usado en ppb (CO en ppm), con ``col`` = {píxel:
    columna}. Devuelve la tabla y las referencias."""
    for i, s in enumerate(series):
        c = None if s.get("pixel") is None else cams[s["gas"]][:, col[s["pixel"]]]
        s["horas_obs"] = int(len(obs[i]))
        s["razon"], s["pares"], s["razon_anual_min"], s["razon_anual_max"] = razon(obs[i], cams_t, c)
    refs = {g: referencia(series, g) for g in GASES if any(s["gas"] == g for s in series)}
    filas = []
    for i, s in enumerate(series):
        g = s["gas"]
        d = decidir(s, refs[g])
        ind = d["unidad_indicada"]
        vr, vk, vh, vrz = vecina(s, i, series, obs)
        fin = lambda x, n: round(x, n) if np.isfinite(x) else ""  # noqa: E731
        filas.append({"serie": f"{s['estacion']}_{g}", "estacion": s["estacion"], "nombre": s.get("nombre", ""),
                      "region": s.get("region", ""), "contaminante": g, "grupo": s["grupo"], "rotulo": s["rotulo"],
                      "unidad_que_indica": ind or "indeterminada", "estadistico": d["motivo"],
                      "decision": decision_textual(s["rotulo"], g, ind), "razon_obs_cams": fin(s["razon"], 3),
                      "pares_cams": s["pares"], "z_por_unidad": "; ".join(f"{u}={v:+.2f}" for u, v in d["z"].items()),
                      "razon_verosimilitud": fin(d["lr"], 2), "razon_anual_min": fin(s["razon_anual_min"], 3),
                      "razon_anual_max": fin(s["razon_anual_max"], 3),
                      "pixel_cams_dist_km": fin(s["dist_pixel_km"], 1), "horas_obs": s["horas_obs"],
                      "vecina_ref": vr, "vecina_km": vk, "vecina_horas": vh, "razon_vecina": vrz})
    tabla = pd.DataFrame(filas, columns=COLUMNAS).sort_values(["contaminante", "grupo", "rotulo", "estacion"])
    return tabla.reset_index(drop=True), {g: {"centro_log": m, "dispersion_log": sd, "n": n} for g, (m, sd, n) in refs.items()}


def cambios_frente_a(primera: pd.DataFrame, segunda: pd.DataFrame) -> list[dict]:
    """Series cuya ``unidad_que_indica`` cambió entre dos corridas (rige la segunda; R6)."""
    gases = set(segunda["contaminante"])
    a = primera[primera["contaminante"].isin(gases)].set_index(["estacion", "contaminante"])["unidad_que_indica"]
    b = segunda.set_index(["estacion", "contaminante"])["unidad_que_indica"]
    out = []
    for k in sorted(set(a.index) | set(b.index)):
        va, vb = a.get(k, "(ausente)"), b.get(k, "(ausente)")
        if va != vb:
            out.append({"estacion": k[0], "contaminante": k[1], "primera": va, "segunda": vb})
    return out


# ---------------------------------------------------------------------------
# Lectura (en el armado)
# ---------------------------------------------------------------------------
def catalogo_cams(carpeta: Path) -> tuple[np.ndarray, np.ndarray, list[Path]]:
    """Latitud y longitud de los píxeles CAMS y los archivos mensuales en disco."""
    import xarray as xr

    archivos = sorted(Path(carpeta).glob("cams_eac4_*_chile_pixeles.nc"))
    if not archivos:
        raise SystemExit(f"No hay CAMS en {carpeta}")
    with xr.open_dataset(archivos[0]) as d0:
        return d0["latitude"].to_numpy(), d0["longitude"].to_numpy(), archivos


def leer_cams(archivos: list[Path], usados: list[int], gases=GASES) -> tuple[pd.DatetimeIndex, dict, dict]:
    """CAMS EAC4 mensual de los píxeles usados (fracción de masa → ppb; CO → ppm), como el programa original."""
    import xarray as xr

    tiempos, cams = [], {g: [] for g in gases}
    for f in archivos:
        with xr.open_dataset(f) as d:
            tiempos.append(d["time"].to_numpy())
            for g in gases:
                fac = (M_AIRE / M[g]) * (1e6 if g == "co" else 1e9)
                cams[g].append(d[g].isel(pixel=usados).to_numpy().astype("float64") * fac)
    return (pd.DatetimeIndex(np.concatenate(tiempos)), {g: np.concatenate(v, axis=0) for g, v in cams.items()},
            {p: j for j, p in enumerate(usados)})


def series_red2(derivado: list[Path], datos: Path, gases=("no2", "o3"), series_d: list[dict] | None = None,
                huellas: dict | None = None) -> tuple[list[dict], dict[int, pd.Series]]:
    """Series de la segunda corrida desde el derivado de la red 2 (filas ``seleccionada`` con valor), con el rótulo de
    ``unidades_v2.rotulos_de_ficha`` y las coordenadas de los maestros de R8. ``series_d`` y ``huellas``: las series y
    el registro de ``reloj_sinca_v2.series_con_huella`` (``huellas_de``), que ``main`` registra en el lateral: cada serie
    se lee desde los bytes cuyo sha256 es el registrado (``reloj_sinca_v2.leer_serie``; ronda 5 de la traducción, menor
    3); sin ellas, las de ``series_del_derivado``, leídas sin comparar."""
    import red_ampliada_v2 as ra
    import reloj_sinca_v2 as rs

    m = uv.leer_manifiestos(datos)
    rot = uv.rotulos_de_ficha(m["nuevas"], m["actualizacion"], m["otras"], m["actuales"], contaminantes=gases)
    rot = rot.set_index(["estacion", "contaminante"])
    maestro = ra.maestro_red2(datos).set_index("estacion")
    series, obs = [], {}
    for s in (rs.series_del_derivado(derivado, gases) if series_d is None else series_d):
        clave = (s["estacion"], s["contaminante"])
        if clave not in rot.index:
            continue
        d = rs.leer_serie(s, ["ts_local", "obs", "seleccionada"], huellas, "contraste_unidades_v2")
        d = d[d["seleccionada"].astype(bool) & d["obs"].notna()]
        c = maestro.loc[s["estacion"]] if s["estacion"] in maestro.index else None
        obs[len(series)] = preparar_serie(d["ts_local"], d["obs"])
        series.append({"estacion": s["estacion"], "gas": s["contaminante"], "grupo": rot.loc[clave, "grupo"],
                       "rotulo": rot.loc[clave, "rotulo"], "nombre": "" if c is None else str(c["nombre"]),
                       "region": "" if c is None else str(c["region_sinca"]),
                       "lat": float("nan") if c is None else float(c["lat"]),
                       "lon": float("nan") if c is None else float(c["lon"])})
    return series, obs


NOMBRES_SALIDA = ("contraste_unidades_cams_segunda.csv", "contraste_unidades_cams_segunda.json")
GASES_RED2 = ("no2", "o3")             # los gases del derivado de la red 2 (contrato y rama O3)


def exigir_cams(info: dict, quien: str = "la segunda corrida") -> list[dict]:
    """Quinta revisión, menor 7 (mayor 2 de la segunda revisión): el lateral registra los archivos CAMS que leyó la
    corrida, al menos uno, cada uno con su ruta y un sha256 de 64 caracteres hexadecimales; si no, se detiene (la
    corrida se escribe una sola vez: un lateral sin CAMS ya no se podría corregir). Devuelve la lista."""
    import re

    archivos = (info.get("cams") or {}).get("archivos") if isinstance(info.get("cams"), dict) else None
    malos = not isinstance(archivos, list) or not archivos or any(
        not isinstance(a, dict) or not a.get("ruta") or not re.fullmatch(r"[0-9a-f]{64}", str(a.get("sha256") or ""))
        for a in archivos)
    if malos:
        raise SystemExit(f"{quien}: el lateral tiene que registrar los archivos CAMS que leyó, cada uno con su ruta y su "
                         f"sha256 (cams.archivos)")
    return archivos


def exigir_lateral_completo(info: dict) -> None:
    """Lo que la segunda corrida tiene que registrar antes de escribirse (una sola vez): la primera corrida por su
    huella con sus cambios (R6, aunque la lista esté vacía), los archivos CAMS con su sha256 (``exigir_cams``) y las
    series leídas de NO2 y O3."""
    p = info.get("primera_corrida") or {}
    if p.get("sha256") != uv.SHA_CONTRASTE_PRIMERA or not isinstance(p.get("cambios"), list):
        raise SystemExit("la segunda corrida registra los cambios frente a la primera (R6): falta primera_corrida con la "
                         f"huella {uv.SHA_CONTRASTE_PRIMERA[:8]}… y su lista de cambios; corre con --primera")
    exigir_cams(info)
    gases = sorted((info.get("series_leidas") or {}).get("contaminantes") or [])
    if gases != sorted(GASES_RED2):
        raise SystemExit(f"la segunda corrida se escribe con {GASES_RED2}, no con {gases}")


def huellas_cams(archivos: list[Path], datos: Path) -> list[dict]:
    """Los archivos CAMS que lee la corrida, con su ruta relativa a la raíz de datos y su sha256."""
    import reloj_sinca_v2 as rs
    out = []
    for a in archivos:
        a = Path(a)
        rel = a.resolve().relative_to(Path(datos).resolve()).as_posix() if a.resolve().is_relative_to(
            Path(datos).resolve()) else a.name
        out.append({"ruta": rel, "sha256": rs.sha256_archivo(a)})
    return out


def leer_cams_con_huellas(archivos: list[Path], usados: list[int], gases, datos: Path, leer=None
                          ) -> tuple[pd.DatetimeIndex, dict, dict, list[dict]]:
    """``leer_cams`` entre dos huellas de cada archivo, como ``read_source`` del preparador: el sha256 de cada mensual
    antes de leerlo y otra vez después; si alguno cambió, se detiene («CAMS cambió durante la lectura»), porque la
    corrida se escribe una sola vez y el lateral tiene que registrar lo que se leyó. ``leer``, sólo para las pruebas.
    Devuelve lo de ``leer_cams`` y las huellas (``huellas_cams``)."""
    antes = huellas_cams(archivos, datos)
    cams_t, cams, col = (leer or leer_cams)(archivos, usados, gases)
    despues = huellas_cams(archivos, datos)
    cambiados = [a["ruta"] for a, b in zip(antes, despues) if a != b]
    if cambiados or len(antes) != len(despues):
        raise SystemExit(f"CAMS cambió durante la lectura: {cambiados[:5]}; la segunda corrida no se escribe")
    return cams_t, cams, col, antes


def publicar_una_vez(r, tabla: pd.DataFrame, info: dict, cfg=None, estado=None, insumos: dict | None = None
                     ) -> tuple[dict, str]:
    """Publica la segunda corrida en ``<raíz v2>/unidades_red2/`` (CSV y su json lateral) después de exigir la
    traducción confirmada en git (R22) y un lateral completo (``exigir_lateral_completo``). El lateral lleva su
    procedencia (``traza``: ``red_ampliada_v2.traza_red2`` con ``insumos``, que no se compara). Se escribe una sola vez:
    con el mismo CSV y su lateral no toca nada; con otro, se detiene. Si una corrida anterior se cortó entre el CSV y
    el lateral y el CSV es el mismo, escribe el lateral («completado»); si no, se detiene con «corrida incompleta».
    Devuelve (lateral, estado)."""
    import _rutas_v2 as rv
    import red_ampliada_v2 as ra

    compuerta = ra.exigir_traduccion_confirmada(r, cfg, estado)
    exigir_lateral_completo(info)
    info = {**info, "traza": ra.traza_red2(r, compuerta, insumos, None, 1, programa="contraste_unidades_v2")}
    salida = r.raiz_v2 / "unidades_red2"
    destinos = [salida / n for n in NOMBRES_SALIDA]
    texto = tabla.to_csv(index=False, lineterminator="\n")
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    with rv.candado_artefactos(destinos, r):
        previo = rv.leer_json(destinos[1])
        csv_previo = hashlib.sha256(destinos[0].read_bytes()).hexdigest() if destinos[0].exists() else None
        if previo is not None:
            if previo.get("sha256_csv") == sha and csv_previo == sha:
                return previo, "sin_cambios"
            raise SystemExit("la segunda corrida del contraste ya existe con otro contenido: se escribe una sola vez")
        if csv_previo is not None:
            if csv_previo != sha:
                raise SystemExit(f"corrida incompleta: {NOMBRES_SALIDA[0]} existe sin su lateral y con otro contenido; "
                                 f"revisa a mano antes de seguir (se escribe una sola vez)")
            info = {**info, "sha256_csv": sha}
            rv.publicar_json(info, destinos[1], r)
            return info, "completado"
        info = {**info, "sha256_csv": rv.publicar_csv(tabla, destinos[0], r)}
        if info["sha256_csv"] != sha:
            raise RuntimeError("el CSV publicado no es el calculado")
        rv.publicar_json(info, destinos[1], r)
    return info, "escrito"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Segunda corrida del contraste de unidades (R6), con las reglas fijadas.")
    ap.add_argument("--derivado", nargs="+", type=Path, required=True)
    ap.add_argument("--primera", type=Path,
                    help="CSV de la primera corrida (ca0805ae…), para registrar los cambios (R6); obligatoria para "
                         "escribir")
    ap.add_argument("--gases", default=",".join(GASES_RED2),
                    help="no2,o3, los del derivado de la red 2; para escribir, los dos (con --no-escribir, uno basta)")
    ap.add_argument("--no-escribir", action="store_true")
    args = ap.parse_args(argv)
    import _rutas_v2 as rv

    import red_ampliada_v2 as ra
    import reloj_sinca_v2 as rs

    r = rv.rutas_v2()
    ra.exigir_traduccion_confirmada(r)                      # R22, paso 2: antes de leer ningún valor
    gases = tuple(dict.fromkeys(g.strip() for g in args.gases.split(",") if g.strip()))
    if not gases or not set(gases) <= set(GASES_RED2):
        raise SystemExit(f"--gases: el derivado de la red 2 trae {GASES_RED2}, no {gases}")
    if not args.no_escribir and (sorted(gases) != sorted(GASES_RED2) or args.primera is None):
        raise SystemExit(f"para escribir, la segunda corrida va con {GASES_RED2} y con --primera (R6: el cambio de "
                         f"decisión se registra); sin eso, sólo con --no-escribir")
    primera = uv.leer_contraste(args.primera, uv.SHA_CONTRASTE_PRIMERA) if args.primera is not None else None
    ra.verificar_lista_cerrada(r.datos)                     # antes de leer los maestros y las fichas
    if not args.no_escribir:                                # la escritura es única: sólo sobre el derivado completo
        import derivado_red2_v2 as dr
        dr.exigir_derivado_completo(args.derivado, rs.series_del_derivado(args.derivado, rs.CONTAMINANTES_SINCA),
                                    r.datos, "contraste_unidades_v2")
    registro_series, series_leidas = rs.series_con_huella(args.derivado, r.datos, gases)
    series, obs = series_red2(args.derivado, r.datos, gases, series_leidas, rs.huellas_de(registro_series))
    plat, plon, archivos = catalogo_cams(r.datos / "contaminantes" / "CAMS_EAC4" / "chile_nativo_075deg" / "mensual")
    usados = asignar_pixeles(series, plat, plon)
    cams_t, cams, col, huellas = leer_cams_con_huellas(archivos, usados, gases, r.datos)   # antes y después
    tabla, refs = contrastar(series, obs, cams_t, cams, col)
    info = {"schema": SCHEMA, "programa_original": PROGRAMA_ORIGINAL, "referencias": refs, "series": int(len(tabla)),
            "cams": {"desde": str(cams_t.min()), "hasta": str(cams_t.max()), "archivos": huellas},
            "series_leidas": registro_series,
            "lectura": "las series nuevas y las actuales se leen del derivado red 2 (filas «seleccionada» del ranking "
                       "afg), no del CSV crudo como en la primera corrida"}
    if primera is not None:
        info["primera_corrida"] = {"sha256": primera[1], "cambios": cambios_frente_a(primera[0], tabla)}
    print(json.dumps({k: v for k, v in info.items() if k != "referencias"}, ensure_ascii=False)[:2000])
    if args.no_escribir:
        return 0
    _, estado = publicar_una_vez(r, tabla, info, insumos={"primera_corrida": args.primera})
    print(estado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
