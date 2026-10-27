"""Read an uploaded CSV into a DuckDB table where every column is text.

Everything is read as text on purpose. Automatic type detection silently turns
SKU "00810" into 810 and guesses date formats. Typing happens later in SQL,
where every failure becomes a visible rejection reason.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field

import duckdb
import pyarrow as pa

from retailpulse.report import Issue
from retailpulse.schema import LIMITS, Column

ROW_NUMBER = "_row_number"  # line number in the original file (header = line 1)
PARSE_ERROR = "_parse_error"  # set when a row can't be split into the right fields
_DELIMITERS = (",", ";", "\t", "|")


@dataclass
class RawFile:
    table: pa.Table | None = None
    columns_present: frozenset[str] = frozenset()
    raw_rows: int = 0
    blocking: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    info: list[Issue] = field(default_factory=list)


def normalize_header(header: str) -> str:
    """'Unit Price ($)' -> 'unit_price', 'StockCode' -> 'stock_code', 'Qty.' -> 'qty'."""
    text = header.replace("﻿", "").strip()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)  # camelCase -> camel_Case
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text.lower())
    return text.strip("_")


def _decode(data: bytes) -> tuple[str, Issue | None]:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16"), None
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        pass
    note = Issue(
        "not_utf8",
        "File is not UTF-8, so it was read as Windows-1252 (the usual Excel encoding). "
        "Check that accented characters in product names look right.",
    )
    try:
        return data.decode("cp1252"), note
    except UnicodeDecodeError:
        return data.decode("latin-1"), note


def _detect_delimiter(text: str) -> str:
    first_line = text.split("\n", 1)[0]
    counts = {d: first_line.count(d) for d in _DELIMITERS}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def _map_columns(
    headers: list[str], spec: tuple[Column, ...]
) -> tuple[dict[str, int], list[Issue], list[str]]:
    lookup: dict[str, str] = {}
    for col in spec:
        lookup[col.name] = col.name
        for alias in col.aliases:
            lookup.setdefault(alias, col.name)

    mapping: dict[str, int] = {}
    problems: list[Issue] = []
    ignored: list[str] = []
    for idx, header in enumerate(headers):
        canonical = lookup.get(normalize_header(header))
        if canonical is None:
            if header.strip():
                ignored.append(header.strip())
        elif canonical in mapping:
            first = headers[mapping[canonical]].strip()
            problems.append(Issue(
                "duplicate_column",
                f"Both '{first}' and '{header.strip()}' look like the '{canonical}' column. "
                "Remove or rename one of them.",
            ))
        else:
            mapping[canonical] = idx

    missing = [c.name for c in spec if c.required and c.name not in mapping]
    if missing:
        found = ", ".join(h.strip() for h in headers if h.strip()) or "(none)"
        problems.append(Issue(
            "missing_columns",
            f"Required column(s) missing: {', '.join(missing)}. Columns found: {found}.",
            count=len(missing),
            examples=tuple(missing),
        ))
    return mapping, problems, ignored


CHUNK_ROWS = 50_000


class _Chunk:
    """Up to CHUNK_ROWS parsed rows, column by column, before conversion to Arrow."""

    def __init__(self, spec: tuple[Column, ...]) -> None:
        self.spec = spec
        self.values: dict[str, list[str]] = {c.name: [] for c in spec}
        self.row_numbers: list[int] = []
        self.parse_errors: list[str | None] = []

    def to_batch(self) -> pa.RecordBatch:
        arrays = [pa.array(self.row_numbers, pa.int64())]
        arrays += [pa.array(self.values[c.name], pa.string()) for c in self.spec]
        arrays.append(pa.array(self.parse_errors, pa.string()))
        names = [ROW_NUMBER, *(c.name for c in self.spec), PARSE_ERROR]
        return pa.record_batch(arrays, names=names)


def _lines(text: str):
    """Yield lines with their endings, without copying the whole text (unlike io.StringIO)."""
    start = 0
    while start < len(text):
        end = text.find("\n", start)
        if end == -1:
            yield text[start:]
            return
        yield text[start:end + 1]
        start = end + 1


def read_csv(data: bytes, spec: tuple[Column, ...]) -> RawFile:
    """Parse CSV bytes into an all-text Arrow table with one column per spec column."""
    result = RawFile()
    if len(data) > LIMITS.max_upload_bytes:
        mb = LIMITS.max_upload_bytes // (1024 * 1024)
        result.blocking.append(Issue("file_too_large", f"File is larger than {mb} MB."))
        return result

    text, encoding_note = _decode(data)
    if encoding_note:
        result.warnings.append(encoding_note)

    if "\n" not in text:  # old Mac files end lines with a bare "\r"
        text = text.replace("\r", "\n")
    reader = csv.reader(_lines(text), delimiter=_detect_delimiter(text))
    try:
        headers = next(reader, None)
        if headers is None or not any(h.strip() for h in headers):
            result.blocking.append(Issue("empty_file", "File is empty or has no header row."))
            return result

        mapping, problems, ignored = _map_columns(headers, spec)
        if problems:
            result.blocking.extend(problems)
            return result

        # Rows are converted to Arrow in chunks: holding every value of a large file as
        # Python strings at once costs several times the file size in memory.
        batches: list[pa.RecordBatch] = []
        chunk = _Chunk(spec)
        blank_rows = 0
        for row in reader:
            if not any(v.strip() for v in row):
                blank_rows += 1
                continue
            chunk.row_numbers.append(reader.line_num)
            chunk.parse_errors.append(
                None if len(row) == len(headers) else "wrong_number_of_fields")
            for col in spec:
                idx = mapping.get(col.name)
                chunk.values[col.name].append(
                    row[idx] if idx is not None and idx < len(row) else "")
            if len(chunk.row_numbers) == CHUNK_ROWS:
                batches.append(chunk.to_batch())
                chunk = _Chunk(spec)
        if chunk.row_numbers:
            batches.append(chunk.to_batch())
    except csv.Error as exc:
        result.blocking.append(Issue("unreadable_file", f"Could not read the file as CSV: {exc}"))
        return result

    if not batches:
        result.blocking.append(Issue("no_data_rows", "File has a header row but no data rows."))
        return result

    result.table = pa.Table.from_batches(batches)
    result.raw_rows = result.table.num_rows
    result.columns_present = frozenset(mapping)

    if ignored:
        result.info.append(Issue(
            "ignored_columns", f"Columns not used by RetailPulse: {', '.join(ignored)}.",
            count=len(ignored), examples=tuple(ignored[: LIMITS.max_examples]),
        ))
    if blank_rows:
        result.info.append(Issue(
            "blank_rows_skipped", f"{blank_rows} completely blank row(s) were skipped.",
            count=blank_rows,
        ))
    return result


def load_table(con: duckdb.DuckDBPyConnection, name: str, table: pa.Table) -> None:
    """Materialise an Arrow table as a DuckDB table. `name` is an internal constant."""
    con.register("_incoming", table)
    try:
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _incoming")
    finally:
        con.unregister("_incoming")
