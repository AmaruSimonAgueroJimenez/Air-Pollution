"""Rutas, guarda de escritura y candados de la v2 del modelo 1 km × hora.

La v2 (contrato ``DISENO_AMBIENTAL_V2.md``, fijado el 2026-10-12 antes de estimar, con su Enmienda 1) vive aparte
de la v1, que queda congelada. Lee los paneles y la grilla de la v1 y el catálogo de estaciones **en sólo
lectura**, y escribe únicamente en tres lugares:

* ``scripts_modelo_1km/v2/``: código, configuración y pruebas;
* ``output_files/modelo_1km_v2/``: tablas pequeñas, versionadas en git;
* la raíz de datos v2, ``AIR_POLLUTION_MODELO_1KM_ROOT``, por omisión
  ``~/Asesorias_Data_local/AirPollution/modelado_1km_v2``, fuera del repositorio.

**Guarda de escritura** (Enmienda 1, punto 14). Toda escritura pasa por ``verificar_escritura``, que se niega a
tocar cualquier otra ruta, también a través de ``..`` o de enlaces simbólicos, y que protege el contrato aunque
esté dentro de ``v2/``. Las rutas se comparan **sin distinguir mayúsculas ni la forma Unicode** (NFC + casefold) y,
cuando existen, **por identidad** (``st_dev`` y ``st_ino``), porque el disco del Mac no distingue mayúsculas y
``Path.resolve`` no las normaliza: ``~/ASESORIAS_DATA_LOCAL/…/modelado_1km`` es la raíz v1 aunque el texto
difiera. La comparación es asimétrica a propósito: para *prohibir* (contrato, raíz v1, datos crudos, cruces de
raíces) basta que coincidan el texto plegado o la identidad; para *permitir* se exige el texto exacto o la
identidad de un ancestro existente, de modo que un disco que sí distingue mayúsculas no abra otra carpeta.

**Candado por artefacto** (Enmienda 1, punto 14). Escribir en la raíz v2 o en ``output_files/modelo_1km_v2`` exige
que **el hilo que escribe** tenga tomado **el candado de ese artefacto**, no uno cualquiera: ``candado_de(ruta)``
da su nombre (reglas de ``REGLAS_CANDADO`` y, para rutas sin regla, un candado por archivo) y
``candado_artefactos([rutas])`` toma los que hagan falta. Los candados son ``fcntl.flock`` sobre
``<raíz v2>/.candados/<nombre>.lock``, entre procesos; dentro de un proceso son reentrantes sólo para el hilo que
los tiene (otro hilo espera o recibe ``CandadoOcupado``) y su registro está protegido por un cerrojo. Las
escrituras son atómicas: archivo temporal en la misma carpeta, ``fsync`` y ``os.replace``.

**Nombres normalizados** (Complemento de la Enmienda 1, punto 10). Como la guardia de escritura, los nombres de los
candados se comparan **sin distinguir mayúsculas ni la forma Unicode**: ``normalizar_candado`` (NFC + casefold) se
aplica al nombre que da ``candado_de``, al archivo ``<nombre>.lock`` y al registro de los tomados, y las reglas de
``REGLAS_CANDADO`` calzan sin distinguir mayúsculas. Así «comparacion.principal.pm25.LRO.k003» y
«…lro.k003» son el mismo candado también en un disco que distingue mayúsculas, y una ruta escrita con otra grafía
cae en el candado de su artefacto.

La raíz v2 no puede coincidir con la raíz v1, ni contenerla ni estar dentro de ella, ni estar dentro del
repositorio o del disco de datos crudos: así, una variable de entorno mal puesta no abre la v1 a la escritura.

Raíces de lectura:

* ``AIR_POLLUTION_MODELO_1KM_V1_ROOT``: raíz v1 (paneles, grilla y modelos). Por omisión,
  ``$AIR_POLLUTION_LOCAL_ROOT/modelado_1km`` o ``~/Asesorias_Data_local/AirPollution/modelado_1km``, la
  misma regla de ``_comun_modelo.py:71-73``. Aquí no se lee ``AIR_POLLUTION_MODELO_1KM_ROOT``, porque en la
  v2 esa variable apunta a la raíz v2.
* ``AIR_POLLUTION_DATA_ROOT``: datos crudos (catálogo SINCA y red SNIFA), con la regla de
  ``scripts_pipeline/_common.py:20-42``. No se importa ``_comun_modelo`` para no heredar su raíz.

Este módulo sólo usa la biblioteca estándar: los programas de línea de órdenes pueden importarlo antes que numpy
(``hilos_de_la_linea``) para fijar el tope de hilos de BLAS y OpenMP antes de cargarlo.
"""
from __future__ import annotations

import argparse
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
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Mapping

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
_LARGO_MAXIMO_CANDADO = 180                         # el archivo <nombre>.lock no pasa de 255 bytes
ESTADO_PENDIENTE = "pendiente"
PREFIJO_RATIFICADO = "ratificado"                   # «ratificado (Enmienda 1)», «ratificado (Enmienda 2)», …


class EscrituraNoPermitida(PermissionError):
    """Intento de escribir fuera de las rutas de la v2, o en un artefacto sin su candado."""


class CandadoOcupado(RuntimeError):
    """Otro proceso, u otro hilo de este proceso, tiene tomado el candado de escritura."""


class RaizInvalida(ValueError):
    """La raíz v2 se cruza con la v1, el repositorio o los datos crudos."""


def ahora_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Comparación de rutas (Enmienda 1, punto 14)
# ---------------------------------------------------------------------------
def _resolver(ruta) -> Path:
    """Ruta absoluta con ``~``, ``..`` y enlaces simbólicos resueltos (aunque el final no exista)."""
    return Path(ruta).expanduser().resolve(strict=False)


def _plegar(texto: str) -> str:
    """Forma comparable de un texto: Unicode NFC y sin distinguir mayúsculas (casefold)."""
    return unicodedata.normalize("NFC", str(texto)).casefold()


def _partes_plegadas(ruta: Path) -> tuple[str, ...]:
    return tuple(_plegar(p) for p in Path(ruta).parts)


def _identidad(ruta: Path) -> tuple[int, int] | None:
    """(``st_dev``, ``st_ino``) de una ruta existente; None si no existe o el sistema no da un inodo útil."""
    try:
        st = os.stat(ruta)
    except OSError:
        return None
    return (int(st.st_dev), int(st.st_ino)) if st.st_ino > 0 else None


def _ancestro_con_identidad(ruta: Path, base: Path) -> Path | None:
    """El ancestro existente de ``ruta`` (o ella misma) que es el mismo directorio que ``base``, si lo hay."""
    ib = _identidad(base)
    if ib is None:
        return None
    for p in (ruta, *ruta.parents):
        if _identidad(p) == ib:
            return p
    return None


def misma_ruta(a, b) -> bool:
    """¿Nombran ``a`` y ``b`` el mismo archivo? Sin distinguir mayúsculas ni forma Unicode, o por identidad."""
    ra, rb = _resolver(a), _resolver(b)
    if _partes_plegadas(ra) == _partes_plegadas(rb):
        return True
    ia = _identidad(ra)
    return ia is not None and ia == _identidad(rb)


def _dentro(ruta: Path, base: Path) -> bool:
    """¿``ruta`` es ``base`` o está dentro de ella? Comparación **amplia**, para prohibir: texto plegado (NFC y
    sin mayúsculas) o identidad de un ancestro existente."""
    pr, pb = _partes_plegadas(ruta), _partes_plegadas(base)
    if len(pr) >= len(pb) and pr[:len(pb)] == pb:
        return True
    return _ancestro_con_identidad(Path(ruta), Path(base)) is not None


def _dentro_estricto(ruta: Path, base: Path) -> bool:
    """¿``ruta`` es ``base`` o está dentro de ella? Comparación **estricta**, para permitir: texto exacto o
    identidad de un ancestro existente (en un disco que distingue mayúsculas, otra grafía es otra carpeta)."""
    ruta, base = Path(ruta), Path(base)
    if ruta == base or base in ruta.parents:
        return True
    return _ancestro_con_identidad(ruta, base) is not None


def _relativa_a(ruta: Path, base: Path) -> Path | None:
    """Parte de ``ruta`` bajo ``base`` (con la comparación amplia), o None si no está dentro."""
    ruta, base = Path(ruta), Path(base)
    pr, pb = _partes_plegadas(ruta), _partes_plegadas(base)
    if len(pr) >= len(pb) and pr[:len(pb)] == pb:
        return Path(*ruta.parts[len(pb):]) if len(pr) > len(pb) else Path(".")
    ancestro = _ancestro_con_identidad(ruta, base)
    if ancestro is None:
        return None
    return ruta.relative_to(ancestro) if ruta != ancestro else Path(".")


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
                                   f"estar dentro ni contenerla (sin distinguir mayúsculas ni forma Unicode). "
                                   f"Revisa {VAR_RAIZ_V2}.")

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
        """Donde escribir exige el candado del artefacto: datos y tablas, no el código."""
        return (self.salidas_v2, self.raiz_v2)

    @property
    def protegidos(self) -> tuple[Path, ...]:
        """Archivos que la v2 nunca reescribe aunque estén en una ruta escribible."""
        return (self.scripts_v2 / NOMBRE_CONTRATO,)

    @property
    def nunca_escribibles(self) -> tuple[Path, ...]:
        """Raíces de sólo lectura (defensa en profundidad, con la comparación amplia), con el derivado SINCA v1
        (Enmienda 2, §3: la red 2 escribe su derivado en ``SINCA/v1_red2``)."""
        return (self.raiz_v1, self.datos, _resolver(VOLUMEN_DATOS),
                _resolver(self.datos.parent / "derived" / "modelado" / "SINCA" / "v1"))

    # --- Contrato y configuración -------------------------------------------
    @property
    def contrato(self) -> Path:
        return self.scripts_v2 / NOMBRE_CONTRATO

    @property
    def config(self) -> Path:
        return self.scripts_v2 / NOMBRE_CONFIG

    # --- Insumos v1 y crudos (sólo lectura) ----------------------------------
    def panel(self, pol: str) -> Path:
        """Panel de la red ampliada, en la raíz v2 (Enmienda 2, bloque de la red ampliada, R11): lo arma
        ``panel_red2_v2``. Los paneles v1 (``panel_v1``) quedan intactos y la v2 ya no los lee."""
        return self.raiz_v2 / "paneles" / f"panel_{pol}_red2.parquet"

    def panel_v1(self, pol: str) -> Path:
        """Panel v1: referencia histórica congelada (R12); la v2 no lo lee desde la Enmienda 2."""
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
        """Manifiesto de pliegues vigente. Desde la Enmienda 2 (bloque de la red ampliada, R13) es el de la red 2,
        ``pliegues_v2_red2.json``: lo fija ``pliegues_red2_v2`` y es la única fuente de pliegues, pesos, E2 y bloque
        más influyente. El de la red original queda intacto como ``pliegues_v2_reemplazado_<marca>.json``."""
        return self.raiz_v2 / "pliegues_v2_red2.json"

    @property
    def candados(self) -> Path:
        return self.raiz_v2 / CARPETA_CANDADOS

    def relativa(self, ruta) -> dict:
        """Ruta portable para las trazas: raíz simbólica más ruta relativa, nunca la ruta absoluta."""
        r = _resolver(ruta)
        for nombre, base in (("raiz_v2", self.raiz_v2), ("raiz_v1", self.raiz_v1), ("datos", self.datos),
                             ("repo", self.repo)):
            rel = _relativa_a(r, base)
            if rel is not None:
                return {"raiz": nombre, "ruta": rel.as_posix() or "."}
        return {"raiz": None, "ruta": r.name}


class RutasRedOriginal(RutasV2):
    """Rutas de la red original, las de antes de la Enmienda 2: panel v1, ``calidad_<pol>.parquet`` y
    ``pliegues_v2.json``. Sirven para reproducir la bandera y los pliegues de la red original (``calidad_v2`` y
    ``pliegues_v2`` con la configuración sin el nodo ``red_de_monitores``) y a sus pruebas; la v2 usa ``RutasV2``."""

    def panel(self, pol: str) -> Path:
        return self.panel_v1(pol)

    manifiesto_pliegues = property(lambda self: self.raiz_v2 / "pliegues_v2.json",
                                   doc="Manifiesto de pliegues de la red original.")


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
    if any(misma_ruta(destino, p) for p in r.protegidos):
        raise EscrituraNoPermitida(f"{destino} es el contrato v2: se cambia sólo por enmienda, a mano")
    if not any(_dentro_estricto(destino, base) for base in r.escribibles):
        permitidas = ", ".join(str(b) for b in r.escribibles)
        raise EscrituraNoPermitida(f"La v2 no escribe en {destino}; sólo en: {permitidas}")
    for base in r.nunca_escribibles:
        if _dentro(destino, base):
            raise EscrituraNoPermitida(f"{destino} cae en una raíz de sólo lectura ({base})")
    return destino


# ---------------------------------------------------------------------------
# Candado de cada artefacto
# ---------------------------------------------------------------------------
# (raíz, expresión sobre la ruta relativa en POSIX, plantilla del nombre del candado). La primera que calza manda.
# Las expresiones calzan sin distinguir mayúsculas (Complemento, punto 10) y el nombre resultante se normaliza.
_PROT = r"(?P<prot>LOSO-D|LBO-10|BLQ-75|LRO|LPO)"
_POL = r"(?P<pol>pm25|no2)"


def _regla(patron: str) -> re.Pattern:
    return re.compile(patron, re.IGNORECASE)


REGLAS_CANDADO: list[tuple[str, re.Pattern, str]] = [
    ("raiz_v2", _regla(r"pliegues_v2(?:_red2)?(?:_reemplazado_[^/]+)?\.json"), "pliegues"),
    ("raiz_v2", _regla(r"paneles/calidad_[^/]+"), "calidad"),
    ("raiz_v2", _regla(r"vecindario/[^/]+"), "vecindario"),
    ("raiz_v2", _regla(r"piloto_tiempos/[^/]+"), "piloto_tiempos"),
    ("raiz_v2", _regla(r"plan_corrida_v2(?:_reemplazado_[^/]+)?\.json"), "plan_corrida"),
    ("raiz_v2", _regla(r"comparacion/(?P<etiqueta>[^/]+)/(?P<pol>[^/]+)/(?P<prot>[^/]+)/(?P<k>k\d+)/.+"),
     "comparacion.{etiqueta}.{pol}.{prot}.{k}"),
    ("raiz_v2", _regla(r"comparacion/(?P<etiqueta>[^/]+)/(?P<pol>[^/]+)/(?P<prot>[^/]+)/[^/]+"),
     "comparacion.{etiqueta}.{pol}.{prot}.consolidar"),
    ("raiz_v2", _regla(r"comparacion/(?P<etiqueta>[^/]+)/(?P<pol>[^/]+)/[^/]+"), "comparacion.{etiqueta}.{pol}"),
    ("raiz_v2", _regla(r"comparacion/(?P<etiqueta>[^/]+)/[^/]+"), "comparacion.{etiqueta}"),
    ("salidas_v2", _regla(r"pliegues_v2_[^/]+"), "pliegues"),
    ("salidas_v2", _regla(r"calidad_v2_[^/]+"), "calidad"),
    ("salidas_v2", _regla(r"vecindario_v2_[^/]+"), "vecindario"),
    ("salidas_v2", _regla(r"comparacion_piloto(?:_[^/]*)?\.(?:csv|json)"), "plan_corrida"),
    ("salidas_v2", _regla(rf"comparacion_(?P<etiqueta>[^/]+)_{_POL}_{_PROT}(?:_[^/]*)?\.(?:csv|json)"),
     "comparacion.{etiqueta}.{pol}.{prot}.consolidar"),
    ("salidas_v2", _regla(rf"comparacion_(?P<etiqueta>[^/]+)_{_POL}(?:_[^/]*)?\.(?:csv|json)"),
     "comparacion.{etiqueta}.{pol}"),
]


def registrar_candado(raiz: str, patron: str, plantilla: str) -> None:
    """Agrega una regla ``(raíz, patrón, plantilla)`` antes de las existentes, para un artefacto nuevo. Cada
    módulo que la necesite la registra al importarse, así todos los procesos derivan el mismo candado. El patrón
    calza sin distinguir mayúsculas y el nombre que deriva se normaliza (``normalizar_candado``)."""
    if raiz not in ("raiz_v2", "salidas_v2"):
        raise ValueError(f"raíz desconocida para un candado: {raiz!r}")
    REGLAS_CANDADO.insert(0, (raiz, _regla(patron), plantilla))


def normalizar_candado(nombre: str) -> str:
    """Nombre normalizado de un candado (Complemento de la Enmienda 1, punto 10): Unicode NFC y sin distinguir
    mayúsculas (casefold), como la guardia de escritura. Es el que llevan el archivo ``<nombre>.lock``, el
    registro de los candados tomados y lo que devuelve ``candado_de``."""
    return _plegar(nombre)


def _sanear(texto: str) -> str:
    """Nombre de candado válido y normalizado a partir de un texto (``/`` → ``.``; lo demás fuera de
    ``[a-z0-9_.-]``, ``_``); si es muy largo, se acorta con un sha256 del nombre completo."""
    nombre = re.sub(r"[^A-Za-z0-9_.-]", "_", normalizar_candado(texto).replace("/", "."))
    if len(nombre) > _LARGO_MAXIMO_CANDADO:
        nombre = f"{nombre[:_LARGO_MAXIMO_CANDADO - 17]}.{hashlib.sha256(nombre.encode('utf-8')).hexdigest()[:16]}"
    return nombre


def candado_de(ruta, rutas: RutasV2 | None = None) -> str | None:
    """Nombre (normalizado) del candado que protege el artefacto ``ruta``; None si escribir ahí no exige candado
    (el código).

    Las reglas de ``REGLAS_CANDADO`` agrupan los archivos de un mismo artefacto (el manifiesto y su respaldo, el
    punto de control de un pliegue, el consolidado de un protocolo y sus tablas, …); una ruta sin regla tiene su
    propio candado, con el nombre de su ruta relativa. Dos grafías de la misma ruta (mayúsculas o forma Unicode)
    dan el mismo nombre (Complemento, punto 10)."""
    r = rutas or rutas_v2()
    destino = _resolver(ruta)
    for atributo in ("raiz_v2", "salidas_v2"):
        rel = _relativa_a(destino, getattr(r, atributo))
        if rel is None:
            continue
        texto = unicodedata.normalize("NFC", rel.as_posix())
        for raiz, patron, plantilla in REGLAS_CANDADO:
            if raiz == atributo:
                m = patron.fullmatch(texto)
                if m:
                    return _sanear(plantilla.format(**m.groupdict()))
        return _sanear(f"{atributo}.{texto}")
    return None


_CERROJO = threading.Lock()          # protege _TOMADOS entre hilos
_TOMADOS: dict[str, dict] = {}       # clave plegada del archivo del candado → {fd, profundidad, hilo, nombre, carpeta}


def _ruta_candado(nombre: str, r: RutasV2) -> Path:
    """Archivo del candado ``nombre``, con el nombre normalizado (Complemento, punto 10)."""
    normal = normalizar_candado(nombre) if isinstance(nombre, str) else nombre
    if not isinstance(normal, str) or not _NOMBRE_CANDADO.fullmatch(normal):
        raise ValueError(f"nombre de candado inválido: {nombre!r} (letras, dígitos, '_', '.', '-')")
    return r.candados / f"{normal}.lock"


def _titular(ruta: Path) -> str:
    try:
        return ruta.read_text(encoding="utf-8").strip() or "(sin datos del titular)"
    except OSError:
        return "(no se pudo leer el titular)"


@contextlib.contextmanager
def candado_escritura(nombre: str = "raiz", rutas: RutasV2 | None = None, espera_s: float = 0.0,
                      intervalo_s: float = 0.2) -> Iterator[Path]:
    """Candado exclusivo ``nombre`` sobre ``<raíz v2>/.candados/<nombre>.lock``, entre procesos y entre hilos.

    Es reentrante sólo para el hilo que lo tiene. Si otro proceso u otro hilo lo tiene, espera hasta ``espera_s``
    segundos y luego levanta ``CandadoOcupado`` con los datos del titular (pid, máquina, hilo, inicio y programa).
    El archivo del candado no se borra al soltarlo: borrarlo abriría una carrera entre procesos. Para escribir un
    artefacto hay que tener **su** candado (``candado_de``); ``candado_artefactos`` los toma por ruta. El nombre se
    normaliza (NFC + casefold; Complemento, punto 10): «X.LRO» y «x.lro» son el mismo candado."""
    r = rutas or rutas_v2()
    ruta = _ruta_candado(nombre, r)
    nombre = ruta.name[:-len(".lock")]                    # el normalizado
    clave = _plegar(str(ruta))
    yo = threading.get_ident()
    with _CERROJO:
        actual = _TOMADOS.get(clave)
        reentrante = actual is not None and actual["hilo"] == yo
        if reentrante:
            actual["profundidad"] += 1
    if reentrante:
        try:
            yield ruta
        finally:
            with _CERROJO:
                _TOMADOS[clave]["profundidad"] -= 1
        return
    verificar_escritura(ruta, r)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    limite = time.monotonic() + max(0.0, float(espera_s))
    fd = None
    try:
        while True:
            with _CERROJO:
                de_otro_hilo = clave in _TOMADOS
            if not de_otro_hilo:
                if fd is None:
                    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with _CERROJO:
                        if clave in _TOMADOS:                     # otro hilo ganó la carrera entre el chequeo y el flock
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        else:
                            _TOMADOS[clave] = {"fd": fd, "profundidad": 1, "hilo": yo, "nombre": nombre,
                                               "carpeta": _plegar(str(r.candados))}
                            break
                except OSError as exc:
                    if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                        raise
            if time.monotonic() >= limite:
                quien = "otro hilo de este proceso" if de_otro_hilo else _titular(ruta)
                raise CandadoOcupado(f"El candado {ruta} está tomado: {quien}") from None
            time.sleep(intervalo_s)
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise
    try:
        titular = {"pid": os.getpid(), "maquina": socket.gethostname(), "hilo": threading.current_thread().name,
                   "desde_utc": ahora_utc(), "programa": Path(sys.argv[0]).name if sys.argv and sys.argv[0] else None}
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, (json.dumps(titular, ensure_ascii=False) + "\n").encode("utf-8"))
        os.fsync(fd)
        yield ruta
    finally:
        with _CERROJO:
            _TOMADOS.pop(clave, None)
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def candado_tomado(rutas: RutasV2 | None = None, nombre: str | None = None) -> bool:
    """¿Tiene **este hilo** el candado ``nombre`` de la raíz v2 de ``rutas`` (o, sin nombre, alguno de ellos)?"""
    r = rutas or rutas_v2()
    yo = threading.get_ident()
    with _CERROJO:
        if nombre is not None:
            info = _TOMADOS.get(_plegar(str(_ruta_candado(nombre, r))))
            return info is not None and info["hilo"] == yo
        carpeta = _plegar(str(r.candados))
        return any(v["carpeta"] == carpeta and v["hilo"] == yo for v in _TOMADOS.values())


@contextlib.contextmanager
def candado_artefactos(destinos: Iterable, rutas: RutasV2 | None = None, espera_s: float = 0.0,
                       intervalo_s: float = 0.2) -> Iterator[list[str]]:
    """Toma los candados de todos los artefactos ``destinos`` (sin repetir y en orden alfabético, para que dos
    procesos no se traben) y devuelve sus nombres."""
    r = rutas or rutas_v2()
    nombres = sorted({n for n in (candado_de(d, r) for d in destinos) if n is not None}, key=_plegar)
    with contextlib.ExitStack() as pila:
        for nombre in nombres:
            pila.enter_context(candado_escritura(nombre, r, espera_s=espera_s, intervalo_s=intervalo_s))
        yield nombres


# ---------------------------------------------------------------------------
# Escritura atómica
# ---------------------------------------------------------------------------
def _preparar_destino(ruta, rutas: RutasV2 | None) -> Path:
    r = rutas or rutas_v2()
    destino = verificar_escritura(ruta, r)
    nombre = candado_de(destino, r)
    if nombre is not None and not candado_tomado(r, nombre):
        raise EscrituraNoPermitida(f"{destino}: escribir este artefacto exige que este hilo tenga su candado "
                                   f"«{nombre}» (candado_escritura({nombre!r}) o candado_artefactos([ruta])); otro "
                                   f"candado no basta (Enmienda 1, punto 14)")
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
    """``os.replace`` con las mismas guardas en ambos extremos (para respaldar un artefacto): exige los candados
    del artefacto de origen y del de destino."""
    r = rutas or rutas_v2()
    o = _preparar_destino(origen, r)
    d = _preparar_destino(destino, r)
    os.replace(o, d)
    _fsync_carpeta(d.parent)
    return d


def ruta_de_respaldo(ruta, etiqueta: str) -> Path:
    """``<nombre>_<etiqueta>_<sello UTC>[_n]<sufijo>`` junto a ``ruta``, sin pisar un respaldo que ya exista (dos
    respaldos en el mismo segundo llevan ``_1``, ``_2``, …). No escribe nada."""
    p = Path(ruta)
    sello = ahora_utc().replace(":", "").replace("-", "")
    destino, n = p.with_name(f"{p.stem}_{etiqueta}_{sello}{p.suffix}"), 1
    while destino.exists():
        destino, n = p.with_name(f"{p.stem}_{etiqueta}_{sello}_{n}{p.suffix}"), n + 1
    return destino


def copiar_artefacto(origen, destino, rutas: RutasV2 | None = None) -> str:
    """Copia atómica de ``origen`` en ``destino`` para respaldar un artefacto antes de sobrescribirlo: las guardas de
    escritura y el candado del artefacto de destino (``publicar_bytes``), las fechas del original conservadas (como
    ``cp -p``) y los bytes comprobados por su sha256. El original no se toca. Devuelve el sha256."""
    r = rutas or rutas_v2()
    o = Path(origen)
    datos = o.read_bytes()
    st = os.stat(o)
    sha = publicar_bytes(datos, destino, r)
    d = verificar_escritura(destino, r)
    os.utime(d, ns=(st.st_atime_ns, st.st_mtime_ns))
    if _sha256_archivo(d) != sha or hashlib.sha256(datos).hexdigest() != sha:
        raise RuntimeError(f"la copia de {o.name} en {d.name} no conserva sus bytes")
    return sha


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


def estado_vigente(item) -> str:
    """«contrato» (valor fijado por el contrato), «ratificado» (provisional que una enmienda ratificó) o
    «pendiente» (provisional todavía sin ratificar)."""
    if isinstance(item, dict) and "estado" in item:
        estado = str(item["estado"])
        if estado == ESTADO_PENDIENTE:
            return "pendiente"
        if estado.startswith(PREFIJO_RATIFICADO):
            return "ratificado"
        raise ValueError(f"estado desconocido en config_v2.json: {estado!r}")
    if isinstance(item, str) and item == ESTADO_PENDIENTE:
        return "pendiente"
    return "contrato"


def valor_vigente(item, nombre: str):
    """Valor que usa el código: el del contrato; el «valor» de un provisional que una enmienda ratificó
    (``{"estado": "ratificado (Enmienda 1)", "valor": …}``); o, si sigue pendiente, el «provisional» declarado en la
    configuración. Un pendiente sin provisional, un ratificado sin valor o un estado desconocido detienen la corrida."""
    if isinstance(item, dict) and "estado" in item:
        estado = str(item["estado"])
        if estado == ESTADO_PENDIENTE:
            if "provisional" not in item:
                raise ValueError(f"{nombre}: está pendiente en config_v2.json y no tiene valor provisional")
            return item["provisional"]
        if estado.startswith(PREFIJO_RATIFICADO):
            if "valor" not in item:
                raise ValueError(f"{nombre}: está ratificado en config_v2.json pero no tiene «valor»")
            return item["valor"]
        raise ValueError(f"{nombre}: estado desconocido en config_v2.json: {estado!r}")
    if isinstance(item, str) and item == ESTADO_PENDIENTE:
        raise ValueError(f"{nombre}: está pendiente en config_v2.json")
    return item


# ---------------------------------------------------------------------------
# Hilos de los programas de línea de órdenes (antes de importar numpy)
# ---------------------------------------------------------------------------
def hilos_maximos_config(rutas: RutasV2 | None = None, por_omision: int = 12) -> int:
    """``operacion.hilos_maximos`` de la configuración, sin verificar el contrato (sólo para el tope de hilos)."""
    r = rutas or rutas_v2()
    try:
        return int(json.loads(r.config.read_text(encoding="utf-8"))["operacion"]["hilos_maximos"])
    except (OSError, KeyError, ValueError, TypeError):
        return int(por_omision)


def hilos_de_la_linea(argv: list[str] | None = None, por_omision: int | None = None,
                      tope: int | None = None) -> int:
    """Hilos pedidos con ``--hilos N`` en la línea de órdenes (por omisión, ``operacion.hilos_maximos``), acotados
    al tope de la configuración. Se llama antes de importar numpy, para fijar las variables de entorno de BLAS y
    OpenMP (``_traza_v2.fijar_hilos``) antes de que se carguen esas bibliotecas."""
    maximo = int(tope) if tope is not None else hilos_maximos_config()
    previo = argparse.ArgumentParser(add_help=False)
    previo.add_argument("--hilos", type=int, default=None)
    pedido = previo.parse_known_args(sys.argv[1:] if argv is None else list(argv))[0].hilos
    n = int(pedido) if pedido else int(por_omision if por_omision is not None else maximo)
    return max(1, min(n, maximo))
