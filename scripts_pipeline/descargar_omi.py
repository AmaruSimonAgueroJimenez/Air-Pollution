#!/usr/bin/env python3
"""LEGADO OPT-IN: Aura OMI L3 diario, no máxima resolución instrumental.

CMR sólo usa el bbox para encontrar gránulos: los HDF descargados continúan
siendo globales. Cada global se descarga una vez, se recorta por AOIs compactas
de continente, Juan Fernández/Desventuradas y Rapa Nui/Sala y Gómez, conserva
todos los píxeles nativos y se elimina únicamente cuando todos los recortes
solicitados fueron validados. No incluye Antártica.

OMI L3 es diario (NO2/SO2 0,25°; O3 1°); nunca se inventan horas.
Es la máxima resolución nativa de estas colecciones L3, no del instrumento:
OMNO2/OMSO2/OMTO3 L2 v004 conservan huella y tiempo de pasada más finos y
requieren un descargador swath separado antes de declarar cobertura máxima.

Este script queda deshabilitado por defecto. Sólo se ejecuta con
``--permitir-l3-legado`` para una comparación científica explícita; el pipeline
principal debe usar OMI L2 swath y no conservar L3 en el disco final.
"""
from __future__ import annotations

import argparse
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
    nombre_hdf_recortado, recortar_omi, validar_omi,
)

log = get_logger("omi")
SHORT = {"no2": "OMNO2d", "o3": "OMTO3d", "so2": "OMSO2e"}
VER = {"no2": "004", "o3": "004", "so2": "004"}
RES = {"no2": 0.25, "so2": 0.25, "o3": 1.0}


def _nombre_granulo(g) -> str:
    try:
        return g.data_links()[0].rsplit("/", 1)[-1].split("?", 1)[0]
    except Exception:
        return ""


def _url_granulo(g) -> str | None:
    try:
        return url_publica(g.data_links()[0])
    except Exception:
        return None


def _bbox_con_huella(aoi: AOI, resolucion: float):
    # Incluye el centro de celdas gruesas cuya huella toca una isla pequeña.
    lon0, lat0, lon1, lat1 = aoi.bbox
    m = resolucion / 2 + 1e-6
    return lon0 - m, lat0 - m, lon1 + m, lat1 + m


def _nombre_salida(nombre: str, aoi: AOI) -> str:
    return nombre_hdf_recortado(nombre, sufijo=f".{aoi.id}.chile.he5")


def _salidas_validas(nombre: str, destino: Path, pol: str,
                     aois: tuple[AOI, ...], mani: Manifiesto) -> bool:
    todas = True
    for aoi in aois:
        path = destino / _nombre_salida(nombre, aoi)
        if not path.exists():
            todas = False
            continue
        try:
            validar_omi(path, _bbox_con_huella(aoi, RES[pol]), pol)
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


def _procesar_fuente(src: Path, destino: Path, pol: str, aois: tuple[AOI, ...],
                     *, conservar_global: bool, comunas: Path,
                     manifiesto: Manifiesto, url: str | None,
                     temporal: bool) -> list[Path]:
    salidas: list[tuple[Path, AOI, tuple]] = []
    try:
        for aoi in aois:
            bbox = _bbox_con_huella(aoi, RES[pol])
            salida = recortar_omi(
                src, destino, bbox, producto=pol, comunas_path=comunas,
                etiqueta=aoi.id)
            salidas.append((salida, aoi, bbox))
        checksum_fuente = sha256(src)
        borrado = not conservar_global
        if borrado:
            src.unlink(missing_ok=True)
        for salida, aoi, bbox in salidas:
            manifiesto.archivo(
                salida=salida, version=VER[pol], granule_id=src.name, url=url,
                aoi_id=aoi.id, territorio=aoi.territorio, bbox=bbox,
                resolucion=f"{RES[pol]:g} grados",
                tiempo_nativo="daily", qa="QA/fill nativos OMI; sin promedio",
                pixeles=_pixeles(salida),
                mascara=(f"{comunas}; centro=cod_comuna; "
                         "huella=toca_chile; geometrías make_valid"),
                validacion="HDF5 reabierto, campos/forma/coordenadas verificados",
                crudo_eliminado=borrado, crudo=src,
                checksum_fuente=checksum_fuente)
        return [x[0] for x in salidas]
    except BaseException as exc:
        # Un temporal nuevo no queda abandonado: se podrá volver a descargar.
        # Los globales históricos de raw_chile no se destruyen si la migración
        # falla, porque no son copias transitorias.
        descartado = temporal and not conservar_global
        if descartado:
            src.unlink(missing_ok=True)
        manifiesto.registrar({
            "evento": "archivo_fallido", "granule_id": src.name,
            "url": url, "error": f"{type(exc).__name__}: {exc}",
            "crudo_temporal_descartado": descartado,
        })
        raise


def _backlog(carpeta: Path, destino: Path, pol: str, aois: tuple[AOI, ...],
             **kwargs) -> int:
    fuentes = sorted(p for p in carpeta.glob("*.he5") if ".chile.he5" not in p.name)
    fallos = 0
    for i, src in enumerate(fuentes, 1):
        try:
            _procesar_fuente(src, destino, pol, aois,
                             temporal=carpeta.name == "_tmp_global", **kwargs)
        except Exception as exc:
            fallos += 1
            log.warning("No se pudo migrar %s: %s", src.name, exc)
        if i % 100 == 0:
            log.info("  backlog %s: %d/%d", pol.upper(), i, len(fuentes))
    return fallos


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contaminantes", default="no2,o3,so2")
    ap.add_argument("--desde", default="2004-10-01")
    ap.add_argument("--hasta", default=date.today().isoformat())
    ap.add_argument("--aoi", default="todos",
                    help="todos o IDs/territorios separados por coma")
    ap.add_argument("--solo-recortar", action="store_true")
    ap.add_argument("--recortar-backlog", action="store_true",
                    help="migra globales históricos actualmente en raw_chile")
    ap.add_argument("--conservar-global", action="store_true",
                    help="sólo depuración; deja el global después de validar")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--permitir-l3-legado", action="store_true",
                    help="opt-in explícito; L3 no es la máxima resolución OMI")
    args = ap.parse_args(argv)

    if not args.permitir_l3_legado:
        ap.error("OMI L3 está deshabilitado: usa OMI L2 swath; para una "
                 "comparación legado añade --permitir-l3-legado")

    pols = [p.strip().lower() for p in args.contaminantes.split(",") if p.strip()]
    malos = [p for p in pols if p not in SHORT]
    if malos:
        ap.error(f"contaminantes inválidos: {malos}. Válidos: {list(SHORT)}")
    try:
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except ValueError as exc:
        ap.error(str(exc))
    if not args.dry_run and not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")
    if not (args.dry_run or args.solo_recortar):
        login()

    fallos_totales = 0
    for pol in pols:
        base = CONTAMINANTES / "OMI" / pol.upper()
        tmp, destino = ensure_dir(base / "_tmp_global"), ensure_dir(base / "raw_chile")
        mani = Manifiesto(base / "_manifiestos", f"OMI_{pol.upper()}", {
            "short_name": SHORT[pol], "version": VER[pol], "desde": args.desde,
            "hasta": args.hasta, "aoi": [a.__dict__ for a in aois],
            "temporal": "daily", "resolucion_grados": RES[pol],
            "nivel_producto": "L3",
            "estado_pipeline": "legacy_opt_in_no_conservar_en_disco_final",
            "maxima_resolucion_instrumental": False,
            "l2_mayor_resolucion_pendiente": {
                "no2": "OMNO2 v004", "so2": "OMSO2 v004",
                "o3": "OMTO3 v004",
            }[pol],
            "antartica": False, "dry_run": args.dry_run,
            "mascara_sha256": (sha256_conjunto_shapefile(args.comunas)
                                if args.comunas.exists() else None),
            "unidades_administrativas": (resumen_mascara(args.comunas)
                                           if args.comunas.exists() else None),
        })
        log.warning("OMI %s usa L3 diario; L2 swath ofrece mayor resolución ",
                    pol.upper())
        log.info("=== OMI %s: diario %g°, %d AOIs ===", pol.upper(), RES[pol], len(aois))
        if args.dry_run:
            mani.terminar("dry_run")
            continue

        for patron in ("*.part", "*.tmp", "*.download"):
            for huerfano in tmp.glob(patron):
                huerfano.unlink(missing_ok=True)
                mani.registrar({"evento": "temporal_incompleto_eliminado",
                                "ruta": str(huerfano)})

        comunes = dict(conservar_global=args.conservar_global,
                       comunas=args.comunas, manifiesto=mani, url=None)
        fallos_producto = _backlog(tmp, destino, pol, aois, **comunes)
        if args.recortar_backlog:
            fallos_producto += _backlog(destino, destino, pol, aois, **comunes)
        if args.solo_recortar:
            mani.terminar("completo" if not fallos_producto else "con_fallos",
                          fallos=fallos_producto)
            fallos_totales += fallos_producto
            continue

        import earthaccess
        # Consulta AOIs separadas; deduplica el mismo global diario antes de
        # descargarlo. Así se registra cobertura insular sin corredor oceánico.
        por_nombre = {}
        conteo_aoi = {}
        for aoi in aois:
            encontrados = earthaccess.search_data(
                short_name=SHORT[pol], version=VER[pol],
                bounding_box=aoi.bbox, temporal=(args.desde, args.hasta))
            conteo_aoi[aoi.id] = len(encontrados)
            for g in encontrados:
                nombre = _nombre_granulo(g)
                por_nombre[nombre or f"sin_nombre_{id(g)}"] = g
        mani.registrar({"evento": "consulta_cmr", "granulos_por_aoi": conteo_aoi,
                        "granulos_unicos": len(por_nombre)})

        pendientes = []
        for nombre, g in por_nombre.items():
            if (not nombre.startswith("sin_nombre_") and
                    _salidas_validas(nombre, destino, pol, aois, mani)):
                continue
            pendientes.append(g)
        log.info("%d globales pendientes de %d únicos", len(pendientes), len(por_nombre))
        fallos = fallos_producto
        for i, g in enumerate(pendientes, 1):
            try:
                archivos = earthaccess.download([g], str(tmp)) or []
                if not archivos:
                    raise RuntimeError("Earthaccess no devolvió archivo")
                for archivo in archivos:
                    _procesar_fuente(
                        Path(archivo), destino, pol, aois,
                        conservar_global=args.conservar_global,
                        comunas=args.comunas, manifiesto=mani,
                        url=_url_granulo(g), temporal=True)
            except Exception as exc:
                fallos += 1
                nombre_fallido = _nombre_granulo(g)
                candidato = tmp / nombre_fallido if nombre_fallido else None
                if candidato and candidato.exists() and not args.conservar_global:
                    candidato.unlink(missing_ok=True)
                    mani.registrar({"evento": "temporal_descarga_fallida_eliminado",
                                    "ruta": str(candidato)})
                log.warning("Gránulo %d/%d falló: %s", i, len(pendientes), exc)
            if i % 100 == 0 or i == len(pendientes):
                log.info("  %s %d/%d", pol.upper(), i, len(pendientes))
        mani.terminar("completo" if not fallos else "con_fallos", fallos=fallos)
        fallos_totales += fallos

    if fallos_totales:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
