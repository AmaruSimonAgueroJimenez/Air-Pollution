"""Read published hourly gas matrices without interpreting summaries as samples.

Supported: text PDFs with a day/date column followed by 24 explicitly labelled
hours (0--23, 1--24 or HHMM), including SERPRAM Los Guindos/SAPU/Quinel;
and Los Guindos columnar annexes with YYYYMMDDHHMM and explicitly labelled
hourly gas columns. Adjacent columnar pages must have consecutive timestamps.
Column coordinates, rather than token counts, preserve blank cells. Decimal
commas and original invalidation codes are retained. No unit conversion, time
zone assignment, interpolation, or default station/unit is applied.

Image-only tables (including the inspected El Peñón December 2012 annex),
other vertical long tables, split 12-hour panels and unknown layouts require separate
review and are reported in ``issues``. Summary-only reports may legitimately
produce no rows; that is never evidence of a complete historical series.
"""
from __future__ import annotations

import bisect
import io
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path


_MONTHS = {
    name: number for number, names in enumerate(
        ("ene enero", "feb febrero", "mar marzo", "abr abril", "may mayo",
         "jun junio", "jul julio", "ago agosto", "sep sept septiembre setiembre",
         "oct octubre", "nov noviembre", "dic diciembre"), 1)
    for name in names.split()
}
_GASES = {
    "no2": r"\bNO\s*2\b|\bDIOXIDO\s+DE\s+NITROGENO\b",
    "so2": r"\bSO\s*2\b|\bDIOXIDO\s+DE\s+AZUFRE\b|\bANHIDRIDO\s+SULFUROSO\b",
    "co": r"\bCO\b|\bMONOXIDO\s+DE\s+CARBONO\b",
    "o3": r"\bO\s*3\b|\bOZONO\b",
}
_NUMBER = re.compile(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[Ee][+-]?\d+)?\Z")
_CODE = re.compile(r"(?:\d+[.,][A-Za-z]+|[-–—]+|[A-Za-z]+(?:[./][A-Za-z]+)*|[<>≤≥].+|\*+)\Z")
_STAMP = re.compile(r"(?:19|20)\d{10}\Z")


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).upper()


def _moving(text: str) -> bool:
    return bool(re.search(r"MOVIL(?:ES)?\b|MOVING\s+AVERAGE", _normal(text)))


def _pollutant(text: str) -> str | None:
    norm = _normal(text)
    variable = re.search(r"VARIABLE\s*:\s*([^\n]+)", norm)
    if variable:
        norm = variable.group(1).split("UNIDAD")[0]
    found = [gas for gas, expression in _GASES.items() if re.search(expression, norm)]
    return found[0] if len(found) == 1 else None


def _station(text: str, stations: list[dict]) -> str | None:
    norm = _normal(text)
    explicit = re.search(r"ESTACION\s*[:\-]?\s*([^\n]+)", norm)
    if explicit:
        norm = explicit.group(1).split("VARIABLE")[0]
    found = []
    for station in stations:
        aliases = station.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        names = [station["id"], station.get("name", ""), *aliases]
        if any(name and re.search(r"(?<!\w)" + re.escape(_normal(name)) + r"(?!\w)", norm)
               for name in names):
            found.append(station["id"])
    return found[0] if len(found) == 1 else None


def _unit(text: str) -> str | None:
    # The source spelling is returned unchanged apart from repeated whitespace.
    match = re.search(r"UNIDAD(?:\s+DE\s+MEDIDA)?\s*:\s*([^\n]+)", text, re.I)
    if match:
        value = re.split(r"\s{2,}|\b(?:AÑO|MES|PER[IÍ]ODO|VARIABLE)\s*:", match.group(1))[0]
        value = re.sub(r"\s+", " ", value).strip()
        if value and len(value) < 35:
            return value
    # Older tables publish the unit in the concentration title, not a field.
    match = re.search(r"(?:\(|\bEN\s+)([µμu\uf06dgmk]+\s*/\s*m(?:3|³)\s*N?|pp[mb]v?)\)?", text, re.I)
    return match.group(1).strip() if match else None


def _year_month(text: str, period_start: str, period_end: str) -> tuple[int, int] | None:
    norm = _normal(text)
    year = re.search(r"ANO\s*:\s*(20\d{2}|19\d{2})\b", norm)
    month = re.search(r"MES\s*:\s*([A-Z]+|\d{1,2})\b", norm)
    if year and month:
        value = month.group(1).lower()
        number = int(value) if value.isdigit() else _MONTHS.get(value)
        if number and 1 <= number <= 12:
            return int(year.group(1)), number
    pairs = set()
    for match in re.finditer(r"\b([A-Z]+)\s*(?:,\s*|\s+DE(?:L)?\s+|\s+)(20\d{2}|19\d{2})\b", norm):
        if match.group(1).lower() in _MONTHS:
            pairs.add((int(match.group(2)), _MONTHS[match.group(1).lower()]))
    if len(pairs) == 1:
        return pairs.pop()
    if pairs:
        return None
    try:
        start, end = date.fromisoformat(period_start), date.fromisoformat(period_end)
    except (TypeError, ValueError):
        return None
    return (start.year, start.month) if (start.year, start.month) == (end.year, end.month) else None


def _row_date(raw: str, year_month: tuple[int, int]) -> str | None:
    raw = _normal(raw).lower().strip()
    year, month = year_month
    match = re.fullmatch(r"(\d{1,2})(?:[-/]([a-z]+|\d{1,2})(?:[-/](\d{4}))?)?", raw)
    if not match:
        return None
    if match.group(2):
        m = match.group(2)
        supplied_month = int(m) if m.isdigit() else _MONTHS.get(m)
        if supplied_month != month:
            return None
    if match.group(3) and int(match.group(3)) != year:
        return None
    try:
        return date(year, month, int(match.group(1))).isoformat()
    except ValueError:
        return None


def _hour_sequence(tokens: list[str]) -> tuple[int, list[str]] | None:
    for start in range(max(0, len(tokens) - 23)):
        raw = tokens[start:start + 24]
        if len(raw) != 24:
            continue
        numbers = []
        for token in raw:
            if re.fullmatch(r"\d{1,2}", token):
                numbers.append(int(token))
            elif re.fullmatch(r"\d{2}:?00", token):
                numbers.append(int(token[:2]))
            else:
                break
        if numbers in [list(range(24)), list(range(1, 25))]:
            return start, raw
    return None


def _lines(words: list[dict]) -> list[list[dict]]:
    # SERPRAM Excel exports can have <3 pt between rows; the default 3 pt
    # pdfplumber tolerance joins adjacent dates and silently corrupts readings.
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 0.6:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _value(raw: str) -> tuple[float | None, str]:
    if not raw:
        return None, "blank"
    if _NUMBER.fullmatch(raw):
        value = float(raw.replace(",", "."))
        if math.isfinite(value):
            return value, ""
    return None, raw


def _matrix_lines(geometry, source_page) -> list[list[dict]]:
    """Read upright or 90-degree historical tables, leaving the source intact."""
    import pdfplumber
    from pypdf import PdfWriter

    def extract(page):
        return _lines(page.extract_words(x_tolerance=0.5, y_tolerance=0.3))

    def has_header(lines):
        return any(_hour_sequence([word["text"] for word in line]) for line in lines)

    lines = extract(geometry)
    if has_header(lines):
        return lines
    for angle in (90, 270, 180):
        writer = PdfWriter()
        writer.add_page(source_page).rotate(angle)
        content = io.BytesIO()
        writer.write(content)
        content.seek(0)
        with pdfplumber.open(content) as rotated:
            candidate = extract(rotated.pages[0])
            if has_header(candidate):
                return candidate
    return lines


def _parse_matrix(lines: list[list[dict]], header_index: int, offset: int,
                  context: dict, page_no: int, table_no: int) -> tuple[list[dict], list[str]]:
    header = lines[header_index][offset:offset + 24]
    centers = [(word["x0"] + word["x1"]) / 2 for word in header]
    if any(b <= a for a, b in zip(centers, centers[1:])):
        return [], [f"page:{page_no}: ambiguous_hour_columns"]
    bounds = [centers[0] - (centers[1] - centers[0]) / 2]
    bounds += [(a + b) / 2 for a, b in zip(centers, centers[1:])]
    bounds += [centers[-1] + (centers[-1] - centers[-2]) / 2]
    rows, issues = [], []
    seen_days = set()
    for line in lines[header_index + 1:]:
        if _hour_sequence([word["text"] for word in line]):
            break
        day_words = [word for word in line if (word["x0"] + word["x1"]) / 2 < bounds[0]]
        raw_day = "".join(word["text"] for word in day_words).strip()
        observed_date = _row_date(raw_day, context["year_month"])
        if not observed_date:
            if seen_days and _normal(raw_day).startswith(("MED", "MAX", "MIN", "PROM", "TOTAL")):
                break
            continue
        if observed_date in seen_days:
            issues.append(f"page:{page_no}: duplicate_day:{observed_date}")
            continue
        cells: list[list[str]] = [[] for _ in range(24)]
        for word in line:
            center = (word["x0"] + word["x1"]) / 2
            column = bisect.bisect_right(bounds, center) - 1
            if 0 <= column < 24:
                cells[column].append(word["text"])
        if sum(bool(cell) for cell in cells) < 12:
            issues.append(f"page:{page_no}: incomplete_or_unsupported_row:{raw_day}")
            continue
        # Combining distinct tokens could hide a shifted cell or a footnote.
        if any(len(cell) > 1 for cell in cells):
            issues.append(f"page:{page_no}: ambiguous_cells:{raw_day}")
            continue
        raw_values = [cell[0] if cell else "" for cell in cells]
        if any(raw and not (_NUMBER.fullmatch(raw) or _CODE.fullmatch(raw)) for raw in raw_values):
            issues.append(f"page:{page_no}: unrecognized_cell:{raw_day}")
            continue
        seen_days.add(observed_date)
        if "" in raw_values:
            issues.append(f"page:{page_no}: blank_cells_preserved:{observed_date}")
        for hour, raw in zip(header, raw_values):
            value, quality = _value(raw)
            rows.append({
                "station_id": context["station_id"], "pollutant": context["pollutant"],
                "date": observed_date, "hour_label": hour["text"],
                "value": value, "raw_value": raw, "unit": context["unit"],
                "quality_code": quality,
                "source_locator": f"page:{page_no};table:{table_no};day:{raw_day}",
                "resolution": "hourly",
            })
    return rows, issues


def _timestamp(raw: str) -> datetime | None:
    # This layout uses start-of-hour timestamps, not the matrix's 1--24 labels.
    if not _STAMP.fullmatch(raw) or raw[-2:] != "00":
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M")
    except ValueError:
        return None


def _column_context(lines: list[list[dict]], text: str, stations: list[dict],
                    width: float) -> dict | None:
    """Read each gas and unit from its own physical header, never by index."""
    station_id = _station(text, stations)
    if not station_id:
        return None
    stamp_lines = [line for line in lines if line and _STAMP.fullmatch(line[0]["text"])]
    if not stamp_lines:
        return None
    # Pick a populated row so a blank first row cannot merge two header columns.
    reference = max(stamp_lines[:8], key=len)
    cells = reference[1:]
    if len(cells) < 2 or any(not (_NUMBER.fullmatch(word["text"]) or _CODE.fullmatch(word["text"]))
                             for word in cells):
        return None
    centers = [(word["x0"] + word["x1"]) / 2 for word in cells]
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    median_gap = sorted(gaps)[len(gaps) // 2]
    if median_gap <= 0 or max(gaps) > 1.6 * median_gap or min(gaps) < 0.5 * median_gap:
        return None
    bounds = [centers[0] - gaps[0] / 2]
    bounds += [(a + b) / 2 for a, b in zip(centers, centers[1:])]
    bounds += [centers[-1] + gaps[-1] / 2]
    first_top = min(word["top"] for word in stamp_lines[0])
    headers: list[list[str]] = [[] for _ in centers]
    for line in lines:
        for word in line:
            # Labels, units and averaging period are immediately above data.
            if not first_top - 50 <= word["top"] < first_top - 0.6:
                continue
            column = bisect.bisect_right(bounds, (word["x0"] + word["x1"]) / 2) - 1
            if 0 <= column < len(headers):
                headers[column].append(word["text"])
    gases = []
    for index, words in enumerate(headers):
        header = " ".join(words)
        pollutant = _pollutant(header)
        if not pollutant or _moving(header) or not re.search(r"\bHORARIOS?\b", _normal(header)):
            continue
        unit = re.search(r"(?:[µμu\uf06d]g|mg|g)\s*/\s*m(?:3|³)\s*N?|\bpp[mb]v?\b", header, re.I)
        if unit:
            gases.append({"index": index, "pollutant": pollutant, "unit": unit.group().strip()})
    if not gases or len({gas["pollutant"] for gas in gases}) != len(gases):
        return None
    return {"station_id": station_id, "bounds": bounds, "gases": gases, "width": width}


def _parse_columns(geometry, text: str, stations: list[dict], previous: dict | None,
                   page_no: int) -> tuple[list[dict], list[str], dict | None]:
    lines = _lines(geometry.extract_words(x_tolerance=0.5, y_tolerance=0.3))
    stamp_lines = [line for line in lines if line and _STAMP.fullmatch(line[0]["text"])]
    if not stamp_lines:
        return [], [f"page:{page_no}: columnar_layout_requires_review"], None
    context = _column_context(lines, text, stations, geometry.width)
    if context is None and previous and not re.search(r"\bESTACION\b", _normal(text)):
        first_stamp = _timestamp(stamp_lines[0][0]["text"])
        if (abs(geometry.width - previous["width"]) < 0.5 and first_stamp
                and first_stamp == previous["last_stamp"] + timedelta(hours=1)):
            context = dict(previous)
    if context is None:
        return [], [f"page:{page_no}: columnar_missing_or_ambiguous_metadata"], None
    rows, issues = [], []
    last_stamp = context.get("last_stamp")
    for line in stamp_lines:
        raw_stamp = line[0]["text"]
        stamp = _timestamp(raw_stamp)
        if not stamp or (last_stamp and stamp <= last_stamp):
            issues.append(f"page:{page_no}: columnar_invalid_or_unordered_timestamp:{raw_stamp}")
            continue
        cells: list[list[str]] = [[] for _ in range(len(context["bounds"]) - 1)]
        for word in line[1:]:
            index = bisect.bisect_right(context["bounds"], (word["x0"] + word["x1"]) / 2) - 1
            if 0 <= index < len(cells):
                cells[index].append(word["text"])
        for gas in context["gases"]:
            cell = cells[gas["index"]]
            if len(cell) > 1:
                issues.append(f"page:{page_no}: columnar_ambiguous_cell:{raw_stamp}:{gas['pollutant']}")
                continue
            raw = cell[0] if cell else ""
            if raw and not (_NUMBER.fullmatch(raw) or _CODE.fullmatch(raw)):
                issues.append(f"page:{page_no}: columnar_unrecognized_cell:{raw_stamp}:{gas['pollutant']}")
                continue
            value, quality = _value(raw)
            rows.append({
                "station_id": context["station_id"], "pollutant": gas["pollutant"],
                "date": stamp.date().isoformat(), "hour_label": raw_stamp[-4:],
                "value": value, "raw_value": raw, "unit": gas["unit"],
                "quality_code": quality,
                "source_locator": f"page:{page_no};column:{gas['index'] + 1};timestamp:{raw_stamp}",
                "resolution": "hourly",
            })
        last_stamp = stamp
    context["last_stamp"] = last_stamp
    return rows, issues, context if rows else None


def parse_pdf(path: Path, stations: list[dict], period_start: str = "",
              period_end: str = "") -> dict:
    """Return extracted original hourly samples and explicit coverage issues.

    ``stations`` supplies ``id`` and ``aliases``. Default units in station
    configuration deliberately cannot substitute for a published PDF unit.
    Matrix continuation pages need an explicit continuation marker. Columnar
    continuation pages need identical width and consecutive hourly timestamps;
    an explicit unconfigured station always resets that context.
    """
    try:
        from pypdf import PdfReader
        import pdfplumber
    except ImportError as exc:
        return {"rows": [], "issues": [f"dependency_missing:{exc.name}: requires pypdf and pdfplumber"]}
    rows: list[dict] = []
    issues: list[str] = []
    previous = None
    previous_columns = None
    try:
        reader = PdfReader(str(path))
        with pdfplumber.open(str(path)) as document:
            for page_index, page in enumerate(reader.pages):
                page_no = page_index + 1
                try:
                    text = page.extract_text() or ""
                    text_lines = text.splitlines()
                    if re.search(r"(?<!\d)(?:19|20)\d{10}(?!\d)", text):
                        extracted, problems, previous_columns = _parse_columns(
                            document.pages[page_index], text, stations, previous_columns, page_no)
                        rows.extend(extracted)
                        issues.extend(problems)
                        previous = None
                        continue
                    previous_columns = None
                    candidates = [i for i, line in enumerate(text_lines) if _hour_sequence(line.split())]
                    if not candidates:
                        if not text.strip() and len(page.images):
                            issues.append(f"page:{page_no}: image_only_requires_ocr_review")
                        # Image-backed titled concentration tables are review
                        # items even when the surrounding report is searchable.
                        if (_pollutant(text) and _unit(text) and len(text.split()) < 90
                                and not _moving(text) and _station(text, stations)):
                            geometry = document.pages[page_index]
                            large_image = any(
                                (image["x1"] - image["x0"]) * (image["bottom"] - image["top"])
                                > geometry.width * geometry.height * 0.15
                                for image in geometry.images)
                            if large_image:
                                issues.append(f"page:{page_no}: image_table_requires_ocr_review")
                        previous = None
                        continue
                    preamble = "\n".join(text_lines[:candidates[0]])
                    if _moving(preamble):
                        issues.append(f"page:{page_no}: excluded_moving_average")
                        previous = None
                        continue
                    context = {
                        "station_id": _station(preamble, stations),
                        "pollutant": _pollutant(preamble),
                        "unit": _unit(preamble),
                        "year_month": _year_month(preamble, period_start, period_end),
                    }
                    if previous and re.search(r"\bCONTINUACION\b|\bCONTINUED\b", _normal(preamble)):
                        # Explicit non-target variables must not inherit a gas.
                        if "VARIABLE" not in _normal(preamble) or context["pollutant"]:
                            context = {key: value or previous[key] for key, value in context.items()}
                    if not context["pollutant"]:
                        previous = None
                        continue  # PM, NO, NOx and meteorology are outside scope.
                    missing = [key for key, value in context.items() if not value]
                    if missing:
                        issues.append(f"page:{page_no}: missing_or_ambiguous_metadata:{','.join(missing)}")
                        previous = None
                        continue
                    lines = _matrix_lines(document.pages[page_index], page)
                    matrix_count = 0
                    page_rows = []
                    for line_index, line in enumerate(lines):
                        sequence = _hour_sequence([word["text"] for word in line])
                        if not sequence:
                            continue
                        matrix_count += 1
                        extracted, problems = _parse_matrix(lines, line_index, sequence[0], context, page_no, matrix_count)
                        # Multiple variables/tables on one page need individual
                        # metadata segmentation; do not reuse a single context.
                        # A second 0--23 sequence can instead be a chart axis.
                        if extracted and page_rows:
                            issues.append(f"page:{page_no}: multiple_matrices_require_review")
                            page_rows = []
                            break
                        page_rows.extend(extracted)
                        issues.extend(problems)
                    if not page_rows:
                        issues.append(f"page:{page_no}: no_supported_hourly_rows")
                    else:
                        rows.extend(page_rows)
                    previous = context if page_rows else None
                except Exception as exc:
                    issues.append(f"page:{page_no}: extraction_error:{type(exc).__name__}:{exc}")
                    previous = None
                    previous_columns = None
    except Exception as exc:
        issues.append(f"pdf_error:{type(exc).__name__}:{exc}")
    if not rows:
        issues.append("no_hourly_rows_extracted: coverage_not_established")
    return {"rows": rows, "issues": list(dict.fromkeys(issues))}


def _event_column_context(geometry, lines: list[list[dict]], text: str,
                          stations: list[dict]) -> dict | None:
    """Use the published vertical grid: event columns can be entirely blank."""
    station_id = _station(text, stations)
    stamp_lines = [line for line in lines if line and _STAMP.fullmatch(line[0]["text"])]
    if not station_id or not stamp_lines:
        return None
    stamp_word = stamp_lines[0][0]
    stamp_center = (stamp_word["x0"] + stamp_word["x1"]) / 2
    first_top = min(word["top"] for word in stamp_lines[0])
    candidates = []
    for edge in [*geometry.rects, *geometry.lines]:
        if (abs(edge["x1"] - edge["x0"]) <= 1.5 and edge["top"] <= first_top
                and edge["bottom"] >= first_top + 10):
            center = (edge["x0"] + edge["x1"]) / 2
            if center > stamp_center:
                candidates.append(center)
    bounds = []
    for center in sorted(candidates):
        if not bounds or center - bounds[-1] > 1.5:
            bounds.append(center)
    if len(bounds) < 3:
        return None
    headers: list[list[str]] = [[] for _ in range(len(bounds) - 1)]
    for line in lines:
        for word in line:
            if not first_top - 50 <= word["top"] < first_top - 0.6:
                continue
            index = bisect.bisect_right(bounds, (word["x0"] + word["x1"]) / 2) - 1
            if 0 <= index < len(headers):
                headers[index].append(word["text"])
    gases = []
    for index, words in enumerate(headers):
        header = " ".join(words)
        gas = _pollutant(header)
        if gas and not _moving(header) and re.search(r"\bHORARIOS?\b", _normal(header)):
            gases.append({"index": index, "pollutant": gas})
    if not gases or len({gas["pollutant"] for gas in gases}) != len(gases):
        return None
    return {"station_id": station_id, "bounds": bounds, "gases": gases, "width": geometry.width}


def parse_pdf_events(path: Path, stations: list[dict], period_start: str = "",
                     period_end: str = "") -> dict:
    """Read separate columnar quality-event annexes, never concentrations.

    Only nonempty nonnumeric codes in explicitly hourly gas columns are emitted.
    The table's grid supplies column identity even when all cells on a page are
    blank. Adjacent pages retain context only across consecutive timestamps;
    blank pages of events therefore retain context but emit no observations.
    Units are deliberately ``unknown``: event codes are not concentrations.
    Published dates are preserved, including when report-level period metadata
    differ. The caller must match station, gas, date and original hour to data,
    retain both source locators and decide its report-scope conflict policy.
    ``tables_recognized`` counts explicit compatible headers, including tables
    without events. Extraction issues still require review of partial coverage.
    """
    try:
        from pypdf import PdfReader
        import pdfplumber
    except ImportError as exc:
        return {"rows": [], "issues": [f"dependency_missing:{exc.name}: requires pypdf and pdfplumber"],
                "tables_recognized": 0, "stations_recognized": []}
    rows, issues = [], []
    previous = None
    tables_recognized = 0
    stations_recognized = set()
    try:
        reader = PdfReader(str(path))
        with pdfplumber.open(str(path)) as document:
            for page_index, page in enumerate(reader.pages):
                page_no = page_index + 1
                try:
                    text = page.extract_text() or ""
                    if not re.search(r"(?<!\d)(?:19|20)\d{10}(?!\d)", text):
                        if not text.strip() and len(page.images):
                            issues.append(f"page:{page_no}: event_image_only_requires_review")
                        previous = None
                        continue
                    geometry = document.pages[page_index]
                    lines = _lines(geometry.extract_words(x_tolerance=0.5, y_tolerance=0.3))
                    stamp_lines = [line for line in lines if line and _STAMP.fullmatch(line[0]["text"])]
                    if not stamp_lines:
                        issues.append(f"page:{page_no}: event_columnar_layout_requires_review")
                        previous = None
                        continue
                    context = _event_column_context(geometry, lines, text, stations)
                    if context:
                        tables_recognized += 1
                        stations_recognized.add(context["station_id"])
                    if context is None and previous and not re.search(r"\bESTACION\b", _normal(text)):
                        first_stamp = _timestamp(stamp_lines[0][0]["text"])
                        if (abs(geometry.width - previous["width"]) < 0.5 and first_stamp
                                and first_stamp == previous["last_stamp"] + timedelta(hours=1)):
                            context = dict(previous)
                    if context is None:
                        issues.append(f"page:{page_no}: event_missing_or_ambiguous_metadata")
                        previous = None
                        continue
                    last_stamp = context.get("last_stamp")
                    for line in stamp_lines:
                        raw_stamp = line[0]["text"]
                        stamp = _timestamp(raw_stamp)
                        if not stamp or (last_stamp and stamp <= last_stamp):
                            issues.append(f"page:{page_no}: event_invalid_or_unordered_timestamp:{raw_stamp}")
                            continue
                        cells: list[list[str]] = [[] for _ in range(len(context["bounds"]) - 1)]
                        for word in line[1:]:
                            column = bisect.bisect_right(context["bounds"], (word["x0"] + word["x1"]) / 2) - 1
                            if 0 <= column < len(cells):
                                cells[column].append(word["text"])
                        for gas in context["gases"]:
                            cell = cells[gas["index"]]
                            if not cell:
                                continue
                            if len(cell) != 1 or not _CODE.fullmatch(cell[0]):
                                issues.append(f"page:{page_no}: event_unrecognized_code:{raw_stamp}:{gas['pollutant']}")
                                continue
                            code = cell[0]
                            rows.append({
                                "station_id": context["station_id"], "pollutant": gas["pollutant"],
                                "date": stamp.date().isoformat(), "hour_label": raw_stamp[-4:],
                                "value": None, "raw_value": code, "unit": "unknown",
                                "quality_code": code,
                                "source_locator": f"page:{page_no};column:{gas['index'] + 1};timestamp:{raw_stamp}",
                                "resolution": "quality_event",
                            })
                        last_stamp = stamp
                    context["last_stamp"] = last_stamp
                    previous = context if last_stamp else None
                except Exception as exc:
                    issues.append(f"page:{page_no}: event_extraction_error:{type(exc).__name__}:{exc}")
                    previous = None
    except Exception as exc:
        issues.append(f"pdf_error:{type(exc).__name__}:{exc}")
    if not tables_recognized:
        issues.append("no_quality_events_extracted: coverage_not_established")
    return {"rows": rows, "issues": list(dict.fromkeys(issues)),
            "tables_recognized": tables_recognized,
            "stations_recognized": sorted(stations_recognized)}
