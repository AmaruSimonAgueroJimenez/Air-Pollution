#!/usr/bin/env python3
"""MAIAC MCD19A2 nativo (1 km) -> pixeles, pasadas y horas por estacion.

Lee exclusivamente el contrato normalizado de ``descargar_maiac_aod.py``:

* ``pixeles_horario/catalogo_pixeles``: geometria nativa estable;
* ``pixeles_horario/catalogo_pasadas``: hora UTC exacta de cada pasada; y
* ``pixeles_horario/observaciones``: AOD/QA por ``pixel_id`` y pasada.

La salida primaria no promedia los pixeles. Cada candidato dentro de
``--radio-km`` conserva ``pixel_id``, coordenadas, distancia, QA y ``ts_utc``
exacto en un conjunto Parquet particionado por dia. A partir de esa tabla se
generan, de forma explicita, dos derivados para el modelo: media por pasada y
media por hora UTC. Por tanto, el redondeo horario nunca reemplaza ni borra la
hora de observacion original.

No usa HDF ni ``raw_chile``; esos archivos son temporales del descargador y se
eliminan despues de validar los Parquet nativos.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from _comun import CONT, PROCESADO, leer_estaciones, progreso, radio_a_cuerda, xyz


BASE = CONT / "MCD19A2.061" / "pixeles_horario"
CATALOGO_PIXELES = BASE / "catalogo_pixeles"
CATALOGO_PASADAS = BASE / "catalogo_pasadas"
OBSERVACIONES = BASE / "observaciones"
PIXELES_ESTACION = PROCESADO / "maiac_aod_estacion_pixeles"

COLUMNAS_CANDIDATOS = [
    "estacion", "ts_utc", "overpass_id", "pixel_id", "satelite",
    "aod055", "qa_raw", "qa_clear", "qa_aod",
    "qa_aceptado_estricto", "qa_aceptado_relajado",
    "distancia_km", "lat", "lon", "cod_comuna", "territorio",
]


def _archivos_recursivos(base: Path, patron: str) -> list[Path]:
    return sorted(base.rglob(patron)) if base.exists() else []


def _fecha_nombre(path: Path) -> str:
    m = re.search(r"(\d{8})", path.name)
    if not m:
        raise ValueError(f"fecha YYYYMMDD ausente en {path.name}")
    return m.group(1)


def _parejas_diarias(prueba: int = 0) -> list[tuple[Path, Path]]:
    obs = {_fecha_nombre(p): p for p in _archivos_recursivos(
        OBSERVACIONES, "maiac_obs_*.parquet"
    )}
    pas = {_fecha_nombre(p): p for p in _archivos_recursivos(
        CATALOGO_PASADAS, "maiac_pasadas_*.parquet"
    )}
    faltan = sorted(set(obs) - set(pas))
    if faltan:
        raise ValueError(
            "observaciones MAIAC sin catalogo de pasadas: " + ", ".join(faltan[:5])
        )
    pares = [(obs[d], pas[d]) for d in sorted(set(obs) & set(pas))]
    return pares[:prueba] if prueba else pares


def _leer_catalogo() -> pd.DataFrame:
    archivos = _archivos_recursivos(CATALOGO_PIXELES, "pixeles.parquet")
    if not archivos:
        raise SystemExit(
            "sin catalogo MAIAC nativo; corre scripts_pipeline/descargar_maiac_aod.py"
        )
    columnas = [
        "pixel_id", "lat", "lon", "cod_comuna", "territorio", "tile",
        "fila", "columna",
    ]
    cat = pd.concat(
        [pd.read_parquet(p, columns=columnas) for p in archivos],
        ignore_index=True,
    )
    if cat["pixel_id"].duplicated().any():
        raise ValueError("pixel_id duplicado en el catalogo MAIAC")
    return cat


def _mapa_estacion_pixel(
    catalogo: pd.DataFrame, estaciones: pd.DataFrame, radio_km: float,
) -> pd.DataFrame:
    """Relacion muchos-a-muchos pixel-estacion sin agregar espacialmente."""
    from scipy.spatial import cKDTree

    arbol = cKDTree(xyz(catalogo["lat"].to_numpy(), catalogo["lon"].to_numpy()))
    vecinos = arbol.query_ball_point(
        xyz(estaciones["lat"].to_numpy(), estaciones["lon"].to_numpy()),
        r=radio_a_cuerda(radio_km),
    )
    partes = []
    for (_, estacion), indices in zip(estaciones.iterrows(), vecinos):
        if not indices:
            # Siempre conserva al menos la celda nativa mas cercana; se marca
            # su distancia real para que el analisis pueda decidir si usarla.
            _, indice = arbol.query(xyz([estacion.lat], [estacion.lon])[0], k=1)
            indices = [int(indice)]
        sub = catalogo.iloc[np.asarray(indices, dtype=int)].copy()
        sub["estacion"] = str(estacion.estacion)
        # La distancia exacta queda por candidato, no solo el radio de busqueda.
        lat1 = np.radians(float(estacion.lat))
        lon1 = np.radians(float(estacion.lon))
        lat2 = np.radians(sub["lat"].to_numpy(float))
        lon2 = np.radians(sub["lon"].to_numpy(float))
        a = (np.sin((lat2 - lat1) / 2) ** 2
             + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
        sub["distancia_km"] = (2 * 6371.0 * np.arcsin(np.sqrt(a))).astype("float32")
        partes.append(sub)
    if not partes:
        raise ValueError("ninguna estacion pudo enlazarse al catalogo MAIAC")
    out = pd.concat(partes, ignore_index=True)
    out["pixel_id"] = out["pixel_id"].astype("uint32")
    return out


def _salida_dia(fecha: str) -> Path:
    y, m, d = fecha[:4], fecha[4:6], fecha[6:]
    return (PIXELES_ESTACION / f"year={y}" / f"month={m}" / f"day={d}"
            / f"maiac_estacion_pixeles_{fecha}.parquet")


def _publicar_atomico(df: pd.DataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".part")
    parcial.unlink(missing_ok=True)
    df.to_parquet(parcial, index=False, compression="zstd")
    # Relectura minima: evita publicar un derivado truncado.
    comprobacion = pd.read_parquet(
        parcial, columns=["estacion", "overpass_id", "pixel_id", "ts_utc"]
    )
    if len(comprobacion) != len(df):
        parcial.unlink(missing_ok=True)
        raise ValueError(f"relectura incompleta de {parcial.name}")
    parcial.replace(destino)


def procesar_dia(
    obs_path: Path,
    pasadas_path: Path,
    mapa: pd.DataFrame,
) -> Path:
    fecha = _fecha_nombre(obs_path)
    destino = _salida_dia(fecha)
    if destino.exists():
        return destino

    obs = pd.read_parquet(
        obs_path, columns=["overpass_id", "pixel_id", "aod055", "qa_raw"]
    )
    obs["pixel_id"] = obs["pixel_id"].astype("uint32")
    candidatos = obs.merge(mapa, on="pixel_id", how="inner", validate="many_to_many")
    pasadas = pd.read_parquet(
        pasadas_path, columns=["overpass_id", "ts_utc", "satelite"]
    )
    candidatos = candidatos.merge(
        pasadas, on="overpass_id", how="left", validate="many_to_one"
    )
    if len(candidatos) and candidatos["ts_utc"].isna().any():
        raise ValueError(f"{fecha}: overpass_id sin timestamp")

    qa = candidatos["qa_raw"].astype("uint16")
    candidatos["qa_clear"] = (qa & np.uint16(0b111)).astype("uint8")
    candidatos["qa_aod"] = ((qa >> np.uint16(8)) & np.uint16(0b1111)).astype("uint8")
    candidatos["qa_aceptado_estricto"] = (
        (candidatos["qa_clear"] == 1) & (candidatos["qa_aod"] == 0)
    )
    candidatos["qa_aceptado_relajado"] = (
        (candidatos["qa_clear"] == 1) & (candidatos["qa_aod"] <= 1)
    )
    candidatos["estacion"] = candidatos["estacion"].astype(str)
    candidatos = candidatos[COLUMNAS_CANDIDATOS].sort_values(
        ["ts_utc", "estacion", "distancia_km", "pixel_id"], kind="stable"
    )
    _publicar_atomico(candidatos.reset_index(drop=True), destino)
    return destino


def _resumir(archivos: list[Path], qa_relajado: bool) -> None:
    partes = []
    for path in archivos:
        df = pd.read_parquet(path)
        columna_qa = (
            "qa_aceptado_relajado" if qa_relajado else "qa_aceptado_estricto"
        )
        df = df[df[columna_qa]]
        if df.empty:
            continue
        parte = (df.groupby(
            ["estacion", "overpass_id", "ts_utc", "satelite"], as_index=False,
            sort=False,
        ).agg(
            aod055=("aod055", "mean"),
            aod055_sd=("aod055", "std"),
            n_pix=("pixel_id", "nunique"),
            distancia_media_km=("distancia_km", "mean"),
        ))
        partes.append(parte)
    if not partes:
        print("sin candidatos MAIAC con la QA solicitada", flush=True)
        return

    pasadas = pd.concat(partes, ignore_index=True).drop_duplicates(
        ["estacion", "overpass_id"], keep="last"
    )
    pasadas = pasadas.sort_values(["ts_utc", "estacion"]).reset_index(drop=True)
    pasadas.to_parquet(
        PROCESADO / "maiac_aod_estacion_pasadas.parquet",
        index=False, compression="zstd",
    )

    horario = pasadas.copy()
    horario["ts"] = pd.to_datetime(horario["ts_utc"], utc=True).dt.tz_convert(None).dt.floor("h")
    horario = (horario.groupby(["estacion", "ts"], as_index=False).agg(
        aod_maiac_est=("aod055", "mean"),
        maiac_n_pasadas=("overpass_id", "nunique"),
        maiac_n_pix=("n_pix", "sum"),
        maiac_minuto_utc=("ts_utc", lambda s: float(pd.to_datetime(s).dt.minute.mean())),
    ))
    horario.to_parquet(
        PROCESADO / "maiac_estacion_horario.parquet",
        index=False, compression="zstd",
    )

    diario = pasadas.copy()
    diario["fecha"] = pd.to_datetime(diario["ts_utc"], utc=True).dt.tz_convert(None).dt.floor("D")
    diario = (diario.groupby(["estacion", "fecha"], as_index=False).agg(
        aod_maiac_est=("aod055", "mean"),
        n_pasadas=("overpass_id", "nunique"),
        n_pix=("n_pix", "sum"),
    ))
    diario.to_parquet(
        PROCESADO / "maiac_aod_estacion_diario.parquet",
        index=False, compression="zstd",
    )
    print(
        f"LISTO: {len(pasadas):,} estacion-pasadas; "
        f"{len(horario):,} estacion-horas; {len(diario):,} estacion-dias",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radio-km", type=float, default=3.0)
    ap.add_argument("--qa-relajado", action="store_true")
    ap.add_argument("--procesos", type=int, default=1,
                    help="compatibilidad; la lectura Parquet es secuencial")
    ap.add_argument("--prueba", type=int, default=0, help="solo N dias")
    ap.add_argument("--solo-resumir", action="store_true")
    args = ap.parse_args()
    if args.radio_km <= 0:
        ap.error("--radio-km debe ser positivo")

    pares = _parejas_diarias(args.prueba)
    if not pares:
        raise SystemExit(
            "sin observaciones MAIAC normalizadas; corre descargar_maiac_aod.py"
        )
    if not args.solo_resumir:
        catalogo = _leer_catalogo()
        estaciones = leer_estaciones()
        mapa = _mapa_estacion_pixel(catalogo, estaciones, args.radio_km)
        print(
            f"{len(catalogo):,} pixeles nativos; {len(mapa):,} enlaces "
            f"pixel-estacion; {len(pares):,} dias",
            flush=True,
        )
        for i, (obs, pasadas) in enumerate(pares, 1):
            procesar_dia(obs, pasadas, mapa)
            progreso(i, len(pares), 50, "dias")

    salidas = [_salida_dia(_fecha_nombre(obs)) for obs, _ in pares]
    salidas = [p for p in salidas if p.exists()]
    _resumir(salidas, args.qa_relajado)


if __name__ == "__main__":
    main()
