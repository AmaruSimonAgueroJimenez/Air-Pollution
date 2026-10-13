"""Rutas, guarda de escritura y candado de la v2 del modelo 1 km × hora.

La v2 (contrato ``DISENO_AMBIENTAL_V2.md``, fijado el 2026-10-12 antes de estimar) vive aparte de la
v1, que queda congelada. Lee los paneles y la grilla de la v1 y el catálogo de estaciones **en sólo
lectura**, y escribe únicamente en tres lugares:

* ``scripts_modelo_1km/v2/``: código, configuración y pruebas;
* ``output_files/modelo_1km_v2/``: tablas pequeñas, versionadas en git;
* la raíz de datos v2, ``AIR_POLLUTION_MODELO_1KM_ROOT``, por omisión
  ``~/Asesorias_Data_local/AirPollution/modelado_1km_v2``, fuera del repositorio.

Toda escritura pasa por ``verificar_escritura``, que se niega a tocar cualquier otra ruta, también a
través de ``..`` o de enlaces simbólicos, y que protege el contrato aunque esté dentro de ``v2/``. Lo que
cae en la raíz v2 o en ``output_files/modelo_1km_v2`` exige además que este proceso tenga tomado un
candado de escritura (``fcntl.flock`` sobre ``<raíz v2>/.candados/<nombre>.lock``), para que dos corridas
no escriban a la vez. Las escrituras son atómicas: archivo temporal en la misma carpeta, ``fsync`` y
``os.replace``.

La raíz v2 no puede coincidir con la raíz v1, ni contenerla ni estar dentro de ella, ni estar dentro del
repositorio o del disco de datos crudos: así, una variable de entorno mal puesta no abre la v1 a la
escritura.

Raíces de lectura:

* ``AIR_POLLUTION_MODELO_1KM_V1_ROOT``: raíz v1 (paneles, grilla y modelos). Por omisión,
  ``$AIR_POLLUTION_LOCAL_ROOT/modelado_1km`` o ``~/Asesorias_Data_local/AirPollution/modelado_1km``, la
  misma regla de ``_comun_modelo.py:71-73``. Aquí no se lee ``AIR_POLLUTION_MODELO_1KM_ROOT``, porque en la
  v2 esa variable apunta a la raíz v2.
* ``AIR_POLLUTION_DATA_ROOT``: datos crudos (catálogo SINCA y red SNIFA), con la regla de
  ``scripts_pipeline/_common.py:20-42``. No se importa ``_comun_modelo`` para no heredar su raíz.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import functools
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping

AQUI = Path(__file__).resolve().parent              # scripts_modelo_1km/v2
REPO = AQUI.parents[1]                              # raíz del repositorio Air-Pollution
NOMBRE_CONTRATO = "DISENO_AMBIENTAL_V2.md"
NOMBRE_CONFIG = "config_v2.json"

VAR_RAIZ_V2 = "AIR_POLLUTION_MODELO_1KM_ROOT"
VAR_RAIZ_V1 = "AIR_POLLUTION_MODELO_1KM_V1_ROOT"
VAR_LOCAL = "AIR_POLLUTION_LOCAL_ROOT"
VAR_DATOS = "AIR_POLLUTION_DATA_ROOT"
VAR_DATOS_BASE = "ASESORIAS_DATA_ROOT"
DATOS_BASE_POR_OMISION = "/Volumes/Datos/Asesorias_Data"     # como scripts_pipeline/_common.py:38
VOLUMEN_DATOS = Path("/Volumes/Datos")                      # disco de datos crudos: sólo lectura

CARPETA_CANDADOS = ".candados"
_NOMBRE_CANDADO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class EscrituraNoPermitida(PermissionError):
    """Intento de escribir fuera de las rutas de la v2, o en la raíz v2 sin el candado."""


class CandadoOcupado(RuntimeError):
    """Otro proceso tiene tomado el candado de escritura."""


class RaizInvalida(ValueError):
    """La raíz v2 se cruza con la v1, el repositorio o los datos crudos."""


def ahora_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolver(ruta) -> Path:
    """Ruta absoluta con ``~``, ``..`` y enlaces simbólicos resueltos (aunque el final no exista)."""
    return Path(ruta).expanduser().resolve(strict=False)


def _dentro(ruta: Path, base: Path) -> bool:
    return ruta == base or base in ruta.parents


# ---------------------------------------------------------------------------
# Raíces
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RutasV2:
    """Raíces de la v2. Se valida al crearse: la raíz v2 no puede cruzarse con ninguna otra."""

    raiz_v2: Path
    raiz_v1: Path
    datos: Path
    repo: Path = REPO
    scripts_v2: Path = AQUI

    def __post_init__(self) -> None:
        for campo in ("raiz_v2", "raiz_v1", "datos", "repo", "scripts_v2"):
            object.__setattr__(self, campo, _resolver(getattr(self, campo)))
        prohibidas = {"la raíz v1": self.raiz_v1, "el repositorio": self.repo,
                      "los datos crudos": self.datos, "el volumen de datos": _resolver(VOLUMEN_DATOS)}
        for nombre, otra in prohibidas.items():
            if _dentro(self.raiz_v2, otra) or _dentro(otra, self.raiz_v2):
                raise RaizInvalida(f"La raíz v2 {self.raiz_v2} no puede coincidir con {nombre} ({otra}), "
                                   f"estar dentro ni contenerla. Revisa {VAR_RAIZ_V2}.")

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str] | None = None) -> "RutasV2":
        e = os.environ if entorno is None else entorno
        local = Path(e.get(VAR_LOCAL) or Path.home() / "Asesorias_Data_local" / "AirPollution").expanduser()
        datos_base = Path(e.get(VAR_DATOS_BASE) or DATOS_BASE_POR_OMISION).expanduser()
        return cls(raiz_v2=Path(e.get(VAR_RAIZ_V2) or local / "modelado_1km_v2").expanduser(),
                   raiz_v1=Path(e.get(VAR_RAIZ_V1) or local / "modelado_1km").expanduser(),
                   datos=Path(e.get(VAR_DATOS) or datos_base / "AirPollution" / "data").expanduser())

    # --- Escritura ---------------------------------------------------------
    @property
    def salidas_v2(self) -> Path:
        return self.repo / "output_files" / "modelo_1km_v2"

    @property
    def escribibles(self) -> tuple[Path, ...]:
        return (self.scripts_v2, self.salidas_v2, self.raiz_v2)

    @property
    def con_candado(self) -> tuple[Path, ...]:
        """Donde escribir exige el candado: datos y tablas, no el código."""
        return (self.salidas_v2, self.raiz_v2)

    @property
    def protegidos(self) -> tuple[Path, ...]:
        """Archivos que la v2 nunca reescribe aunque estén en una ruta escribible."""
        return (self.scripts_v2 / NOMBRE_CONTRATO,)

    # --- Contrato y configuración -------------------------------------------
    @property
    def contrato(self) -> Path:
        return self.scripts_v2 / NOMBRE_CONTRATO

    @property
    def config(self) -> Path:
        return self.scripts_v2 / NOMBRE_CONFIG

    # --- Insumos v1 y crudos (sólo lectura) ----------------------------------
    def panel(self, pol: str) -> Path:
        return self.raiz_v1 / "paneles" / f"panel_{pol}.parquet"

    def panel_meta(self, pol: str) -> Path:
        return self.panel(pol).with_suffix(".json")

    @property
    def grilla_v1(self) -> Path:
        return self.raiz_v1 / "grilla_1km"

    @property
    def catalogo_sinca(self) -> Path:
        return self.datos / "sinca" / "estaciones_georreferenciadas.csv"

    @property
    def snifa(self) -> Path:
        return self.datos / "snifa_adicional" / "processed" / "observaciones_horarias.parquet"

    # --- Salidas v2 ---------------------------------------------------------
    @property
    def manifiesto_pliegues(self) -> Path:
        return self.raiz_v2 / "pliegues_v2.json"

    @property
    def candados(self) -> Path:
        return self.raiz_v2 / CARPETA_CANDADOS

    def relativa(self, ruta) -> dict:
        """Ruta portable para las trazas: raíz simbólica más ruta relativa, nunca la ruta absoluta."""
        r = _resolver(ruta)
        for nombre, base in (("raiz_v2", self.raiz_v2), ("raiz_v1", self.raiz_v1), ("datos", self.datos),
                             ("repo", self.repo)):
            if _dentro(r, base):
                return {"raiz": nombre, "ruta": r.relative_to(base).as_posix() or "."}
        return {"raiz": None, "ruta": r.name}


@functools.lru_cache(maxsize=1)
def rutas_v2() -> RutasV2:
    """Raíces según el entorno (perezoso: importar este módulo no valida ni escribe nada)."""
    return RutasV2.desde_entorno()


# ---------------------------------------------------------------------------
# Guarda de escritura
# ---------------------------------------------------------------------------
def verificar_escritura(ruta, rutas: RutasV2 | None = None) -> Path:
    """Devuelve la ruta resuelta si la v2 puede escribir en ella; si no, ``EscrituraNoPermitida``."""
    r = rutas or rutas_v2()
    destino = _resolver(ruta)
    if destino in r.protegidos:
        raise EscrituraNoPermitida(f"{destino} es el contrato v2: se cambia sólo por enmienda, a mano")
    if not any(_dentro(destino, base) for base in r.escribibles):
        permitidas = ", ".join(str(b) for b in r.escribibles)
        raise EscrituraNoPermitida(f"La v2 no escribe en {destino}; sólo en: {permitidas}")
    return destino


# ---------------------------------------------------------------------------
# Candado de escritura (fcntl.flock)
# ---------------------------------------------------------------------------
_TOMADOS: dict[str, list] = {}       # ruta del candado → [descriptor, profundidad]


def _ruta_candado(nombre: str, r: RutasV2) -> Path:
    if not _NOMBRE_CANDADO.fullmatch(nombre):
        raise ValueError(f"nombre de candado inválido: {nombre!r} (letras, dígitos, '_', '.', '-')")
    return r.candados / f"{nombre}.lock"


def _titular(ruta: Path) -> str:
    try:
        return ruta.read_text(encoding="utf-8").strip() or "(sin datos del titular)"
    except OSError:
        return "(no se pudo leer el titular)"


@contextlib.contextmanager
def candado_escritura(nombre: str = "raiz", rutas: RutasV2 | None = None, espera_s: float = 0.0,
                      intervalo_s: float = 0.2) -> Iterator[Path]:
    """Candado exclusivo entre procesos sobre ``<raíz v2>/.candados/<nombre>.lock``.

    Es reentrante dentro del mismo proceso. Si otro proceso lo tiene, espera hasta ``espera_s`` segundos y
    luego levanta ``CandadoOcupado`` con los datos del titular (pid, máquina, inicio y programa). El
    archivo del candado no se borra al soltarlo: borrarlo abriría una carrera entre procesos.
    """
    r = rutas or rutas_v2()
    ruta = _ruta_candado(nombre, r)
    clave = str(ruta)
    if clave in _TOMADOS:
        _TOMADOS[clave][1] += 1
        try:
            yield ruta
        finally:
            _TOMADOS[clave][1] -= 1
        return
    verificar_escritura(ruta, r)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        limite = time.monotonic() + max(0.0, float(espera_s))
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() >= limite:
                    raise CandadoOcupado(f"El candado {ruta} está tomado: {_titular(ruta)}") from None
                time.sleep(intervalo_s)
    except BaseException:
        os.close(fd)
        raise
    try:
        titular = {"pid": os.getpid(), "maquina": socket.gethostname(), "desde_utc": ahora_utc(),
                   "programa": Path(sys.argv[0]).name if sys.argv and sys.argv[0] else None}
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, (json.dumps(titular, ensure_ascii=False) + "\n").encode("utf-8"))
        os.fsync(fd)
        _TOMADOS[clave] = [fd, 1]
        yield ruta
    finally:
        _TOMADOS.pop(clave, None)
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def candado_tomado(rutas: RutasV2 | None = None) -> bool:
    """¿Tiene este proceso algún candado de la raíz v2 de ``rutas``?"""
    r = rutas or rutas_v2()
    return any(Path(k).parent == r.candados for k in _TOMADOS)


# ---------------------------------------------------------------------------
# Escritura atómica
# ---------------------------------------------------------------------------
def _preparar_destino(ruta, rutas: RutasV2 | None) -> Path:
    r = rutas or rutas_v2()
    destino = verificar_escritura(ruta, r)
    if any(_dentro(destino, base) for base in r.con_candado) and not candado_tomado(r):
        raise EscrituraNoPermitida(f"{destino}: escribir en la raíz v2 o en output_files/modelo_1km_v2 exige "
                                   f"tomar antes candado_escritura()")
    destino.parent.mkdir(parents=True, exist_ok=True)
    return destino


def _fsync_carpeta(carpeta: Path) -> None:
    try:
        fd = os.open(carpeta, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _temporal(destino: Path) -> str:
    fd, tmp = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".part", dir=destino.parent)
    os.close(fd)
    return tmp


def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(8 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def publicar_bytes(datos: bytes, ruta, rutas: RutasV2 | None = None) -> str:
    """Escribe ``datos`` de forma atómica y devuelve su sha256."""
    destino = _preparar_destino(ruta, rutas)
    tmp = _temporal(destino)
    try:
        with open(tmp, "wb") as fh:
            fh.write(datos)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, destino)
        _fsync_carpeta(destino.parent)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return hashlib.sha256(datos).hexdigest()


def a_json(obj):
    """Convierte tipos de numpy y pandas a tipos nativos para ``json.dumps``."""
    if hasattr(obj, "item") and callable(obj.item) and getattr(obj, "ndim", 0) == 0:
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    if isinstance(obj, Path):
        raise TypeError("las rutas se registran con RutasV2.relativa(), no como Path")
    raise TypeError(f"{type(obj).__name__} no es serializable a JSON")


def texto_json(datos) -> str:
    return json.dumps(datos, ensure_ascii=False, indent=1, default=a_json) + "\n"


def publicar_texto(texto: str, ruta, rutas: RutasV2 | None = None) -> str:
    return publicar_bytes(texto.encode("utf-8"), ruta, rutas)


def publicar_json(datos, ruta, rutas: RutasV2 | None = None) -> str:
    return publicar_texto(texto_json(datos), ruta, rutas)


def publicar_csv(df, ruta, rutas: RutasV2 | None = None) -> str:
    return publicar_texto(df.to_csv(index=False, lineterminator="\n"), ruta, rutas)


def publicar_parquet(df, ruta, rutas: RutasV2 | None = None) -> str:
    """Parquet atómico: se escribe, se reabre para contar filas y recién entonces se publica."""
    import pyarrow.parquet as pq

    destino = _preparar_destino(ruta, rutas)
    tmp = _temporal(destino)
    try:
        df.to_parquet(tmp, index=False, compression="zstd")
        if pq.read_metadata(tmp).num_rows != len(df):
            raise ValueError(f"{destino}: la reapertura del Parquet no coincide en filas")
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, destino)
        _fsync_carpeta(destino.parent)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return _sha256_archivo(destino)


def renombrar(origen, destino, rutas: RutasV2 | None = None) -> Path:
    """``os.replace`` con las mismas guardas en ambos extremos (para respaldar un artefacto)."""
    r = rutas or rutas_v2()
    o = _preparar_destino(origen, r)
    d = _preparar_destino(destino, r)
    os.replace(o, d)
    _fsync_carpeta(d.parent)
    return d


def leer_json(ruta) -> dict | None:
    p = Path(ruta)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
def cargar_config(rutas: RutasV2 | None = None, verificar_contrato: bool = True) -> dict:
    """Lee ``config_v2.json`` y comprueba que traduce el contrato vigente (mismo sha256). Si el contrato
    cambió (una enmienda), la configuración tiene que actualizarse antes de correr nada."""
    r = rutas or rutas_v2()
    cfg = json.loads(r.config.read_text(encoding="utf-8"))
    if verificar_contrato:
        actual = _sha256_archivo(r.contrato)
        declarado = cfg.get("contrato", {}).get("sha256")
        if actual != declarado:
            raise SystemExit(f"{r.config.name} traduce el contrato con sha256 {declarado}, pero "
                             f"{r.contrato.name} tiene {actual}: actualiza la configuración (enmienda) antes de seguir.")
    return cfg


def valor_vigente(item, nombre: str):
    """Valor que usa el código: el del contrato o, si está pendiente, el «provisional» declarado en la
    configuración. Un pendiente sin provisional detiene la corrida."""
    if isinstance(item, dict) and item.get("estado") == "pendiente":
        if "provisional" not in item:
            raise ValueError(f"{nombre}: está pendiente en config_v2.json y no tiene valor provisional")
        return item["provisional"]
    if isinstance(item, str) and item == "pendiente":
        raise ValueError(f"{nombre}: está pendiente en config_v2.json")
    return item
