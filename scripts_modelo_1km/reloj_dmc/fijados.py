"""Código fijado ajeno: carga por ruta y huella, extracción por AST y versiones del descargador.

Responsabilidad única: toda interacción con código de los repositorios que este paquete no
escribe. Nada de ese código se modifica (§7.3, §9).
- El adaptador ``v2/meteorologia_v2.py`` (f61559ea…): ``leer_artefacto``, ``normalizar``, ``_utc``,
  ``_confirmado``. Se carga por ruta con su sha256, como ``dmc_features._adapter``.
- ``v3/dmc_features.py`` (15762856…): ``cargar_dmc``. ``v3/preflight_v3.py`` (21905706…):
  ``policy_check``. Para cargarlos se agrega ``v3/`` a ``sys.path`` sólo durante la importación.
- ``_comun_modelo.py`` (a83c0384…): sólo se LEE su fuente para copiar ``MACROZONA_REGION`` (§3.3).
  Nunca se importa: importa ``_common``, que termina con SystemExit si el disco no está montado.
- ``verificar_reloj_sinca.py``: importa ``_comun_modelo``; la prueba 3 extrae ``transiciones`` por AST.
- El descargador ``scripts_pipeline/descargar_meteo_chile_horaria.py``: sólo en modo sintético
  (``run_download``, ``parse_report``) y para la huella de la ruta de etiqueta (Anexo C).

Cómo se carga un archivo fijado (``cargar_por_ruta``): se leen sus bytes una sola vez, se exige su
sha256, y se ejecutan exactamente esos bytes (``compile`` + ``exec`` sobre el módulo creado por
``spec_from_file_location``), de modo que lo ejecutado es lo que tiene la huella; al terminar se
vuelve a calcular la sha256 del archivo. No se escribe bytecode (``entorno`` fija
``sys.dont_write_bytecode``).

Lectura de «el nodo de nivel superior llamado n» (Anexo C y extracción por AST): el nombre debe
ligarse UNA sola vez en el nivel superior del módulo (def, class, asignación, asignación anotada o
aumentada, import). Si falta o se liga más de una vez, la huella no se calcula y la versión no se
admite (lectura conservadora; ninguna de las versiones recuperadas está en ese caso).
Depende de: entorno.
"""
from __future__ import annotations

import __future__ as _futuro
import ast
import builtins
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from reloj_dmc import entorno

# Huellas citadas por el protocolo (§1.9, §10 tabla de anclaje). Completas en tabla_anclaje_c0.json.
SHA_ADAPTADOR = "f61559eab281846a4935eb1ea66217e039ff37a727833bf8fcaa7a774b776754"
SHA_DMC_FEATURES = "157628564ffafb2cfc6aab5403e984d8451f7faa31e6f5ce21e743023d766bec"
SHA_PREFLIGHT_V3 = "21905706c69cb9a2b52cdd1a2e3ce17a535d5f18e32ead71d1348020f63bc0f7"
SHA_METEO_GUARD = "06e59f133c8ea29f019144364a43311a66c9a6bb3b9a69d77358eb6483e7fc71"
SHA_COMUN_MODELO = "a83c0384266554e16ab397749544759ae1cf161f138361eefa7d1ad3e29aa6f4"
SHA_CATALOGO_PIXELES = "cc5054c20c43b08d30d21035b89052c521bc74d204149f205658df1dbdf69410"

# Anexo C.
NOMBRES_RUTA_ETIQUETA = ("Tables", "parse_tables", "values", "source_checks", "numeric", "parse_report",
                         "VARIABLES", "RAW_COLUMNS", "LEAF_COLUMNS", "GROUP_COLUMNS", "TIMEZONE")
HUELLA_RUTA_ETIQUETA_ADMITIDA = "af1b0e1bfab1594381c097253f09eabbaa49c7914bacc3f6203b48ef2261fba9"
VERSIONES_ADMITIDAS_C0 = (
    "06e46f839f0c70ec98ffc5ea8fee8f519b6cea532fe64ba2ad6e175d6fe3bfe6",
    "38a50d54a4ac30fb800201468d98ae78f6c7d45d899384ad56ddc7097b717918",
    "bb5f3e9a31769e55344cbda30cf6941e3a3b7bf805a03851340bfaedd5ff1685",
    "ca49c75e388d51cd5384b33f952ca8897ec14a26768f81e8a4963bc66ecf899b",
    "c41831d2e6806d029200d2b9f747e1741011e5f1da7c02f8f5d38b7ead9de0dc",
    "578fa26eea5b4ac4733c56aaf08e9b7b8904595fb8447dd54feb838642612120",
)
VERSIONES_SIN_CODIGO_C0 = (
    "e61d95592bed0a995ba7da7066dd895a9676ede5cd8347e0ef813a1242a0abc7",
    "8de727f78724bc9f3bcadbc5bc0fa065446e7ee16ee06ecb02261583bb6a55af",
    "4c830d3dd306fff579cdaab557b512b2c7f49e227dc0e319dc71f2103b53a4dd",
    "fc1f1bb6c8d1adce4aeab1494595007776bf16a3e4f88faf4ebbdc63eebe3496",
    "975d9bf0b7b5045b575b922d8c32d7a23e4c319e608f96cd3ec7bc7a4a59b2b7",
)

MODULOS_PROHIBIDOS = ("_comun_modelo", "_common")

# Rutas del código fijado, relativas a AP.
RUTA_ADAPTADOR = "scripts_modelo_1km/v2/meteorologia_v2.py"
RUTA_DMC_FEATURES = "scripts_modelo_1km/v3/dmc_features.py"
RUTA_PREFLIGHT_V3 = "scripts_modelo_1km/v3/preflight_v3.py"
RUTA_COMUN_MODELO = "scripts_modelo_1km/_comun_modelo.py"
RUTA_RELOJ_SINCA = "scripts_modelo_1km/verificar_reloj_sinca.py"
RUTA_DESCARGADOR = "scripts_pipeline/descargar_meteo_chile_horaria.py"

# Nombres con que quedan en sys.modules. dmc_features y preflight_v3 llevan su nombre real, para que
# «from dmc_features import …» dentro de preflight_v3 use el módulo ya verificado.
MODULO_ADAPTADOR = "_reloj_dmc_adaptador_v2"
MODULO_DMC_FEATURES = "dmc_features"
MODULO_PREFLIGHT_V3 = "preflight_v3"

_SHA_HEX = re.compile(r"[0-9a-f]{64}")

# nombre_modulo → (ruta resuelta, sha256, módulo), sólo de lo cargado por cargar_por_ruta.
_CARGADOS: dict[str, tuple[Path, str, ModuleType]] = {}


# ---------------------------------------------------------------------------
# Carga por ruta y huella
# ---------------------------------------------------------------------------
def _exigir_sha(sha256: str) -> None:
    if not isinstance(sha256, str) or not _SHA_HEX.fullmatch(sha256):
        raise ValueError("Se exige un sha256 explícito de 64 hexadecimales en minúscula")


def _exigir_sin_prohibidos(momento: str) -> None:
    presentes = [m for m in MODULOS_PROHIBIDOS if m in sys.modules]
    if presentes:
        raise RuntimeError(f"{', '.join(presentes)} en sys.modules {momento} (§9: nunca se importan)")


def _leer_fijado(ruta: Path, sha256: str | None) -> bytes:
    """Bytes de un archivo fijado: archivo regular, no enlace y, si se da, con esa sha256."""
    ruta = Path(ruta)
    if ruta.is_symlink():
        raise ValueError(f"El archivo fijado es un enlace simbólico: {ruta.name}")
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo fijado: {ruta.name}")
    datos = ruta.read_bytes()
    if sha256 is not None and entorno.sha256_bytes(datos) != sha256:
        raise ValueError(f"La huella de {ruta.name} no coincide con la fijada ({sha256[:8]}…)")
    return datos


def cargar_por_ruta(ruta: Path, sha256: str, nombre_modulo: str, *,
                    rutas_import: Sequence[Path] = ()) -> ModuleType:
    """Importa un módulo desde su archivo tras verificar sha256 antes y después (sin enlaces).

    ``rutas_import`` se agregan a ``sys.path`` sólo durante la carga y se retiran después.
    Falla si al terminar aparece en ``sys.modules`` alguno de MODULOS_PROHIBIDOS.
    El módulo queda en ``sys.modules[nombre_modulo]``. Una segunda llamada con la misma ruta y huella
    devuelve el mismo módulo (tras volver a verificar el archivo); con otra ruta u otra huella, falla.
    """
    _exigir_sha(sha256)
    if not isinstance(nombre_modulo, str) or not nombre_modulo:
        raise ValueError("nombre_modulo vacío")
    if not sys.dont_write_bytecode:
        raise RuntimeError("sys.dont_write_bytecode debe ser True antes de cargar código fijado (§9)")
    _exigir_sin_prohibidos("antes de cargar")
    ruta = Path(ruta)
    if not ruta.is_absolute():
        raise ValueError("cargar_por_ruta exige una ruta absoluta")
    datos = _leer_fijado(ruta, sha256)
    resuelta = ruta.resolve()

    previo = _CARGADOS.get(nombre_modulo)
    if previo is not None:
        if previo[0] != resuelta or previo[1] != sha256 or sys.modules.get(nombre_modulo) is not previo[2]:
            raise RuntimeError(f"{nombre_modulo} ya se cargó con otra ruta u otra huella")
        return previo[2]
    if nombre_modulo in sys.modules:
        raise RuntimeError(f"{nombre_modulo} ya está en sys.modules y no lo cargó fijados")

    spec = importlib.util.spec_from_file_location(nombre_modulo, resuelta)
    if spec is None or spec.origin is None or Path(spec.origin).resolve() != resuelta:
        raise ValueError(f"Origen inesperado al cargar {ruta.name}")
    modulo = importlib.util.module_from_spec(spec)
    codigo = compile(datos, str(resuelta), "exec", dont_inherit=True)

    antes = list(sys.path)
    agregadas = [str(Path(r).resolve()) for r in rutas_import]
    for r in reversed(agregadas):
        sys.path.insert(0, r)
    sys.modules[nombre_modulo] = modulo
    try:
        exec(codigo, modulo.__dict__)
    except BaseException:
        sys.modules.pop(nombre_modulo, None)
        raise
    finally:
        sys.path[:] = [p for p in sys.path if p not in agregadas or p in antes]
    try:
        if Path(modulo.__file__).resolve() != resuelta:
            raise ValueError(f"El módulo {nombre_modulo} no quedó con su archivo de origen")
        if entorno.sha256_archivo(resuelta) != sha256:
            raise ValueError(f"{ruta.name} cambió mientras se cargaba")
        _exigir_sin_prohibidos(f"después de cargar {ruta.name}")
    except BaseException:
        sys.modules.pop(nombre_modulo, None)
        raise
    _CARGADOS[nombre_modulo] = (resuelta, sha256, modulo)
    return modulo


def _exigir_atributos(modulo: ModuleType, nombres: Sequence[str]) -> None:
    faltan = [n for n in nombres if not callable(getattr(modulo, n, None))]
    if faltan:
        raise RuntimeError(f"Al módulo fijado le faltan: {', '.join(faltan)}")


def cargar_adaptador(ap: Path, sha256: str = SHA_ADAPTADOR) -> ModuleType:
    """``AP/scripts_modelo_1km/v2/meteorologia_v2.py`` fijado."""
    modulo = cargar_por_ruta(Path(ap) / RUTA_ADAPTADOR, sha256, MODULO_ADAPTADOR)
    _exigir_atributos(modulo, ("leer_artefacto", "normalizar", "_utc", "_confirmado"))
    return modulo


def cargar_dmc_features(ap: Path, sha256: str = SHA_DMC_FEATURES) -> ModuleType:
    """``AP/scripts_modelo_1km/v3/dmc_features.py`` fijado (su ``_adapter`` vuelve a verificar el adaptador)."""
    ruta = Path(ap) / RUTA_DMC_FEATURES
    modulo = cargar_por_ruta(ruta, sha256, MODULO_DMC_FEATURES, rutas_import=(ruta.parent,))
    _exigir_atributos(modulo, ("cargar_dmc", "_adapter"))
    return modulo


def cargar_preflight(ap: Path, sha256: str = SHA_PREFLIGHT_V3) -> ModuleType:
    """``AP/scripts_modelo_1km/v3/preflight_v3.py`` fijado; arrastra runner_v3, preparar_base_v3, etc.

    Efecto conocido de la importación: runner_v3 fija OMP/OPENBLAS/MKL/… a 2 hilos y pyarrow a 2.
    Antes carga ``dmc_features`` fijado, para que ``preflight_v3`` lo reciba ya verificado, y al final
    comprueba que el ``dmc_features`` en uso sea ése.
    """
    dmc = cargar_dmc_features(ap)
    ruta = Path(ap) / RUTA_PREFLIGHT_V3
    modulo = cargar_por_ruta(ruta, sha256, MODULO_PREFLIGHT_V3, rutas_import=(ruta.parent,))
    if sys.modules.get(MODULO_DMC_FEATURES) is not dmc:
        raise RuntimeError("preflight_v3 quedó con un dmc_features distinto del fijado")
    _exigir_atributos(modulo, ("policy_check",))
    return modulo


def cargar_descargador(ap: Path, sha256: str) -> ModuleType:
    """El descargador vigente, sólo para fabricar datos sintéticos con el formato real (§8)."""
    _exigir_sha(sha256)
    modulo = cargar_por_ruta(Path(ap) / RUTA_DESCARGADOR, sha256, f"_reloj_dmc_descargador_{sha256[:8]}")
    _exigir_atributos(modulo, ("run_download", "parse_report"))
    return modulo


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------
def _ligados(nodo: ast.stmt) -> list[str]:
    """Nombres que un nodo de nivel superior liga en el módulo."""
    if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [nodo.name]
    if isinstance(nodo, ast.Assign):
        objetivos = nodo.targets
    elif isinstance(nodo, (ast.AnnAssign, ast.AugAssign)):
        objetivos = [nodo.target]
    elif isinstance(nodo, (ast.Import, ast.ImportFrom)):
        return [(a.asname or a.name).split(".")[0] for a in nodo.names if a.name != "*"]
    else:
        return []
    nombres: list[str] = []
    pendientes = list(objetivos)
    while pendientes:
        t = pendientes.pop(0)
        if isinstance(t, ast.Name):
            nombres.append(t.id)
        elif isinstance(t, (ast.Tuple, ast.List)):
            pendientes.extend(t.elts)
        elif isinstance(t, ast.Starred):
            pendientes.append(t.value)
    return nombres


def nodos_superiores(fuente: str) -> dict[str, list[ast.stmt]]:
    """Nombre → nodos de nivel superior que lo ligan, en orden del texto."""
    arbol = ast.parse(fuente)
    por_nombre: dict[str, list[ast.stmt]] = {}
    for nodo in arbol.body:
        for nombre in _ligados(nodo):
            por_nombre.setdefault(nombre, []).append(nodo)
    return por_nombre


def _nodo_unico(por_nombre: Mapping[str, list[ast.stmt]], nombre: str) -> ast.stmt:
    nodos = por_nombre.get(nombre, [])
    if len(nodos) != 1:
        motivo = "no está" if not nodos else f"se liga {len(nodos)} veces"
        raise ValueError(f"El nombre de nivel superior «{nombre}» {motivo}")
    return nodos[0]


def _banderas_futuro(arbol: ast.Module) -> int:
    """Banderas de compilación de los ``from __future__ import …`` del módulo."""
    banderas = 0
    for nodo in arbol.body:
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "__future__":
            for a in nodo.names:
                banderas |= getattr(_futuro, a.name).compiler_flag
    return banderas


def extraer_por_ast(ruta: Path, sha256: str | None, nombres: Sequence[str],
                    espacio: Mapping[str, Any]) -> dict[str, Any]:
    """Ejecuta sólo los nodos de nivel superior llamados ``nombres`` en un espacio aislado.

    Usa ``ast.get_source_segment``; ``espacio`` trae las dependencias explícitas (p. ej. datetime,
    timedelta, date, ZoneInfo para ``transiciones``). Nunca ejecuta el resto del módulo.
    Cada nombre debe ligarse una sola vez en el nivel superior; no se admiten nodos decorados (sin el
    decorador cambiaría su significado). Los ``from __future__`` del módulo se respetan y los números
    de línea son los del archivo. Con ``sha256`` se exige la huella de los bytes leídos.
    """
    if sha256 is not None:
        _exigir_sha(sha256)
    if not nombres:
        raise ValueError("No se pidió ningún nombre")
    choques = set(nombres) & set(espacio)
    if choques:
        raise ValueError(f"El espacio ya trae {sorted(choques)}")
    ruta = Path(ruta)
    fuente = _leer_fijado(ruta, sha256).decode("utf-8")
    arbol = ast.parse(fuente, filename=ruta.name)
    banderas = _banderas_futuro(arbol)
    por_nombre = nodos_superiores(fuente)
    elegidos: list[ast.stmt] = []
    for nombre in nombres:
        nodo = _nodo_unico(por_nombre, nombre)
        if getattr(nodo, "decorator_list", None):
            raise ValueError(f"«{nombre}» está decorado; no se extrae por AST")
        if nodo not in elegidos:
            elegidos.append(nodo)
    elegidos.sort(key=lambda n: n.lineno)

    aislado: dict[str, Any] = {"__builtins__": builtins, "__name__": f"_reloj_dmc_ast_{ruta.stem}"}
    aislado.update(espacio)
    for nodo in elegidos:
        segmento = ast.get_source_segment(fuente, nodo)
        if segmento is None:
            raise ValueError("No se pudo recuperar el segmento de un nodo")
        sub = ast.parse(segmento, filename=ruta.name)
        ast.increment_lineno(sub, nodo.lineno - 1)
        exec(compile(sub, str(ruta), "exec", flags=banderas, dont_inherit=True), aislado)
    faltan = [n for n in nombres if n not in aislado]
    if faltan:
        raise RuntimeError(f"La extracción no definió {faltan}")
    return {n: aislado[n] for n in nombres}


def macrozona_region(ap: Path) -> dict[int, str]:
    """Copia ``MACROZONA_REGION`` de ``_comun_modelo.py`` leyendo su fuente (huella a83c0384…)."""
    valor = extraer_por_ast(Path(ap) / RUTA_COMUN_MODELO, SHA_COMUN_MODELO, ("MACROZONA_REGION",), {})
    tabla = valor["MACROZONA_REGION"]
    if not isinstance(tabla, dict) or not tabla or not all(
            type(k) is int and isinstance(v, str) and v for k, v in tabla.items()):
        raise RuntimeError("MACROZONA_REGION no es un diccionario {región: macrozona}")
    return dict(tabla)


def transiciones_sinca(ap: Path):
    """``verificar_reloj_sinca.transiciones`` extraída por AST (sólo para la prueba 3).

    El protocolo no fija la huella de ``verificar_reloj_sinca.py`` (por eso ``sha256=None``); la prueba
    comprueba que la función sea la que cita §1.10 (líneas 47-73). Nada más del módulo se ejecuta.
    """
    ruta = Path(ap) / RUTA_RELOJ_SINCA
    espacio = {"date": date, "datetime": datetime, "timedelta": timedelta, "ZoneInfo": ZoneInfo}
    return extraer_por_ast(ruta, None, ("transiciones",), espacio)["transiciones"]


# ---------------------------------------------------------------------------
# Anexo C
# ---------------------------------------------------------------------------
def huella_ruta_etiqueta(fuente: str) -> str:
    """Anexo C: sha256 de ``json.dumps([seg(n) for n in NOMBRES_RUTA_ETIQUETA], ensure_ascii=False)``.

    seg(n) es ``ast.get_source_segment`` del nodo de nivel superior llamado n; el texto JSON (con los
    separadores por omisión) se codifica en UTF-8 (R-13). Lanza ValueError si algún nombre falta o se
    liga más de una vez.
    """
    por_nombre = nodos_superiores(fuente)
    segmentos = []
    for nombre in NOMBRES_RUTA_ETIQUETA:
        segmento = ast.get_source_segment(fuente, _nodo_unico(por_nombre, nombre))
        if segmento is None:
            raise ValueError(f"Sin segmento para «{nombre}»")
        segmentos.append(segmento)
    return entorno.sha256_bytes(json.dumps(segmentos, ensure_ascii=False).encode("utf-8"))


def versiones_admitidas(fuentes: Mapping[str, Path]) -> dict[str, dict]:
    """Para cada versión (sha256 del script) con fuente recuperada: su huella y si se admite.

    Es la comprobación mecánica del addendum de C1 (§3.1 «Versiones del descargador»). Una versión
    cuyo archivo no tiene ese sha256 o cuya huella no es af1b0e1b… no se admite.
    Cada entrada: ``sha256_archivo``, ``huella``, ``admitida``, ``motivo`` (None si se admite;
    «sin_codigo», «sha256_distinto», «huella_no_calculable» o «huella_distinta») y ``en_anexo_c``
    (si es una de las once del Anexo C; sólo informativo, no decide). No guarda rutas (privacidad).
    """
    conocidas = set(VERSIONES_ADMITIDAS_C0) | set(VERSIONES_SIN_CODIGO_C0)
    salida: dict[str, dict] = {}
    for version in sorted(fuentes):
        _exigir_sha(version)
        fila = {"sha256_archivo": None, "huella": None, "admitida": False, "motivo": None,
                "en_anexo_c": version in conocidas}
        ruta = Path(fuentes[version])
        try:
            datos = _leer_fijado(ruta, None)
        except (FileNotFoundError, ValueError):
            fila["motivo"] = "sin_codigo"
            salida[version] = fila
            continue
        fila["sha256_archivo"] = entorno.sha256_bytes(datos)
        if fila["sha256_archivo"] != version:
            fila["motivo"] = "sha256_distinto"
            salida[version] = fila
            continue
        try:
            fila["huella"] = huella_ruta_etiqueta(datos.decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            fila["motivo"] = "huella_no_calculable"
            salida[version] = fila
            continue
        fila["admitida"] = fila["huella"] == HUELLA_RUTA_ETIQUETA_ADMITIDA
        fila["motivo"] = None if fila["admitida"] else "huella_distinta"
        salida[version] = fila
    return salida
