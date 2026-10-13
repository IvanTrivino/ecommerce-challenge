import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from app.services.products.imports.csv_records import CsvRecord

REQUIRED_COLUMNS = ("name", "sku", "category", "price", "stock")
OPTIONAL_COLUMNS = ("description", "weight_kg")
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
COUNT_KEY = "__count__"

MAX_STOCK = 2_147_483_647
_PRICE = re.compile(r"\d{1,8}(\.\d{1,2})?", re.ASCII)
_STOCK = re.compile(r"\d+", re.ASCII)
_WEIGHT = re.compile(r"\d{1,7}(\.\d{1,3})?", re.ASCII)
_PRICE_STEP = Decimal("0.01")
_WEIGHT_STEP = Decimal("0.001")


class HeaderError(Exception):
    pass


def parse_header(fields: list[str] | None) -> dict[str, int]:
    if not fields:
        raise HeaderError("File is not a UTF-8 CSV")
    columns: dict[str, int] = {}
    for index, raw in enumerate(fields):
        name = raw.strip().lower()
        if name not in KNOWN_COLUMNS:
            continue
        if name in columns:
            raise HeaderError(f"Duplicate column: {name}")
        columns[name] = index
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise HeaderError(f"Missing columns: {', '.join(missing)}")
    columns[COUNT_KEY] = len(fields)
    return columns


@dataclass(frozen=True)
class ImportRow:
    line: int
    sku: str
    name: str
    category: str
    price: Decimal
    stock: int
    description: str | None
    weight: Decimal | None


@dataclass(frozen=True)
class RowError:
    line: int
    sku: str | None
    message: str


class Blank:
    pass


BLANK = Blank()


def parse_row(
    record: CsvRecord, columns: dict[str, int]
) -> ImportRow | RowError | Blank:
    if record.fields is None:
        return RowError(record.line, None, "invalid UTF-8")
    fields = [value.strip() for value in record.fields]
    if not any(fields):
        return BLANK
    expected = columns[COUNT_KEY]
    if len(fields) != expected:
        return RowError(
            record.line, None, f"expected {expected} fields, found {len(fields)}"
        )

    def get(column: str) -> str:
        index = columns.get(column)
        return fields[index] if index is not None else ""

    name, sku, category = get("name"), get("sku"), get("category")
    price_text, stock_text = get("price"), get("stock")
    description, weight_text = get("description"), get("weight_kg")

    errors: list[str] = []
    for label, value, limit in (
        ("name", name, 255),
        ("sku", sku, 100),
        ("category", category, 255),
    ):
        if not value:
            errors.append(f"{label}: required")
        elif len(value) > limit:
            errors.append(f"{label}: max {limit} characters")

    price: Decimal | None = None
    if _PRICE.fullmatch(price_text):
        price = Decimal(price_text).quantize(_PRICE_STEP, ROUND_HALF_EVEN)
    else:
        errors.append("price: must be a number like 12.50")

    stock: int | None = None
    if _STOCK.fullmatch(stock_text) and int(stock_text) <= MAX_STOCK:
        stock = int(stock_text)
    else:
        errors.append("stock: must be a whole number ≥ 0")

    weight: Decimal | None = None
    if weight_text:
        if _WEIGHT.fullmatch(weight_text) and Decimal(weight_text) > 0:
            weight = Decimal(weight_text).quantize(_WEIGHT_STEP, ROUND_HALF_EVEN)
        else:
            errors.append("weight_kg: must be a number > 0 with up to 3 decimals")

    if errors or price is None or stock is None:
        # The column is `String(100)`: never store more than fits
        return RowError(record.line, sku[:100] or None, "; ".join(errors))
    return ImportRow(
        line=record.line,
        sku=sku,
        name=name,
        category=category,
        price=price,
        stock=stock,
        description=description or None,
        weight=weight,
    )


def category_code(name: str) -> str:
    code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:40].strip("_")
    return code or "CATEGORY"
