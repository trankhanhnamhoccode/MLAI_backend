"""Bounded CSV/XLSX value reader. No formulas, macros, links or canonical rules."""

import csv
import io
import posixpath
import zipfile
from xml.etree import ElementTree as ET

from app.application.contracts.import_source import (
    SourceCell,
    SourceRow,
    ParsedSheet,
    ParsedFile,
    SourceParseError,
)

MAX_FILE = 20 * 1024 * 1024
MAX_EXPANDED = 200 * 1024 * 1024
MAX_SHEETS = 100
MAX_ROWS = 100_000
MAX_COLUMNS = 256
MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def parse_source(content: bytes, format: str) -> ParsedFile:
    if type(content) is not bytes or len(content) > MAX_FILE:
        raise SourceParseError("RESOURCE_LIMIT_EXCEEDED")
    if format == "csv":
        return _csv(content)
    if format != "xlsx" or not content.startswith(b"PK"):
        raise SourceParseError("INVALID_FILE_TYPE")
    try:
        return _xlsx(content)
    except SourceParseError:
        raise
    except (
        zipfile.BadZipFile,
        KeyError,
        ET.ParseError,
        ValueError,
        OverflowError,
        OSError,
    ):
        raise SourceParseError("MALFORMED_WORKBOOK") from None


def _csv(content: bytes) -> ParsedFile:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        raise SourceParseError("INVALID_CSV_ENCODING") from None
    if "\0" in text:
        raise SourceParseError("INVALID_FILE_TYPE")
    sample = text[:8192]
    # Only delimiter detection; no guesses of date, decimal, identity or schema.
    try:
        delimiter = (
            csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter if sample else ","
        )
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    rows = []
    end = 0
    try:
        for record, values in enumerate(reader, 1):
            start, end = end + 1, reader.line_num
            if len(values) > MAX_COLUMNS or record > MAX_ROWS + 1:
                raise SourceParseError(
                    "RESOURCE_LIMIT_EXCEEDED", sheet="CSV", row=start
                )
            rows.append(
                SourceRow(
                    start,
                    tuple(
                        SourceCell(i, value, "empty" if value == "" else "text")
                        for i, value in enumerate(values)
                    ),
                    record,
                    start,
                    end,
                )
            )
    except csv.Error:
        raise SourceParseError(
            "MALFORMED_CSV", sheet="CSV", row=reader.line_num
        ) from None
    return ParsedFile("csv", (ParsedSheet("CSV", 0, tuple(rows)),))


def _xlsx(content: bytes) -> ParsedFile:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > 4096 or len(set(names)) != len(names):
            raise SourceParseError("MALFORMED_WORKBOOK")
        if sum(entry.file_size for entry in entries) > MAX_EXPANDED:
            raise SourceParseError("RESOURCE_LIMIT_EXCEEDED")
        for entry in entries:
            path = entry.filename
            if (
                path.startswith(("/", "\\"))
                or "\\" in path
                or ".." in path.split("/")
                or ":" in path
            ):
                raise SourceParseError("UNSAFE_WORKBOOK")
            if entry.flag_bits & 1:
                raise SourceParseError("UNSAFE_WORKBOOK")
        if any("vbaproject" in name.lower() for name in names):
            raise SourceParseError("UNSAFE_WORKBOOK")
        consumed = 0

        def xml(name):
            nonlocal consumed
            with archive.open(name) as stream:
                data = stream.read(MAX_EXPANDED - consumed + 1)
            consumed += len(data)
            if consumed > MAX_EXPANDED:
                raise SourceParseError("RESOURCE_LIMIT_EXCEEDED")
            declarations = data.replace(b"\0", b"").upper()
            if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
                raise SourceParseError("UNSAFE_WORKBOOK")
            return ET.fromstring(data)

        workbook = xml("xl/workbook.xml")
        relations = xml("xl/_rels/workbook.xml.rels")
        paths = {}
        for relation in relations:
            if relation.attrib.get("TargetMode") == "External":
                raise SourceParseError("UNSAFE_WORKBOOK")
            target = relation.attrib.get("Target", "")
            path = (
                posixpath.normpath(posixpath.join("xl", target))
                if not target.startswith("/")
                else target[1:]
            )
            if not path.startswith("xl/") or ".." in path.split("/"):
                raise SourceParseError("UNSAFE_WORKBOOK")
            paths[relation.attrib["Id"]] = path
        strings = []
        if "xl/sharedStrings.xml" in names:
            for node in xml("xl/sharedStrings.xml"):
                strings.append(
                    "".join(item.text or "" for item in node.iter(MAIN + "t"))
                )
        sheets = workbook.find(MAIN + "sheets")
        if sheets is None or len(sheets) > MAX_SHEETS:
            raise SourceParseError("RESOURCE_LIMIT_EXCEEDED")
        result, data_rows = [], 0
        for index, sheet in enumerate(sheets):
            name = sheet.attrib["name"]
            root = xml(paths[sheet.attrib[DOC_REL + "id"]])
            rows = []
            previous = 0
            for node in root.iter(MAIN + "row"):
                number = int(node.attrib["r"])
                if number <= previous or not 1 <= number <= 1_048_576:
                    raise SourceParseError("MALFORMED_WORKBOOK", sheet=name, row=number)
                previous = number
                cells, seen = [], set()
                for cell in node.findall(MAIN + "c"):
                    reference = cell.attrib["r"]
                    letters = reference.rstrip("0123456789")
                    if (
                        not letters
                        or not all("A" <= char <= "Z" for char in letters)
                        or reference[len(letters) :] != str(number)
                    ):
                        raise SourceParseError(
                            "MALFORMED_WORKBOOK", sheet=name, row=number
                        )
                    col = 0
                    for char in letters:
                        col = col * 26 + ord(char) - 64
                    col -= 1
                    if col >= MAX_COLUMNS:
                        raise SourceParseError(
                            "RESOURCE_LIMIT_EXCEEDED",
                            sheet=name,
                            row=number,
                            column=col,
                        )
                    if col in seen:
                        raise SourceParseError(
                            "MALFORMED_WORKBOOK", sheet=name, row=number, column=col
                        )
                    seen.add(col)
                    formula = cell.find(MAIN + "f") is not None
                    value = cell.find(MAIN + "v")
                    raw = value.text if value is not None else None
                    kind = cell.attrib.get("t", "n")
                    if formula and (value is None or raw is None):
                        raise SourceParseError(
                            "FORMULA_VALUE_UNAVAILABLE",
                            sheet=name,
                            row=number,
                            column=col,
                        )
                    if kind == "s":
                        if raw is None:
                            raise SourceParseError(
                                "MALFORMED_WORKBOOK", sheet=name, row=number, column=col
                            )
                        offset = int(raw)
                        if not 0 <= offset < len(strings):
                            raise SourceParseError(
                                "MALFORMED_WORKBOOK", sheet=name, row=number, column=col
                            )
                        raw, kind = strings[offset], "text"
                    elif kind == "inlineStr":
                        raw, kind = (
                            "".join(t.text or "" for t in cell.iter(MAIN + "t")),
                            "text",
                        )
                    elif kind in {"str", "b", "d", "e", "n"}:
                        kind = {
                            "str": "text",
                            "b": "boolean",
                            "d": "date",
                            "e": "error",
                            "n": "numeric",
                        }[kind]
                    else:
                        raise SourceParseError(
                            "MALFORMED_WORKBOOK", sheet=name, row=number, column=col
                        )
                    cells.append(
                        SourceCell(col, raw, "empty" if raw is None else kind, formula)
                    )
                rows.append(
                    SourceRow(
                        number, tuple(sorted(cells, key=lambda c: c.column_index))
                    )
                )
                data_rows += int(len(rows) > 1)
                if data_rows > MAX_ROWS:
                    raise SourceParseError(
                        "RESOURCE_LIMIT_EXCEEDED", sheet=name, row=number
                    )
            result.append(ParsedSheet(name, index, tuple(rows)))
        return ParsedFile("xlsx", tuple(result))
