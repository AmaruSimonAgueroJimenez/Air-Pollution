#!/usr/bin/env python3
"""Sentinel-5P TROPOMI L2: órbita global → píxeles nativos de Chile.

Consulta por AOIs administrativas compactas (continente, Juan Fernández,
Desventuradas, Rapa Nui y Sala y Gómez), deduplica cada órbita, conserva cada
píxel con tiempo/scanline/ground_pixel y la selección científica necesaria
(gas+precisión, QA, huella, AMF, nube, superficie, nieve y ángulos), y publica
un recorte separado por AOI. ``CHILE_SUBSET`` contiene pixel_id, máscara por
huella y cod_comuna por centro; no hay promedio ni interpolación horaria.

El global temporal sólo se elimina después de validar todos los AOIs que CMR
asoció al gránulo. Si una órbita no toca la máscara, queda una centinela pequeña
y reproducible para no descargarla otra vez. Antes de borrar el crudo se
sincroniza un registro write-ahead con sus hashes y resultados; si falla esa
persistencia, el crudo se conserva para una reanudación segura.

TROPOMI comienza en 2018-04. Uso:

  python descargar_tropomi.py --desde 2018-04-30   # hasta hoy por defecto
  python descargar_tropomi.py --solo-recortar
  python descargar_tropomi.py --solo-recortar --recortar-backlog
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import AOI, resumen_mascara, seleccionar  # noqa: E402
from _common import CONTAMINANTES, DATA, ensure_dir, get_logger  # noqa: E402
from _env_earthdata import login  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, sha256, sha256_conjunto_shapefile, url_publica,
)
from _recorte_tropomi import limpiar_tmp, recortar, validar_recorte  # noqa: E402

log = get_logger("tropomi")

SHORT = {
    "no2": "S5P_L2__NO2____HiR",
    "o3": "S5P_L2__O3_TOT_HiR",
    "so2": "S5P_L2__SO2____HiR",
    "co": "S5P_L2__CO_____HiR",
}
VERSION = "2"
LOTE = 4
MARGEN_HUELLA = 0.35  # cubre píxeles anchos al borde; la máscara sigue exacta


def _nombre(g) -> str:
    try:
        return unquote(g.data_links()[0].rsplit("/", 1)[-1].split("?", 1)[0])
    except Exception:
        return ""


def _url(g) -> str | None:
    try:
        return url_publica(g.data_links()[0])
    except Exception:
        return None


def _bbox(aoi: AOI):
    lon0, lat0, lon1, lat1 = aoi.bbox
    m = MARGEN_HUELLA
    return lon0 - m, lat0 - m, lon1 + m, lat1 + m


def nombre_recortado(nombre_global: str, aoi: AOI) -> str:
    return nombre_global.removesuffix(".nc") + f".{aoi.id}.chile.nc"


def _centinela(nombre_global: str, aoi: AOI, destino: Path) -> Path:
    return destino / (nombre_recortado(nombre_global, aoi) + ".vacio")


def _centinela_valida(path: Path, mascara_sha256: str) -> bool:
    if not path.exists():
        return False
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(
            "mascara_sha256") == mascara_sha256
    except (OSError, ValueError, TypeError):
        return False


def _salidas_validas(nombre: str, destino: Path, aois: tuple[AOI, ...],
                     mascara_sha256: str, mani: Manifiesto) -> bool:
    todas = True
    for aoi in aois:
        path = destino / nombre_recortado(nombre, aoi)
        if path.exists():
            try:
                validar_recorte(path, _bbox(aoi), mascara_requerida=True)
                continue
            except Exception as exc:
                path.unlink(missing_ok=True)
                mani.registrar({
                    "evento": "salida_invalida_eliminada", "salida": str(path),
                    "aoi_id": aoi.id, "error": f"{type(exc).__name__}: {exc}",
                })
        if _centinela_valida(_centinela(nombre, aoi, destino), mascara_sha256):
            continue
        todas = False
    return todas


def _variables_salida(path: Path) -> list[str]:
    import netCDF4
    with netCDF4.Dataset(path) as ds:
        valor = ds.getncattr("retained_source_variables")
    return list(json.loads(str(valor)))


def _procesar(src: Path, destino: Path, aois: tuple[AOI, ...], *, pol: str,
             comunas: Path, mascara_sha256: str, conservar_global: bool,
             mani: Manifiesto, url: str | None, temporal: bool) -> list[Path]:
    salidas: list[tuple[Path, AOI, tuple, dict, list[str]]] = []
    vacios: list[AOI] = []
    checksum_fuente: str | None = None
    wal_persistido = False
    crudo_eliminado = False
    try:
        checksum_fuente = sha256(src)
        bytes_fuente = src.stat().st_size
        for aoi in aois:
            bbox = _bbox(aoi)
            out = recortar(
                src, destino, bbox, sufijo=f".{aoi.id}.chile.nc",
                comunas_path=comunas, mascara_sha256=mascara_sha256,
                aoi_id=aoi.id, territorio=aoi.territorio,
            )
            if out is None:
                vacios.append(aoi)
                continue
            info = validar_recorte(out, bbox, mascara_requerida=True)
            salidas.append((out, aoi, bbox, info, _variables_salida(out)))

        borrado = not conservar_global
        if borrado:
            resultados_aoi = [
                {
                    "resultado": "archivo_validado",
                    "aoi_id": aoi.id,
                    "territorio": aoi.territorio,
                    "bbox": tuple(bbox),
                    "pixeles_chile": info["pixeles_chile"],
                    "salida": str(out),
                    "bytes_salida": out.stat().st_size,
                    "sha256_salida": sha256(out),
                    "variables_conservadas": variables,
                }
                for out, aoi, bbox, info, variables in salidas
            ]
            resultados_aoi.extend({
                "resultado": "aoi_sin_pixeles",
                "aoi_id": aoi.id,
                "territorio": aoi.territorio,
                "bbox": tuple(_bbox(aoi)),
            } for aoi in vacios)
            # Barrera durable: Manifiesto.registrar hace flush+fsync. El crudo
            # no se toca si construir o sincronizar este registro falla.
            mani.registrar({
                "evento": "granulo_validado_pre_borrado",
                "granule_id": src.name,
                "producto_quimico": pol,
                "version": VERSION,
                "url": url_publica(url),
                "crudo": str(src),
                "bytes_fuente": bytes_fuente,
                "sha256_fuente": checksum_fuente,
                "mascara_sha256": mascara_sha256,
                "temporal": temporal,
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
                "version": VERSION,
                "crudo": str(src),
                "sha256_fuente": checksum_fuente,
                "aoi_ids": [aoi.id for aoi in aois],
                "crudo_eliminado": True,
                "wal_evento": "granulo_validado_pre_borrado",
            })
        for out, aoi, bbox, info, variables in salidas:
            mani.archivo(
                salida=out, version=VERSION, granule_id=src.name, url=url,
                aoi_id=aoi.id, territorio=aoi.territorio, bbox=bbox,
                resolucion=("swath L2 nativo por gránulo; HiR aprox. "
                            "3.5×5.5 km desde 2019-08"),
                tiempo_nativo="scanline: PRODUCT/time_utc + delta_time",
                qa=("qa_value, precision, AMF, nubes, presión/altura, nieve y "
                    "ángulos; averaging_kernel excluido"),
                pixeles=info["pixeles_chile"],
                mascara=(f"{comunas}; bounds-intersects=toca_chile; "
                         "centro=cod_comuna; make_valid"),
                validacion=("NetCDF4 reabierto; PRODUCT/CHILE_SUBSET, formas, "
                            "pixel_id y máscara verificados"),
                crudo_eliminado=crudo_eliminado, crudo=src,
                checksum_fuente=checksum_fuente,
                variables_conservadas=variables,
            )
        for aoi in vacios:
            mani.registrar({
                "evento": "aoi_sin_pixeles", "granule_id": src.name,
                "aoi_id": aoi.id, "territorio": aoi.territorio,
                "bbox": _bbox(aoi), "mascara_sha256": mascara_sha256,
                "crudo_eliminado": crudo_eliminado,
                "sha256_fuente": checksum_fuente,
                "url": url, "version": VERSION,
            })
        return [x[0] for x in salidas]
    except BaseException as exc:
        # En particular, una falla de serialización/flush/fsync del WAL jamás
        # debe activar el borrado que precisamente intentaba autorizar.
        try:
            mani.registrar({
                "evento": "archivo_fallido", "granule_id": src.name,
                "url": url, "error": f"{type(exc).__name__}: {exc}",
                "sha256_fuente": checksum_fuente,
                "wal_pre_borrado_persistido": wal_persistido,
                "crudo_preservado": src.exists(),
                "crudo_temporal_descartado": temporal and crudo_eliminado,
            })
        except BaseException:
            # Preserva la excepción original y, sobre todo, nunca borra como
            # reacción a una segunda falla del propio manifiesto.
            pass
        raise


def _backlog(carpeta: Path, destino: Path, aois: tuple[AOI, ...], **kw) -> None:
    fuentes = sorted(
        p for p in carpeta.glob("*.nc")
        if ".chile.nc" not in p.name and ".chile." not in p.name
    )
    for src in fuentes:
        _procesar(src, destino, aois, temporal=(carpeta.name == "_tmp_global"),
                  url=None, **kw)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contaminantes", default="no2,o3,so2,co")
    ap.add_argument("--desde", default="2018-04-30")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--aoi", default="todos")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--solo-recortar", action="store_true")
    ap.add_argument("--recortar-backlog", action="store_true",
                    help="migra globales históricos que aún estén en raw_chile")
    ap.add_argument(
        "--migrar-legado-continental", action="store_true",
        help=("convierte localmente *.chile.nc rectangulares al formato "
              "compacto/máscara actual; no descarga red y borra cada legado "
              "sólo tras reabrir/validar la salida"))
    ap.add_argument("--espacio-minimo-gb", type=float, default=100.0,
                    help="reserva mínima exigida durante migración local")
    ap.add_argument("--conservar-global", action="store_true",
                    help="diagnóstico: no elimina el global después del commit")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    pols = [p.strip().lower() for p in args.contaminantes.split(",") if p.strip()]
    malos = [p for p in pols if p not in SHORT]
    if malos:
        ap.error(f"contaminantes inválidos: {malos}; válidos: {list(SHORT)}")
    if not args.dry_run and not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")
    try:
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    if not (args.dry_run or args.solo_recortar):
        login()

    mascara_sha = (sha256_conjunto_shapefile(args.comunas)
                    if args.comunas.exists() else "sin_mascara")
    for pol in pols:
        base = CONTAMINANTES / "S5P_TROPOMI" / pol.upper()
        tmp = ensure_dir(base / "_tmp_global")
        destino = ensure_dir(base / "raw_chile")
        mani = Manifiesto(base / "_manifiestos", f"TROPOMI_{pol.upper()}", {
            "short_name": SHORT[pol], "version": VERSION,
            "desde": args.desde, "hasta": args.hasta,
            "aoi": [a.__dict__ for a in aois], "antartica": False,
            "temporal": "native scanline time; no hourly interpolation",
            "variable_policy": (
                "gas+precision, qa/time/bounds, AMF/cloud/surface/snow/angles; "
                "no averaging_kernel"),
            "dry_run": args.dry_run, "mascara_sha256": mascara_sha,
            "unidades_administrativas": (resumen_mascara(args.comunas)
                                           if args.comunas.exists() else None),
        })
        log.info("=== TROPOMI %s: %d AOIs, tiempo nativo ===", pol.upper(), len(aois))
        if args.dry_run:
            mani.terminar("dry_run")
            continue

        for patron in ("*.part", "*.download"):
            for huerfano in tmp.glob(patron):
                huerfano.unlink(missing_ok=True)
        limpiar_tmp(destino)
        comunes = dict(
            pol=pol, comunas=args.comunas, mascara_sha256=mascara_sha,
            conservar_global=args.conservar_global, mani=mani,
        )
        _backlog(tmp, destino, aois, **comunes)
        if args.migrar_legado_continental:
            continente = next((a for a in seleccionar("todos", args.comunas)
                                if a.id == "continente"), None)
            if continente is None:
                raise SystemExit("no se pudo derivar AOI continente")
            patron_nuevo = re.compile(
                r"\.(continente|juan_fernandez|desventuradas|rapa_nui|"
                r"sala_y_gomez)\.chile\.nc$")
            legados = sorted(
                p for p in destino.glob("*.chile.nc")
                if not patron_nuevo.search(p.name))
            mani.registrar({
                "evento": "inicio_migracion_legado_continental",
                "archivos": len(legados),
                "sin_descarga_red": True,
                "limitacion": ("el rectángulo legado sólo contiene continente; "
                               "las islas se completan desde órbitas globales"),
                "espacio_minimo_gb": args.espacio_minimo_gb,
            })
            fallos_migracion = 0
            for i, src in enumerate(legados, 1):
                libres = shutil.disk_usage(destino).free / 2**30
                if libres < args.espacio_minimo_gb:
                    mani.terminar("abortado_espacio", procesados=i - 1,
                                  pendientes=len(legados) - i + 1,
                                  libres_gib=libres)
                    raise SystemExit(
                        f"quedan {libres:.1f} GiB; reserva mínima "
                        f"{args.espacio_minimo_gb:.1f} GiB")
                try:
                    _procesar(
                        src, destino, (continente,), temporal=False, url=None,
                        **comunes)
                except Exception as exc:
                    fallos_migracion += 1
                    log.warning("Legado TROPOMI %s falló: %s", src.name, exc)
                if i % 25 == 0 or i == len(legados):
                    log.info("Migración compacta %s: %d/%d; fallos=%d",
                             pol.upper(), i, len(legados), fallos_migracion)
            mani.terminar(
                "completo" if not fallos_migracion else "con_fallos",
                migrados=len(legados) - fallos_migracion,
                fallos=fallos_migracion,
            )
            if fallos_migracion:
                raise SystemExit(1)
            continue
        if args.recortar_backlog:
            _backlog(destino, destino, aois, **comunes)
        if args.solo_recortar:
            mani.terminar()
            continue

        import earthaccess
        granulos: dict[str, object] = {}
        aois_por_nombre: dict[str, set[str]] = {}
        conteo: dict[str, int] = {}
        for aoi in aois:
            resultados = earthaccess.search_data(
                short_name=SHORT[pol], version=VERSION,
                bounding_box=aoi.bbox, temporal=(args.desde, args.hasta),
            )
            conteo[aoi.id] = len(resultados)
            for g in resultados:
                nombre = _nombre(g)
                if not nombre:
                    continue
                granulos.setdefault(nombre, g)
                aois_por_nombre.setdefault(nombre, set()).add(aoi.id)
        mani.registrar({
            "evento": "consulta_cmr", "granulos_por_aoi": conteo,
            "granulos_unicos": len(granulos),
        })
        por_id = {a.id: a for a in aois}
        pendientes = []
        for nombre, g in granulos.items():
            relevantes = tuple(por_id[x] for x in sorted(aois_por_nombre[nombre]))
            if not _salidas_validas(nombre, destino, relevantes, mascara_sha, mani):
                pendientes.append((nombre, g, relevantes))
        log.info("%d órbitas únicas; %d pendientes", len(granulos), len(pendientes))

        fallos = 0
        for inicio in range(0, len(pendientes), LOTE):
            lote = pendientes[inicio:inicio + LOTE]
            por_nombre = {nombre: (g, relevantes) for nombre, g, relevantes in lote}
            descargados = earthaccess.download([x[1] for x in lote], str(tmp)) or []
            for archivo in descargados:
                if not archivo:
                    continue
                src = Path(archivo)
                item = por_nombre.get(src.name) or por_nombre.get(unquote(src.name))
                if item is None:
                    fallos += 1
                    mani.registrar({"evento": "descarga_nombre_no_asociado",
                                    "granule_id": src.name})
                    src.unlink(missing_ok=True)
                    continue
                g, relevantes = item
                _procesar(src, destino, relevantes, url=_url(g), temporal=True,
                          **comunes)
            for nombre, _, relevantes in lote:
                if not _salidas_validas(
                        nombre, destino, relevantes, mascara_sha, mani):
                    fallos += 1
                    mani.registrar({"evento": "granulo_incompleto_post_lote",
                                    "granule_id": nombre})
            log.info("... %d/%d órbitas procesadas",
                     min(inicio + LOTE, len(pendientes)), len(pendientes))
        mani.terminar("completo" if not fallos else "con_fallos",
                      granulos_unicos=len(granulos), pendientes=len(pendientes),
                      fallos=fallos)
        if fallos:
            raise SystemExit(1)

    log.info("Listo TROPOMI.")


if __name__ == "__main__":
    main()
