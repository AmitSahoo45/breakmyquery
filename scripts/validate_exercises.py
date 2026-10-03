"""Verify authored samples, hidden traps, and equivalent alternatives in SQLite.

This developer-only script reads answers and authored traps. Neither these
fixtures nor this validator is part of counterexample hunting.
"""

from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmq.compare import equal
from bmq.db import LoadError, QueryError, build_db, run_query


TRAP_TYPES = {
    "JOIN_TYPE", "ON_VS_WHERE", "COUNT_STAR_VS_COLUMN", "NULL_COMPARISON",
    "JOIN_FANOUT", "AGGREGATE_LOGIC", "TIES", "INTEGER_DIVISION",
    "DATE_BOUNDARY", "GROUP_BY_GRAIN", "ANTI_JOIN", "OTHER",
}
REQUIRED_FIELDS = {
    "id", "title", "question", "expected_columns", "order_matters",
    "reference_sql", "known_wrong", "known_correct", "sample_data", "trap_datasets",
}


class ValidationError(ValueError):
    """An exercise no longer demonstrates the intended sample/hidden bug."""


def _require(condition, context, message):
    if not condition:
        raise ValidationError(f"{context}: {message}")


def _query(conn, sql, context):
    try:
        return run_query(conn, sql, timeout_s=2.0)
    except QueryError as exc:
        raise ValidationError(f"{context}: query failed: {exc}") from exc


def _check_design(exercise):
    """Keep the teaching examples promised in section 5.4 of the build spec."""
    ident = exercise["id"]
    sample = exercise["sample_data"]
    traps = exercise["trap_datasets"]
    customers, orders = sample["customers"], sample["orders"]
    sample_context = f"{ident} sample design"
    trap_context = f"{ident} trap design"

    if ident == "e2_not_in_pune":
        cities = [row[2] for row in customers]
        _require(None not in cities and cities.count("Pune") >= 1
                 and sum(city != "Pune" for city in cities) >= 2,
                 sample_context, "need Pune and at least two non-Pune customers, no NULL city")
        _require(any(row[2] is None for data in traps for row in data["customers"]),
                 trap_context, "need an unknown city")

    elif ident == "e3_paid_orders_revenue":
        paid = [row for row in orders if row[3] == "paid"]
        items = sample["order_items"]
        _require(len({row[1] for row in paid}) >= 2 and all(
            len(lines := [item for item in items if item[1] == order[0]]) == 1
            and lines[0][3] == 1 for order in paid),
            sample_context, "need two paid customers and one quantity-one line per paid order")
        _require(any(order[3] == "cancelled" and any(item[1] == order[0] for item in items)
                     for order in orders), sample_context, "need a cancelled order with items")
        _require(any(
            len(lines := [item for item in data["order_items"] if item[1] == order[0]]) == 2
            and any(item[3] == 2 for item in lines)
            for data in traps for order in data["orders"] if order[3] == "paid"
        ), trap_context, "need a paid order with two lines, including quantity two")

    elif ident == "e4_most_expensive":
        prices = [row[3] for row in sample["products"]]
        _require(bool(prices) and prices.count(max(prices)) == 1,
                 sample_context, "need a single highest-priced product")
        _require(any(data["products"] and sum(
            row[3] == max(item[3] for item in data["products"]) for row in data["products"]
        ) >= 2 for data in traps), trap_context, "need products tied at the highest price")

    elif ident == "e5_cancellation_rate":
        cancelled = sum(row[3] == "cancelled" for row in orders)
        _require(bool(orders) and cancelled * 100 % len(orders) == 0,
                 sample_context, "need a whole-number cancellation percentage")
        _require(any(len(data["orders"]) == 3 and sum(
            row[3] == "cancelled" for row in data["orders"]
        ) == 1 for data in traps), trap_context, "need one cancellation out of three orders")

    elif ident == "e6_september_orders":
        paid_dates = {row[2] for row in orders if row[3] == "paid"}
        _require(all(row[2].startswith("2026-") for row in orders)
                 and any(date.startswith("2026-09-") for date in paid_dates)
                 and not any(date.startswith("2026-09-30") for date in paid_dates)
                 and {"2026-08-31 23:30", "2026-10-01 00:00"} <= paid_dates,
                 sample_context, "need September 2026 and adjacent month boundaries, excluding September 30")
        trap_dates = {row[2] for data in traps for row in data["orders"] if row[3] == "paid"}
        _require({"2026-09-30 18:45", "2025-09-10 10:00"} <= trap_dates,
                 trap_context, "need late September 30 and a different September year")

    elif ident == "e7_more_than_two_orders":
        counts = Counter(row[1] for row in orders)
        _require(len({row[1] for row in customers}) == len(customers)
                 and any(counts[row[0]] > 2 for row in customers)
                 and any(counts[row[0]] <= 2 for row in customers),
                 sample_context, "need unique names and customers above and below the threshold")
        _require(any(
            {1, 2} <= {sum(order[1] == customer[0] for order in data["orders"])
                       for customer in data["customers"] if customer[1] == "Ravi"}
            for data in traps), trap_context, "need two Ravi customers with one and two orders")

    elif ident == "e8_never_paid":
        statuses = [[order[3] for order in orders if order[1] == customer[0]]
                    for customer in customers]
        _require(len({row[1] for row in customers}) == len(customers)
                 and all(values and (set(values) == {"paid"} or values == ["cancelled"])
                         for values in statuses)
                 and any(set(values) == {"paid"} for values in statuses)
                 and ["cancelled"] in statuses,
                 sample_context, "need unique names, paid-only customers, and single-cancellation customers")
        _require(any(
            any(not any(order[1] == row[0] for order in data["orders"]) for row in data["customers"])
            and any(sorted(order[3] for order in data["orders"] if order[1] == row[0])
                    == ["cancelled", "paid"] for row in data["customers"])
            for data in traps), trap_context, "need an orderless customer and a customer with both statuses")


def validate_exercise(exercise):
    """Raise a contextual ValidationError for the first violated invariant."""
    _require(isinstance(exercise, dict), "catalog", "each exercise must be an object")
    ident = exercise.get("id", "<missing id>")
    _require(REQUIRED_FIELDS <= exercise.keys(), ident,
             f"missing fields: {', '.join(sorted(REQUIRED_FIELDS - exercise.keys()))}")
    for field in ("id", "title", "question", "reference_sql"):
        _require(isinstance(exercise[field], str) and exercise[field].strip(), ident,
                 f"{field} must be a nonempty string")
    _require(isinstance(exercise["order_matters"], bool), ident, "order_matters must be boolean")
    for field in ("expected_columns", "known_wrong", "known_correct", "trap_datasets"):
        _require(isinstance(exercise[field], list) and exercise[field], ident,
                 f"{field} must be a nonempty list")
    _require(all(isinstance(name, str) and name for name in exercise["expected_columns"]),
             ident, "expected_columns must contain column names")
    for index, wrong in enumerate(exercise["known_wrong"]):
        _require(isinstance(wrong, dict) and isinstance(wrong.get("sql"), str), ident,
                 f"known_wrong[{index}] needs SQL")
        _require(wrong.get("trap") in TRAP_TYPES, ident,
                 f"known_wrong[{index}] has an unknown trap category")
    _require(all(isinstance(sql, str) and sql.strip() for sql in exercise["known_correct"]),
             ident, "known_correct must contain nonempty SQL")

    broken = [False] * len(exercise["known_wrong"])
    datasets = [("sample", exercise["sample_data"])] + [
        (f"trap[{index}]", dataset) for index, dataset in enumerate(exercise["trap_datasets"])
    ]
    for label, dataset in datasets:
        context = f"{ident} {label}"
        try:
            conn = build_db(dataset)
        except LoadError as exc:
            raise ValidationError(f"{context}: dataset failed to load: {exc}") from exc
        with closing(conn):
            expected = _query(conn, exercise["reference_sql"], f"{context} reference")
            _require(len(exercise["expected_columns"]) == len(expected.columns), context,
                     "expected_columns length differs from reference column count")
            if label == "sample":
                _require(bool(expected.rows), context, "reference returned no rows")
            for index, wrong in enumerate(exercise["known_wrong"]):
                actual = _query(conn, wrong["sql"], f"{context} known_wrong[{index}]")
                matches = equal(expected, actual, order_matters=exercise["order_matters"])
                if label == "sample":
                    _require(matches, ident, f"known_wrong[{index}] does not match the sample")
                else:
                    broken[index] |= not matches
            for index, sql in enumerate(exercise["known_correct"]):
                actual = _query(conn, sql, f"{context} known_correct[{index}]")
                _require(equal(expected, actual, order_matters=exercise["order_matters"]),
                         ident, f"known_correct[{index}] differs on {label}")
    for index, breaks in enumerate(broken):
        _require(breaks, ident, f"known_wrong[{index}] never differs on a trap dataset")
    _check_design(exercise)


def validate_exercises(exercises):
    """Validate a nonempty catalog and require unique exercise identifiers."""
    _require(isinstance(exercises, list) and exercises, "catalog", "expected a nonempty list")
    seen = set()
    for exercise in exercises:
        validate_exercise(exercise)
        _require(exercise["id"] not in seen, "catalog", f"duplicate id {exercise['id']}")
        seen.add(exercise["id"])


def main():
    try:
        exercises = json.loads((ROOT / "data" / "exercises.json").read_text(encoding="utf-8"))
        validate_exercises(exercises)
    except (OSError, ValueError) as exc:
        print(f"Exercise validation FAILED: {exc}", file=sys.stderr)
        return 1
    wrong_count = sum(len(exercise["known_wrong"]) for exercise in exercises)
    correct_count = sum(len(exercise["known_correct"]) for exercise in exercises)
    print(f"Validated {len(exercises)} exercises, {wrong_count} known-wrong queries, "
          f"and {correct_count} alternative queries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
