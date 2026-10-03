"""SQL result comparison with duplicate-sensitive, rounded numeric values."""

from collections import Counter
from dataclasses import dataclass

from bmq.db import Result


@dataclass
class Diff:
    column_count_mismatch: bool
    missing: list[tuple]
    extra: list[tuple]


def _rows(result: Result) -> list[tuple]:
    return [tuple(round(value, 6) if isinstance(value, float) else value for value in row) for row in result.rows]


def equal(expected: Result, actual: Result, order_matters: bool = False) -> bool:
    if len(expected.columns) != len(actual.columns):
        return False
    expected_rows, actual_rows = _rows(expected), _rows(actual)
    if order_matters:
        return expected_rows == actual_rows
    return Counter(expected_rows) == Counter(actual_rows)


def diff(expected: Result, actual: Result) -> Diff:
    expected_counts, actual_counts = Counter(_rows(expected)), Counter(_rows(actual))
    return Diff(
        column_count_mismatch=len(expected.columns) != len(actual.columns),
        missing=list((expected_counts - actual_counts).elements()),
        extra=list((actual_counts - expected_counts).elements()),
    )
