#!/usr/bin/env python3
"""Observaciones nativas por hora del informe público DMC RE1022.

No importa _common ni crea rutas al importarse. --check-api es sólo en memoria;
las escrituras necesitan --download y DiskGuard. No rellena horas ni reparte RR06.
La zona horaria del informe HTML no está documentada: se conserva sin convertir.
"""
from __future__ import annotations

import argparse
import calendar
import gzip
import hashlib
import http.cookiejar
import io
import json
import math
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://climatologia.meteochile.gob.cl"
CATALOG_URL = BASE + "/application/informacion/buscadorEstaciones"
REPORT_PATH = "/application/mensualb/hojaMensualDatos/{code}/{year}/{month}"
DOC_URL = BASE + "/application/requerimiento/producto/RE1022"
MAX_RESPONSE = 32 * 1024 * 1024
SCHEMA_VERSION = 1
SOURCE = "DMC_RE1022_PUBLIC"
TIMEZONE = "unconfirmed"
MONTH_NAMES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
HOURLY_REQUIRED = ("Ts", "relative_humidity", "wind_direction_instant", "wind_speed_instant", "QFE", "QFF", "QNH")
FIELD_ELEMENT_IDS = {"Ts": 26, "relative_humidity": 66, "wind_direction_instant": 28,
                     "wind_speed_instant": 28, "QFE": 64, "QFF": 65, "QNH": 70}
METADATA_CAUTIONS = {"coordinates_valid_for_historical_dates": "unconfirmed",
                     "historical_station_moves_not_resolved": True}
INVENTORY_IDS = {26, 28, 57, 64, 65, 66, 70}
RAW_COLUMNS = (
    "day", "hour", "wind_direction_instant", "wind_speed_instant", "Ts", "Td",
    "TMin", "TMax", "relative_humidity", "WW", "VV", "visibility_reigning",
    "visibility_minimum", "QFE", "QFF", "QNH", "N", "Nh", "CL", "CM", "CH",
    "Hs1", "RR06",
)
LEAF_COLUMNS = ("DD Inst", "FF Inst", "Ts", "Td", "TMin", "TMax", "WW", "VV",
                "Reinante", "Mínima", "Qfe", "Qff", "Qnh", "N", "Nh", "CL",
                "CM", "CH", "Hs1")
GROUP_COLUMNS = ("Día", "Hora", "Viento ( ° - kt.)", "Temperatura (°c)", "Humedad ( % )",
                 "Fenómeno y Visibilidad ( mts )", "Presión (hPa)", "Nubosidad ( clave )", "RR 06 ( mm )")
VARIABLES = {
    "wind_direction_instant": {"unit": "degree", "period": "instantaneous"},
    "wind_speed_instant": {"unit": "kt", "period": "instantaneous"},
    "Ts": {"unit": "degC", "period": "observation", "description": "Air dry bulb temperature"},
    "Td": {"unit": "degC", "period": "observation", "description": "Dew point"},
    "relative_humidity": {"unit": "%", "period": "observation"},
    "QFE": {"unit": "hPa", "description": "Pressure at station elevation"},
    "QFF": {"unit": "hPa", "description": "Pressure reduced to mean sea level"},
    "QNH": {"unit": "hPa", "description": "Pressure reduced using ICAO standard atmosphere"},
    "RR06": {"unit": "mm", "period": "6 hours", "description": "Not hourly precipitation"},
}


class SourceError(RuntimeError):
    """Malformed, unavailable or unexpected public source response."""


class AccessBlocked(SourceError):
    """A login or access restriction must never be treated as empty data."""


class MissingSourceError(SourceError):
    """A station/period has no product; other stations remain eligible."""


class TransientSourceError(SourceError):
    """Timeout, transport failure, rate limit or temporary server failure."""


def retry_after_seconds(raw):
    """HTTP Retry-After may be delay seconds or an absolute HTTP date."""
    try:
        delay = float(raw)
    except (ValueError, TypeError):
        try:
            moment = parsedate_to_datetime(raw)
            if moment.tzinfo is None:
                return 0.0
            delay = (moment - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, AttributeError, OverflowError):
            return 0.0
    return max(0.0, delay) if math.isfinite(delay) else 0.0


class Tables(HTMLParser):
    """Small stdlib table parser; retains text and original cell attributes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.stack = []
        self.cell = None
        self.inputs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input":
            self.inputs.append(attrs)
        elif tag == "table":
            self.stack.append([])
        elif tag == "tr" and self.stack:
            self.stack[-1].append([])
        elif tag in ("td", "th") and self.stack:
            self.cell = {"text_parts": [], "attributes": attrs}
        elif tag == "br" and self.cell is not None:
            self.cell["text_parts"].append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text_parts"].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            if self.stack and self.stack[-1]:
                self.stack[-1][-1].append({
                    "text": " ".join("".join(self.cell["text_parts"]).split()),
                    "attributes": self.cell["attributes"],
                })
            self.cell = None
        elif tag == "table" and self.stack:
            self.tables.append(self.stack.pop())


def parse_tables(text):
    parser = Tables()
    parser.feed(text)
    return parser


def values(row):
    return [cell["text"] for cell in row]


def source_checks(text):
    low = text.casefold()
    if "producto para usuarios registrados" in low or "servicio ha sido bloqu" in low:
        raise AccessBlocked("La DMC exige acceso registrado para esta respuesta; no se descargaron datos.")


def parse_catalog(text):
    source_checks(text)
    stations = {}
    for table in parse_tables(text).tables:
        if not table or "Código Nacional" not in values(table[0]):
            continue
        headers = values(table[0])
        if not {"Nombre", "Latitud", "Longitud", "Altitud (Mts)"}.issubset(headers):
            continue
        for row in table[1:]:
            if len(row) != len(headers):
                raise SourceError("Cambió el esquema del catastro DMC.")
            record = dict(zip(headers, values(row)))
            code = record["Código Nacional"]
            if not re.fullmatch(r"\d{6}", code):
                raise SourceError("Código nacional inesperado en el catastro DMC.")
            previous = stations.setdefault(code, {})
            for key in ("Nombre", "Latitud", "Longitud", "Altitud (Mts)"):
                if key in previous and previous[key] != record[key]:
                    raise SourceError(f"Metadatos contradictorios para estación {code}.")
            previous.update(record)
    if not stations:
        raise SourceError("El catastro nacional no devolvió estaciones; no se sustituye por la red actual.")
    return [{"code": code, "source_metadata": stations[code], **METADATA_CAUTIONS} for code in sorted(stations)]


def parse_inventory(text):
    source_checks(text)
    records = []
    found = False
    element_rows = 0
    for table in parse_tables(text).tables:
        if not table or values(table[0])[:3] != ["Id", "Nombre", "Descripción"]:
            continue
        found = True
        for row in table[1:]:
            raw = values(row)
            # A replaced invalid byte inside an id, year or count cell makes the
            # row undeterminable; it must neither vanish nor stop the run.
            if any("\ufffd" in cell for cell in raw[:1] + raw[3:6]):
                raise MissingSourceError("Bytes inválidos dentro del inventario DMC; inventario indeterminado, pendiente de reintento.")
            if not raw or not raw[0].isdigit():
                continue
            element_rows += 1
            element = int(raw[0])
            if element not in INVENTORY_IDS:
                continue
            if len(raw) != 6:
                raise SourceError("Cambió el esquema de una fila objetivo del inventario DMC.")
            # The official inventory uses three literal dots for an undeclared
            # range/count. Preserve that uncertainty; it is not zero or no data.
            if raw[3:6] == [".", ".", "."]:
                records.append({"element_id": element, "name": raw[1], "description": raw[2],
                                "first_year": None, "last_year": None, "source_count": None,
                                "inventory_status": "pending_unavailable_range",
                                "retryable": True, "raw_cells": row})
                continue
            if not all(re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", x) for x in raw[3:6]):
                raise SourceError("Años inesperados en el inventario DMC.")
            first, last, count = (int(x.replace(",", "")) for x in raw[3:6])
            if not (1 <= first <= last <= 9999):
                raise SourceError("Rango de años imposible en el inventario DMC.")
            records.append({"element_id": element, "name": raw[1], "description": raw[2],
                            "first_year": first, "last_year": last, "source_count": count,
                            "raw_cells": row})
    if not found:
        raise MissingSourceError("No se encontró el inventario de elementos de la estación.")
    # Even precipitation-only stations list their elements. A table without
    # element rows is undetermined, not proof of no hourly variables.
    if not element_rows:
        raise MissingSourceError("Inventario DMC sin filas de elementos; inventario indeterminado, pendiente de reintento.")
    return records


def numeric(raw):
    if raw == "":
        return {"value": None, "parse_status": "empty_source"}
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", raw):
        return {"value": float(raw.replace(",", ".")), "parse_status": "numeric"}
    return {"value": None, "parse_status": "literal_source"}


def parse_report(text, code, year, month, start=None, end=None):
    source_checks(text)
    if not re.fullmatch(r"\d{6}", str(code)):
        raise SourceError("Código de estación no válido.")
    headings = re.findall(r'<div\b[^>]*\bid\s*=\s*["\']cabezera["\'][^>]*>(.*?)</div>', text, re.S | re.I)
    if len(headings) != 1 or "Hoja Mensual de Datos" not in headings[0]:
        # This explicit portal error is not an empty report or proof of no data.
        errors = re.findall(r'<h5\b[^>]*class\s*=\s*["\'][^"\']*alert-danger[^"\']*["\'][^>]*>(.*?)</h5>', text, re.S | re.I)
        if (not headings and re.search(r'<!--\s*Requerimiento\s*:\s*RE004\s*-->', text)
                and "Su solicitud no se ha podido procesar" in text
                and any(" ".join(re.sub(r"<[^>]+>", " ", item).split()) == "No ha sido posible recuperar datos de las Observaciones" for item in errors)):
            raise MissingSourceError("DMC RE004: observaciones no recuperables en esta consulta; pendiente de reintento.")
        raise SourceError("Respuesta inesperada: no es un informe público RE1022.")
    # The public report identifies the station in its title. Reject a different one.
    if not re.search(r"\(" + re.escape(str(code)) + r"\)", headings[0]):
        raise SourceError("El informe no identifica la estación solicitada.")
    title_text = " ".join(re.sub(r"<[^>]+>", " ", headings[0]).split())
    if not re.search(r"\b" + MONTH_NAMES[month - 1] + r"\s+de\s+" + str(year) + r"\b", title_text, re.I):
        raise SourceError("El mes/año del título DMC no coincide con la consulta.")
    by_time = {}
    empty_times = set()
    tables_found = 0
    duplicates = 0
    for table in parse_tables(text).tables:
        if len(table) < 2 or values(table[0])[:2] != ["Día", "Hora"]:
            continue
        tables_found += 1
        if tuple(x.replace(" ", "").casefold() for x in values(table[0])) != tuple(x.replace(" ", "").casefold() for x in GROUP_COLUMNS):
            raise SourceError("Cambió el encabezado de unidades RE1022.")
        if tuple(values(table[1])) != LEAF_COLUMNS:
            raise SourceError("Cambió el encabezado RE1022; se detuvo antes de interpretar columnas.")
        for cells in table[2:]:
            if len(cells) != len(RAW_COLUMNS):
                raise SourceError("Cambió el número de columnas RE1022.")
            raw = dict(zip(RAW_COLUMNS, values(cells)))
            if not re.fullmatch(r"\d{2}:00", raw["hour"]):
                raise SourceError("Hora no nativa de 60 minutos en RE1022.")
            try:
                moment = datetime(year, month, int(raw["day"]), int(raw["hour"][:2]))
            except ValueError as exc:
                raise SourceError("Fecha/hora imposible en RE1022.") from exc
            if (start and moment.date() < start) or (end and moment.date() > end):
                continue
            timestamp = moment.isoformat()
            if not any(raw[key] for key in VARIABLES):
                empty_times.add(timestamp)
                continue
            record = {
                "station_code": str(code), "timestamp_source": timestamp,
                "source_timezone": TIMEZONE, "timestamp_utc": None,
                "fields": {key: dict(numeric(raw[key]), raw=raw[key], unit=spec["unit"],
                                      source_qc=None) for key, spec in VARIABLES.items()},
                "source_qc_available": False,
                "raw_cells": dict(zip(RAW_COLUMNS, cells)),
            }
            if timestamp in by_time:
                if values(list(by_time[timestamp]["raw_cells"].values())) != values(cells):
                    raise SourceError("Filas DMC duplicadas con valores contradictorios.")
                duplicates += 1
            else:
                by_time[timestamp] = record
    if not tables_found:
        raise MissingSourceError("No hay una tabla RE1022 verificable; se conserva como pendiente.")
    rows = [by_time[key] for key in sorted(by_time)]
    return rows, {"source_empty_slots": len(empty_times - by_time.keys()),
                  "duplicate_display_rows_removed": duplicates,
                  "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                  "timezone": TIMEZONE, "source_qc_available": False}


class PublicDMC:
    def __init__(self, guard=None, timeout=20, interval=1.0, retries=3, request_gate=None):
        self.guard, self.timeout, self.interval, self.retries = guard, timeout, interval, retries
        self.request_gate = request_gate
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.last_request = 0.0
        self.last_response_sha256 = None

    def fetch(self, url, data=None, invalid_utf8="strict"):
        if not url.startswith(BASE + "/"):
            raise SourceError("Sólo se permiten consultas al portal oficial DMC.")
        for attempt in range(self.retries):
            if self.guard:
                self.guard.check()
            if self.request_gate:
                self.request_gate.wait_turn(before_start=self.guard.check if self.guard else None)
            else:
                delay = self.interval - (time.monotonic() - self.last_request)
                if delay > 0:
                    time.sleep(delay)
            self.last_request = time.monotonic()
            request = urllib.request.Request(url, data=data, headers={
                "User-Agent": "Air-Pollution meteorological-research/1.0 (DMC public RE1022; one supervisor; globally rate-limited)"})
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    if urllib.parse.urlsplit(response.url).hostname != urllib.parse.urlsplit(BASE).hostname:
                        raise AccessBlocked("El portal redirigió fuera del origen DMC.")
                    if self.guard:
                        body = (self.guard.read_response(response, cancel_check=self.request_gate.raise_if_cancelled)
                                if self.request_gate else self.guard.read_response(response))
                    else:
                        size = response.headers.get("Content-Length")
                        if size and int(size) > MAX_RESPONSE:
                            raise SourceError("Respuesta DMC supera 32 MiB.")
                        body = response.read(MAX_RESPONSE + 1)
                    if len(body) > MAX_RESPONSE:
                        raise SourceError("Respuesta DMC supera 32 MiB.")
                    if self.request_gate:
                        self.request_gate.raise_if_cancelled()
                    self.last_response_sha256 = hashlib.sha256(body).hexdigest()
                    return body.decode("utf-8", invalid_utf8)
            except urllib.error.HTTPError as exc:
                retry_after = retry_after_seconds(exc.headers.get("Retry-After", 0) if exc.headers else 0)
                exc.close()
                if exc.code in (401, 403):
                    raise AccessBlocked(f"Acceso DMC rechazado (HTTP {exc.code}).") from None
                if exc.code == 404:
                    raise MissingSourceError("No existe producto DMC para la estación/período (HTTP 404).") from None
                if exc.code not in (429, 500, 502, 503, 504):
                    error_class = TransientSourceError if exc.code in (429, 500, 502, 503, 504) else SourceError
                    raise error_class(f"DMC HTTP {exc.code}.") from None
                if self.request_gate:
                    # A server cooldown applies to every client, including after
                    # this request's last attempt. Never shorten Retry-After.
                    self.request_gate.backoff(max(retry_after, min(30, 2 ** (attempt + 1))))
                elif attempt + 1 < self.retries:
                    time.sleep(min(30, max(retry_after, 2 ** (attempt + 1))))
                if attempt + 1 == self.retries:
                    raise TransientSourceError(f"DMC HTTP {exc.code}.") from None
            except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
                if attempt + 1 == self.retries:
                    raise TransientSourceError(f"No se pudo leer DMC: {type(exc).__name__}.") from None
                if self.request_gate:
                    self.request_gate.backoff(2 ** (attempt + 1))
                else:
                    time.sleep(2 ** (attempt + 1))
        raise SourceError("Consulta DMC agotó los reintentos.")

    def catalog(self):
        initial = self.fetch(CATALOG_URL)
        parser = parse_tables(initial)
        tokens = [item["value"] for item in parser.inputs if item.get("name") == "csrf" and "value" in item]
        if not tokens:
            raise SourceError("El formulario oficial de catastro no entregó CSRF.")
        params = {"csrf": tokens[-1], "conDatos": "0", "operativas": "2", "nombreEstacion": ""}
        text = self.fetch(CATALOG_URL, urllib.parse.urlencode(params).encode())
        return parse_catalog(text)

    def inventory(self, code):
        url = BASE + f"/application/informacion/fichaDeEstacion/{code}"
        # Some UTF-8 pages carry Latin-1 bytes in free-text calibration logs
        # (330019). They are replaced and counted; parse_inventory refuses a
        # replacement inside an id, year or count cell.
        self.last_inventory_info = self.last_response_sha256 = None
        text = self.fetch(url, invalid_utf8="replace")
        self.last_inventory_info = {"source_url": url, "invalid_utf8_replacements": text.count("\ufffd"),
                                    "response_sha256": self.last_response_sha256}
        try:
            return parse_inventory(text)
        except SourceError as exc:
            raise type(exc)(f"{exc} station={code}; URL={url}; response_utf8_sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}") from exc

    def report(self, code, year, month, start=None, end=None):
        url = BASE + REPORT_PATH.format(code=code, year=year, month=month)
        text = self.fetch(url)
        try:
            return parse_report(text, code, year, month, start, end), url
        except SourceError as exc:
            raise type(exc)(f"{exc} URL={url}; response_utf8_sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}") from exc


def json_bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def compressed_json(payload):
    return gzip.compress(json_bytes(payload), compresslevel=6, mtime=0)


def month_windows(start, end):
    current = start.replace(day=1)
    while current <= end:
        last = current.replace(day=calendar.monthrange(current.year, current.month)[1])
        yield current.year, current.month, max(start, current), min(end, last)
        current = (last + timedelta(days=1)).replace(day=1)


def validate_artifact(path, expected_sha, row_count, start, end, *, expected_station=None):
    """Read back both checksum and compressed records before advancing a manifest."""
    with path.open("rb") as stream:
        compressed = stream.read(MAX_RESPONSE + 1)
    if len(compressed) > MAX_RESPONSE:
        raise SourceError("Archivo comprimido excede el límite de 32 MiB de verificación.")
    if hashlib.sha256(compressed).hexdigest() != expected_sha:
        raise SourceError("SHA del archivo publicado no coincide.")
    # Hash and decompress the same bounded bytes, not two separate path reads.
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        expanded = stream.read(128 * 1024 * 1024 + 1)
    if len(expanded) > 128 * 1024 * 1024:
        raise SourceError("Archivo derivado excede el límite de memoria de verificación.")
    payload = json.loads(expanded)
    if expected_station is not None:
        if (not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION
                or payload.get("source") != SOURCE or not isinstance(payload.get("station"), dict)
                or payload["station"].get("code") != expected_station
                or payload.get("variables") != VARIABLES or payload.get("source_timezone") != TIMEZONE
                or not isinstance(payload.get("rows"), list)):
            raise SourceError("Identidad o esquema del artefacto no coincide con DMC.")
    rows = payload["rows"]
    if len(rows) != row_count or not rows:
        raise SourceError("Recuento inválido al releer el archivo publicado.")
    seen = set()
    for row in rows:
        moment = datetime.fromisoformat(row["timestamp_source"])
        if moment.tzinfo is not None or moment.minute or moment.second or moment.microsecond or not (start <= moment.date() <= end):
            raise SourceError("Timestamp fuera de la ventana o con zona horaria inventada.")
        if row["timestamp_source"] in seen:
            raise SourceError("Timestamp duplicado en archivo publicado.")
        seen.add(row["timestamp_source"])
        if expected_station is not None:
            if (row.get("station_code") != expected_station or row.get("source_timezone") != TIMEZONE
                    or "timestamp_utc" not in row or row["timestamp_utc"] is not None
                    or row.get("source_qc_available") is not False
                    or moment.isoformat() != row["timestamp_source"]
                    or not isinstance(row.get("fields"), dict) or set(row["fields"]) != set(VARIABLES)):
                raise SourceError("Campos nativos incompletos en el artefacto DMC.")
            for key, field in row["fields"].items():
                if (not isinstance(field, dict) or field.get("unit") != VARIABLES[key]["unit"]
                        or "source_qc" not in field or field["source_qc"] is not None
                        or not isinstance(field.get("raw"), str)
                        or field.get("parse_status") != numeric(field["raw"])["parse_status"]):
                    raise SourceError("Unidad, valor fuente o QC nativo no coincide con DMC.")
                value = field["value"]
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                    raise SourceError("Valor no numérico finito en el artefacto DMC.")
                if value != numeric(field["raw"])["value"]:
                    raise SourceError("Valor no coincide con el token fuente nativo.")
    return rows


def _guard_boundary(guard):
    return getattr(guard, "check_boundary", guard.check)()


def final_verify(output_root, guard, *, inventory_unconfirmed_stations=()):
    """Exhaustive local readback; no requests, imputation or scientific QC.

    Previous artifacts remain published until a candidate passes readback and
    a fresh non-loss comparison. All compressed versions are retained.
    """
    root = Path(output_root).resolve()
    _guard_boundary(guard)
    counts = {key: 0 for key in ("manifests_checked", "artifacts_verified", "artifacts_failed",
                                  "pending_no_artifact", "months_complete", "months_pending",
                                  "nonlosing_rejections")}
    station = None
    inventory_unconfirmed = set(inventory_unconfirmed_stations)
    paths = sorted((root / "estaciones").glob("*/*.manifest.json"))
    for path in paths:
        if path.parent.name != station:
            station = path.parent.name
            _guard_boundary(guard)
        guard.check()
        counts["manifests_checked"] += 1
        manifest = None
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise SourceError("Manifiesto excede el límite de lectura.")
            manifest = json.loads(raw)
            if not isinstance(manifest, dict):
                raise SourceError("El manifiesto no es un objeto JSON.")
            candidate = manifest.get("verification_candidate", manifest)
            if not isinstance(candidate, dict):
                raise SourceError("El candidato no es un objeto JSON.")
            name = candidate.get("artifact_name")
            if not name:
                counts["pending_no_artifact"] += 1
                counts["months_pending"] += 1
                missing = dict(manifest, status="pending_no_artifact", verification_status="failed",
                               verification_error="No artifact_name", coverage_complete=False,
                               available_variable_coverage_complete=False, retryable=True)
                guard.write_atomic_bytes(path, json_bytes(missing))
                continue
            if (Path(name).name != name or not name.endswith(".json.gz")
                    or candidate.get("schema_version") != SCHEMA_VERSION
                    or candidate.get("source") != SOURCE
                    or candidate.get("station_code") != station
                    or path.name != f"{candidate['year']:04d}-{candidate['month']:02d}.manifest.json"):
                raise SourceError("Identidad o nombre de manifiesto no válido.")
            start, end = date.fromisoformat(candidate["requested_start"]), date.fromisoformat(candidate["requested_end"])
            if start > end or (start.year, start.month) != (candidate["year"], candidate["month"]) or (end.year, end.month) != (candidate["year"], candidate["month"]):
                raise SourceError("Ventana mensual inconsistente.")
            rows = validate_artifact(path.parent / name, candidate["artifact_sha256"],
                                     candidate["row_count"], start, end, expected_station=station)
            if "verification_candidate" in manifest:
                previous_name = manifest.get("artifact_name")
                if not previous_name or Path(previous_name).name != previous_name:
                    raise SourceError("Referencia previa no válida.")
                previous = validate_artifact(path.parent / previous_name, manifest["artifact_sha256"],
                           manifest["row_count"], start, end, expected_station=station)
                if not nonlosing(rows, previous):
                    counts["nonlosing_rejections"] += 1
                    raise SourceError("El candidato pierde observaciones frente al archivo previo recién verificado.")
            expected = ((end - start).days + 1) * 24
            fields = {key: sum(row["fields"][key]["value"] is not None for row in rows) for key in VARIABLES}
            required = candidate.get("hourly_fields_expected_from_inventory", HOURLY_REQUIRED)
            if not isinstance(required, list) and not isinstance(required, tuple):
                raise SourceError("Inventario de campos inválido.")
            if len(set(required)) != len(required) or any(key not in HOURLY_REQUIRED for key in required):
                raise SourceError("Inventario de campos desconocido.")
            inventory_confirmed = (station not in inventory_unconfirmed
                                   and not candidate.get("inventory_pending_element_ids"))
            complete = inventory_confirmed and len(rows) == expected and bool(required) and all(fields[key] == expected for key in required)
            # A failed/empty/non-loss refresh remains pending even if the older
            # retained artifact alone is complete. Only its integrity is verified.
            promotable = candidate.get("status") in {"pending_verification", "downloaded_complete", "pending_partial"}
            if not promotable:
                complete = False
            verified = dict(candidate, verification_status="verified_operational",
                            verified_at_utc=datetime.now(timezone.utc).isoformat(),
                            valid_counts=fields, expected_hour_slots=expected,
                            coverage_complete=inventory_confirmed and len(rows) == expected and all(fields[key] == expected for key in HOURLY_REQUIRED),
                            available_variable_coverage_complete=complete,
                            pressure_coverage_complete=all(fields[key] == expected for key in ("QFE", "QFF", "QNH")),
                            status="downloaded_complete" if complete else "pending_partial" if promotable else candidate.get("status"),
                            retryable=not complete)
            if station in inventory_unconfirmed:
                verified["inventory_verification_status"] = "unconfirmed_this_run"
            if "verification_candidate" in manifest:
                verified["retained_previous_artifact"] = {key: manifest[key] for key in ("artifact_name", "artifact_sha256", "row_count")}
            guard.write_atomic_bytes(path, json_bytes(verified))
            counts["artifacts_verified"] += 1
            counts["months_complete" if complete else "months_pending"] += 1
        except (OSError, ValueError, TypeError, KeyError, SourceError, EOFError, zlib.error) as exc:
            counts["artifacts_failed"] += 1
            counts["months_pending"] += 1
            if isinstance(manifest, dict):
                failed = dict(manifest, status="pending_verification_failed", verification_status="failed",
                              verification_error=type(exc).__name__ + ": " + str(exc), retryable=True,
                              coverage_complete=False, available_variable_coverage_complete=False)
                guard.write_atomic_bytes(path, json_bytes(failed))
    _guard_boundary(guard)
    return {**counts, "status": "verified_with_pending" if counts["months_pending"] else "verified_operational",
            "scientific_qc_performed": False, "requests_performed": 0,
            "scope": "all_station_month_manifests_present_at_final_pass_start"}


def existing_rows(root, manifest_path, start, end):
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = manifest["artifact_name"]
        if Path(name).name != name:
            raise SourceError("Nombre de artefacto inseguro en manifiesto.")
        rows = validate_artifact(manifest_path.parent / name, manifest["artifact_sha256"], manifest["row_count"], start, end)
        return manifest, rows
    except (OSError, ValueError, TypeError, KeyError, SourceError):
        return None, []


def verified_existing(path, manifest_path, start, end):
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = validate_artifact(path, manifest["artifact_sha256"], manifest["row_count"], start, end)
        return _complete_validated_rows(manifest, rows, start, end)
    except (OSError, ValueError, TypeError, KeyError, SourceError):
        return False


def _complete_validated_rows(manifest, rows, start, end):
    """Decide completeness only for rows just read and validated in this job.

    No persisted or cross-operation validation cache. The caller still gates
    reuse on today's confirmed station inventory.
    """
    try:
        if not manifest or manifest.get("status") != "downloaded_complete" or manifest.get("requested_start") != str(start) or manifest.get("requested_end") != str(end):
            return False
        if end.year == date.today().year and end.month == date.today().month:
            return False
        if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("row_count", 0) < 1:
            return False
        expected = ((end - start).days + 1) * 24
        required = manifest.get("hourly_fields_expected_from_inventory", HOURLY_REQUIRED)
        return len(rows) == expected and bool(required) and all(row["fields"][key]["value"] is not None for row in rows for key in required)
    except (OSError, ValueError, TypeError, KeyError, SourceError):
        return False


def nonlosing(candidate, previous):
    by_time = {row["timestamp_source"]: row for row in candidate}
    for old in previous:
        new = by_time.get(old["timestamp_source"])
        if new is None:
            return False
        if any(old["fields"][key]["value"] is not None and new["fields"][key]["value"] is None for key in VARIABLES):
            return False
    return True


def _local_months(folder):
    """Only existence for priority; completeness still needs fresh read/hash/QC.

    Manifests of errors/empty months, corrupt files and orphaned artifacts all
    go to review. A failed earlier attempt never delays a nationally new month.
    Atomic temporary names are also evidence; no content is read here.
    """
    try:
        names = [path.name for path in folder.iterdir()]
    except FileNotFoundError:
        return set()
    months = set()
    for name in names:
        match = re.match(r"^\.?(\d{4})-(\d{2})(?:\.|$)", name)
        if match and 1 <= int(match[2]) <= 12:
            months.add((int(match[1]), int(match[2])))
    return months


FAST_SCHEDULE_POLICY = "fast_retry_stations_first_skip_stable_historical_review"
FAST_RECENT_MONTHS = 3
_FAST_STABLE_WITH_DATA = {"downloaded_complete", "pending_partial", "pending_verification",
                          "pending_nonlosing_refresh", "pending_empty_refresh"}


def fast_recent_cutoff(end):
    """First day of the month FAST_RECENT_MONTHS before ``end``'s month."""
    index = end.year * 12 + end.month - 1 - FAST_RECENT_MONTHS
    return date(index // 12, index % 12 + 1, 1)


def fast_review_decision(folder, year, month, window_start, window_end, cutoff, *, temporary=False):
    """Authorized fast schedule only: whether a month with local files is requested again.

    Months ending on or after ``cutoff``, months with a leftover temporary name
    (``temporary``), months stored for another request window and every error,
    corrupt, unreadable or orphaned month are reviewed as before. Not requested
    again: a historical month whose manifest names an artifact present on disk, and
    a historical month whose last report had no rows and no error. Completeness is
    never inferred here; the final verification still rereads every manifest and
    artifact, with the inventory expectations stored at the month's last commit.
    """
    if window_end >= cutoff or temporary:
        return "review"
    try:
        with (folder / f"{year:04d}-{month:02d}.manifest.json").open("rb") as stream:
            raw = stream.read(MAX_RESPONSE + 1)
        manifest = json.loads(raw) if len(raw) <= MAX_RESPONSE else None
    except (OSError, ValueError, RecursionError):
        return "review"
    if not isinstance(manifest, dict):
        return "review"
    candidate = manifest.get("verification_candidate", manifest)
    if not isinstance(candidate, dict):
        return "review"
    if any(item.get("requested_start") != str(window_start) or item.get("requested_end") != str(window_end)
           for item in (manifest, candidate)):
        return "review"
    status, name = manifest.get("status"), candidate.get("artifact_name")
    if (status in _FAST_STABLE_WITH_DATA and isinstance(name, str) and name
            and Path(name).name == name and (folder / name).is_file()):
        return "stable_historical"
    if (status in {"pending_no_artifact", "pending_empty"} and not manifest.get("error")
            and manifest.get("row_count") == 0 and not name):
        return "empty_at_source"
    return "review"


def run_download(output_root, start, end, guard, limit_jobs=None, client=None, *, http_workers=1, client_factory=None,
                 fast_schedule=False, inventory_client_factory=None):
    run_state = {}
    try:
        return _run_download(output_root, start, end, guard, limit_jobs, client,
                             http_workers=http_workers, client_factory=client_factory,
                             fast_schedule=fast_schedule, inventory_client_factory=inventory_client_factory,
                             _run_state=run_state)
    except SourceError as exc:
        progress = Path(output_root).resolve() / "progreso.json"
        guard.check()
        if progress.is_file():
            summary = run_state.get("summary") or json.loads(progress.read_text())
            summary.update(status="blocked_source", error_type=type(exc).__name__, error=str(exc))
            guard.write_atomic_bytes(progress, json_bytes(summary))
        raise


def _run_download(output_root, start, end, guard, limit_jobs=None, client=None, *, http_workers=1, client_factory=None,
                  fast_schedule=False, inventory_client_factory=None, _run_state=None):
    """Run after guard.meteo_lock(); no disk paths are trusted without guard checks."""
    start = date.fromisoformat(start) if isinstance(start, str) else start
    end = date.fromisoformat(end) if isinstance(end, str) else end
    if start > end:
        raise ValueError("--start debe ser anterior o igual a --end.")
    if limit_jobs is not None and limit_jobs < 1:
        raise ValueError("--limit-jobs debe ser positivo.")
    if type(http_workers) is not int or http_workers not in (1, 2, 4):
        raise ValueError("Sólo se permiten uno, dos o cuatro trabajadores HTTP.")
    if type(fast_schedule) is not bool:
        raise ValueError("El calendario rápido debe ser verdadero o falso.")
    if http_workers == 4 and not fast_schedule:
        raise ValueError("Cuatro trabajadores HTTP sólo existen con el calendario rápido autorizado.")
    if http_workers > 1 and client is not None and client_factory is None:
        raise ValueError("Varios trabajadores requieren una fábrica de clientes aislados.")
    if hasattr(guard, "http_workers") and guard.http_workers != http_workers:
        raise ValueError("El guard debe reservar los mismos trabajadores que la descarga.")
    root = Path(output_root).resolve()
    _guard_boundary(guard)
    deferred = bool(getattr(guard, "defer_heavy_checks", False))
    if fast_schedule and not deferred:
        raise ValueError("El calendario rápido requiere la relectura final diferida.")
    if fast_schedule and getattr(guard, "frsize_allocation_grain", True) is not True:
        # With per-station full checks, a 1 MiB APFS grain would inflate the
        # light-check quota bound by ~2 MiB per write until the next station.
        raise ValueError("El calendario rápido requiere el grano de asignación f_frsize en el guard.")
    request_gate = None
    if http_workers > 1 or fast_schedule:
        # Fresh inventory sessions and every reader share one start-rate limit.
        from _meteo_http_parallel import RequestGate
        request_gate = RequestGate(interval=1.0)
    client_injected = client is not None
    client = client or PublicDMC(guard=guard, request_gate=request_gate)
    if fast_schedule and inventory_client_factory is None and not client_injected:
        inventory_client_factory = lambda: PublicDMC(guard=guard, request_gate=request_gate)
    previous_retry_codes = set()
    if fast_schedule:
        # Best-effort, read-only: stations whose inventory failed in the previous run,
        # or that an earlier fast run prioritised but never reached, go first.
        try:
            with os.fdopen(os.open(root / "progreso.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise OSError("progreso.json is not a regular file")
                raw = stream.read(MAX_RESPONSE + 1)
            prior = json.loads(raw) if len(raw) <= MAX_RESPONSE else {}
            if isinstance(prior, dict):
                carried = prior.get("fast_schedule", {})
                for codes in (prior.get("stations_inventory_retry_codes", []),
                              carried.get("priority_codes_not_yet_attempted", []) if isinstance(carried, dict) else []):
                    if isinstance(codes, list):
                        previous_retry_codes |= {code for code in codes
                                                 if isinstance(code, str) and re.fullmatch(r"\d{6}", code)}
        except Exception:
            previous_retry_codes = set()
    retrieved = datetime.now(timezone.utc).isoformat()
    script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    stations = client.catalog()
    catalog_payload = {"source": SOURCE, "url": CATALOG_URL, "retrieved_at_utc": retrieved,
                       "filters": {"conDatos": "0", "operativas": "2", "nombreEstacion": ""},
                       "scope": "All national-catalogue stations with archived data, including inactive stations; hourly availability varies",
                       "stations": stations, "station_count": len(stations)}
    guard.write_atomic_bytes(root / "catalogo_nacional.json.gz", compressed_json(catalog_payload))
    summary = {"source": SOURCE, "requested_start": str(start), "requested_end": str(end),
               "started_at_utc": retrieved, "station_count": len(stations), "jobs_requested": 0,
               "jobs_downloaded": 0, "jobs_existing_verified": 0, "jobs_pending": 0,
               "stations_without_target_inventory": 0, "stations_pending_inventory": 0,
               "stations_inventory_retry": 0, "stations_inventory_retry_codes": [],
               "rows_downloaded": 0,
               "jobs_existing_deferred": 0, "verification_deferred": deferred,
               "http_workers": http_workers, "publication_workers": 1,
               "global_request_interval_seconds": 1.0,
               "report_jobs_committed": 0, "report_jobs_awaiting_commit": 0,
               "jobs_requested_semantics": "Report jobs dispatched; may include up to two uncommitted or cancelled jobs, not HTTP attempts or new observations. Awaiting-commit counters do not prove current activity.",
               "schema_version": SCHEMA_VERSION, "script_sha256": script_sha,
               "timezone": TIMEZONE, "coverage_complete": False, "status": "running"}
    if _run_state is not None:
        _run_state["summary"] = summary
    guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
    consecutive_errors = 0
    inventory_unconfirmed_stations = set()
    deferred_review = []
    phase_counts = {key: 0 for key in ("jobs_processed", "jobs_requested", "jobs_downloaded", "jobs_existing_verified", "jobs_pending", "rows_downloaded")}
    summary.update(phase="acquisition", scheduling_policy="national_missing_months_then_review",
                   acquisition=dict(phase_counts, jobs_discovered=0, traversal_complete=False),
                   review=dict(phase_counts, jobs_scheduled=0, jobs_remaining=0, traversal_complete=False))
    recent_cutoff = fast_recent_cutoff(end) if fast_schedule else None
    retry_later = []
    retry_pass_streak = 0
    if fast_schedule:
        priority_codes = sorted(previous_retry_codes & {item["code"] for item in stations})
        summary["scheduling_policy"] = FAST_SCHEDULE_POLICY
        summary["jobs_requested_semantics"] = summary["jobs_requested_semantics"].replace(
            "up to two", f"up to {http_workers}")
        summary["fast_schedule"] = {
            "recent_review_cutoff": str(recent_cutoff),
            "priority_inventory_retry_stations": len(priority_codes),
            "priority_codes": priority_codes,
            "priority_codes_not_yet_attempted": list(priority_codes),
            "inventory_fresh_session": inventory_client_factory is not None,
            "inventory_retry_pass": True,
            "full_guard_check": "once per station boundary; light check (volume fingerprint, path, free-space "
                                "reserve, conservative retained quota) on every job, request and write",
            "not_requested_again": ["historical month with an artifact on disk",
                                    "historical month whose last report had no rows and no error"],
            "skipped_months_inventory_expectations": "kept from their last commit; the final verification "
                                                     "rereads them with those stored expectations"}
        summary["acquisition"].update(inventory_retry_pass_attempted=0, inventory_retry_pass_recovered=0,
                                      inventory_retry_pass_stopped=None)
        summary["review"].update(jobs_skipped_stable_historical=0, jobs_skipped_empty_at_source=0)
    guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))

    def priority_jobs():
        nonlocal consecutive_errors
        for station in stations:
            # Drain HTTP results before inventory/summary changes of a new station.
            yield "boundary", None
            _guard_boundary(guard)
            code = station["code"]
            metadata_path = root / "metadata" / f"{code}.json"
            inventory = None
            try:
                cached = json.loads(metadata_path.read_text(encoding="utf-8"))
                age = datetime.now(timezone.utc) - datetime.fromisoformat(cached["retrieved_at_utc"])
                # An empty inventory is always re-queried. This is the safety net for
                # outage pages that parse_inventory cannot tell apart: on 2026-10-12
                # (05:35-06:40 UTC) Quinta Normal, Pudahuel and ~900 other stations
                # were recorded without target variables.
                if (age < timedelta(days=7) and cached.get("schema_version") == SCHEMA_VERSION
                        and cached["inventory"]
                        and not any(item.get("inventory_status") == "pending_unavailable_range"
                                    for item in cached["inventory"])):
                    inventory = cached["inventory"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
            if inventory is None:
                try:
                    inventory = client.inventory(code)
                except AccessBlocked:
                    raise
                except (MissingSourceError, TransientSourceError) as exc:
                    inventory_unconfirmed_stations.add(code)
                    consecutive_errors = consecutive_errors + 1 if isinstance(exc, TransientSourceError) else 0
                    summary["jobs_pending"] += 1
                    summary["stations_inventory_retry"] += 1
                    summary["stations_inventory_retry_codes"].append(code)
                    summary["last_error"] = {"station": code, "phase": "inventory", "reason": str(exc)}
                    if consecutive_errors >= 3:
                        summary["status"] = "blocked_source"
                    guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
                    if consecutive_errors >= 3:
                        raise SourceError("Tres errores DMC consecutivos; descarga detenida y pendientes conservados.")
                    continue
                except SourceError as exc:
                    summary["last_error"] = {"station": code, "phase": "inventory", "reason": str(exc)}
                    guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
                    raise
                consecutive_errors = 0
                metadata = {"schema_version": SCHEMA_VERSION, "station": station,
                            "inventory": inventory, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                            "source_url": BASE + f"/application/informacion/fichaDeEstacion/{code}",
                            "caution": "Inventory years/counts do not prove complete hourly coverage."}
                response = getattr(client, "last_inventory_info", None)
                if response and response.get("source_url") == metadata["source_url"]:
                    metadata["source_response"] = {key: response[key] for key in
                                                   ("invalid_utf8_replacements", "response_sha256")}
                guard.write_atomic_bytes(metadata_path, json_bytes(metadata))
            if not inventory:
                inventory_unconfirmed_stations.add(code)
                summary["stations_without_target_inventory"] += 1
                continue
            pending_inventory = [item["element_id"] for item in inventory
                                 if item.get("inventory_status") == "pending_unavailable_range"]
            known_inventory = [item for item in inventory if item["element_id"] not in pending_inventory]
            if pending_inventory:
                inventory_unconfirmed_stations.add(code)
                summary["stations_pending_inventory"] += 1
                summary["jobs_pending"] += 1
                summary["last_inventory_pending"] = {"station": code, "element_ids": pending_inventory,
                                                     "status": "pending_unavailable_range", "retryable": True}
                guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
            guard.check()
            # File names schedule review; no artifact/manifest is trusted yet.
            local_months = _local_months(root / "estaciones" / code)
            for year, month, window_start, window_end in month_windows(start, end):
                if not any(item["first_year"] <= year <= item["last_year"] for item in known_inventory):
                    continue
                job = (station, inventory, known_inventory, pending_inventory, year, month, window_start, window_end)
                if (year, month) in local_months:
                    deferred_review.append(job)
                    summary["review"]["jobs_scheduled"] += 1
                    summary["review"]["jobs_remaining"] += 1
                    continue
                summary["acquisition"]["jobs_discovered"] += 1
                yield "acquisition", job
        yield "boundary", None
        summary["acquisition"]["traversal_complete"] = True
        summary["phase"] = "review"
        guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
        review_station = None
        for job in deferred_review:
            if job[0]["code"] != review_station:
                yield "boundary", None
                review_station = job[0]["code"]
            guard.check()
            yield "review", job
        yield "boundary", None
        summary["review"]["traversal_complete"] = True

    def fast_station_jobs(station, retry_pass=False):
        """One station of the authorized fast schedule; same rules as priority_jobs
        except a fresh public session per inventory and the review filter. Failures
        in the retry pass never touch the national three-error stop; three
        consecutive transient ones only end the retry pass (see fast_priority_jobs)."""
        nonlocal consecutive_errors, retry_pass_streak
        code = station["code"]
        metadata_path = root / "metadata" / f"{code}.json"
        inventory = None
        pending_priority = summary["fast_schedule"]["priority_codes_not_yet_attempted"]
        if code in pending_priority:
            pending_priority.remove(code)
        if not retry_pass:
            try:
                cached = json.loads(metadata_path.read_text(encoding="utf-8"))
                age = datetime.now(timezone.utc) - datetime.fromisoformat(cached["retrieved_at_utc"])
                if (age < timedelta(days=7) and cached.get("schema_version") == SCHEMA_VERSION
                        and cached["inventory"]
                        and not any(item.get("inventory_status") == "pending_unavailable_range"
                                    for item in cached["inventory"])):
                    inventory = cached["inventory"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if inventory is None:
            inventory_client = inventory_client_factory() if inventory_client_factory else client
            try:
                inventory = inventory_client.inventory(code)
            except AccessBlocked:
                raise
            except (MissingSourceError, TransientSourceError) as exc:
                summary["last_error"] = {"station": code, "phase": "inventory", "reason": str(exc)}
                if retry_pass:
                    retry_pass_streak = retry_pass_streak + 1 if isinstance(exc, TransientSourceError) else 0
                    guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
                    return
                consecutive_errors = consecutive_errors + 1 if isinstance(exc, TransientSourceError) else 0
                inventory_unconfirmed_stations.add(code)
                summary["jobs_pending"] += 1
                summary["stations_inventory_retry"] += 1
                summary["stations_inventory_retry_codes"].append(code)
                retry_later.append(station)
                if consecutive_errors >= 3:
                    summary["status"] = "blocked_source"
                guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
                if consecutive_errors >= 3:
                    raise SourceError("Tres errores DMC consecutivos; descarga detenida y pendientes conservados.")
                return
            except SourceError as exc:
                summary["last_error"] = {"station": code, "phase": "inventory", "reason": str(exc)}
                guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
                raise
            consecutive_errors = 0
            if retry_pass:
                # Undo only this station's first-pass retry accounting.
                retry_pass_streak = 0
                inventory_unconfirmed_stations.discard(code)
                summary["jobs_pending"] -= 1
                summary["stations_inventory_retry"] -= 1
                summary["stations_inventory_retry_codes"].remove(code)
                summary["acquisition"]["inventory_retry_pass_recovered"] += 1
            metadata = {"schema_version": SCHEMA_VERSION, "station": station,
                        "inventory": inventory, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "source_url": BASE + f"/application/informacion/fichaDeEstacion/{code}",
                        "caution": "Inventory years/counts do not prove complete hourly coverage."}
            response = getattr(inventory_client, "last_inventory_info", None)
            if response and response.get("source_url") == metadata["source_url"]:
                metadata["source_response"] = {key: response[key] for key in
                                               ("invalid_utf8_replacements", "response_sha256")}
            guard.write_atomic_bytes(metadata_path, json_bytes(metadata))
        if not inventory:
            inventory_unconfirmed_stations.add(code)
            summary["stations_without_target_inventory"] += 1
            return
        pending_inventory = [item["element_id"] for item in inventory
                             if item.get("inventory_status") == "pending_unavailable_range"]
        known_inventory = [item for item in inventory if item["element_id"] not in pending_inventory]
        if pending_inventory:
            inventory_unconfirmed_stations.add(code)
            summary["stations_pending_inventory"] += 1
            summary["jobs_pending"] += 1
            summary["last_inventory_pending"] = {"station": code, "element_ids": pending_inventory,
                                                 "status": "pending_unavailable_range", "retryable": True}
            guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
        guard.check()
        folder = root / "estaciones" / code
        local_months = _local_months(folder)
        try:
            # Leftover atomic temporary names (".YYYY-MM.*") keep their month in review.
            temporary_months = {(int(match[1]), int(match[2])) for path in folder.iterdir()
                                for match in [re.match(r"^\.(\d{4})-(\d{2})\.", path.name)] if match}
        except FileNotFoundError:
            temporary_months = set()
        for year, month, window_start, window_end in month_windows(start, end):
            if not any(item["first_year"] <= year <= item["last_year"] for item in known_inventory):
                continue
            job = (station, inventory, known_inventory, pending_inventory, year, month, window_start, window_end)
            if (year, month) in local_months:
                decision = fast_review_decision(folder, year, month, window_start, window_end, recent_cutoff,
                                                temporary=(year, month) in temporary_months)
                if decision == "review":
                    deferred_review.append(job)
                    summary["review"]["jobs_scheduled"] += 1
                    summary["review"]["jobs_remaining"] += 1
                else:
                    summary["review"]["jobs_skipped_" + decision] += 1
                continue
            summary["acquisition"]["jobs_discovered"] += 1
            yield "acquisition", job

    def fast_priority_jobs():
        """Authorized fast schedule. Stations whose inventory failed in the previous
        run go first (catalogue order otherwise kept), each inventory request uses a
        fresh public session, and an inventory that fails now gets exactly one more
        attempt after the national traversal. Review then skips what
        fast_review_decision leaves out. The full guard check runs at every station
        boundary of every phase; prepare_job uses the light check in between."""
        ordered = sorted(stations, key=lambda item: item["code"] not in previous_retry_codes)
        for station in ordered:
            # Drain HTTP results before inventory/summary changes of a new station.
            yield "boundary", None
            _guard_boundary(guard)
            yield from fast_station_jobs(station)
        for station in list(retry_later):
            if retry_pass_streak >= 3:
                summary["acquisition"]["inventory_retry_pass_stopped"] = "three_consecutive_transient_errors"
                break
            yield "boundary", None
            _guard_boundary(guard)
            summary["acquisition"]["inventory_retry_pass_attempted"] += 1
            yield from fast_station_jobs(station, retry_pass=True)
        yield "boundary", None
        summary["acquisition"]["traversal_complete"] = True
        summary["phase"] = "review"
        guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
        review_station = None
        for job in deferred_review:
            if job[0]["code"] != review_station:
                yield "boundary", None
                _guard_boundary(guard)
                review_station = job[0]["code"]
            guard.check()
            yield "review", job
        yield "boundary", None
        summary["review"]["traversal_complete"] = True

    def finish_job(phase, before):
        counts = summary[phase]
        counts["jobs_processed"] += 1
        for key in ("jobs_requested", "jobs_downloaded", "jobs_existing_verified", "jobs_pending", "rows_downloaded"):
            if http_workers > 1 and key == "jobs_requested":
                continue
            counts[key] += summary[key] - before[key]
        if phase == "review":
            counts["jobs_remaining"] -= 1

    def prepare_job(phase, job):
        # Read-only preparation; no summary, progress or manifest changes can
        # overtake an earlier HTTP result in the bounded wave.
        station, inventory, known_inventory, pending_inventory, year, month, window_start, window_end = job
        code = station["code"]
        folder = root / "estaciones" / code
        manifest_path = folder / f"{year:04d}-{month:02d}.manifest.json"
        if fast_schedule:
            # Authorized fast schedule: full check at station boundaries only.
            guard.check()
        else:
            _guard_boundary(guard)
        previous, previous_rows = None, []
        if deferred:
            try:
                with manifest_path.open("rb") as stream:
                    previous = json.loads(stream.read(MAX_RESPONSE + 1))
                if not isinstance(previous, dict):
                    previous = None
            except (OSError, ValueError):
                previous = None
            prior_status = previous.get("status") if previous else None
            prior_window = (previous.get("verification_candidate", previous)
                            if prior_status == "pending_verification" else previous)
            same_window = (isinstance(prior_window, dict)
                           and prior_window.get("requested_start") == str(window_start)
                           and prior_window.get("requested_end") == str(window_end))
            current_month = (window_end.year == date.today().year and window_end.month == date.today().month)
            current_required = [key for key in HOURLY_REQUIRED if FIELD_ELEMENT_IDS[key] in {
                item["element_id"] for item in known_inventory if item.get("source_count", 1) > 0}]
            expected_slots = ((window_end - window_start).days + 1) * 24
            verified_full_metadata = (prior_status == "pending_partial" and previous.get("verification_status") == "verified_operational"
                and not pending_inventory and bool(current_required) and previous.get("row_count") == expected_slots
                and isinstance(previous.get("valid_counts"), dict)
                and all(previous["valid_counts"].get(key) == expected_slots for key in current_required))
            if (previous and previous.get("artifact_name") and same_window
                    and (prior_status == "pending_verification"
                         or ((prior_status == "downloaded_complete" or verified_full_metadata) and not current_month))):
                # Metadata queues a final check, never establishes fresh reuse.
                prior = dict(previous, status="pending_verification", verification_status="pending",
                             coverage_complete=False, available_variable_coverage_complete=False, retryable=True,
                             inventory_pending_element_ids=pending_inventory,
                             hourly_fields_expected_from_inventory=[key for key in HOURLY_REQUIRED
                                 if FIELD_ELEMENT_IDS[key] in {item["element_id"] for item in known_inventory
                                                               if item.get("source_count", 1) > 0}])
                if isinstance(prior.get("verification_candidate"), dict):
                    prior["verification_candidate"] = dict(prior["verification_candidate"],
                        inventory_pending_element_ids=prior["inventory_pending_element_ids"],
                        hourly_fields_expected_from_inventory=prior["hourly_fields_expected_from_inventory"],
                        coverage_complete=False, available_variable_coverage_complete=False)
                return {"phase": phase, "job": job, "kind": "deferred",
                        "manifest": prior, "manifest_path": manifest_path}
        else:
            previous, previous_rows = existing_rows(root, manifest_path, window_start, window_end)
        if not deferred and not pending_inventory and _complete_validated_rows(previous, previous_rows, window_start, window_end):
            return {"phase": phase, "job": job, "kind": "verified",
                    "manifest_path": manifest_path}
        return {"phase": phase, "job": job, "kind": "report",
                "manifest_path": manifest_path, "previous": previous,
                "previous_rows": previous_rows}

    def commit_job(context, pool):
        nonlocal consecutive_errors
        if pool:
            pool.raise_if_failed()
        phase, job = context["phase"], context["job"]
        station, inventory, known_inventory, pending_inventory, year, month, window_start, window_end = job
        code = station["code"]
        folder = root / "estaciones" / code
        manifest_path = context["manifest_path"]
        summary["phase"] = phase
        before = {key: summary[key] for key in ("jobs_requested", "jobs_downloaded", "jobs_existing_verified", "jobs_pending", "rows_downloaded")}
        if context["kind"] != "report":
            if context["kind"] == "deferred":
                guard.write_atomic_bytes(manifest_path, json_bytes(context["manifest"]))
                summary["jobs_existing_deferred"] += 1
                summary["jobs_pending"] += 1
            else:
                summary["jobs_existing_verified"] += 1
            finish_job(phase, before)
            summary["last_station_month"] = f"{code}/{year:04d}-{month:02d}"
            guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
            return
        previous, previous_rows = context["previous"], context["previous_rows"]
        if not pool:
            summary["jobs_requested"] += 1
        summary["report_jobs_awaiting_commit"] = summary["jobs_requested"] - summary["report_jobs_committed"]
        manifest = {"schema_version": SCHEMA_VERSION, "source": SOURCE, "station_code": code,
                    "year": year, "month": month, "requested_start": str(window_start),
                    "requested_end": str(window_end), "script_sha256": script_sha,
                    "source_timezone": TIMEZONE, "documentation_url": DOC_URL,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            (rows, info), url = (pool.result(context["future"]) if pool else
                                 client.report(code, year, month, window_start, window_end))
            if pool:
                pool.raise_if_failed()
            expected = (window_end - window_start).days * 24 + 24
            counts = {key: sum(row["fields"][key]["value"] is not None for row in rows) for key in VARIABLES}
            inventory_ids = {item["element_id"] for item in known_inventory if item.get("source_count", 1) > 0}
            required = [key for key in HOURLY_REQUIRED if FIELD_ELEMENT_IDS[key] in inventory_ids]
            complete = not pending_inventory and len(rows) == expected and bool(required) and all(counts[key] == expected for key in required)
            manifest.update(info, source_url=url, row_count=len(rows), expected_hour_slots=expected,
                            observed_hour_slot_fraction=len(rows) / expected,
                            coverage_complete=not pending_inventory and len(rows) == expected and all(counts[key] == expected for key in HOURLY_REQUIRED),
                            inventory_pending_element_ids=pending_inventory,
                            available_variable_coverage_complete=complete,
                            hourly_fields_expected_from_inventory=required,
                            fields_not_declared_by_station_inventory=[key for key in HOURLY_REQUIRED if FIELD_ELEMENT_IDS[key] not in {item["element_id"] for item in inventory}],
                            hourly_fields_with_undetermined_inventory=[key for key in HOURLY_REQUIRED if FIELD_ELEMENT_IDS[key] in pending_inventory],
                            hourly_missing_counts={key: expected - counts[key] for key in required},
                            pressure_coverage_complete=all(counts[key] == expected for key in ("QFE", "QFF", "QNH")),
                            available_hours=[row["timestamp_source"] for row in rows],
                            valid_counts=counts,
                            status="downloaded_complete" if complete else "pending_partial" if rows else "pending_empty", retryable=not complete)
            if rows:
                body = compressed_json({"schema_version": SCHEMA_VERSION, "source": SOURCE,
                                        "station": station, "inventory": inventory, "variables": VARIABLES,
                                        "source_url": url,
                                        "source_timezone": TIMEZONE, "rows": rows})
                manifest["artifact_sha256"] = hashlib.sha256(body).hexdigest()
                manifest["artifact_bytes"] = len(body)
                path = folder / f"{year:04d}-{month:02d}.{manifest['artifact_sha256']}.json.gz"
                manifest["artifact_name"] = path.name
                if previous and not deferred and rows == previous_rows:
                    # Acquisition time/source HTML hashes live in the manifest,
                    # so identical observations never create duplicate versions.
                    manifest.update({key: previous[key] for key in ("artifact_name", "artifact_sha256", "artifact_bytes")})
                    path = folder / previous["artifact_name"]
                else:
                    guard.write_atomic_bytes(path, body)
                guard.check()
                if not deferred:
                    validate_artifact(path, manifest["artifact_sha256"], len(rows), window_start, window_end)
                guard.check()
                if deferred:
                    candidate = dict(manifest, status="pending_verification", verification_status="pending",
                                     coverage_complete=False, available_variable_coverage_complete=False, retryable=True)
                    if previous and previous.get("artifact_name"):
                        manifest = dict(previous, status="pending_verification", verification_status="pending",
                                        verification_candidate=candidate, retryable=True,
                                        coverage_complete=False, available_variable_coverage_complete=False)
                    else:
                        manifest = candidate
                    summary["jobs_pending"] += 1
                elif previous and not nonlosing(rows, previous_rows):
                    candidate = {key: manifest[key] for key in ("artifact_name", "artifact_sha256", "row_count", "valid_counts", "retrieved_at_utc")}
                    manifest = dict(previous, status="pending_nonlosing_refresh", retryable=True,
                                    rejected_lower_coverage_candidate=candidate,
                                    last_refresh_at_utc=datetime.now(timezone.utc).isoformat())
                    summary["jobs_pending"] += 1
                elif not complete:
                    summary["jobs_pending"] += 1
                summary["jobs_downloaded"] += 1
                summary["rows_downloaded"] += len(rows)
            else:
                if previous:
                    manifest = dict(previous, status="pending_empty_refresh", retryable=True,
                                    last_refresh_at_utc=datetime.now(timezone.utc).isoformat())
                summary["jobs_pending"] += 1
            consecutive_errors = 0
        except AccessBlocked:
            raise
        except (MissingSourceError, TransientSourceError) as exc:
            consecutive_errors = consecutive_errors + 1 if isinstance(exc, TransientSourceError) else 0
            manifest = dict(previous or manifest, status="pending_error", retryable=True, error=str(exc))
            if "artifact_name" not in manifest:
                manifest["row_count"] = 0
            summary["jobs_pending"] += 1
        if pending_inventory:
            # Preserving an older artifact must not restore its stale claim
            # of completeness after today's inventory became uncertain.
            manifest.update(coverage_complete=False, available_variable_coverage_complete=False,
                            retryable=True, inventory_pending_element_ids=pending_inventory,
                            hourly_fields_with_undetermined_inventory=[key for key in HOURLY_REQUIRED if FIELD_ELEMENT_IDS[key] in pending_inventory],
                            fields_not_declared_by_station_inventory=[key for key in HOURLY_REQUIRED if FIELD_ELEMENT_IDS[key] not in {item["element_id"] for item in inventory}])
        guard.write_atomic_bytes(manifest_path, json_bytes(manifest))
        summary["report_jobs_committed"] += 1
        summary["report_jobs_awaiting_commit"] = summary["jobs_requested"] - summary["report_jobs_committed"]
        finish_job(phase, before)
        summary["last_station_month"] = f"{code}/{year:04d}-{month:02d}"
        if consecutive_errors >= 3:
            summary["status"] = "blocked_source"
        guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
        if consecutive_errors >= 3:
            raise SourceError("Tres errores DMC consecutivos; descarga detenida y pendientes conservados.")

    # Only the coordinator advances inventories and writes. A wave contains at
    # most http_workers station-months of the same station and phase. Results are
    # consumed in planning order, not completion order; error streaks and deltas
    # stay deterministic. Reservations cover every response even while awaiting
    # commit. In the authorized fast schedule the wave is a sliding window: when
    # it is full only its oldest result is committed before the next dispatch.
    from contextlib import nullcontext
    pool_context = nullcontext(None)
    if http_workers > 1:
        from _meteo_http_parallel import ReportWorkers, RequestCancelled
        if client_factory is None:
            client_factory = lambda: PublicDMC(guard=guard, request_gate=request_gate)
        pool_context = ReportWorkers(http_workers, client_factory, request_gate,
            fatal_predicate=lambda exc: not isinstance(exc, (MissingSourceError, TransientSourceError, RequestCancelled)),
            fatal_record_lock=getattr(guard, "_state_lock", None))
    pool = None
    try:
        with pool_context as pool:
            if pool:
                guard.abort_check = pool.raise_if_failed
            wave = []
            def drain():
                try:
                    for context in wave:
                        commit_job(context, pool)
                finally:
                    wave.clear()
            def commit_oldest():
                try:
                    commit_job(wave.pop(0), pool)
                except BaseException:
                    wave.clear()
                    raise
            for phase, job in (fast_priority_jobs() if fast_schedule else priority_jobs()):
                if phase == "boundary":
                    drain()
                    continue
                if limit_jobs is not None and summary["jobs_requested"] >= limit_jobs:
                    drain()
                    summary["status"] = "limited"
                    guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
                    return summary
                context = prepare_job(phase, job)
                if context["kind"] == "report" and pool:
                    context["future"] = pool.submit(job)
                    summary["jobs_requested"] += 1
                    summary[phase]["jobs_requested"] += 1
                    summary["report_jobs_awaiting_commit"] = summary["jobs_requested"] - summary["report_jobs_committed"]
                wave.append(context)
                if context["kind"] != "report":
                    drain()
                elif len(wave) >= http_workers and fast_schedule:
                    commit_oldest()
                elif len(wave) >= http_workers:
                    drain()
            drain()
    finally:
        if pool:
            guard.abort_check = None
    if deferred:
        summary["phase"] = "final_verification"
        guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
        summary["final_verification"] = final_verify(root, guard,
            inventory_unconfirmed_stations=inventory_unconfirmed_stations)
        summary["jobs_pending_during_acquisition"] = summary["jobs_pending"]
        summary["jobs_pending"] = (summary["final_verification"]["months_pending"]
                                   + summary["stations_pending_inventory"]
                                   + summary["stations_inventory_retry"])
    summary["phase"] = "finished"
    summary.update(status="finished_with_pending" if summary["jobs_pending"] else "finished",
                   finished_at_utc=datetime.now(timezone.utc).isoformat())
    # Finished means catalogue traversal, never complete nationwide observations.
    guard.write_atomic_bytes(root / "progreso.json", json_bytes(summary))
    return summary


def check_api():
    today = datetime.now(timezone.utc).date()
    client = PublicDMC(timeout=20, retries=1)
    (rows, info), url = client.report("330020", today.year, today.month)
    pressure = [key for key in ("QFE", "QFF", "QNH") if any(row["fields"][key]["value"] is not None for row in rows)]
    ready = bool(rows and pressure)
    return {"ok": ready, "source_ready": ready, "requires_credentials": False,
            "source": SOURCE, "source_url": url, "documentation_url": DOC_URL,
            "hours_with_observations": len(rows), "pressure_fields": pressure,
            "source_timezone": info["timezone"], "persistent_writes": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check-api", "--probe", dest="check_api", action="store_true")
    action.add_argument("--download", action="store_true")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--start", default="2000-01-01")
    parser.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--limit-jobs", type=int)
    parser.add_argument("--http-workers", type=int, choices=(1, 2, 4), default=1,
                        help="Una, dos o cuatro consultas de informes (cuatro sólo con --fast-schedule); un solo coordinador y escritor")
    parser.add_argument("--concurrent-authorization-file", type=Path)
    parser.add_argument("--concurrent-authorization-sha256")
    parser.add_argument("--defer-heavy-checks", action="store_true",
                        help="Controles completos por frontera y relectura operacional local al final")
    parser.add_argument("--fast-schedule", action="store_true",
                        help="Calendario rápido autorizado: primero las estaciones con inventario fallido, sesión nueva "
                             "por inventario y sin volver a pedir meses históricos ya publicados; requiere --defer-heavy-checks")
    args = parser.parse_args(argv)
    if bool(args.concurrent_authorization_file) != bool(args.concurrent_authorization_sha256):
        parser.error("La concurrencia requiere archivo y SHA256 juntos.")
    if args.check_api and (args.concurrent_authorization_file or args.defer_heavy_checks or args.http_workers != 1
                           or args.fast_schedule):
        parser.error("La autorización concurrente y el aplazamiento sólo corresponden a --download.")
    if args.fast_schedule and not args.defer_heavy_checks:
        parser.error("El calendario rápido requiere --defer-heavy-checks.")
    if args.http_workers == 4 and not args.fast_schedule:
        parser.error("Cuatro consultas HTTP sólo existen con --fast-schedule.")
    try:
        if args.check_api:
            report = check_api()
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report["ok"] else 2
        if args.output_root is None:
            parser.error("--download requiere --output-root verificado en el disco externo.")
        start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
        if start > end or end > datetime.now(timezone.utc).date():
            raise ValueError("Rango inválido: --start <= --end y --end no puede ser futuro.")
        from _meteo_guard import DiskGuard, load_concurrent_authorization
        concurrent = (load_concurrent_authorization(args.concurrent_authorization_file,
                      args.concurrent_authorization_sha256, output_root=args.output_root)
                      if args.concurrent_authorization_file else None)
        guard = DiskGuard(args.output_root, concurrent_authorization=concurrent,
                          defer_heavy_checks=args.defer_heavy_checks, http_workers=args.http_workers,
                          frsize_allocation_grain=args.fast_schedule)
        with guard.meteo_lock():
            result = run_download(args.output_root, start, end, guard, args.limit_jobs,
                                  http_workers=args.http_workers, fast_schedule=args.fast_schedule)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "finished" else 2
    except Exception as exc:
        paused = type(exc).__name__ == "GuardBlocked"
        print(json.dumps({"ok": False, "source_ready": False, "requires_credentials": False,
                          "source": SOURCE, "status": "paused_guard" if paused else "blocked_source",
                          "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False))
        return 3 if paused else 2


if __name__ == "__main__":
    raise SystemExit(main())
