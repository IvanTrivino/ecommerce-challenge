from decimal import Decimal
from pathlib import Path

import pytest

from app.services.products.imports.csv_records import CsvRecord, iter_records
from app.services.products.imports.rows import (
    BLANK,
    HeaderError,
    ImportRow,
    RowError,
    category_code,
    parse_header,
    parse_row,
)

FIXTURE = Path(__file__).parents[3] / "fixtures" / "product-import-example.csv"
HEADER = "name,sku,description,category,price,stock,weight_kg".split(",")


def record(*fields: str, line: int = 2) -> CsvRecord:
    return CsvRecord(line=line, end_offset=0, fields=list(fields), next_line=line + 1)


@pytest.fixture
def columns() -> dict[str, int]:
    return parse_header(HEADER)


def test_parse_header_is_case_and_space_insensitive() -> None:
    result = parse_header([" NAME ", "Sku", "CATEGORY", "price ", " Stock"])

    assert result["name"] == 0
    assert "description" not in result


def test_parse_header_ignores_unknown_columns() -> None:
    result = parse_header(["name", "color", "sku", "category", "price", "stock"])

    assert result["sku"] == 2
    assert result["__count__"] == 6


def test_parse_header_missing_columns() -> None:
    with pytest.raises(HeaderError, match="^Missing columns: price, stock$"):
        parse_header(["name", "sku", "category"])


def test_parse_header_duplicate_column() -> None:
    with pytest.raises(HeaderError, match="^Duplicate column: sku$"):
        parse_header(["name", "sku", "SKU", "category", "price", "stock"])


@pytest.mark.parametrize("fields", [None, []])
def test_parse_header_not_a_csv(fields: list[str] | None) -> None:
    with pytest.raises(HeaderError, match="^File is not a UTF-8 CSV$"):
        parse_header(fields)


def test_valid_row(columns: dict[str, int]) -> None:
    result = parse_row(
        record(" Mug ", " M-1 ", " ceramic ", " Kitchen ", "12.5", "40", "0.35"),
        columns,
    )

    assert result == ImportRow(
        line=2,
        sku="M-1",
        name="Mug",
        category="Kitchen",
        price=Decimal("12.50"),
        stock=40,
        description="ceramic",
        weight=Decimal("0.350"),
    )


def test_optional_fields_default_to_none(columns: dict[str, int]) -> None:
    result = parse_row(record("Mug", "M-1", "", "Kitchen", "0", "0", ""), columns)

    assert isinstance(result, ImportRow)
    assert result.description is None
    assert result.weight is None
    assert result.price == Decimal("0.00")


def test_missing_optional_columns() -> None:
    columns = parse_header(["name", "sku", "category", "price", "stock"])

    result = parse_row(record("Mug", "M-1", "Kitchen", "1", "2"), columns)

    assert isinstance(result, ImportRow)
    assert result.description is None
    assert result.weight is None


@pytest.mark.parametrize("fields", [("", "", "", "", "", "", ""), ("  ",) * 7, ()])
def test_blank_rows(columns: dict[str, int], fields: tuple[str, ...]) -> None:
    assert parse_row(record(*fields), columns) is BLANK


def test_invalid_utf8_record(columns: dict[str, int]) -> None:
    bad = CsvRecord(line=9, end_offset=0, fields=None, next_line=10)

    assert parse_row(bad, columns) == RowError(9, None, "invalid UTF-8")


def test_wrong_field_count(columns: dict[str, int]) -> None:
    result = parse_row(record("a", "b", "c"), columns)

    assert result == RowError(2, None, "expected 7 fields, found 3")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": ""}, "name: required"),
        ({"name": "x" * 256}, "name: max 255 characters"),
        ({"sku": ""}, "sku: required"),
        ({"sku": "x" * 101}, "sku: max 100 characters"),
        ({"category": ""}, "category: required"),
        ({"category": "x" * 256}, "category: max 255 characters"),
        ({"price": "$29.99"}, "price: must be a number like 12.50"),
        ({"price": "free"}, "price: must be a number like 12.50"),
        ({"price": "-1"}, "price: must be a number like 12.50"),
        ({"price": "1.234"}, "price: must be a number like 12.50"),
        ({"price": "123456789"}, "price: must be a number like 12.50"),
        ({"stock": "-5"}, "stock: must be a whole number ≥ 0"),
        ({"stock": "1.5"}, "stock: must be a whole number ≥ 0"),
        ({"stock": "2147483648"}, "stock: must be a whole number ≥ 0"),
        ({"weight_kg": "0"}, "weight_kg: must be a number > 0 with up to 3 decimals"),
        (
            {"weight_kg": "1.2345"},
            "weight_kg: must be a number > 0 with up to 3 decimals",
        ),
        ({"weight_kg": "abc"}, "weight_kg: must be a number > 0 with up to 3 decimals"),
    ],
)
def test_row_rules(
    columns: dict[str, int], overrides: dict[str, str], message: str
) -> None:
    values = {
        "name": "Mug",
        "sku": "M-1",
        "description": "",
        "category": "Kitchen",
        "price": "1.00",
        "stock": "1",
        "weight_kg": "",
    } | overrides

    result = parse_row(record(*[values[name] for name in HEADER]), columns)

    assert isinstance(result, RowError)
    assert result.message == message


def test_boundary_values_are_accepted(columns: dict[str, int]) -> None:
    result = parse_row(
        record("n", "s", "", "c", "99999999.99", "2147483647", "9999999.999"), columns
    )

    assert isinstance(result, ImportRow)


def test_all_field_errors_are_reported_together(columns: dict[str, int]) -> None:
    result = parse_row(record("", "S-1", "", "", "x", "-1", "0"), columns)

    assert result == RowError(
        2,
        "S-1",
        "name: required; category: required; price: must be a number like 12.50; "
        "stock: must be a whole number ≥ 0; "
        "weight_kg: must be a number > 0 with up to 3 decimals",
    )


def test_long_sku_is_truncated_in_the_error(columns: dict[str, int]) -> None:
    result = parse_row(record("n", "s" * 150, "", "c", "1", "1", ""), columns)

    assert isinstance(result, RowError)
    assert result.sku == "s" * 100


def test_bad_rows_of_the_example_file(columns: dict[str, int]) -> None:
    chunks = [FIXTURE.read_bytes()]
    parsed = {
        r.line: parse_row(r, columns)
        for r in iter_records(
            chunks, start_offset=0, start_line=1, max_record_bytes=64 * 1024
        )
        if r.line > 1
    }

    errors = {line: p for line, p in parsed.items() if isinstance(p, RowError)}
    assert {line: e.message for line, e in errors.items()} == {
        4: "price: must be a number like 12.50",
        7: "price: must be a number like 12.50",
        16: "stock: must be a whole number ≥ 0",
        25: "name: required",
        41: "name: required",
        52: "category: required; weight_kg: must be a number > 0 with up to 3 decimals",
    }
    assert errors[4].sku == "WM-042"
    assert sum(1 for p in parsed.values() if p is BLANK) == 2
    assert sum(1 for p in parsed.values() if isinstance(p, ImportRow)) == 89


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Outdoors clothes", "OUTDOORS_CLOTHES"),
        ("Food & Beverage", "FOOD_BEVERAGE"),
        ("Home & Office", "HOME_OFFICE"),
        ("  Électronique  ", "LECTRONIQUE"),
        ("&&&", "CATEGORY"),
        ("word " * 12, "WORD_WORD_WORD_WORD_WORD_WORD_WORD_WORD"),
    ],
)
def test_category_code(name: str, expected: str) -> None:
    assert category_code(name) == expected
