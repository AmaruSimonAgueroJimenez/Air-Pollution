"""_common.py — utilidades compartidas del pipeline de descarga.

Rutas del repo, bounding box de Chile, carga de credenciales (../.env),
logging y reintentos con backoff. Todos los descargadores importan de aquí.
"""
from __future__ import annotations

import functools
import logging
import os
import time
from datetime import date
from pathlib import Path

# --- Rutas del repo y de los datos ---------------------------------
# El código y output_files/ permanecen en el repo. Los datos pesados viven en
# el disco externo y pueden reubicarse sin modificar los scripts.
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
_EXPLICIT_DATA_ROOT = os.environ.get("AIR_POLLUTION_DATA_ROOT")
_DATOS_VOLUME = Path("/Volumes/Datos")


def _require_fallback_volume(ruta: Path) -> None:
    """Evita escribir en el Mac si el punto de montaje quedó vacío."""
    if not _EXPLICIT_DATA_ROOT and \
            (ruta == _DATOS_VOLUME or _DATOS_VOLUME in ruta.parents) and \
            not _DATOS_VOLUME.is_mount():
        raise SystemExit(
            "El volumen externo /Volumes/Datos no está montado; se aborta "
            "para no crear datos en el disco interno. Conecta el disco o "
            "define AIR_POLLUTION_DATA_ROOT explícitamente."
        )


AIR_POLLUTION_DATA_ROOT = Path(
    _EXPLICIT_DATA_ROOT
    or Path(os.environ.get("ASESORIAS_DATA_ROOT", "/Volumes/Datos/Asesorias_Data"))
    / "AirPollution" / "data"
).expanduser().resolve()
_require_fallback_volume(AIR_POLLUTION_DATA_ROOT)
DATA = AIR_POLLUTION_DATA_ROOT
CONTAMINANTES = DATA / "contaminantes"
SINCA = DATA / "sinca"
OUTPUT = REPO_ROOT / "output_files"

# --- Compatibilidad: caja continental histórica (WGS84) -------------
# NO representa la cobertura total de Chile. Los descargadores satelitales
# nuevos usan ``aois_chile()`` para derivar continente e islas desde la máscara.
CHILE_BBOX = (-76.0, -56.5, -66.0, -17.0)


def aois_chile(comunas_path: Path | None = None, margen: float = 0.05):
    """AOIs administrativas derivadas de la máscara, excluyendo Antártica."""
    from _chile_aoi import derivar
    return derivar(comunas_path or (DATA / "comunas.shp"), margen=margen)


def bbox_area_cds():
    """CDS/ADS espera area = [Norte, Oeste, Sur, Este]."""
    lon_min, lat_min, lon_max, lat_max = CHILE_BBOX
    return [lat_max, lon_min, lat_min, lon_max]


def bbox_earthaccess():
    """earthaccess espera (lon_min, lat_min, lon_max, lat_max)."""
    return tuple(CHILE_BBOX)


# --- .env -----------------------------------------------------------
def load_env(dotenv: Path | None = None) -> None:
    """Carga ../.env (KEY=VALUE) en os.environ, sin dependencias externas."""
    dotenv = dotenv or (REPO_ROOT / ".env")
    if not dotenv.exists():
        return
    for line in dotenv.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and not os.environ.get(k):
            os.environ[k] = v


def require_env(*claves: str) -> None:
    """Aborta con un mensaje claro si falta alguna credencial."""
    load_env()
    faltan = [c for c in claves if not os.environ.get(c)]
    if faltan:
        raise SystemExit(
            "Faltan credenciales en ../.env: " + ", ".join(faltan) +
            "\nCopia .env.example a .env y complétalas."
        )


# --- logging --------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)


# --- reintentos -----------------------------------------------------
def retry(n: int = 4, base: float = 2.0, exc=Exception):
    """Decorador: reintenta con backoff exponencial.

    CMR / GES DISC / SINCA devuelven 500 intermitentes; esto los absorbe.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **k):
            last = None
            for i in range(n):
                try:
                    return fn(*a, **k)
                except exc as e:  # noqa: BLE001
                    last = e
                    wait = base * (2 ** i)
                    logging.getLogger(fn.__module__).warning(
                        "intento %d/%d falló (%s); reintento en %.0fs",
                        i + 1, n, e, wait,
                    )
                    time.sleep(wait)
            raise last  # type: ignore[misc]
        return wrap
    return deco


def ensure_dir(p: Path) -> Path:
    _require_fallback_volume(AIR_POLLUTION_DATA_ROOT)
    p.mkdir(parents=True, exist_ok=True)
    return p


def add_common_args(parser):
    """--desde / --hasta / --dry-run comunes a todos los descargadores."""
    parser.add_argument("--desde", default="2000-01-01", help="fecha inicio YYYY-MM-DD")
    parser.add_argument("--hasta", default=date.today().isoformat(),
                        help="fecha fin YYYY-MM-DD (por defecto hoy)")
    parser.add_argument("--dry-run", action="store_true",
                        help="lista lo que bajaría, sin descargar")
    return parser


# Contaminantes objetivo del proyecto.
CONTAMINANTES_OBJETIVO = ["pm25", "pm10", "no2", "o3", "so2", "co"]
