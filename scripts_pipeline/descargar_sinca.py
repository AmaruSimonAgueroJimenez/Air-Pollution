#!/usr/bin/env python3
"""descargar_sinca.py — Verdad-terreno SINCA para los 6 contaminantes.

Descarga las series por estación desde el exportador de SINCA
(``apub.tsindico2.cgi``) para PM2.5, PM10, NO2, O3, SO2 y CO, en resolución
horaria y/o diaria, y las guarda en ``data/sinca/<pol>/<res>/``.

Estaciones: ``data/sinca/config_sinca_estaciones.json`` (region, estacion, ...).
El exportador SINCA se llama así (ejemplo real de una estación de la RM):

  https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi
     ?outtype=xcl
     &macro=./RM/D15/Cal/PM25//PM25.horario.horario.ic
     &from=040101&to=241231
     &path=/usr/airviro/data/CONAMA/&lang=esp

donde el CÓDIGO del contaminante (ver ``PARAM_CODES``) aparece dos veces en
``macro``: como carpeta y como prefijo del archivo ``.ic``. Las estaciones que
no miden un contaminante devuelven vacío y se registran en
``no_disponibles.csv``.

Uso:
  python descargar_sinca.py --desde 2004-01-01 --hasta 2024-12-31 \
      --resolucion horario --contaminantes pm25,pm10,no2,o3,so2,co
  python descargar_sinca.py --limite 3 --dry-run     # prueba rápida
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SINCA, ensure_dir, get_logger, retry  # noqa: E402

log = get_logger("sinca")

BASE = "https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi"
AIRVIRO_PATH = "/usr/airviro/data/CONAMA/"

# Códigos de parámetro SINCA/Airviro. PM25/PM10 son nominales; los gases usan
# códigos numéricos. 0001=SO2 y 0003=NO2 están confirmados por URLs reales de
# estaciones; O3/CO son los códigos estándar de Airviro — si algún gas no baja
# en una estación, verifica el código en su ficha SINCA (pestaña "Registros").
PARAM_CODES = {
    "pm25": "PM25",
    "pm10": "PM10",
    "so2": "0001",
    "no2": "0003",
    "o3": "0008",
    "co": "0004",
}

# Resolución -> sufijo del parámetro `macro`.
RES_SUFIJO = {"horario": "horario", "diario": "diario"}


def yymmdd(fecha_iso: str) -> str:
    return datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%y%m%d")


@retry(n=4, base=3.0, exc=(requests.RequestException,))
def _get(params: dict) -> requests.Response:
    r = requests.get(BASE, params=params, timeout=120)
    r.raise_for_status()
    return r


def descargar_serie(region, estacion, code, res, desde, hasta, dest: Path,
                    dry_run=False):
    """Descarga una serie (estacion x contaminante x resolucion). Devuelve
    (ruta | None, n_bytes)."""
    params = {
        "outtype": "xcl",
        # todo en un solo `macro` con ruta completa y extensión .ic; con
        # macropath+macro separados el exportador responde "Could not load
        # macro ... /indico/..." y ninguna serie baja
        "macro": f"./{region}/{estacion}/Cal/{code}//{code}.{res}.{res}.ic",
        "from": yymmdd(desde),
        "to": yymmdd(hasta),
        "path": AIRVIRO_PATH,
        "lang": "esp",
        "rsrc": "",
    }
    if dry_run:
        pedido = requests.Request("GET", BASE, params=params).prepare().url
        log.info("  [dry-run] %s", pedido)
        return None, 0

    resp = _get(params)
    texto = resp.text
    # Respuesta útil = tabla con datos; vacía/errores = HTML corto o "sin datos".
    util = len(texto) > 400 and ("Sin datos" not in texto) and \
        ("no existe" not in texto.lower())
    if not util:
        return None, 0
    ensure_dir(dest)
    fn = dest / f"{region}_{estacion}_{res}_{desde}_{hasta}.csv"
    fn.write_text(texto, encoding="utf-8", errors="replace")
    return fn, len(texto.encode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2004-01-01", help="YYYY-MM-DD")
    ap.add_argument("--hasta", default="2024-12-31", help="YYYY-MM-DD")
    ap.add_argument("--resolucion", default="horario",
                    choices=["horario", "diario", "ambas"])
    ap.add_argument("--contaminantes", default=",".join(PARAM_CODES),
                    help="lista separada por comas (pm25,pm10,no2,o3,so2,co)")
    ap.add_argument("--config", default=str(SINCA / "config_sinca_estaciones.json"))
    ap.add_argument("--limite", type=int, default=0,
                    help="procesa solo las primeras N estaciones (para probar)")
    ap.add_argument("--pausa", type=float, default=0.5,
                    help="segundos entre peticiones (cortesía)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    pols = [p.strip().lower() for p in args.contaminantes.split(",") if p.strip()]
    desconocidos = [p for p in pols if p not in PARAM_CODES]
    if desconocidos:
        ap.error(f"contaminantes desconocidos: {desconocidos}. Válidos: {list(PARAM_CODES)}")
    resoluciones = ["horario", "diario"] if args.resolucion == "ambas" else [args.resolucion]

    estaciones = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.limite:
        estaciones = estaciones[: args.limite]
    log.info("%d estaciones · contaminantes=%s · resoluciones=%s",
             len(estaciones), pols, resoluciones)

    manifiesto, faltantes = [], []
    for i, est in enumerate(estaciones, 1):
        region, estacion = est["region"], str(est["estacion"])
        nombre = est.get("nombre", "")
        for pol in pols:
            code = PARAM_CODES[pol]
            for res in resoluciones:
                dest = SINCA / pol / res
                try:
                    ruta, nb = descargar_serie(region, estacion, code, res,
                                               args.desde, args.hasta, dest,
                                               dry_run=args.dry_run)
                except Exception as e:  # noqa: BLE001
                    log.error("  %s/%s %s/%s: %s", region, estacion, pol, res, e)
                    faltantes.append([region, estacion, nombre, pol, res, f"error: {e}"])
                    continue
                if ruta:
                    log.info("  ✓ %s %s %s/%s (%d KB)", region, estacion, pol, res, nb // 1024)
                    manifiesto.append([region, estacion, nombre, pol, res, str(ruta), nb])
                else:
                    faltantes.append([region, estacion, nombre, pol, res, "sin datos"])
                if not args.dry_run:
                    time.sleep(args.pausa)
        if i % 10 == 0:
            log.info("… %d/%d estaciones", i, len(estaciones))

    if not args.dry_run:
        ensure_dir(SINCA)
        with open(SINCA / "manifiesto_descarga.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["region", "estacion", "nombre", "contaminante", "resolucion", "ruta", "bytes"])
            w.writerows(manifiesto)
        with open(SINCA / "no_disponibles.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["region", "estacion", "nombre", "contaminante", "resolucion", "motivo"])
            w.writerows(faltantes)
        log.info("Listo: %d series descargadas, %d sin datos. Ver manifiesto_descarga.csv",
                 len(manifiesto), len(faltantes))


if __name__ == "__main__":
    main()
