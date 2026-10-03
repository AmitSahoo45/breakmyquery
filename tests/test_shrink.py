from contextlib import closing
from copy import deepcopy
import sqlite3

import pytest

from bmq.compare import equal
from bmq.db import LoadError, build_db, run_query
from bmq.shrink import shrink


def test_shrink_finds_single_customer_join_counterexample_without_mutating_input():
    data = {
        "customers": [[1, "Asha", "Pune"], [2, "Ravi", None]],
        "products": [[1, "Pen", None, 100]],
        "orders": [[1, 1, "2026-09-01 00:00", "paid"]],
        "order_items": [[1, 1, 1, 2]],
    }
    original = deepcopy(data)

    def still_fails(candidate):
        with closing(build_db(candidate)) as conn:
            expected = run_query(conn, "SELECT c.name FROM customers c LEFT JOIN orders o ON o.customer_id=c.id", 1)
            actual = run_query(conn, "SELECT c.name FROM customers c JOIN orders o ON o.customer_id=c.id", 1)
            return not equal(expected, actual)

    small = shrink(data, still_fails)
    assert data == original
    assert small == {"customers": [[1, "Asha", "Pune"]], "products": [], "orders": [], "order_items": []}
    assert still_fails(small)


def test_shrink_keeps_required_parent_rows_and_is_row_minimal():
    data = {
        "customers": [[1, "Asha", "Pune"], [2, "Extra", None]],
        "products": [[1, "Pen", None, 100], [2, "Extra", None, 0]],
        "orders": [[1, 1, "2026-09-01 00:00", "paid"]],
        "order_items": [[1, 1, 1, 2]],
    }

    def still_fails(candidate):
        return any(row[3] == 2 for row in candidate["order_items"])

    small = shrink(data, still_fails)
    assert sum(map(len, small.values())) == 4
    for table, rows in small.items():
        for index in range(len(rows)):
            candidate = deepcopy(small)
            del candidate[table][index]
            try:
                with closing(build_db(candidate)):
                    assert not still_fails(candidate)
            except LoadError:
                pass


def test_shrink_revisits_rows_when_later_table_deletions_enable_more_removals():
    data = {"customers": [[1, "Asha", None]], "products": [[1, "Pen", None, 100]], "orders": [], "order_items": []}

    def still_fails(candidate):
        # Products are visited before customers. The product cannot disappear
        # until the customer has gone, so a second pass is required.
        return not candidate["customers"] or bool(candidate["products"])

    assert shrink(data, still_fails) == {"customers": [], "products": [], "orders": [], "order_items": []}


def test_shrink_closes_validation_connections(monkeypatch):
    import importlib
    module = importlib.import_module("bmq.shrink")
    connections = []

    def tracked_build(data):
        conn = build_db(data)
        connections.append(conn)
        return conn

    monkeypatch.setattr(module, "build_db", tracked_build)
    shrink({"customers": [[1, "Asha", None]], "products": [], "orders": [], "order_items": []}, lambda _: True)
    assert connections
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
