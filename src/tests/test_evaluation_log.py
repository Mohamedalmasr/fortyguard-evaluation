import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


LOG_PATH = Path(__file__).resolve().parents[2] / "evaluation_log.csv"
EXPECTED_HEADER = [
    "record_type",
    "operation",
    "result",
    "trace_id",
    "latency_ms",
    "credit_cost",
    "details",
]
ALLOWED_RECORD_TYPES = {
    "executed_test",
    "schema_inspection",
    "catalog_finding",
    "finding",
}
REQUIRED_FIELDS = ("record_type", "operation", "result")
NUMERIC_OR_BLANK_FIELDS = ("latency_ms", "credit_cost")


def test_evaluation_log_has_exact_seven_column_header():
    with LOG_PATH.open(newline="", encoding="utf-8-sig") as log_file:
        reader = csv.reader(log_file)
        header = next(reader)

    assert header == EXPECTED_HEADER
    assert len(header) == 7


def test_evaluation_log_rows_have_seven_columns():
    with LOG_PATH.open(newline="", encoding="utf-8-sig") as log_file:
        rows = list(csv.reader(log_file))

    assert rows
    assert all(len(row) == 7 for row in rows)


def test_evaluation_log_uses_allowed_record_types():
    with LOG_PATH.open(newline="", encoding="utf-8-sig") as log_file:
        records = list(csv.DictReader(log_file))

    assert records
    assert all(record["record_type"] in ALLOWED_RECORD_TYPES for record in records)


def test_evaluation_log_has_required_fields():
    with LOG_PATH.open(newline="", encoding="utf-8-sig") as log_file:
        records = list(csv.DictReader(log_file))

    assert records
    assert all(
        record[field] is not None and record[field].strip()
        for record in records
        for field in REQUIRED_FIELDS
    )


def test_evaluation_log_latency_and_cost_are_numeric_or_blank():
    with LOG_PATH.open(newline="", encoding="utf-8-sig") as log_file:
        records = list(csv.DictReader(log_file))

    assert records
    for record in records:
        for field in NUMERIC_OR_BLANK_FIELDS:
            value = record[field]
            if value is None or not value.strip():
                continue
            try:
                number = Decimal(value)
            except InvalidOperation:
                assert False, f"{field} must be numeric or blank"
            assert number.is_finite(), f"{field} must be finite or blank"
