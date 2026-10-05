#!/usr/bin/env python3
"""ERA5 BLH 0,25 grados horario -> pixeles nativos de Chile administrativo.

Usa el mismo motor reproducible de ERA5-Land, configurado para la grilla
nativa ERA5 de 0,25 grados y la variable ``boundary_layer_height``. Conserva
continente, Juan Fernandez, Desventuradas, Rapa Nui y Sala y Gomez mediante
huellas de celda, sin corredor oceanico en la salida, sin remuestreo y sin
promedio comunal.

Los rectangulos historicos de ``ERA5/raw_chile`` se leen, hashean y conservan
por defecto. Solo ``--eliminar-fuentes-validadas`` permite borrarlos, mes a
mes y despues de publicar, reabrir, validar y comprobar el hash de cada
resultado. Esto permite primero normalizar/auditar los 318 meses existentes y
autorizar la retirada del legado en una corrida posterior.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

import pandas as pd

import normalizar_era5land_chile as motor


VOLUMEN_DATOS = Path("/Volumes/Datos")
DATA_ROOT = motor.DATA_ROOT
COMUNAS = DATA_ROOT / "comunas.shp"
LEGADO = DATA_ROOT / "contaminantes" / "ERA5" / "raw_chile"
RAIZ_SALIDA = DATA_ROOT / "contaminantes" / "ERA5" / "chile_nativo_025deg"


def configurar_motor() -> None:
    motor.RESOLUCION = 0.25
    motor.N_LAT_GLOBAL = 721
    motor.N_LON_GLOBAL = 1440
    motor.PRODUCTO = "ERA5 boundary layer height"
    motor.PREFIJO_ARCHIVO = "era5_blh"
    motor.SCRIPT_PRODUCTO = Path(__file__)
    motor.ALIAS_VARIABLES = {
        "blh": ("blh", "PBLH", "boundary_layer_height"),
    }
    motor.ALIAS_A_CANONICO = {
        alias.lower(): canonico
        for canonico, aliases in motor.ALIAS_VARIABLES.items()
        for alias in aliases
    }


configurar_motor()


def _fuente_periodo(periodo: pd.Period) -> Path | None:
    candidatos = (
        LEGADO / f"era5_pblh_{periodo.strftime('%Y%m')}_chile.nc",
        LEGADO / f"era5_blh_{periodo.strftime('%Y%m')}.nc",
    )
    existentes = [p for p in candidatos if p.exists()]
    if len(existentes) > 1:
        raise ValueError(f"{periodo}: fuentes BLH ambiguas {existentes}")
    return existentes[0] if existentes else None


def periodos_disponibles() -> list[pd.Period]:
    periodos = set()
    paths = list(LEGADO.glob("*.nc")) + list((RAIZ_SALIDA / "mensual").glob("*.nc"))
    for path in paths:
        import re
        m = re.search(r"(\d{6})", path.name)
        if m:
            periodos.add(pd.Period(m.group(1), freq="M"))
    return sorted(periodos)


def _salida_previa_validada(periodo: pd.Period) -> bool:
    salida = (
        RAIZ_SALIDA / "mensual"
        / f"era5_blh_{periodo.strftime('%Y%m')}_chile_pixeles.nc"
    )
    manifest = (
        RAIZ_SALIDA / "manifiestos"
        / f"era5_blh_{periodo.strftime('%Y%m')}.json"
    )
    catalogo = RAIZ_SALIDA / "catalogo_pixeles.parquet"
    if not (salida.exists() and manifest.exists() and catalogo.exists()):
        return False
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        permitir_parcial = bool(
            meta.get("parametros_normalizacion", {}).get("permitir_mes_parcial")
        )
        motor.validar_salida_mensual(
            salida, periodo, catalogo, ["blh"], permitir_parcial
        )
        return (
            motor.sha256_archivo(salida) == meta["salida"]["sha256"]
            and bool(meta.get("fuentes_eliminadas_despues_de_validar"))
        )
    except Exception:
        return False


def normalizar_rango(
    desde: pd.Period,
    hasta: pd.Period,
    eliminar: bool = False,
) -> dict[str, int]:
    motor.asegurar_disco_externo(RAIZ_SALIDA)
    catalogo, _, _ = motor.crear_catalogos(RAIZ_SALIDA, COMUNAS)
    resumen = {"normalizados": 0, "faltantes": 0, "fuentes_eliminadas": 0}
    for periodo in pd.period_range(desde, hasta, freq="M"):
        fuente = _fuente_periodo(periodo)
        if fuente is None:
            if _salida_previa_validada(periodo):
                print(f"VALIDADO PREVIO {periodo}: fuente ya retirada", flush=True)
                resumen["normalizados"] += 1
                continue
            print(f"FALTA {periodo}: sin fuente BLH", flush=True)
            resumen["faltantes"] += 1
            continue
        inventario = motor._inventario_fuente(fuente, periodo)
        permitir_parcial = (
            len(inventario["times"]) < periodo.days_in_month * 24
        )
        salida, manifest = motor.normalizar_mes(
            [fuente],
            periodo,
            RAIZ_SALIDA,
            COMUNAS,
            ["blh"],
            permitir_parcial,
        )
        resumen["normalizados"] += 1
        print(f"VALIDADO {periodo}: {salida.name}", flush=True)
        if eliminar and not permitir_parcial:
            motor.eliminar_fuentes_validadas(
                [fuente], salida, manifest, periodo, catalogo, permitir_parcial
            )
            resumen["fuentes_eliminadas"] += 1
            print(f"FUENTE RETIRADA TRAS VALIDAR {fuente.name}", flush=True)
        elif eliminar and permitir_parcial:
            print(
                f"FUENTE PARCIAL CONSERVADA {fuente.name}: se reemplazara antes de borrar",
                flush=True,
            )
    return resumen


def main() -> None:
    disponibles = periodos_disponibles()
    if not disponibles:
        raise SystemExit(f"sin NetCDF BLH en {LEGADO}")
    ap = argparse.ArgumentParser(
        description="Normaliza ERA5 BLH horario 0,25 grados sin perder resolucion"
    )
    ap.add_argument("--desde", default=str(disponibles[0]))
    ap.add_argument("--hasta", default=str(disponibles[-1]))
    ap.add_argument(
        "--eliminar-fuentes-validadas",
        action="store_true",
        help="BORRADO EXPLICITO del legado, solo despues de validacion y hashes",
    )
    a = ap.parse_args()
    try:
        desde, hasta = pd.Period(a.desde, "M"), pd.Period(a.hasta, "M")
    except ValueError as exc:
        ap.error(str(exc))
    if desde > hasta:
        ap.error("--desde debe ser anterior o igual a --hasta")
    resumen = normalizar_rango(desde, hasta, a.eliminar_fuentes_validadas)
    print(
        "BLH COMPLETO: "
        f"{resumen['normalizados']} meses normalizados; "
        f"{resumen['faltantes']} faltantes; "
        f"{resumen['fuentes_eliminadas']} fuentes retiradas",
        flush=True,
    )


if __name__ == "__main__":
    main()
