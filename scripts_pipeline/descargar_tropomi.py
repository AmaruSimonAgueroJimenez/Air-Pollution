#!/usr/bin/env python3
"""descargar_tropomi.py — Sentinel-5P TROPOMI (gases) vía NASA Earthdata.

Descarga gránulos L2 (productos OFFL/HiR de GES DISC) para NO2, O3, SO2 y CO
y los RECORTA a Chile al vuelo: cada gránulo es una órbita completa de polo a
polo (~600 MB) de la que solo ~5% de los píxeles caen sobre Chile. El gránulo
global se baja a `<POL>/_tmp_global/`, se recorta a `<POL>/raw_chile/` (~4% del
tamaño, ~23 MB) y el global se borra de inmediato.

El recorte conserva TODAS las variables y la resolución nativa (ver
`_recorte_tropomi.py`): solo desaparece la geografía fuera del bbox de Chile.
Sin recorte, solo NO2 ocuparía ~4 TB.

Si quedan gránulos globales de una corrida anterior en `_tmp_global/`, primero
los recorta y los elimina. Es seguro relanzarlo: salta lo ya recortado.

TROPOMI cubre 2018-04 en adelante (HiR ~5.5 km desde 2019-08). Requiere
credenciales NASA Earthdata.

short_names verificados en CMR (GES DISC), versión 2:
  NO2 S5P_L2__NO2____HiR · O3 S5P_L2__O3_TOT_HiR · SO2 S5P_L2__SO2____HiR · CO S5P_L2__CO_____HiR

Uso:
  python descargar_tropomi.py --contaminantes no2,o3,so2,co \
      --desde 2019-01-01 --hasta 2024-12-31
  python descargar_tropomi.py --solo-recortar     # procesa el backlog y sale
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CHILE_BBOX, CONTAMINANTES, ensure_dir, get_logger  # noqa: E402
from _env_earthdata import login  # noqa: E402
from _recorte_tropomi import limpiar_tmp, recortar  # noqa: E402

log = get_logger("tropomi")

# short_names OFFL/HiR verificados en CMR, todos versión 2.
SHORT = {
    "no2": "S5P_L2__NO2____HiR",
    "o3": "S5P_L2__O3_TOT_HiR",
    "so2": "S5P_L2__SO2____HiR",
    "co": "S5P_L2__CO_____HiR",
}
VERSION = "2"
LOTE = 4  # gránulos por tanda (~2.4 GB de tránsito máximo en _tmp_global)


def nombre_recortado(nombre_global: str) -> str:
    return nombre_global.removesuffix(".nc") + ".chile.nc"


def _procesar(f: Path, destino: Path) -> None:
    """Recorta un gránulo global y lo borra; los ilegibles también se borran."""
    try:
        if recortar(f, destino, CHILE_BBOX) is None:
            log.info("  %s no cruza Chile; lo descarto", f.name)
    except Exception as e:  # truncado/corrupto: se re-descargará
        log.warning("  gránulo ilegible %s (%s); lo borro para re-descargar",
                    f.name, e)
    f.unlink(missing_ok=True)


def recortar_pendientes(tmp: Path, destino: Path) -> None:
    """Procesa gránulos globales huérfanos de corridas anteriores."""
    n_tmp = limpiar_tmp(destino)
    if n_tmp:
        log.info("Barridos %d recortes .tmp huérfanos de una interrupción previa",
                 n_tmp)
    globales = sorted(f for f in tmp.glob("*.nc") if ".chile." not in f.name)
    if not globales:
        return
    log.info("Recortando %d gránulos globales de corridas anteriores ...",
             len(globales))
    for k, f in enumerate(globales, 1):
        _procesar(f, destino)
        if k % 25 == 0:
            log.info("  ... %d/%d recortados", k, len(globales))
    log.info("Recorte de pendientes listo (%d).", len(globales))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contaminantes", default="no2,o3,so2,co")
    ap.add_argument("--desde", default="2019-01-01")
    ap.add_argument("--hasta", default="2024-12-31")
    ap.add_argument("--solo-recortar", action="store_true",
                    help="procesa el backlog de _tmp_global y termina")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    pols = [p.strip().lower() for p in args.contaminantes.split(",") if p.strip()]
    malos = [p for p in pols if p not in SHORT]
    if malos:
        ap.error(f"contaminantes inválidos: {malos}. Válidos: {list(SHORT)}")

    if not (args.dry_run or args.solo_recortar):
        login()

    for pol in pols:
        base = CONTAMINANTES / "S5P_TROPOMI" / pol.upper()
        tmp, destino = base / "_tmp_global", base / "raw_chile"
        ensure_dir(tmp)
        ensure_dir(destino)
        log.info("=== TROPOMI %s (%s v%s) — recorte a Chile al vuelo ===",
                 pol.upper(), SHORT[pol], VERSION)

        if args.dry_run:
            log.info("[dry-run] %s %s→%s → %s", SHORT[pol], args.desde,
                     args.hasta, destino)
            continue

        recortar_pendientes(tmp, destino)
        if args.solo_recortar:
            continue

        import earthaccess
        results = earthaccess.search_data(
            short_name=SHORT[pol], version=VERSION,
            bounding_box=tuple(CHILE_BBOX), temporal=(args.desde, args.hasta))
        log.info("%d gránulos en CMR", len(results))

        # los .vacio marcan gránulos que no cruzan Chile; sin contarlos se
        # re-descargarían 600 MB en cada corrida
        hechos = ({p.name for p in destino.glob("*.chile.nc")} |
                  {p.name.removesuffix(".vacio")
                   for p in destino.glob("*.chile.nc.vacio")})
        pendientes = []
        for g in results:
            try:
                nombre = g.data_links()[0].rsplit("/", 1)[-1]
            except Exception:
                pendientes.append(g)
                continue
            if nombre_recortado(nombre) not in hechos:
                pendientes.append(g)
        log.info("%d por descargar (%d ya recortados)", len(pendientes),
                 len(hechos))

        for i in range(0, len(pendientes), LOTE):
            for f in earthaccess.download(pendientes[i:i + LOTE], str(tmp)):
                if f:
                    _procesar(Path(f), destino)
            if (i // LOTE) % 25 == 0:
                log.info("... %d/%d gránulos procesados",
                         min(i + LOTE, len(pendientes)), len(pendientes))

        log.info("Listo %s: %d gránulos recortados en %s", pol.upper(),
                 len(list(destino.glob("*.chile.nc"))), destino)

    log.info("Listo TROPOMI.")


if __name__ == "__main__":
    main()
