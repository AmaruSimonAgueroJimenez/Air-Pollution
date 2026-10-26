#!/usr/bin/env python3
"""geometria_sinca_ampliacion.py — Envoltorio declarado de actualizar_geometria_sinca.py.

Corre el script sellado ``actualizar_geometria_sinca.py`` sin modificarlo (su
huella queda registrada) para el maestro georreferenciado de la ampliación
SINCA, con tres agregados que viven sólo en memoria y sólo en esta corrida:

1. **Correcciones oficiales de coordenadas.** Es el mismo mecanismo que usa el
   script para las estaciones 560 y 548 (``COORDENADAS_OFICIALES_SUPLETORIAS``:
   UTM, huso, URL de la fuente, detalle y documento guardado), pero las
   entradas se leen desde un JSON de la carpeta de la ampliación
   (``--correcciones``), nunca desde la configuración sellada. Cada corrección
   exige el documento fuente ya guardado en ``--cache-documentos`` y su
   SHA-256; no se usa la red. El documento puede ser un PDF o la ficha SINCA
   (HTML, comprimido o no).
2. **Polígonos comunales inválidos.** Tras la reproyección que hace el script,
   algunos polígonos de ``comunas.shp`` quedan inválidos (p. ej. Chañaral) y la
   prueba de pertenencia lanza ``TopologyException``. Aquí se validan en
   memoria (``make_valid``, conservando sólo las partes poligonales); el
   archivo ``comunas.shp`` no se toca.
3. **Tolerancia costera explícita por estación.** Si la coordenada oficial cae
   fuera de todo polígono comunal y a no más de ``tolerancia_costa_m`` metros
   de la comuna que publica la ficha (costa generalizada del archivo de
   comunas), se le asigna esa comuna y queda marcada en ``qc_comuna``.

Rechaza cualquier ruta de salida dentro de ``data/sinca``. Escribe además
``envoltorio_geometria.json`` junto al manifiesto, con las huellas del script
sellado, de este envoltorio y del JSON de correcciones.

Uso (mismos argumentos que el script sellado, más ``--correcciones``)::

  python geometria_sinca_ampliacion.py --offline --correcciones <json> \\
      --estaciones ... --salida ... --geojson ... --manifiesto ... \\
      --cache ... --cache-documentos ...
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actualizar_geometria_sinca as geo  # noqa: E402
from _common import SINCA, get_logger  # noqa: E402

log = get_logger("geometria_sinca_ampliacion")

VERSION = "1.0.0"
ENVOLTORIO_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SELLADO_SHA256 = hashlib.sha256(Path(geo.__file__).read_bytes()).hexdigest()
CAMPOS_CORRECCION = ("utm_e", "utm_n", "huso", "fuente", "detalle", "cache_nombre",
                     "sha256", "consultado_utc", "tipo_documento")
SALIDAS = ("salida", "geojson", "manifiesto", "cache", "cache_documentos")


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def cargar_correcciones(ruta: Path) -> dict:
    """Lee y valida el JSON de correcciones (``{"estaciones": {codigo: {...}}}``)."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    estaciones = datos.get("estaciones")
    if not isinstance(estaciones, dict):
        raise ValueError("el JSON de correcciones debe tener un objeto 'estaciones'")
    for codigo, c in estaciones.items():
        faltan = [k for k in CAMPOS_CORRECCION if k not in c]
        if faltan:
            raise ValueError(f"corrección {codigo}: faltan {faltan}")
        if c["tipo_documento"] not in ("pdf", "ficha_sinca_html"):
            raise ValueError(f"corrección {codigo}: tipo_documento desconocido")
        if int(c["huso"]) not in (17, 18, 19):
            raise ValueError(f"corrección {codigo}: huso fuera de 17-19")
        for k in ("utm_e", "utm_n"):
            if not math.isfinite(float(c[k])):
                raise ValueError(f"corrección {codigo}: {k} no finito")
        tol = float(c.get("tolerancia_costa_m", 0) or 0)
        if not 0 <= tol <= 1000:
            raise ValueError(f"corrección {codigo}: tolerancia_costa_m fuera de 0-1000")
    return estaciones


def _validar_documento(datos: bytes, tipo: str, codigo: str) -> None:
    if tipo == "pdf":
        if len(datos) < 10_000 or not datos.lstrip().startswith(b"%PDF-"):
            raise ValueError(f"documento PDF inválido para SINCA {codigo}")
        return
    texto = gzip.decompress(datos) if datos[:2] == b"\x1f\x8b" else datos
    if b'id="tablaGeneral"' not in texto:
        raise ValueError(f"la ficha SINCA guardada para {codigo} no es una ficha")


def documento_oficial_factory(correcciones: dict, original):
    """Reemplazo de ``_obtener_documento_oficial``: sin red y con huella exigida."""

    def obtener(estacion: str, cache: Path, *, refrescar: bool, offline: bool) -> dict:
        if estacion not in correcciones:
            return original(estacion, cache, refrescar=refrescar, offline=offline)
        c = correcciones[estacion]
        ruta = Path(cache) / c["cache_nombre"]
        if not ruta.is_file():
            raise FileNotFoundError(f"falta el documento de la corrección {estacion}: {ruta.name}")
        datos = ruta.read_bytes()
        if _sha256(datos) != c["sha256"]:
            raise ValueError(f"la huella del documento de {estacion} no coincide")
        _validar_documento(datos, c["tipo_documento"], estacion)
        return {"url": c["fuente"], "cache_path": str(ruta.resolve()), "bytes": len(datos),
                "sha256": c["sha256"], "detalle": c["detalle"],
                "consultado_utc": c["consultado_utc"], "tipo_documento": c["tipo_documento"]}

    return obtener


def poligonal(geom):
    """``make_valid`` conservando sólo superficies (descarta líneas y puntos)."""
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
    from shapely.ops import unary_union
    from shapely.validation import make_valid
    if geom is None or geom.is_valid:
        return geom
    reparada = make_valid(geom)
    if isinstance(reparada, (Polygon, MultiPolygon)):
        return reparada
    partes = [g for g in getattr(reparada, "geoms", [])
              if isinstance(g, (Polygon, MultiPolygon))]
    return unary_union(partes) if partes else GeometryCollection()


def cargar_comunas_factory(original, registro: dict):
    def cargar(ruta: Path):
        comunas = original(ruta)
        invalidas = ~comunas.geometry.is_valid
        registro["comunas_validadas_en_memoria"] = sorted(
            str(c) for c in comunas.loc[invalidas, "Comuna"])
        if invalidas.any():
            comunas = comunas.copy()
            comunas["geometry"] = comunas.geometry.map(poligonal)
            log.info("polígonos comunales validados en memoria: %s",
                     registro["comunas_validadas_en_memoria"])
        return comunas
    return cargar


def resolver_factory(original, correcciones: dict, registro: dict):
    """Aplica la tolerancia costera sólo a las estaciones que la declaran."""

    def resolver(estacion, ficha, comunas):
        tol = float(correcciones.get(estacion, {}).get("tolerancia_costa_m", 0) or 0)
        try:
            return original(estacion, ficha, comunas)
        except ValueError as exc:
            if not tol or "no pertenece a Chile administrativo" not in str(exc):
                raise
        declarada = comunas["_nombre_norm"] == geo._normalizar_nombre(ficha["comuna_sinca"])
        if not declarada.any():
            raise ValueError(f"SINCA {estacion}: sin comuna publicada para la tolerancia")
        c = correcciones[estacion]
        lon, lat = geo.TRANSFORMADORES_WGS84[int(c["huso"])].transform(
            float(c["utm_e"]), float(c["utm_n"]))
        # Distancia real al polígono publicado, en el UTM de la corrección.
        import geopandas as gpd
        from shapely.geometry import Point
        poligono_utm = gpd.GeoSeries(comunas.loc[declarada, "geometry"],
                                     crs=comunas.crs).to_crs(32700 + int(c["huso"])).union_all()
        distancia = float(Point(float(c["utm_e"]), float(c["utm_n"])).distance(poligono_utm))
        if distancia > tol:
            raise ValueError(f"SINCA {estacion}: {distancia:.0f} m fuera de la comuna publicada; "
                             f"supera la tolerancia de {tol:.0f} m")
        # El búfer se hace en 3857 con el factor de escala local (1/cos lat).
        ampliadas = comunas.copy()
        ampliadas.loc[declarada, "geometry"] = ampliadas.loc[declarada, "geometry"].buffer(
            (tol + 1) / math.cos(math.radians(lat)))
        resultado = original(estacion, ficha, ampliadas)
        resultado.update(
            qc_comuna=f"fuera_de_poligono_costero_{distancia:.0f}m_tolerancia_{tol:.0f}m",
            coincide_comuna_sinca=False, distancia_comuna_sinca_m=distancia)
        registro.setdefault("tolerancia_costera_aplicada", {})[estacion] = round(distancia, 1)
        return resultado

    return resolver


def instalar(correcciones: dict, registro: dict) -> None:
    """Parchea en memoria el módulo sellado (sólo dentro de este proceso)."""
    for codigo, c in correcciones.items():
        if codigo in geo.COORDENADAS_OFICIALES_SUPLETORIAS:
            raise ValueError(f"{codigo} ya tiene una corrección sellada; no se reemplaza")
        geo.COORDENADAS_OFICIALES_SUPLETORIAS[codigo] = {
            "utm_e": float(c["utm_e"]), "utm_n": float(c["utm_n"]), "huso": int(c["huso"]),
            "fuente": c["fuente"], "detalle": c["detalle"], "cache_nombre": c["cache_nombre"],
        }
    geo._obtener_documento_oficial = documento_oficial_factory(
        correcciones, geo._obtener_documento_oficial)
    geo._cargar_comunas = cargar_comunas_factory(geo._cargar_comunas, registro)
    geo._resolver_coordenada = resolver_factory(geo._resolver_coordenada, correcciones,
                                                registro)


def _dentro_de_sinca(ruta: Path) -> bool:
    sinca = SINCA.resolve()
    ruta = Path(ruta).expanduser().resolve()
    return ruta == sinca or sinca in ruta.parents


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--correcciones", type=Path, required=True)
    for nombre in ("estaciones", "salida", "geojson", "manifiesto", "cache",
                   "cache-documentos"):
        ap.add_argument(f"--{nombre}", type=Path, required=True)
    propios, resto = ap.parse_known_args(argv)
    for nombre in SALIDAS:
        if _dentro_de_sinca(getattr(propios, nombre)):
            ap.error(f"--{nombre.replace('_', '-')} no puede estar dentro de data/sinca")
    if "--offline" not in resto:
        ap.error("se exige --offline: los documentos ya están guardados")
    correcciones = cargar_correcciones(propios.correcciones)
    registro = {"version": VERSION, "envoltorio_sha256": ENVOLTORIO_SHA256,
                "script_sellado": "scripts_pipeline/actualizar_geometria_sinca.py",
                "script_sellado_sha256": SELLADO_SHA256,
                "script_sellado_version": geo.SCRIPT_VERSION,
                "correcciones": str(propios.correcciones.name),
                "correcciones_sha256": _sha256(propios.correcciones.read_bytes()),
                "estaciones_corregidas": sorted(correcciones),
                "inicio_utc": datetime.now(UTC).isoformat()}
    instalar(correcciones, registro)
    argumentos = [*resto]
    for nombre in ("estaciones", "salida", "geojson", "manifiesto", "cache",
                   "cache-documentos"):
        argumentos += [f"--{nombre}", str(getattr(propios, nombre.replace("-", "_")))]
    geo.main(argumentos)
    registro["fin_utc"] = datetime.now(UTC).isoformat()
    destino = propios.manifiesto.parent / "envoltorio_geometria.json"
    geo._escribir_bytes_atomicos(
        destino, (json.dumps(registro, ensure_ascii=False, indent=2) + "\n").encode())
    log.info("envoltorio: %s", json.dumps({k: registro.get(k) for k in (
        "estaciones_corregidas", "comunas_validadas_en_memoria",
        "tolerancia_costera_aplicada")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
