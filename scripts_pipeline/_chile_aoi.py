"""Deriva AOIs compactas de Chile administrativo desde ``comunas.shp``.

La derivación separa componentes remotos para no crear corredores oceánicos.
Se excluye Antártica (el shapefile comunal termina cerca de 56°S). Las
constantes sólo son un fallback explícito para poder inspeccionar ``--help`` o
un ``--dry-run`` sin datos montados; las descargas normales pasan el shapefile.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AOI:
    id: str
    territorio: str
    bbox: tuple[float, float, float, float]


AOIS_FALLBACK = (
    AOI("continente", "continental", (-75.80, -56.05, -66.35, -17.43)),
    AOI("juan_fernandez", "juan_fernandez_desventuradas",
        (-80.90, -33.87, -78.72, -33.52)),
    AOI("desventuradas", "juan_fernandez_desventuradas",
        (-80.20, -26.40, -79.80, -26.20)),
    AOI("rapa_nui", "isla_de_pascua",
        (-109.51, -27.26, -109.17, -26.99)),
    AOI("sala_y_gomez", "isla_de_pascua",
        (-105.42, -26.54, -105.30, -26.42)),
)


def _partes(geom):
    if geom is None or geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        yield geom
    elif hasattr(geom, "geoms"):
        for sub in geom.geoms:
            yield from _partes(sub)


def _bbox_partes(partes, margen: float):
    partes = list(partes)
    if not partes:
        raise ValueError("grupo territorial sin geometría")
    x0 = min(g.bounds[0] for g in partes) - margen
    y0 = min(g.bounds[1] for g in partes) - margen
    x1 = max(g.bounds[2] for g in partes) + margen
    y1 = max(g.bounds[3] for g in partes) + margen
    return float(x0), float(y0), float(x1), float(y1)


def derivar(comunas_path: Path, margen: float = 0.05) -> tuple[AOI, ...]:
    import geopandas as gpd

    g = gpd.read_file(comunas_path).to_crs("EPSG:4326")
    if "cod_comuna" not in g:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    try:
        g["geometry"] = g.geometry.make_valid()
    except AttributeError:
        from shapely.validation import make_valid
        g["geometry"] = g.geometry.map(make_valid)

    remotos = {5104, 5201}
    continente = (p for geom in g.loc[~g.cod_comuna.isin(remotos), "geometry"]
                  for p in _partes(geom))
    jf_todos = [p for geom in g.loc[g.cod_comuna == 5104, "geometry"]
                for p in _partes(geom)]
    rapa_todos = [p for geom in g.loc[g.cod_comuna == 5201, "geometry"]
                  for p in _partes(geom)]
    # Los grupos están separados por >7° de latitud o >4° de longitud;
    # umbrales estables y auditables, no clustering dependiente del orden.
    juan = [p for p in jf_todos if p.centroid.y < -30]
    des = [p for p in jf_todos if p.centroid.y >= -30]
    rapa = [p for p in rapa_todos if p.centroid.x < -107]
    sala = [p for p in rapa_todos if p.centroid.x >= -107]
    return (
        AOI("continente", "continental", _bbox_partes(continente, margen)),
        AOI("juan_fernandez", "juan_fernandez_desventuradas",
            _bbox_partes(juan, margen)),
        AOI("desventuradas", "juan_fernandez_desventuradas",
            _bbox_partes(des, margen)),
        AOI("rapa_nui", "isla_de_pascua", _bbox_partes(rapa, margen)),
        AOI("sala_y_gomez", "isla_de_pascua", _bbox_partes(sala, margen)),
    )


def resumen_mascara(comunas_path: Path) -> dict[str, object]:
    """Describe explícitamente comunas y la zona administrativa código cero."""
    import geopandas as gpd
    import pandas as pd

    g = gpd.read_file(comunas_path)
    if "cod_comuna" not in g:
        raise ValueError(f"{comunas_path}: falta cod_comuna")
    codigos = pd.to_numeric(g["cod_comuna"], errors="raise").astype("int64")
    negativos = sorted(int(x) for x in codigos[codigos < 0].unique())
    if negativos:
        raise ValueError(f"{comunas_path}: códigos administrativos negativos {negativos}")
    return {
        "unidades_geometricas": int(len(g)),
        "comunas_cod_positivo": int((codigos > 0).sum()),
        "zona_sin_demarcar_cod_0": int((codigos == 0).sum()),
        "codigo_fuera_mascara": -1,
        "semantica": "cod_comuna=0 se conserva; -1 significa centro fuera de la máscara",
    }


def seleccionar(texto: str = "todos", comunas_path: Path | None = None) -> tuple[AOI, ...]:
    aois = derivar(comunas_path) if comunas_path else AOIS_FALLBACK
    pedidos = {x.strip().lower() for x in texto.split(",") if x.strip()}
    if not pedidos or "todos" in pedidos:
        return aois
    encontrados = tuple(a for a in aois
                        if a.id in pedidos or a.territorio in pedidos)
    validos = {a.id for a in aois} | {a.territorio for a in aois}
    faltan = pedidos - validos
    if faltan:
        raise ValueError(f"AOIs desconocidas {sorted(faltan)}; válidas: {sorted(validos)}")
    return encontrados


def etiqueta(aoi: AOI) -> str:
    return f"{aoi.territorio}.{aoi.id}"
