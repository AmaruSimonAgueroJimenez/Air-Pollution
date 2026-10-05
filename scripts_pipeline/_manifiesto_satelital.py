"""Manifiesto JSONL durable para descargas satelitales reproducibles."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path, bloque: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while trozo := f.read(bloque):
            h.update(trozo)
    return h.hexdigest()


def sha256_conjunto_shapefile(path: Path) -> str:
    """Hash reproducible de geometría, índice, atributos y proyección."""
    path = Path(path)
    h = hashlib.sha256()
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        parte = path.with_suffix(ext)
        if not parte.exists():
            continue
        h.update(ext.encode("ascii"))
        h.update(bytes.fromhex(sha256(parte)))
    return h.hexdigest()


def url_publica(url: str | None) -> str | None:
    """Elimina query strings que podrían contener credenciales temporales."""
    return url.split("?", 1)[0] if url else None


def adquisicion_de_nombre(nombre: str) -> str | None:
    tropomi = re.search(r"_{2,}(\d{4})(\d{2})(\d{2})T\d{6}_", nombre)
    if tropomi:
        return f"{tropomi.group(1)}-{tropomi.group(2)}-{tropomi.group(3)}"
    patrones = (
        r"_(\d{4})m(\d{2})(\d{2})_",       # OMI
        r"MOP03J-(\d{4})(\d{2})(\d{2})",  # MOPITT
        r"\.(\d{4})(\d{2})-\d{6}\.",     # ACAG mensual
        r"\.(\d{4})01-\d{4}12\.",         # ACAG anual
        r"\.A(\d{4})(\d{3})\.",           # NASA año+día juliano
    )
    for i, patron in enumerate(patrones):
        m = re.search(patron, nombre)
        if not m:
            continue
        if i < 2:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if i == 2:
            return f"{m.group(1)}-{m.group(2)}"
        if i == 3:
            return m.group(1)
        return f"{m.group(1)}-DOY{m.group(2)}"
    return None


def _argv_saneado(argv: list[str]) -> list[str]:
    """Quita secretos y query strings sin perder parámetros reproducibles."""
    sensibles = ("password", "passwd", "token", "secret", "credential",
                 "authorization", "api-key", "apikey")
    salida: list[str] = []
    ocultar_siguiente = False
    for arg in argv:
        if ocultar_siguiente:
            salida.append("[REDACTADO]")
            ocultar_siguiente = False
            continue
        if arg.startswith("--"):
            clave = arg[2:].split("=", 1)[0].lower()
            if any(s in clave for s in sensibles):
                if "=" in arg:
                    salida.append(arg.split("=", 1)[0] + "=[REDACTADO]")
                else:
                    salida.append(arg)
                    ocultar_siguiente = True
                continue
        if "://" in arg and "?" in arg:
            arg = arg.split("?", 1)[0] + "?[REDACTADO]"
        salida.append(arg)
    return salida


def _runtime_reproducible() -> dict:
    script = Path(sys.argv[0]).expanduser()
    script_info = None
    if script.is_file():
        script = script.resolve()
        script_info = {"ruta": str(script), "sha256": sha256(script)}
    carpeta = Path(__file__).resolve().parent
    h = hashlib.sha256()
    archivos_codigo = sorted(carpeta.glob("*.py"))
    for archivo in archivos_codigo:
        h.update(archivo.name.encode("utf-8"))
        h.update(bytes.fromhex(sha256(archivo)))
    req = carpeta / "requirements.txt"
    paquetes = {}
    for nombre in ("earthaccess", "numpy", "pandas", "xarray", "netCDF4",
                   "h5py", "geopandas", "shapely", "rasterio", "pyarrow"):
        try:
            paquetes[nombre] = importlib.metadata.version(nombre)
        except importlib.metadata.PackageNotFoundError:
            paquetes[nombre] = None
    return {
        "argv": _argv_saneado(list(sys.argv)),
        "script": script_info,
        "codigo_pipeline_sha256": h.hexdigest(),
        "archivos_codigo": len(archivos_codigo),
        "requirements": ({"ruta": str(req), "sha256": sha256(req)}
                         if req.exists() else None),
        "python": {"version": sys.version, "executable": sys.executable,
                   "platform": platform.platform()},
        "paquetes_criticos": paquetes,
    }


class Manifiesto:
    """Un JSON por línea; cada append se sincroniza antes de continuar."""

    def __init__(self, carpeta: Path, producto: str, parametros: dict):
        self.producto = producto
        self.execution_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" +
            uuid.uuid4().hex[:8])
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        self.path = carpeta / f"{producto.lower()}_{self.execution_id}.jsonl"
        self.registrar({"evento": "inicio", "parametros": parametros,
                        "runtime": _runtime_reproducible()})

    def registrar(self, datos: dict) -> None:
        registro = {
            "schema": "airpollution.satellite-manifest.v1",
            "execution_id": self.execution_id,
            "producto": self.producto,
            "registrado_utc": ahora_utc(),
            **datos,
        }
        linea = json.dumps(registro, ensure_ascii=False, sort_keys=True,
                           default=str) + "\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(linea)
            f.flush()
            os.fsync(f.fileno())

    def archivo(self, *, salida: Path, version: str, granule_id: str,
                url: str | None, aoi_id: str, territorio: str, bbox,
                resolucion: str, tiempo_nativo: str, qa: str,
                pixeles: int | None, mascara: str, validacion: str,
                crudo_eliminado: bool, crudo: Path | None = None,
                checksum_fuente: str | None = None,
                variables_conservadas: list[str] | None = None) -> None:
        salida = Path(salida)
        self.registrar({
            "evento": "archivo_validado",
            "version": version,
            "granule_id": granule_id,
            "url": url_publica(url),
            "adquisicion": adquisicion_de_nombre(granule_id),
            "tiempo_nativo": tiempo_nativo,
            "resolucion_nativa": resolucion,
            "aoi_id": aoi_id,
            "territorio": territorio,
            "bbox": tuple(bbox),
            "mascara": mascara,
            "qa": qa,
            "variables_conservadas": variables_conservadas,
            "pixeles_chile": pixeles,
            "salida": str(salida),
            "bytes_salida": salida.stat().st_size,
            "sha256_salida": sha256(salida),
            "crudo_temporal": str(crudo) if crudo else None,
            "sha256_fuente": checksum_fuente,
            "validacion": validacion,
            "crudo_eliminado": crudo_eliminado,
        })

    def terminar(self, estado="completo", **extra) -> None:
        self.registrar({"evento": "fin", "estado": estado, **extra})
