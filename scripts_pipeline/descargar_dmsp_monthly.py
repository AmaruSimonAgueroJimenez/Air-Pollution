#!/usr/bin/env python3
"""Descarga EOG DMSP-OLS Monthly Series y publica sólo píxeles de Chile.

Este descargador cubre la brecha pre-VIIRS del proyecto (2000-01--2011-12)
con la máxima resolución publicada por EOG para la serie mensual: grilla
global nativa de 30 arc-sec y un compuesto por satélite/mes. Conserva
``avg_vis`` (DN), ``cf_cvg`` y ``cvg`` sin remuestreo ni promedio comunal. No
crea una hora: el producto es mensual y no contiene tiempo intradiario.

El acceso programático oficial usa OAuth2. El programa acepta exclusivamente
variables de entorno: ``EOG_ACCESS_TOKEN``; o ``EOG_CLIENT_ID``,
``EOG_CLIENT_SECRET``, ``EOG_USERNAME`` y ``EOG_PASSWORD``. Los secretos no se
escriben en argumentos, URL, logs, inventarios ni manifiestos.

Flujo transaccional por satélite/mes:

1. inventario autenticado del directorio oficial;
2. descarga temporal de los tres GeoTIFF globales;
3. selección de toda celda nativa cuya huella toca una comuna de Chile en
   cinco AOI separadas (sin corredor oceánico ni Antártica);
4. publicación y reapertura de Parquet ZSTD pixel-level;
5. catálogo espacial y enlace muchos-a-muchos píxel-comuna;
6. borrado de los GeoTIFF globales sólo después de validar todo lo anterior.
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
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _chile_aoi import AOI, resumen_mascara, seleccionar  # noqa: E402
from _common import CONTAMINANTES, DATA, ensure_dir, get_logger, load_env  # noqa: E402
from _manifiesto_satelital import (  # noqa: E402
    Manifiesto, sha256, sha256_conjunto_shapefile,
)

log = get_logger("dmsp_monthly")

PRODUCTO = "EOG_DMSP_OLS_MONTHLY"
VERSION = "EOG DMSP-OLS Monthly Series"
PRODUCT_PAGE = "https://eogdata.mines.edu/products/dmsp/"
BASE_URL = "https://eogdata.mines.edu/wwwdata/dmsp/monthly_composites/"
TOKEN_URL = (
    "https://eogauth.mines.edu/realms/eog/protocol/openid-connect/token"
)
REGISTRATION_URL = "https://eogdata.mines.edu/products/register/"
RESOLUCION = 1.0 / 120.0
PERIODO_INICIO_PROYECTO = "2000-01"
PERIODO_FIN_PROYECTO = "2011-12"
VARIABLES = ("avg_vis", "cf_cvg", "cvg")
SATELITES = {"F10", "F12", "F14", "F15", "F16", "F18"}
INVENTARIO_SCHEMA = "airpollution.eog-dmsp-monthly-inventory.v1"
CATALOGO_SCHEMA = "airpollution.eog-dmsp-pixel-catalog.v1"


class CredencialesEOGError(RuntimeError):
    """Acceso programático no configurado o no autorizado."""


@dataclass(frozen=True)
class ItemInventario:
    satelite: str
    periodo: str
    variable: str
    url: str
    nombre: str


@dataclass(frozen=True)
class GrupoInventario:
    satelite: str
    periodo: str
    items: dict[str, ItemInventario]


@dataclass(frozen=True)
class Grilla:
    width: int
    height: int
    transform: tuple[float, ...]
    crs: str
    resolucion_x: float
    resolucion_y: float
    fingerprint: str


class _HrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for clave, valor in attrs:
            if clave.lower() == "href" and valor:
                self.hrefs.append(valor)


def _url_sin_query(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def _url_oficial(url: str, *, directorio: bool = False) -> str:
    """Valida destino antes de adjuntar Authorization."""
    limpia = _url_sin_query(url)
    p = urlsplit(limpia)
    base = urlsplit(BASE_URL)
    if p.scheme != "https" or p.hostname != base.hostname:
        raise ValueError("el inventario contiene una URL fuera de eogdata.mines.edu")
    if not p.path.startswith(base.path):
        raise ValueError("el inventario contiene una ruta fuera de monthly_composites")
    if directorio and not p.path.endswith("/"):
        limpia += "/"
    return limpia


def _es_redireccion_login(respuesta) -> bool:
    p = urlsplit(str(respuesta.url))
    tipo = str(respuesta.headers.get("Content-Type", "")).lower()
    return (
        p.hostname == "eogauth.mines.edu"
        or "/protocol/openid-connect/auth" in p.path
        or ("text/html" in tipo and "login" in p.path.lower())
    )


class ClienteEOG:
    """Cliente OAuth sin persistencia de secretos ni token."""

    def __init__(self):
        import requests

        load_env()
        self.requests = requests
        self.token = os.environ.get("EOG_ACCESS_TOKEN", "").strip() or None
        self.token_directo = self.token is not None
        self.expira_monotonic = math.inf if self.token_directo else 0.0
        self.credenciales = {
            "client_id": os.environ.get("EOG_CLIENT_ID", "").strip(),
            "client_secret": os.environ.get("EOG_CLIENT_SECRET", "").strip(),
            "username": os.environ.get("EOG_USERNAME", "").strip(),
            "password": os.environ.get("EOG_PASSWORD", ""),
            "grant_type": "password",
        }
        if not self.token_directo:
            faltan = [
                env for env, campo in (
                    ("EOG_CLIENT_ID", "client_id"),
                    ("EOG_CLIENT_SECRET", "client_secret"),
                    ("EOG_USERNAME", "username"),
                    ("EOG_PASSWORD", "password"),
                ) if not self.credenciales[campo]
            ]
            if faltan:
                raise CredencialesEOGError(
                    "EOG exige acceso programático OAuth de suscriptor. Define "
                    "EOG_ACCESS_TOKEN o las cuatro variables EOG_CLIENT_ID, "
                    "EOG_CLIENT_SECRET, EOG_USERNAME y EOG_PASSWORD. Faltan: "
                    + ", ".join(faltan)
                    + f". Información oficial: {REGISTRATION_URL}"
                )

    def _renovar(self, *, forzar: bool = False) -> None:
        if self.token_directo:
            if forzar:
                raise CredencialesEOGError(
                    "EOG rechazó EOG_ACCESS_TOKEN; entrega un token vigente o "
                    "configura las cuatro credenciales OAuth para renovación automática"
                )
            return
        if not forzar and self.token and time.monotonic() < self.expira_monotonic - 30:
            return
        try:
            r = self.requests.post(TOKEN_URL, data=self.credenciales, timeout=(20, 60))
        except self.requests.RequestException as exc:
            raise CredencialesEOGError(
                f"no se pudo contactar el servidor OAuth EOG: {type(exc).__name__}"
            ) from exc
        if r.status_code != 200:
            raise CredencialesEOGError(
                f"OAuth EOG rechazó las credenciales (HTTP {r.status_code}); "
                "no se guardó ni mostró la respuesta"
            )
        try:
            cuerpo = r.json()
            token = str(cuerpo["access_token"]).strip()
            expira = max(60, int(cuerpo.get("expires_in", 300)))
        except (KeyError, TypeError, ValueError) as exc:
            raise CredencialesEOGError("OAuth EOG no devolvió un token utilizable") from exc
        if not token:
            raise CredencialesEOGError("OAuth EOG devolvió un token vacío")
        self.token = token
        self.expira_monotonic = time.monotonic() + expira

    def get(self, url: str, *, stream: bool = False):
        url = _url_oficial(url)
        ultimo = None
        for intento in range(2):
            self._renovar(forzar=intento > 0)
            try:
                r = self.requests.get(
                    url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=(30, 180),
                    stream=stream,
                    allow_redirects=True,
                )
            except self.requests.RequestException as exc:
                ultimo = exc
                if intento == 0:
                    time.sleep(2)
                    continue
                raise RuntimeError(
                    f"falló conexión con EOG: {type(exc).__name__}"
                ) from exc
            if r.status_code in {401, 403} or _es_redireccion_login(r):
                r.close()
                if intento == 0:
                    continue
                raise CredencialesEOGError(
                    "EOG no autorizó el recurso mensual; verifica que la cuenta tenga "
                    "suscripción para acceso programático"
                )
            if r.status_code != 200:
                estado = r.status_code
                r.close()
                raise RuntimeError(f"EOG respondió HTTP {estado} para un recurso oficial")
            return r
        raise RuntimeError(f"no se pudo consultar EOG: {ultimo}")

    def descargar(self, url: str, destino: Path) -> dict[str, object]:
        """Descarga atómica; nunca conserva un .part fallido."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        part = destino.with_suffix(destino.suffix + ".part")
        part.unlink(missing_ok=True)
        r = self.get(url, stream=True)
        try:
            tipo = str(r.headers.get("Content-Type", "")).lower()
            if "text/html" in tipo:
                raise CredencialesEOGError(
                    "EOG devolvió HTML en vez de GeoTIFF; la autorización no alcanzó el archivo"
                )
            total = 0
            with part.open("wb") as f:
                for bloque in r.iter_content(chunk_size=8 * 1024 * 1024):
                    if bloque:
                        f.write(bloque)
                        total += len(bloque)
                f.flush()
                os.fsync(f.fileno())
            esperado = r.headers.get("Content-Length")
            if esperado is not None and total != int(esperado):
                raise IOError(f"descarga truncada: {total} de {esperado} bytes")
            if total == 0:
                raise IOError("EOG devolvió un archivo vacío")
            os.replace(part, destino)
            return {
                "bytes": total,
                "etag": str(r.headers.get("ETag", "")).strip('"') or None,
                "last_modified": r.headers.get("Last-Modified"),
            }
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        finally:
            r.close()


def _extraer_enlaces(html: str, directorio: str) -> list[str]:
    parser = _HrefParser()
    parser.feed(html)
    salida = []
    for href in parser.hrefs:
        if href.startswith(("#", "?", "mailto:", "javascript:")):
            continue
        try:
            url = _url_oficial(urljoin(directorio, href))
        except ValueError:
            continue
        salida.append(url)
    return sorted(set(salida))


def _clasificar_url(url: str) -> ItemInventario | None:
    texto = unquote(urlsplit(url).path)
    bajo = texto.lower()
    if not bajo.endswith((".tif", ".tiff")):
        return None
    m = re.search(r"(?P<sat>F\d{2})[^0-9]{0,20}(?P<ym>(?:19|20)\d{4})", texto,
                  flags=re.IGNORECASE)
    if not m:
        # También admite nombres compactos como F15200001_avg_vis.tif.
        m = re.search(r"(?P<sat>F\d{2})(?P<ym>(?:19|20)\d{4})", texto,
                      flags=re.IGNORECASE)
    if not m:
        return None
    satelite = m.group("sat").upper()
    ym = m.group("ym")
    if satelite not in SATELITES or not (1 <= int(ym[4:]) <= 12):
        return None
    if "avg_vis" in bajo:
        variable = "avg_vis"
    elif "cf_cvg" in bajo:
        variable = "cf_cvg"
    elif re.search(r"(^|[._/-])cvg([._/-]|$)", bajo):
        variable = "cvg"
    else:
        return None
    return ItemInventario(
        satelite=satelite,
        periodo=f"{ym[:4]}-{ym[4:]}",
        variable=variable,
        url=_url_oficial(url),
        nombre=Path(urlsplit(url).path).name,
    )


def inventariar(cliente: ClienteEOG, *, max_profundidad: int = 5) -> list[ItemInventario]:
    """Recorre sólo el árbol oficial; sirve con listados planos o anidados."""
    pendientes = [(BASE_URL, 0)]
    vistos: set[str] = set()
    items: dict[tuple[str, str, str], ItemInventario] = {}
    while pendientes:
        directorio, profundidad = pendientes.pop(0)
        directorio = _url_oficial(directorio, directorio=True)
        if directorio in vistos:
            continue
        vistos.add(directorio)
        r = cliente.get(directorio)
        try:
            tipo = str(r.headers.get("Content-Type", "")).lower()
            if "html" not in tipo:
                raise RuntimeError(f"el inventario EOG no es HTML: {tipo or 'sin tipo'}")
            html = r.text
        finally:
            r.close()
        for url in _extraer_enlaces(html, directorio):
            item = _clasificar_url(url)
            if item:
                clave = (item.satelite, item.periodo, item.variable)
                previo = items.get(clave)
                if previo and previo.url != item.url:
                    raise ValueError(f"inventario ambiguo: dos archivos para {clave}")
                items[clave] = item
            elif url.endswith("/") and profundidad < max_profundidad:
                pendientes.append((url, profundidad + 1))
    if not items:
        raise RuntimeError(
            "EOG autorizó el directorio pero no se reconocieron GeoTIFF mensuales; "
            "revisa si cambió la estructura del inventario oficial"
        )
    return sorted(items.values(), key=lambda x: (x.periodo, x.satelite, x.variable))


def _agrupar(items: list[ItemInventario], desde: str, hasta: str) -> list[GrupoInventario]:
    grupos: dict[tuple[str, str], dict[str, ItemInventario]] = {}
    for item in items:
        if desde <= item.periodo <= hasta:
            por_variable = grupos.setdefault((item.satelite, item.periodo), {})
            previo = por_variable.get(item.variable)
            if previo and previo.url != item.url:
                raise ValueError(
                    f"inventario ambiguo: dos archivos para "
                    f"{item.satelite} {item.periodo} {item.variable}"
                )
            por_variable[item.variable] = item
    completos = []
    incompletos = []
    for (sat, periodo), por_variable in sorted(grupos.items(), key=lambda x: (x[0][1], x[0][0])):
        faltan = sorted(set(VARIABLES) - set(por_variable))
        if faltan:
            incompletos.append({"satelite": sat, "periodo": periodo, "faltan": faltan})
        else:
            completos.append(GrupoInventario(sat, periodo, por_variable))
    if incompletos:
        raise ValueError(
            "inventario mensual incompleto; no se fabricarán variables faltantes: "
            + json.dumps(incompletos[:12], ensure_ascii=False)
        )
    return completos


def _guardar_json_atomico(path: Path, datos: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.unlink(missing_ok=True)
    try:
        with part.open("w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(part, path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def _guardar_inventario(path: Path, items: list[ItemInventario]) -> None:
    from datetime import datetime, timezone

    _guardar_json_atomico(path, {
        "schema": INVENTARIO_SCHEMA,
        "consultado_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pagina_producto": PRODUCT_PAGE,
        "endpoint": BASE_URL,
        "autenticacion": "OAuth2 bearer; credenciales no persistidas",
        "items": [asdict(x) for x in items],
    })


def _leer_inventario(path: Path) -> list[ItemInventario]:
    datos = json.loads(path.read_text(encoding="utf-8"))
    if datos.get("schema") != INVENTARIO_SCHEMA:
        raise ValueError(f"{path}: schema de inventario no reconocido")
    items = []
    for fila in datos.get("items", []):
        item = ItemInventario(**fila)
        clasificado = _clasificar_url(item.url)
        if not clasificado or clasificado != item:
            raise ValueError(f"{path}: item de inventario inválido o no oficial")
        items.append(item)
    if not items:
        raise ValueError(f"{path}: inventario vacío")
    return items


def _rango_mensual(desde: str, hasta: str) -> tuple[str, str] | None:
    try:
        d0, d1 = date.fromisoformat(desde), date.fromisoformat(hasta)
    except ValueError as exc:
        raise ValueError("--desde/--hasta deben ser fechas ISO YYYY-MM-DD") from exc
    if d0 > d1:
        raise ValueError("--desde es posterior a --hasta")
    inicio = max(f"{d0.year:04d}-{d0.month:02d}", PERIODO_INICIO_PROYECTO)
    fin = min(f"{d1.year:04d}-{d1.month:02d}", PERIODO_FIN_PROYECTO)
    if inicio > fin:
        return None
    return inicio, fin


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
        raise ValueError("la máscara contiene códigos administrativos negativos")
    return comunas


def _fingerprint_grilla(src) -> Grilla:
    transform = tuple(float(x) for x in src.transform)[:6]
    rx, ry = abs(transform[0]), abs(transform[4])
    datos = {
        "width": int(src.width), "height": int(src.height),
        "transform": transform, "crs": str(src.crs),
        "resolucion_x": rx, "resolucion_y": ry,
    }
    fp = hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()
    return Grilla(**datos, fingerprint=fp)


def _validar_fuentes(paths: dict[str, Path]) -> Grilla:
    import rasterio

    primera = None
    with ExitStack() as stack:
        for variable in VARIABLES:
            path = paths[variable]
            src = stack.enter_context(rasterio.open(path))
            if src.count != 1:
                raise ValueError(f"{path.name}: se esperaba un GeoTIFF monobanda")
            if src.crs is None or src.crs.to_epsg() != 4326:
                raise ValueError(f"{path.name}: CRS no es EPSG:4326")
            b = src.bounds
            tol = RESOLUCION * 1.1
            if not (b.left <= -180 + tol and b.right >= 180 - tol
                    and b.bottom <= -65 + tol and b.top >= 75 - tol):
                raise ValueError(
                    f"{path.name}: cobertura {tuple(b)} no es la grilla global "
                    "oficial 180W–180E, 65S–75N"
                )
            if not np.issubdtype(np.dtype(src.dtypes[0]), np.integer):
                raise ValueError(f"{path.name}: {variable} no es entero")
            grilla = _fingerprint_grilla(src)
            if not (np.isclose(grilla.resolucion_x, RESOLUCION, atol=1e-10)
                    and np.isclose(grilla.resolucion_y, RESOLUCION, atol=1e-10)):
                raise ValueError(
                    f"{path.name}: resolución {grilla.resolucion_x}×"
                    f"{grilla.resolucion_y}, no 30 arc-sec"
                )
            if primera is None:
                primera = grilla
            elif grilla.fingerprint != primera.fingerprint:
                raise ValueError("avg_vis/cf_cvg/cvg no comparten exactamente la grilla")
    assert primera is not None
    return primera


def _window_entera(src, bbox):
    from rasterio.windows import Window, from_bounds

    w = from_bounds(*bbox, transform=src.transform)
    c0, r0 = max(0, math.floor(w.col_off)), max(0, math.floor(w.row_off))
    c1 = min(src.width, math.ceil(w.col_off + w.width))
    r1 = min(src.height, math.ceil(w.row_off + w.height))
    if c1 <= c0 or r1 <= r0:
        raise ValueError("AOI fuera de la grilla fuente")
    return Window(c0, r0, c1 - c0, r1 - r0)


def _a_uint16(datos: np.ndarray, variable: str) -> np.ndarray:
    if not np.issubdtype(datos.dtype, np.integer):
        raise ValueError(f"{variable}: fuente no entera")
    minimo, maximo = int(datos.min()), int(datos.max())
    if minimo < 0 or maximo > np.iinfo("uint16").max:
        raise ValueError(f"{variable}: rango [{minimo}, {maximo}] fuera de uint16")
    if variable == "avg_vis" and maximo > 255:
        raise ValueError(f"avg_vis: DN {maximo} excede el rango DMSP de 8 bits")
    return datos.astype("uint16", copy=False)


def _extraer_aoi(paths: dict[str, Path], grilla: Grilla, aoi: AOI, comunas,
                 satelite: str, periodo: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    import rasterio
    from rasterio.features import rasterize
    from shapely.geometry import box

    with ExitStack() as stack:
        srcs = {v: stack.enter_context(rasterio.open(paths[v])) for v in VARIABLES}
        ref = srcs["avg_vis"]
        window = _window_entera(ref, aoi.bbox)
        transform = ref.window_transform(window)
        shape = (int(window.height), int(window.width))
        sub = comunas[comunas.geometry.intersects(box(*aoi.bbox))]
        formas = [
            (geom, int(cod)) for geom, cod in
            zip(sub.geometry, sub.cod_comuna, strict=False)
            if geom is not None and not geom.is_empty
        ]
        if not formas:
            raise ValueError(f"{aoi.id}: AOI sin geometría administrativa")
        formas.sort(key=lambda x: x[1] == 0)
        toca = rasterize(
            [(geom, 1) for geom, _ in formas], out_shape=shape,
            transform=transform, fill=0, dtype="uint8", all_touched=True,
        ).astype(bool)
        codigos = rasterize(
            formas, out_shape=shape, transform=transform,
            fill=-1, dtype="int32", all_touched=False,
        )
        if not toca.any():
            raise ValueError(f"{aoi.id}: ninguna celda nativa toca Chile")
        filas, columnas = np.where(toca)
        global_fila = filas.astype("int64") + int(window.row_off)
        global_col = columnas.astype("int64") + int(window.col_off)
        pixel_id = global_fila * int(grilla.width) + global_col
        xs, ys = rasterio.transform.xy(transform, filas, columnas, offset="center")
        catalogo = pd.DataFrame({
            "pixel_id": pixel_id.astype("int64"),
            "source_row": global_fila.astype("int32"),
            "source_col": global_col.astype("int32"),
            "lat": np.asarray(ys, dtype="float64"),
            "lon": np.asarray(xs, dtype="float64"),
            "cod_comuna": codigos[filas, columnas].astype("int32"),
            "aoi_id": aoi.id,
            "territorio": aoi.territorio,
            "resolution_degrees": RESOLUCION,
        }).sort_values("pixel_id").reset_index(drop=True)
        observaciones = pd.DataFrame({"pixel_id": pixel_id.astype("int64")})
        for variable in VARIABLES:
            datos = _a_uint16(srcs[variable].read(1, window=window), variable)
            observaciones[variable] = datos[filas, columnas]
        observaciones["satelite"] = satelite
        observaciones["periodo"] = periodo
        observaciones["aoi_id"] = aoi.id
        observaciones = observaciones.sort_values("pixel_id").reset_index(drop=True)
    if catalogo.pixel_id.duplicated().any() or observaciones.pixel_id.duplicated().any():
        raise ValueError(f"{aoi.id}: pixel_id duplicado")
    if not np.array_equal(catalogo.pixel_id.to_numpy(), observaciones.pixel_id.to_numpy()):
        raise ValueError(f"{aoi.id}: observaciones y catálogo no coinciden")
    return catalogo, observaciones


def _publicar_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.unlink(missing_ok=True)
    try:
        df.to_parquet(part, index=False, compression="zstd")
        leido = pd.read_parquet(part)
        if len(leido) != len(df) or list(leido.columns) != list(df.columns):
            raise ValueError(f"{path}: validación Parquet falló")
        os.replace(part, path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def _validar_catalogo(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    requeridas = {
        "pixel_id", "source_row", "source_col", "lat", "lon", "cod_comuna",
        "aoi_id", "territorio", "resolution_degrees",
    }
    if requeridas - set(df.columns) or df.empty or df.pixel_id.duplicated().any():
        raise ValueError(f"{path}: catálogo espacial inválido")
    if not np.isfinite(df[["lat", "lon"]].to_numpy()).all():
        raise ValueError(f"{path}: coordenadas no finitas")
    if not np.allclose(df.resolution_degrees, RESOLUCION):
        raise ValueError(f"{path}: resolución declarada no nativa")
    return df.sort_values("pixel_id").reset_index(drop=True)


def _validar_observaciones(path: Path, catalogo: pd.DataFrame,
                           satelite: str, periodo: str, aoi: AOI,
                           esperado: pd.DataFrame | None = None) -> int:
    df = pd.read_parquet(path)
    columnas = ["pixel_id", *VARIABLES, "satelite", "periodo", "aoi_id"]
    if list(df.columns) != columnas or len(df) != len(catalogo):
        raise ValueError(f"{path}: esquema o número de píxeles inválido")
    df = df.sort_values("pixel_id").reset_index(drop=True)
    if df.pixel_id.duplicated().any() or not np.array_equal(
            df.pixel_id.to_numpy(), catalogo.pixel_id.to_numpy()):
        raise ValueError(f"{path}: pixel_id no coincide con catálogo")
    if not (df.satelite.eq(satelite).all() and df.periodo.eq(periodo).all()
            and df.aoi_id.eq(aoi.id).all()):
        raise ValueError(f"{path}: identidad temporal/espacial inconsistente")
    for variable in VARIABLES:
        valores = pd.to_numeric(df[variable], errors="raise")
        if (valores < 0).any() or (valores > 65535).any():
            raise ValueError(f"{path}: {variable} fuera de rango")
    if esperado is not None:
        esperado = esperado.sort_values("pixel_id").reset_index(drop=True)
        if not df.equals(esperado):
            raise ValueError(f"{path}: valores cambiaron al publicar")
    return len(df)


def _ruta_observacion(base: Path, grupo: GrupoInventario, aoi: AOI) -> Path:
    anio, mes = grupo.periodo.split("-")
    return (base / "observaciones" / f"satelite={grupo.satelite}" /
            f"year={anio}" / f"month={mes}" / f"{aoi.id}.parquet")


def _catalogos_existentes(base: Path, aois: tuple[AOI, ...], grilla: Grilla | None,
                           mascara_sha: str) -> dict[str, pd.DataFrame] | None:
    meta_path = base / "catalogo_pixeles" / "metadata.json"
    paths = {a.id: base / "catalogo_pixeles" / f"{a.id}.parquet" for a in aois}
    if not meta_path.exists() and not any(p.exists() for p in paths.values()):
        return None
    if not meta_path.exists() or not all(p.exists() for p in paths.values()):
        raise ValueError("catálogo DMSP incompleto; no se mezclará con observaciones")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("schema") != CATALOGO_SCHEMA or meta.get("mascara_sha256") != mascara_sha:
        raise ValueError("catálogo DMSP usa otra versión de la máscara comunal")
    if grilla is not None and meta.get("grid_fingerprint") != grilla.fingerprint:
        raise ValueError("catálogo DMSP usa otra grilla fuente")
    return {a.id: _validar_catalogo(paths[a.id]) for a in aois}


def _publicar_catalogos(base: Path, catalogos: dict[str, pd.DataFrame],
                        grilla: Grilla, mascara_sha: str, comunas_path: Path) -> None:
    carpeta = base / "catalogo_pixeles"
    for aoi_id, df in catalogos.items():
        path = carpeta / f"{aoi_id}.parquet"
        _publicar_parquet(df, path)
        _validar_catalogo(path)
    _guardar_json_atomico(carpeta / "metadata.json", {
        "schema": CATALOGO_SCHEMA,
        "producto": PRODUCTO,
        "grid_fingerprint": grilla.fingerprint,
        "grilla": asdict(grilla),
        "mascara": str(comunas_path),
        "mascara_sha256": mascara_sha,
        "pixel_id": "source_row * source_width + source_col",
        "seleccion": "native cell footprint touches Chile; all_touched=True",
        "cod_comuna": "centro de celda; -1 si sólo la huella toca Chile; 0 se conserva",
        "sin_remuestreo": True,
    })


def _publicar_enlaces(base: Path, catalogos: dict[str, pd.DataFrame],
                       comunas_path: Path, mascara_sha: str) -> dict[str, int]:
    """Materializa una sola vez el vínculo de huellas con todas las comunas."""
    from crear_enlaces_pixeles import construir_enlace, enlazar_estaciones

    carpeta = base / "enlaces_geoespaciales"
    enlace_path = carpeta / "pixel_comuna.parquet"
    estaciones_path = carpeta / "estacion_pixel.parquet"
    excluidas_path = carpeta / "estaciones_excluidas.parquet"
    meta_path = carpeta / "metadata.json"
    if enlace_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        enlace = pd.read_parquet(enlace_path)
        if (meta.get("mascara_sha256") == mascara_sha and not enlace.empty
                and not enlace.duplicated(["pixel_id", "cod_comuna"]).any()):
            return {
                "enlaces_pixel_comuna": len(enlace),
                "pixeles_enlazados": int(enlace.pixel_id.nunique()),
                "unidades_administrativas": int(enlace.cod_comuna.nunique()),
            }
        raise ValueError("enlace DMSP existente no corresponde a la máscara actual")
    pix = pd.concat(catalogos.values(), ignore_index=True)
    pix = pix.drop_duplicates("pixel_id").sort_values("pixel_id").reset_index(drop=True)
    enlace = construir_enlace(pix, comunas_path, lote=20_000)
    codigos_esperados = set(_geometrias(comunas_path).cod_comuna.astype(int))
    faltan = sorted(codigos_esperados - set(enlace.cod_comuna.astype(int)))
    if faltan:
        raise ValueError(f"enlace píxel-comuna no cubre unidades {faltan}")
    conteos = enlace.groupby("cod_comuna").pixel_id.nunique()
    menos_dos = {int(k): int(v) for k, v in conteos[conteos < 2].items()}
    if menos_dos:
        raise ValueError(f"unidades con menos de dos píxeles nativos: {menos_dos}")
    _publicar_parquet(enlace, enlace_path)
    estaciones_fuente = DATA / "sinca" / "estaciones_georreferenciadas.csv"
    if estaciones_fuente.exists():
        estaciones, excluidas = enlazar_estaciones(enlace, estaciones_fuente)
        _publicar_parquet(estaciones, estaciones_path)
        _publicar_parquet(excluidas, excluidas_path)
    _guardar_json_atomico(meta_path, {
        "schema": "airpollution.pixel-commune-links.v1",
        "producto": PRODUCTO,
        "mascara_sha256": mascara_sha,
        "metodo": "intersección exacta de huella nativa 30 arc-sec; muchos-a-muchos",
        "sin_agregacion": True,
        "enlaces_pixel_comuna": len(enlace),
        "pixeles_enlazados": int(enlace.pixel_id.nunique()),
        "unidades_administrativas": int(enlace.cod_comuna.nunique()),
        "min_pixeles_por_unidad": int(conteos.min()),
        "max_pixeles_por_unidad": int(conteos.max()),
    })
    return {
        "enlaces_pixel_comuna": len(enlace),
        "pixeles_enlazados": int(enlace.pixel_id.nunique()),
        "unidades_administrativas": int(enlace.cod_comuna.nunique()),
    }


def _gb_libres(path: Path) -> float:
    existente = path
    while not existente.exists() and existente != existente.parent:
        existente = existente.parent
    return shutil.disk_usage(existente).free / 1_000_000_000


def _limpiar_parts(base: Path, mani: Manifiesto | None = None) -> int:
    n = 0
    if not base.exists():
        return 0
    for patron in ("*.part", "*.tmp", "*.download"):
        for path in base.rglob(patron):
            if path.is_file():
                path.unlink(missing_ok=True)
                n += 1
                if mani:
                    mani.registrar({"evento": "temporal_incompleto_eliminado",
                                    "ruta": str(path)})
    return n


def _descargas_grupo(cliente: ClienteEOG, grupo: GrupoInventario, tmp: Path,
                      min_gb_libres: float, mani: Manifiesto) -> dict[str, Path]:
    carpeta = tmp / f"{grupo.satelite}_{grupo.periodo.replace('-', '')}"
    carpeta.mkdir(parents=True, exist_ok=True)
    paths = {}
    for variable in VARIABLES:
        path = carpeta / f"{grupo.satelite}_{grupo.periodo.replace('-', '')}.{variable}.tif"
        paths[variable] = path
        if path.exists() and path.stat().st_size > 0:
            continue
        libres = _gb_libres(tmp)
        if libres < min_gb_libres:
            raise OSError(
                f"reserva de disco: quedan {libres:.1f} GB; se exigen "
                f"{min_gb_libres:.1f} GB"
            )
        item = grupo.items[variable]
        meta = cliente.descargar(item.url, path)
        mani.registrar({
            "evento": "crudo_global_descargado", "satelite": grupo.satelite,
            "periodo": grupo.periodo, "variable": variable,
            "nombre_fuente": item.nombre, "url": item.url,
            "ruta_temporal": str(path), "sha256": sha256(path), **meta,
        })
    return paths


def _grupo_ya_completo(base: Path, grupo: GrupoInventario, aois: tuple[AOI, ...],
                        catalogos: dict[str, pd.DataFrame] | None) -> bool:
    if catalogos is None:
        return False
    for aoi in aois:
        path = _ruta_observacion(base, grupo, aoi)
        if not path.exists():
            return False
        try:
            _validar_observaciones(
                path, catalogos[aoi.id], grupo.satelite, grupo.periodo, aoi)
        except Exception:
            return False
    return True


def _procesar_grupo(base: Path, grupo: GrupoInventario, paths: dict[str, Path],
                     aois: tuple[AOI, ...], comunas, comunas_path: Path,
                     mascara_sha: str, catalogos: dict[str, pd.DataFrame] | None,
                     conservar_crudo: bool, mani: Manifiesto) -> dict[str, pd.DataFrame]:
    grilla = _validar_fuentes(paths)
    existentes = _catalogos_existentes(base, aois, grilla, mascara_sha)
    if catalogos is None:
        catalogos = existentes
    elif existentes is not None:
        for aoi in aois:
            if not np.array_equal(catalogos[aoi.id].pixel_id, existentes[aoi.id].pixel_id):
                raise ValueError("catálogo cargado cambió durante la corrida")
    nuevos_catalogos: dict[str, pd.DataFrame] = {}
    observaciones: dict[str, pd.DataFrame] = {}
    for aoi in aois:
        cat, obs = _extraer_aoi(
            paths, grilla, aoi, comunas, grupo.satelite, grupo.periodo)
        if catalogos is not None:
            previo = catalogos[aoi.id]
            if not (np.array_equal(cat.pixel_id, previo.pixel_id)
                    and np.allclose(cat.lat, previo.lat)
                    and np.allclose(cat.lon, previo.lon)
                    and np.array_equal(cat.cod_comuna, previo.cod_comuna)):
                raise ValueError(f"{aoi.id}: grilla/máscara difiere del catálogo estable")
        nuevos_catalogos[aoi.id] = cat
        observaciones[aoi.id] = obs
    if catalogos is None:
        _publicar_catalogos(base, nuevos_catalogos, grilla, mascara_sha, comunas_path)
        catalogos = {a.id: _validar_catalogo(
            base / "catalogo_pixeles" / f"{a.id}.parquet") for a in aois}
        resumen_enlaces = _publicar_enlaces(base, catalogos, comunas_path, mascara_sha)
        mani.registrar({"evento": "catalogo_y_enlaces_validados", **resumen_enlaces})
    hashes_fuente = {v: sha256(paths[v]) for v in VARIABLES}
    hash_conjunto = hashlib.sha256(json.dumps(
        hashes_fuente, sort_keys=True).encode()).hexdigest()
    salidas = []
    for aoi in aois:
        salida = _ruta_observacion(base, grupo, aoi)
        obs = observaciones[aoi.id]
        if salida.exists():
            try:
                _validar_observaciones(
                    salida, catalogos[aoi.id], grupo.satelite, grupo.periodo, aoi,
                    esperado=obs)
            except Exception:
                salida.unlink(missing_ok=True)
        if not salida.exists():
            _publicar_parquet(obs, salida)
        pixeles = _validar_observaciones(
            salida, catalogos[aoi.id], grupo.satelite, grupo.periodo, aoi,
            esperado=obs)
        salidas.append((aoi, salida, pixeles))
    # Reabre todas las salidas antes de retirar la única copia global temporal.
    for aoi, salida, _ in salidas:
        _validar_observaciones(
            salida, catalogos[aoi.id], grupo.satelite, grupo.periodo, aoi)
    crudos_eliminados = False
    if not conservar_crudo:
        for path in paths.values():
            path.unlink(missing_ok=True)
        crudos_eliminados = all(not p.exists() for p in paths.values())
        carpeta = next(iter(paths.values())).parent
        try:
            carpeta.rmdir()
        except OSError:
            pass
        if not crudos_eliminados:
            raise IOError("no se pudieron eliminar todos los GeoTIFF globales")
    urls = {v: grupo.items[v].url for v in VARIABLES}
    mani.registrar({
        "evento": "grupo_mensual_validado", "satelite": grupo.satelite,
        "periodo": grupo.periodo, "urls_fuente": urls,
        "sha256_fuentes": hashes_fuente, "sha256_conjunto_fuente": hash_conjunto,
        "crudos_globales_eliminados": crudos_eliminados,
        "salidas": len(salidas), "pixeles": sum(x[2] for x in salidas),
        "tiempo_nativo": "monthly composite; no exact intraday time",
        "sin_hora_inventada": True, "sin_remuestreo": True,
    })
    for aoi, salida, pixeles in salidas:
        mani.archivo(
            salida=salida, version=VERSION,
            granule_id=f"{grupo.satelite}_{grupo.periodo.replace('-', '')}",
            url=BASE_URL, aoi_id=aoi.id, territorio=aoi.territorio,
            bbox=aoi.bbox,
            resolucion="30 arc-sec (~1 km Ecuador), native grid, no resampling",
            tiempo_nativo=f"monthly composite {grupo.periodo}; no intraday time",
            qa="cf_cvg cloud-free coverage count + cvg coverage count",
            pixeles=pixeles,
            mascara=(f"{comunas_path}; cell footprint all_touched=True; "
                     "catalogue center cod_comuna and many-to-many footprint links"),
            validacion=("Parquet reopened; exact pixel_id/value comparison; five-AOI "
                        "catalogue and pixel-commune links validated"),
            crudo_eliminado=crudos_eliminados,
            checksum_fuente=hash_conjunto,
            variables_conservadas=list(VARIABLES),
        )
    return catalogos


def _plan_dry_run(args, aois, rango) -> dict:
    load_env()
    token = bool(os.environ.get("EOG_ACCESS_TOKEN", "").strip())
    oauth = all(os.environ.get(x, "").strip() for x in (
        "EOG_CLIENT_ID", "EOG_CLIENT_SECRET", "EOG_USERNAME", "EOG_PASSWORD"))
    return {
        "producto": PRODUCTO,
        "fuente": PRODUCT_PAGE,
        "endpoint_protegido": BASE_URL,
        "rango_efectivo": rango,
        "inicio_brecha_pre_viirs": PERIODO_INICIO_PROYECTO,
        "tope_brecha_pre_viirs": PERIODO_FIN_PROYECTO,
        "variables": list(VARIABLES),
        "resolucion": "30 arc-sec; mensual; sin hora intradiaria",
        "aois": [asdict(x) for x in aois],
        "autenticacion_configurada": token or oauth,
        "metodo_autenticacion": "access_token" if token else ("oauth_refresh" if oauth else None),
        "dry_run_sin_red": True,
        "crudo_global_se_elimina": not args.conservar_crudo,
        "min_gb_libres": args.min_gb_libres,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desde", default="2000-01-01")
    ap.add_argument("--hasta", default="2011-12-31")
    ap.add_argument("--aoi", default="todos")
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument("--inventario-json", type=Path,
                    help="inventario oficial guardado; útil para --solo-recortar")
    ap.add_argument("--solo-inventario", action="store_true",
                    help="consulta y guarda el inventario autenticado; no descarga GeoTIFF")
    ap.add_argument("--solo-recortar", action="store_true",
                    help="no usa red; procesa crudos completos que ya estén en _tmp_global")
    ap.add_argument("--conservar-crudo", action="store_true",
                    help="opt-in de diagnóstico; por defecto se elimina tras validar")
    ap.add_argument("--min-gb-libres", type=float,
                    default=float(os.environ.get("MIN_GB_LIBRES", "100")))
    ap.add_argument("--limite", type=int, help="máximo de satélite-meses (smoke controlado)")
    ap.add_argument("--dry-run", action="store_true",
                    help="muestra plan y credenciales presentes sin red ni escritura")
    args = ap.parse_args(argv)
    try:
        rango = _rango_mensual(args.desde, args.hasta)
        aois = seleccionar(args.aoi, args.comunas if args.comunas.exists() else None)
    except ValueError as exc:
        ap.error(str(exc))
    if args.min_gb_libres < 0:
        ap.error("--min-gb-libres no puede ser negativo")
    if args.limite is not None and args.limite < 1:
        ap.error("--limite debe ser positivo")
    if len(aois) != 5:
        ap.error("la descarga reproducible DMSP exige las cinco AOI de Chile")
    if args.dry_run:
        print(json.dumps(_plan_dry_run(args, aois, rango), ensure_ascii=False, indent=2))
        return 0
    if rango is None:
        log.info("El rango pedido no intersecta la brecha DMSP 2000–2011; nada que hacer")
        return 0
    if not args.comunas.exists():
        ap.error(f"no existe {args.comunas}")
    if args.solo_inventario and args.solo_recortar:
        ap.error("--solo-inventario y --solo-recortar son excluyentes")

    base = ensure_dir(CONTAMINANTES / "Nightlights" / "DMSP_OLS_Monthly")
    tmp = ensure_dir(base / "_tmp_global")
    inventario_path = base / "_inventarios" / "inventario_eog_dmsp_monthly.json"
    mascara_sha = sha256_conjunto_shapefile(args.comunas)
    mani = Manifiesto(base / "_manifiestos", PRODUCTO, {
        "pagina_producto": PRODUCT_PAGE, "endpoint": BASE_URL,
        "desde": rango[0], "hasta": rango[1],
        "limite_pre_viirs": PERIODO_FIN_PROYECTO,
        "resolucion_nativa": "30 arc-sec", "tiempo_nativo": "monthly",
        "sin_hora_intradiaria": True, "variables": list(VARIABLES),
        "aoi": [asdict(x) for x in aois], "antartica": False,
        "mascara_sha256": mascara_sha,
        "unidades_administrativas": resumen_mascara(args.comunas),
        "min_gb_libres": args.min_gb_libres,
        "conservar_crudo": args.conservar_crudo,
        "credenciales": "sólo entorno; valores nunca persistidos",
    })
    _limpiar_parts(base, mani)
    try:
        if args.solo_recortar:
            fuente_inventario = args.inventario_json or inventario_path
            if not fuente_inventario.exists():
                raise ValueError("--solo-recortar requiere un inventario JSON guardado")
            items = _leer_inventario(fuente_inventario)
            cliente = None
        else:
            cliente = ClienteEOG()
            items = inventariar(cliente)
            _guardar_inventario(inventario_path, items)
            fuente_inventario = inventario_path
        mani.registrar({
            "evento": "inventario_validado", "ruta": str(fuente_inventario),
            "sha256": sha256(fuente_inventario),
            "items": len(items), "credenciales_persistidas": False,
        })
        if args.solo_inventario:
            mani.terminar("completo", items=len(items))
            print(f"Inventario oficial guardado: {inventario_path} ({len(items)} archivos)")
            return 0
        grupos = _agrupar(items, *rango)
        if args.limite:
            grupos = grupos[:args.limite]
        if not grupos:
            raise ValueError(f"inventario sin satélite-meses completos para {rango[0]}–{rango[1]}")
        comunas = _geometrias(args.comunas)
        catalogos = _catalogos_existentes(base, aois, None, mascara_sha)
        if catalogos is not None:
            resumen_enlaces = _publicar_enlaces(
                base, catalogos, args.comunas, mascara_sha)
            mani.registrar({"evento": "enlaces_existentes_validados",
                            **resumen_enlaces})
        fallos = 0
        procesados = 0
        for i, grupo in enumerate(grupos, 1):
            if _grupo_ya_completo(base, grupo, aois, catalogos):
                mani.registrar({"evento": "grupo_ya_validado", "satelite": grupo.satelite,
                                "periodo": grupo.periodo})
                continue
            carpeta = tmp / f"{grupo.satelite}_{grupo.periodo.replace('-', '')}"
            paths = {v: carpeta / f"{grupo.satelite}_{grupo.periodo.replace('-', '')}.{v}.tif"
                     for v in VARIABLES}
            try:
                if args.solo_recortar:
                    faltan = [str(p) for p in paths.values() if not p.exists()]
                    if faltan:
                        raise FileNotFoundError("faltan crudos locales: " + ", ".join(faltan))
                else:
                    assert cliente is not None
                    paths = _descargas_grupo(
                        cliente, grupo, tmp, args.min_gb_libres, mani)
                catalogos = _procesar_grupo(
                    base, grupo, paths, aois, comunas, args.comunas,
                    mascara_sha, catalogos, args.conservar_crudo, mani)
                procesados += 1
                log.info("DMSP %d/%d validado: %s %s", i, len(grupos),
                         grupo.satelite, grupo.periodo)
            except BaseException as exc:
                if not args.conservar_crudo:
                    for path in paths.values():
                        path.unlink(missing_ok=True)
                    try:
                        carpeta.rmdir()
                    except OSError:
                        pass
                mani.registrar({
                    "evento": "grupo_fallido", "satelite": grupo.satelite,
                    "periodo": grupo.periodo,
                    "error": f"{type(exc).__name__}: {exc}",
                    "crudos_temporales_eliminados": not args.conservar_crudo,
                })
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                fallos += 1
                log.warning("DMSP %s %s falló: %s", grupo.satelite, grupo.periodo, exc)
        _limpiar_parts(base, mani)
        try:
            tmp.rmdir()
        except OSError:
            pass
        estado = "completo" if not fallos else "con_fallos"
        mani.terminar(estado, grupos_inventario=len(grupos), procesados=procesados,
                      fallos=fallos)
        if fallos:
            raise SystemExit(1)
        return 0
    except CredencialesEOGError as exc:
        mani.registrar({
            "evento": "bloqueado_credenciales", "estado": "credenciales_pendientes",
            "motivo": str(exc), "registro_oficial": REGISTRATION_URL,
            "secretos_persistidos": False,
        })
        mani.terminar("bloqueado_credenciales")
        try:
            tmp.rmdir()
        except OSError:
            pass
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


if __name__ == "__main__":
    raise SystemExit(main())
