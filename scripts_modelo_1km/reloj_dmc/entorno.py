"""Entorno fijado, rutas por alias, huellas y escritura atómica (§9, §7.4 «Privacidad»).

Responsabilidad única: el proceso y el disco. No conoce la ciencia.
- Al importarse fija ``sys.dont_write_bytecode = True`` y reinicia la base de zonas a sólo el
  paquete tzdata (``zoneinfo.reset_tzpath(to=[])`` y ``ZoneInfo.clear_cache()``), como exige §9.
  No hace ninguna otra E/S al importarse.
- Las rutas reales se construyen desde ``Path.home()``; lo que se escribe en salidas va por alias
  (AP, APH, LOCAL, DMC, ERA5L), nunca con «/Users/» ni «@».
- Las rutas se comparan de forma léxica (``os.path.normpath``), sin tocar el disco: así ni
  ``alias`` ni ``prohibido_volumes`` abren ni consultan nada bajo /Volumes (§8, prueba 27).
Depende sólo de la biblioteca estándar.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import zoneinfo  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from importlib import metadata as _metadata  # noqa: E402
from pathlib import Path, PurePosixPath  # noqa: E402
from typing import Any, Mapping  # noqa: E402

zoneinfo.reset_tzpath(to=[])
zoneinfo.ZoneInfo.clear_cache()

# Entorno fijado (§9). Se comprueba, no se supone.
PYTHON_FIJADO = "3.11.16"
PANDAS_FIJADO = "2.3.3"
NETCDF4_FIJADO = "1.7.4"
TZDATA_FIJADO = "2026.3"
IANA_FIJADO = "2026c"
INTERPRETE = "~/micromamba/envs/amb_v2/bin/python"

# Alias del protocolo (encabezado). AP = parents[2] de este archivo; APH = AP.parent/«Air-Pollution-Health-Chile»;
# LOCAL = Path.home()/SUBRUTA_LOCAL. Así el código no escribe el usuario ni la cuenta.
VOLUMEN_DATOS = Path("/Volumes/Datos/Asesorias_Data/AirPollution")
SUBRUTA_DMC = "data/meteorologia/estaciones_horarias/DMC"
SUBRUTA_ERA5L = "data/contaminantes/ERA5Land/chile_nativo_01deg"
SUBRUTA_LOCAL = "Asesorias_Data_local/AirPollution"
SUBRUTA_CORRIDAS = "modelado_1km/verificacion_reloj_dmc/v1"

# «Base del sistema» de la prueba 2 de §8 (la del sistema operativo, IANA 2026e el 2026-10-23); no es la
# TZPATH compilada del intérprete, que en amb_v2 apunta a la tzdata de conda.
BASE_ZONAS_SISTEMA = "/usr/share/zoneinfo"

_BLOQUE_LECTURA = 1 << 20
_ORDEN_ALIAS = ("AP", "APH", "LOCAL", "DMC", "ERA5L")


@dataclass(frozen=True)
class Rutas:
    """Rutas reales de una corrida. En modo sintético todas apuntan a carpetas temporales."""
    ap: Path
    aph: Path
    local: Path
    dmc: Path
    era5l: Path

    @property
    def corridas(self) -> Path:
        """LOCAL/modelado_1km/verificacion_reloj_dmc/v1 (cerrojo y carpetas HUMAN…)."""
        return self.local / SUBRUTA_CORRIDAS


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
def _lexica(ruta: Path | str) -> Path:
    """Ruta absoluta normalizada sin tocar el disco (relativa → respecto del directorio actual)."""
    return Path(os.path.normpath(os.path.abspath(os.fspath(ruta))))


def _bajo(ruta: Path, raiz: Path) -> bool:
    """True si ``ruta`` es ``raiz`` o cuelga de ella, componente a componente (léxico)."""
    return ruta == raiz or raiz in ruta.parents


def _ap_real() -> Path:
    """AP = padre de scripts_modelo_1km de este archivo (sin consultar /Volumes)."""
    ap = Path(__file__).resolve().parents[2]
    if ap.name != ALIAS_ESPERADOS["AP"]:
        raise RuntimeError(f"El paquete no está en el repositorio esperado («{ALIAS_ESPERADOS['AP']}»)")
    return ap


def rutas_reales() -> Rutas:
    """Rutas de --aplicar y --control-era5. AP es el padre de scripts_modelo_1km de este archivo."""
    ap = _ap_real()
    return Rutas(ap=ap, aph=ap.parent / ALIAS_ESPERADOS["APH"], local=Path.home() / SUBRUTA_LOCAL,
                 dmc=VOLUMEN_DATOS / SUBRUTA_DMC, era5l=VOLUMEN_DATOS / SUBRUTA_ERA5L)


def rutas_sinteticas(raiz_temporal: Path) -> Rutas:
    """Rutas bajo una carpeta temporal (grupos A a D de §8); nada bajo /Volumes.

    Crea ``<raíz>/AP``, ``APH``, ``LOCAL``, ``DMC`` y ``ERA5L`` si no existen. La raíz se resuelve
    (en macOS, /var → /private/var) para que ``alias`` compare siempre la misma forma. Rechaza una
    raíz bajo /Volumes o dentro de los repositorios reales (§9: nada se escribe en ellos).
    """
    prohibido_volumes(raiz_temporal)
    prohibido_repositorios(raiz_temporal)
    raiz = Path(raiz_temporal).resolve()
    prohibido_volumes(raiz)
    prohibido_repositorios(raiz)
    carpetas = {nombre: raiz / nombre for nombre in _ORDEN_ALIAS}
    for carpeta in carpetas.values():
        carpeta.mkdir(parents=True, exist_ok=True)
    return Rutas(ap=carpetas["AP"], aph=carpetas["APH"], local=carpetas["LOCAL"], dmc=carpetas["DMC"],
                 era5l=carpetas["ERA5L"])


def alias(ruta: Path, rutas: Rutas) -> str:
    """Reescribe una ruta absoluta como «AP/…», «APH/…», «LOCAL/…», «DMC/…» o «ERA5L/…».

    Lanza ValueError si la ruta no cae bajo ningún alias (así nunca sale una ruta absoluta).
    La comparación es léxica (no toca el disco); si dos alias contienen la ruta, gana el más profundo.
    El resultado usa «/» y debe pasar ``sin_datos_privados``.
    """
    if not Path(ruta).is_absolute():
        raise ValueError("alias exige una ruta absoluta")
    destino = _lexica(ruta)
    raices = {"AP": rutas.ap, "APH": rutas.aph, "LOCAL": rutas.local, "DMC": rutas.dmc, "ERA5L": rutas.era5l}
    candidatos = []
    for nombre in _ORDEN_ALIAS:
        raiz = _lexica(raices[nombre])
        if _bajo(destino, raiz):
            candidatos.append((len(raiz.parts), nombre, raiz))
    if not candidatos:
        raise ValueError("La ruta no cae bajo ningún alias (AP, APH, LOCAL, DMC, ERA5L)")
    _, nombre, raiz = max(candidatos, key=lambda c: c[0])
    resto = destino.relative_to(raiz)
    texto = nombre if resto == Path(".") else f"{nombre}/{PurePosixPath(*resto.parts).as_posix()}"
    if not sin_datos_privados(texto):
        raise ValueError("El alias de la ruta contiene «/Users/» o «@»")
    return texto


# ---------------------------------------------------------------------------
# Intérprete
# ---------------------------------------------------------------------------
def _versiones_instaladas() -> dict[str, str]:
    """Versiones que se comparan con las fijadas (separado para poder simularlo en las pruebas)."""
    import tzdata  # paquete, no la base del sistema
    return {
        "python": platform.python_version(),
        "pandas": _metadata.version("pandas"),
        "netCDF4": _metadata.version("netCDF4"),
        "tzdata": _metadata.version("tzdata"),
        "iana": str(tzdata.IANA_VERSION),
    }


def comprobar_interprete() -> dict[str, str]:
    """Verifica Python 3.11.16, pandas 2.3.3, netCDF4 1.7.4 y tzdata 2026.3 (IANA 2026c).

    Devuelve las versiones para el informe; lanza RuntimeError si alguna difiere o si el proceso
    no corre con ``sys.flags.dont_write_bytecode`` o ``sys.dont_write_bytecode``.
    Comprueba además que el ejecutable sea ``INTERPRETE`` y que la base de zonas sea sólo el paquete
    tzdata (``zoneinfo.TZPATH == ()``), las otras dos condiciones del entorno fijado de §9.
    """
    fallas = []
    if not (sys.flags.dont_write_bytecode or sys.dont_write_bytecode):
        fallas.append("el proceso escribe bytecode (falta -B o sys.dont_write_bytecode)")
    esperado_exe = Path(os.path.expanduser(INTERPRETE)).resolve()
    if Path(sys.executable).resolve() != esperado_exe:
        fallas.append(f"el intérprete no es {INTERPRETE}")
    if zoneinfo.TZPATH != ():
        fallas.append("la base de zonas no es sólo el paquete tzdata (TZPATH no vacío)")
    versiones = _versiones_instaladas()
    esperadas = {"python": PYTHON_FIJADO, "pandas": PANDAS_FIJADO, "netCDF4": NETCDF4_FIJADO,
                 "tzdata": TZDATA_FIJADO, "iana": IANA_FIJADO}
    for nombre, valor in esperadas.items():
        if versiones.get(nombre) != valor:
            fallas.append(f"{nombre} {versiones.get(nombre)} ≠ {valor}")
    if fallas:
        raise RuntimeError("Entorno no fijado: " + "; ".join(fallas))
    return {**versiones, "interprete": INTERPRETE}


# ---------------------------------------------------------------------------
# Huellas y JSON
# ---------------------------------------------------------------------------
def sha256_archivo(ruta: Path) -> str:
    """sha256 hex de un archivo, leído entero en bloques, en modo sólo lectura."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while bloque := f.read(_BLOQUE_LECTURA):
            h.update(bloque)
    return h.hexdigest()


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def json_canonico(obj: Any) -> bytes:
    """JSON con claves ordenadas, separadores «,» y «:», UTF-8, ``allow_nan=False``, sin salto final."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------
def escribir_atomico(ruta: Path, datos: bytes) -> str:
    """Escribe en «ruta.part», hace fsync y renombra; devuelve el sha256. Nunca bajo /Volumes.

    Tampoco escribe en los repositorios reales (``prohibido_repositorios``). Crea las carpetas que
    falten, sólo después de esas dos comprobaciones.
    """
    if not isinstance(datos, (bytes, bytearray, memoryview)):
        raise TypeError("escribir_atomico recibe bytes")
    datos = bytes(datos)
    destino = _lexica(ruta)
    parcial = destino.with_name(destino.name + ".part")
    for r in (destino, parcial):
        prohibido_volumes(r)
        prohibido_repositorios(r)
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(parcial, "wb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        os.replace(parcial, destino)
    except BaseException:
        try:
            parcial.unlink()
        except FileNotFoundError:
            pass
        raise
    try:  # el renombre queda en disco al sincronizar la carpeta (no todos los sistemas lo permiten)
        fd = os.open(destino.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass
    return sha256_bytes(datos)


def prohibido_volumes(ruta: Path) -> None:
    """Lanza PermissionError si una escritura apunta bajo /Volumes (§9 «Sólo lectura»).

    Primero mira la ruta léxica (sin tocar el disco; mayúsculas indistintas, como APFS). Sólo si
    no está bajo /Volumes la resuelve, para atrapar un enlace simbólico que lleve allí.
    """
    def _en_volumes(p: Path) -> bool:
        return len(p.parts) >= 2 and p.parts[0] == "/" and p.parts[1].casefold() == "volumes"

    lexica = _lexica(ruta)
    if _en_volumes(lexica):
        raise PermissionError("Escritura bajo /Volumes prohibida (§9)")
    if _en_volumes(Path(os.path.realpath(lexica))):
        raise PermissionError("Escritura bajo /Volumes prohibida (§9): la ruta lleva allí por un enlace")


def prohibido_repositorios(ruta: Path) -> None:
    """Lanza PermissionError si una escritura apunta dentro de AP o APH reales (§9, R-32, R-49).

    Durante una corrida nada se escribe en los repositorios; la publicación (C5) es un paso aparte.
    """
    ap = _ap_real()
    repos = (ap, ap.parent / ALIAS_ESPERADOS["APH"])
    for p in {_lexica(ruta), Path(os.path.realpath(_lexica(ruta)))}:
        if any(_bajo(p, r) for r in repos):
            raise PermissionError("Escritura en los repositorios prohibida durante la corrida (§9)")


def sin_datos_privados(texto: str) -> bool:
    """True si el texto no contiene «/Users/» ni «@» (§7.4 «Privacidad»).

    Rechaza también la carpeta personal (``Path.home()``), por si no empieza con «/Users/».
    """
    casa = str(Path.home())
    return "/Users/" not in texto and "@" not in texto and (len(casa) <= 1 or casa not in texto)


def reiniciar_zonas(base: str = "tzdata") -> None:
    """``base="tzdata"``: sólo el paquete (reset_tzpath(to=[])); ``"sistema"``: la base del sistema.

    Siempre limpia la caché. Lo usan tablas.transiciones_utc (prueba 2) y la batería.
    La base del sistema es ``BASE_ZONAS_SISTEMA``; si no existe, lanza RuntimeError en vez de caer
    en silencio al paquete tzdata. Quien la usa debe volver después a ``reiniciar_zonas("tzdata")``.
    """
    if base == "tzdata":
        zoneinfo.reset_tzpath(to=[])
    elif base == "sistema":
        if not os.path.isdir(BASE_ZONAS_SISTEMA):
            raise RuntimeError("No hay base de zonas del sistema en " + BASE_ZONAS_SISTEMA)
        zoneinfo.reset_tzpath(to=[BASE_ZONAS_SISTEMA])
    else:
        raise ValueError(f"Base de zonas desconocida: {base!r} (tzdata o sistema)")
    zoneinfo.ZoneInfo.clear_cache()


ALIAS_ESPERADOS: Mapping[str, str] = {
    "AP": "Air-Pollution", "APH": "Air-Pollution-Health-Chile", "LOCAL": SUBRUTA_LOCAL,
    "DMC": SUBRUTA_DMC, "ERA5L": SUBRUTA_ERA5L,
}
