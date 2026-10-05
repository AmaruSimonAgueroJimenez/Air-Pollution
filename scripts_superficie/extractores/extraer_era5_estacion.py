#!/usr/bin/env python3
"""ERA5-Land (+ BLH de ERA5) mensual → serie horaria por estación.

Combina sin duplicar horas los productos nativos compactos y, solo para meses
que aun no hayan sido reemplazados, los archivos historicos de Chile:

* ``ERA5Land/chile_nativo_01deg/mensual/*_chile_pixeles.nc``: fuente preferida
  (0,1 grados, ``time x pixel``, sin corredor oceanico).
* ``ERA5/chile_nativo_025deg/mensual/*_chile_pixeles.nc``: BLH preferida
  (0,25 grados nativos, sin interpolarla a ERA5-Land).
* ``era5land_YYYYMM_chile.nc`` o ``era5land_YYYYMM.nc``: fallback historico.
* ``era5land_tp_YYYYMM.nc``: precipitación horaria descargada por separado.
* ``era5_pblh_YYYYMM_chile.nc`` o ``era5_blh_YYYYMM.nc``: capa límite.

Acepta tanto ``lat/lon`` y variables mayúsculas (archivos históricos) como
``latitude/longitude`` y variables minúsculas (CDS). Si hay más de un archivo
para un mismo mes, prefiere el que cubre el mes completo; a igualdad de
cobertura prefiere el formato nuevo. ERA5 está en UTC, igual que el panel.

Salida: data/procesado_estacion/era5land_estacion_horario.parquet
        columnas: estacion, ts, era5_t2m (K), era5_d2m (K), era5_rh (%),
        era5_u10, era5_v10 (m/s), era5_sp (Pa), era5_tp (mm/h), era5_blh (m)

La salida es incremental: si ya existe, se conserva por estación-hora todo
valor previo no nulo que no esté disponible en los NetCDF actuales. Los datos
recién extraídos válidos tienen precedencia. Esto permite purgar NetCDF de TP
después de validarlos sin perderlos en ejecuciones futuras del extractor.

Uso:  python extraer_era5_estacion.py
"""
from __future__ import annotations

import calendar
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import CONT, PROCESADO, leer_estaciones, progreso, xyz  # noqa: E402


CLAVES = ["estacion", "ts"]
PREDICTORES = [
    "era5_t2m", "era5_d2m", "era5_rh", "era5_u10", "era5_v10",
    "era5_sp", "era5_tp", "era5_blh",
]

VARS_LAND: dict[str, tuple[str, ...]] = {
    "era5_t2m": ("t2m", "T2M", "2m_temperature"),
    "era5_d2m": ("d2m", "D2M", "2m_dewpoint_temperature"),
    "era5_rh": ("rh2m", "RH2M", "2m_relative_humidity", "relative_humidity"),
    "era5_u10": ("u10", "U10M", "10m_u_component_of_wind"),
    "era5_v10": ("v10", "V10M", "10m_v_component_of_wind"),
    "era5_sp": ("sp", "PS", "surface_pressure"),
    "era5_tp": ("tp", "TP", "total_precipitation"),
}
VARS_TP = {"era5_tp": VARS_LAND["era5_tp"]}
VARS_BLH = {
    "era5_blh": ("blh", "PBLH", "boundary_layer_height"),
}

RE_LAND = re.compile(r"^era5land_(\d{6})(?:_chile)?\.nc$")
RE_TP = re.compile(r"^era5land_tp_(\d{6})(?:_chile)?\.nc$")
RE_BLH = re.compile(r"^era5_(?:pblh|blh)_(\d{6})(?:_chile)?\.nc$")
RE_LAND_NATIVO = re.compile(r"^era5land_(\d{6})_chile_pixeles\.nc$")
RE_BLH_NATIVO = re.compile(r"^era5_blh_(\d{6})_chile_pixeles\.nc$")

_INDICES_GRILLA: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def _coord(ds, candidatos: Iterable[str], tipo: str) -> str:
    for nombre in candidatos:
        if nombre in ds.coords or nombre in ds.dims:
            return nombre
    raise KeyError(f"sin coordenada de {tipo}; hay {list(ds.coords)}")


def _tiempo(ds) -> str:
    return _coord(ds, ("valid_time", "time"), "tiempo")


def _puntos(ds, est, lat: str, lon: str):
    import xarray as xr
    from scipy.spatial import cKDTree

    latitudes = np.asarray(ds[lat].values)
    longitudes = np.asarray(ds[lon].values)
    if latitudes.ndim != 1 or longitudes.ndim != 1:
        raise ValueError("ERA5 requiere coordenadas latitude/longitude 1-D")
    dims_lat = tuple(ds[lat].dims)
    dims_lon = tuple(ds[lon].dims)
    # El contrato nuevo es una grilla irregular compactada como ``time x
    # pixel``: latitude y longitude comparten la dimension pixel. La celda
    # elegida sigue siendo una celda nativa; no se interpola.
    es_compacto = (
        len(dims_lat) == 1 and dims_lat == dims_lon
        and dims_lat[0] in ds.dims
        and dims_lat[0] not in {lat, lon}
    )
    if es_compacto:
        dim_pixel = dims_lat[0]
        referencia = next(
            da for da in ds.data_vars.values() if dim_pixel in da.dims
        )
        for dim in [d for d in referencia.dims if d != dim_pixel]:
            referencia = referencia.notnull().any(dim=dim)
        mascara = np.asarray(referencia.values, dtype=bool)
        validos = np.flatnonzero(
            mascara & np.isfinite(latitudes) & np.isfinite(longitudes)
        )
        if not len(validos):
            raise ValueError("la grilla ERA5 compacta no contiene celdas validas")
        firma = (
            "compacta", dim_pixel, len(latitudes),
            float(np.nanmin(latitudes)), float(np.nanmax(latitudes)),
            float(np.nanmin(longitudes)), float(np.nanmax(longitudes)),
            int(mascara.sum()),
            tuple(np.round(est["lat"].to_numpy(), 6)),
            tuple(np.round(est["lon"].to_numpy(), 6)),
        )
        indices = _INDICES_GRILLA.get(firma)
        if indices is None:
            arbol = cKDTree(xyz(latitudes[validos], longitudes[validos]))
            _, cercanas = arbol.query(
                xyz(est["lat"].to_numpy(), est["lon"].to_numpy())
            )
            elegidos = validos[np.asarray(cercanas, dtype=int)]
            indices = (elegidos, elegidos)
            _INDICES_GRILLA[firma] = indices
        return ds.isel({dim_pixel: xr.DataArray(indices[0], dims="est")})
    # La celda geométricamente más cercana puede ser mar y contener NaN en
    # ERA5-Land (por ejemplo, Arica). La grilla y su máscara terrestre son
    # constantes entre meses, por lo que calculamos una vez la celda válida
    # más cercana y reutilizamos sus índices.
    firma = (
        len(latitudes), float(latitudes[0]), float(latitudes[-1]),
        len(longitudes), float(longitudes[0]), float(longitudes[-1]),
        tuple(np.round(est["lat"].to_numpy(), 6)),
        tuple(np.round(est["lon"].to_numpy(), 6)),
    )
    indices = _INDICES_GRILLA.get(firma)
    if indices is None:
        referencia = next(iter(ds.data_vars.values()))
        for dim in [d for d in referencia.dims if d not in {lat, lon}]:
            referencia = referencia.isel({dim: 0}, drop=True)
        mascara = np.isfinite(referencia.transpose(lat, lon).values)
        ilat, ilon = np.nonzero(mascara)
        if not len(ilat):
            raise ValueError("la grilla ERA5 no contiene ninguna celda válida")
        arbol = cKDTree(xyz(latitudes[ilat], longitudes[ilon]))
        _, cercanas = arbol.query(xyz(est["lat"].to_numpy(), est["lon"].to_numpy()))
        indices = (ilat[cercanas], ilon[cercanas])
        _INDICES_GRILLA[firma] = indices
    return ds.isel(
        {
            lat: xr.DataArray(indices[0], dims="est"),
            lon: xr.DataArray(indices[1], dims="est"),
        }
    )


def _colapsar_dimensiones_extra(da, permitidas: set[str]):
    """Colapsa ``number/expver`` conservando el primer valor no nulo."""
    for dim in [d for d in da.dims if d not in permitidas]:
        if da.sizes[dim] == 1:
            da = da.isel({dim: 0}, drop=True)
            continue
        unida = da.isel({dim: 0}, drop=True)
        for j in range(1, da.sizes[dim]):
            unida = unida.combine_first(da.isel({dim: j}, drop=True))
        da = unida
    return da


def _variable(ds, aliases: Iterable[str]):
    por_minuscula = {nombre.lower(): nombre for nombre in ds.data_vars}
    for alias in aliases:
        original = por_minuscula.get(alias.lower())
        if original is not None:
            return original
    return None


def _tp_a_mm(da):
    """Normaliza precipitación a mm/h (ERA5/ERA5-Land la entrega en m)."""
    unidades = str(da.attrs.get("units", "")).strip().lower()
    if "mm" in unidades or "kg" in unidades:
        return da
    # En CDS la unidad es ``m``. También se aplica cuando el atributo falta
    # para mantener compatibilidad con NetCDF antiguos del mismo producto.
    da = da * 1000.0
    da.attrs["units"] = "mm"
    return da


def extraer_archivo(
    archivo: Path,
    est: pd.DataFrame,
    variables: Mapping[str, tuple[str, ...]],
) -> pd.DataFrame:
    """Extrae un archivo mensual y devuelve como máximo una fila por hora."""
    import xarray as xr

    with xr.open_dataset(archivo) as ds:
        lat = _coord(ds, ("latitude", "lat"), "latitud")
        lon = _coord(ds, ("longitude", "lon"), "longitud")
        tiempo = _tiempo(ds)
        elegidas = {}
        dimensiones_espaciales = set(ds[lat].dims) | set(ds[lon].dims)
        for destino, aliases in variables.items():
            original = _variable(ds, aliases)
            if original is None:
                continue
            da = _colapsar_dimensiones_extra(
                ds[original], {tiempo, lat, lon, *dimensiones_espaciales}
            )
            if destino == "era5_tp":
                da = _tp_a_mm(da)
            elegidas[destino] = da
        if not elegidas:
            raise KeyError(
                f"{archivo.name}: no contiene ninguna variable esperada; "
                f"hay {list(ds.data_vars)}"
            )
        compacto = xr.Dataset(elegidas)
        # En los NetCDF ``time x pixel``, latitude/longitude son coordenadas
        # auxiliares del pixel y xarray no siempre las propaga al reconstruir
        # un Dataset sólo desde variables científicas.
        for coordenada in (lat, lon):
            if coordenada not in compacto and coordenada in ds:
                compacto = compacto.assign_coords({coordenada: ds[coordenada]})
        sub = _puntos(compacto, est, lat, lon)
        df = sub.to_dataframe().reset_index()

    df = df.rename(columns={tiempo: "ts"})
    if "est" not in df:
        raise KeyError(f"{archivo.name}: la selección no conservó el índice de estación")
    indices = pd.to_numeric(df["est"], errors="raise").astype(int).to_numpy()
    df["estacion"] = est["estacion"].to_numpy()[indices]
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=True).dt.tz_convert(None)
    df["ts"] = df["ts"].dt.floor("h")
    valores = [col for col in variables if col in df]
    df = df.dropna(subset=["ts"])
    # ``first`` combina de manera segura posibles pares de expver sin crear
    # dos observaciones para una misma estación-hora.
    return (
        df[CLAVES + valores]
        .groupby(CLAVES, as_index=False, sort=False)[valores]
        .first()
    )


def _horas_archivo(archivo: Path) -> int:
    import xarray as xr

    with xr.open_dataset(archivo) as ds:
        tiempo = _tiempo(ds)
        valores = np.asarray(ds[tiempo].values).reshape(-1)
    try:
        horas = pd.to_datetime(valores, errors="coerce", utc=True).floor("h")
        return int(horas.dropna().nunique())
    except Exception:
        return int(len(valores))


def _horas_esperadas(mes: pd.Period) -> int:
    return calendar.monthrange(mes.year, mes.month)[1] * 24


def _es_nuevo(archivo: Path, familia: str) -> bool:
    if archivo.name.endswith("_chile_pixeles.nc"):
        return True
    if familia in {"land", "tp"}:
        return "_chile" not in archivo.stem
    return archivo.name.startswith("era5_blh_") and "_chile" not in archivo.stem


def preferir_nativo(
    legado: Mapping[pd.Period, Path], nativo: Mapping[pd.Period, Path],
) -> dict[pd.Period, Path]:
    """Superpone por mes el producto nativo; el legado solo llena brechas."""
    return {**dict(legado), **dict(nativo)}


def descubrir_mensuales(
    directorio: Path,
    patron: re.Pattern[str],
    familia: str,
) -> dict[pd.Period, Path]:
    """Elige por mes el archivo con mejor cobertura y luego el más nuevo."""
    candidatos: dict[pd.Period, list[Path]] = {}
    for archivo in directorio.glob("*.nc"):
        coincidencia = patron.match(archivo.name)
        if coincidencia:
            mes = pd.Period(coincidencia.group(1), freq="M")
            candidatos.setdefault(mes, []).append(archivo)

    elegidos: dict[pd.Period, Path] = {}
    for mes, opciones in candidatos.items():
        evaluadas = []
        for archivo in opciones:
            try:
                horas = _horas_archivo(archivo)
            except Exception as exc:
                print(f"  se omite {archivo.name}: no se puede leer ({exc})", flush=True)
                continue
            completa = horas >= _horas_esperadas(mes)
            evaluadas.append(
                ((completa, horas, _es_nuevo(archivo, familia), archivo.stat().st_mtime), archivo)
            )
        if evaluadas:
            evaluadas.sort(key=lambda item: item[0], reverse=True)
            elegidos[mes] = evaluadas[0][1]
            if len(evaluadas) > 1:
                descartados = ", ".join(item[1].name for item in evaluadas[1:])
                print(
                    f"  {mes}: se usa {evaluadas[0][1].name}; se descarta {descartados}",
                    flush=True,
                )
    return elegidos


def combinar_fuentes(fuentes: Iterable[pd.DataFrame]) -> pd.DataFrame | None:
    """Une fuentes; las posteriores reemplazan valores no nulos anteriores."""
    unido = None
    for fuente in fuentes:
        if fuente is None or fuente.empty:
            continue
        actual = fuente.drop_duplicates(CLAVES).set_index(CLAVES)
        unido = actual if unido is None else actual.combine_first(unido)
    if unido is None:
        return None
    return unido.reset_index()


def _completar_mes(out: pd.DataFrame) -> pd.DataFrame:
    if {"era5_t2m", "era5_d2m"}.issubset(out.columns):
        t = out["era5_t2m"] - 273.15
        td = out["era5_d2m"] - 273.15
        a, b = 17.625, 243.04
        calculada = (
            100 * np.exp(a * td / (b + td)) / np.exp(a * t / (b + t))
        ).clip(0, 100)
        if "era5_rh" in out:
            out["era5_rh"] = out["era5_rh"].fillna(calculada)
        else:
            out["era5_rh"] = calculada

    for columna in PREDICTORES:
        if columna not in out:
            out[columna] = np.nan
        out[columna] = pd.to_numeric(out[columna], errors="coerce").astype("float32")
    out = out.dropna(subset=PREDICTORES, how="all")
    out["estacion"] = out["estacion"].astype(str)
    out["ts"] = pd.to_datetime(out["ts"]).dt.floor("h")
    out = out.drop_duplicates(CLAVES, keep="last")
    return out[CLAVES + PREDICTORES].sort_values(CLAVES).reset_index(drop=True)


def procesar_mes(
    mes: pd.Period,
    est: pd.DataFrame,
    land: Mapping[pd.Period, Path],
    tp: Mapping[pd.Period, Path],
    blh: Mapping[pd.Period, Path],
) -> pd.DataFrame | None:
    fuentes = []
    if mes in land:
        land_mes = extraer_archivo(land[mes], est, VARS_LAND)
    else:
        land_mes = None
    if mes in tp:
        tp_mes = extraer_archivo(tp[mes], est, VARS_TP)
    else:
        tp_mes = None
    if land_mes is not None and land[mes].name.endswith("_chile_pixeles.nc"):
        # El NetCDF nativo ya contiene TP validada y tiene precedencia. Una TP
        # historica solo puede completar nulos, nunca reemplazarla.
        fuentes.extend([tp_mes, land_mes])
    else:
        # En el formato historico, la descarga especifica de TP era la fuente
        # mas reciente y por eso conserva precedencia.
        fuentes.extend([land_mes, tp_mes])
    if mes in blh:
        fuentes.append(extraer_archivo(blh[mes], est, VARS_BLH))
    out = combinar_fuentes(fuentes)
    return _completar_mes(out) if out is not None else None


def meses_en_parquet(ruta: Path) -> set[pd.Period]:
    """Descubre meses previos usando estadísticas de row groups cuando existen."""
    if not ruta.exists() or ruta.stat().st_size == 0:
        return set()
    import pyarrow.parquet as pq

    archivo = pq.ParquetFile(ruta)
    if "ts" not in archivo.schema_arrow.names:
        raise KeyError(f"{ruta.name}: el parquet previo no contiene ts")
    indice_ts = archivo.schema_arrow.names.index("ts")
    meses: set[pd.Period] = set()
    for i in range(archivo.metadata.num_row_groups):
        columna = archivo.metadata.row_group(i).column(indice_ts)
        estadisticas = columna.statistics
        if estadisticas is not None and estadisticas.has_min_max:
            valores = [estadisticas.min, estadisticas.max]
        else:
            tabla = archivo.read_row_group(i, columns=["ts"])
            valores = tabla.column("ts").to_pylist()
        tiempos = pd.to_datetime(valores, errors="coerce", utc=True)
        tiempos = pd.DatetimeIndex(tiempos).dropna().tz_convert(None)
        if not len(tiempos):
            continue
        primero = tiempos.min().to_period("M")
        ultimo = tiempos.max().to_period("M")
        meses.update(pd.period_range(primero, ultimo, freq="M"))
    return meses


def leer_mes_previo(ruta: Path, mes: pd.Period) -> pd.DataFrame | None:
    """Lee sólo el row-group/rango mensual pertinente del parquet permanente."""
    if not ruta.exists() or ruta.stat().st_size == 0:
        return None
    import pyarrow.parquet as pq

    disponibles = set(pq.ParquetFile(ruta).schema_arrow.names)
    columnas = [col for col in CLAVES + PREDICTORES if col in disponibles]
    if not set(CLAVES).issubset(columnas):
        raise KeyError(f"{ruta.name}: faltan claves {CLAVES} en el parquet previo")
    inicio = pd.Timestamp(mes.start_time)
    fin = inicio + pd.offsets.MonthBegin(1)
    previo = pd.read_parquet(
        ruta,
        columns=columnas,
        filters=[("ts", ">=", inicio), ("ts", "<", fin)],
    )
    if previo.empty:
        return None
    previo["estacion"] = previo["estacion"].astype(str)
    previo["ts"] = pd.to_datetime(
        previo["ts"], errors="coerce", utc=True
    ).dt.tz_convert(None).dt.floor("h")
    previo = previo[previo["ts"].between(inicio, fin, inclusive="left")]
    if previo.empty:
        return None
    return _completar_mes(previo)


def main():
    import pyarrow as pa
    import pyarrow.parquet as pq

    est = leer_estaciones()
    land_legado = descubrir_mensuales(
        CONT / "ERA5Land" / "raw_chile", RE_LAND, "land"
    )
    land_nativo = descubrir_mensuales(
        CONT / "ERA5Land" / "chile_nativo_01deg" / "mensual",
        RE_LAND_NATIVO, "land",
    )
    land = preferir_nativo(land_legado, land_nativo)
    tp = descubrir_mensuales(CONT / "ERA5Land" / "raw_chile", RE_TP, "tp")
    blh_legado = descubrir_mensuales(
        CONT / "ERA5" / "raw_chile", RE_BLH, "blh"
    )
    blh_nativo = descubrir_mensuales(
        CONT / "ERA5" / "chile_nativo_025deg" / "mensual",
        RE_BLH_NATIVO, "blh",
    )
    blh = preferir_nativo(blh_legado, blh_nativo)
    destino = PROCESADO / "era5land_estacion_horario.parquet"
    meses_previos = meses_en_parquet(destino)
    meses = sorted(set(land) | set(tp) | set(blh) | meses_previos)
    print(
        f"{len(land_nativo)}/{len(land)} meses ERA5-Land nativos/totales · "
        f"{len(tp)} meses TP separada · "
        f"{len(blh_nativo)}/{len(blh)} meses BLH nativos/totales · "
        f"{len(meses_previos)} meses preservados · "
        f"{len(est)} estaciones",
        flush=True,
    )
    if not meses:
        raise SystemExit("sin archivos ERA5; corre descargar_era5land.py")

    parcial = destino.with_name(f"{destino.stem}.part{destino.suffix}")
    parcial.unlink(missing_ok=True)
    escritor = None
    filas = 0
    estaciones: set[str] = set()
    try:
        for i, mes in enumerate(meses, 1):
            previo = leer_mes_previo(destino, mes) if mes in meses_previos else None
            nuevo = procesar_mes(mes, est, land, tp, blh)
            combinado = combinar_fuentes([previo, nuevo])
            parte = _completar_mes(combinado) if combinado is not None else None
            if parte is not None and not parte.empty:
                tabla = pa.Table.from_pandas(parte, preserve_index=False)
                if escritor is None:
                    escritor = pq.ParquetWriter(parcial, tabla.schema, compression="zstd")
                else:
                    tabla = tabla.cast(escritor.schema)
                escritor.write_table(tabla)
                filas += len(parte)
                estaciones.update(parte["estacion"].unique())
            progreso(i, len(meses), 12, "meses")
        if escritor is None:
            raise RuntimeError("los archivos ERA5 no contienen observaciones extraíbles")
        escritor.close()
        escritor = None
        parcial.replace(destino)
    except BaseException:
        if escritor is not None:
            escritor.close()
        parcial.unlink(missing_ok=True)
        raise
    print(f"→ {destino}  ({filas:,} filas, {len(estaciones)} estaciones)")


if __name__ == "__main__":
    main()
