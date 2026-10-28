"""Entorno fijado, rutas por alias, carpetas de salida y hilos (§8 del texto).

Responsabilidad única: el proceso y el disco. Reexporta de ``reloj_dmc.entorno`` el intérprete, las huellas y el JSON
canónico (§9.1 del diseño); las prohibiciones y la escritura atómica son propias, con el mismo nombre (ENT-7). Agrega
los alias y carpetas de este producto. Toda guarda de rutas mira primero la ruta léxica y sólo después la resuelve
(§0, regla 10), y al resolverla nunca consulta un componente bajo /Volumes: ni ``rutas_reales`` ni ``alias`` ni
``carpeta_salida`` ni las guardas abren ni consultan nada bajo /Volumes.

Alias (encabezado del texto y §2.3 del diseño), con la misma anidación en las rutas reales y en las sintéticas:
- AP = el repositorio de este archivo (``parents[2]``); APH = el hermano «Air-Pollution-Health-Chile»;
- LOCAL = ``Path.home()/Asesorias_Data_local/AirPollution``;
- DATOS = ``/Volumes/Datos/Asesorias_Data/AirPollution/data``, y bajo DATOS: DMC, ERA5L, NASADEM, INVARIANTES, GHS y
  SINCA_MET;
- bajo LOCAL: GRILLA, PESOS y V3.
Así el código no escribe el usuario ni la cuenta, y lo que va a una salida va por alias.

Lecturas propias (ENT-n), para el addendum de M1:
- ENT-1. INVARIANTES = ``DATOS/contaminantes/ERA5Land/invariantes`` (el destino por omisión de
  ``scripts_pipeline/descargar_era5land_geopotencial.py`` y la ruta de ``m0/huellas_m0.json``); GHS =
  ``DATOS/poblacion/ghs_pop_r2023a`` (``pesos_poblacion.GHS_DIR``); SINCA_MET = ``DATOS/sinca_meteorologia``
  (destino por omisión de ``descargar_sinca_meteorologia.py``). Sólo se leyó código, nunca los datos.
- ENT-2. PESOS = ``LOCAL/neuro/poblacion``, la carpeta de ``poblacion_celda_anio.parquet`` según
  ``APH/scripts_neuro/_pesos.py`` (``SALIDA``) cuando no se define ``AIR_POLLUTION_LOCAL_ROOT``. Este paquete no lee
  esa variable: la ruta es la de por omisión de ``_pesos.py``, y una prueba lo compara.
- ENT-3. V3 = ``LOCAL/riesgo_agudo_v3/meteo_civil``: la carpeta común de ``civil``, ``utc4`` y ``regional`` que fija
  ``config_v3.json`` (``confusores.meteorologia_productos``). Ojo: en la configuración v3 el alias «LOCAL» es
  ``~/Asesorias_Data_local`` (sin «AirPollution»); aquí LOCAL es el de este texto, como en RELOJ. Las rutas coinciden.
- ENT-4. ``carpeta_salida`` (§8 del texto, §0 regla 10 del diseño). Compuertas y carpetas, todas bajo
  ``LOCAL/meteo_combinada/v1``:
  - «m1» → ``m1`` y «m2a» → ``m2a`` (con ``etiqueta``, una subcarpeta de ellas);
  - «m34» y «m5» → la carpeta de la corrida sellada, ``<etiqueta>`` = ``HUMAN<AAAAMMDD>_METEO_COMB_<n>``, y con una
    errata posterior a la frontera ``…_ERRATA<k>`` (§10). M5 publica en la misma carpeta que su M3-4 (§8: ``salud/``,
    ``producto_01deg/``…);
  - «m6» → ``<etiqueta>/m6`` (§8: «``m6/``: ``decision_m6.json``…»).
  No crea la carpeta (sólo ``salidas`` escribe) y rechaza /Volumes y los repositorios.
- ENT-5. ``fijar_hilos``: fija en «1» las tres variables (también si ya estaban; las heredan los procesos hijos),
  carga numpy y aplica ``threadpoolctl.threadpool_limits(1)`` a las bibliotecas ya cargadas. Falla si alguna variable
  o alguna biblioteca de ``threadpool_info()`` no queda en 1. Devuelve las variables y las bibliotecas, sin rutas.
- ENT-6. ``rutas_sinteticas`` reproduce la anidación real bajo la carpeta temporal (``<raíz>/DATOS/…/DMC``,
  ``<raíz>/LOCAL/modelado_1km/grilla_1km``…), para que el código que arma una ruta desde DATOS o desde LOCAL dé lo
  mismo que el alias. Crea las 13 carpetas. Desde la revisión de la ola 1 (B-H13) exige que la raíz esté **bajo**
  ``tempfile.gettempdir()`` resuelto (§5.1 del diseño: «Toda fabricación ocurre en ``tempfile.TemporaryDirectory``»):
  una raíz fuera de la carpeta temporal del sistema se rechaza aunque no sea /Volumes ni un repositorio, porque LOCAL
  guarda datos reales con los mismos nombres.
- ENT-7. **Guardas que nunca consultan /Volumes** (revisión de la ola 1, B-H8). ``prohibido_volumes`` y
  ``prohibido_repositorios`` del reloj resuelven la ruta con ``os.path.realpath``: un enlace (en una carpeta temporal)
  que lleva a /Volumes haría consultar los componentes de /Volumes al resolverlo. Este módulo **no las reexporta**:
  define las suyas con el mismo nombre, que miran la ruta léxica y después la resuelven componente a componente
  (``_resolver_seguro``: ``os.lstat`` y ``os.readlink`` sobre cada componente), deteniéndose **antes** de consultar un
  componente que cae bajo /Volumes (desde ahí el resto es léxico). Es una diferencia con §9.1 del diseño, que las
  daba por reexportadas. ``escribir_atomico`` es un envoltorio: aplica estas dos guardas al destino y a su «.part» y
  después llama a la del reloj, que ya no puede llegar a /Volumes por un enlace (las dos siguen el mismo camino).
- ENT-8. **Etiqueta de una corrida** (B-H22): además del patrón ``HUMAN<AAAAMMDD>_METEO_COMB_<n>[_ERRATA<k>]``, la fecha
  debe existir (como ``_fecha_ocho`` del reloj): ``HUMAN20261399_…`` se rechaza (``es_etiqueta_corrida``).
- ENT-9. **Carpeta de trabajo temporal** (ola 6; PED-3 de I22 y PED-4 de I21). ``costo.medir`` y la batería
  (``verificar --sintetico --costo``) necesitan dónde trabajar, y no pueden escribir ni borrar (§0, regla 8).
  ``with carpeta_de_trabajo(prefijo) as carpeta:`` la da:
  - **La crea** con ``tempfile.mkdtemp`` (permisos 0700, nombre ``<prefijo>`` más ocho caracteres al azar) bajo la carpeta
    temporal del sistema, resuelta sin consultar /Volumes, como ``rutas_sinteticas``. Si ``tempfile.gettempdir`` aún no
    eligió carpeta, antes se miran TMPDIR, TEMP y TMP, porque al elegirla escribe un archivo de prueba en la
    candidata. La temporal no puede caer bajo /Volumes ni en los repositorios. El prefijo es un nombre simple
    (``[A-Za-z0-9][A-Za-z0-9_.-]*``).
  - **La borra entera al salir**, también si el cuerpo lanza una excepción. Antes exige que la ruta cuelgue de la
    temporal del sistema (léxica, y su carpeta madre resuelta sin consultar /Volumes) y que siga siendo la misma
    carpeta: mismo dispositivo e inodo que al crearla, no un enlace ni otra cosa puesta en su lugar. Si no, lanza
    PermissionError y no borra nada: una carpeta movida queda donde la movieron, y un enlace en su lugar queda, con su
    destino intacto.
  - **Sin seguir enlaces.** Borra con ``shutil.rmtree``, que en este sistema no los sigue (``avoids_symlink_attacks``;
    si no, RuntimeError y no borra). Un enlace adentro hacia /Volumes, AP u otra carpeta se borra como enlace y su
    destino queda intacto; nada consulta /Volumes.
  - Si el cuerpo lanzó una excepción y además el borrado se niega, se propaga la del borrado, con la del cuerpo como
    contexto.
Depende de: reloj_dmc.entorno.
"""
from __future__ import annotations

import os
import re
import shutil
import stat as _stat
import sys
import tempfile
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Iterator

from reloj_dmc import entorno as _reloj
from reloj_dmc.entorno import (IANA_FIJADO, INTERPRETE, NETCDF4_FIJADO, PANDAS_FIJADO,  # noqa: F401
                               PYTHON_FIJADO, TZDATA_FIJADO, comprobar_interprete, json_canonico, reiniciar_zonas,
                               sha256_archivo, sha256_bytes, sin_datos_privados)

# Raíces (encabezado del texto). DATOS no se consulta nunca al construir rutas.
NOMBRE_AP = "Air-Pollution"
NOMBRE_APH = "Air-Pollution-Health-Chile"
SUBRUTA_LOCAL = "Asesorias_Data_local/AirPollution"
DATOS_REAL = PurePosixPath("/Volumes/Datos/Asesorias_Data/AirPollution/data")

# Alias bajo DATOS y bajo LOCAL (ENT-1 a ENT-3).
BAJO_DATOS = {
    "dmc": "meteorologia/estaciones_horarias/DMC",
    "era5l": "contaminantes/ERA5Land/chile_nativo_01deg",
    "nasadem": "contaminantes/Topografia/NASADEM_30m_native",
    "invariantes": "contaminantes/ERA5Land/invariantes",
    "ghs": "poblacion/ghs_pop_r2023a",
    "sinca_met": "sinca_meteorologia",
}
BAJO_LOCAL = {
    "grilla": "modelado_1km/grilla_1km",
    "pesos": "neuro/poblacion",
    "v3": "riesgo_agudo_v3/meteo_civil",
}
SUBRUTA_SALIDAS = "meteo_combinada/v1"

# Campo de Rutas → alias, en el orden de la dataclass.
ALIAS = {"ap": "AP", "aph": "APH", "local": "LOCAL", "datos": "DATOS", "dmc": "DMC", "era5l": "ERA5L",
         "nasadem": "NASADEM", "invariantes": "INVARIANTES", "ghs": "GHS", "sinca_met": "SINCA_MET",
         "grilla": "GRILLA", "pesos": "PESOS", "v3": "V3"}

# ENT-4: compuertas y la etiqueta de una corrida sellada (§10).
COMPUERTAS = ("m1", "m2a", "m34", "m5", "m6")
PATRON_ETIQUETA_CORRIDA = re.compile(r"HUMAN(?P<anio>\d{4})(?P<mes>\d{2})(?P<dia>\d{2})_METEO_COMB_(?P<n>[1-9]\d*)"
                                     r"(?:_ERRATA(?P<errata>[1-9]\d*))?")
_PATRON_SUBCARPETA = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")

VARIABLES_HILOS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
UN_HILO = "1"


@dataclass(frozen=True)
class Rutas:
    """Rutas reales de una corrida. En modo sintético todas apuntan a carpetas temporales."""
    ap: Path
    aph: Path
    local: Path
    datos: Path
    dmc: Path
    era5l: Path
    nasadem: Path
    invariantes: Path
    ghs: Path
    sinca_met: Path
    grilla: Path
    pesos: Path
    v3: Path

    @property
    def salidas(self) -> Path:
        """LOCAL/meteo_combinada/v1."""
        return self.local / SUBRUTA_SALIDAS


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
def _lexica(ruta) -> Path:
    """Ruta absoluta normalizada sin tocar el disco (relativa → respecto del directorio actual)."""
    return Path(os.path.normpath(os.path.abspath(os.fspath(ruta))))


def _bajo(ruta: Path, raiz: Path) -> bool:
    """True si ``ruta`` es ``raiz`` o cuelga de ella, componente a componente (léxico)."""
    return ruta == raiz or raiz in ruta.parents


_AP_RESUELTO = Path(__file__).resolve().parents[2]      # el archivo propio, una vez al importarse (no es /Volumes)


def _ap_real() -> Path:
    ap = _AP_RESUELTO
    if ap.name != NOMBRE_AP:
        raise RuntimeError(f"El paquete no está en el repositorio esperado («{NOMBRE_AP}»)")
    return ap


def _construir(ap: Path, aph: Path, local: Path, datos: Path) -> Rutas:
    return Rutas(ap=ap, aph=aph, local=local, datos=datos,
                 **{k: datos / v for k, v in BAJO_DATOS.items()}, **{k: local / v for k, v in BAJO_LOCAL.items()})


def rutas_reales() -> Rutas:
    """Las rutas de las corridas reales. Sólo construye rutas: no consulta el disco."""
    ap = _ap_real()
    return _construir(ap, ap.parent / NOMBRE_APH, Path.home() / SUBRUTA_LOCAL, Path(DATOS_REAL))


def rutas_sinteticas(raiz_temporal) -> Rutas:
    """Las 13 rutas bajo una carpeta temporal, con la anidación real (ENT-6), y las crea.

    Rechaza, antes de tocar el disco, una raíz bajo /Volumes o dentro de los repositorios reales (ENT-7), y una raíz que
    no esté bajo ``tempfile.gettempdir()`` resuelto (B-H13). La raíz se resuelve sin consultar /Volumes (en macOS,
    /var → /private/var) para que ``alias`` compare siempre la misma forma.
    """
    prohibido_volumes(raiz_temporal)
    prohibido_repositorios(raiz_temporal)
    raiz = Path(_resolver_seguro(raiz_temporal)[0])
    temporal = Path(_resolver_seguro(tempfile.gettempdir())[0])
    if temporal not in raiz.parents:
        raise PermissionError("rutas_sinteticas exige una raíz bajo la carpeta temporal del sistema "
                              "(tempfile.TemporaryDirectory; §5.1 del diseño)")
    rutas = _construir(raiz / "AP", raiz / "APH", raiz / "LOCAL", raiz / "DATOS")
    for f in fields(rutas):
        getattr(rutas, f.name).mkdir(parents=True, exist_ok=True)
    return rutas


def alias(ruta, rutas: Rutas) -> str:
    """«AP/…», «APH/…», «LOCAL/…», «DATOS/…», «ERA5L/…», «GRILLA/…»…; ValueError si la ruta no cae bajo ningún alias.

    Léxica (no toca el disco); si dos alias contienen la ruta, gana el más profundo. El resultado usa «/» y pasa
    ``sin_datos_privados``.
    """
    if not Path(ruta).is_absolute():
        raise ValueError("alias exige una ruta absoluta")
    destino = _lexica(ruta)
    candidatos = []
    for campo, nombre in ALIAS.items():
        raiz = _lexica(getattr(rutas, campo))
        if _bajo(destino, raiz):
            candidatos.append((len(raiz.parts), nombre, raiz))
    if not candidatos:
        raise ValueError("La ruta no cae bajo ningún alias de este producto")
    _, nombre, raiz = max(candidatos, key=lambda c: c[0])
    resto = destino.relative_to(raiz)
    texto = nombre if resto == Path(".") else f"{nombre}/{PurePosixPath(*resto.parts).as_posix()}"
    if not sin_datos_privados(texto):
        raise ValueError("El alias de la ruta contiene datos privados")
    return texto


def carpeta_salida(rutas: Rutas, compuerta: str, etiqueta: str | None = None) -> Path:
    """LOCAL/meteo_combinada/v1/… de una compuerta (ENT-4); nunca bajo /Volumes ni en los repositorios. No la crea."""
    if compuerta not in COMPUERTAS:
        raise ValueError(f"compuerta desconocida: {compuerta!r} (son {COMPUERTAS})")
    base = rutas.salidas
    if compuerta in ("m1", "m2a"):
        destino = base / compuerta
        if etiqueta is not None:
            if not isinstance(etiqueta, str) or not _PATRON_SUBCARPETA.fullmatch(etiqueta) or etiqueta in (".", ".."):
                raise ValueError(f"etiqueta de subcarpeta inválida: {etiqueta!r}")
            destino = destino / etiqueta
    else:
        if not es_etiqueta_corrida(etiqueta):
            raise ValueError(f"{compuerta} exige la etiqueta de la corrida HUMAN<AAAAMMDD>_METEO_COMB_<n>: {etiqueta!r}")
        destino = base / etiqueta
        if compuerta == "m6":
            destino = destino / "m6"
    destino = _lexica(destino)
    prohibido_volumes(destino)
    prohibido_repositorios(destino)
    return destino


def es_etiqueta_corrida(texto) -> bool:
    """``HUMAN<AAAAMMDD>_METEO_COMB_<n>[_ERRATA<k>]`` con una fecha que existe (ENT-8)."""
    m = PATRON_ETIQUETA_CORRIDA.fullmatch(texto) if isinstance(texto, str) else None
    if m is None:
        return False
    try:
        date(int(m.group("anio")), int(m.group("mes")), int(m.group("dia")))
    except ValueError:
        return False
    return True


def etiqueta_corrida(fecha_aaaammdd: str, numero: int = 1, errata: int | None = None) -> str:
    """``HUMAN<AAAAMMDD>_METEO_COMB_<n>`` y, con una errata, ``…_ERRATA<k>`` (§10)."""
    texto = f"HUMAN{fecha_aaaammdd}_METEO_COMB_{numero}" + (f"_ERRATA{errata}" if errata is not None else "")
    if not es_etiqueta_corrida(texto):
        raise ValueError(f"etiqueta de corrida inválida: {texto!r}")
    return texto


# ---------------------------------------------------------------------------
# Guardas de escritura que nunca consultan /Volumes (ENT-7)
# ---------------------------------------------------------------------------
_MAX_ENLACES = 40  # no-umbral: tope de enlaces seguidos al resolver una ruta, como MAXSYMLINKS


def _en_volumes(texto: str) -> bool:
    """True si la ruta (absoluta, normalizada) es /Volumes o cuelga de /Volumes, sin distinguir mayúsculas (APFS)."""
    partes = Path(texto).parts
    return len(partes) >= 2 and partes[0] == os.sep and partes[1].casefold() == "volumes"


def _resolver_seguro(ruta) -> tuple[str, bool]:
    """Sigue los enlaces de ``ruta`` componente a componente sin consultar nunca un componente bajo /Volumes.

    Devuelve (ruta resuelta, llega a /Volumes). En cuanto el camino entra en /Volumes, el resto se arma de forma léxica
    y no se consulta. Un componente que no existe deja el resto léxico. Más de ``_MAX_ENLACES`` enlaces: OSError.
    """
    texto = os.path.normpath(os.path.abspath(os.fspath(ruta)))
    if _en_volumes(texto):
        return texto, True
    pendientes = deque(p for p in texto.split(os.sep) if p)
    actual, saltos = os.sep, 0
    while pendientes:
        parte = pendientes.popleft()
        if parte == ".":
            continue
        if parte == "..":
            actual = os.path.dirname(actual) or os.sep
            continue
        candidato = os.path.join(actual, parte)
        if _en_volumes(candidato):
            return os.path.normpath(os.path.join(candidato, *pendientes)), True
        try:
            st = os.lstat(candidato)
        except OSError:
            resto = os.path.normpath(os.path.join(candidato, *pendientes))
            return resto, _en_volumes(resto)
        if _stat.S_ISLNK(st.st_mode):
            saltos += 1
            if saltos > _MAX_ENLACES:
                raise OSError(f"demasiados enlaces al resolver la ruta ({_MAX_ENLACES})")
            destino = os.readlink(candidato)
            if os.path.isabs(destino):
                actual = os.sep
            pendientes.extendleft(reversed([p for p in destino.split(os.sep) if p]))
            continue
        actual = candidato
    return actual, False


def prohibido_volumes(ruta) -> None:
    """PermissionError si una escritura apunta bajo /Volumes, léxicamente o por un enlace, sin consultar /Volumes."""
    if _en_volumes(str(_lexica(ruta))):
        raise PermissionError("Escritura bajo /Volumes prohibida (§8 del texto)")
    if _resolver_seguro(ruta)[1]:
        raise PermissionError("Escritura bajo /Volumes prohibida (§8 del texto): la ruta lleva allí por un enlace")


def prohibido_repositorios(ruta) -> None:
    """PermissionError si una escritura apunta dentro de AP o APH reales (léxica o resuelta sin consultar /Volumes)."""
    ap = _ap_real()
    repos = (ap, ap.parent / NOMBRE_APH)
    resuelta, _ = _resolver_seguro(ruta)
    for p in (_lexica(ruta), Path(resuelta)):
        if any(_bajo(p, r) for r in repos):
            raise PermissionError("Escritura en los repositorios prohibida durante una corrida (§0, regla 10)")


def escribir_atomico(ruta, datos) -> str:
    """La escritura atómica del reloj («.part», fsync y renombre; devuelve el sha256), con las guardas de ENT-7 antes:
    destino y «.part» no pueden caer bajo /Volumes ni en los repositorios, tampoco por un enlace."""
    destino = _lexica(ruta)
    for r in (destino, destino.with_name(destino.name + ".part")):
        prohibido_volumes(r)
        prohibido_repositorios(r)
    return _reloj.escribir_atomico(destino, datos)


# ---------------------------------------------------------------------------
# Carpeta de trabajo temporal (ENT-9)
# ---------------------------------------------------------------------------
PREFIJO_TRABAJO = "meteo_combinada_"
_VARIABLES_TEMPORAL = ("TMPDIR", "TEMP", "TMP")      # las que mira tempfile.gettempdir al elegir carpeta


def _temporal_del_sistema() -> Path:
    """``tempfile.gettempdir()`` resuelta sin consultar /Volumes; PermissionError si cae bajo /Volumes o en los
    repositorios (ENT-9). Si gettempdir aún no eligió carpeta, mira antes las variables que usará."""
    if tempfile.tempdir is None:
        for variable in _VARIABLES_TEMPORAL:
            if os.environ.get(variable):
                prohibido_volumes(os.environ[variable])
    crudo = tempfile.gettempdir()
    prohibido_volumes(crudo)
    prohibido_repositorios(crudo)
    return Path(_resolver_seguro(crudo)[0])


def _identidad(estado: os.stat_result) -> tuple[int, int]:
    return estado.st_dev, estado.st_ino


def _borrar_carpeta_de_trabajo(carpeta, identidad: tuple[int, int]) -> None:
    """Borra la carpeta de trabajo entera, sin seguir enlaces, si sigue siendo la que se creó bajo la temporal del
    sistema; si no, PermissionError sin borrar nada (ENT-9)."""
    lexica = _lexica(carpeta)
    if _en_volumes(str(lexica)):
        raise PermissionError("la carpeta de trabajo cae bajo /Volumes: no se borra")
    temporal = _temporal_del_sistema()
    if temporal not in lexica.parents:               # primero lo léxico: fuera de la temporal no se consulta nada
        raise PermissionError("la carpeta de trabajo no está bajo la carpeta temporal del sistema: no se borra")
    madre, a_volumes = _resolver_seguro(lexica.parent)
    if a_volumes or not _bajo(Path(madre), temporal):
        raise PermissionError("la carpeta de trabajo no está bajo la carpeta temporal del sistema (su carpeta madre "
                              "lleva fuera por un enlace): no se borra")
    try:
        estado = os.lstat(lexica)
    except FileNotFoundError:
        raise PermissionError("la carpeta de trabajo ya no está donde se creó (¿se movió?): no se borra nada") from None
    if _stat.S_ISLNK(estado.st_mode):
        raise PermissionError("la carpeta de trabajo pasó a ser un enlace: no se borra, ni lo que apunta")
    if not _stat.S_ISDIR(estado.st_mode) or _identidad(estado) != tuple(identidad):
        raise PermissionError("en lugar de la carpeta de trabajo hay otra cosa: no se borra")
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError("en este sistema shutil.rmtree podría seguir enlaces: la carpeta de trabajo no se borra")
    shutil.rmtree(lexica)


@contextmanager
def carpeta_de_trabajo(prefijo: str = PREFIJO_TRABAJO) -> Iterator[Path]:
    """Una carpeta nueva bajo la temporal del sistema (resuelta sin consultar /Volumes), que se borra entera al salir,
    también con una excepción, sin seguir enlaces (ENT-9). Se niega a borrar (PermissionError, sin borrar nada) si ya
    no es la carpeta que creó, si pasó a ser un enlace o si no cuelga de la temporal del sistema."""
    if not isinstance(prefijo, str) or not _PATRON_SUBCARPETA.fullmatch(prefijo):
        raise ValueError(f"prefijo de carpeta de trabajo inválido: {prefijo!r}")
    temporal = _temporal_del_sistema()
    carpeta = Path(tempfile.mkdtemp(prefix=prefijo, dir=temporal))
    identidad = _identidad(os.lstat(carpeta))
    try:
        yield carpeta
    finally:
        _borrar_carpeta_de_trabajo(carpeta, identidad)


# ---------------------------------------------------------------------------
# Hilos (§8 del texto; MC-36)
# ---------------------------------------------------------------------------
def fijar_hilos() -> dict:
    """Variables de entorno y threadpoolctl en 1 (ENT-5); RuntimeError si algo no queda en 1."""
    for variable in VARIABLES_HILOS:
        os.environ[variable] = UN_HILO
    import numpy  # noqa: F401  (carga las bibliotecas de álgebra lineal, ya con las variables)
    import threadpoolctl
    limites = threadpoolctl.threadpool_limits(limits=int(UN_HILO))
    _LIMITES.append(limites)          # se conserva: el límite rige mientras viva el proceso
    bibliotecas = [{"api": b.get("user_api"), "biblioteca": b.get("internal_api"), "hilos": b.get("num_threads")}
                   for b in threadpoolctl.threadpool_info()]
    fallas = [f"{v}={os.environ.get(v)!r}" for v in VARIABLES_HILOS if os.environ.get(v) != UN_HILO]
    fallas += [f"{b['biblioteca']} con {b['hilos']} hilos" for b in bibliotecas if b["hilos"] != int(UN_HILO)]
    if fallas:
        raise RuntimeError("Los hilos del álgebra lineal no quedaron en 1: " + "; ".join(fallas))
    return {"variables": {v: os.environ[v] for v in VARIABLES_HILOS}, "bibliotecas": bibliotecas,
            "numpy_cargado": "numpy" in sys.modules}


_LIMITES: list = []

# Lo reexportado es el mismo objeto del reloj (§9.1 del diseño); test_entorno lo comprueba.
REEXPORTADOS = ("comprobar_interprete", "sha256_archivo", "sha256_bytes", "json_canonico", "sin_datos_privados",
                "reiniciar_zonas")
# Propias, con el mismo nombre y el mismo contrato que las del reloj, pero sin consultar /Volumes (ENT-7).
PROPIAS = ("prohibido_volumes", "prohibido_repositorios", "escribir_atomico")
assert all(globals()[n] is getattr(_reloj, n) for n in REEXPORTADOS)
