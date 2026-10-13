"""Traza de procedencia de los artefactos v2 (``DISENO_AMBIENTAL_V2.md`` §0, «Procedencia»).

Cada artefacto v2 lleva:

* el commit del repositorio y la lista de archivos de ``v2/`` con cambios sin commit (el código nuevo
  todavía no está en git, así que el commit solo no lo identifica);
* el hash del código v2: sha256 conjunto de ``v2/*.py`` (sin las pruebas), más el de cada archivo;
* el sha256 del contrato, de la configuración y de cada insumo;
* las versiones de las bibliotecas, sin importarlas (``importlib.metadata``);
* los hilos configurados y las semillas.

Las rutas se registran relativas a su raíz (``raiz_v1``, ``raiz_v2``, ``datos`` o ``repo``), nunca absolutas.
``git`` se llama con ``--no-optional-locks`` para no reescribir el índice del repositorio.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rutas_v2 import RutasV2, a_json, ahora_utc, rutas_v2  # noqa: E402

BIBLIOTECAS = ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn", "lightgbm", "xgboost", "statsmodels",
               "pyproj", "joblib", "threadpoolctl")
VARIABLES_HILOS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                   "NUMEXPR_NUM_THREADS")

_CACHE_SHA: dict[tuple, str] = {}


def sha256_archivo(ruta, bloque: int = 8 << 20) -> str:
    """sha256 de un archivo, memoizado por (ruta, tamaño, mtime): un panel de 780 MB se lee una sola vez."""
    p = Path(ruta).resolve()
    st = p.stat()
    clave = (str(p), st.st_size, st.st_mtime_ns)
    if clave not in _CACHE_SHA:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for b in iter(lambda: fh.read(bloque), b""):
                h.update(b)
        _CACHE_SHA[clave] = h.hexdigest()
    return _CACHE_SHA[clave]


def json_canonico(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=a_json)


def sha256_json(obj) -> str:
    """sha256 de la forma canónica (claves ordenadas, sin espacios): no depende del orden de inserción."""
    return hashlib.sha256(json_canonico(obj).encode("utf-8")).hexdigest()


def archivos_codigo_v2(carpeta: Path) -> list[Path]:
    """Módulos de la v2 que entran al hash del código: ``*.py`` de la carpeta, sin pruebas ni caché."""
    return sorted(p for p in Path(carpeta).glob("*.py") if p.is_file())


def _clave_archivo(p: Path, r: RutasV2) -> str:
    rel = r.relativa(p)
    return rel["ruta"] if rel["raiz"] == "repo" else p.name


def hash_codigo_v2(rutas: RutasV2 | None = None, extra: Iterable[Path] = ()) -> dict:
    """Hash conjunto del código v2 y de los módulos ``extra`` que se importen de la v1 (si alguno lo hace)."""
    r = rutas or rutas_v2()
    archivos = archivos_codigo_v2(r.scripts_v2) + [Path(p).resolve() for p in extra]
    h = hashlib.sha256()
    por_archivo = {}
    for p in archivos:
        clave, s = _clave_archivo(p, r), sha256_archivo(p)
        por_archivo[clave] = s
        h.update(clave.encode("utf-8"))
        h.update(bytes.fromhex(s))
    return {"hash": h.hexdigest(), "archivos": por_archivo}


def commit_git(repo: Path) -> dict:
    """Commit vigente y cambios sin commit en ``scripts_modelo_1km/v2``; «desconocido» si no hay git."""
    def git(*args: str) -> str:
        return subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args], capture_output=True,
                              text=True, timeout=120, check=True).stdout
    try:
        commit = git("rev-parse", "HEAD").strip()
        v2 = git("status", "--porcelain", "--untracked-files=all", "--", "scripts_modelo_1km/v2")
        rastreados = git("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.SubprocessError) as exc:
        return {"commit": "desconocido", "error": type(exc).__name__}
    return {"commit": commit,
            "v2_sin_commit": sorted(linea[3:] for linea in v2.splitlines() if linea.strip()),
            "arbol_con_cambios_rastreados": bool(rastreados.strip())}


def versiones_bibliotecas(nombres: Iterable[str] = BIBLIOTECAS) -> dict:
    out = {"python": platform.python_version()}
    for n in nombres:
        try:
            out[n] = importlib.metadata.version(n)
        except importlib.metadata.PackageNotFoundError:
            out[n] = None
    return out


def fijar_hilos(n: int) -> dict:
    """Tope de hilos: variables de entorno de BLAS y OpenMP (nunca se suben si ya eran menores) y el
    grupo de hilos de pyarrow. Conviene llamarlo antes de cargar las bibliotecas numéricas pesadas."""
    n = int(n)
    for v in VARIABLES_HILOS:
        try:
            previo = int(os.environ.get(v, ""))
        except ValueError:
            previo = None
        os.environ[v] = str(min(n, previo) if previo and previo > 0 else n)
    try:
        import pyarrow as pa
        pa.set_cpu_count(n)
        pa.set_io_thread_count(n)
    except ImportError:
        pass
    return hilos(n)


def hilos(configurados: int) -> dict:
    return {"configurados": int(configurados), "cpu_count": os.cpu_count(),
            "entorno": {v: os.environ.get(v) for v in VARIABLES_HILOS}}


def entorno_python() -> dict:
    return {"entorno": Path(sys.prefix).name, "implementacion": platform.python_implementation(),
            "sistema": platform.platform(), "maquina": platform.machine()}


def huella_archivo(ruta, rutas: RutasV2 | None = None) -> dict:
    """Ruta portable, sha256 y tamaño de un insumo."""
    r = rutas or rutas_v2()
    p = Path(ruta)
    return {**r.relativa(p), "sha256": sha256_archivo(p), "bytes": p.stat().st_size}


def traza(insumos: Mapping[str, Path], semillas, hilos_configurados: int, rutas: RutasV2 | None = None,
          extra_codigo: Iterable[Path] = (), parametros: dict | None = None) -> dict:
    """Bloque de procedencia que va dentro de cada artefacto v2."""
    r = rutas or rutas_v2()
    out = {
        "creado_utc": ahora_utc(),
        "programa": Path(sys.argv[0]).name if sys.argv and sys.argv[0] else None,
        "git": commit_git(r.repo),
        "codigo": hash_codigo_v2(r, extra_codigo),
        "contrato": huella_archivo(r.contrato, r) if r.contrato.exists() else None,
        "config": huella_archivo(r.config, r) if r.config.exists() else None,
        "insumos": {nombre: huella_archivo(p, r) for nombre, p in sorted(insumos.items())},
        "bibliotecas": versiones_bibliotecas(),
        "python": entorno_python(),
        "hilos": hilos(hilos_configurados),
        "semillas": semillas,
    }
    if parametros is not None:
        out["parametros"] = parametros
    return out
