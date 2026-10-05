#!/usr/bin/env python3
"""World Bank Light Every Night DMSP-OLS: pasadas nocturnas de Chile.

La fuente es el bucket publico ``s3://globalnightlight`` y su catalogo STAC
estatico. Para la brecha anterior a VIIRS este programa conserva cada segmento
orbital nocturno de 2000-01-01 a 2012-01-18, sin generar compuestos mensuales ni
inventar observaciones horarias. ``segment_start_utc`` es la hora UTC de inicio
del segmento (precision de minuto), no la hora de observacion de cada pixel.

Los COG globales nunca se descargan: rasterio/GDAL lee por rangos solamente las
ventanas de cinco AOI de Chile. La salida exige y conserva ``vis_dn``,
``qa_flag``, ``sample_position`` y ``lunar_illuminance_lux`` en la grilla OIS
publicada de 30 arc-sec, sin
remuestreo. Ese espaciado no debe interpretarse como una huella fisica de 1 km:
OLS Interleaved Smooth tiene GSD/smooth aproximado de 2,7 km y resolución
nocturna efectiva/IFOV cercana a 4,9 km. Cada
Parquet se publica de forma atomica, se reabre, valida y registra con SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import AOI, resumen_mascara, seleccionar  # noqa: E402
from _common import CONTAMINANTES, DATA, ensure_dir, get_logger  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, sha256, sha256_conjunto_shapefile,
)
from _satellite_streaming import AreaTrabajo, BloqueoProceso  # noqa: E402

log = get_logger("dmsp_len")

PRODUCTO = "WB_LEN_DMSP_OLS_NIGHTLY"
VERSION = "World Bank Light Every Night DMSP-OLS nightly COG"
BUCKET = "globalnightlight"
REGION = "us-east-1"
HTTPS_ROOT = "https://globalnightlight.s3.amazonaws.com/"
STAC_KEY = "DMSP_catalog.json"
STAC_URL = HTTPS_ROOT + STAC_KEY
DOCUMENTACION_URL = (
    "https://worldbank.github.io/OpenNightLights/"
    "wb-light-every-night-readme.html"
)
REGISTRY_URL = "https://registry.opendata.aws/wb-light-every-night/"

FECHA_INICIO = date(2000, 1, 1)
FECHA_FIN = date(2012, 1, 18)
RESOLUCION = 1.0 / 120.0
GRID_WEST_EDGE = -180.0 - RESOLUCION / 2.0
GRID_NORTH_EDGE = 75.0 + RESOLUCION / 2.0
GRID_WIDTH = 43_200
GRID_HEIGHT = 16_801
GRID_ID = "dmsp_ols_30arcsec_centers_lon0_lat75_v1"

FLAG_NO_DATA = 1 << 15
AUSENCIAS_SIN_OTRO_SATELITE = (
    "2008-10-26", "2009-04-23", "2009-04-24",
    "2009-12-01", "2009-12-02", "2009-12-03",
)
QA_BITS = {
    "cloud_1": 0,
    "light_1": 1,
    "glare": 2,
    "bad_scanline_or_lightning": 3,
    "pixel_center": 4,
    "daytime": 5,
    "marginal": 6,
    "light_2": 7,
    "cloud_2": 10,
    "zero_lunar_illuminance": 11,
    "fixed_gain": 12,
    "clouds_unknown": 13,
    "no_data": 15,
}

INVENTARIO_SCHEMA = "airpollution.wb-len-dmsp-inventory.v2"
CATALOGO_SCHEMA = "airpollution.wb-len-dmsp-pixel-catalog.v2"
ESTADO_SCHEMA = "airpollution.wb-len-dmsp-segment-state.v2"
PROCESSOR_VERSION = "dmsp-len-nightly-v2"
PROCESSOR_SHA256 = sha256(Path(__file__).resolve())
LINKER_SHA256 = sha256(Path(__file__).resolve().with_name("crear_enlaces_pixeles.py"))

# Catálogos publicados para la ventana que complementa a Black Marble local.
# En 2012 sólo se recorren items hasta el 18 de enero inclusive.
SATELITE_ANIOS = {
    "F14": tuple(range(2000, 2004)),
    "F15": (*tuple(range(2000, 2008)), 2012),
    "F16": tuple(range(2004, 2011)),
    "F18": tuple(range(2010, 2013)),
}
CATALOGOS_ESPERADOS = tuple(sorted(
    (year, satelite,
     f"{satelite}{year}/{satelite}{year}_catalog.json")
    for satelite, years in SATELITE_ANIOS.items() for year in years
))
ITEM_LINKS_2000_2011_ESPERADOS = 108_131

ITEM_RE = re.compile(
    r"^(?P<sat>F\d{2})(?P<stamp>\d{12})\.night\.OIS\.vis\.co\.json$"
)
ANUAL_RE = re.compile(r"^(?P<sat>F\d{2})(?P<year>\d{4})_catalog\.json$")


@dataclass(frozen=True)
class AssetFuente:
    banda: str
    key: str
    href: str
    size: int
    etag: str
    last_modified: str
    version_id: str | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class Granulo:
    granule_id: str
    satelite: str
    segment_start_utc: str
    item_key: str
    bbox: tuple[float, float, float, float]
    assets: dict[str, AssetFuente]


@dataclass(frozen=True)
class GrupoDia:
    satelite: str
    fecha_utc: str
    granulos: tuple[Granulo, ...]


class ReservaEspacioError(RuntimeError):
    """La siguiente unidad no puede empezar respetando la reserva de disco."""


def _utc(texto: str) -> datetime:
    try:
        valor = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"timestamp STAC no es ISO-8601: {texto!r}") from exc
    if valor.tzinfo is None:
        raise ValueError(f"timestamp STAC no declara zona horaria: {texto!r}")
    return valor.astimezone(timezone.utc)


def _utc_texto(valor: datetime) -> str:
    return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rango(desde: str, hasta: str) -> tuple[date, date] | None:
    try:
        inicio, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
    except ValueError as exc:
        raise ValueError("--desde/--hasta deben ser fechas ISO YYYY-MM-DD") from exc
    if inicio > fin:
        raise ValueError("--desde es posterior a --hasta")
    inicio, fin = max(inicio, FECHA_INICIO), min(fin, FECHA_FIN)
    return None if inicio > fin else (inicio, fin)


def _key_segura(key: str) -> str:
    key = unquote(str(key)).lstrip("/")
    partes = PurePosixPath(key).parts
    if (not key or "?" in key or "#" in key or any(x in {"", ".", ".."}
                                                       for x in partes)):
        raise ValueError(f"key S3 insegura: {key!r}")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", key):
        raise ValueError(f"key S3 contiene caracteres no permitidos: {key!r}")
    return key


def _key_href(href: str, *, base: str = HTTPS_ROOT) -> str:
    absoluto = urljoin(base, str(href))
    p = urlsplit(absoluto)
    if (p.scheme != "https" or p.hostname != "globalnightlight.s3.amazonaws.com"
            or p.query or p.fragment):
        raise ValueError(f"href STAC fuera del bucket publico: {href!r}")
    return _key_segura(p.path)


def _href(key: str) -> str:
    return HTTPS_ROOT + quote(_key_segura(key), safe="/._-")


def cliente_s3():
    """Cliente de solo lectura sin cadena de credenciales AWS."""
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError as exc:
        raise SystemExit("Falta boto3: pip install boto3") from exc
    return boto3.client(
        "s3", region_name=REGION,
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=20,
            read_timeout=90,
            retries={"max_attempts": 10, "mode": "standard"},
        ),
    )


def _leer_json_s3(s3, key: str, *, max_bytes: int = 64 * 1024 * 1024) -> dict:
    key = _key_segura(key)
    respuesta = s3.get_object(Bucket=BUCKET, Key=key)
    cuerpo = respuesta["Body"]
    try:
        declarado = int(respuesta.get("ContentLength", 0) or 0)
        if declarado > max_bytes:
            raise ValueError(f"{key}: JSON excede {max_bytes} bytes")
        datos = cuerpo.read(max_bytes + 1)
    finally:
        cerrar = getattr(cuerpo, "close", None)
        if cerrar:
            cerrar()
    if len(datos) > max_bytes:
        raise ValueError(f"{key}: JSON excede {max_bytes} bytes")
    try:
        valor = json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{key}: JSON STAC invalido") from exc
    if not isinstance(valor, dict):
        raise ValueError(f"{key}: se esperaba un objeto JSON")
    return valor


def _metadata_asset(s3, banda: str, key: str):
    key = _key_segura(key)
    meta = s3.head_object(Bucket=BUCKET, Key=key)
    size = int(meta.get("ContentLength", 0))
    if size <= 0:
        raise ValueError(f"{key}: asset vacio")
    etag = str(meta.get("ETag", "")).strip('"')
    if not etag:
        raise ValueError(f"{key}: S3 no entrego ETag")
    modificado = meta.get("LastModified")
    if isinstance(modificado, datetime):
        modificado = _utc_texto(modificado)
    elif modificado is not None:
        modificado = str(modificado)
    else:
        raise ValueError(f"{key}: S3 no entrego LastModified")
    return AssetFuente(
        banda=banda,
        key=key,
        href=_href(key),
        size=size,
        etag=etag,
        last_modified=modificado,
        version_id=(str(meta["VersionId"]) if meta.get("VersionId") else None),
        checksum_sha256=(str(meta["ChecksumSHA256"])
                         if meta.get("ChecksumSHA256") else None),
    )


def _desplazamiento_longitud(
    bbox_fuente, bbox_aoi,
) -> float | None:
    """Devuelve -360/0/+360 para alinear un AOI con la convencion del COG."""
    sx0, sy0, sx1, sy1 = map(float, bbox_fuente)
    ax0, ay0, ax1, ay1 = map(float, bbox_aoi)
    if ay1 < sy0 or ay0 > sy1:
        return None
    for desplazamiento in (0.0, 360.0, -360.0):
        x0, x1 = ax0 + desplazamiento, ax1 + desplazamiento
        if x1 >= sx0 and x0 <= sx1:
            return desplazamiento
    return None


def _intersecta_chile(bbox, aois: tuple[AOI, ...]) -> bool:
    return any(_desplazamiento_longitud(bbox, aoi.bbox) is not None
               for aoi in aois)


def _item_key_desde_link(link: dict, catalogo_key: str) -> str:
    href = str(link.get("href", ""))
    base = _href(str(PurePosixPath(catalogo_key).parent) + "/")
    return _key_href(href, base=base)


def _cargar_item(s3, item_key: str, aois: tuple[AOI, ...],
                  inicio: date, fin: date) -> Granulo | None:
    item_key = _key_segura(item_key)
    nombre = PurePosixPath(item_key).name
    m = ITEM_RE.fullmatch(nombre)
    if not m:
        raise ValueError(f"item DMSP no reconocido: {item_key}")
    inicio_nombre = datetime.strptime(m.group("stamp"), "%Y%m%d%H%M").replace(
        tzinfo=timezone.utc)
    if not (inicio <= inicio_nombre.date() <= fin):
        return None
    item = _leer_json_s3(s3, item_key)
    if item.get("type") != "Feature" or str(item.get("id")) != nombre[:-5]:
        raise ValueError(f"{item_key}: identidad STAC inconsistente")
    inicio_stac = _utc(item.get("properties", {}).get("datetime", ""))
    if inicio_stac != inicio_nombre:
        raise ValueError(
            f"{item_key}: fecha del nombre {inicio_nombre} difiere de STAC {inicio_stac}"
        )
    try:
        bbox = tuple(float(x) for x in item["bbox"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{item_key}: bbox STAC invalido") from exc
    if len(bbox) != 4 or not all(math.isfinite(x) for x in bbox):
        raise ValueError(f"{item_key}: bbox STAC invalido")
    if not _intersecta_chile(bbox, aois):
        return None
    try:
        vis_key = _key_href(item["assets"]["image"]["href"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{item_key}: asset visible ausente") from exc
    esperado = item_key[:-5] + ".tif"
    if vis_key != esperado or not vis_key.endswith(".vis.co.tif"):
        raise ValueError(f"{item_key}: asset visible no corresponde al item")
    flag_key = vis_key[:-len(".vis.co.tif")] + ".flag.co.tif"
    samples_key = vis_key[:-len(".vis.co.tif")] + ".samples.co.tif"
    lunar_key = vis_key[:-len(".vis.co.tif")] + ".li.co.tif"
    vis = _metadata_asset(s3, "vis", vis_key)
    flag = _metadata_asset(s3, "flag", flag_key)
    samples = _metadata_asset(s3, "samples", samples_key)
    # LI forma parte del producto analítico requerido. Un 404 debe reintentarse
    # en otra ejecución, no consolidarse silenciosamente como un día completo.
    lunar = _metadata_asset(s3, "li", lunar_key)
    assets = {"vis": vis, "flag": flag, "samples": samples, "li": lunar}
    return Granulo(
        granule_id=nombre[:-5],
        satelite=m.group("sat"),
        segment_start_utc=_utc_texto(inicio_stac),
        item_key=item_key,
        bbox=bbox,
        assets=assets,
    )


def _catalogos_esperados(inicio: date, fin: date) -> list[tuple[int, str, str]]:
    return [fila for fila in CATALOGOS_ESPERADOS
            if inicio.year <= fila[0] <= fin.year]


def _catalogos_anuales(s3, inicio: date, fin: date) -> list[tuple[int, str, str]]:
    raiz = _leer_json_s3(s3, STAC_KEY)
    salida = []
    duplicados = []
    vistos = set()
    for link in raiz.get("links", []):
        if link.get("rel") != "child":
            continue
        key = _key_href(str(link.get("href", "")), base=STAC_URL)
        nombre = PurePosixPath(key).name
        m = ANUAL_RE.fullmatch(nombre)
        if not m or PurePosixPath(key).parent.name != m.group("sat") + m.group("year"):
            continue
        year = int(m.group("year"))
        if inicio.year <= year <= fin.year:
            fila = (year, m.group("sat"), key)
            if fila in vistos:
                duplicados.append(key)
            vistos.add(fila)
            salida.append(fila)
    esperados = _catalogos_esperados(inicio, fin)
    if duplicados or sorted(salida) != esperados:
        faltan = sorted(set(esperados) - set(salida))
        sobran = sorted(set(salida) - set(esperados))
        raise ValueError(
            "catalogos satelite-anio DMSP incompletos/inesperados: "
            f"faltan={faltan}, sobran={sobran}, duplicados={sorted(duplicados)}"
        )
    return esperados


def _items_catalogo(catalogo: dict, catalogo_key: str, satelite: str,
                    year: int, inicio: date, fin: date) -> tuple[int, list[str]]:
    links = [link for link in catalogo.get("links", [])
             if link.get("rel") == "item"]
    if not links:
        raise ValueError(f"{catalogo_key}: catalogo anual sin links item")
    keys = []
    vistos = set()
    carpeta_esperada = f"{satelite}{year}"
    for link in links:
        key = _item_key_desde_link(link, catalogo_key)
        m = ITEM_RE.fullmatch(PurePosixPath(key).name)
        if (not m or m.group("sat") != satelite
                or PurePosixPath(key).parent.name != carpeta_esperada):
            raise ValueError(f"{catalogo_key}: link item inesperado {key}")
        instante = datetime.strptime(m.group("stamp"), "%Y%m%d%H%M").date()
        if instante.year != year:
            raise ValueError(f"{catalogo_key}: item pertenece a otro anio: {key}")
        if key in vistos:
            raise ValueError(f"{catalogo_key}: link item duplicado {key}")
        vistos.add(key)
        if inicio <= instante <= fin:
            keys.append(key)
    return len(links), keys


def _rango_solo_ausencias_conocidas(inicio: date, fin: date) -> bool:
    ausencias = {date.fromisoformat(x) for x in AUSENCIAS_SIN_OTRO_SATELITE}
    dias = (fin - inicio).days + 1
    return sum(inicio <= x <= fin for x in ausencias) == dias


def _validar_auditoria_catalogos(auditoria: list[dict], *, inicio: date,
                                  fin: date, completo: bool) -> None:
    claves = [(int(x["year"]), str(x["satelite"]), str(x["catalog_key"]))
              for x in auditoria]
    if len(claves) != len(set(claves)):
        raise ValueError("auditoria de catalogos contiene duplicados")
    for fila in auditoria:
        if int(fila.get("item_links_total", 0)) <= 0:
            raise ValueError(f"{fila.get('catalog_key')}: catalogo sin items")
        if not re.fullmatch(r"[0-9a-f]{64}", str(fila.get("catalog_sha256", ""))):
            raise ValueError(f"{fila.get('catalog_key')}: hash de catalogo ausente")
        if int(fila.get("items_visitados", -1)) < 0:
            raise ValueError("auditoria de catalogos tiene conteos invalidos")
    if not completo:
        return
    esperados = _catalogos_esperados(inicio, fin)
    if sorted(claves) != esperados:
        raise ValueError(
            f"inventario no recorrio exactamente los catalogos esperados: {claves}"
        )
    for fila in auditoria:
        if not fila.get("recorrido_completo"):
            raise ValueError(f"{fila['catalog_key']}: recorrido incompleto")
        if int(fila["items_visitados"]) != int(fila["item_links_en_rango"]):
            raise ValueError(f"{fila['catalog_key']}: no se visitaron todos los items")
    if inicio == FECHA_INICIO and fin >= date(2011, 12, 31):
        total_base = sum(
            int(fila["item_links_total"])
            for fila in auditoria if int(fila["year"]) <= 2011
        )
        if total_base != ITEM_LINKS_2000_2011_ESPERADOS:
            raise ValueError(
                "conteo STAC 2000-2011 incompleto/inesperado: "
                f"{total_base} != {ITEM_LINKS_2000_2011_ESPERADOS}"
            )


def inventariar(s3, *, inicio: date, fin: date, aois: tuple[AOI, ...],
                limite: int | None = None, workers: int = 16
                ) -> tuple[list[Granulo], list[dict]]:
    """Lee el STAC estatico y conserva todos los segmentos que pueden tocar Chile."""
    if workers < 1:
        raise ValueError("workers debe ser positivo")
    encontrados: list[Granulo] = []
    auditoria: list[dict] = []
    vistos: set[str] = set()
    for year, satelite, catalogo_key in _catalogos_anuales(s3, inicio, fin):
        catalogo = _leer_json_s3(s3, catalogo_key)
        total_links, keys = _items_catalogo(
            catalogo, catalogo_key, satelite, year, inicio, fin)
        repetidos = sorted(set(keys) & vistos)
        if repetidos:
            raise ValueError(f"items repetidos entre catalogos: {repetidos[:3]}")
        vistos.update(keys)
        registro = {
            "year": year,
            "satelite": satelite,
            "catalog_key": catalogo_key,
            "catalog_sha256": hashlib.sha256(json.dumps(
                catalogo, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")).hexdigest(),
            "item_links_total": total_links,
            "item_links_en_rango": len(keys),
            "items_visitados": 0,
            "segmentos_chile_detectados": 0,
            "recorrido_completo": False,
        }
        auditoria.append(registro)
        # Lotes acotados permiten que --limite sea un smoke sin recorrer 108 mil items.
        for pos in range(0, len(keys), 128):
            lote = keys[pos:pos + 128]
            if workers == 1:
                resultados = [
                    _cargar_item(s3, key, aois, inicio, fin) for key in lote
                ]
            else:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    resultados = list(executor.map(
                        lambda key: _cargar_item(s3, key, aois, inicio, fin), lote
                    ))
            registro["items_visitados"] += len(lote)
            registro["segmentos_chile_detectados"] += sum(
                x is not None for x in resultados)
            encontrados.extend(x for x in resultados if x is not None)
            if limite is not None and len(encontrados) >= limite:
                encontrados.sort(key=lambda x: (
                    x.segment_start_utc, x.satelite, x.granule_id))
                _validar_auditoria_catalogos(
                    auditoria, inicio=inicio, fin=fin, completo=False)
                return encontrados[:limite], auditoria
        registro["recorrido_completo"] = True
    encontrados.sort(key=lambda x: (x.segment_start_utc, x.satelite, x.granule_id))
    _validar_auditoria_catalogos(auditoria, inicio=inicio, fin=fin, completo=True)
    if not encontrados and not _rango_solo_ausencias_conocidas(inicio, fin):
        raise ValueError("el inventario STAC no contiene segmentos que alcancen Chile")
    return encontrados, auditoria


def _agrupar_dias(granulos: list[Granulo]) -> list[GrupoDia]:
    grupos: dict[tuple[str, str], list[Granulo]] = {}
    for granulo in granulos:
        fecha = _utc(granulo.segment_start_utc).date().isoformat()
        grupos.setdefault((granulo.satelite, fecha), []).append(granulo)
    salida = []
    for (satelite, fecha), items in sorted(
            grupos.items(), key=lambda x: (x[0][1], x[0][0])):
        items.sort(key=lambda x: (x.segment_start_utc, x.granule_id))
        salida.append(GrupoDia(satelite, fecha, tuple(items)))
    return sorted(salida, key=lambda x: (x.fecha_utc, x.satelite))


def _guardar_json_atomico(path: Path, datos: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.unlink(missing_ok=True)
    try:
        with part.open("w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def _guardar_inventario(path: Path, granulos: list[Granulo], *, inicio: date,
                        fin: date, aois: tuple[AOI, ...], mascara_sha: str,
                        limite: int | None, auditoria_catalogos: list[dict]) -> None:
    completo = limite is None
    _validar_auditoria_catalogos(
        auditoria_catalogos, inicio=inicio, fin=fin, completo=completo)
    _guardar_json_atomico(path, {
        "schema": INVENTARIO_SCHEMA,
        "consultado_utc": _utc_texto(datetime.now(timezone.utc)),
        "bucket": BUCKET,
        "region": REGION,
        "stac": STAC_URL,
        "documentacion": DOCUMENTACION_URL,
        "licencias_declaradas": {
            "stac_dmsp": "MIT",
            "registro_aws": "World Bank Open Database License (ODbL)",
            "politica": "conservar atribucion y aplicar la condicion mas restrictiva",
        },
        "rango": [inicio.isoformat(), fin.isoformat()],
        "limite_smoke": limite,
        "inventario_completo": completo,
        "processor_version": PROCESSOR_VERSION,
        "processor_sha256": PROCESSOR_SHA256,
        "mascara_sha256": mascara_sha,
        "aois": [asdict(aoi) for aoi in aois],
        "catalogos": auditoria_catalogos,
        "granulos": [asdict(x) for x in granulos],
    })


def _leer_inventario(path: Path, *, inicio: date, fin: date,
                     aois: tuple[AOI, ...], mascara_sha: str,
                     limite: int | None) -> tuple[list[Granulo], list[dict]]:
    datos = json.loads(path.read_text(encoding="utf-8"))
    if datos.get("schema") != INVENTARIO_SCHEMA:
        raise ValueError(f"{path}: schema de inventario no reconocido")
    if datos.get("rango") != [inicio.isoformat(), fin.isoformat()]:
        raise ValueError(f"{path}: rango de inventario distinto")
    if datos.get("limite_smoke") != limite:
        raise ValueError(f"{path}: limite de inventario distinto")
    if datos.get("mascara_sha256") != mascara_sha:
        raise ValueError(f"{path}: inventario creado con otra mascara")
    if datos.get("aois") != [asdict(aoi) for aoi in aois]:
        raise ValueError(f"{path}: inventario creado con otras AOI")
    if (datos.get("processor_version") != PROCESSOR_VERSION
            or datos.get("processor_sha256") != PROCESSOR_SHA256):
        raise ValueError(f"{path}: inventario creado con otro procesador")
    completo = limite is None
    if bool(datos.get("inventario_completo")) != completo:
        raise ValueError(f"{path}: declaracion de completitud inconsistente")
    auditoria = datos.get("catalogos")
    if not isinstance(auditoria, list):
        raise ValueError(f"{path}: falta auditoria por catalogo")
    _validar_auditoria_catalogos(
        auditoria, inicio=inicio, fin=fin, completo=completo)
    salida = []
    vistos_granulo = set()
    for fila in datos.get("granulos", []):
        assets = {k: AssetFuente(**v) for k, v in fila["assets"].items()}
        granulo = Granulo(
            granule_id=fila["granule_id"], satelite=fila["satelite"],
            segment_start_utc=fila["segment_start_utc"],
            item_key=fila["item_key"], bbox=tuple(fila["bbox"]), assets=assets,
        )
        if not ITEM_RE.fullmatch(granulo.granule_id + ".json"):
            raise ValueError(f"{path}: granule_id invalido")
        if granulo.granule_id in vistos_granulo:
            raise ValueError(f"{path}: granule_id duplicado")
        vistos_granulo.add(granulo.granule_id)
        if set(assets) != {"vis", "flag", "samples", "li"}:
            raise ValueError(f"{path}: bandas de inventario invalidas")
        for asset in assets.values():
            if _key_href(asset.href) != asset.key:
                raise ValueError(f"{path}: href/key inconsistente")
        salida.append(granulo)
    if completo and len(salida) != sum(
            int(x["segmentos_chile_detectados"]) for x in auditoria):
        raise ValueError(f"{path}: lista de granulos truncada respecto de auditoria")
    if not salida and not _rango_solo_ausencias_conocidas(inicio, fin):
        raise ValueError(f"{path}: inventario vacio")
    return salida, auditoria


def _grid_transform():
    from affine import Affine
    return Affine(RESOLUCION, 0.0, GRID_WEST_EDGE,
                  0.0, -RESOLUCION, GRID_NORTH_EDGE)


def _grid_fingerprint() -> str:
    datos = {
        "grid_id": GRID_ID,
        "crs": "EPSG:4326",
        "resolution": RESOLUCION,
        "west_edge": GRID_WEST_EDGE,
        "north_edge": GRID_NORTH_EDGE,
        "width": GRID_WIDTH,
        "height": GRID_HEIGHT,
    }
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()


def _geometrias(comunas_path: Path):
    import geopandas as gpd
    comunas = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    if "cod_comuna" not in comunas:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    try:
        comunas["geometry"] = comunas.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        comunas["geometry"] = comunas.geometry.map(make_valid)
    comunas["cod_comuna"] = pd.to_numeric(
        comunas.cod_comuna, errors="raise").astype("int32")
    if (comunas.cod_comuna < 0).any():
        raise ValueError("la mascara contiene codigos administrativos negativos")
    return comunas


def _window_entera(transform, width: int, height: int, bbox):
    from rasterio.windows import Window, from_bounds
    w = from_bounds(*bbox, transform=transform)
    c0, r0 = max(0, math.floor(w.col_off)), max(0, math.floor(w.row_off))
    c1 = min(width, math.ceil(w.col_off + w.width))
    r1 = min(height, math.ceil(w.row_off + w.height))
    if c1 <= c0 or r1 <= r0:
        raise ValueError("AOI fuera de la grilla DMSP")
    return Window(c0, r0, c1 - c0, r1 - r0)


def _construir_catalogo_aoi(aoi: AOI, comunas) -> pd.DataFrame:
    import rasterio
    from rasterio.features import rasterize
    from shapely.geometry import box

    transform_global = _grid_transform()
    window = _window_entera(
        transform_global, GRID_WIDTH, GRID_HEIGHT, aoi.bbox)
    transform = rasterio.windows.transform(window, transform_global)
    shape = (int(window.height), int(window.width))
    sub = comunas[comunas.geometry.intersects(box(*aoi.bbox))]
    formas = [
        (geom, int(cod)) for geom, cod in
        zip(sub.geometry, sub.cod_comuna, strict=False)
        if geom is not None and not geom.is_empty
    ]
    if not formas:
        raise ValueError(f"{aoi.id}: AOI sin geometria administrativa")
    formas.sort(key=lambda x: x[1] == 0)
    toca = rasterize(
        [(geom, 1) for geom, _ in formas], out_shape=shape,
        transform=transform, fill=0, dtype="uint8", all_touched=True,
    ).astype(bool)
    codigos = rasterize(
        formas, out_shape=shape, transform=transform,
        fill=-1, dtype="int32", all_touched=False,
    )
    filas, columnas = np.where(toca)
    if not len(filas):
        raise ValueError(f"{aoi.id}: ninguna celda de 30 arc-sec toca Chile")
    grid_row = filas.astype("int64") + int(window.row_off)
    grid_col = columnas.astype("int64") + int(window.col_off)
    pixel_id = grid_row * GRID_WIDTH + grid_col
    xs, ys = rasterio.transform.xy(transform, filas, columnas, offset="center")
    salida = pd.DataFrame({
        "pixel_id": pixel_id.astype("int64"),
        "grid_row": grid_row.astype("int32"),
        "grid_col": grid_col.astype("int32"),
        "lat": np.asarray(ys, dtype="float64"),
        "lon": np.asarray(xs, dtype="float64"),
        "cod_comuna": codigos[filas, columnas].astype("int32"),
        "aoi_id": aoi.id,
        "territorio": aoi.territorio,
        "resolution_degrees": RESOLUCION,
        "grid_id": GRID_ID,
    }).sort_values("pixel_id").reset_index(drop=True)
    if salida.pixel_id.duplicated().any():
        raise ValueError(f"{aoi.id}: pixel_id duplicado en catalogo")
    return salida


CATALOGO_COLUMNAS = [
    "pixel_id", "grid_row", "grid_col", "lat", "lon", "cod_comuna",
    "aoi_id", "territorio", "resolution_degrees", "grid_id",
]


def _validar_catalogo(path: Path, aoi: AOI | None = None) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if list(df.columns) != CATALOGO_COLUMNAS or df.empty:
        raise ValueError(f"{path}: esquema/catalogo vacio")
    if df.pixel_id.duplicated().any():
        raise ValueError(f"{path}: pixel_id duplicado")
    if not np.isfinite(df[["lat", "lon"]].to_numpy()).all():
        raise ValueError(f"{path}: coordenadas no finitas")
    if not np.allclose(df.resolution_degrees, RESOLUCION, rtol=0.0):
        raise ValueError(f"{path}: resolucion no es 30 arc-sec")
    if not df.grid_id.eq(GRID_ID).all():
        raise ValueError(f"{path}: grid_id distinto")
    if aoi is not None and not (
            df.aoi_id.eq(aoi.id).all() and df.territorio.eq(aoi.territorio).all()):
        raise ValueError(f"{path}: identidad AOI inconsistente")
    esperado = (df.grid_row.astype("int64") * GRID_WIDTH
                + df.grid_col.astype("int64"))
    if not np.array_equal(esperado.to_numpy(), df.pixel_id.to_numpy()):
        raise ValueError(f"{path}: pixel_id no corresponde a la grilla")
    return df.sort_values("pixel_id").reset_index(drop=True)


def _publicar_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.unlink(missing_ok=True)
    try:
        df.to_parquet(part, index=False, compression="zstd")
        comprobacion = pd.read_parquet(part)
        if len(comprobacion) != len(df) or list(comprobacion.columns) != list(df.columns):
            raise ValueError(f"{path}: reapertura Parquet no coincide")
        with part.open("rb") as fh:
            os.fsync(fh.fileno())
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)


def _registro_parquet(path: Path, filas: int) -> dict:
    return {
        "filas": int(filas),
        "bytes": int(path.stat().st_size),
        "sha256": sha256(path),
    }


def _validar_registro_parquet(path: Path, registro: dict, filas: int) -> None:
    if (not path.is_file()
            or int(registro.get("filas", -1)) != int(filas)
            or int(registro.get("bytes", -1)) != path.stat().st_size
            or registro.get("sha256") != sha256(path)):
        raise ValueError(f"{path}: hash/filas del Parquet cacheado no coinciden")


def _cargar_o_publicar_catalogos(base: Path, aois: tuple[AOI, ...], comunas,
                                  comunas_path: Path,
                                  mascara_sha: str) -> dict[str, pd.DataFrame]:
    carpeta = base / "catalogo_pixeles"
    meta_path = carpeta / "metadata.json"
    paths = {a.id: carpeta / f"{a.id}.parquet" for a in aois}
    alguno = meta_path.exists() or any(path.exists() for path in paths.values())
    if alguno:
        if not meta_path.exists() or not all(path.exists() for path in paths.values()):
            raise ValueError("catalogo LEN DMSP incompleto; no se mezclara")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if (meta.get("schema") != CATALOGO_SCHEMA
                or meta.get("mascara_sha256") != mascara_sha
                or meta.get("grid_fingerprint") != _grid_fingerprint()
                or meta.get("processor_version") != PROCESSOR_VERSION
                or meta.get("processor_sha256") != PROCESSOR_SHA256):
            raise ValueError("catalogo LEN DMSP pertenece a otra mascara/grilla")
        archivos = meta.get("archivos")
        if not isinstance(archivos, dict) or set(archivos) != set(paths):
            raise ValueError("catalogo LEN DMSP sin auditoria completa de archivos")
        catalogos = {}
        for aoi in aois:
            catalogo = _validar_catalogo(paths[aoi.id], aoi)
            _validar_registro_parquet(
                paths[aoi.id], archivos[aoi.id], len(catalogo))
            catalogos[aoi.id] = catalogo
        return catalogos
    catalogos = {a.id: _construir_catalogo_aoi(a, comunas) for a in aois}
    for aoi in aois:
        _publicar_parquet(catalogos[aoi.id], paths[aoi.id])
        catalogos[aoi.id] = _validar_catalogo(paths[aoi.id], aoi)
    _guardar_json_atomico(meta_path, {
        "schema": CATALOGO_SCHEMA,
        "producto": PRODUCTO,
        "grid_id": GRID_ID,
        "grid_fingerprint": _grid_fingerprint(),
        "processor_version": PROCESSOR_VERSION,
        "processor_sha256": PROCESSOR_SHA256,
        "crs": "EPSG:4326",
        "resolution_degrees": RESOLUCION,
        "pixel_id": f"grid_row * {GRID_WIDTH} + grid_col",
        "mascara": str(comunas_path),
        "mascara_sha256": mascara_sha,
        "seleccion": "cell footprint intersects Chile; all_touched=True",
        "cod_comuna": "centro de celda; -1 si solo la huella toca Chile",
        "sin_remuestreo": True,
        "archivos": {
            aoi.id: _registro_parquet(paths[aoi.id], len(catalogos[aoi.id]))
            for aoi in aois
        },
    })
    return catalogos


def _publicar_enlaces(base: Path, catalogos: dict[str, pd.DataFrame],
                       comunas_path: Path, mascara_sha: str) -> dict[str, int]:
    from crear_enlaces_pixeles import construir_enlace, enlazar_estaciones

    carpeta = base / "enlaces_geoespaciales"
    enlace_path = carpeta / "pixel_comuna.parquet"
    estacion_path = carpeta / "estacion_pixel.parquet"
    excluidas_path = carpeta / "estaciones_excluidas.parquet"
    meta_path = carpeta / "metadata.json"
    estaciones = DATA / "sinca" / "estaciones_georreferenciadas.csv"
    fuente_estaciones = ({
        "ruta": str(estaciones),
        "bytes": int(estaciones.stat().st_size),
        "sha256": sha256(estaciones),
    } if estaciones.exists() else None)
    if enlace_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        enlace = pd.read_parquet(enlace_path)
        if (meta.get("schema") == "airpollution.pixel-commune-links.v1"
                and meta.get("mascara_sha256") == mascara_sha
                and meta.get("grid_fingerprint") == _grid_fingerprint()
                and meta.get("processor_version") == PROCESSOR_VERSION
                and meta.get("processor_sha256") == PROCESSOR_SHA256
                and meta.get("linker_sha256") == LINKER_SHA256
                and meta.get("estaciones_fuente") == fuente_estaciones
                and not enlace.empty
                and not enlace.duplicated(["pixel_id", "cod_comuna"]).any()):
            archivos = meta.get("archivos", {})
            if "pixel_comuna" not in archivos:
                raise ValueError("enlaces LEN DMSP sin hash de pixel-comuna")
            _validar_registro_parquet(
                enlace_path, archivos["pixel_comuna"], len(enlace))
            if fuente_estaciones is not None:
                if set(archivos) != {
                        "pixel_comuna", "estacion_pixel", "estaciones_excluidas"}:
                    raise ValueError("auditoria de enlaces de estaciones incompleta")
                est = pd.read_parquet(estacion_path)
                excluidas = pd.read_parquet(excluidas_path)
                _validar_registro_parquet(
                    estacion_path, archivos["estacion_pixel"], len(est))
                _validar_registro_parquet(
                    excluidas_path, archivos["estaciones_excluidas"], len(excluidas))
            elif (estacion_path.exists() or excluidas_path.exists()
                  or set(archivos) != {"pixel_comuna"}):
                raise ValueError("salidas de estaciones sin fuente registrada")
            return {
                "enlaces_pixel_comuna": len(enlace),
                "pixeles_enlazados": int(enlace.pixel_id.nunique()),
                "unidades_administrativas": int(enlace.cod_comuna.nunique()),
            }
        raise ValueError("enlaces LEN DMSP no corresponden a mascara/grilla")
    if enlace_path.exists() != meta_path.exists():
        raise ValueError("enlaces LEN DMSP incompletos")
    pix = pd.concat(catalogos.values(), ignore_index=True)
    pix = pix.drop_duplicates("pixel_id").sort_values("pixel_id").reset_index(drop=True)
    # `cod_comuna` del catalogo corresponde solo al centro; el enlace exacto
    # debe recalcular todas las intersecciones de huella sin colisionar columnas.
    enlace = construir_enlace(pix.drop(columns=["cod_comuna"]),
                              comunas_path, lote=20_000)
    esperados = set(_geometrias(comunas_path).cod_comuna.astype(int))
    faltan = sorted(esperados - set(enlace.cod_comuna.astype(int)))
    if faltan:
        raise ValueError(f"enlace pixel-comuna no cubre unidades {faltan}")
    conteos = enlace.groupby("cod_comuna").pixel_id.nunique()
    unidades_un_pixel = {int(k): int(v) for k, v in conteos[conteos < 2].items()}
    _publicar_parquet(enlace, enlace_path)
    archivos = {"pixel_comuna": _registro_parquet(enlace_path, len(enlace))}
    if estaciones.exists():
        est, excluidas = enlazar_estaciones(enlace, estaciones)
        _publicar_parquet(est, estacion_path)
        _publicar_parquet(excluidas, excluidas_path)
        if sha256(estaciones) != fuente_estaciones["sha256"]:
            raise RuntimeError("el CSV de estaciones cambio durante el enlace")
        archivos.update({
            "estacion_pixel": _registro_parquet(estacion_path, len(est)),
            "estaciones_excluidas": _registro_parquet(
                excluidas_path, len(excluidas)),
        })
    _guardar_json_atomico(meta_path, {
        "schema": "airpollution.pixel-commune-links.v1",
        "producto": PRODUCTO,
        "processor_version": PROCESSOR_VERSION,
        "processor_sha256": PROCESSOR_SHA256,
        "linker_sha256": LINKER_SHA256,
        "mascara_sha256": mascara_sha,
        "grid_fingerprint": _grid_fingerprint(),
        "metodo": "interseccion exacta de huella 30 arc-sec; muchos-a-muchos",
        "sin_agregacion": True,
        "enlaces_pixel_comuna": len(enlace),
        "pixeles_enlazados": int(enlace.pixel_id.nunique()),
        "unidades_administrativas": int(enlace.cod_comuna.nunique()),
        "min_pixeles_por_unidad": int(conteos.min()),
        "max_pixeles_por_unidad": int(conteos.max()),
        "unidades_con_un_pixel": unidades_un_pixel,
        "estaciones_fuente": fuente_estaciones,
        "archivos": archivos,
    })
    return {
        "enlaces_pixel_comuna": len(enlace),
        "pixeles_enlazados": int(enlace.pixel_id.nunique()),
        "unidades_administrativas": int(enlace.cod_comuna.nunique()),
    }


def _validar_grilla_fuente(src, banda: str, referencia=None) -> None:
    if src.count != 1 or src.crs is None or src.crs.to_epsg() != 4326:
        raise ValueError(f"{banda}: COG no es raster monobanda EPSG:4326")
    t = src.transform
    if (not np.isclose(abs(t.a), RESOLUCION, atol=1e-8, rtol=0.0)
            or not np.isclose(abs(t.e), RESOLUCION, atol=1e-8, rtol=0.0)
            or not np.isclose(t.b, 0.0, rtol=0.0)
            or not np.isclose(t.d, 0.0, rtol=0.0)):
        raise ValueError(f"{banda}: resolucion/rotacion no es grilla 30 arc-sec")
    x, y = src.xy(0, 0, offset="center")
    lon = ((float(x) + 180.0) % 360.0) - 180.0
    col = (lon + 180.0) / RESOLUCION
    row = (75.0 - float(y)) / RESOLUCION
    if not (np.isclose(col, round(col), atol=2e-5, rtol=0.0)
            and np.isclose(row, round(row), atol=2e-5, rtol=0.0)):
        raise ValueError(f"{banda}: grilla no esta alineada con centros DMSP")
    if referencia is not None and (
            src.width != referencia.width or src.height != referencia.height
            or not np.allclose(
                tuple(src.transform)[:6], tuple(referencia.transform)[:6],
                atol=1e-10, rtol=0.0,
            )):
        raise ValueError(f"{banda}: no comparte grilla con vis")
    dtype = np.dtype(src.dtypes[0])
    if banda == "vis" and dtype != np.dtype("uint8"):
        raise ValueError(f"vis: dtype {dtype}, se esperaba uint8")
    if banda == "flag" and dtype != np.dtype("uint16"):
        raise ValueError(f"flag: dtype {dtype}, se esperaba uint16")
    if banda == "samples" and dtype != np.dtype("uint16"):
        raise ValueError(f"samples: dtype {dtype}, se esperaba uint16")
    if banda == "li" and not np.issubdtype(dtype, np.floating):
        raise ValueError(f"li: dtype {dtype}, se esperaba flotante")


OBS_BASE_COLUMNAS = [
    "pixel_id", "vis_dn", "qa_flag", "sample_position", "satelite", "orbit_id",
    "segment_start_utc", "time_is_pixel_specific", "time_reference", "aoi_id",
]


def _leer_aoi(srcs, granulo: Granulo, aoi: AOI,
               catalogo: pd.DataFrame) -> tuple[pd.DataFrame | None, dict]:
    import rasterio
    from rasterio.windows import Window

    ref = srcs["vis"]
    desplazamiento = _desplazamiento_longitud(ref.bounds, aoi.bbox)
    if desplazamiento is None:
        return None, {"estado": "fuera_bbox", "pixeles_catalogo": len(catalogo)}
    xs = catalogo.lon.to_numpy(dtype="float64") + desplazamiento
    ys = catalogo.lat.to_numpy(dtype="float64")
    rows, cols = rasterio.transform.rowcol(ref.transform, xs, ys)
    rows, cols = np.asarray(rows, dtype="int64"), np.asarray(cols, dtype="int64")
    dentro = ((rows >= 0) & (rows < ref.height)
              & (cols >= 0) & (cols < ref.width))
    if not dentro.any():
        return None, {"estado": "sin_datos", "pixeles_catalogo": len(catalogo),
                      "pixeles_en_bbox": 0}
    indices = np.flatnonzero(dentro)
    rr, cc = rows[dentro], cols[dentro]
    r0, r1, c0, c1 = int(rr.min()), int(rr.max()), int(cc.min()), int(cc.max())
    window = Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
    centros_x, centros_y = rasterio.transform.xy(
        ref.transform, rr, cc, offset="center")
    # Los GeoTIFF publican el paso como decimal truncado; la deriva acumulada
    # observada en un segmento largo llega a ~5,3e-05 grados. Se admite menos
    # de 0,1 pixel y nunca se interpola/remuestrea.
    if (not np.allclose(
            np.asarray(centros_x), xs[dentro], atol=1e-4, rtol=0.0)
            or not np.allclose(
                np.asarray(centros_y), ys[dentro], atol=1e-4, rtol=0.0)):
        raise ValueError(f"{granulo.granule_id} {aoi.id}: celdas no alineadas")
    local_r, local_c = rr - r0, cc - c0
    vis = srcs["vis"].read(1, window=window)[local_r, local_c]
    flag = srcs["flag"].read(1, window=window)[local_r, local_c]
    samples = srcs["samples"].read(1, window=window)[local_r, local_c]
    # No se filtran nubes, luces, glare, luna cero, dia ni margen: esos bits
    # quedan empacados para decidir el QA durante el analisis. Solo se retira el
    # fill/no-data que no representa una observacion terrestre.
    validos = (vis <= 63) & ((flag.astype("uint16") & FLAG_NO_DATA) == 0)
    stats = {
        "estado": "archivo" if validos.any() else "sin_datos",
        "pixeles_catalogo": len(catalogo),
        "pixeles_en_bbox": len(indices),
        "vis_fill_o_fuera_rango": int((vis > 63).sum()),
        "flag_no_data": int(((flag.astype("uint16") & FLAG_NO_DATA) != 0).sum()),
        "pixeles_source_nonfill": int(validos.sum()),
    }
    if not validos.any():
        return None, stats
    seleccion = catalogo.iloc[indices[validos]]
    samples_visibles = samples[validos].astype("uint16")
    if (samples_visibles > 1465).any():
        raise ValueError(
            f"{granulo.granule_id} {aoi.id}: sample_position fuera de 0..1465"
        )
    samples_nullable = pd.array(samples_visibles, dtype="UInt16")
    samples_nullable[samples_visibles == 0] = pd.NA
    stats["samples_fill"] = int((samples_visibles == 0).sum())
    obs = pd.DataFrame({
        "pixel_id": seleccion.pixel_id.to_numpy(dtype="int64"),
        "vis_dn": vis[validos].astype("uint8"),
        "qa_flag": flag[validos].astype("uint16"),
        # Cero es fill de posición cross-track. No elimina la observación VIS.
        "sample_position": samples_nullable,
    })
    lunar = srcs["li"].read(1, window=window)[local_r, local_c]
    lunar = lunar[validos].astype("float32")
    # La documentacion menciona -1, pero existen fills reales cercanos a
    # -999,3. Todos los negativos se normalizan a nulo, nunca a cero lux.
    lunar_fill = (~np.isfinite(lunar)) | (lunar < 0)
    lunar = lunar.copy()
    lunar[lunar_fill] = np.nan
    obs["lunar_illuminance_lux"] = lunar
    stats["lunar_fill"] = int(lunar_fill.sum())
    obs["satelite"] = granulo.satelite
    obs["orbit_id"] = granulo.granule_id
    obs["segment_start_utc"] = pd.Timestamp(granulo.segment_start_utc)
    obs["time_is_pixel_specific"] = False
    obs["time_reference"] = "orbit_segment_start_utc_not_pixel_time"
    obs["aoi_id"] = aoi.id
    obs = obs.sort_values("pixel_id").reset_index(drop=True)
    return obs, stats


def _extraer_granulo(granulo: Granulo, aois: tuple[AOI, ...],
                      catalogos: dict[str, pd.DataFrame],
                      trabajo: Path | None = None):
    import rasterio
    opciones = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "VSI_CACHE": "FALSE",
        "AWS_NO_SIGN_REQUEST": "YES",
        "GDAL_HTTP_CONNECTTIMEOUT": "20",
        "GDAL_HTTP_TIMEOUT": "120",
        "GDAL_HTTP_MAX_RETRY": "10",
        "GDAL_HTTP_RETRY_DELAY": "1",
        "GDAL_HTTP_RETRY_CODES": "429,500,502,503,504",
    }
    if trabajo is not None:
        opciones["CPL_TMPDIR"] = str(trabajo)
    with rasterio.Env(**opciones), ExitStack() as stack:
        srcs = {
            banda: stack.enter_context(rasterio.open(asset.href))
            for banda, asset in granulo.assets.items()
        }
        _validar_grilla_fuente(srcs["vis"], "vis")
        _validar_grilla_fuente(srcs["flag"], "flag", srcs["vis"])
        _validar_grilla_fuente(srcs["samples"], "samples", srcs["vis"])
        _validar_grilla_fuente(srcs["li"], "li", srcs["vis"])
        return {
            aoi.id: _leer_aoi(srcs, granulo, aoi, catalogos[aoi.id])
            for aoi in aois
        }


def _ruta_observacion(base: Path, grupo: GrupoDia, aoi: AOI) -> Path:
    fecha = date.fromisoformat(grupo.fecha_utc)
    return (base / "observaciones" / f"satelite={grupo.satelite}"
            / f"year={fecha.year:04d}" / f"month={fecha.month:02d}"
            / f"day={fecha.day:02d}"
            / f"{grupo.satelite}_{fecha:%Y%m%d}.{aoi.id}.parquet")


def _ruta_estado(base: Path, grupo: GrupoDia) -> Path:
    fecha = date.fromisoformat(grupo.fecha_utc)
    return (base / "_estado" / f"satelite={grupo.satelite}"
            / f"year={fecha.year:04d}" / f"month={fecha.month:02d}"
            / f"{grupo.satelite}_{fecha:%Y%m%d}.json")


def _identidad_fuente(granulo: Granulo) -> str:
    datos = {
        "granule_id": granulo.granule_id,
        "segment_start_utc": granulo.segment_start_utc,
        "item_key": granulo.item_key,
        "bbox": granulo.bbox,
        "assets": {k: asdict(v) for k, v in sorted(granulo.assets.items())},
    }
    return hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()


def _identidad_grupo(grupo: GrupoDia) -> str:
    identidades = [
        {"granule_id": g.granule_id, "sha256": _identidad_fuente(g)}
        for g in grupo.granulos
    ]
    return hashlib.sha256(json.dumps(identidades, sort_keys=True).encode()).hexdigest()


def _verificar_fuentes_sin_cambio(s3, grupo: GrupoDia) -> bool:
    """HEAD posterior: impide publicar si un COG cambió desde el inventario."""
    if s3 is None:  # Sólo para pruebas locales sin red; main siempre entrega S3.
        return False
    for granulo in grupo.granulos:
        for banda, esperado in sorted(granulo.assets.items()):
            actual = _metadata_asset(s3, banda, esperado.key)
            if actual != esperado:
                raise RuntimeError(
                    f"{granulo.granule_id} {banda}: fuente cambio despues "
                    "del inventario; no se publicara el dia"
                )
    return True


def _columnas_obs(con_lunar: bool) -> list[str]:
    return (OBS_BASE_COLUMNAS[:4]
            + (["lunar_illuminance_lux"] if con_lunar else [])
            + OBS_BASE_COLUMNAS[4:])


def _validar_observaciones(path: Path, catalogo: pd.DataFrame,
                           grupo: GrupoDia, aoi: AOI,
                           *, con_lunar: bool,
                           esperado: pd.DataFrame | None = None) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if list(df.columns) != _columnas_obs(con_lunar) or df.empty:
        raise ValueError(f"{path}: esquema/observaciones vacias")
    df = df.sort_values(["orbit_id", "pixel_id"]).reset_index(drop=True)
    ids_catalogo = catalogo.pixel_id.to_numpy(dtype="int64")
    ids_obs = df.pixel_id.to_numpy(dtype="int64")
    posiciones = np.searchsorted(ids_catalogo, ids_obs)
    dentro = posiciones < len(ids_catalogo)
    pertenecen = np.zeros(len(ids_obs), dtype=bool)
    pertenecen[dentro] = ids_catalogo[posiciones[dentro]] == ids_obs[dentro]
    if df.duplicated(["orbit_id", "pixel_id"]).any() or not pertenecen.all():
        raise ValueError(f"{path}: orbit_id+pixel_id duplicado o fuera del catalogo")
    vis = pd.to_numeric(df.vis_dn, errors="raise")
    flags = pd.to_numeric(df.qa_flag, errors="raise")
    samples = pd.to_numeric(df.sample_position, errors="raise")
    if not vis.between(0, 63).all():
        raise ValueError(f"{path}: vis_dn fuera de 0..63")
    if ((flags.astype("uint16") & FLAG_NO_DATA) != 0).any():
        raise ValueError(f"{path}: contiene filas marcadas no_data")
    presentes_samples = samples.notna()
    if not samples[presentes_samples].between(1, 1465).all():
        raise ValueError(f"{path}: sample_position presente fuera de 1..1465")
    if con_lunar:
        lunar = pd.to_numeric(df.lunar_illuminance_lux, errors="raise")
        presentes = lunar.notna()
        if not np.isfinite(lunar[presentes]).all() or (lunar[presentes] < 0).any():
            raise ValueError(f"{path}: iluminancia lunar invalida")
    tiempos_esperados = {
        granulo.granule_id: pd.Timestamp(granulo.segment_start_utc)
        for granulo in grupo.granulos
    }
    if not df.orbit_id.isin(tiempos_esperados).all():
        raise ValueError(f"{path}: orbit_id no pertenece al dia-satelite")
    tiempos = pd.to_datetime(df.segment_start_utc, utc=True, errors="raise")
    esperados = df.orbit_id.map(tiempos_esperados)
    if not tiempos.eq(esperados).all():
        raise ValueError(f"{path}: tiempo de inicio de orbita inconsistente")
    if not (df.satelite.eq(grupo.satelite).all()
            and df.aoi_id.eq(aoi.id).all()
            and df.time_is_pixel_specific.eq(False).all()
            and df.time_reference.eq(
                "orbit_segment_start_utc_not_pixel_time").all()):
        raise ValueError(f"{path}: identidad/semantica temporal inconsistente")
    if esperado is not None:
        esperado = esperado.sort_values(["orbit_id", "pixel_id"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(df, esperado, check_dtype=False, check_exact=True)
    return df


def _relativa_segura(base: Path, path: Path) -> str:
    base_r, path_r = base.resolve(), path.resolve()
    if base_r != path_r and base_r not in path_r.parents:
        raise ValueError("salida fuera de la carpeta LEN DMSP")
    return str(path_r.relative_to(base_r))


def _estado_valido(path: Path, base: Path, grupo: GrupoDia,
                   aois: tuple[AOI, ...], catalogos: dict[str, pd.DataFrame],
                   mascara_sha: str) -> bool:
    try:
        datos = json.loads(path.read_text(encoding="utf-8"))
        if (datos.get("schema") != ESTADO_SCHEMA
                or datos.get("processor_version") != PROCESSOR_VERSION
                or datos.get("processor_sha256") != PROCESSOR_SHA256
                or datos.get("satelite") != grupo.satelite
                or datos.get("fecha_utc") != grupo.fecha_utc
                or datos.get("source_identity_sha256") != _identidad_grupo(grupo)
                or datos.get("mascara_sha256") != mascara_sha
                or datos.get("grid_fingerprint") != _grid_fingerprint()
                or set(datos.get("aois", {})) != {a.id for a in aois}):
            return False
        base_r = base.resolve()
        for aoi in aois:
            registro = datos["aois"][aoi.id]
            if registro.get("estado") not in {"archivo", "sin_datos", "fuera_bbox"}:
                return False
            if registro["estado"] != "archivo":
                if _ruta_observacion(base, grupo, aoi).exists():
                    return False
                continue
            if registro.get("con_lunar") is not True:
                return False
            salida = (base / str(registro["salida"])).resolve()
            if base_r not in salida.parents or not salida.is_file():
                return False
            if (salida.stat().st_size != int(registro["bytes"])
                    or sha256(salida) != registro["sha256"]):
                return False
            _validar_observaciones(
                salida, catalogos[aoi.id], grupo, aoi,
                con_lunar=bool(registro.get("con_lunar")),
            )
        return True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            AssertionError):
        return False


def _mover_commit(origen: Path, destino: Path) -> None:
    """Punto único de rename para probar rollback del commit multi-AOI."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    os.replace(origen, destino)


def _commit_dia_atomico(base: Path, grupo: GrupoDia, aois: tuple[AOI, ...],
                        staged: dict[str, Path], estado_datos: dict,
                        catalogos: dict[str, pd.DataFrame], mascara_sha: str,
                        transaccion: Path) -> Path:
    """Publica las cinco AOI como una transacción con rollback completo.

    Los Parquet se escribieron y validaron previamente en ``transaccion``. Se
    respaldan las salidas anteriores, se mueven las nuevas y el estado durable
    se publica al final como marcador de commit. Cualquier fallo restaura el
    conjunto anterior y retira todos los Parquet nuevos ya movidos.
    """
    finales = {aoi.id: _ruta_observacion(base, grupo, aoi) for aoi in aois}
    estado_path = _ruta_estado(base, grupo)
    estado_original_existia = estado_path.exists()
    respaldos_dir = transaccion / "respaldos"
    respaldos_dir.mkdir(parents=True, exist_ok=True)
    respaldos: dict[Path, Path] = {}
    nuevos_publicados: list[Path] = []
    estado_retirado = False
    estado_nuevo = False
    try:
        for aoi in aois:
            final = finales[aoi.id]
            if final.exists():
                respaldo = respaldos_dir / f"{aoi.id}.parquet"
                _mover_commit(final, respaldo)
                respaldos[final] = respaldo
        if estado_path.exists():
            respaldo_estado = respaldos_dir / "estado.json"
            _mover_commit(estado_path, respaldo_estado)
            respaldos[estado_path] = respaldo_estado
            estado_retirado = True
        for aoi in aois:
            origen = staged.get(aoi.id)
            if origen is None:
                continue
            final = finales[aoi.id]
            _mover_commit(origen, final)
            nuevos_publicados.append(final)
        _guardar_json_atomico(estado_path, estado_datos)
        estado_nuevo = True
        if not _estado_valido(
                estado_path, base, grupo, aois, catalogos, mascara_sha):
            raise ValueError("estado diario no valida despues del commit")
        return estado_path
    except BaseException as exc:
        errores_rollback = []
        if estado_nuevo or estado_retirado or not estado_original_existia:
            try:
                estado_path.unlink(missing_ok=True)
            except OSError as rollback_exc:
                errores_rollback.append(rollback_exc)
        for final in reversed(nuevos_publicados):
            try:
                final.unlink(missing_ok=True)
            except OSError as rollback_exc:
                errores_rollback.append(rollback_exc)
        for final, respaldo in reversed(list(respaldos.items())):
            if not respaldo.exists():
                continue
            try:
                _mover_commit(respaldo, final)
            except OSError as rollback_exc:
                errores_rollback.append(rollback_exc)
        if errores_rollback:
            raise RuntimeError(
                "fallo el commit diario y su rollback no pudo restaurar todo: "
                + "; ".join(str(x) for x in errores_rollback)
            ) from exc
        raise


def _procesar_grupo_dia(base: Path, grupo: GrupoDia, aois: tuple[AOI, ...],
                        catalogos: dict[str, pd.DataFrame], mascara_sha: str,
                        mani: Manifiesto, trabajo: Path, s3=None) -> None:
    # Primero se leen y validan todas las orbitas anunciadas del dia. Si una
    # falla, no se publica un Parquet diario parcial.
    acumulados: dict[str, list[pd.DataFrame]] = {a.id: [] for a in aois}
    estadisticas: dict[str, dict[str, dict]] = {a.id: {} for a in aois}
    for granulo in grupo.granulos:
        resultados = _extraer_granulo(granulo, aois, catalogos, trabajo)
        for aoi in aois:
            obs, stats = resultados[aoi.id]
            estadisticas[aoi.id][granulo.granule_id] = stats
            if obs is not None:
                acumulados[aoi.id].append(obs)
    fuentes_revalidadas = _verificar_fuentes_sin_cambio(s3, grupo)
    estado_aois = {}
    eventos = []
    fuentes = {
        granulo.granule_id: {
            "segment_start_utc": granulo.segment_start_utc,
            "item_key": granulo.item_key,
            "assets": {k: asdict(v) for k, v in sorted(granulo.assets.items())},
        }
        for granulo in grupo.granulos
    }
    trabajo.mkdir(parents=True, exist_ok=True)
    prefijo = f"{grupo.satelite}_{grupo.fecha_utc.replace('-', '')}."
    with tempfile.TemporaryDirectory(prefix=prefijo, dir=trabajo) as tmp:
        transaccion = Path(tmp)
        staged = {}
        for aoi in aois:
            partes = acumulados[aoi.id]
            stats = estadisticas[aoi.id]
            if not partes:
                estado_sin_archivo = (
                    "sin_datos" if any(
                        x["estado"] == "sin_datos" for x in stats.values())
                    else "fuera_bbox"
                )
                estado_aois[aoi.id] = {
                    "estado": estado_sin_archivo, "filas": 0,
                    "estadisticas_por_orbita": stats,
                }
                eventos.append({
                    "evento": "aoi_dia_sin_observaciones",
                    "satelite": grupo.satelite,
                    "fecha_utc": grupo.fecha_utc,
                    "orbitas": [x.granule_id for x in grupo.granulos],
                    "tiempo_especifico_por_pixel": False,
                    "aoi_id": aoi.id,
                    "estado": estado_sin_archivo,
                    "estadisticas_por_orbita": stats,
                    "fuentes": fuentes,
                })
                continue
            if any("lunar_illuminance_lux" not in parte.columns for parte in partes):
                raise ValueError(f"{aoi.id}: una orbita carece de LI obligatoria")
            obs = pd.concat(partes, ignore_index=True, sort=False)
            obs = obs.reindex(columns=_columnas_obs(True)).sort_values(
                ["orbit_id", "pixel_id"]).reset_index(drop=True)
            salida_stage = transaccion / f"{aoi.id}.parquet"
            _publicar_parquet(obs, salida_stage)
            validado = _validar_observaciones(
                salida_stage, catalogos[aoi.id], grupo, aoi,
                con_lunar=True, esperado=obs,
            )
            staged[aoi.id] = salida_stage
            salida_final = _ruta_observacion(base, grupo, aoi)
            salida_sha = sha256(salida_stage)
            estado_aois[aoi.id] = {
                "estado": "archivo",
                "filas": len(validado),
                "salida": _relativa_segura(base, salida_final),
                "bytes": salida_stage.stat().st_size,
                "sha256": salida_sha,
                "con_lunar": True,
                "estadisticas_por_orbita": stats,
            }
            eventos.append({
                "evento": "archivo_validado",
                "version": VERSION,
                "processor_version": PROCESSOR_VERSION,
                "processor_sha256": PROCESSOR_SHA256,
                "satelite": grupo.satelite,
                "fecha_utc": grupo.fecha_utc,
                "orbitas": [x.granule_id for x in grupo.granulos],
                "segment_start_utc_por_orbita": {
                    x.granule_id: x.segment_start_utc for x in grupo.granulos
                },
                "precision_temporal_fuente": "minuto",
                "tiempo_especifico_por_pixel": False,
                "semantica_temporal": (
                    "inicio UTC del segmento orbital; no hora por pixel"),
                "aoi_id": aoi.id,
                "territorio": aoi.territorio,
                "bbox": aoi.bbox,
                "resolucion_nativa": (
                    "malla OIS 30 arc-sec sin remuestreo; GSD smooth ~2,7 km; "
                    "resolucion nocturna efectiva/IFOV ~4,9 km"),
                "qa": {
                    "campo": "qa_flag", "bits": QA_BITS,
                    "solo_se_excluye": "bit 15 no_data o vis fuera de 0..63",
                    "conservado_sin_filtrar": "nubes, dia, glare, margen y otros bits",
                },
                "variables_conservadas": list(validado.columns),
                "pixeles_source_nonfill": len(validado),
                "salida": str(salida_final),
                "bytes_salida": salida_stage.stat().st_size,
                "sha256_salida": salida_sha,
                "fuentes": fuentes,
                "source_identity_sha256": _identidad_grupo(grupo),
                "integridad_fuente": (
                    "HEAD posterior coincide con inventario"
                    if fuentes_revalidadas else "omitido sólo en prueba local"),
                "lectura": (
                    "ventanas COG remotas por HTTP range; crudo global no descargado"),
                "crudo_global_guardado": False,
                "mascara_sha256": mascara_sha,
                "estadisticas_por_orbita": stats,
            })
        estado_datos = {
            "schema": ESTADO_SCHEMA,
            "producto": PRODUCTO,
            "processor_version": PROCESSOR_VERSION,
            "processor_sha256": PROCESSOR_SHA256,
            "satelite": grupo.satelite,
            "fecha_utc": grupo.fecha_utc,
            "orbitas": [x.granule_id for x in grupo.granulos],
            "segment_start_utc_por_orbita": {
                x.granule_id: x.segment_start_utc for x in grupo.granulos
            },
            "tiempo_especifico_por_pixel": False,
            "source_identity_sha256": _identidad_grupo(grupo),
            "fuentes": fuentes,
            "mascara_sha256": mascara_sha,
            "grid_fingerprint": _grid_fingerprint(),
            "aois": estado_aois,
        }
        estado_path = _commit_dia_atomico(
            base, grupo, aois, staged, estado_datos, catalogos, mascara_sha,
            transaccion,
        )
    for evento in eventos:
        mani.registrar(evento)
    mani.registrar({
        "evento": "dia_satelite_validado",
        "satelite": grupo.satelite,
        "fecha_utc": grupo.fecha_utc,
        "orbitas": [x.granule_id for x in grupo.granulos],
        "estado": str(estado_path),
        "sha256_estado": sha256(estado_path),
        "filas": sum(int(x["filas"]) for x in estado_aois.values()),
        "crudo_global_guardado": False,
        "limitacion_transferencia_cog": (
            "GDAL puede transferir bloques comprimidos que cubren la ventana "
            "rectangular de cada AOI; nunca guarda el raster global"),
    })


def _limpiar_parts(base: Path, mani: Manifiesto | None = None) -> int:
    eliminados = 0
    if not base.exists():
        return eliminados
    for patron in ("*.part", "*.tmp", "*.download"):
        for path in base.rglob(patron):
            if path.is_file():
                path.unlink(missing_ok=True)
                eliminados += 1
                if mani is not None:
                    mani.registrar({"evento": "temporal_incompleto_eliminado",
                                    "ruta": str(path)})
    return eliminados


def _exigir_reserva(path: Path, minimo_gib: float, *, granule_id: str) -> float:
    libres = shutil.disk_usage(path).free / 2**30
    if libres < minimo_gib:
        raise ReservaEspacioError(
            f"quedan {libres:.1f} GiB; se exigen {minimo_gib:.1f} GiB "
            f"antes de {granule_id}"
        )
    return libres


def _inventario_path(base: Path, inicio: date, fin: date,
                     limite: int | None) -> Path:
    sufijo = "completo" if limite is None else f"limite{limite:06d}"
    return (base / "_inventarios"
            / f"inventario_{inicio:%Y%m%d}_{fin:%Y%m%d}_{sufijo}.json")


def _plan(args, rango, aois: tuple[AOI, ...]) -> dict:
    return {
        "producto": PRODUCTO,
        "fuente": "World Bank Light Every Night / NOAA DMSP-OLS",
        "bucket_publico": f"s3://{BUCKET}",
        "stac": STAC_URL,
        "autenticacion": "ninguna; S3 anonimo",
        "rango_efectivo": ([x.isoformat() for x in rango] if rango else None),
        "segmentos": "todas las pasadas/orbit-segments nocturnas; todos los satelites",
        "tiempo": "UTC de inicio del segmento, precision minuto; no es hora por pixel",
        "agregacion_temporal": "ninguna; no se crea mensual ni horario",
        "resolucion": ("malla OIS publicada 30 arc-sec, sin remuestreo; "
                       "GSD/smooth ~2,7 km; resolucion nocturna efectiva/IFOV "
                       "~4,9 km"),
        "variables": ["vis_dn", "qa_flag", "sample_position",
                      "lunar_illuminance_lux obligatoria"],
        "qa": ("se conserva qa_flag crudo; no se filtran nubes, dia, glare "
               "ni margen durante la descarga"),
        "aois": [asdict(aoi) for aoi in aois],
        "antimeridiano": "admite longitudes -180..180 y 0..360",
        "crudo_global_guardado": False,
        "limitacion_transferencia_cog": (
            "GDAL puede transferir bloques comprimidos que cubren la ventana "
            "rectangular de cada AOI; no se guarda el raster global"),
        "min_gib_libres": args.min_gb_libres,
        "limite_smoke": args.limite,
        "estimacion_salida_final_gib": "65-85",
        "concurrencia_black_marble": "no ejecutar simultaneamente",
        "ausencias_fuente_sin_otro_satelite": list(AUSENCIAS_SIN_OTRO_SATELITE),
        "dry_run_sin_red_y_sin_escritura": True,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desde", default=FECHA_INICIO.isoformat())
    ap.add_argument("--hasta", default=FECHA_FIN.isoformat())
    ap.add_argument("--aoi", default="todos")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--solo-inventario", action="store_true",
                    help="guarda el inventario STAC/S3; no lee COG ni publica pixeles")
    ap.add_argument("--refrescar-inventario", action="store_true")
    ap.add_argument("--limite", type=int,
                    help="maximo de segmentos relevantes; solo para smoke controlado")
    ap.add_argument("--workers-inventario", type=int, default=16,
                    help="concurrencia de lecturas JSON STAC (no descarga COG)")
    ap.add_argument("--min-gb-libres", type=float,
                    default=float(os.environ.get("MIN_GB_LIBRES", "100")))
    ap.add_argument("--dry-run", action="store_true",
                    help="muestra el plan sin red ni escritura")
    args = ap.parse_args(argv)
    try:
        rango = _rango(args.desde, args.hasta)
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except ValueError as exc:
        ap.error(str(exc))
    if len(aois) != 5:
        ap.error("la descarga reproducible LEN DMSP exige las cinco AOI de Chile")
    if args.limite is not None and args.limite < 1:
        ap.error("--limite debe ser positivo")
    if args.workers_inventario < 1:
        ap.error("--workers-inventario debe ser positivo")
    if not math.isfinite(args.min_gb_libres) or args.min_gb_libres < 0:
        ap.error("--min-gb-libres debe ser finito y no negativo")
    if args.dry_run:
        print(json.dumps(_plan(args, rango, aois), ensure_ascii=False, indent=2))
        return 0
    if rango is None:
        log.info("El rango no intersecta DMSP LEN 2000-01-01--2012-01-18")
        return 0
    if not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")

    inicio, fin = rango
    base = ensure_dir(CONTAMINANTES / "Nightlights" / "DMSP_OLS_LEN_Nightly")
    trabajo = base / "_trabajo"
    mascara_sha = sha256_conjunto_shapefile(args.comunas)
    mani = Manifiesto(base / "_manifiestos", PRODUCTO, {
        "bucket": BUCKET,
        "region": REGION,
        "stac": STAC_URL,
        "documentacion": DOCUMENTACION_URL,
        "registro_aws": REGISTRY_URL,
        "desde": inicio.isoformat(),
        "hasta": fin.isoformat(),
        "limite_smoke": args.limite,
        "resolucion": ("malla OIS publicada 30 arc-sec; GSD/smooth ~2,7 km; "
                       "resolucion nocturna efectiva/IFOV ~4,9 km"),
        "temporal": "segment_start_utc minute precision; not per-pixel time",
        "sin_agregacion_mensual": True,
        "sin_hora_inventada": True,
        "aoi": [asdict(aoi) for aoi in aois],
        "antartica": False,
        "mascara_sha256": mascara_sha,
        "unidades_administrativas": resumen_mascara(args.comunas),
        "min_gib_libres": args.min_gb_libres,
        "estimacion_salida_final_gib": "65-85",
        "concurrencia_black_marble": "no ejecutar simultaneamente",
        "processor_version": PROCESSOR_VERSION,
        "processor_sha256": PROCESSOR_SHA256,
        "crudo_global_guardado": False,
        "ausencias_fuente_sin_otro_satelite": list(AUSENCIAS_SIN_OTRO_SATELITE),
    })
    s3 = None
    try:
        s3 = cliente_s3()
        with BloqueoProceso(base / ".descargar_len.lock"), AreaTrabajo(trabajo):
            _limpiar_parts(base, mani)
            _exigir_reserva(base, args.min_gb_libres, granule_id="inventario")
            inventario_path = _inventario_path(base, inicio, fin, args.limite)
            granulos = auditoria_catalogos = None
            if inventario_path.exists() and not args.refrescar_inventario:
                try:
                    granulos, auditoria_catalogos = _leer_inventario(
                        inventario_path, inicio=inicio, fin=fin, aois=aois,
                        mascara_sha=mascara_sha, limite=args.limite)
                except (OSError, ValueError, TypeError, KeyError,
                        json.JSONDecodeError) as exc:
                    mani.registrar({"evento": "inventario_cache_invalido",
                                    "ruta": str(inventario_path),
                                    "error": f"{type(exc).__name__}: {exc}"})
            if granulos is None:
                granulos, auditoria_catalogos = inventariar(
                    s3, inicio=inicio, fin=fin, aois=aois,
                    limite=args.limite, workers=args.workers_inventario)
                _guardar_inventario(
                    inventario_path, granulos, inicio=inicio, fin=fin,
                    aois=aois, mascara_sha=mascara_sha, limite=args.limite,
                    auditoria_catalogos=auditoria_catalogos)
            mani.registrar({
                "evento": "inventario_validado",
                "ruta": str(inventario_path),
                "sha256": sha256(inventario_path),
                "segmentos": len(granulos),
                "satelites": sorted({x.satelite for x in granulos}),
                "inventario_completo": args.limite is None,
                "catalogos": auditoria_catalogos,
                "acceso": "S3 publico anonimo",
            })
            if args.solo_inventario:
                mani.terminar(
                              "completo" if args.limite is None
                              else "inventario_limitado",
                              segmentos=len(granulos),
                              solo_inventario=True)
                print(f"Inventario LEN guardado: {inventario_path} ({len(granulos)} segmentos)")
                return 0

            comunas = _geometrias(args.comunas)
            catalogos = _cargar_o_publicar_catalogos(
                base, aois, comunas, args.comunas, mascara_sha)
            enlaces = _publicar_enlaces(base, catalogos, args.comunas, mascara_sha)
            mani.registrar({"evento": "catalogo_y_enlaces_validados", **enlaces})
            grupos = _agrupar_dias(granulos)
            procesados = omitidos = fallos = 0
            for indice, grupo in enumerate(grupos, 1):
                estado = _ruta_estado(base, grupo)
                if estado.exists() and _estado_valido(
                        estado, base, grupo, aois, catalogos, mascara_sha):
                    omitidos += 1
                    mani.registrar({"evento": "dia_satelite_ya_validado",
                                    "satelite": grupo.satelite,
                                    "fecha_utc": grupo.fecha_utc,
                                    "orbitas": len(grupo.granulos),
                                    "estado": str(estado)})
                    continue
                try:
                    _exigir_reserva(
                        base, args.min_gb_libres,
                        granule_id=f"{grupo.satelite}_{grupo.fecha_utc}")
                    _procesar_grupo_dia(
                        base, grupo, aois, catalogos, mascara_sha, mani, trabajo,
                        s3=s3)
                    procesados += 1
                    log.info("LEN DMSP %d/%d validado: %s %s (%d orbitas)",
                             indice, len(grupos), grupo.satelite, grupo.fecha_utc,
                             len(grupo.granulos))
                except ReservaEspacioError:
                    raise
                except Exception as exc:
                    fallos += 1
                    mani.registrar({
                        "evento": "dia_satelite_fallido",
                        "satelite": grupo.satelite,
                        "fecha_utc": grupo.fecha_utc,
                        "orbitas": [x.granule_id for x in grupo.granulos],
                        "error": f"{type(exc).__name__}: {exc}",
                        "crudo_global_guardado": False,
                    })
                    log.warning("LEN DMSP %s %s fallo: %s", grupo.satelite,
                                grupo.fecha_utc, exc)
            _limpiar_parts(base, mani)
            estado_final = (
                "smoke_limitado" if args.limite is not None
                else ("completo" if not fallos else "con_fallos")
            )
            mani.terminar(
                estado_final, segmentos_inventario=len(granulos),
                dias_satelite=len(grupos), procesados=procesados,
                omitidos=omitidos, fallos=fallos)
            return 0 if not fallos else 1
    except ReservaEspacioError as exc:
        mani.registrar({"evento": "reserva_espacio_alcanzada", "motivo": str(exc)})
        mani.terminar("abortado_espacio")
        raise SystemExit(str(exc)) from None
    except (KeyboardInterrupt, SystemExit):
        _limpiar_parts(base, mani)
        raise
    except BaseException as exc:
        _limpiar_parts(base, mani)
        mani.registrar({"evento": "fallo_fatal",
                        "error": f"{type(exc).__name__}: {exc}"})
        mani.terminar("fallo")
        raise
    finally:
        cerrar_s3 = getattr(s3, "close", None)
        if cerrar_s3:
            cerrar_s3()


if __name__ == "__main__":
    raise SystemExit(main())
