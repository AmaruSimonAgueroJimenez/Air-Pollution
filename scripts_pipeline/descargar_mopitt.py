#!/usr/bin/env python3
"""LEGADO OPT-IN: MOPITT MOP03J L3, no máxima resolución instrumental.

Procesa una grilla global por vez, produce recortes separados para Chile
continental, Juan Fernández/Desventuradas y Rapa Nui/Sala y Gómez, valida cada
salida y sólo entonces elimina el HDF temporal. MOPITT L3 es diario a 1° y
contiene campos Day/Night; no posee una serie horaria ni se interpola como tal.
Es la resolución nativa de MOP03J L3, pero MOP02J L2 v10 conserva observaciones
de ~22 km y tiempo de pasada; L2 debe añadirse antes de declarar máxima
resolución instrumental.

Este script queda deshabilitado por defecto. Sólo se ejecuta con
``--permitir-l3-legado`` para comparaciones explícitas; el pipeline principal
debe usar MOP02J L2 y no conservar L3 en el disco final.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import AOI, resumen_mascara, seleccionar  # noqa: E402
from _common import CONTAMINANTES, DATA, ensure_dir, get_logger  # noqa: E402
from _env_earthdata import login  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, sha256, sha256_conjunto_shapefile, url_publica,
)
from _recorte_grillas_nativas import (  # noqa: E402
    nombre_hdf_recortado, recortar_mopitt, validar_mopitt,
)

log = get_logger("mopitt")
SHORT = "MOP03J"
RES = 1.0


def _version_fuente(path: Path, version_cmr: str) -> str:
    """Distingue backlog v8 de descargas nuevas v10 sin inventar procedencia."""
    m = re.search(r"L3V(\d+(?:\.\d+)*)", Path(path).name, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    try:
        import h5py
        with h5py.File(path, "r") as h:
            for clave in ("VersionID", "Version", "version", "ProductionVersion"):
                if clave in h.attrs:
                    valor = h.attrs[clave]
                    if isinstance(valor, bytes):
                        valor = valor.decode("utf-8", errors="replace")
                    return str(valor)
    except (OSError, ValueError):
        pass
    return f"CMR-{version_cmr}; no codificada en archivo"


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


def _bbox(aoi: AOI):
    lon0, lat0, lon1, lat1 = aoi.bbox
    return lon0 - 0.500001, lat0 - 0.500001, lon1 + 0.500001, lat1 + 0.500001


def _salida(nombre: str, aoi: AOI):
    return nombre_hdf_recortado(nombre, sufijo=f".{aoi.id}.chile.he5")


def _salidas_validas(nombre: str, dest: Path, aois: tuple[AOI, ...],
                     mani: Manifiesto) -> bool:
    todas = True
    for aoi in aois:
        path = dest / _salida(nombre, aoi)
        if not path.exists():
            todas = False
            continue
        try:
            validar_mopitt(path, _bbox(aoi))
        except Exception as exc:
            path.unlink(missing_ok=True)
            mani.registrar({"evento": "salida_invalida_eliminada", "ruta": str(path),
                            "error": f"{type(exc).__name__}: {exc}"})
            todas = False
    return todas


def _pixeles(path: Path) -> int:
    import h5py
    with h5py.File(path, "r") as h:
        return int(h["ChileSubset/toca_chile"][:].sum())


def _procesar(src: Path, dest: Path, aois: tuple[AOI, ...], *, version: str,
             comunas: Path, conservar_global: bool, mani: Manifiesto,
             url: str | None, temporal: bool):
    salidas = []
    try:
        version_archivo = _version_fuente(src, version)
        for aoi in aois:
            bbox = _bbox(aoi)
            out = recortar_mopitt(src, dest, bbox, comunas_path=comunas,
                                  etiqueta=aoi.id)
            salidas.append((out, aoi, bbox))
        checksum_fuente = sha256(src)
        borrado = not conservar_global
        if borrado:
            src.unlink(missing_ok=True)
        for out, aoi, bbox in salidas:
            mani.archivo(
                salida=out, version=version_archivo, granule_id=src.name, url=url,
                aoi_id=aoi.id, territorio=aoi.territorio, bbox=bbox,
                resolucion="1 grado", tiempo_nativo="daily; Day/Night fields",
                qa="campos de error/variabilidad/NumberofPixels nativos conservados",
                pixeles=_pixeles(out),
                mascara=(f"{comunas}; toca_chile conserva celdas insulares; "
                         "cod_comuna sólo por centro"),
                validacion="HDF5 reabierto; campos, formas y coordenadas verificados",
                crudo_eliminado=borrado, crudo=src,
                checksum_fuente=checksum_fuente)
        return [x[0] for x in salidas]
    except BaseException as exc:
        descartado = temporal and not conservar_global
        if descartado:
            src.unlink(missing_ok=True)
        mani.registrar({"evento": "archivo_fallido", "granule_id": src.name,
                        "url": url, "error": f"{type(exc).__name__}: {exc}",
                        "crudo_temporal_descartado": descartado})
        raise


def _backlog(carpeta: Path, dest: Path, aois, **kw):
    fuentes = sorted(p for p in carpeta.glob("*.he5") if ".chile.he5" not in p.name)
    fallos = 0
    for i, src in enumerate(fuentes, 1):
        try:
            _procesar(src, dest, aois, temporal=carpeta.name == "_tmp_global", **kw)
        except Exception as exc:
            fallos += 1
            log.warning("Backlog %s falló: %s", src.name, exc)
        if i % 100 == 0:
            log.info("  backlog %d/%d", i, len(fuentes))
    return fallos


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default="10",
                    help="version_id CMR (10, no 010)")
    ap.add_argument("--desde", default="2000-03-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--aoi", default="todos")
    ap.add_argument("--solo-recortar", action="store_true")
    ap.add_argument("--recortar-backlog", action="store_true")
    ap.add_argument("--conservar-global", action="store_true")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--permitir-l3-legado", action="store_true",
                    help="opt-in explícito; MOP03J no es máxima resolución")
    args = ap.parse_args(argv)
    if not args.permitir_l3_legado:
        ap.error("MOPITT L3 está deshabilitado: usa MOP02J L2; para una "
                 "comparación legado añade --permitir-l3-legado")
    try:
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except ValueError as exc:
        ap.error(str(exc))
    if not args.dry_run and not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")
    if not (args.dry_run or args.solo_recortar):
        login()

    base = CONTAMINANTES / "MOPITT_CO"
    tmp, dest = ensure_dir(base / "_tmp_global"), ensure_dir(base / "raw_chile")
    mani = Manifiesto(base / "_manifiestos", "MOPITT_CO", {
        "short_name": SHORT, "version": args.version, "desde": args.desde,
        "hasta": args.hasta, "aoi": [a.__dict__ for a in aois],
        "temporal": "daily_day_night", "resolucion_grados": RES,
        "nivel_producto": "L3", "maxima_resolucion_instrumental": False,
        "estado_pipeline": "legacy_opt_in_no_conservar_en_disco_final",
        "l2_mayor_resolucion_pendiente": "MOP02J v10 (~22 km; tiempo de pasada)",
        "antartica": False, "dry_run": args.dry_run,
        "mascara_sha256": (sha256_conjunto_shapefile(args.comunas)
                            if args.comunas.exists() else None),
        "unidades_administrativas": (resumen_mascara(args.comunas)
                                       if args.comunas.exists() else None),
    })
    log.warning("MOPITT usa MOP03J L3; MOP02J L2 ofrece mayor resolución")
    if args.dry_run:
        mani.terminar("dry_run")
        return
    for patron in ("*.part", "*.tmp", "*.download"):
        for huerfano in tmp.glob(patron):
            huerfano.unlink(missing_ok=True)
            mani.registrar({"evento": "temporal_incompleto_eliminado",
                            "ruta": str(huerfano)})
    comunes = dict(version=args.version, comunas=args.comunas,
                   conservar_global=args.conservar_global, mani=mani, url=None)
    fallos_backlog = _backlog(tmp, dest, aois, **comunes)
    if args.recortar_backlog:
        fallos_backlog += _backlog(dest, dest, aois, **comunes)
    if args.solo_recortar:
        mani.terminar("completo" if not fallos_backlog else "con_fallos",
                      fallos=fallos_backlog)
        if fallos_backlog:
            raise SystemExit(1)
        return

    import earthaccess
    por_nombre, conteo = {}, {}
    for aoi in aois:
        rs = earthaccess.search_data(short_name=SHORT, version=args.version,
                                     bounding_box=aoi.bbox,
                                     temporal=(args.desde, args.hasta))
        conteo[aoi.id] = len(rs)
        for g in rs:
            por_nombre[_nombre(g) or f"sin_nombre_{id(g)}"] = g
    mani.registrar({"evento": "consulta_cmr", "granulos_por_aoi": conteo,
                    "granulos_unicos": len(por_nombre)})
    pendientes = []
    for nombre, g in por_nombre.items():
        if (not nombre.startswith("sin_nombre_") and
                _salidas_validas(nombre, dest, aois, mani)):
            continue
        pendientes.append(g)
    fallos = fallos_backlog
    for i, g in enumerate(pendientes, 1):
        try:
            fs = earthaccess.download([g], str(tmp)) or []
            if not fs:
                raise RuntimeError("Earthaccess no devolvió archivo")
            for f in fs:
                _procesar(Path(f), dest, aois, version=args.version,
                         comunas=args.comunas,
                         conservar_global=args.conservar_global, mani=mani,
                         url=_url(g), temporal=True)
        except Exception as exc:
            fallos += 1
            nombre_fallido = _nombre(g)
            candidato = tmp / nombre_fallido if nombre_fallido else None
            if candidato and candidato.exists() and not args.conservar_global:
                candidato.unlink(missing_ok=True)
                mani.registrar({"evento": "temporal_descarga_fallida_eliminado",
                                "ruta": str(candidato)})
            log.warning("MOPITT %d/%d falló: %s", i, len(pendientes), exc)
        if i % 100 == 0 or i == len(pendientes):
            log.info("  MOPITT %d/%d", i, len(pendientes))
    mani.terminar("completo" if not fallos else "con_fallos", fallos=fallos)
    if fallos:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
