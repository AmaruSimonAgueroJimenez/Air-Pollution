"""Selección pura y auditable de producciones MODIS C6.1 coexistentes.

No consulta la red, descarga, borra ni altera los objetos recibidos. El sello
final del filename es producción, no adquisición ni revisión del registro CMR:
https://modaps.modaps.eosdis.nasa.gov/services/about/nomenclature.html
LP DAAC recomienda la producción más reciente para duplicados MCD19A2.061:
https://forum.earthdata.nasa.gov/viewtopic.php?t=5988

En MAIAC, día + tile identifica una unidad diaria *multiórbita*, no una única
pasada. Esta selección no demuestra igualdad científica entre producciones ni
certifica disponibilidad HTTP: el llamador debe descargar/validar la elegida y
fallar si no está disponible, sin volver silenciosamente a una anterior.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import unquote, urlsplit

POLITICA_VERSION = "1.1.0"
TOLERANCIA_ESPACIAL_GRADOS = Decimal("0.000001")
_PRODUCTOS = {"MOD04_3K", "MYD04_3K", "MCD19A2"}
_COLECCIONES = {"6.1": "061", "061": "061"}
_NOMBRE = re.compile(
    r"(?P<producto>MOD04_3K|MYD04_3K|MCD19A2)\.A(?P<dia>\d{7})\."
    r"(?P<unidad>\d{4}|h\d{2}v\d{2})\.(?P<coleccion>\d{3})\."
    r"(?P<produccion>\d{13})\.hdf"
)
_CONCEPTO = re.compile(r"G\d+-[A-Za-z0-9_-]+")


def _fecha_solicitada(valor: date | str) -> date:
    if isinstance(valor, datetime):
        raise ValueError("fecha debe ser un día, no datetime")
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str):
        raise ValueError("fecha debe ser date o YYYY-MM-DD")
    try:
        resultado = date.fromisoformat(valor)
    except ValueError:
        raise ValueError("fecha solicitada inválida") from None
    if resultado.isoformat() != valor:
        raise ValueError("fecha debe usar YYYY-MM-DD")
    return resultado


def _dia_ordinal(texto: str) -> date:
    try:
        anio, ordinal = int(texto[:4]), int(texto[4:])
        resultado = date(anio, 1, 1) + timedelta(days=ordinal - 1)
    except (ValueError, OverflowError):
        raise ValueError("calendario ordinal inválido en filename") from None
    if not 1 <= ordinal <= 366 or resultado.year != anio:
        raise ValueError("calendario ordinal inválido en filename")
    return resultado


def _produccion(texto: str) -> datetime:
    dia = _dia_ordinal(texto[:7])
    try:
        hora = time(int(texto[7:9]), int(texto[9:11]), int(texto[11:13]))
    except ValueError:
        raise ValueError("hora de producción inválida en filename") from None
    return datetime.combine(dia, hora, tzinfo=timezone.utc)


def _utc(valor: Any, campo: str) -> datetime:
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError
        return dt.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        raise ValueError(f"{campo} inválido o sin zona horaria") from None


def _canonico(valor: Any) -> str:
    try:
        return json.dumps(valor, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError):
        raise ValueError("metadatos de identidad no serializables") from None


def _objeto(valor: Any, campo: str) -> Mapping:
    if not isinstance(valor, Mapping):
        raise ValueError(f"{campo} debe ser un objeto de metadatos")
    return valor


def _huella(valor: Any) -> str:
    return hashlib.sha256(_canonico(valor).encode("utf-8")).hexdigest()


def _delta_espacial(valores: list, campo: str | None = None) -> Decimal:
    """Rango máximo de TODOS los candidatos, sin modificar el UMM original.

    Se tolera exclusivamente redondeo de Latitude/Longitude. Estructura, orden
    de vértices y otros campos son exactos; no prueba equivalencia de píxeles.
    Decimal(str(...)) evita aceptar/rechazar por error binario en el borde 1e-6.
    """
    primero = valores[0]
    if campo in {"Latitude", "Longitude"}:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in valores):
            raise ValueError("identidad UMM diferente: coordenada espacial inválida")
        numeros = [Decimal(str(v)) for v in valores]
        limite = 90 if campo == "Latitude" else 180
        if any(not v.is_finite() or abs(v) > limite for v in numeros):
            raise ValueError("identidad UMM diferente: coordenada espacial fuera de rango")
        delta = max(numeros) - min(numeros)
        if delta > TOLERANCIA_ESPACIAL_GRADOS:
            raise ValueError("identidad UMM diferente: delta espacial supera 1e-6 grados")
        return delta
    if isinstance(primero, Mapping):
        if any(not isinstance(v, Mapping) or set(v) != set(primero) for v in valores):
            raise ValueError("identidad UMM diferente: estructura espacial")
        return max((_delta_espacial([v[k] for v in valores], k)
                    for k in sorted(primero)), default=Decimal(0))
    if isinstance(primero, list):
        if any(not isinstance(v, list) or len(v) != len(primero) for v in valores):
            raise ValueError("identidad UMM diferente: estructura espacial")
        return max((_delta_espacial([v[i] for v in valores])
                    for i in range(len(primero))), default=Decimal(0))
    if any(_canonico(v) != _canonico(primero) for v in valores):
        raise ValueError("identidad UMM diferente: campo espacial no coordenada")
    return Decimal(0)


def _filename(granulo: Any) -> str:
    try:
        enlaces = list(granulo.data_links())
    except Exception:
        raise ValueError("no se pudo obtener data_links del gránulo") from None
    nombres = set()
    for enlace in enlaces:
        try:
            uri = urlsplit(enlace)
            nombre = unquote(uri.path.rsplit("/", 1)[-1])
            valido = (uri.scheme in {"https", "http", "s3"} and uri.netloc
                      and not uri.username and not uri.password
                      and _NOMBRE.fullmatch(nombre))
        except (TypeError, ValueError):
            valido = False
        if not valido:
            # Nunca interpolar el enlace: puede contener un token firmado.
            raise ValueError("data_links contiene un filename MODIS inválido")
        nombres.add(nombre)
    if len(nombres) != 1:
        raise ValueError("identidad desconocida: se exige un único filename real")
    return nombres.pop()


@dataclass
class _Candidato:
    objeto: Any
    concept_id: str
    revision_id: int
    filename: str
    unidad: str
    sello: str
    produccion: datetime
    compatibilidad: dict
    validaciones: dict

    def auditar(self, repeticiones: int, coleccion: str) -> dict:
        return {
            "concept_id": self.concept_id,
            "revision_id": self.revision_id,
            "filename": self.filename,
            "produccion_sello": self.sello,
            "produccion_utc": self.produccion.isoformat().replace("+00:00", "Z"),
            "coleccion": coleccion,
            "ocurrencias_bbox": repeticiones,
            "validaciones_metadata": self.validaciones,
            "spatial_extent_sha256": self.compatibilidad["spatial_extent_sha256"],
        }


def _candidato(granulo: Any, producto: str, coleccion: str,
               fecha: date) -> _Candidato:
    if not isinstance(granulo, Mapping):
        raise ValueError("identidad CMR desconocida: gránulo no es Mapping")
    meta = granulo.get("meta", {})
    if not isinstance(meta, Mapping):
        raise ValueError("identidad CMR desconocida")
    cid, revision = meta.get("concept-id"), meta.get("revision-id")
    if not isinstance(cid, str) or not _CONCEPTO.fullmatch(cid):
        raise ValueError("concept_id CMR ausente o inválido")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("revision_id CMR ausente o inválido")
    nombre = _filename(granulo)
    partes = _NOMBRE.fullmatch(nombre).groupdict()
    if partes["producto"] != producto:
        raise ValueError("mezcla de producto o sensor en selección")
    if partes["coleccion"] != coleccion:
        raise ValueError("colección del filename no coincide con la solicitada")
    if _dia_ordinal(partes["dia"]) != fecha:
        raise ValueError("fecha del filename no coincide con la solicitada")
    unidad = partes["unidad"]
    if producto == "MCD19A2":
        if not re.fullmatch(r"h\d{2}v\d{2}", unidad) or \
                int(unidad[1:3]) >= 36 or int(unidad[4:6]) >= 18:
            raise ValueError("tile MAIAC inválido")
        nominal = datetime.combine(fecha, time.min, tzinfo=timezone.utc)
    else:
        try:
            if not re.fullmatch(r"\d{4}", unidad):
                raise ValueError
            nominal = datetime.combine(
                fecha, time(int(unidad[:2]), int(unidad[2:])),
                tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("hora nativa MODIS inválida") from None
    produccion = _produccion(partes["produccion"])
    if produccion < nominal:
        raise ValueError("producción anterior a la adquisición declarada")

    umm = granulo.get("umm", {})
    if not isinstance(umm, Mapping):
        raise ValueError("UMM inválido")
    proveedor = meta.get("provider-id") or cid.split("-", 1)[1]
    if proveedor != cid.split("-", 1)[1]:
        raise ValueError("proveedor CMR contradice concept_id")
    collection_cid = meta.get("collection-concept-id")
    if collection_cid is not None and (
            not isinstance(collection_cid, str) or
            not re.fullmatch(r"C\d+-[A-Za-z0-9_-]+", collection_cid)):
        raise ValueError("collection_concept_id inválido")
    compatibilidad = {"proveedor": proveedor,
                      "collection_concept_id": collection_cid}
    validaciones = {}
    pdt = _objeto(umm.get("DataGranule", {}), "DataGranule").get("ProductionDateTime")
    validaciones["production_datetime_presente"] = pdt is not None
    if pdt is not None and _utc(pdt, "ProductionDateTime") != produccion:
        raise ValueError("ProductionDateTime contradice el sello del filename")
    referencia = umm.get("CollectionReference")
    validaciones["collection_reference_presente"] = referencia is not None
    if referencia is not None:
        if not isinstance(referencia, Mapping) or \
                referencia.get("ShortName") != producto or \
                _COLECCIONES.get(str(referencia.get("Version"))) != coleccion:
            raise ValueError("CollectionReference contradice producto/colección")
    temporal = _objeto(umm.get("TemporalExtent", {}), "TemporalExtent").get("RangeDateTime")
    validaciones["temporal_extent_presente"] = temporal is not None
    if temporal is not None:
        temporal = _objeto(temporal, "RangeDateTime")
        inicio = _utc(temporal.get("BeginningDateTime"), "BeginningDateTime")
        fin = _utc(temporal.get("EndingDateTime"), "EndingDateTime")
        if inicio.date() != fecha or fin < inicio or \
                (producto != "MCD19A2" and inicio != nominal):
            raise ValueError("TemporalExtent contradice la identidad nativa")
        compatibilidad["temporal"] = (inicio.isoformat(), fin.isoformat())
    else:
        compatibilidad["temporal"] = None
    plataformas = umm.get("Platforms")
    validaciones["platforms_presente"] = plataformas is not None
    if plataformas is not None:
        esperadas = ({"Terra", "Aqua"} if producto == "MCD19A2"
                     else {"Terra" if producto == "MOD04_3K" else "Aqua"})
        if not isinstance(plataformas, list) or not plataformas or \
                any(not isinstance(p, Mapping) or p.get("ShortName") not in esperadas
                    for p in plataformas):
            raise ValueError("plataforma UMM contradice el producto")
        compatibilidad["plataformas_sha256"] = _huella(sorted(_canonico(p) for p in plataformas))
    else:
        compatibilidad["plataformas_sha256"] = None
    espacio = umm.get("SpatialExtent")
    validaciones["spatial_extent_presente"] = espacio is not None
    compatibilidad["spatial_extent_sha256"] = _huella(espacio) if espacio is not None else None
    return _Candidato(granulo, cid, revision, nombre, unidad,
                      partes["produccion"], produccion, compatibilidad, validaciones)


def seleccionar_produccion_nativa(
        granulos: Iterable, *, producto: str, coleccion: str,
        fecha: date | str) -> tuple[list, dict]:
    """Elige el máximo sello único por unidad nativa, conservando los objetos.

    La entrada debe proceder de una consulta CMR acotada a una colección y día.
    C6.1 admite las grafías CMR ``6.1`` y ``061``, ambas filename ``061``.
    Metadatos UMM presentes se contrastan; los ausentes se anotan, no se inventan.
    Coordenadas UMM admiten como máximo 1e-6 grados de rango entre todos los
    candidatos, con la misma estructura y demás campos exactos. Se auditan los
    hashes originales y el delta; nunca se alteran coordenadas científicas.
    """
    if not isinstance(producto, str) or producto not in _PRODUCTOS:
        raise ValueError("producto no soportado por esta política")
    canonica = _COLECCIONES.get(coleccion) if isinstance(coleccion, str) else None
    if canonica is None:
        raise ValueError("colección no soportada: esta política requiere C6.1")
    dia = _fecha_solicitada(fecha)
    candidatos: dict[str, _Candidato] = {}
    ocurrencias: Counter = Counter()
    for granulo in granulos:
        candidato = _candidato(granulo, producto, canonica, dia)
        previo = candidatos.get(candidato.concept_id)
        if previo is not None and (
                previo.auditar(1, canonica) != candidato.auditar(1, canonica) or
                previo.compatibilidad != candidato.compatibilidad):
            raise ValueError("mismo concept_id con metadatos contradictorios")
        candidatos.setdefault(candidato.concept_id, candidato)
        ocurrencias[candidato.concept_id] += 1
    proveedores = {_canonico(c.compatibilidad["proveedor"])
                   for c in candidatos.values()}
    colecciones_cmr = {_canonico(c.compatibilidad["collection_concept_id"])
                      for c in candidatos.values()}
    if len(proveedores) > 1 or len(colecciones_cmr) > 1:
        raise ValueError("mezcla de proveedor o colección-concepto CMR")
    por_unidad: dict[str, list[_Candidato]] = defaultdict(list)
    for candidato in candidatos.values():
        por_unidad[candidato.unidad].append(candidato)
    elegidos, grupos = [], []
    for unidad, miembros in sorted(por_unidad.items()):
        miembros.sort(key=lambda c: (c.produccion, c.concept_id, c.filename))
        sin_espacio = lambda c: {k: v for k, v in c.compatibilidad.items()
                                 if k != "spatial_extent_sha256"}
        if any(sin_espacio(c) != sin_espacio(miembros[0]) or
               c.validaciones != miembros[0].validaciones for c in miembros[1:]):
            raise ValueError("candidatos de la misma unidad con identidad UMM diferente")
        delta_espacial = _delta_espacial([
            c.objeto.get("umm", {}).get("SpatialExtent") for c in miembros])
        # Ni siquiera los empates de producciones anteriores se descartan
        # arbitrariamente: requieren aclarar sus identidades antes de proceder.
        if len({c.produccion for c in miembros}) != len(miembros):
            raise ValueError("empate de producción entre distintos concept_ids")
        elegido = miembros[-1]
        elegidos.append(elegido.objeto)
        identidad = {"producto": producto, "coleccion": canonica,
                     "fecha": dia.isoformat(), "unidad": unidad,
                     "tipo": ("tile_diario_multiorbita" if producto == "MCD19A2"
                              else "swath_5min")}
        grupos.append({
            "identidad_nativa": identidad,
            "compatibilidad_metadata": {
                **sin_espacio(miembros[0]),
                "espacial": {
                    "delta_maximo_grados": float(delta_espacial),
                    "tolerancia_grados": float(TOLERANCIA_ESPACIAL_GRADOS),
                    "estructura_orden_y_campos_no_coordenada_exactos": True,
                    "hashes_originales_por_candidato": True,
                },
            },
            "candidatos": [c.auditar(ocurrencias[c.concept_id], canonica)
                           for c in miembros],
            "elegido": elegido.concept_id,
            "motivo": "maximo_unico_sello_produccion_filename",
            "superseded": [{"concept_id": c.concept_id,
                            "motivo": "produccion_anterior_misma_unidad_nativa"}
                           for c in miembros[:-1]],
        })
    auditoria = {
        "schema": "airpollution.native-production-selection.v1",
        "politica": {"nombre": "maximo_unico_sello_produccion_filename",
                     "version": POLITICA_VERSION,
                     "revision_cmr_no_es_criterio": True,
                     "tolerancia_espacial_umm_grados": float(TOLERANCIA_ESPACIAL_GRADOS),
                     "fallback_produccion_anterior": False,
                     "equivalencia_orbitas_maiac_no_demostrada": True},
        "producto": producto, "coleccion": canonica, "fecha": dia.isoformat(),
        "granulos_entrada": sum(ocurrencias.values()),
        "candidatos_unicos": len(candidatos),
        "duplicados_bbox": sum(ocurrencias.values()) - len(candidatos),
        "seleccionados": len(elegidos),
        "superseded": len(candidatos) - len(elegidos),
        "grupos": grupos,
    }
    return elegidos, auditoria
