"""Cambia la corrección de retransformación del producto **sin volver a predecir**.

La corrección de Duan es un factor multiplicativo en escala física: una predicción publicada vale
``pred = exp(μ)·f − 1``, así que pasar de una corrección ``f`` a otra ``f'`` es exactamente
``pred' = (pred + 1)·f'/f − 1``. Verificado sobre 400.000 filas contra volver a predecir: diferencia
máxima 3,2 × 10⁻⁵ µg/m³ y 2 casillas de 400.000 cambian tras cuantizar a 0,1 µg/m³ (puro redondeo).

Eso convierte un cambio de ~34 h de re-predicción en uno de ~1 h de reescritura, y es reversible.

Qué hace, por contaminante:
  1. Recalcula ``smear`` desde ``oof.parquet`` con el método vigente de ese contaminante, usando
     las mismas funciones que el documento (``claves_retrans`` y ``smear_de`` de ``produccion``).
  2. Actualiza ``modelo_final.json`` conservando la corrección anterior en ``smear_anterior``.
     **No toca** ``modelo_final.txt``: el booster es el mismo y su sha256 no cambia.
  3. Reescala los NetCDF ya publicados de los ámbitos que se le pidan y rehace su manifiesto.

Es idempotente: un día cuyo manifiesto ya declara el método vigente se salta. Es interrumpible: cada
día se reescribe de forma atómica y su manifiesto se publica después.

    python -B scripts_modelo_1km/aplicar_retransformacion.py --contaminantes pm25 --ambitos rm
    python -B scripts_modelo_1km/aplicar_retransformacion.py --solo-smear
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from _comun_modelo import (  # noqa: E402
    AMBITOS_GRILLA, ESCALA_SUPERFICIE, MODELO_ROOT, SUPERFICIES_ROOT, carpeta_ambito,
    escribir_superficie_dia, leer_superficie_dia, log, publicar_json,
)
from _manifiesto_satelital import sha256  # noqa: E402
import produccion as P  # noqa: E402


_OOF: dict = {}


def smear_de_metodo(pol: str, sufijo: str, metodo: str) -> dict:
    """La corrección que produce ``metodo`` sobre los residuos fuera de pliegue, como el documento."""
    if (pol, sufijo) not in _OOF:
        _OOF[(pol, sufijo)] = pd.read_parquet(MODELO_ROOT / "modelos" / f"{pol}{sufijo}" / "oof.parquet",
                                              columns=["obs", "hora_local", "macrozona_cod", "z_loso"])
    oof = _OOF[(pol, sufijo)]
    res = np.log1p(np.clip(oof["obs"].to_numpy("float64"), 0, None)) - oof["z_loso"].to_numpy("float64")
    return P.smear_de(res, P.claves_retrans(oof, metodo), metodo)


def smear_vigente(pol: str, sufijo: str = "") -> tuple[dict, str]:
    """Corrección que corresponde hoy a ``pol``, calculada como la calcula el documento."""
    metodo = P.RETRANSFORMACION_POR_DEFECTO[pol]
    return smear_de_metodo(pol, sufijo, metodo), metodo


def factores(smear: dict, n_horas: int, macrozona: np.ndarray) -> np.ndarray:
    """``exp(adj)`` de cada (hora local, celda), con la misma búsqueda que usa la predicción."""
    f = np.empty((n_horas, len(macrozona)), dtype="float64")
    for h in range(n_horas):
        claves = P.claves_retransformacion(smear, np.full(len(macrozona), h), macrozona)
        f[h] = np.exp(np.array([smear.get(k, smear["_global"]) for k in claves], dtype="float64"))
    return f


def reescalar_dia(nc: Path, js: Path, f_viejo: np.ndarray, f_nuevo: np.ndarray, pol: str, metodo: str,
                  origen: str | None = None) -> bool:
    """Reescala un día publicado. Devuelve False si ya estaba en el método vigente."""
    import netCDF4

    reg = json.loads(js.read_text(encoding="utf-8")) if js.exists() else {}
    if reg.get("retransformacion") == metodo:
        return False
    with netCDF4.Dataset(nc) as d:
        atributos = {k: d.getncattr(k) for k in d.ncattrs()}
    ts, celdas, val = leer_superficie_dia(nc)
    nuevo = ((val.astype("float64") + 1.0) * (f_nuevo / f_viejo) - 1.0).astype("float32")
    nuevo[~np.isfinite(val)] = np.nan
    atributos["predictores"] = json.loads(atributos["predictores"]) if isinstance(atributos.get("predictores"), str) \
        else atributos.get("predictores")
    atributos["retransformacion"] = metodo
    atributos["nota"] = (str(atributos.get("nota", "")) +
                         f" | corrección de retransformación reescalada de '{origen}' a '{metodo}' el "
                         f"{datetime.now(timezone.utc).date().isoformat()} sin volver a predecir")
    escribir_superficie_dia(nc, pol, celdas, ts, nuevo, atributos)
    reg.update({"bytes": nc.stat().st_size, "sha256": sha256(nc), "retransformacion": metodo,
                "retransformacion_origen": origen,
                "fraccion_nan": float(np.mean(~np.isfinite(nuevo))), "media": float(np.nanmean(nuevo)),
                "p50": float(np.nanmedian(nuevo)), "p99": float(np.nanpercentile(nuevo, 99)),
                "reescalado_utc": datetime.now(timezone.utc).isoformat()})
    publicar_json(reg, js)
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--contaminantes", default="pm25")
    p.add_argument("--ambitos", default="rm,biobio,nacional")
    p.add_argument("--sufijo", default=None)
    p.add_argument("--solo-smear", action="store_true", help="actualiza modelo_final.json y no toca las superficies")
    args = p.parse_args(argv)
    sufijo = args.sufijo if args.sufijo is not None else (f"_{e}" if (e := os.environ.get("MODELO_1KM_ETIQUETA", "")) else "")
    if not logging.getLogger("modelo_1km").handlers:
        h = logging.StreamHandler(); h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        logging.getLogger("modelo_1km").addHandler(h)
    logging.getLogger("modelo_1km").setLevel(logging.INFO)

    from _comun_modelo import cargar_celdas, celdas_de_ambito
    celdas = cargar_celdas()
    for pol in [c.strip() for c in args.contaminantes.split(",") if c.strip()]:
        ruta_meta = MODELO_ROOT / "modelos" / f"{pol}{sufijo}" / "modelo_final.json"
        meta = json.loads(ruta_meta.read_text(encoding="utf-8"))
        nuevo, metodo = smear_vigente(pol, sufijo)
        viejo = meta["smear"]
        if meta.get("retransformacion") == metodo and viejo == nuevo:
            print(f"{pol}: ya está en '{metodo}', nada que hacer")
        else:
            meta["smear_anterior"] = {"smear": viejo, "retransformacion": meta.get("retransformacion")}
            meta["smear"], meta["retransformacion"] = nuevo, metodo
            meta["retransformacion_actualizada_utc"] = datetime.now(timezone.utc).isoformat()
            ruta_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{pol}: corrección -> '{metodo}' ({len([k for k in nuevo if '|' in k])} claves por macrozona)")
            for k in sorted(nuevo):
                print(f"    {k:14s} {nuevo[k]:.4f}" + (f"   (antes {viejo[k]:.4f})" if k in viejo else ""))
        if args.solo_smear:
            continue
        for ambito in [a.strip() for a in args.ambitos.split(",") if a.strip() in AMBITOS_GRILLA]:
            raiz = carpeta_ambito(SUPERFICIES_ROOT, "superficies", sufijo, ambito) / pol
            rutas = sorted(raiz.rglob(f"{pol}_1km_*.nc"))
            if not rutas:
                continue
            mz = celdas_de_ambito(celdas, ambito)["macrozona_cod"].to_numpy()
            # La corrección "vieja" de un día es la del método que ese día declara en su manifiesto,
            # recalculada desde las predicciones fuera de pliegue. NO se toma de modelo_final.json: si
            # éste ya se había actualizado (por ejemplo con --solo-smear, o porque el documento lo
            # reescribió), vieja y nueva coincidían, el factor valía uno y cada día quedaba rotulado con
            # el método nuevo y los valores viejos. Así pasó con 1.340 días de NO₂ el 2026-10-02.
            f_n = factores(nuevo, 24, mz)
            f_por_metodo: dict = {}
            hechos = 0
            for k, nc in enumerate(rutas):
                js = nc.with_suffix(".json")
                reg = json.loads(js.read_text(encoding="utf-8")) if js.exists() else {}
                origen = reg.get("retransformacion") or meta.get("smear_anterior", {}).get("retransformacion")
                if origen == metodo:
                    continue
                if origen not in f_por_metodo:
                    f_por_metodo[origen] = factores(smear_de_metodo(pol, sufijo, origen), 24, mz)
                    r = f_n / f_por_metodo[origen]
                    print(f"{pol} · {ambito}: de '{origen}' a '{metodo}': factor medio {np.mean(r):.4f} "
                          f"(mín {np.min(r):.4f}, máx {np.max(r):.4f})", flush=True)
                if reescalar_dia(nc, js, f_por_metodo[origen], f_n, pol, metodo, origen):
                    hechos += 1
                if (k + 1) % 1000 == 0:
                    print(f"   {k + 1:,}/{len(rutas):,}", flush=True)
            log.info("%s %s: %d días reescalados, %d ya estaban", pol, ambito, hechos, len(rutas) - hechos)
            print(f"   {hechos:,} reescalados, {len(rutas) - hechos:,} ya estaban")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
