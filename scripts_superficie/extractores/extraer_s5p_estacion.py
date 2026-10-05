#!/usr/bin/env python3
"""TROPOMI L2 compacto -> candidatos nativos por estación SINCA.

La salida maestra conserva una fila por pareja estación-píxel, sin promedio
espacial ni temporal. Lee sólo los recortes compactos por AOI publicados por
``descargar_tropomi.py``, exige ``CHILE_SUBSET/toca_chile`` y mantiene el
tiempo UTC nativo de cada scanline. Los resúmenes por pasada y día se escriben
como productos derivados con nombres explícitos; nunca reemplazan al maestro.

Salidas para cada producto::

  s5p_<producto>_estacion_pixeles_nativos.parquet       # maestro
  s5p_<producto>_estacion_pasadas_derivado.parquet      # promedio opcional
  s5p_<producto>_estacion_diario_derivado.parquet       # promedio opcional

Uso:
  python3 extraer_s5p_estacion.py --producto NO2
  python3 extraer_s5p_estacion.py --producto NO2 --prueba 5
  python3 extraer_s5p_estacion.py --producto SO2 --qa 0.5

Las columnas gaseosas nativas (mol/m²) también se expresan como
10^15 moléculas/cm² mediante el factor 6,02214·10^4.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

from comun import (CONT, SALIDA, Checkpoint, anexar_parquet,
                   consolidar_candidatos, haversine_km, leer_estaciones)

VARIABLE = {
    "NO2": "nitrogendioxide_tropospheric_column",
    "SO2": "sulfurdioxide_total_vertical_column",
    "CO": "carbonmonoxide_total_column",
    "O3": "ozone_total_vertical_column",
}
QA_DEFECTO = {"NO2": 0.75, "SO2": 0.5, "CO": 0.5, "O3": 0.5}
MOL_M2_A_1E15_MOLEC_CM2 = 6.02214e4
AOI_IDS = ("continente", "juan_fernandez", "desventuradas",
           "rapa_nui", "sala_y_gomez")


def _tiempo_desde_delta(g, n_scanline: int) -> pd.DatetimeIndex:
    """Convierte delta_time a UTC; respaldo para time_utc ausente/inválido."""
    var = g["delta_time"]
    delta = np.ma.filled(var[0], np.nan).astype(float).ravel()
    if len(delta) != n_scanline:
        raise ValueError("delta_time no coincide con la dimensión scanline")
    unidades = str(var.units)
    if "since" not in unidades.lower():
        raise ValueError(f"unidades delta_time no reconocidas: {unidades!r}")
    unidad, base = unidades.lower().split("since", 1)
    unidad = unidad.strip()
    if unidad.startswith("millisecond"):
        unidad_pd = "ms"
    elif unidad.startswith("microsecond"):
        unidad_pd = "us"
    elif unidad.startswith("nanosecond"):
        unidad_pd = "ns"
    elif unidad.startswith("second"):
        unidad_pd = "s"
    else:
        raise ValueError(f"unidad delta_time no reconocida: {unidad!r}")
    origen = pd.to_datetime(base.strip(), utc=True)
    return pd.DatetimeIndex(origen + pd.to_timedelta(delta, unit=unidad_pd))


def _tiempo_scanline_utc(g, n_scanline: int) -> pd.DatetimeIndex:
    """Lee el ISO UTC nativo y completa valores faltantes con delta_time."""
    directo = None
    if "time_utc" in g.variables:
        crudo = np.asarray(g["time_utc"][0]).astype(str).ravel()
        if len(crudo) == n_scanline:
            directo = pd.DatetimeIndex(
                pd.to_datetime(crudo, errors="coerce", utc=True))
            if not directo.hasnans:
                return directo

    respaldo = _tiempo_desde_delta(g, n_scanline)
    if directo is None:
        return respaldo
    return pd.DatetimeIndex([
        respaldo[i] if pd.isna(valor) else valor
        for i, valor in enumerate(directo)
    ])


def _granule_id(sub, ruta: str) -> str:
    """ID estable entre el legado continental y el recorte compacto."""
    if "granule_id" in sub.ncattrs():
        valor = str(sub.getncattr("granule_id"))
    else:
        valor = Path(ruta).name
        for aoi in AOI_IDS:
            valor = valor.removesuffix(f".{aoi}.chile.nc")
        valor = valor.removesuffix(".nc")
    return valor.removesuffix(".chile")


def procesar_orbita(args):
    """Devuelve cada candidato estación-píxel sin agregarlo."""
    ruta, producto, est_lat, est_lon, est_id, radio_km, qa_min = args
    try:
        with nc.Dataset(ruta) as ds:
            g = ds["PRODUCT"]
            sub = ds["CHILE_SUBSET"]
            lat_2d = np.ma.filled(g["latitude"][0], np.nan).astype(float)
            lon_2d = np.ma.filled(g["longitude"][0], np.nan).astype(float)
            qa_2d = np.ma.filled(g["qa_value"][0], np.nan).astype(float)
            val_2d = np.ma.filled(
                g[VARIABLE[producto]][0], np.nan).astype(float)
            if lat_2d.ndim != 2 or not (
                    lon_2d.shape == qa_2d.shape == val_2d.shape == lat_2d.shape):
                raise ValueError("mallas PRODUCT incompatibles")
            n_scanline, n_ground_pixel = lat_2d.shape
            tiempo_scanline = _tiempo_scanline_utc(g, n_scanline)

            toca_2d = np.asarray(sub["toca_chile"][:], dtype=bool)
            pixel_id_2d = np.asarray(sub["pixel_id"][:], dtype="int64")
            cod_comuna_2d = np.asarray(sub["cod_comuna"][:], dtype="int32")
            centro_2d = np.asarray(
                sub["dentro_chile_centro"][:], dtype=bool)
            if not (toca_2d.shape == pixel_id_2d.shape ==
                    cod_comuna_2d.shape == centro_2d.shape == lat_2d.shape):
                raise ValueError("CHILE_SUBSET no coincide con PRODUCT")

            scanline = np.asarray(
                sub["source_scanline"][:], dtype="int32").ravel()
            ground_pixel = np.asarray(
                sub["source_ground_pixel"][:], dtype="int32").ravel()
            if len(scanline) != n_scanline or len(ground_pixel) != n_ground_pixel:
                raise ValueError("índices fuente no coinciden con la malla")

            granule_id = _granule_id(sub, ruta)
            aoi_id = (str(sub.getncattr("aoi_id"))
                      if "aoi_id" in sub.ncattrs() else "sin_etiqueta")

        lat = lat_2d.ravel()
        lon = lon_2d.ravel()
        qa = qa_2d.ravel()
        valor = val_2d.ravel()
        toca = toca_2d.ravel()
        pixel_id = pixel_id_2d.ravel()
        cod_comuna = cod_comuna_2d.ravel()
        dentro_centro = centro_2d.ravel()
        source_scanline = np.repeat(scanline, n_ground_pixel)
        source_ground_pixel = np.tile(ground_pixel, n_scanline)
        ts_utc = tiempo_scanline.repeat(n_ground_pixel)
    except Exception as exc:  # archivo corrupto, legado o incompleto
        return Path(ruta).name, None, f"{type(exc).__name__}: {exc}"

    ok = (toca & np.isfinite(valor) & np.isfinite(lat) & np.isfinite(lon) &
          np.isfinite(qa) & (qa >= qa_min) & ~pd.isna(ts_utc))
    if not ok.any():
        return Path(ruta).name, pd.DataFrame(), None

    lat = lat[ok]
    lon = lon[ok]
    qa = qa[ok]
    valor = valor[ok]
    pixel_id = pixel_id[ok]
    cod_comuna = cod_comuna[ok]
    dentro_centro = dentro_centro[ok]
    source_scanline = source_scanline[ok]
    source_ground_pixel = source_ground_pixel[ok]
    ts_utc = ts_utc[ok]

    partes = []
    for estacion, est_la, est_lo in zip(est_id, est_lat, est_lon):
        caja = ((np.abs(lat - est_la) < radio_km / 100.0) &
                (np.abs(lon - est_lo) < radio_km / 60.0))
        if not caja.any():
            continue
        indices_caja = np.flatnonzero(caja)
        distancias = haversine_km(
            est_la, est_lo, lat[indices_caja], lon[indices_caja])
        dentro_radio = distancias <= radio_km
        if not dentro_radio.any():
            continue
        indices = indices_caja[dentro_radio]
        distancias = distancias[dentro_radio]
        pids = pixel_id[indices]
        partes.append(pd.DataFrame({
            "estacion": str(estacion),
            "producto": producto,
            "granule_id": granule_id,
            "aoi_id": aoi_id,
            "observation_id": [f"{granule_id}:{int(pid)}" for pid in pids],
            "pixel_id": pids,
            "source_scanline": source_scanline[indices],
            "source_ground_pixel": source_ground_pixel[indices],
            "cod_comuna": cod_comuna[indices],
            "dentro_chile_centro": dentro_centro[indices],
            "toca_chile": True,
            "ts_utc": ts_utc[indices],
            "lat": lat[indices],
            "lon": lon[indices],
            "qa_value": qa[indices],
            "valor_mol_m2": valor[indices],
            "valor_1e15_molec_cm2": (
                valor[indices] * MOL_M2_A_1E15_MOLEC_CM2),
            "distancia_km": distancias,
            "estacion_lat": float(est_la),
            "estacion_lon": float(est_lo),
            "archivo": Path(ruta).name,
        }))
    resultado = (pd.concat(partes, ignore_index=True)
                 if partes else pd.DataFrame())
    return Path(ruta).name, resultado, None


def derivar_pasadas(candidatos: pd.DataFrame) -> pd.DataFrame:
    """Resumen explícitamente derivado; el maestro permanece sin cambios."""
    return (candidatos.groupby(
        ["estacion", "producto", "granule_id", "aoi_id"], as_index=False)
        .agg(ts_utc_inicio=("ts_utc", "min"),
             ts_utc_fin=("ts_utc", "max"),
             ts_utc_media=("ts_utc", "mean"),
             valor_mol_m2_media=("valor_mol_m2", "mean"),
             valor_1e15_molec_cm2_media=("valor_1e15_molec_cm2", "mean"),
             qa_media=("qa_value", "mean"),
             distancia_min_km=("distancia_km", "min"),
             n_pix=("pixel_id", "size")))


def derivar_diario(pasadas: pd.DataFrame) -> pd.DataFrame:
    """Resumen diario opcional calculado desde las pasadas derivadas."""
    datos = pasadas.copy()
    datos["fecha_utc"] = datos["ts_utc_media"].dt.floor("D")
    return (datos.groupby(
        ["estacion", "producto", "fecha_utc"], as_index=False)
        .agg(ts_utc_inicio=("ts_utc_inicio", "min"),
             ts_utc_fin=("ts_utc_fin", "max"),
             valor_mol_m2_media_pasadas=("valor_mol_m2_media", "mean"),
             valor_1e15_molec_cm2_media_pasadas=(
                 "valor_1e15_molec_cm2_media", "mean"),
             qa_media_pasadas=("qa_media", "mean"),
             n_pix=("n_pix", "sum"),
             n_pasadas=("granule_id", "size")))


def _archivos_compactos(carpeta: Path, prueba: int = 0) -> list[Path]:
    """Excluye rectángulos legados durante la migración en curso."""
    archivos = sorted(
        p for p in carpeta.glob("*.nc")
        if any(p.name.endswith(f".{aoi}.chile.nc") for aoi in AOI_IDS)
    )
    return archivos[:prueba] if prueba else archivos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--producto", default="NO2", choices=list(VARIABLE))
    ap.add_argument("--radio", type=float, default=7.0, help="radio en km")
    ap.add_argument("--qa", type=float, default=None)
    ap.add_argument("--procesos", type=int,
                    default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--prueba", type=int, default=0,
                    help="procesar sólo N recortes compactos")
    a = ap.parse_args()
    qa_min = a.qa if a.qa is not None else QA_DEFECTO[a.producto]
    nombre = f"s5p_{a.producto.lower()}_estacion_pixeles_nativos"

    est = leer_estaciones()
    carpeta = CONT / "S5P_TROPOMI" / a.producto / "raw_chile"
    archivos = _archivos_compactos(carpeta, a.prueba)
    ck = Checkpoint(nombre)
    pendientes = ck.falta(archivos)
    print(f"{a.producto}: {len(archivos)} recortes compactos, "
          f"{len(pendientes)} pendientes, {len(est)} estaciones, "
          f"radio {a.radio} km, qa>={qa_min}", flush=True)

    tareas = [(str(f), a.producto, est["lat"].to_numpy(),
               est["lon"].to_numpy(), est["estacion"].to_numpy(),
               a.radio, qa_min) for f in pendientes]
    d_partes = SALIDA / f"_partes_{nombre}"
    parte = len(list(d_partes.glob("*.parquet"))) if d_partes.exists() else 0
    buffer, errores = [], []
    with ProcessPoolExecutor(max_workers=a.procesos) as ex:
        futs = [ex.submit(procesar_orbita, tarea) for tarea in tareas]
        for i, fut in enumerate(as_completed(futs), 1):
            nombre_arch, df, err = fut.result()
            if err:
                errores.append((nombre_arch, err))
            else:
                if len(df):
                    buffer.append(df)
                ck.marcar(nombre_arch)
            if i % 200 == 0 or i == len(futs):
                if buffer:
                    anexar_parquet(
                        pd.concat(buffer, ignore_index=True), nombre, parte)
                    parte += 1
                    buffer = []
                print(f"  {i}/{len(futs)} recortes · errores {len(errores)}",
                      flush=True)
    if errores:
        (SALIDA / f"_errores_{nombre}.txt").write_text(
            "\n".join(f"{n}\t{e}" for n, e in errores), encoding="utf-8")

    candidatos = consolidar_candidatos(nombre)
    if candidatos is None:
        print("sin candidatos nativos")
        return
    pasadas = derivar_pasadas(candidatos)
    diario = derivar_diario(pasadas)
    prefijo = f"s5p_{a.producto.lower()}_estacion"
    pasadas.to_parquet(
        SALIDA / f"{prefijo}_pasadas_derivado.parquet", index=False)
    diario.to_parquet(
        SALIDA / f"{prefijo}_diario_derivado.parquet", index=False)
    print(f"LISTO: {len(candidatos):,} candidatos píxel-estación nativos · "
          f"{len(pasadas):,} pasadas derivadas · {len(diario):,} días "
          f"-> data/procesado_estacion/{nombre}.parquet")


if __name__ == "__main__":
    main()
