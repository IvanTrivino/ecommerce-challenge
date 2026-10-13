import csv
import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class CsvRecord:
    line: int
    end_offset: int
    fields: list[str] | None
    next_line: int


class UnterminatedRecordError(Exception):
    def __init__(self, line: int) -> None:
        super().__init__(f"Line {line}: unterminated quoted field")
        self.line = line


def _parse(data: bytes, *, strip_bom: bool) -> list[str] | None:
    if strip_bom and data.startswith(BOM):
        data = data[len(BOM) :]
    data = data.removesuffix(b"\n").removesuffix(b"\r")
    try:
        text = data.decode("utf-8")
        return next(csv.reader(io.StringIO(text, newline="")), [])
    except UnicodeDecodeError, csv.Error:
        return None


def iter_records(
    chunks: Iterable[bytes],
    *,
    start_offset: int,
    start_line: int,
    max_record_bytes: int,
) -> Iterator[CsvRecord]:
    buffer = bytearray()
    record = bytearray()
    quotes = 0
    offset = start_offset
    line = start_line
    first = start_offset == 0

    def emit(*, at_eof: bool) -> CsvRecord:
        nonlocal record, quotes, line, first
        data = bytes(record)
        newlines = data.count(b"\n")
        result = CsvRecord(
            line=line,
            end_offset=offset,
            fields=_parse(data, strip_bom=first),
            next_line=line
            + newlines
            + (1 if at_eof and not data.endswith(b"\n") else 0),
        )
        record = bytearray()
        quotes = 0
        line = result.next_line
        first = False
        return result

    for chunk in chunks:
        buffer.extend(chunk)
        while (index := buffer.find(b"\n")) >= 0:
            piece = bytes(buffer[: index + 1])
            del buffer[: index + 1]
            record.extend(piece)
            quotes += piece.count(b'"')
            offset += len(piece)
            if len(record) > max_record_bytes:
                raise UnterminatedRecordError(line)
            if quotes % 2 == 0:
                yield emit(at_eof=False)
        if len(record) + len(buffer) > max_record_bytes:
            raise UnterminatedRecordError(line)

    if buffer:
        record.extend(buffer)
        quotes += buffer.count(b'"')
        offset += len(buffer)
        buffer.clear()
    if record:
        if quotes % 2:
            raise UnterminatedRecordError(line)
        yield emit(at_eof=True)
