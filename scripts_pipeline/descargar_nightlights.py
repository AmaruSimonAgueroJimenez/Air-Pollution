#!/usr/bin/env python3
"""Luces nocturnas Black Marble con máxima resolución nativa y hora por píxel.

Por defecto empareja VNP46A2 diario (radiancia BRDF corregida) con VNP46A1 del
mismo día/tile (``UTC_Time`` por píxel, radiancia al sensor y QA mínima), ambos
a 15 arc-sec (~500 m). Conserva sólo las variables necesarias, recorta por AOI,
valida y elimina cada tile temporal. La llave es fecha + tile + pixel_id.
VNP46A2 solo es un compuesto de 24 h y nunca se rotula con hora exacta; esa hora
proviene exclusivamente de A1. ``--producto monthly`` añade VNP46A3 sin hora.

Para 2000-01-01–2012-01-18 el descargador separado ``descargar_dmsp_len.py`` usa el archivo
público World Bank Light Every Night: segmentos nocturnos DMSP-OLS en la grilla
publicada de 30 arc-sec, con UTC de inicio, DN visible, iluminación lunar y QA.
No necesita credenciales y no convierte las pasadas en una serie horaria.

Si aparecen GeoTIFF ``ntl_armonizado_YYYY_chile.tif`` sin fuente, versión,
unidades ni método de armonización DMSP–VIIRS verificable, se marcan
``provenance_blocked`` y no se usan como insumo reproducible.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import AOI, resumen_mascara, seleccionar  # noqa: E402
from _common import CONTAMINANTES, DATA, ensure_dir, get_logger  # noqa: E402
from _env_earthdata import login  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, sha256, sha256_conjunto_shapefile, url_publica,
)
from _recorte_grillas_nativas import (  # noqa: E402
    nombre_hdf_recortado,
    recortar_viirs_black_marble,
    validar_viirs_black_marble,
)

log = get_logger("nightlights")
PRODUCTOS = {
    # CMR usa version_id "2" (los nombres muestran colección 002).
    "a1": ("VNP46A1", "2", "per_pixel_UTC_Time; native overpass"),
    "a2": ("VNP46A2", "2", "daily_24h_composite; no exact intraday time"),
    "monthly": ("VNP46A3", "2", "monthly; no exact intraday time"),
}


def _nombre(g):
    try:
        return g.data_links()[0].rsplit("/", 1)[-1].split("?", 1)[0]
    except Exception:
        return ""


def _url(g):
    try:
        return url_publica(g.data_links()[0])
    except Exception:
        return None


def _fecha_diaria(nombre: str) -> date | None:
    import re
    m = re.search(r"\.A(\d{4})(\d{3})\.", nombre)
    if not m:
        return None
    return date(int(m.group(1)), 1, 1) + timedelta(days=int(m.group(2)) - 1)


def _diario_en_rango(nombre: str, desde: str, hasta: str) -> bool:
    f = _fecha_diaria(nombre)
    return f is not None and date.fromisoformat(desde) <= f <= date.fromisoformat(hasta)


def _salida(nombre: str, aoi: AOI):
    return nombre_hdf_recortado(nombre, sufijo=f".{aoi.id}.chile.h5")


def _centinela(nombre: str, aoi: AOI, dest: Path) -> Path:
    return dest / (_salida(nombre, aoi) + ".vacio")


def _centinela_valida(path: Path, mascara_sha256: str) -> bool:
    try:
        return path.exists() and json.loads(path.read_text(encoding="utf-8")).get(
            "mascara_sha256") == mascara_sha256
    except (OSError, ValueError, TypeError):
        return False


def _exigir_reserva_espacio(path: Path, reserva_gib: float, mani: Manifiesto,
                            *, fase: str, granule_id: str) -> None:
    """Aborta antes de iniciar trabajo si no puede respetarse la reserva."""
    error = None
    try:
        libres_gib = shutil.disk_usage(path).free / 2**30
    except OSError as exc:
        libres_gib = None
        error = f"{type(exc).__name__}: {exc}"
    if libres_gib is not None and libres_gib >= reserva_gib:
        return

    if error:
        motivo = f"no se pudo comprobar el espacio libre en {path}: {error}"
    else:
        motivo = (
            f"quedan {libres_gib:.1f} GiB; reserva mínima "
            f"{reserva_gib:.1f} GiB"
        )
    detalle = {
        "motivo": motivo,
        "fase": fase,
        "granule_id": granule_id,
        "ruta_verificada": str(path),
        "libres_gib": libres_gib,
        "reserva_gib": reserva_gib,
        "operacion_iniciada": False,
    }
    mani.registrar({"evento": "reserva_espacio_alcanzada", **detalle})
    mani.terminar("abortado_espacio", **detalle)
    log.error("%s; se aborta antes de %s %s", motivo, fase, granule_id)
    raise SystemExit(2)


def auditar_legado(base: Path, mani: Manifiesto) -> None:
    try:
        import rasterio
    except ImportError:
        rasterio = None
    for tif in sorted(base.glob("ntl_armonizado_*_chile.tif")):
        metadatos = {}
        if rasterio:
            with rasterio.open(tif) as ds:
                metadatos = {"crs": str(ds.crs), "bounds": tuple(ds.bounds),
                             "resolucion": tuple(ds.res), "dtype": ds.dtypes[0],
                             "nodata": ds.nodata, "tags": ds.tags()}
        mani.registrar({
            "evento": "legacy_provenance_blocked",
            "ruta": str(tif), "bytes": tif.stat().st_size,
            "sha256": sha256(tif), **metadatos,
            "motivo": ("faltan fuente/URL, producto, versión, unidades y método "
                       "documentado de armonización DMSP–VIIRS"),
            "accion": "conservar; no usar como insumo reproducible hasta documentar",
        })


def _pixeles(path: Path) -> int:
    import h5py
    with h5py.File(path, "r") as h:
        return int(h["ChileSubset/toca_chile"][:].sum())


def _variables(path: Path) -> list[str]:
    import json
    import h5py
    with h5py.File(path, "r") as h:
        valor = h.attrs.get("retained_science_fields", "[]")
        if isinstance(valor, bytes):
            valor = valor.decode("utf-8")
        return list(json.loads(str(valor)))


def _procesar(src: Path, dest: Path, aois: tuple[AOI, ...], *, short: str,
             version: str, temporal_nativo: str, comunas: Path,
             mascara_sha256: str,
             conservar_crudo: bool, mani: Manifiesto, url: str | None,
             es_temporal: bool):
    salidas = []
    vacios = []
    sin_cruce = []
    checksum_fuente = None
    wal_persistido = False
    crudo_eliminado = False
    try:
        checksum_fuente = sha256(src)
        bytes_fuente = src.stat().st_size
        for aoi in aois:
            try:
                out = recortar_viirs_black_marble(
                    src, dest, aoi.bbox, comunas_path=comunas, etiqueta=aoi.id,
                    mascara_sha256=mascara_sha256)
            except ValueError as exc:
                if "no cruza AOI" in str(exc):
                    sin_cruce.append(aoi)
                    continue
                raise
            if out is None:
                vacios.append(aoi)
            else:
                salidas.append((out, aoi, _pixeles(out), _variables(out)))
        borrado = not conservar_crudo
        if borrado:
            resultados_aoi = [
                {
                    "resultado": "archivo_validado",
                    "aoi_id": aoi.id,
                    "territorio": aoi.territorio,
                    "bbox": tuple(aoi.bbox),
                    "pixeles_chile": pixeles,
                    "salida": str(out),
                    "bytes_salida": out.stat().st_size,
                    "sha256_salida": sha256(out),
                    "variables_conservadas": variables,
                }
                for out, aoi, pixeles, variables in salidas
            ]
            resultados_aoi.extend({
                "resultado": resultado,
                "aoi_id": aoi.id,
                "territorio": aoi.territorio,
                "bbox": tuple(aoi.bbox),
                "pixeles_chile": 0,
                "variables_conservadas": [],
            } for resultado, grupo in (("aoi_sin_pixeles", vacios),
                                       ("aoi_no_cruza", sin_cruce))
                for aoi in grupo)
            # Barrera durable: registrar hace flush+fsync. Ni un fallo de
            # construcción ni uno de sincronización puede autorizar el borrado.
            mani.registrar({
                "evento": "granulo_validado_pre_borrado",
                "granule_id": src.name,
                "producto_fuente": short,
                "version": version,
                "url": url_publica(url),
                "crudo": str(src),
                "bytes_fuente": bytes_fuente,
                "sha256_fuente": checksum_fuente,
                "mascara": str(comunas),
                "mascara_sha256": mascara_sha256,
                "resolucion_nativa": "15 arc-sec (~500 m)",
                "tiempo_nativo": temporal_nativo,
                "temporal": es_temporal,
                "borrado_solicitado": True,
                "crudo_eliminado": False,
                "resultados_aoi": resultados_aoi,
            })
            wal_persistido = True
            src.unlink()
            crudo_eliminado = True
            mani.registrar({
                "evento": "crudo_eliminado_post_validacion",
                "granule_id": src.name,
                "version": version,
                "crudo": str(src),
                "sha256_fuente": checksum_fuente,
                "aoi_ids": [aoi.id for aoi in aois],
                "crudo_eliminado": True,
                "wal_evento": "granulo_validado_pre_borrado",
            })
        for out, aoi, pixeles, variables in salidas:
            qa_detalle = {
                "VNP46A1": ("UTC_Time por píxel, DNB al sensor, QF_DNB y "
                             "QF_Cloud_Mask"),
                "VNP46A2": ("DNB BRDF, gap-fill, calidad obligatoria, nube, "
                             "nieve y última recuperación"),
                "VNP46A3": "compuestos snow-free, desviación y conteos",
            }.get(short, "variables necesarias registradas en manifiesto")
            mani.archivo(
                salida=out, version=version, granule_id=src.name, url=url,
                aoi_id=aoi.id, territorio=aoi.territorio, bbox=aoi.bbox,
                resolucion="15 arc-sec (~500 m)",
                tiempo_nativo=temporal_nativo,
                qa=qa_detalle,
                pixeles=pixeles,
                mascara=(f"{comunas}; toca_chile/cod_comuna; geometrías make_valid"),
                validacion="HDF5 reabierto; SDS/geolocalización/pixel_id verificados",
                crudo_eliminado=crudo_eliminado, crudo=src,
                checksum_fuente=checksum_fuente,
                variables_conservadas=variables)
        for aoi in vacios:
            mani.registrar({
                "evento": "aoi_sin_pixeles", "granule_id": src.name,
                "aoi_id": aoi.id, "territorio": aoi.territorio,
                "bbox": aoi.bbox, "mascara_sha256": mascara_sha256,
                "sha256_fuente": checksum_fuente,
                "crudo_eliminado": crudo_eliminado,
                "url": url, "version": version,
            })
        return [x[0] for x in salidas]
    except BaseException as exc:
        try:
            mani.registrar({
                "evento": "archivo_fallido", "granule_id": src.name,
                "url": url, "error": f"{type(exc).__name__}: {exc}",
                "sha256_fuente": checksum_fuente,
                "wal_pre_borrado_persistido": wal_persistido,
                "crudo_preservado": src.exists(),
                "crudo_temporal_descartado": es_temporal and crudo_eliminado,
            })
        except BaseException:
            # Una segunda falla del manifiesto no borra ni oculta la original.
            pass
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--producto", default="daily",
                    choices=["daily", "a1", "a2", "monthly", "todos"],
                    help="daily=A1+A2 emparejados; a1/a2 permiten diagnóstico")
    ap.add_argument("--desde", default="2012-01-19")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--aoi", default="todos")
    ap.add_argument("--solo-recortar", action="store_true")
    ap.add_argument("--conservar-crudo", action="store_true")
    ap.add_argument("--auditar-legado", action=argparse.BooleanOptionalAction,
                    default=True)
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--min-gb-libres", type=float, default=100.0,
                    help="reserva mínima exigida antes de cada gránulo (GiB)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not math.isfinite(args.min_gb_libres) or args.min_gb_libres < 0:
        ap.error("--min-gb-libres debe ser finito y no negativo")
    try:
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except ValueError as exc:
        ap.error(str(exc))
    if not args.dry_run and not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")
    if not (args.dry_run or args.solo_recortar):
        login()

    base = ensure_dir(CONTAMINANTES / "Nightlights")
    mascara_sha = (sha256_conjunto_shapefile(args.comunas)
                    if args.comunas.exists() else "sin_mascara")
    if args.producto == "daily":
        productos = ("a1", "a2")
    elif args.producto == "todos":
        productos = tuple(PRODUCTOS)
    else:
        productos = (args.producto,)
    fallos_totales = 0
    for producto in productos:
        short, version, temporal = PRODUCTOS[producto]
        prod_base = ensure_dir(base / short)
        tmp, dest = ensure_dir(prod_base / "_tmp_tiles"), ensure_dir(prod_base / "raw_chile")
        mani = Manifiesto(prod_base / "_manifiestos", short, {
            "short_name": short, "version": version, "desde": args.desde,
            "hasta": args.hasta, "temporal": temporal,
            "resolucion": "15 arc-sec", "aoi": [a.__dict__ for a in aois],
            "emparejamiento_a1_a2": "fecha_adquisicion + tile + pixel_id",
            "fuente_hora_exacta": ("UTC_Time por pixel" if short == "VNP46A1"
                                    else "ninguna; enlazar VNP46A1"),
            "antartica": False, "dry_run": args.dry_run,
            "min_gb_libres": args.min_gb_libres,
            "mascara_sha256": mascara_sha,
            "unidades_administrativas": (resumen_mascara(args.comunas)
                                           if args.comunas.exists() else None),
        })
        if args.auditar_legado:
            auditar_legado(base, mani)
        if args.dry_run:
            mani.terminar("dry_run")
            continue

        fallos = 0
        # Backlog: prueba cada AOI; elimina el temporal sólo después de que al
        # menos un recorte territorial quede validado.
        for src in sorted(tmp.glob("*.h5")):
            if ".chile.h5" in src.name:
                continue
            _exigir_reserva_espacio(
                tmp, args.min_gb_libres, mani,
                fase="procesar_backlog", granule_id=src.name)
            try:
                _procesar(src, dest, aois, short=short, version=version,
                         temporal_nativo=temporal, comunas=args.comunas,
                         mascara_sha256=mascara_sha,
                         conservar_crudo=args.conservar_crudo, mani=mani,
                         url=None, es_temporal=True)
            except Exception as exc:
                fallos += 1
                log.warning("Backlog %s falló: %s", src.name, exc)
        for patron in ("*.part", "*.tmp", "*.download"):
            for part in tmp.glob(patron):
                part.unlink(missing_ok=True)
                mani.registrar({"evento": "temporal_incompleto_eliminado",
                                "ruta": str(part)})
        if args.solo_recortar:
            mani.terminar("completo" if not fallos else "con_fallos",
                          fallos=fallos)
            fallos_totales += fallos
            continue

        import earthaccess
        granulos, aois_por_nombre, conteo = {}, {}, {}
        for aoi in aois:
            rs = earthaccess.search_data(short_name=short, version=version,
                                         bounding_box=aoi.bbox,
                                         temporal=(args.desde, args.hasta))
            conteo[aoi.id] = len(rs)
            for g in rs:
                nombre = _nombre(g) or f"sin_nombre_{id(g)}"
                if short in {"VNP46A1", "VNP46A2"} and \
                        not nombre.startswith("sin_nombre_") and \
                        not _diario_en_rango(nombre, args.desde, args.hasta):
                    continue
                granulos[nombre] = g
                aois_por_nombre.setdefault(nombre, set()).add(aoi.id)
        mani.registrar({"evento": "consulta_cmr", "granulos_por_aoi": conteo,
                        "granulos_unicos": len(granulos)})
        por_id = {a.id: a for a in aois}
        for i, (nombre, g) in enumerate(granulos.items(), 1):
            relevantes = tuple(por_id[x] for x in sorted(aois_por_nombre[nombre]))
            validas = True
            if not nombre.startswith("sin_nombre_"):
                for a in relevantes:
                    p = dest / _salida(nombre, a)
                    if not p.exists():
                        if not _centinela_valida(
                                _centinela(nombre, a, dest), mascara_sha):
                            validas = False
                        continue
                    try:
                        validar_viirs_black_marble(p, a.bbox)
                    except Exception as exc:
                        p.unlink(missing_ok=True)
                        mani.registrar({"evento": "salida_invalida_eliminada",
                                        "ruta": str(p),
                                        "error": f"{type(exc).__name__}: {exc}"})
                        validas = False
            else:
                validas = False
            if validas:
                continue
            _exigir_reserva_espacio(
                tmp, args.min_gb_libres, mani,
                fase="descargar_granulo", granule_id=nombre)
            try:
                fs = earthaccess.download([g], str(tmp)) or []
                if not fs:
                    raise RuntimeError("Earthaccess no devolvió archivo")
                for f in fs:
                    _procesar(Path(f), dest, relevantes, short=short,
                             version=version, temporal_nativo=temporal,
                             comunas=args.comunas,
                             mascara_sha256=mascara_sha,
                             conservar_crudo=args.conservar_crudo, mani=mani,
                             url=_url(g), es_temporal=True)
            except Exception as exc:
                fallos += 1
                nombre_fallido = _nombre(g)
                candidato = tmp / nombre_fallido if nombre_fallido else None
                if candidato and candidato.exists() and not args.conservar_crudo:
                    # También cubre fallos de _procesar/WAL: no saltarse su
                    # barrera durable borrando la fuente desde el llamador.
                    mani.registrar({"evento": "temporal_descarga_fallida_preservado",
                                    "ruta": str(candidato),
                                    "crudo_preservado": True})
                log.warning("%s %d/%d falló: %s", short, i, len(granulos), exc)
            if i % 100 == 0 or i == len(granulos):
                log.info("  %s %d/%d", short, i, len(granulos))
        mani.terminar("completo" if not fallos else "con_fallos", fallos=fallos)
        fallos_totales += fallos

    if fallos_totales:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
