#!/usr/bin/env python3
"""CAMS EAC4 nativo (0,75 grados, 3-h) para Chile administrativo completo.

Descarga por mes y por AOI las variables de superficie PM2.5/PM10 y los gases
CO/NO2/O3/SO2 del nivel de modelo 60. Publica un NetCDF mensual ``time x
pixel`` sin remuestreo ni interpolacion, con catalogo nativo y enlaces
muchos-a-muchos a comuna. Los rectangulos ADS son staging: se borran solo tras
validar/reabrir/hash-validar el mes final. Los archivos anuales continentales
historicos se reutilizan como una fuente, pero no se eliminan hasta que los 12
meses de su ano tengan reemplazo completo validado.

EAC4 comienza en 2003 y su cadencia nativa es 00/03/06/.../21 UTC; nunca se
fabrica una serie horaria.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONTAMINANTES, ensure_dir, get_logger, require_env, retry  # noqa: E402
from _chile_aoi import derivar  # noqa: E402
from normalizar_reanalisis_chile import (  # noqa: E402
    COMUNAS,
    PRODUCTOS,
    _json_atomico,
    eliminar_fuentes_validadas,
    exigir_espacio,
    normalizar_mes,
    salida_vigente,
    sha256_archivo,
)


log = get_logger("cams_eac4")
SPEC = PRODUCTOS["cams_eac4"]
DATASET = "cams-global-reanalysis-eac4"
STAGING = SPEC.salida / "_staging_descarga"
LEGADO = CONTAMINANTES / "CAMS_EAC4" / "raw_chile"
HORAS = ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
VARS_PM = ["particulate_matter_2.5um", "particulate_matter_10um"]
VARS_GAS = ["carbon_monoxide", "nitrogen_dioxide", "ozone", "sulphur_dioxide"]
NIVEL_SUPERFICIE = "60"
# Catalogo ADS consultado el 2026-09-02: cobertura publicada 2003-2025.
# Se puede adelantar sin editar codigo cuando ADS publique un nuevo semestre.
ULTIMO_PUBLICADO = pd.Period(os.environ.get("CAMS_EAC4_ULTIMO_MES", "2025-12"), "M")


def cliente():
    require_env("ADSAPI_URL", "ADSAPI_KEY")
    try:
        import cdsapi
    except ImportError as exc:
        raise SystemExit("Falta cdsapi; instala scripts_pipeline/requirements.txt") from exc
    return cdsapi.Client(url=os.environ["ADSAPI_URL"], key=os.environ["ADSAPI_KEY"])


@retry(n=4, base=10.0)
def _retrieve(c, req, destino: Path):
    c.retrieve(DATASET, req, str(destino))


def _legacy(anio: int) -> list[Path]:
    candidatos = sorted(LEGADO.glob(f"cams_eac4_*_{anio}.nc"))
    etiquetas = {
        "gas" if "_gas_" in p.name else "pm" if "_pm_" in p.name else "otro"
        for p in candidatos
    }
    return candidatos if {"gas", "pm"}.issubset(etiquetas) else []


def _validar_stage(path: Path, periodo: pd.Period, etiqueta: str, aoi_id: str) -> None:
    import numpy as np
    import xarray as xr

    esperadas = {
        "pm": {"pm2p5", "pm10"},
        "gas": {"co", "no2", "go3", "o3", "so2"},
    }
    with xr.open_dataset(path) as ds:
        t = "valid_time" if "valid_time" in ds.coords else "time"
        y = "latitude" if "latitude" in ds.coords else "lat"
        x = "longitude" if "longitude" in ds.coords else "lon"
        tiempos = pd.DatetimeIndex(pd.to_datetime(ds[t].values, utc=True))
        inicio = pd.Timestamp(periodo.start_time, tz="UTC")
        esperado = pd.date_range(inicio, periods=periodo.days_in_month * 8, freq="3h")
        if not tiempos.equals(esperado):
            raise ValueError(f"{path.name}: tiempo EAC4 incompleto/no nativo")
        nombres = {str(v).lower() for v in ds.data_vars}
        if etiqueta == "pm" and not esperadas["pm"].issubset(nombres):
            raise ValueError(f"{path.name}: faltan PM2.5/PM10")
        if etiqueta == "gas" and not {"co", "no2", "so2"}.issubset(nombres):
            raise ValueError(f"{path.name}: faltan gases")
        if etiqueta == "gas" and not ({"go3", "o3"} & nombres):
            raise ValueError(f"{path.name}: falta ozono")
        if not len(ds[y]) or not len(ds[x]):
            raise ValueError(f"{path.name}: AOI vacia")
        primera = next(iter(ds.data_vars.values()))
        if not np.isfinite(np.asarray(primera.isel({t: [0, -1]}))).any():
            raise ValueError(f"{path.name}: sin valores finitos")
        if ds.attrs.get("aoi_id") not in (None, aoi_id):
            raise ValueError(f"{path.name}: aoi_id inconsistente")


def _publicar_stage(c, req: dict, destino: Path, periodo: pd.Period, etiqueta: str, aoi) -> Path:
    import xarray as xr

    if destino.exists():
        _validar_stage(destino, periodo, etiqueta, aoi.id)
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".part")
    tmp.unlink(missing_ok=True)
    try:
        _retrieve(c, req, tmp)
        # ADS no conserva atributos del request; se anota antes de publicar.
        with xr.open_dataset(tmp) as ds:
            cargado = ds.load()
        cargado.attrs.update(
            aoi_id=aoi.id,
            territorio=aoi.territorio,
            dataset=DATASET,
            native_resolution="0.75 degree",
            native_time="3-hourly UTC",
            spatial_operation="temporary native-grid AOI; no resampling",
        )
        reescrito = tmp.with_suffix(tmp.suffix + ".rewrite")
        cargado.to_netcdf(
            reescrito, engine="netcdf4", format="NETCDF4",
            encoding={v: {"zlib": True, "complevel": 4, "shuffle": True} for v in cargado.data_vars},
        )
        os.replace(reescrito, tmp)
        _validar_stage(tmp, periodo, etiqueta, aoi.id)
        with tmp.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, destino)
        _validar_stage(destino, periodo, etiqueta, aoi.id)
    except BaseException:
        tmp.unlink(missing_ok=True)
        tmp.with_suffix(tmp.suffix + ".rewrite").unlink(missing_ok=True)
        raise
    return destino


def _requests(periodo: pd.Period, aoi):
    fecha = f"{periodo.start_time:%Y-%m-%d}/{periodo.end_time:%Y-%m-%d}"
    oeste, sur, este, norte = aoi.bbox
    base = {
        "date": fecha,
        "time": HORAS,
        "area": [norte, oeste, sur, este],
        "data_format": "netcdf",
    }
    return {
        "pm": {**base, "variable": VARS_PM},
        "gas": {**base, "variable": VARS_GAS, "model_level": NIVEL_SUPERFICIE},
    }


def procesar_mes(
    c,
    periodo: pd.Period,
    comunas: Path,
    *,
    espacio_minimo: float,
    dry_run: bool,
) -> None:
    if salida_vigente(SPEC, periodo, comunas, aceptar_parcial=False):
        log.info("%s ya validado", periodo)
        return
    legacy = _legacy(periodo.year)
    # Los dos anuales historicos cubren solo continente; se solicitan solo islas.
    aois = derivar(comunas, margen=max(SPEC.resolucion_lat, SPEC.resolucion_lon) / 2)
    pedidos = tuple(a for a in aois if not legacy or a.id != "continente")
    log.info(
        "%s: %d fuente(s) anual(es) reutilizadas; %d AOIs por solicitar",
        periodo, len(legacy), len(pedidos),
    )
    if dry_run:
        return
    mes_dir = ensure_dir(STAGING / periodo.strftime("%Y%m"))
    staging: list[Path] = []
    requests_manifest = []
    for aoi in pedidos:
        for etiqueta, req in _requests(periodo, aoi).items():
            exigir_espacio(SPEC.salida, espacio_minimo)
            destino = mes_dir / f"cams_eac4_{etiqueta}_{periodo.strftime('%Y%m')}.{aoi.id}.stage.nc"
            _publicar_stage(c, req, destino, periodo, etiqueta, aoi)
            staging.append(destino)
            requests_manifest.append(
                {
                    "aoi_id": aoi.id,
                    "territorio": aoi.territorio,
                    "etiqueta": etiqueta,
                    "request": req,
                    "archivo": destino.name,
                    "sha256": sha256_archivo(destino),
                }
            )
    fuentes = [*legacy, *staging]
    salida, manifest = normalizar_mes(
        SPEC, fuentes, periodo, comunas,
        permitir_parcial=False,
        espacio_minimo_gib=espacio_minimo,
    )
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    meta["adquisicion"] = {
        "dataset": DATASET,
        "requests_ads_sin_credenciales": requests_manifest,
        "fuentes_anuales_legacy_reutilizadas": [str(x) for x in legacy],
        "descargador": str(Path(__file__).resolve()),
        "descargador_sha256": sha256_archivo(Path(__file__)),
    }
    _json_atomico(manifest, meta)
    if staging:
        liberados = eliminar_fuentes_validadas(SPEC, staging, periodo, salida, manifest)
        try:
            mes_dir.rmdir()
        except OSError:
            pass
        log.info("%s validado; staging retirado (%.3f GiB)", periodo, liberados / 1024**3)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2003-01-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--comunas", type=Path, default=COMUNAS)
    ap.add_argument("--espacio-minimo-gb", type=float, default=100)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    p0 = max(pd.Period(a.desde[:7], "M"), pd.Period("2003-01", "M"))
    solicitado = pd.Period(a.hasta[:7], "M")
    p1 = min(solicitado, ULTIMO_PUBLICADO)
    if solicitado > p1:
        log.info(
            "CAMS EAC4 publicado hasta %s; %s queda pendiente de la proxima actualizacion",
            p1, solicitado,
        )
    if p1 < p0:
        ap.error("rango anterior al inicio nativo 2003-01")
    periodos = list(pd.period_range(p0, p1, freq="M"))
    c = None if a.dry_run else cliente()
    for periodo in periodos:
        procesar_mes(
            c, periodo, a.comunas,
            espacio_minimo=a.espacio_minimo_gb,
            dry_run=a.dry_run,
        )


if __name__ == "__main__":
    main()
