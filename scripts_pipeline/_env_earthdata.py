"""_env_earthdata.py — Autenticación NASA Earthdata para earthaccess.

Usa EARTHDATA_USERNAME/PASSWORD (o ~/.netrc) para TROPOMI, OMI, MOPITT,
MERRA-2 y MODIS. Expone `login()` y un helper `buscar_y_descargar()`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ensure_dir, get_logger, load_env  # noqa: E402

log = get_logger("earthdata")


def login():
    """Devuelve una sesión earthaccess autenticada (o aborta con instrucciones)."""
    load_env()
    try:
        import earthaccess
    except ImportError as e:
        raise SystemExit("Falta 'earthaccess'. Instala: pip install earthaccess") from e

    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"):
        auth = earthaccess.login(strategy="environment", persist=True)
    else:
        auth = earthaccess.login(strategy="netrc")  # ~/.netrc

    if not auth or not getattr(auth, "authenticated", False):
        raise SystemExit(
            "No se pudo autenticar en NASA Earthdata. Revisa EARTHDATA_USERNAME/"
            "PASSWORD en ../.env o ~/.netrc (regístrate en "
            "https://urs.earthdata.nasa.gov/)."
        )
    log.info("Autenticado en NASA Earthdata.")
    return auth


def buscar_y_descargar(short_name, bbox, desde, hasta, dest, *,
                       version=None, dry_run=False, count=-1):
    """Busca en CMR por short_name + bbox + rango temporal y descarga a `dest`."""
    ensure_dir(Path(dest))

    if dry_run:
        log.info("[dry-run] %s bbox=%s %s→%s → %s",
                 short_name, tuple(bbox), desde, hasta, dest)
        try:
            import earthaccess
        except ImportError:
            log.info("  (earthaccess no instalado; omito el conteo CMR)")
            return []
        try:
            kwargs = dict(short_name=short_name, bounding_box=tuple(bbox),
                          temporal=(desde, hasta))
            if version:
                kwargs["version"] = version
            results = earthaccess.search_data(**kwargs)
            log.info("  %d gránulos en CMR", len(results))
        except Exception as e:  # noqa: BLE001
            log.info("  (no se pudo consultar CMR ahora: %s)", e)
        return []

    import earthaccess
    kwargs = dict(short_name=short_name, bounding_box=tuple(bbox),
                  temporal=(desde, hasta))
    if version:
        kwargs["version"] = version
    if count and count > 0:
        kwargs["count"] = count
    log.info("Buscando %s en CMR (%s → %s) ...", short_name, desde, hasta)
    results = earthaccess.search_data(**kwargs)
    log.info("%d gránulos para %s", len(results), short_name)

    limite = limite_bytes_s()
    if not limite:
        try:
            files = earthaccess.download(results, str(dest))
        except Exception as e:  # noqa: BLE001
            # Un gránulo que CMR indexa pero el DAAC ya no sirve (404) abortaba
            # la colección entera; en ese caso se baja de a uno y se saltan los
            # rotos, dejando constancia en el log.
            log.warning("Descarga en lote falló (%s); paso a modo uno-a-uno",
                        str(e)[:120])
            files, rotos = [], []
            for g in results:
                try:
                    files += [f for f in (earthaccess.download([g], str(dest)) or []) if f]
                except Exception as e2:  # noqa: BLE001
                    rotos.append(str(e2)[:90])
            if rotos:
                log.warning("%d gránulos no disponibles en el DAAC (se omiten): %s",
                            len(rotos), rotos[0])
        log.info("Descargados %d archivos a %s", len(files), dest)
        return files

    # LIMITE_MBPS activo: gránulo a gránulo, durmiendo lo necesario para que
    # el promedio no supere el tope (ráfagas cortas a plena velocidad).
    import time
    log.info("Límite de descarga activo: %.0f Mbps (promedio)", limite * 8 / 1e6)
    files = []
    for k, g in enumerate(results, 1):
        try:
            nombre = g.data_links()[0].rsplit("/", 1)[-1]
        except Exception:
            nombre = ""
        ya_existia = bool(nombre) and (Path(dest) / nombre).exists()
        t0 = time.monotonic()
        fs = [f for f in (earthaccess.download([g], str(dest)) or []) if f]
        files += fs
        if not ya_existia:
            n_bytes = sum(os.path.getsize(f) for f in fs if os.path.exists(f))
            espera = n_bytes / limite - (time.monotonic() - t0)
            if espera > 0:
                time.sleep(espera)
        if k % 100 == 0:
            log.info("  ... %d/%d gránulos", k, len(results))
    log.info("Descargados %d archivos a %s", len(files), dest)
    return files


def limite_bytes_s() -> float:
    """Tope de descarga en bytes/s desde LIMITE_MBPS (megabits/s); 0 = sin tope."""
    v = os.environ.get("LIMITE_MBPS", "").strip()
    try:
        return float(v) * 1e6 / 8 if v else 0.0
    except ValueError:
        log.warning("LIMITE_MBPS=%r no es numérico; lo ignoro", v)
        return 0.0
