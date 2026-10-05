#!/usr/bin/env python3
"""ACAG V6GL03 PM2.5: S3 Sudamérica → píxeles 0,01° de Chile → limpieza.

Descarga un NetCDF a la vez, conserva cada píxel (sin promedio comunal), aplica
la máscara administrativa, valida la salida comprimida y elimina el archivo SA
temporal. La mayor resolución temporal publicada por esta colección es mensual;
los valores no se duplican ni interpolan a horas.

El dominio FineResolution/SA cubre continente y Juan Fernández/Desventuradas,
pero no Rapa Nui/Sala y Gómez; esa ausencia queda registrada en el manifiesto.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import AOI, resumen_mascara, seleccionar  # noqa: E402
from _common import CONTAMINANTES, DATA, ensure_dir, get_logger  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, sha256, sha256_conjunto_shapefile,
)
from _recorte_grillas_nativas import (  # noqa: E402
    nombre_acag_recortado,
    recortar_acag,
    validar_acag,
)

log = get_logger("acag")
BUCKET = "satpmdata"
REGION = "us-east-1"
VERSION_TOKEN = "V6GL03"
PREFIJO_DEFECTO = "V6GL03/FineResolution/SA/"


def cliente():
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError as exc:
        raise SystemExit("Falta boto3: pip install boto3") from exc
    return boto3.client("s3", region_name=REGION,
                        config=Config(signature_version=UNSIGNED))


def listar_objetos(s3, prefijo=""):
    for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=BUCKET, Prefix=prefijo):
        yield from page.get("Contents", [])


def _periodo(nombre: str):
    m = re.search(r"\.(\d{4})(\d{2})-(\d{4})(\d{2})\.nc$", nombre)
    return tuple(map(int, m.groups())) if m else None


def _en_rango(nombre: str, desde: str, hasta: str) -> bool:
    p = _periodo(nombre)
    if not p:
        return False
    y0, m0, y1, m1 = p
    ini, fin = y0 * 100 + m0, y1 * 100 + m1
    return fin >= int(desde[:4] + desde[5:7]) and ini <= int(hasta[:4] + hasta[5:7])


def _bbox(aoi: AOI):
    lon0, lat0, lon1, lat1 = aoi.bbox
    return lon0 - 0.005001, lat0 - 0.005001, lon1 + 0.005001, lat1 + 0.005001


def _soportada(aoi: AOI) -> bool:
    # Dominio SA fuente verificado: lon -85..-34, lat -57..13.
    lon0, lat0, lon1, lat1 = aoi.bbox
    return lon1 >= -85 and lon0 <= -34 and lat1 >= -57 and lat0 <= 13


def _pixeles(path: Path) -> int:
    import xarray as xr
    with xr.open_dataset(path, decode_times=False) as ds:
        return int(ds["toca_chile"].sum().load())


def _procesar(src: Path, dest: Path, aois: tuple[AOI, ...], *, comunas: Path,
             temporal: str, mani: Manifiesto, conservar_fuente: bool,
             key: str | None, etag: str | None, es_temporal: bool):
    soportadas = tuple(a for a in aois if _soportada(a))
    salidas = []
    try:
        checksum_fuente = (f"s3-etag:{etag}" if etag else sha256(src))
        for aoi in soportadas:
            bbox = _bbox(aoi)
            out = recortar_acag(src, dest, bbox, comunas_path=comunas,
                                etiqueta=aoi.id)
            salidas.append((out, aoi, bbox))
        borrado = not conservar_fuente
        if borrado:
            src.unlink(missing_ok=True)
        for out, aoi, bbox in salidas:
            mani.archivo(
                salida=out, version=VERSION_TOKEN, granule_id=src.name,
                url=f"s3://{BUCKET}/{key}" if key else None,
                aoi_id=aoi.id, territorio=aoi.territorio, bbox=bbox,
                resolucion="0.01 grados", tiempo_nativo=temporal,
                qa="PM25 y metadatos ACAG nativos; sin promedio/interpolación",
                pixeles=_pixeles(out),
                mascara=(f"{comunas}; toca_chile y cod_comuna por centro; "
                         "geometrías make_valid"),
                validacion="NetCDF4 reabierto; PM25/coords/pixel_id verificados",
                crudo_eliminado=borrado, crudo=src,
                checksum_fuente=checksum_fuente)
        return [x[0] for x in salidas]
    except BaseException as exc:
        descartado = es_temporal and not conservar_fuente
        if descartado:
            src.unlink(missing_ok=True)
        mani.registrar({"evento": "archivo_fallido", "granule_id": src.name,
                        "s3_key": key, "error": f"{type(exc).__name__}: {exc}",
                        "crudo_temporal_descartado": descartado})
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--temporal", default="monthly",
                    choices=["monthly", "annual", "todo"])
    ap.add_argument("--desde", default="2000-01-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--prefijo", default=PREFIJO_DEFECTO)
    ap.add_argument("--aoi", default="todos")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--max-listar", type=int, default=40)
    ap.add_argument("--solo-recortar", action="store_true")
    ap.add_argument("--recortar-backlog", action="store_true")
    ap.add_argument("--conservar-fuente", action="store_true")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except ValueError as exc:
        ap.error(str(exc))
    if not args.dry_run and not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")

    s3 = cliente()
    if args.listar:
        for i, obj in enumerate(listar_objetos(s3, args.prefijo), 1):
            log.info("%s (%d MB)", obj["Key"], obj["Size"] // 2**20)
            if i >= args.max_listar:
                break
        return

    base = CONTAMINANTES / "ACAG_V6GL03"
    tmp, dest = ensure_dir(base / "_tmp_sa"), ensure_dir(base / "raw_chile")
    mani = Manifiesto(base / "_manifiestos", "ACAG_PM25", {
        "bucket": BUCKET, "prefijo": args.prefijo, "version": VERSION_TOKEN,
        "temporal": args.temporal, "desde": args.desde, "hasta": args.hasta,
        "aoi": [a.__dict__ for a in aois], "antartica": False,
        "dry_run": args.dry_run,
        "mascara_sha256": (sha256_conjunto_shapefile(args.comunas)
                            if args.comunas.exists() else None),
        "unidades_administrativas": (resumen_mascara(args.comunas)
                                       if args.comunas.exists() else None),
    })
    for aoi in aois:
        if not _soportada(aoi):
            mani.registrar({"evento": "aoi_no_cubierta_por_fuente",
                            "aoi_id": aoi.id, "territorio": aoi.territorio,
                            "dominio_fuente": [-85, -57, -34, 13]})

    fallos = 0
    if not args.dry_run:
        # Reanuda temporales completos; dry-run nunca modifica el disco.
        for part in tmp.glob("*.part"):
            part.unlink(missing_ok=True)
            mani.registrar({"evento": "temporal_incompleto_eliminado",
                            "ruta": str(part)})
        for src in sorted(tmp.glob("*.nc")):
            try:
                temporal = ("monthly" if re.search(r"\.\d{6}-\d{6}\.nc$", src.name)
                            else "annual")
                _procesar(src, dest, aois, comunas=args.comunas, temporal=temporal,
                         mani=mani, conservar_fuente=args.conservar_fuente,
                         key=None, etag=None, es_temporal=True)
            except Exception as exc:
                fallos += 1
                log.warning("Temporal ACAG %s falló: %s", src.name, exc)
        if args.recortar_backlog:
            fuentes = sorted(p for p in dest.glob("*.nc")
                              if ".chile.nc" not in p.name and
                              _en_rango(p.name, args.desde, args.hasta))
            for src in fuentes:
                try:
                    temporal = ("monthly" if re.search(
                        r"\.\d{6}-\d{6}\.nc$", src.name) else "annual")
                    _procesar(src, dest, aois, comunas=args.comunas,
                             temporal=temporal, mani=mani,
                             conservar_fuente=args.conservar_fuente,
                             key=None, etag=None, es_temporal=False)
                except Exception as exc:
                    fallos += 1
                    log.warning("Backlog ACAG %s falló: %s", src.name, exc)
        if args.solo_recortar:
            mani.terminar("completo" if not fallos else "con_fallos",
                          fallos=fallos)
            if fallos:
                raise SystemExit(1)
            return

    def coincide(key: str) -> bool:
        kl = key.lower()
        if VERSION_TOKEN.lower() not in kl or not kl.endswith(".nc"):
            return False
        if Path(key).name.startswith("._") or not _en_rango(Path(key).name,
                                                             args.desde, args.hasta):
            return False
        return (args.temporal == "todo" or
                (args.temporal == "monthly" and "monthly" in kl) or
                (args.temporal == "annual" and "annual" in kl))

    objetos = [o for o in listar_objetos(s3, args.prefijo) if coincide(o["Key"])]
    mani.registrar({"evento": "inventario_s3", "archivos": len(objetos)})
    if args.dry_run:
        for obj in objetos[:100]:
            log.info("[dry-run] %s (%d MB)", obj["Key"], obj["Size"] // 2**20)
        mani.terminar("dry_run", archivos=len(objetos))
        return

    soportadas = tuple(a for a in aois if _soportada(a))
    for i, obj in enumerate(objetos, 1):
        key, nombre = obj["Key"], Path(obj["Key"]).name
        validas = True
        for a in soportadas:
            p = dest / nombre_acag_recortado(nombre, a.id)
            if not p.exists():
                validas = False
                continue
            try:
                validar_acag(p, _bbox(a))
            except Exception as exc:
                p.unlink(missing_ok=True)
                mani.registrar({"evento": "salida_invalida_eliminada",
                                "ruta": str(p),
                                "error": f"{type(exc).__name__}: {exc}"})
                validas = False
        if validas:
            continue
        part, src = tmp / f"{nombre}.download.part", tmp / nombre
        part.unlink(missing_ok=True)
        try:
            log.info("↓ %s (%d MB)", key, obj["Size"] // 2**20)
            s3.download_file(BUCKET, key, str(part))
            os.replace(part, src)
            temporal = "monthly" if "monthly" in key.lower() else "annual"
            _procesar(src, dest, aois, comunas=args.comunas, temporal=temporal,
                     mani=mani, conservar_fuente=args.conservar_fuente,
                     key=key, etag=str(obj.get("ETag", "")).strip('"') or None,
                     es_temporal=True)
        except Exception as exc:
            fallos += 1
            part.unlink(missing_ok=True)
            src.unlink(missing_ok=True)
            log.warning("ACAG %d/%d falló: %s", i, len(objetos), exc)
        if i % 20 == 0 or i == len(objetos):
            log.info("  ACAG %d/%d", i, len(objetos))
    mani.terminar("completo" if not fallos else "con_fallos", fallos=fallos)
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
