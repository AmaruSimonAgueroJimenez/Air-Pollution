#!/usr/bin/env python3
"""descargar_sinca.py — Verdad-terreno SINCA para los 6 contaminantes.

Descarga las series por estación desde el exportador de SINCA
(``apub.tsindico2.cgi``) para PM2.5, PM10, NO2, O3, SO2 y CO, en resolución
horaria y/o diaria, y las guarda en ``data/sinca/<pol>/<res>/``.

Estaciones: ``config/sinca/config_sinca_estaciones.json`` (region, estacion, ...).
El exportador SINCA se llama así (ejemplo real de una estación de la RM):

  https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi
     ?outtype=xcl
     &macro=./RM/D15/Cal/PM25//PM25.horario.horario.ic
     &from=040101&to=241231
     &path=/usr/airviro/data/CONAMA/&lang=esp

donde el CÓDIGO del contaminante (ver ``PARAM_CODES``) aparece dos veces en
``macro``: como carpeta y como prefijo del archivo ``.ic``. Las estaciones que
no miden un contaminante devuelven vacío y se registran en
``no_disponibles.csv``.

Uso:
  python descargar_sinca.py \
      --resolucion horario --contaminantes pm25,pm10,no2,o3,so2,co
  python descargar_sinca.py --limite 3 --dry-run     # prueba rápida
"""
from __future__ import annotations

import argparse
import fcntl
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import time
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REPO_ROOT, SINCA, ensure_dir, get_logger, retry  # noqa: E402
from actualizar_geometria_sinca import main as actualizar_geometria  # noqa: E402

log = get_logger("sinca")

SCRIPT_VERSION = "1.2.0"
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
BASE = "https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi"
AIRVIRO_PATH = "/usr/airviro/data/CONAMA/"
POLITICA_TEMPORAL_RUTA = (
    REPO_ROOT / "config" / "sinca" / "politica_temporal.json"
)
_POLITICA_TEMPORAL_BYTES = POLITICA_TEMPORAL_RUTA.read_bytes()
POLITICA_TEMPORAL = json.loads(_POLITICA_TEMPORAL_BYTES)
POLITICA_TEMPORAL_SHA256 = hashlib.sha256(_POLITICA_TEMPORAL_BYTES).hexdigest()
MARCA_TEMPORAL_SINCA = str(POLITICA_TEMPORAL["sinca"]["reloj_fuente"])
POLITICA_UTC = (
    f"config/sinca/politica_temporal.json#sha256="
    f"{POLITICA_TEMPORAL_SHA256}"
)

# Códigos de parámetro SINCA/Airviro. PM25/PM10 son nominales; los gases usan
# códigos numéricos. 0001=SO2 y 0003=NO2 están confirmados por URLs reales de
# estaciones; O3/CO son los códigos estándar de Airviro — si algún gas no baja
# en una estación, verifica el código en su ficha SINCA (pestaña "Registros").
PARAM_CODES = {
    "pm25": "PM25",
    "pm10": "PM10",
    "so2": "0001",
    "no2": "0003",
    "o3": "0008",
    "co": "0004",
}

# Resolución -> sufijo del parámetro `macro`.
RES_SUFIJO = {"horario": "horario", "diario": "diario"}
# Mismos rangos de plausibilidad que afg_lib.RANGO_VALIDO. No filtran la
# descarga: sólo impiden destruir una copia útil por una revisión fuera de rango.
RANGO_VALIDO = {
    "pm25": (0, 1500), "pm10": (0, 3000), "no2": (0, 1000),
    "o3": (0, 500), "so2": (0, 3000), "co": (0, 60),
}


def resumir_respuesta_sinca(texto: str) -> dict:
    """Resume una exportación SINCA y detecta mediciones numéricas reales.

    El exportador puede devolver una tabla completa de fechas cuyo contenido
    de medición está totalmente vacío. Esas plantillas no son una descarga
    útil, aunque su respuesta pese cerca de 800 KB.
    """
    filas = 0
    primera = ""
    ultima = ""
    primera_observacion = ""
    ultima_observacion = ""
    filas_con_observacion = 0
    tiene_observaciones = False
    lector = csv.reader(io.StringIO(texto), delimiter=";")
    next(lector, None)  # encabezado
    for fila in lector:
        if len(fila) < 2:
            continue
        filas += 1
        marca = f"{fila[0].strip()} {fila[1].strip()}".strip()
        primera = primera or marca
        ultima = marca
        observada = False
        for valor in fila[2:5]:
            valor = valor.strip().replace(",", ".")
            if not valor:
                continue
            try:
                es_observacion = math.isfinite(float(valor))
            except ValueError:
                continue
            if es_observacion:
                tiene_observaciones = True
                observada = True
                break
        if observada:
            filas_con_observacion += 1
            primera_observacion = primera_observacion or marca
            ultima_observacion = marca
    return {
        "filas": filas,
        "primera_marca": primera,
        "ultima_marca": ultima,
        "tiene_observaciones": tiene_observaciones,
        "filas_con_observacion": filas_con_observacion,
        "primera_observacion": primera_observacion,
        "ultima_observacion": ultima_observacion,
    }


def auditar_descargas_locales() -> list[dict]:
    """Registra CSV existentes que solo contienen una plantilla sin datos."""
    hallazgos = []
    for ruta in sorted(SINCA.glob("*/*/*.csv")):
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        resumen = resumir_respuesta_sinca(texto)
        if resumen["filas"] and not resumen["tiene_observaciones"]:
            hallazgos.append({
                "relative_path": str(ruta.relative_to(SINCA)),
                "size_bytes": ruta.stat().st_size,
                "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(),
                "data_rows": resumen["filas"],
                "first_timestamp_raw": resumen["primera_marca"],
                "last_timestamp_raw": resumen["ultima_marca"],
                "reason": "all_measurement_fields_empty",
                "action": "removed_from_active_data",
            })

    metadata = ensure_dir(SINCA / "metadata")
    destino = metadata / "series_sin_observaciones.csv"
    campos = [
        "relative_path", "size_bytes", "sha256", "data_rows",
        "first_timestamp_raw", "last_timestamp_raw", "reason", "action",
    ]
    # El manifiesto es histórico: una auditoría posterior a la limpieza no
    # debe borrar el registro de las series ya retiradas.
    historial = []
    if destino.exists():
        with destino.open(encoding="utf-8", newline="") as f:
            historial = list(csv.DictReader(f))
    por_ruta = {r["relative_path"]: r for r in historial}
    por_ruta.update({r["relative_path"]: r for r in hallazgos})
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(por_ruta[k] for k in sorted(por_ruta))
    return hallazgos


def reconciliar_manifiestos(hallazgos: list[dict]) -> tuple[int, int]:
    """Mueve hallazgos del manifiesto de éxitos al de no disponibles."""
    ruta_exitos = SINCA / "manifiesto_descarga.csv"
    ruta_faltantes = SINCA / "no_disponibles.csv"
    if not ruta_exitos.exists() or not ruta_faltantes.exists():
        raise SystemExit("Faltan manifiesto_descarga.csv o no_disponibles.csv")

    claves_vacias = {r["relative_path"] for r in hallazgos}
    with ruta_exitos.open(encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        campos_exitos = lector.fieldnames
        exitos = list(lector)

    conservar, reclasificar = [], []
    for fila in exitos:
        clave = f"{fila['contaminante']}/{fila['resolucion']}/{Path(fila['ruta']).name}"
        (reclasificar if clave in claves_vacias else conservar).append(fila)

    with ruta_faltantes.open(encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        campos_faltantes = lector.fieldnames
        faltantes = list(lector)
    claves_faltantes = {
        (r["region"], r["estacion"], r["contaminante"], r["resolucion"])
        for r in faltantes
    }
    for fila in reclasificar:
        clave = (fila["region"], fila["estacion"], fila["contaminante"],
                 fila["resolucion"])
        if clave not in claves_faltantes:
            faltantes.append({
                "region": fila["region"],
                "estacion": fila["estacion"],
                "nombre": fila["nombre"],
                "contaminante": fila["contaminante"],
                "resolucion": fila["resolucion"],
                "motivo": "sin observaciones (plantilla vacía)",
            })
            claves_faltantes.add(clave)

    with ruta_exitos.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos_exitos)
        w.writeheader()
        w.writerows(conservar)
    with ruta_faltantes.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos_faltantes)
        w.writeheader()
        w.writerows(faltantes)
    return len(reclasificar), len(faltantes)


def yymmdd(fecha_iso: str) -> str:
    return datetime.strptime(fecha_iso, "%Y-%m-%d").strftime("%y%m%d")


@retry(n=4, base=3.0, exc=(requests.RequestException,))
def _get(params: dict) -> requests.Response:
    r = requests.get(BASE, params=params, timeout=120)
    r.raise_for_status()
    return r


def _parametros_serie(region, estacion, code, res, desde, hasta) -> dict:
    return {
        "outtype": "xcl",
        "macro": f"./{region}/{estacion}/Cal/{code}//{code}.{res}.{res}.ic",
        "from": yymmdd(desde),
        "to": yymmdd(hasta),
        "path": AIRVIRO_PATH,
        "lang": "esp",
        "rsrc": "",
    }


def _url_preparada(params: dict) -> str:
    return str(requests.Request("GET", BASE, params=params).prepare().url)


def _escribir_csv_atomico(ruta: Path, campos: list[str], filas: list[dict]) -> None:
    ensure_dir(ruta.parent)
    temporal = ruta.with_name(f".{ruta.name}.{os.getpid()}.part")
    try:
        with temporal.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)
            f.flush()
            os.fsync(f.fileno())
        temporal.replace(ruta)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


def _fusionar_por_clave(
    ruta: Path, nuevas: list[dict], campos: list[str], claves: list[str]
) -> list[dict]:
    anteriores = []
    if ruta.exists():
        with ruta.open(encoding="utf-8", newline="") as f:
            anteriores = list(csv.DictReader(f))
    # Migración idempotente del manifiesto histórico (que no tenía columnas
    # desde/hasta): el rango ya está codificado en el nombre del CSV.
    for fila in anteriores:
        if "script_version" in campos and not fila.get("script_version"):
            fila["script_version"] = "legacy_sin_version"
        if "marca_temporal" in campos and not fila.get("marca_temporal"):
            fila["marca_temporal"] = MARCA_TEMPORAL_SINCA
        if "politica_utc" in campos and not fila.get("politica_utc"):
            fila["politica_utc"] = POLITICA_UTC
        if "politica_temporal_sha256" in campos \
                and not fila.get("politica_temporal_sha256"):
            fila["politica_temporal_sha256"] = POLITICA_TEMPORAL_SHA256
        if fila.get("desde") and fila.get("hasta") or not fila.get("ruta"):
            continue
        rango = re.search(
            r"_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$",
            Path(fila["ruta"]).name,
        )
        if rango:
            fila["desde"], fila["hasta"] = rango.groups()
    # Retira referencias activas a archivos que ya fueron reemplazados por una
    # descarga más amplia y validada; el manifiesto de la nueva serie conserva
    # checksum, fuente y rango.
    anteriores = [
        f for f in anteriores
        if not f.get("ruta") or Path(f["ruta"]).exists()
    ]
    unidos = {tuple(f.get(c, "") for c in claves): f for f in anteriores}
    unidos.update({tuple(f.get(c, "") for c in claves): f for f in nuevas})
    return [
        {campo: fila.get(campo, "") for campo in campos}
        for _, fila in sorted(unidos.items())
    ]


def _fecha_de_marca(marca: str) -> date | None:
    try:
        return datetime.strptime(marca.split()[0], "%y%m%d").date()
    except (ValueError, IndexError):
        return None


def _cubre_rango(resumen: dict, desde: str, hasta: str, res: str) -> bool:
    primera = _fecha_de_marca(str(resumen.get("primera_marca", "")))
    ultima = _fecha_de_marca(str(resumen.get("ultima_marca", "")))
    cobertura_fechas = bool(
        primera and ultima
        and primera <= date.fromisoformat(desde)
        and ultima >= date.fromisoformat(hasta)
    )
    if not cobertura_fechas:
        return False
    if res == "horario":
        dias = (date.fromisoformat(hasta) - date.fromisoformat(desde)).days + 1
        # El exportador inicia a 01:00 del primer día y termina a 23:00 del
        # último; por eso son horas civiles inclusivas menos una fila.
        return int(resumen.get("filas", 0)) == dias * 24 - 1
    return True


def _calidades_observadas(texto: str, rango=None) -> dict[str, int]:
    """Mejor calidad numérica finita por marca original; no modifica el reloj."""
    calidades: dict[str, int] = {}
    lector = csv.reader(io.StringIO(texto), delimiter=";")
    next(lector, None)
    for fila in lector:
        if len(fila) < 2:
            continue
        for calidad, valor in zip((3, 2, 1), fila[2:5]):
            try:
                numero = float(valor.strip().replace(",", "."))
            except ValueError:
                continue
            if math.isfinite(numero):
                marca = f"{fila[0].strip()} {fila[1].strip()}"
                if rango is not None and not rango[0] <= numero <= rango[1]:
                    calidad = 0
                calidades[marca] = max(calidad, calidades.get(marca, 0))
                break
    return calidades


def _marcas_observadas(texto: str) -> set[str]:
    return set(_calidades_observadas(texto))


def _validar_preservacion(texto_anterior: str, texto_nuevo: str, rango=None) -> None:
    """Rechaza reemplazos que pierden horas observadas o degradan su calidad."""
    anteriores = _calidades_observadas(texto_anterior, rango)
    nuevas = _calidades_observadas(texto_nuevo, rango)
    perdidas = sum(marca not in nuevas for marca in anteriores)
    degradadas = sum(
        marca in nuevas and nuevas[marca] < calidad
        for marca, calidad in anteriores.items()
    )
    if perdidas or degradadas:
        raise ValueError(
            f"actualización insegura: {perdidas} horas perdidas y "
            f"{degradadas} de menor calidad/plausibilidad; se conserva la serie anterior"
        )


def _registrar_reemplazo(anterior: Path, nueva: Path, motivo: str) -> None:
    """Deja evidencia durable de los hashes antes de retirar una copia."""
    evento = {
        "registrado_utc": datetime.now(UTC).isoformat(), "motivo": motivo,
        "ruta_anterior": str(anterior), "ruta_nueva": str(nueva),
        "sha256_anterior": hashlib.sha256(anterior.read_bytes()).hexdigest(),
        "sha256_nueva": hashlib.sha256(nueva.read_bytes()).hexdigest(),
        "script_version": SCRIPT_VERSION, "script_sha256": SCRIPT_SHA256,
    }
    with (anterior.parent / "reemplazos_sinca.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _comprobar_espacio(dest: Path, reserva_gb: float, bytes_nuevos: int = 0) -> None:
    ensure_dir(dest)  # También comprueba que el volumen siga montado.
    libres = shutil.disk_usage(dest).free
    if libres - bytes_nuevos < reserva_gb * 1024**3:
        raise OSError(f"SINCA detenido: se debe conservar la reserva de {reserva_gb:g} GiB")


def _retirar_series_suplantadas(
    dest: Path,
    region: str,
    estacion: str,
    res: str,
    desde: str,
    hasta: str,
    nueva: Path,
    texto_nuevo: str,
) -> int:
    """Elimina rangos redundantes sólo si sus observaciones están cubiertas."""
    patron = re.compile(
        rf"^{re.escape(region)}_{re.escape(estacion)}_{re.escape(res)}_"
        r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$"
    )
    inicio_nuevo, fin_nuevo = date.fromisoformat(desde), date.fromisoformat(hasta)
    # Reabrir el archivo final impide retirar una copia por una respuesta
    # en memoria que no coincida con lo efectivamente guardado.
    if nueva.read_text(encoding="utf-8", errors="replace") != texto_nuevo:
        raise ValueError("la serie final no coincide con la respuesta validada")
    retirados = 0
    for anterior in dest.glob(f"{region}_{estacion}_{res}_*.csv"):
        if anterior == nueva:
            continue
        m = patron.match(anterior.name)
        if not m:
            continue
        inicio, fin = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        if inicio < inicio_nuevo or fin > fin_nuevo:
            continue
        texto_anterior = anterior.read_text(encoding="utf-8", errors="replace")
        resumen_anterior = resumir_respuesta_sinca(texto_anterior)
        if not resumen_anterior["tiene_observaciones"]:
            continue
        try:
            _validar_preservacion(texto_anterior, texto_nuevo, RANGO_VALIDO.get(dest.parent.name))
        except ValueError:
            continue
        _registrar_reemplazo(anterior, nueva, "rango_cubierto_sin_perdida_de_calidad")
        anterior.unlink()
        retirados += 1
    return retirados


def descargar_serie(region, estacion, code, res, desde, hasta, dest: Path,
                    dry_run=False, reserva_gb=100.0):
    """Descarga atomica y reanudable de una serie SINCA."""
    params = _parametros_serie(region, estacion, code, res, desde, hasta)
    pedido = _url_preparada(params)
    if dry_run:
        log.info("  [dry-run] %s", pedido)
        return None, 0, {}, pedido, "dry_run"

    _comprobar_espacio(dest, reserva_gb)
    fn = dest / f"{region}_{estacion}_{res}_{desde}_{hasta}.csv"
    pol = next((p for p, c in PARAM_CODES.items() if c == code), None)
    rango = RANGO_VALIDO.get(pol)
    texto_existente = ""
    if fn.exists():
        texto_existente = fn.read_text(encoding="utf-8", errors="replace")
        resumen_existente = resumir_respuesta_sinca(texto_existente)
        # Una serie que termina hoy se vuelve a consultar: SINCA agrega horas
        # y validaciones durante el día. Las series históricas sí son cacheables.
        historica = date.fromisoformat(hasta) < date.today()
        if historica and resumen_existente["tiene_observaciones"] \
                and _cubre_rango(resumen_existente, desde, hasta, res):
            n_retiradas = _retirar_series_suplantadas(
                dest, region, estacion, res, desde, hasta, fn, texto_existente,
            )
            return (
                fn, fn.stat().st_size, resumen_existente, pedido,
                f"reutilizado_validado;suplantados={n_retiradas}",
            )

    resp = _get(params)
    texto = resp.text
    # Una plantilla larga pero sin ninguna medición también significa "sin datos".
    resumen = resumir_respuesta_sinca(texto)
    util = len(texto) > 400 and ("Sin datos" not in texto) and \
        ("no existe" not in texto.lower()) and resumen["tiene_observaciones"]
    if texto_existente:
        _validar_preservacion(texto_existente, texto, rango)
    if not util:
        return None, 0, resumen, pedido, "sin_datos"

    datos = texto.encode("utf-8", errors="replace")
    _comprobar_espacio(dest, reserva_gb, len(datos))
    temporal = dest / f".{fn.name}.{os.getpid()}.part"
    try:
        with temporal.open("wb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        comprobacion = resumir_respuesta_sinca(
            temporal.read_text(encoding="utf-8", errors="replace")
        )
        if not comprobacion["filas"] or not comprobacion["tiene_observaciones"]:
            raise ValueError("la validacion posterior a descarga no encontro mediciones")
        if not _cubre_rango(comprobacion, desde, hasta, res):
            raise ValueError(
                "la respuesta SINCA no cubre íntegramente el rango solicitado"
            )
        if fn.exists():
            # La evidencia se registra antes del reemplazo atómico.
            _validar_preservacion(fn.read_text(encoding="utf-8"), texto, rango)
            _registrar_reemplazo(fn, temporal, "refresco_sin_perdida_de_calidad")
        temporal.replace(fn)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise
    n_retiradas = _retirar_series_suplantadas(
        dest, region, estacion, res, desde, hasta, fn, texto,
    )
    return (
        fn, len(datos), comprobacion, pedido,
        f"descargado;suplantados={n_retiradas}",
    )


@contextmanager
def _bloqueo_descarga():
    """Un solo escritor SINCA; el bloqueo se libera incluso al apagar el Mac."""
    ensure_dir(SINCA)
    with (SINCA / ".descarga_sinca.lock").open("a+") as archivo:
        try:
            fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Ya hay otra descarga SINCA activa; no se inicia una segunda") from exc
        try:
            yield
        finally:
            fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)


def _guardar_manifiestos(manifiesto: list[dict], faltantes: list[dict]) -> None:
    campos_m = [
        "region", "estacion", "nombre", "contaminante", "resolucion",
        "desde", "hasta", "ruta", "bytes", "sha256", "filas",
        "filas_con_observacion", "primera_marca", "ultima_marca",
        "primera_observacion", "ultima_observacion", "url_fuente",
        "accion", "script_version", "script_sha256", "config_estaciones_sha256",
        "marca_temporal", "politica_utc", "politica_temporal_sha256", "registrado_utc",
    ]
    campos_f = [
        "region", "estacion", "nombre", "contaminante", "resolucion",
        "desde", "hasta", "motivo",
    ]
    claves = ["region", "estacion", "contaminante", "resolucion", "desde", "hasta"]
    ruta_m = SINCA / "manifiesto_descarga.csv"
    ruta_f = SINCA / "no_disponibles.csv"
    _escribir_csv_atomico(
        ruta_m, campos_m, _fusionar_por_clave(ruta_m, manifiesto, campos_m, claves)
    )
    exitos_nuevos = {tuple(f.get(c, "") for c in claves) for f in manifiesto}
    pendientes = _fusionar_por_clave(ruta_f, faltantes, campos_f, claves)
    pendientes = [f for f in pendientes if tuple(f.get(c, "") for c in claves) not in exitos_nuevos]
    _escribir_csv_atomico(ruta_f, campos_f, pendientes)


def _main(argv, recursos):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desde", default="2000-01-01", help="YYYY-MM-DD")
    ap.add_argument("--hasta", default=datetime.now().strftime("%Y-%m-%d"),
                    help="YYYY-MM-DD; por defecto, hoy")
    ap.add_argument("--resolucion", default="horario",
                    choices=["horario", "diario", "ambas"])
    ap.add_argument("--contaminantes", default=",".join(PARAM_CODES),
                    help="lista separada por comas (pm25,pm10,no2,o3,so2,co)")
    ap.add_argument(
        "--config",
        default=str(REPO_ROOT / "config" / "sinca" / "config_sinca_estaciones.json"),
    )
    ap.add_argument("--limite", type=int, default=0,
                    help="procesa solo las primeras N estaciones (para probar)")
    ap.add_argument("--pausa", type=float, default=0.5,
                    help="segundos entre peticiones (cortesía)")
    ap.add_argument("--reserva-gb", type=float, default=100.0,
                    help="reserva mínima de espacio libre en GiB (por defecto 100)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validar-local", action="store_true",
                    help="audita CSV locales y registra plantillas sin observaciones")
    ap.add_argument("--reconciliar-manifiestos", action="store_true",
                    help="con --validar-local, reclasifica plantillas como no disponibles")
    ap.add_argument("--refrescar-geometria", action="store_true",
                    help="vuelve a consultar las fichas de estaciones SINCA")
    args = ap.parse_args(argv)

    try:
        inicio, fin = date.fromisoformat(args.desde), date.fromisoformat(args.hasta)
    except ValueError:
        ap.error("--desde y --hasta deben ser fechas YYYY-MM-DD")
    if inicio > fin or fin > date.today():
        ap.error("el rango debe estar ordenado y no incluir fechas futuras")
    if args.reserva_gb < 0 or not math.isfinite(args.reserva_gb) \
            or args.pausa < 0 or not math.isfinite(args.pausa):
        ap.error("reserva y pausa deben ser valores finitos no negativos")
    if not args.dry_run:
        _comprobar_espacio(SINCA, args.reserva_gb)
        recursos.enter_context(_bloqueo_descarga())

    if args.reconciliar_manifiestos and not args.validar_local:
        ap.error("--reconciliar-manifiestos requiere --validar-local")
    if args.validar_local:
        hallazgos = auditar_descargas_locales()
        log.info("Auditoría local: %d series sin observaciones", len(hallazgos))
        if args.reconciliar_manifiestos:
            movidas, total_faltantes = reconciliar_manifiestos(hallazgos)
            log.info("Reclasificadas: %d; no disponibles totales: %d",
                     movidas, total_faltantes)
        return

    if not args.dry_run:
        geo_args = ["--refrescar"] if args.refrescar_geometria else []
        actualizar_geometria(geo_args)

    pols = [p.strip().lower() for p in args.contaminantes.split(",") if p.strip()]
    desconocidos = [p for p in pols if p not in PARAM_CODES]
    if desconocidos:
        ap.error(f"contaminantes desconocidos: {desconocidos}. Válidos: {list(PARAM_CODES)}")
    resoluciones = ["horario", "diario"] if args.resolucion == "ambas" else [args.resolucion]

    config_ruta = Path(args.config)
    config_bytes = config_ruta.read_bytes()
    config_estaciones_sha256 = hashlib.sha256(config_bytes).hexdigest()
    estaciones = json.loads(config_bytes)
    if args.limite:
        estaciones = estaciones[: args.limite]
    log.info("%d estaciones · contaminantes=%s · resoluciones=%s",
             len(estaciones), pols, resoluciones)

    manifiesto: list[dict] = []
    faltantes: list[dict] = []
    errores = 0
    for i, est in enumerate(estaciones, 1):
        region, estacion = est["region"], str(est["estacion"])
        nombre = est.get("nombre", "")
        for pol in pols:
            code = PARAM_CODES[pol]
            for res in resoluciones:
                dest = SINCA / pol / res
                if not args.dry_run:
                    # Fallar antes de la petición si el disco se llenó/desmontó.
                    _comprobar_espacio(dest, args.reserva_gb)
                try:
                    ruta, nb, resumen, url, accion = descargar_serie(
                        region, estacion, code, res, args.desde, args.hasta,
                        dest, dry_run=args.dry_run, reserva_gb=args.reserva_gb,
                    )
                except Exception as e:  # noqa: BLE001
                    errores += 1
                    log.error("  %s/%s %s/%s: %s", region, estacion, pol, res, e)
                    faltantes.append({
                        "region": region, "estacion": estacion, "nombre": nombre,
                        "contaminante": pol, "resolucion": res,
                        "desde": args.desde, "hasta": args.hasta,
                        "motivo": f"error: {e}",
                    })
                    if not args.dry_run:
                        _guardar_manifiestos(manifiesto, faltantes)
                        time.sleep(args.pausa)
                    continue
                if ruta:
                    log.info("  ✓ %s %s %s/%s (%d KB)", region, estacion, pol, res, nb // 1024)
                    manifiesto.append({
                        "region": region,
                        "estacion": estacion,
                        "nombre": nombre,
                        "contaminante": pol,
                        "resolucion": res,
                        "desde": args.desde,
                        "hasta": args.hasta,
                        "ruta": str(ruta),
                        "bytes": nb,
                        "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest(),
                        "filas": resumen.get("filas", ""),
                        "filas_con_observacion": resumen.get(
                            "filas_con_observacion", ""
                        ),
                        "primera_marca": resumen.get("primera_marca", ""),
                        "ultima_marca": resumen.get("ultima_marca", ""),
                        "primera_observacion": resumen.get(
                            "primera_observacion", ""
                        ),
                        "ultima_observacion": resumen.get(
                            "ultima_observacion", ""
                        ),
                        "url_fuente": url,
                        "accion": accion,
                        "script_version": SCRIPT_VERSION,
                        "script_sha256": SCRIPT_SHA256,
                        "config_estaciones_sha256": config_estaciones_sha256,
                        "marca_temporal": MARCA_TEMPORAL_SINCA,
                        "politica_utc": POLITICA_UTC,
                        "politica_temporal_sha256": POLITICA_TEMPORAL_SHA256,
                        "registrado_utc": datetime.now(UTC).isoformat(),
                    })
                else:
                    faltantes.append({
                        "region": region, "estacion": estacion, "nombre": nombre,
                        "contaminante": pol, "resolucion": res,
                        "desde": args.desde, "hasta": args.hasta,
                        "motivo": "sin datos",
                    })
                if not args.dry_run:
                    # Checkpoint por petición: una desconexión no deja toda
                    # la sesión sin procedencia ni obliga a recomenzarla.
                    _guardar_manifiestos(manifiesto, faltantes)
                    time.sleep(args.pausa)
        if i % 10 == 0:
            log.info("… %d/%d estaciones", i, len(estaciones))

    if not args.dry_run:
        _guardar_manifiestos(manifiesto, faltantes)
        log.info("Listo: %d series útiles, %d sin datos, %d errores. Ver manifiesto_descarga.csv",
                 len(manifiesto), len(faltantes) - errores, errores)
    return 1 if errores else 0


def main(argv=None):
    with ExitStack() as recursos:
        return _main(argv, recursos)


if __name__ == "__main__":
    raise SystemExit(main())
