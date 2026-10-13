"""Hand-written physical source fixtures; no ORM, provider or invented facts."""

from dataclasses import FrozenInstanceError
import io
import zipfile

import pytest

from app.application.contracts.import_source import SourceParseError
from app.infrastructure import import_parser as parser


def workbook(cells, *, extra=None, encoding="utf-8"):
    out = io.BytesIO()
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    parts = {
        "xl/workbook.xml": f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="r1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{ns}"><sheetData>{cells}</sheetData></worksheet>',
    }
    parts.update(extra or {})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(
                name, value.encode(encoding) if isinstance(value, str) else value
            )
    return out.getvalue()


def test_csv_bom_multiline_locations_missing_different_zero():
    source = parser.parse_source(
        b'\xef\xbb\xbfkey,quantity,note\r\nA,0,"line1\r\nline2"\r\nB,,end\r\n', "csv"
    )
    rows = source.sheets[0].rows
    assert rows[1].cells[1].raw == "0" and rows[1].cells[1].kind == "text"
    assert rows[2].cells[1].raw == "" and rows[2].cells[1].kind == "empty"
    assert (rows[1].record_number, rows[1].line_start, rows[1].line_end) == (2, 2, 3)
    assert (rows[2].record_number, rows[2].line_start, rows[2].line_end) == (3, 4, 4)
    with pytest.raises(FrozenInstanceError):
        rows[1].cells[1].raw = "99"


def test_xlsx_exact_lexical_numeric_and_cached_formula_never_evaluate():
    data = workbook(
        '<row r="1"><c r="A1" t="inlineStr"><is><t>quantity</t></is></c></row>'
        '<row r="2"><c r="A2"><v>1000.123456789012345678901</v></c><c r="C2"><f>1+1</f><v>9</v></c></row>'
    )
    row = parser.parse_source(data, "xlsx").sheets[0].rows[1]
    assert [(c.column_index, c.raw) for c in row.cells] == [
        (0, "1000.123456789012345678901"),
        (2, "9"),
    ]
    assert row.cells[1].formula is True and row.cells[1].raw != "2"


def test_formula_without_cache_blocks_with_physical_location():
    data = workbook(
        '<row r="7"><c r="B7"><f>WEBSERVICE("https://example.test")</f></c></row>'
    )
    with pytest.raises(SourceParseError) as caught:
        parser.parse_source(data, "xlsx")
    assert (
        caught.value.code,
        caught.value.sheet,
        caught.value.row,
        caught.value.column,
    ) == ("FORMULA_VALUE_UNAVAILABLE", "Data", 7, 1)
    assert "example.test" not in str(caught.value)


def test_missing_shared_string_index_is_structured_with_location():
    data = workbook('<row r="3"><c r="B3" t="s"/></row>')
    with pytest.raises(SourceParseError) as caught:
        parser.parse_source(data, "xlsx")
    assert (
        caught.value.code,
        caught.value.sheet,
        caught.value.row,
        caught.value.column,
    ) == (
        "MALFORMED_WORKBOOK",
        "Data",
        3,
        1,
    )


@pytest.mark.parametrize(
    "extra", [{"../evil.xml": "x"}, {"xl/vbaProject.bin": b"macro"}, {"/absolute": "x"}]
)
def test_unsafe_archive_not_extracted_or_executed(extra):
    with pytest.raises(SourceParseError, match="UNSAFE_WORKBOOK"):
        parser.parse_source(workbook("", extra=extra), "xlsx")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_xml_entities_rejected_before_expansion(encoding):
    unsafe = '<!DOCTYPE worksheet [<!ENTITY x "EXPAND">]><worksheet>&x;</worksheet>'
    with pytest.raises(SourceParseError, match="UNSAFE_WORKBOOK"):
        parser.parse_source(
            workbook("", extra={"xl/worksheets/sheet1.xml": unsafe}, encoding=encoding),
            "xlsx",
        )


def test_external_relationship_is_not_fetched():
    extra = {
        "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="https://example.test/data" TargetMode="External"/></Relationships>'
    }
    with pytest.raises(SourceParseError, match="UNSAFE_WORKBOOK"):
        parser.parse_source(workbook("", extra=extra), "xlsx")


def test_size_columns_rows_limits_fail_without_truncation(monkeypatch):
    monkeypatch.setattr(parser, "MAX_FILE", 10)
    with pytest.raises(SourceParseError, match="RESOURCE_LIMIT_EXCEEDED"):
        parser.parse_source(b"x" * 11, "csv")
    monkeypatch.setattr(parser, "MAX_FILE", 1024 * 1024)
    monkeypatch.setattr(parser, "MAX_ROWS", 1)
    with pytest.raises(SourceParseError, match="RESOURCE_LIMIT_EXCEEDED"):
        parser.parse_source(b"key\nA\nB\n", "csv")
    monkeypatch.setattr(parser, "MAX_COLUMNS", 1)
    with pytest.raises(SourceParseError, match="RESOURCE_LIMIT_EXCEEDED"):
        parser.parse_source(workbook('<row r="1"><c r="B1"><v>0</v></c></row>'), "xlsx")


@pytest.mark.parametrize(
    "content,code",
    [
        (b"\xff", "INVALID_CSV_ENCODING"),
        (b'key,value\nA,"unclosed', "MALFORMED_CSV"),
        (b"\0binary", "INVALID_FILE_TYPE"),
    ],
)
def test_invalid_csv_is_structured(content, code):
    with pytest.raises(SourceParseError) as caught:
        parser.parse_source(content, "csv")
    assert caught.value.code == code
