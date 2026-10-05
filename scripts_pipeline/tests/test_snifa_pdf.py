"""Extraction regressions using tiny actual PDFs; no network or large fixtures."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from _snifa_pdf import parse_pdf, parse_pdf_events

PDF_AVAILABLE = bool(importlib.util.find_spec("pypdf") and importlib.util.find_spec("pdfplumber"))
STATIONS = [
    {"id": "charrua", "aliases": ["Charrúa", "Charrua Sur"]},
    {"id": "progreso", "aliases": ["Progreso"]},
    {"id": "sapu", "aliases": ["SAPU"], "unit": "do-not-assume"},
    {"id": "quinel", "aliases": ["Quinel"]},
]


def _make_pdf(path: Path, specifications: list[dict]) -> None:
    """Emit small independent PDF tables with deliberately blank physical cells."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
    })
    font_ref = writer._add_object(font)
    for specification in specifications:
        page = writer.add_blank_page(width=900, height=600)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
        commands = []

        def write(text, x, y):
            escaped = str(text).encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            commands.append(b"BT /F1 8 Tf " + f"{x} {y} Td (".encode() + escaped + b") Tj ET")

        for number, line in enumerate(specification["heading"].splitlines()):
            write(line, 20, 570 - number * 13)
        if "columns" in specification:
            if specification.get("event_grid"):
                for column in range(len(specification["columns"]) + 1):
                    x = 110 + column * 85
                    commands.append(f"{x} 400 m {x} 520 l S".encode())
            for column, (label, unit, averaging) in enumerate(specification["columns"]):
                if specification.get("column_headers", True):
                    for dy, text in enumerate([averaging, label, unit]):
                        write(text, 130 + column * 85, 495 - dy * 13)
            for row_number, (stamp, values) in enumerate(specification["rows"]):
                write(stamp, 20, 450 - row_number * 15)
                for column, value in enumerate(values):
                    if value is not None:
                        write(value, 130 + column * 85, 450 - row_number * 15)
            stream = DecodedStreamObject()
            stream.set_data(b"\n".join(commands))
            page[NameObject("/Contents")] = writer._add_object(stream)
            continue
        labels = specification.get("hours", list(map(str, range(24))))
        if not specification.get("summary_only"):
            write("DIA", 20, 470)
            for column, label in enumerate(labels):
                write(label, 70 + column * 27, 470)
        for row_number, (day, values) in enumerate(specification.get("rows", [("1", ["1"] * 24)])):
            write(day, 20, 450 - row_number * 15)
            for column, value in enumerate(values):
                if value is not None:
                    write(value, 70 + column * 27, 450 - row_number * 15)
            # Summary columns are intentionally attractive but must never be
            # ingested, nor slide into the empty hourly cell.
            for column in range(3):
                write("9999", 730 + column * 40, 450 - row_number * 15)
        if specification.get("chart_axis"):
            for column, label in enumerate(labels):
                write(label, 70 + column * 27, 100)
        stream = DecodedStreamObject()
        stream.set_data(b"\n".join(commands))
        page[NameObject("/Contents")] = writer._add_object(stream)
        if specification.get("rotation"):
            page.rotate(specification["rotation"])
    with path.open("wb") as handle:
        writer.write(handle)


def _heading(station="CHARRUA", pollutant="DIOXIDO DE NITROGENO", unit="ppb", date_heading="ANO: 2025 MES: DICIEMBRE"):
    return f"{station} VARIABLE : {pollutant}\n{date_heading}\nUNIDAD : {unit}\nHORAS"


@unittest.skipUnless(PDF_AVAILABLE, "Requires the same pypdf/pdfplumber dependencies as the parser")
class TestSnifaPdf(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="snifa-pdf-test-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "measurements.pdf"

    def read(self, pages, **kwargs):
        _make_pdf(self.path, pages)
        return parse_pdf(self.path, STATIONS, **kwargs)

    def test_decimal_comma_invalid_codes_and_blank_do_not_shift_hours(self):
        values = ["1"] * 24
        values[:6] = ["5,8", "2.e", None, "-0,2", "<0,1", "4.2"]
        result = self.read([{"heading": _heading(), "rows": [("1", values)]}])
        rows = result["rows"]
        self.assertEqual(len(rows), 24)
        self.assertEqual([r["hour_label"] for r in rows], list(map(str, range(24))))
        self.assertEqual(rows[0]["value"], 5.8)
        self.assertEqual(rows[0]["raw_value"], "5,8")
        self.assertIsNone(rows[1]["value"])
        self.assertEqual(rows[1]["quality_code"], "2.e")
        self.assertIsNone(rows[2]["value"])
        self.assertEqual(rows[2]["raw_value"], "")
        self.assertEqual(rows[3]["value"], -0.2)
        self.assertIsNone(rows[4]["value"])
        self.assertEqual(rows[4]["quality_code"], "<0,1")
        self.assertNotIn(9999, [row["value"] for row in rows])
        self.assertEqual(rows[0]["source_locator"], "page:1;table:1;day:1")

    def test_station_and_pollutant_context_is_not_carried_between_tables(self):
        result = self.read([
            {"heading": _heading()},
            {"heading": _heading("PROGRESO", "MONOXIDO DE CARBONO", "ppm")},
            {"heading": _heading("OTHER STATION", "OZONO")},
            {"heading": _heading("QUINEL", "NOX")},
            {"heading": _heading("QUINEL", "NO")},
        ])
        self.assertEqual(Counter((row["station_id"], row["pollutant"]) for row in result["rows"]),
                         {("charrua", "no2"): 24, ("progreso", "co"): 24})
        self.assertTrue(any("station_id" in issue for issue in result["issues"]))

    def test_moving_eight_hour_and_summary_pages_are_excluded(self):
        result = self.read([
            {"heading": _heading("PROGRESO", "OZONO") + "\nPROMEDIO MOVIL 8 HORAS"},
            {"heading": _heading("PROGRESO", "CO") + "\nRESUMEN MENSUAL", "summary_only": True},
            {"heading": _heading("PROGRESO", "OZONO"), "chart_axis": True},
        ])
        self.assertEqual(len(result["rows"]), 24)
        self.assertEqual({r["source_locator"].split(";")[0] for r in result["rows"]}, {"page:3"})
        self.assertTrue(any("excluded_moving_average" in issue for issue in result["issues"]))

    def test_serpram_1_to_24_and_original_units(self):
        result = self.read([{
            "heading": "ESTACION : SAPU VARIABLE : Dioxido de Azufre (SO2)\nPERIODO : 01 al 31 de agosto del 2026\nUNIDAD : µg/m3N\nHora",
            "hours": list(map(str, range(1, 25))), "rows": [("01-ago", ["2,5"] * 24)],
        }])
        self.assertEqual(len(result["rows"]), 24)
        self.assertEqual(result["rows"][0]["date"], "2026-08-01")
        self.assertEqual(result["rows"][-1]["hour_label"], "24")
        self.assertEqual(result["rows"][0]["unit"], "µg/m3N")

    def test_no_unit_is_not_filled_from_station_config(self):
        result = self.read([{"heading": "SAPU VARIABLE : NO2\nANO: 2025 MES: DICIEMBRE\nHORAS"}])
        self.assertEqual(result["rows"], [])
        self.assertTrue(any("metadata:unit" in issue for issue in result["issues"]))

    def test_period_fallback_requires_one_unambiguous_month(self):
        pages = [{"heading": _heading(date_heading="") }]
        good = self.read(pages, period_start="2025-12-01", period_end="2025-12-31")
        bad = self.read(pages, period_start="2025-10-01", period_end="2025-12-31")
        self.assertEqual(len(good["rows"]), 24)
        self.assertEqual(bad["rows"], [])

    def test_invalid_dates_and_hhmm_labels_are_not_normalized(self):
        result = self.read([{
            "heading": _heading(date_heading="ANO: 2025 MES: FEBRERO"),
            "hours": [f"{hour:02d}00" for hour in range(24)],
            "rows": [("28", ["2"] * 24), ("29", ["3"] * 24)],
        }])
        self.assertEqual(len(result["rows"]), 24)
        self.assertEqual(result["rows"][0]["hour_label"], "0000")
        self.assertEqual(result["rows"][-1]["hour_label"], "2300")
        self.assertEqual({row["date"] for row in result["rows"]}, {"2025-02-28"})

    def test_explicit_continuation_can_inherit_metadata(self):
        result = self.read([
            {"heading": _heading()},
            {"heading": "CONTINUACION\nHORAS", "rows": [("2", ["4"] * 24)]},
            {"heading": "HORAS", "rows": [("3", ["5"] * 24)]},
        ])
        self.assertEqual(len(result["rows"]), 48)
        self.assertEqual({row["date"] for row in result["rows"]}, {"2025-12-01", "2025-12-02"})

    def test_rotated_matrix_recovers_original_hour_alignment(self):
        result = self.read([{
            "heading": _heading("QUINEL"), "rotation": 90,
            "rows": [("1", [str(hour + 0.5) for hour in range(24)])],
        }])
        self.assertEqual(len(result["rows"]), 24)
        self.assertEqual([row["value"] for row in result["rows"]], [hour + 0.5 for hour in range(24)])
        self.assertEqual({row["station_id"] for row in result["rows"]}, {"quinel"})

    def test_columnar_gases_units_quality_continuation_and_station_boundary(self):
        columns = [(gas, "ppm" if gas.startswith("CO") else "ppb", average) for gas, average in [
            ("SO2", "horarios"), ("O3", "horarios"), ("O3", "Móvil 8 horas"),
            ("CO", "horarios"), ("CO", "Móvil 8 horas"), ("NO", "horarios"),
            ("NO2", "horarios"), ("NOX", "horarios"),
        ]]
        values = ["1", "2", "999", "0,1", "888", "777", "5,8", "666"]
        second = ["3", "4", "999", None, "888", "777", "2.e", "666"]
        result = self.read([
            {"heading": "ESTACION CHARRUA", "columns": columns,
             "rows": [("201701010000", values), ("201701010100", second), ("201701010130", values)]},
            {"heading": "", "columns": columns, "column_headers": False,
             "rows": [("201701010200", values)]},
            {"heading": "ESTACION POLICLINICO", "columns": columns,
             "rows": [("201701010300", values)]},
            {"heading": "", "columns": columns, "column_headers": False,
             "rows": [("201701010400", values)]},
            {"heading": "ESTACION PROGRESO", "columns": columns,
             "rows": [("201701010500", values)]},
            {"heading": "", "columns": columns, "column_headers": False,
             "rows": [("201701010700", values)]},
        ])
        rows = result["rows"]
        self.assertEqual(Counter((r["station_id"], r["pollutant"]) for r in rows),
                         {(station, gas): count for station, count in [("charrua", 3), ("progreso", 1)]
                          for gas in ["so2", "o3", "co", "no2"]})
        self.assertEqual({r["date"] for r in rows}, {"2017-01-01"})
        self.assertEqual({r["hour_label"] for r in rows}, {"0000", "0100", "0200", "0500"})
        first = {r["pollutant"]: r for r in rows if r["hour_label"] == "0000"}
        self.assertEqual(first["no2"]["value"], 5.8)
        self.assertEqual((first["co"]["value"], first["co"]["unit"]), (0.1, "ppm"))
        self.assertEqual(first["no2"]["unit"], "ppb")
        self.assertEqual(first["no2"]["source_locator"], "page:1;column:7;timestamp:201701010000")
        second_rows = {r["pollutant"]: r for r in rows if r["hour_label"] == "0100"}
        self.assertEqual(second_rows["no2"]["quality_code"], "2.e")
        self.assertIsNone(second_rows["no2"]["value"])
        self.assertIsNone(second_rows["co"]["value"])
        self.assertEqual(second_rows["co"]["quality_code"], "blank")
        self.assertTrue(any("invalid_or_unordered_timestamp:201701010130" in s for s in result["issues"]))
        self.assertTrue(any("page:3: columnar_missing" in s for s in result["issues"]))

    def test_quality_events_keep_column_identity_after_blank_pages(self):
        columns = [(gas, "", average) for gas, average in [
            ("SO2", "horarios"), ("O3", "horarios"), ("O3", "Móvil 8 horas"),
            ("CO", "horarios"), ("CO", "Móvil 8 horas"), ("NO", "horarios"),
            ("NO2", "horarios"), ("NOX", "horarios"),
        ]]
        blank = [None] * len(columns)
        coded = ["2.h", "2.e", "2.h", "2.h", "2.h", "2.h", "2.h", "2.h"]
        no2_only = [None, None, None, None, None, None, "ND", None]
        numeric_not_event = [None, None, None, "9", None, None, "2.e", None]
        pages = [
            {"heading": "ESTACION CHARRUA", "rows": [("201701010000", blank), ("201701010100", blank)]},
            {"heading": "", "column_headers": False,
             "rows": [("201701010200", coded), ("201701010300", no2_only)]},
            {"heading": "ESTACION POLICLINICO", "rows": [("201701010400", coded)]},
            {"heading": "", "column_headers": False, "rows": [("201701010500", coded)]},
            {"heading": "ESTACION PROGRESO", "rows": [("201701010600", numeric_not_event)]},
        ]
        for page in pages:
            page.update(columns=columns, event_grid=True)
        _make_pdf(self.path, pages)
        result = parse_pdf_events(self.path, STATIONS)
        rows = result["rows"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(Counter((r["station_id"], r["pollutant"]) for r in rows),
                         {("charrua", "so2"): 1, ("charrua", "o3"): 1, ("charrua", "co"): 1,
                          ("charrua", "no2"): 2, ("progreso", "no2"): 1})
        self.assertEqual({r["hour_label"] for r in rows}, {"0200", "0300", "0600"})
        for row in rows:
            self.assertIsNone(row["value"])
            self.assertEqual(row["unit"], "unknown")
            self.assertEqual(row["quality_code"], row["raw_value"])
            self.assertEqual(row["resolution"], "quality_event")
        only = next(r for r in rows if r["hour_label"] == "0300")
        self.assertEqual((only["pollutant"], only["quality_code"]), ("no2", "ND"))
        self.assertEqual(only["source_locator"], "page:2;column:7;timestamp:201701010300")
        self.assertTrue(any("page:3: event_missing" in issue for issue in result["issues"]))
        self.assertTrue(any("event_unrecognized_code:201701010600:co" in issue for issue in result["issues"]))
        self.assertEqual(result["tables_recognized"], 2)
        self.assertEqual(result["stations_recognized"], ["charrua", "progreso"])

    def test_empty_quality_table_is_recognized_but_missing_grid_is_not(self):
        page = {"heading": "ESTACION CHARRUA", "event_grid": True,
                "columns": [("SO2", "", "horarios"), ("NO2", "", "horarios")],
                "rows": [("201701010000", [None, None]), ("201701010100", [None, None])]}
        _make_pdf(self.path, [page])
        result = parse_pdf_events(self.path, STATIONS)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["tables_recognized"], 1)
        self.assertEqual(result["stations_recognized"], ["charrua"])
        page["event_grid"] = False
        _make_pdf(self.path, [page])
        result = parse_pdf_events(self.path, STATIONS)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["tables_recognized"], 0)
        self.assertEqual(result["stations_recognized"], [])
        self.assertTrue(any("coverage_not_established" in issue for issue in result["issues"]))

    @unittest.skipUnless(os.environ.get("SNIFA_TEST_DOWNLOAD_ROOT"), "Optional external originals, never downloaded by tests")
    def test_original_charrua_events_identify_76_numeric_invalid_cells(self):
        root = Path(os.environ["SNIFA_TEST_DOWNLOAD_ROOT"])
        data_path = root / "raw/los_guindos/59516/141627_DATOS CHARRUA COLUMNA los guindos 01.17 im.pdf"
        events_path = root / "raw/los_guindos/59516/141628_DATOS EVENTOS CHARRUA COLUMNA los guindos 01.17 im.pdf"
        data = parse_pdf(data_path, STATIONS)
        events = parse_pdf_events(events_path, STATIONS)
        self.assertEqual(events["issues"], [])
        self.assertEqual(events["tables_recognized"], 1)
        self.assertEqual(events["stations_recognized"], ["charrua"])
        key = lambda r: tuple(r[field] for field in ("station_id", "pollutant", "date", "hour_label"))
        lookup = {key(r): r for r in data["rows"]}
        self.assertTrue(all(key(r) in lookup for r in events["rows"]))
        affected = [(lookup[key(event)], event) for event in events["rows"]
                    if lookup[key(event)]["value"] is not None]
        self.assertEqual(len(affected), 76)
        selected = {value["pollutant"]: (value, event) for value, event in affected
                    if value["date"] == "2017-01-27" and value["hour_label"] == "0000"}
        self.assertEqual({gas: value["value"] for gas, (value, _) in selected.items()},
                         {"so2": 13, "o3": 41, "co": 6.1, "no2": 123})
        self.assertEqual({event["quality_code"] for _, event in selected.values()}, {"2.h"})
        self.assertEqual({event["resolution"] for _, event in selected.values()}, {"quality_event"})

    @unittest.skipUnless(os.environ.get("SNIFA_TEST_FIXTURES_ROOT"), "Optional local originals, never downloaded by tests")
    def test_local_original_los_guindos_and_scanned_el_penon(self):
        root = Path(os.environ["SNIFA_TEST_FIXTURES_ROOT"])
        guindos = next(root.rglob("*Guindos*12.25.pdf"))
        result = parse_pdf(guindos, STATIONS)
        self.assertEqual(Counter((row["station_id"], row["pollutant"]) for row in result["rows"]),
                         {(station, gas): 744 for station in ["charrua", "progreso"] for gas in ["no2", "so2", "co", "o3"]})
        first = next(row for row in result["rows"] if row["station_id"] == "charrua" and row["pollutant"] == "co")
        self.assertEqual((first["date"], first["hour_label"], first["value"]), ("2025-12-01", "0", 0.1))
        scanned = root / "el_penon" / "informe_2012_12.pdf"
        result = parse_pdf(scanned, [{"id": "el_penon", "aliases": ["El Peñón"]}])
        self.assertEqual(result["rows"], [])
        self.assertIn("page:34: image_table_requires_ocr_review", result["issues"])


if __name__ == "__main__":
    unittest.main()
