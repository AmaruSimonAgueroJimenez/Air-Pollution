#!/usr/bin/env python3
"""descargar_sinca_meteorologia.py — Meteorología horaria SINCA (validación).

Descarga, de las estaciones de ``config/sinca/config_sinca_estaciones.json``,
las series horarias de temperatura (TEMP), humedad relativa (RHUM), rapidez
(WSPD) y dirección (WDIR) del viento desde el exportador SINCA
(``apub.tsindico2.cgi``). Es un insumo sólo descriptivo: valida el producto
meteorológico combinado en celdas y laderas, y no entra en ninguna regla.

Diferencias con ``descargar_sinca.py`` (contaminantes), que no se modifica:

* Las series meteorológicas viven bajo ``Met/`` y no bajo ``Cal/``. La macro
  exportable es ``./<REG>/<EST>/Met/<PARAM>//<macro>.ic``, con ``<macro>`` =
  ``horario_<NNN>`` tal como lo publica la ficha de la estación (NNN es la
  altura del sensor en metros; ``000`` = sin información).
* En WDIR la macro ``<macro>.ic`` entrega una rosa de vientos (porcentaje por
  sector de 15°), no una serie. La serie horaria es ``<macro>_spec.ic``
  («serie de tiempo» en el visor SINCA). En WSPD ambas son idénticas y se usa
  ``<macro>.ic``.
* La exportación trae una sola columna de valores, sin el desglose
  validado/preliminar/no validado de los contaminantes.

Inventario: las fichas oficiales ya cacheadas por
``actualizar_geometria_sinca.py`` en ``data/sinca/metadata/fichas_estaciones_
sinca/<estacion>.html.gz``. Se leen sin modificarlas; su SHA-256 queda en el
manifiesto. No se consulta ni se reescribe nada de la carpeta de contaminantes.

Salida (carpeta nueva y separada, por omisión ``data/sinca_meteorologia/``)::

    <PARAM>/<REG>_<EST>_<PARAM>_<macro>_<desde>_<hasta>.csv   respuesta cruda
    manifiesto_descarga.csv      una fila por serie publicada (SHA-256)
    no_disponibles.csv           series sin datos, macro inexistente o error
    SHA256SUMS.txt               huellas de todos los CSV publicados
    corridas/<marca_utc>/        parámetros, inventario de fichas y resumen

Reglas de seguridad: nunca sobrescribe ni borra un archivo publicado (la
publicación es un enlace duro que falla si el destino existe), conserva un
piso de espacio libre (``--piso-gb``, 1 GiB por omisión), un solo escritor
(bloqueo ``fcntl``), un solo proceso y peticiones secuenciales.

Reloj: hora civil local SINCA sin desfase, igual que los contaminantes
(``config/sinca/politica_temporal.json``). No se convierte a UTC aquí.

Uso:
  python descargar_sinca_meteorologia.py --dry-run --limite 2
  python descargar_sinca_meteorologia.py --desde 2000-01-01 --hasta 2026-10-24
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import gzip
import hashlib
import html
import io
import json
import math
import os
import re
import shutil
import signal
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA, REPO_ROOT, SINCA, ensure_dir, get_logger, retry  # noqa: E402

log = get_logger("sinca_meteorologia")

SCRIPT_VERSION = "1.0.0"
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
BASE = "https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi"
AIRVIRO_PATH = "/usr/airviro/data/CONAMA/"
DESTINO_POR_OMISION = DATA / "sinca_meteorologia"
FICHAS_POR_OMISION = SINCA / "metadata" / "fichas_estaciones_sinca"
CONFIG_POR_OMISION = REPO_ROOT / "config" / "sinca" / "config_sinca_estaciones.json"
POLITICA_TEMPORAL_RUTA = REPO_ROOT / "config" / "sinca" / "politica_temporal.json"

# Parámetro SINCA -> nombre canónico y unidad esperada (la ficha la confirma).
PARAMETROS = {
    "TEMP": ("temperatura", "°C"),
    "RHUM": ("humedad_relativa", "%"),
    "WSPD": ("rapidez_viento", "m/s"),
    "WDIR": ("direccion_viento", "°"),
}
# Sufijo de la macro que entrega la serie de tiempo (la .ic de WDIR es rosa).
SUFIJO_SERIE = {"WDIR": "_spec"}

CAMPOS_MANIFIESTO = [
    "region", "estacion", "nombre", "parametro", "variable", "macro_ficha",
    "macro_exportada", "altura_ficha", "unidad_ficha", "instrumento_ficha",
    "desde_ficha", "hasta_ficha", "desde", "hasta", "ruta_relativa", "bytes",
    "sha256", "filas", "filas_con_observacion", "filas_no_numericas",
    "primera_observacion", "ultima_observacion", "minimo", "maximo",
    "url_fuente", "accion", "ficha_sha256", "config_estaciones_sha256",
    "marca_temporal", "politica_temporal_sha256", "script_version",
    "script_sha256", "registrado_utc",
]
CAMPOS_FALTANTES = [
    "region", "estacion", "nombre", "parametro", "macro_ficha",
    "macro_exportada", "desde", "hasta", "motivo", "url_fuente", "registrado_utc",
]
CLAVE = ("region", "estacion", "parametro", "macro_ficha", "desde", "hasta")


class DetencionSegura(Exception):
    """Condición que obliga a detener la corrida completa (espacio, señal)."""


# --------------------------------------------------------------------------
# Inventario desde las fichas cacheadas
# --------------------------------------------------------------------------
_RE_FILA = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_RE_CELDA = re.compile(r"<t([dh])\b[^>]*>(.*?)</t\1>", re.S | re.I)
_RE_ENLACE = re.compile(
    r"macropath=\./([A-Za-z0-9]+)/([A-Za-z0-9]+)/Met/([A-Z0-9]+)"
    r"&(?:amp;)?macro=([A-Za-z0-9_]+)"
    r"(?:&(?:amp;)?from=(\d*))?(?:&(?:amp;)?to=(\d*))?"
)
_RE_UNIDAD = re.compile(r"\(([^()]*)\)\s*$")


def _texto_plano(fragmento: str) -> str:
    sin_etiquetas = re.sub(r"<br\s*/?>", " ", fragmento, flags=re.I)
    sin_etiquetas = re.sub(r"<[^>]+>", " ", sin_etiquetas)
    return re.sub(r"\s+", " ", html.unescape(sin_etiquetas)).strip()


def nombre_ficha(estacion: str) -> str:
    """Mismo saneamiento que ``actualizar_geometria_sinca.py``."""
    return f"{re.sub(r'[^A-Za-z0-9_.-]', '_', estacion)}.html.gz"


def parsear_ficha(texto: str, region: str, estacion: str,
                  parametros=tuple(PARAMETROS)) -> list[dict]:
    """Series meteorológicas que la ficha publica para la estación."""
    series = {}
    for fila in _RE_FILA.findall(texto):
        enlace = _RE_ENLACE.search(fila)
        if not enlace:
            continue
        reg, est, param, macro, desde, hasta = enlace.groups()
        if reg != region or est != estacion or param not in parametros:
            continue
        celdas = [_texto_plano(c[1]) for c in _RE_CELDA.findall(fila)]
        encabezado = celdas[0] if celdas else ""
        unidad = _RE_UNIDAD.search(encabezado)
        unidad_txt = unidad.group(1).split(" - ")[-1].strip() if unidad else ""
        resto = celdas[1:]
        clave = (param, macro)
        if clave in series:
            # Misma serie en dos filas (p. ej., cambio de instrumento): se pide
            # una sola vez; se conservan el rango más amplio y ambos sensores.
            previa = series[clave]
            fechas_desde = [x for x in (previa["desde_ficha"], desde or "") if x]
            fechas_hasta = [x for x in (previa["hasta_ficha"], hasta or "") if x]
            previa["desde_ficha"] = min(fechas_desde) if fechas_desde else ""
            previa["hasta_ficha"] = max(fechas_hasta) if fechas_hasta else ""
            instrumento = resto[4] if len(resto) > 4 else ""
            if instrumento and instrumento not in previa["instrumento_ficha"].split(" | "):
                previa["instrumento_ficha"] = " | ".join(
                    x for x in (previa["instrumento_ficha"], instrumento) if x)
            continue
        series[clave] = {
            "region": region,
            "estacion": estacion,
            "parametro": param,
            "macro_ficha": macro,
            "nombre_variable_ficha": _RE_UNIDAD.sub("", encabezado).strip(),
            "unidad_ficha": unidad_txt,
            "resolucion_ficha": resto[0] if len(resto) > 0 else "",
            "altura_ficha": resto[1] if len(resto) > 1 else "",
            "desde_ficha": desde or "",
            "hasta_ficha": hasta or "",
            "instrumento_ficha": resto[4] if len(resto) > 4 else "",
        }
    return [series[k] for k in sorted(series)]


def inventariar(estaciones: list[dict], dir_fichas: Path,
                parametros=tuple(PARAMETROS)) -> tuple[list[dict], list[dict]]:
    """Recorre las fichas cacheadas (sólo lectura)."""
    series, sin_ficha = [], []
    for est in estaciones:
        region, estacion = est["region"], str(est["estacion"])
        ruta = dir_fichas / nombre_ficha(estacion)
        if not ruta.is_file():
            sin_ficha.append({"region": region, "estacion": estacion,
                              "nombre": est.get("nombre", "")})
            continue
        crudo = ruta.read_bytes()
        texto = gzip.decompress(crudo).decode("utf-8", errors="replace")
        huella = hashlib.sha256(crudo).hexdigest()
        for serie in parsear_ficha(texto, region, estacion, parametros):
            serie["nombre"] = est.get("nombre", "")
            serie["ficha"] = ruta.name
            serie["ficha_sha256"] = huella
            series.append(serie)
    return series, sin_ficha


# --------------------------------------------------------------------------
# Pedido y validación de la respuesta
# --------------------------------------------------------------------------
def macro_exportacion(region: str, estacion: str, parametro: str, macro: str) -> str:
    sufijo = SUFIJO_SERIE.get(parametro, "")
    return f"./{region}/{estacion}/Met/{parametro}//{macro}{sufijo}.ic"


def _yymmdd(fecha_iso: str) -> str:
    return date.fromisoformat(fecha_iso).strftime("%y%m%d")


def parametros_pedido(macro_ic: str, desde: str, hasta: str) -> dict:
    return {
        "outtype": "xcl",
        "macro": macro_ic,
        "from": _yymmdd(desde),
        "to": _yymmdd(hasta),
        "path": AIRVIRO_PATH,
        "lang": "esp",
        "rsrc": "",
    }


def url_pedido(params: dict) -> str:
    return str(requests.Request("GET", BASE, params=params).prepare().url)


def _pedir_una_vez(params: dict) -> str:
    respuesta = requests.get(BASE, params=params, timeout=300)
    respuesta.raise_for_status()
    return respuesta.text


pedir = retry(n=4, base=5.0, exc=(requests.RequestException,))(_pedir_una_vez)

_RE_DATO = re.compile(r"^(\d{6});(\d{4});(.*)$")


def analizar_respuesta(texto: str, desde: str, hasta: str) -> dict:
    """Clasifica la respuesta y resume sus observaciones sin modificarla.

    Estados: ``serie`` (publicable), ``macro_inexistente``,
    ``formato_no_serie`` (p. ej., la rosa de vientos), ``incompleta`` (no cubre
    el rango con la grilla horaria del exportador) y ``sin_observaciones``.
    """
    resumen = {
        "estado": "", "motivo": "", "filas": 0, "filas_con_observacion": 0,
        "filas_no_numericas": 0, "primera_marca": "", "ultima_marca": "",
        "primera_observacion": "", "ultima_observacion": "",
        "minimo": "", "maximo": "",
    }
    if "could not load macro" in texto.lower():
        resumen.update(estado="macro_inexistente", motivo="la macro no existe en SINCA")
        return resumen
    lineas = [x for x in texto.splitlines() if x.strip()]
    if not lineas or not lineas[0].upper().startswith("FECHA"):
        resumen.update(estado="formato_no_serie", motivo="sin encabezado FECHA")
        return resumen
    minimo, maximo = math.inf, -math.inf
    for linea in lineas[1:]:
        m = _RE_DATO.match(linea.strip())
        if not m:
            resumen.update(estado="formato_no_serie",
                           motivo=f"fila no horaria: {linea.strip()[:40]!r}")
            return resumen
        fecha, hora, resto = m.groups()
        marca = f"{fecha} {hora}"
        resumen["filas"] += 1
        resumen["primera_marca"] = resumen["primera_marca"] or marca
        resumen["ultima_marca"] = marca
        campo = resto.split(";")[0].strip()
        if not campo:
            continue
        try:
            valor = float(campo.replace(",", "."))
        except ValueError:
            resumen["filas_no_numericas"] += 1
            continue
        if not math.isfinite(valor):
            resumen["filas_no_numericas"] += 1
            continue
        resumen["filas_con_observacion"] += 1
        resumen["primera_observacion"] = resumen["primera_observacion"] or marca
        resumen["ultima_observacion"] = marca
        minimo, maximo = min(minimo, valor), max(maximo, valor)
    # El exportador inicia a las 01:00 del primer día y termina a las 23:00
    # del último: horas civiles inclusivas menos una fila (como en contaminantes).
    dias = (date.fromisoformat(hasta) - date.fromisoformat(desde)).days + 1
    esperadas = dias * 24 - 1
    primera = f"{_yymmdd(desde)} 0100"
    ultima = f"{_yymmdd(hasta)} 2300"
    if (resumen["filas"] != esperadas or resumen["primera_marca"] != primera
            or resumen["ultima_marca"] != ultima):
        resumen.update(
            estado="incompleta",
            motivo=(f"{resumen['filas']} filas de {esperadas}; "
                    f"{resumen['primera_marca']}..{resumen['ultima_marca']}"),
        )
        return resumen
    if not resumen["filas_con_observacion"]:
        resumen.update(estado="sin_observaciones", motivo="plantilla sin mediciones")
        return resumen
    resumen.update(estado="serie", minimo=f"{minimo:g}", maximo=f"{maximo:g}")
    return resumen


# --------------------------------------------------------------------------
# Escritura segura
# --------------------------------------------------------------------------
def _fsync_directorio(carpeta: Path) -> None:
    fd = os.open(carpeta, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publicar_sin_sobrescribir(datos: bytes, destino: Path) -> None:
    """Escribe y publica con enlace duro: falla si ``destino`` ya existe."""
    ensure_dir(destino.parent)
    temporal = destino.with_name(f".{destino.name}.{os.getpid()}.part")
    try:
        with temporal.open("xb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        os.link(temporal, destino)  # FileExistsError si ya existe
    finally:
        temporal.unlink(missing_ok=True)
    _fsync_directorio(destino.parent)


def escribir_csv_atomico(ruta: Path, campos: list[str], filas: list[dict]) -> None:
    """Sólo para los registros propios de esta carpeta (manifiestos)."""
    ensure_dir(ruta.parent)
    temporal = ruta.with_name(f".{ruta.name}.{os.getpid()}.part")
    try:
        with temporal.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)
            f.flush()
            os.fsync(f.fileno())
        temporal.replace(ruta)
    finally:
        temporal.unlink(missing_ok=True)


def escribir_json_atomico(ruta: Path, contenido: dict) -> None:
    ensure_dir(ruta.parent)
    temporal = ruta.with_name(f".{ruta.name}.{os.getpid()}.part")
    try:
        temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        temporal.replace(ruta)
    finally:
        temporal.unlink(missing_ok=True)


def _leer_csv(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def comprobar_piso(carpeta: Path, piso_gb: float, bytes_nuevos: int = 0) -> int:
    libres = shutil.disk_usage(carpeta).free
    if libres - bytes_nuevos < piso_gb * 1024**3:
        raise DetencionSegura(
            f"piso de espacio: quedarían {(libres - bytes_nuevos) / 1024**3:.2f} GiB "
            f"y el mínimo es {piso_gb:g} GiB"
        )
    return libres


class BloqueoExclusivo:
    """Un solo escritor por carpeta de destino; se libera al cerrar."""

    def __init__(self, carpeta: Path):
        self.ruta = carpeta / ".descarga_sinca_meteorologia.lock"
        self.archivo = None

    def __enter__(self):
        ensure_dir(self.ruta.parent)
        self.archivo = self.ruta.open("a+")
        try:
            fcntl.flock(self.archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.archivo.close()
            raise SystemExit("Ya hay otra descarga meteorológica SINCA activa") from exc
        return self

    def __exit__(self, *_):
        fcntl.flock(self.archivo.fileno(), fcntl.LOCK_UN)
        self.archivo.close()
        return False


def _al_recibir_senal(signum, _frame):
    raise DetencionSegura(f"señal {signal.Signals(signum).name}")


# --------------------------------------------------------------------------
# Corrida
# --------------------------------------------------------------------------
def nombre_archivo(serie: dict, desde: str, hasta: str) -> str:
    return (f"{serie['region']}_{serie['estacion']}_{serie['parametro']}_"
            f"{serie['macro_ficha']}_{desde}_{hasta}.csv")


def _clave(fila: dict) -> tuple:
    return tuple(str(fila.get(c, "")) for c in CLAVE)


def procesar_serie(serie: dict, desde: str, hasta: str, destino: Path,
                   piso_gb: float, contexto: dict) -> tuple[str, dict]:
    """Devuelve (``manifiesto`` | ``faltante``, fila)."""
    macro_ic = macro_exportacion(serie["region"], serie["estacion"],
                                 serie["parametro"], serie["macro_ficha"])
    params = parametros_pedido(macro_ic, desde, hasta)
    url = url_pedido(params)
    ruta = destino / serie["parametro"] / nombre_archivo(serie, desde, hasta)
    ahora = datetime.now(UTC).isoformat()
    base = {
        "region": serie["region"], "estacion": serie["estacion"],
        "nombre": serie.get("nombre", ""), "parametro": serie["parametro"],
        "macro_ficha": serie["macro_ficha"], "macro_exportada": macro_ic,
        "desde": desde, "hasta": hasta, "url_fuente": url, "registrado_utc": ahora,
    }
    if ruta.exists():
        datos = ruta.read_bytes()
        resumen = analizar_respuesta(datos.decode("utf-8", errors="replace"), desde, hasta)
        if resumen["estado"] != "serie":
            return "faltante", {**base, "motivo": (
                f"archivo existente no válido ({resumen['estado']}); no se toca")}
        accion = "reutilizado_en_disco"
    else:
        comprobar_piso(destino, piso_gb, 8 * 1024**2)
        texto = pedir(params)
        resumen = analizar_respuesta(texto, desde, hasta)
        if resumen["estado"] != "serie":
            return "faltante", {**base, "motivo": f"{resumen['estado']}: {resumen['motivo']}"}
        datos = texto.encode("utf-8")
        comprobar_piso(destino, piso_gb, len(datos))
        publicar_sin_sobrescribir(datos, ruta)
        accion = "descargado"
        # Relectura: lo publicado debe ser idéntico a lo validado.
        if ruta.read_bytes() != datos:
            raise RuntimeError(f"la relectura de {ruta.name} no coincide")
    variable, unidad_esperada = PARAMETROS[serie["parametro"]]
    fila = {
        **base,
        "variable": variable,
        "altura_ficha": serie.get("altura_ficha", ""),
        "unidad_ficha": serie.get("unidad_ficha", "") or unidad_esperada,
        "instrumento_ficha": serie.get("instrumento_ficha", ""),
        "desde_ficha": serie.get("desde_ficha", ""),
        "hasta_ficha": serie.get("hasta_ficha", ""),
        "ruta_relativa": str(ruta.relative_to(destino)),
        "bytes": len(datos),
        "sha256": hashlib.sha256(datos).hexdigest(),
        "filas": resumen["filas"],
        "filas_con_observacion": resumen["filas_con_observacion"],
        "filas_no_numericas": resumen["filas_no_numericas"],
        "primera_observacion": resumen["primera_observacion"],
        "ultima_observacion": resumen["ultima_observacion"],
        "minimo": resumen["minimo"], "maximo": resumen["maximo"],
        "accion": accion,
        "ficha_sha256": serie.get("ficha_sha256", ""),
        **contexto,
    }
    return "manifiesto", fila


def guardar_registros(destino: Path, manifiesto: dict, faltantes: dict) -> None:
    escribir_csv_atomico(destino / "manifiesto_descarga.csv", CAMPOS_MANIFIESTO,
                         [manifiesto[k] for k in sorted(manifiesto)])
    escribir_csv_atomico(destino / "no_disponibles.csv", CAMPOS_FALTANTES,
                         [faltantes[k] for k in sorted(faltantes)])


def escribir_sha256sums(destino: Path, manifiesto: dict) -> None:
    lineas = sorted(f"{f['sha256']}  {f['ruta_relativa']}" for f in manifiesto.values())
    temporal = destino / f".SHA256SUMS.txt.{os.getpid()}.part"
    try:
        temporal.write_text("\n".join(lineas) + ("\n" if lineas else ""), encoding="utf-8")
        temporal.replace(destino / "SHA256SUMS.txt")
    finally:
        temporal.unlink(missing_ok=True)


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2000-01-01", help="YYYY-MM-DD")
    ap.add_argument("--hasta", default=date.today().isoformat(),
                    help="YYYY-MM-DD; por omisión, hoy")
    ap.add_argument("--parametros", default=",".join(PARAMETROS),
                    help="subconjunto de TEMP,RHUM,WSPD,WDIR")
    ap.add_argument("--config", default=str(CONFIG_POR_OMISION))
    ap.add_argument("--fichas", default=str(FICHAS_POR_OMISION),
                    help="carpeta de fichas .html.gz cacheadas (sólo lectura)")
    ap.add_argument("--destino", default=str(DESTINO_POR_OMISION))
    ap.add_argument("--piso-gb", type=float, default=1.0,
                    help="espacio libre mínimo que se conserva, en GiB")
    ap.add_argument("--pausa", type=float, default=1.0,
                    help="segundos entre peticiones (cortesía)")
    ap.add_argument("--limite", type=int, default=0,
                    help="sólo las primeras N series del inventario (prueba)")
    ap.add_argument("--dry-run", action="store_true",
                    help="inventaria y lista los pedidos, sin red ni escritura")
    args = ap.parse_args(argv)

    try:
        inicio, fin = date.fromisoformat(args.desde), date.fromisoformat(args.hasta)
    except ValueError:
        ap.error("--desde y --hasta deben ser YYYY-MM-DD")
    if inicio > fin or fin > date.today():
        ap.error("el rango debe estar ordenado y no incluir fechas futuras")
    for nombre in ("piso_gb", "pausa"):
        valor = getattr(args, nombre)
        if not math.isfinite(valor) or valor < 0:
            ap.error(f"--{nombre.replace('_', '-')} debe ser finito y no negativo")
    parametros = tuple(p.strip().upper() for p in args.parametros.split(",") if p.strip())
    desconocidos = [p for p in parametros if p not in PARAMETROS]
    if desconocidos:
        ap.error(f"parámetros desconocidos: {desconocidos}")

    destino = Path(args.destino).expanduser().resolve()
    sinca_contaminantes = SINCA.resolve()
    if destino == sinca_contaminantes or sinca_contaminantes in destino.parents:
        ap.error("el destino no puede estar dentro de la carpeta SINCA de contaminantes")

    config_bytes = Path(args.config).read_bytes()
    estaciones = json.loads(config_bytes)
    series, sin_ficha = inventariar(estaciones, Path(args.fichas), parametros)
    if args.limite:
        series = series[: args.limite]
    log.info("%d estaciones, %d sin ficha; %d series %s; %s..%s",
             len(estaciones), len(sin_ficha), len(series), parametros,
             args.desde, args.hasta)
    if args.dry_run:
        for s in series:
            macro = macro_exportacion(s["region"], s["estacion"], s["parametro"],
                                      s["macro_ficha"])
            log.info("  [dry-run] %s", url_pedido(parametros_pedido(macro, args.desde,
                                                                   args.hasta)))
        return 0

    politica_bytes = POLITICA_TEMPORAL_RUTA.read_bytes()
    contexto = {
        "config_estaciones_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "marca_temporal": json.loads(politica_bytes)["sinca"]["reloj_fuente"],
        "politica_temporal_sha256": hashlib.sha256(politica_bytes).hexdigest(),
        "script_version": SCRIPT_VERSION,
        "script_sha256": SCRIPT_SHA256,
    }
    ensure_dir(destino)
    comprobar_piso(destino, args.piso_gb)
    # Sólo SIGTERM: SIGHUP queda como lo deje nohup (ignorado).
    signal.signal(signal.SIGTERM, _al_recibir_senal)

    marca = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    carpeta_corrida = destino / "corridas" / marca
    corrida = {
        "inicio_utc": datetime.now(UTC).isoformat(), "fin_utc": None,
        "estado": "en_curso", "argumentos": vars(args) | {"destino": "<destino>",
                                                          "config": Path(args.config).name,
                                                          "fichas": Path(args.fichas).name},
        "pid": os.getpid(), **contexto,
        "series_inventariadas": len(series), "estaciones": len(estaciones),
        "estaciones_sin_ficha": sin_ficha,
    }
    with BloqueoExclusivo(destino):
        escribir_csv_atomico(
            carpeta_corrida / "inventario_fichas.csv",
            ["region", "estacion", "nombre", "parametro", "macro_ficha",
             "nombre_variable_ficha", "unidad_ficha", "resolucion_ficha",
             "altura_ficha", "desde_ficha", "hasta_ficha", "instrumento_ficha",
             "ficha", "ficha_sha256"],
            series,
        )
        escribir_json_atomico(carpeta_corrida / "corrida.json", corrida)
        manifiesto = {_clave(f): f for f in _leer_csv(destino / "manifiesto_descarga.csv")}
        faltantes = {_clave(f): f for f in _leer_csv(destino / "no_disponibles.csv")}
        conteo = {"descargado": 0, "reutilizado_en_disco": 0, "faltante": 0, "error": 0}
        codigo = 0
        try:
            for i, serie in enumerate(series, 1):
                clave = (serie["region"], serie["estacion"], serie["parametro"],
                         serie["macro_ficha"], args.desde, args.hasta)
                try:
                    tipo, fila = procesar_serie(serie, args.desde, args.hasta, destino,
                                                args.piso_gb, contexto)
                except (DetencionSegura, KeyboardInterrupt):
                    raise
                except Exception as exc:  # noqa: BLE001
                    tipo, fila = "error", {
                        "region": serie["region"], "estacion": serie["estacion"],
                        "nombre": serie.get("nombre", ""), "parametro": serie["parametro"],
                        "macro_ficha": serie["macro_ficha"], "macro_exportada": "",
                        "desde": args.desde, "hasta": args.hasta,
                        "motivo": f"error: {type(exc).__name__}: {exc}"[:300],
                        "url_fuente": "", "registrado_utc": datetime.now(UTC).isoformat(),
                    }
                if tipo == "manifiesto":
                    manifiesto[clave] = fila
                    faltantes.pop(clave, None)
                    conteo[fila["accion"]] += 1
                    log.info("  ok %s %s %s/%s %d KB (%s; %s obs.)", serie["region"],
                             serie["estacion"], serie["parametro"], serie["macro_ficha"],
                             int(fila["bytes"]) // 1024, fila["accion"],
                             fila["filas_con_observacion"])
                else:
                    faltantes[clave] = fila
                    conteo["error" if tipo == "error" else "faltante"] += 1
                    log.info("  -- %s %s %s/%s: %s", serie["region"], serie["estacion"],
                             serie["parametro"], serie["macro_ficha"], fila["motivo"])
                guardar_registros(destino, manifiesto, faltantes)
                if i % 25 == 0:
                    log.info("… %d/%d series", i, len(series))
                if fila.get("accion") != "reutilizado_en_disco":
                    time.sleep(args.pausa)
            corrida["estado"] = "terminada"
            codigo = 1 if conteo["error"] else 0
        except (DetencionSegura, KeyboardInterrupt) as exc:
            corrida["estado"] = f"detenida: {exc or type(exc).__name__}"
            log.error("Corrida detenida: %s", corrida["estado"])
            codigo = 2
        finally:
            guardar_registros(destino, manifiesto, faltantes)
            escribir_sha256sums(destino, manifiesto)
            corrida.update(fin_utc=datetime.now(UTC).isoformat(), conteo=conteo,
                           series_en_manifiesto=len(manifiesto),
                           series_no_disponibles=len(faltantes),
                           bytes_en_manifiesto=sum(int(f["bytes"]) for f in manifiesto.values()))
            escribir_json_atomico(carpeta_corrida / "corrida.json", corrida)
    log.info("Listo (%s): %s; %d series en el manifiesto", corrida["estado"], conteo,
             len(manifiesto))
    return codigo


def main(argv=None) -> int:
    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
