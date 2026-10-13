from pathlib import Path

import pytest

from app.services.products.imports.csv_records import (
    CsvRecord,
    UnterminatedRecordError,
    iter_records,
)

CHUNK_SIZES = [1, 2, 3, 7, 64 * 1024]
FIXTURE = Path(__file__).parents[3] / "fixtures" / "product-import-example.csv"


def chunked(data: bytes, size: int) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)] or [b""]


def records(
    data: bytes,
    chunk_size: int,
    *,
    start: int = 0,
    line: int = 1,
    max_record_bytes: int = 64 * 1024,
) -> list[CsvRecord]:
    return list(
        iter_records(
            chunked(data, chunk_size),
            start_offset=start,
            start_line=line,
            max_record_bytes=max_record_bytes,
        )
    )


@pytest.mark.parametrize("size", CHUNK_SIZES)
@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
def test_line_endings(size: int, eol: bytes) -> None:
    result = records(b"a,b" + eol + b"1,2" + eol + b"3,4", size)

    assert [r.fields for r in result] == [["a", "b"], ["1", "2"], ["3", "4"]]
    assert [r.line for r in result] == [1, 2, 3]


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_mixed_line_endings(size: int) -> None:
    result = records(b"a\r\nb\nc\r\n", size)

    assert [r.fields for r in result] == [["a"], ["b"], ["c"]]


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_final_newline_adds_no_phantom_record(size: int) -> None:
    data = b"a,b\n1,2\n"

    result = records(data, size)

    assert len(result) == 2
    assert result[-1].end_offset == len(data)


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_no_final_newline(size: int) -> None:
    data = b"a,b\n1,2"

    result = records(data, size)

    assert [r.fields for r in result] == [["a", "b"], ["1", "2"]]
    assert result[-1].end_offset == len(data)


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_quoted_commas_and_escaped_quotes(size: int) -> None:
    data = b'n,d\n"Quote ""Inside"" Name","a, b"\n'

    result = records(data, size)

    assert result[1].fields == ['Quote "Inside" Name', "a, b"]


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_quoted_field_spanning_lines(size: int) -> None:
    data = b'h\n"one\r\ntwo\r\nthree",x\nlast\n'

    result = records(data, size)

    assert result[1].fields == ["one\r\ntwo\r\nthree", "x"]
    assert result[1].line == 2
    assert result[1].next_line == 5
    assert result[2].line == 5
    assert result[2].fields == ["last"]


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_bom_is_stripped_but_counted(size: int) -> None:
    data = b"\xef\xbb\xbfname,sku\n1,2\n"

    result = records(data, size)

    assert result[0].fields == ["name", "sku"]
    assert result[0].end_offset == len(b"\xef\xbb\xbfname,sku\n")


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_invalid_utf8_only_affects_its_record(size: int) -> None:
    result = records(b"a\n\xff\xfe\nb\n", size)

    assert [r.fields for r in result] == [["a"], None, ["b"]]


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_multibyte_characters_split_across_chunks(size: int) -> None:
    data = "name\nWidget — ™ ñ\n".encode()

    assert records(data, size)[1].fields == ["Widget — ™ ñ"]


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_empty_line_is_an_empty_record(size: int) -> None:
    result = records(b"a\n\nb\n", size)

    assert [r.fields for r in result] == [["a"], [], ["b"]]


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_unterminated_quote_at_eof(size: int) -> None:
    with pytest.raises(UnterminatedRecordError) as exc_info:
        records(b'a\nb\n"oops,1\nmore\n', size)

    assert exc_info.value.line == 3
    assert str(exc_info.value) == "Line 3: unterminated quoted field"


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_record_larger_than_the_limit(size: int) -> None:
    data = b'a\n"' + b"x\n" * 100

    with pytest.raises(UnterminatedRecordError) as exc_info:
        records(data, size, max_record_bytes=50)

    assert exc_info.value.line == 2


@pytest.mark.parametrize("size", CHUNK_SIZES)
def test_example_file_end_offset_matches_its_size(size: int) -> None:
    data = FIXTURE.read_bytes()

    result = records(data, size)

    assert len(result) == 98
    assert result[-1].end_offset == len(data)
    assert [r.line for r in result] == list(range(1, 99))


@pytest.mark.parametrize("size", [3, 64 * 1024])
def test_resuming_from_any_record_boundary_yields_the_rest(size: int) -> None:
    data = FIXTURE.read_bytes()
    full = records(data, size)

    for index, record in enumerate(full[:-1]):
        resumed = records(
            data[record.end_offset :],
            size,
            start=record.end_offset,
            line=record.next_line,
        )
        assert resumed == full[index + 1 :]
