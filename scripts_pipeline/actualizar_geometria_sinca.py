#!/usr/bin/env python3
"""Descarga, corrige y valida la geometria de las estaciones SINCA.

La tabla historica ``estaciones.csv`` contiene algunas coordenadas convertidas
con un huso equivocado o campos UTM con el separador decimal perdido. Este
descargador consulta la ficha oficial de cada estacion, conserva una copia
comprimida de la fuente y reconstruye WGS84 sin alterar la medicion horaria.

La seleccion de coordenadas es reproducible:

1. normaliza solamente errores decimales que dejan Este/Norte fuera de rango;
2. prueba los husos UTM 17S, 18S y 19S;
3. prioriza pertenencia a la comuna publicada por SINCA;
4. si la comuna publicada no coincide, conserva el punto oficial, identifica
   la comuna geometrica y deja la discrepancia marcada;
5. usa excepciones solo cuando existe otro documento oficial MMA que corrige
   una ficha SINCA defectuosa.

Salidas atomicas (por defecto en el disco externo):

* ``data/sinca/estaciones_georreferenciadas.csv``;
* ``data/sinca/estaciones_georreferenciadas.geojson``;
* ``data/sinca/metadata/geometria_sinca_manifest.json``;
* instantaneas ``.html.gz`` de las fichas oficiales usadas;
* copias PDF con SHA-256 de los documentos MMA que corrigen fichas defectuosas.

Uso:
  python actualizar_geometria_sinca.py
  python actualizar_geometria_sinca.py --refrescar
  python actualizar_geometria_sinca.py --offline
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pyproj import Transformer
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATA, REPO_ROOT, SINCA, ensure_dir, get_logger  # noqa: E402

log = get_logger("geometria_sinca")

SCRIPT_VERSION = "1.2.0"
FICHA = "https://sinca.mma.gob.cl/index.php/estacion/index/key/{estacion}"
POLITICA_TEMPORAL_RUTA = (
    REPO_ROOT / "config" / "sinca" / "politica_temporal.json"
)

# Las fichas 560 y 548 publican campos UTM corruptos. Los reemplazos provienen
# de informes alojados en dominios oficiales del Ministerio del Medio Ambiente.
COORDENADAS_OFICIALES_SUPLETORIAS: dict[str, dict[str, Any]] = {
    "560": {
        "utm_e": 265069.0,
        "utm_n": 6354089.0,
        "huso": 19,
        "fuente": (
            "https://pras.mma.gob.cl/wp-content/uploads/2023/01/"
            "AMBIMET_INFORME_FINAL_Revision1.pdf"
        ),
        "detalle": "Tabla 2-1, estacion Concon MMA",
        "cache_nombre": "560_concon_mma_AMBIMET_INFORME_FINAL_Revision1.pdf",
    },
    "548": {
        "utm_e": 267547.0,
        "utm_n": 6374609.0,
        "huso": 19,
        "fuente": (
            "https://pras.mma.gob.cl/wp-content/uploads/2023/01/"
            "OC608897-150-SE20_REPORTE_FINAL_20211130_v5.pdf"
        ),
        "detalle": "Tabla 11, codigo SINCA S2 Ventanas",
        "cache_nombre": "548_ventanas_reporte_final_20211130_v5.pdf",
    },
}

TRANSFORMADORES_WGS84 = {
    huso: Transformer.from_crs(32700 + huso, 4326, always_xy=True)
    for huso in (17, 18, 19)
}
TRANSFORMADOR_METRICO = Transformer.from_crs(4326, 3857, always_xy=True)


def _sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _componentes_shapefile(ruta: Path) -> tuple[dict[str, dict[str, Any]], str]:
    """Hashea el conjunto completo que materializa un shapefile.

    ``.shp`` por sí solo no contiene atributos ni CRS: ``.dbf``, ``.shx`` y
    ``.prj`` también cambian el resultado. Se incluyen además todos los
    sidecars presentes con el mismo nombre base para dejar la entrada exacta
    auditada.
    """
    componentes = sorted(
        (p for p in ruta.parent.glob(f"{ruta.stem}.*") if p.is_file()),
        key=lambda p: p.name.casefold(),
    )
    nombres = {p.suffix.lower() for p in componentes}
    faltan = {".shp", ".shx", ".dbf", ".prj"} - nombres
    if faltan:
        raise FileNotFoundError(
            f"Shapefile incompleto {ruta}: faltan {sorted(faltan)}"
        )
    salida = {
        p.name: {
            "path": str(p.resolve()),
            "bytes": p.stat().st_size,
            "sha256": _sha256_archivo(p),
        }
        for p in componentes
    }
    # El resumen es portable entre máquinas: las rutas absolutas quedan como
    # metadato, pero no participan del hash del contenido.
    contenido = {
        nombre: {"bytes": datos["bytes"], "sha256": datos["sha256"]}
        for nombre, datos in salida.items()
    }
    resumen = _sha256_bytes(
        json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    return salida, resumen


def _normalizar_nombre(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def _escribir_bytes_atomicos(destino: Path, datos: bytes) -> None:
    ensure_dir(destino.parent)
    fd, nombre = tempfile.mkstemp(prefix=f".{destino.name}.", dir=destino.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        Path(nombre).replace(destino)
    except BaseException:
        Path(nombre).unlink(missing_ok=True)
        raise


def _escribir_csv_atomico(tabla: pd.DataFrame, destino: Path) -> None:
    ensure_dir(destino.parent)
    fd, nombre = tempfile.mkstemp(
        prefix=f".{destino.name}.", suffix=".csv", dir=destino.parent
    )
    os.close(fd)
    temporal = Path(nombre)
    try:
        tabla.to_csv(temporal, index=False)
        temporal.replace(destino)
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


def _escribir_geojson_atomico(tabla: gpd.GeoDataFrame, destino: Path) -> None:
    """Escribe GeoJSON canónico; el nombre no depende del archivo temporal."""
    documento = json.loads(tabla.to_json(drop_id=True, to_wgs84=True))
    documento["name"] = destino.stem
    datos = (json.dumps(
        documento, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ) + "\n").encode("utf-8")
    _escribir_bytes_atomicos(destino, datos)


def _obtener_documento_oficial(
    estacion: str,
    cache: Path,
    *,
    refrescar: bool,
    offline: bool,
) -> dict[str, Any]:
    """Conserva y verifica el PDF MMA que sustenta una coordenada supletoria."""
    fuente = COORDENADAS_OFICIALES_SUPLETORIAS[estacion]
    ruta = cache / str(fuente["cache_nombre"])
    url = str(fuente["fuente"])

    def validar(datos: bytes) -> None:
        if len(datos) < 10_000 or not datos.lstrip().startswith(b"%PDF-"):
            raise ValueError(f"documento MMA inválido o incompleto para SINCA {estacion}")

    if ruta.exists() and not refrescar:
        datos = ruta.read_bytes()
        validar(datos)
    else:
        if offline:
            raise FileNotFoundError(
                f"No existe PDF oficial offline para SINCA {estacion}: {ruta}"
            )
        ultimo: Exception | None = None
        for intento in range(1, 5):
            try:
                respuesta = requests.get(
                    url,
                    timeout=180,
                    headers={
                        "User-Agent": (
                            "AirPollutionChile-reproducible-pipeline/"
                            f"{SCRIPT_VERSION}"
                        )
                    },
                )
                respuesta.raise_for_status()
                datos = respuesta.content
                validar(datos)
                _escribir_bytes_atomicos(ruta, datos)
                break
            except (requests.RequestException, ValueError) as exc:
                ultimo = exc
                log.warning(
                    "Documento MMA SINCA %s: intento %d/4 fallo: %s",
                    estacion, intento, exc,
                )
        else:
            assert ultimo is not None
            raise ultimo
    return {
        "url": url,
        "cache_path": str(ruta.resolve()),
        "bytes": len(datos),
        "sha256": _sha256_bytes(datos),
        "detalle": fuente["detalle"],
    }


def _descargar_ficha(
    estacion: str,
    cache: Path,
    *,
    refrescar: bool,
    offline: bool,
) -> tuple[bytes, str, str]:
    """Devuelve HTML, URL y fecha UTC, conservando la fuente comprimida."""
    ruta = cache / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', estacion)}.html.gz"
    url = FICHA.format(estacion=estacion)
    if ruta.exists() and not refrescar:
        with gzip.open(ruta, "rb") as f:
            html = f.read()
        fecha = datetime.fromtimestamp(ruta.stat().st_mtime, UTC).isoformat()
        return html, url, fecha
    if offline:
        raise FileNotFoundError(f"No existe instantanea offline para SINCA {estacion}")

    ultimo: Exception | None = None
    for intento in range(1, 5):
        try:
            respuesta = requests.get(
                url,
                timeout=60,
                headers={"User-Agent": "AirPollutionChile-reproducible-pipeline/1.0"},
            )
            respuesta.raise_for_status()
            html = respuesta.content
            if b"Coordenadas UTM" not in html:
                raise ValueError("la ficha no contiene Coordenadas UTM")
            comprimido = gzip.compress(html, compresslevel=9, mtime=0)
            _escribir_bytes_atomicos(ruta, comprimido)
            return html, url, datetime.now(UTC).isoformat()
        except (requests.RequestException, ValueError) as exc:
            ultimo = exc
            log.warning("SINCA %s: intento %d/4 fallo: %s", estacion, intento, exc)
    assert ultimo is not None
    raise ultimo


def _parsear_ficha(html: bytes) -> dict[str, Any]:
    texto = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    utm = re.search(
        r"Coordenadas UTM\s+([\d.,]+)\s*E\s+([\d.,]+)\s*N", texto, re.I
    )
    huso = re.search(r"Huso horario\s+(\d+)", texto, re.I)
    comuna = re.search(r"Comuna\s+(.+?)\s+Coordenadas UTM", texto, re.I)
    if not (utm and huso and comuna):
        raise ValueError("no fue posible parsear comuna, UTM y huso de la ficha")
    return {
        "utm_e_raw": utm.group(1),
        "utm_n_raw": utm.group(2),
        "huso_publicado": int(huso.group(1)),
        "comuna_sinca": comuna.group(1).strip(),
    }


def _valores_plausibles(
    texto: str, minimo: float, maximo: float
) -> list[tuple[float, int]]:
    """Interpreta un campo UTM y prueba hasta tres decimales concatenados."""
    digitos = re.sub(r"\D", "", texto)
    if not digitos:
        return []
    base = float(digitos)
    candidatos: dict[float, int] = {}
    for decimales in range(4):
        valor = base / (10**decimales)
        if minimo <= valor <= maximo:
            candidatos[valor] = decimales
    return sorted(candidatos.items(), key=lambda par: par[1])


def _comuna_que_contiene(
    punto_m: Point, comunas: gpd.GeoDataFrame
) -> pd.Series | None:
    posibles = comunas.iloc[list(comunas.sindex.query(punto_m, predicate="intersects"))]
    for _, fila in posibles.iterrows():
        if fila.geometry.covers(punto_m):
            return fila
    return None


def _resolver_coordenada(
    estacion: str,
    ficha: dict[str, Any],
    comunas: gpd.GeoDataFrame,
) -> dict[str, Any]:
    declarada = ficha["comuna_sinca"]
    objetivo = comunas[comunas["_nombre_norm"] == _normalizar_nombre(declarada)]
    geometria_objetivo = objetivo.geometry.union_all()
    # Distancias en el UTM de cada candidato. Web Mercator (EPSG:3857) sirve
    # para topología, pero exagera 16–32 % las distancias a estas latitudes.
    objetivo_utm: dict[int, Any] = {}
    if not geometria_objetivo.is_empty:
        for zona in (17, 18, 19):
            objetivo_utm[zona] = gpd.GeoSeries(
                [geometria_objetivo], crs=comunas.crs
            ).to_crs(32700 + zona).iloc[0]

    supletoria = COORDENADAS_OFICIALES_SUPLETORIAS.get(estacion)
    if supletoria:
        estes = [(float(supletoria["utm_e"]), 0)]
        nortes = [(float(supletoria["utm_n"]), 0)]
        husos = [int(supletoria["huso"])]
    else:
        estes = _valores_plausibles(ficha["utm_e_raw"], 100_000, 900_000)
        nortes = _valores_plausibles(ficha["utm_n_raw"], 3_600_000, 8_200_000)
        husos = [17, 18, 19]

    candidatos = []
    for utm_e, dec_e in estes:
        for utm_n, dec_n in nortes:
            for huso in husos:
                lon, lat = TRANSFORMADORES_WGS84[huso].transform(utm_e, utm_n)
                if not (-112.0 <= lon <= -65.0 and -57.0 <= lat <= -17.0):
                    continue
                punto_m = Point(*TRANSFORMADOR_METRICO.transform(lon, lat))
                geografica = _comuna_que_contiene(punto_m, comunas)
                nacional = geografica is not None
                declarada_ok = bool(
                    not geometria_objetivo.is_empty
                    and geometria_objetivo.covers(punto_m)
                )
                distancia = (
                    float(Point(utm_e, utm_n).distance(objetivo_utm[huso]))
                    if huso in objetivo_utm else math.nan
                )
                # Primero pertenencia declarada; luego pertenencia nacional. El
                # huso publicado desempata, sin imponerse cuando deja Chile.
                puntaje = (
                    0 if declarada_ok else 1,
                    0 if nacional else 1,
                    0 if huso == ficha["huso_publicado"] else 1,
                    distancia if math.isfinite(distancia) else float("inf"),
                    dec_e + dec_n,
                )
                candidatos.append(
                    (puntaje, utm_e, utm_n, huso, dec_e, dec_n, lon, lat,
                     declarada_ok, geografica, distancia)
                )
    if not candidatos:
        raise ValueError(f"SINCA {estacion}: ningun candidato UTM plausible")

    elegido = min(candidatos, key=lambda valor: valor[0])
    (_, utm_e, utm_n, huso, dec_e, dec_n, lon, lat,
     declarada_ok, geografica, distancia) = elegido
    if geografica is None:
        raise ValueError(
            f"SINCA {estacion}: la mejor coordenada no pertenece a Chile administrativo"
        )

    if supletoria:
        qc_coordenada = "documento_mma_supletorio"
        fuente_coordenada = supletoria["fuente"]
        detalle_fuente = supletoria["detalle"]
    elif dec_e or dec_n or huso != ficha["huso_publicado"]:
        qc_coordenada = "ficha_sinca_normalizada"
        fuente_coordenada = "ficha_sinca"
        cambios = []
        if dec_e:
            cambios.append(f"este_dividido_10^{dec_e}")
        if dec_n:
            cambios.append(f"norte_dividido_10^{dec_n}")
        if huso != ficha["huso_publicado"]:
            cambios.append(f"huso_{ficha['huso_publicado']}_a_{huso}")
        detalle_fuente = ";".join(cambios)
    else:
        qc_coordenada = "ficha_sinca_directa"
        fuente_coordenada = "ficha_sinca"
        detalle_fuente = "sin_correccion"

    return {
        "utm_e": utm_e,
        "utm_n": utm_n,
        "huso_usado": huso,
        "ajuste_decimales_e": dec_e,
        "ajuste_decimales_n": dec_n,
        "lon": lon,
        "lat": lat,
        "cod_comuna_geografica": int(geografica["cod_comuna"]),
        "comuna_geografica": geografica["Comuna"],
        "provincia_geografica": geografica["Provincia"],
        "region_geografica": geografica["Region"],
        "coincide_comuna_sinca": bool(declarada_ok),
        "distancia_comuna_sinca_m": distancia,
        "crs_distancia_comuna": f"EPSG:{32700 + huso}",
        "qc_coordenada": qc_coordenada,
        "qc_comuna": "coincide" if declarada_ok else "discrepancia_publicada",
        "fuente_coordenada": fuente_coordenada,
        "detalle_fuente_coordenada": detalle_fuente,
        "usable_geoespacial": True,
    }


def _cargar_comunas(ruta: Path) -> gpd.GeoDataFrame:
    comunas = gpd.read_file(ruta)
    requeridas = {"cod_comuna", "Comuna", "Provincia", "Region", "geometry"}
    faltan = requeridas - set(comunas.columns)
    if faltan:
        raise SystemExit(f"Faltan columnas en {ruta}: {sorted(faltan)}")
    comunas = comunas.to_crs(3857).copy()
    comunas["_nombre_norm"] = comunas["Comuna"].map(_normalizar_nombre)
    return comunas


def ejecutar(args: argparse.Namespace) -> pd.DataFrame:
    estaciones = pd.read_csv(args.estaciones, dtype={"estacion": str})
    requeridas = {
        "region_sinca", "estacion", "nombre", "comuna", "lat", "lon"
    }
    faltan = requeridas - set(estaciones.columns)
    if faltan:
        raise SystemExit(f"Faltan columnas en {args.estaciones}: {sorted(faltan)}")
    if estaciones["estacion"].duplicated().any():
        raise SystemExit("Hay codigos de estacion duplicados")

    comunas = _cargar_comunas(args.comunas)
    cache = ensure_dir(args.cache)
    cache_documentos = ensure_dir(args.cache_documentos)
    codigos_presentes = set(estaciones["estacion"])
    documentos_supletorios = {
        codigo: _obtener_documento_oficial(
            codigo,
            cache_documentos,
            refrescar=args.refrescar,
            offline=args.offline,
        )
        for codigo in COORDENADAS_OFICIALES_SUPLETORIAS
        if codigo in codigos_presentes
    }
    fuentes: dict[str, tuple[bytes, str, str]] = {}
    errores: dict[str, str] = {}

    def obtener(codigo: str):
        return _descargar_ficha(
            codigo, cache, refrescar=args.refrescar, offline=args.offline
        )

    with ThreadPoolExecutor(max_workers=args.workers) as ejecutor:
        futuros = {
            ejecutor.submit(obtener, codigo): codigo
            for codigo in estaciones["estacion"]
        }
        for futuro in as_completed(futuros):
            codigo = futuros[futuro]
            try:
                fuentes[codigo] = futuro.result()
            except Exception as exc:  # noqa: BLE001
                errores[codigo] = str(exc)
    if errores:
        detalle = "\n".join(f"  {k}: {v}" for k, v in sorted(errores.items()))
        raise SystemExit(f"No se pudieron obtener todas las fichas:\n{detalle}")

    salida = []
    for fila in estaciones.to_dict("records"):
        codigo = str(fila["estacion"])
        html, url, consulta_utc = fuentes[codigo]
        ficha = _parsear_ficha(html)
        resuelta = _resolver_coordenada(codigo, ficha, comunas)
        documento = documentos_supletorios.get(codigo, {})
        salida.append({
            "region_sinca": fila["region_sinca"],
            "estacion": codigo,
            "nombre": fila["nombre"],
            "comuna_catalogo": fila["comuna"],
            "comuna_sinca": ficha["comuna_sinca"],
            "lat_catalogo": fila["lat"],
            "lon_catalogo": fila["lon"],
            **resuelta,
            "utm_e_publicado": ficha["utm_e_raw"],
            "utm_n_publicado": ficha["utm_n_raw"],
            "huso_publicado": ficha["huso_publicado"],
            "fuente_ficha": url,
            "consulta_ficha_utc": consulta_utc,
            "sha256_ficha_html": _sha256_bytes(html),
            "fuente_coordenada_cache": documento.get("cache_path", ""),
            "fuente_coordenada_sha256": documento.get("sha256", ""),
        })

    tabla = pd.DataFrame(salida).sort_values(
        ["region_sinca", "estacion"], kind="stable"
    ).reset_index(drop=True)
    if len(tabla) != len(estaciones) or not tabla["usable_geoespacial"].all():
        raise SystemExit("La validacion no produjo una coordenada usable por estacion")
    if not tabla[["lat", "lon"]].apply(
        lambda serie: serie.map(math.isfinite)
    ).all().all():
        raise SystemExit("La salida contiene coordenadas no finitas")

    _escribir_csv_atomico(tabla, args.salida)
    geo_tabla = tabla.copy()
    # GeoJSON no admite Infinity; las coordenadas antiguas defectuosas se
    # conservan como texto/nulo de procedencia, nunca como geometria activa.
    for columna in ("lat_catalogo", "lon_catalogo"):
        geo_tabla[columna] = [
            valor
            if not isinstance(valor, (int, float)) or math.isfinite(valor)
            else None
            for valor in geo_tabla[columna]
        ]
    geo = gpd.GeoDataFrame(
        geo_tabla,
        geometry=gpd.points_from_xy(tabla["lon"], tabla["lat"]),
        crs=4326,
    )
    _escribir_geojson_atomico(geo, args.geojson)

    conteos = {
        "estaciones": int(len(tabla)),
        "coinciden_comuna_sinca": int(tabla["coincide_comuna_sinca"].sum()),
        "discrepancias_comuna_sinca": int((~tabla["coincide_comuna_sinca"]).sum()),
        "coordenadas_directas": int((tabla["qc_coordenada"] == "ficha_sinca_directa").sum()),
        "coordenadas_normalizadas": int((tabla["qc_coordenada"] == "ficha_sinca_normalizada").sum()),
        "coordenadas_supletorias": int((tabla["qc_coordenada"] == "documento_mma_supletorio").sum()),
    }
    componentes_comunas, sha_componentes_comunas = _componentes_shapefile(
        args.comunas
    )
    manifiesto = {
        "schema_version": 2,
        "script_version": SCRIPT_VERSION,
        "created_utc": datetime.now(UTC).isoformat(),
        "input_stations": str(args.estaciones.resolve()),
        "input_stations_sha256": _sha256_archivo(args.estaciones),
        "temporal_policy": str(POLITICA_TEMPORAL_RUTA.resolve()),
        "temporal_policy_sha256": _sha256_archivo(POLITICA_TEMPORAL_RUTA),
        "communes": str(args.comunas.resolve()),
        "communes_shp_sha256": _sha256_archivo(args.comunas),
        "communes_components": componentes_comunas,
        "communes_components_sha256": sha_componentes_comunas,
        "station_page_template": FICHA,
        "utm_crs_candidates": ["EPSG:32717", "EPSG:32718", "EPSG:32719"],
        "output_csv": str(args.salida.resolve()),
        "output_csv_sha256": _sha256_archivo(args.salida),
        "output_geojson": str(args.geojson.resolve()),
        "output_geojson_sha256": _sha256_archivo(args.geojson),
        "official_overrides": COORDENADAS_OFICIALES_SUPLETORIAS,
        "official_override_sources": documentos_supletorios,
        "counts": conteos,
    }
    _escribir_bytes_atomicos(
        args.manifiesto,
        (json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    log.info(
        "OK: %d estaciones; %d coinciden con comuna SINCA; %d discrepancias marcadas",
        conteos["estaciones"],
        conteos["coinciden_comuna_sinca"],
        conteos["discrepancias_comuna_sinca"],
    )
    return tabla


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--estaciones", type=Path,
        default=REPO_ROOT / "config" / "sinca" / "estaciones.csv",
    )
    ap.add_argument("--comunas", type=Path, default=DATA / "comunas.shp")
    ap.add_argument(
        "--salida", type=Path, default=SINCA / "estaciones_georreferenciadas.csv"
    )
    ap.add_argument(
        "--geojson", type=Path, default=SINCA / "estaciones_georreferenciadas.geojson"
    )
    ap.add_argument(
        "--cache", type=Path,
        default=SINCA / "metadata" / "fichas_estaciones_sinca",
    )
    ap.add_argument(
        "--cache-documentos", type=Path,
        default=SINCA / "metadata" / "fuentes_coordenadas_mma",
    )
    ap.add_argument(
        "--manifiesto", type=Path,
        default=SINCA / "metadata" / "geometria_sinca_manifest.json",
    )
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refrescar", action="store_true")
    ap.add_argument(
        "--offline", action="store_true",
        help="no usa red; exige una instantanea .html.gz para cada estacion",
    )
    args = ap.parse_args(argv)
    if args.refrescar and args.offline:
        ap.error("--refrescar y --offline son incompatibles")
    if args.workers < 1:
        ap.error("--workers debe ser al menos 1")
    ejecutar(args)


if __name__ == "__main__":
    main()
