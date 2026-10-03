"""Database boundaries: real SQLite constraints and bounded read-only queries."""

from contextlib import closing
from copy import deepcopy
import time

import pytest

from bmq.db import LoadError, QueryError, build_db, dump_dataset, run_query, validate_learner_sql


def dataset():
    return {
        "customers": [[2, "Ravi", None], [1, "Asha", "Pune"]],
        "products": [[1, "Pen", "Stationery", 100]],
        "orders": [[1, 1, "2026-09-02 10:15", "paid"]],
        "order_items": [[1, 1, 1, 2]],
    }


def test_load_and_dump_preserve_nulls_and_return_rows_in_primary_key_order():
    original = dataset()
    with closing(build_db(original)) as conn:
        expected = deepcopy(original)
        expected["customers"].reverse()
        assert dump_dataset(conn) == expected
        assert conn.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert conn.execute("PRAGMA temp_store").fetchone() == (2,)


@pytest.mark.parametrize("table,row", [
    ("orders", [2, 999, "2026-09-02 10:15", "paid"]),
    ("customers", [1, "Duplicate", None]),
    ("customers", [3, None, "Pune"]),
    ("products", [2, "Pen", None, -1]),
    ("orders", [2, 1, "yesterday", "paid"]),
    ("orders", [2, 1, "2026-09-02 10:15", "unknown"]),
    ("order_items", [2, 1, 1, 0]),
])
def test_load_rejects_schema_constraint_violations(table, row):
    data = dataset()
    data[table].append(row)
    with pytest.raises(LoadError):
        build_db(data)


@pytest.mark.parametrize("data", [
    {},
    {"customers": [], "products": [], "orders": [], "order_items": [], "other": []},
    {"customers": [[1]], "products": [], "orders": [], "order_items": []},
    {"customers": [[1, {}, None]], "products": [], "orders": [], "order_items": []},
])
def test_load_rejects_malformed_dataset_with_load_error(data):
    with pytest.raises(LoadError):
        build_db(data)


@pytest.mark.parametrize("sql,want", [
    ("-- before\n SELECT 1; -- after", "SELECT 1"),
    ("/* before */ select/* gap */1 /* after */;", "select 1"),
    ("WITH a AS (SELECT 1 AS n) SELECT n FROM a;", "WITH a AS (SELECT 1 AS n) SELECT n FROM a"),
    ("SELECT '-- stays; /* too */' AS text;", "SELECT '-- stays; /* too */' AS text"),
    ("SELECT 'it''s; -- fine' AS \"semi;col\";", "SELECT 'it''s; -- fine' AS \"semi;col\""),
    ("SELECT 1 AS [semi;col];", "SELECT 1 AS [semi;col]"),
    ("SELECT 1 AS `semi;col`;", "SELECT 1 AS `semi;col`"),
])
def test_sql_validation_preserves_quoted_content_and_strips_real_comments(sql, want):
    assert validate_learner_sql(sql) == want


@pytest.mark.parametrize("sql", [
    "", "-- only a comment", "DELETE FROM customers", "PRAGMA user_version",
    "SELECT 1; SELECT 2", "SELECT 1;;", "SELECT 'unterminated", "SELECT 1 /* unfinished",
    "SELECTED 1", "WITHDRAW 1", "SELECT 1\x00", None,
])
def test_sql_validation_rejects_unsafe_or_malformed_statements(sql):
    with pytest.raises(QueryError):
        validate_learner_sql(sql)


def test_query_returns_columns_rows_and_keeps_literals_unmodified():
    with closing(build_db(dataset())) as conn:
        result = run_query(conn, "SELECT name, '--literal;/*value*/' AS detail FROM customers ORDER BY id;", 1)
    assert result.columns == ["name", "detail"]
    assert result.rows == [("Asha", "--literal;/*value*/"), ("Ravi", "--literal;/*value*/")]


@pytest.mark.parametrize("sql", [
    "WITH a AS (SELECT 1) DELETE FROM customers",
    "WITH a AS (SELECT 1) UPDATE customers SET name = 'Changed'",
    "WITH a AS (SELECT 1) INSERT INTO customers VALUES (3, 'New', NULL)",
    "SELECT * FROM pragma_table_info('customers')",
    "SELECT * FROM pragma_database_list",
    "SELECT COUNT(*) FROM sqlite_master",
    "SELECT COUNT(*) FROM sqlite_schema",
    "SELECT load_extension('missing.dll')",
    "SELECT 1; DROP TABLE customers",
])
def test_query_rejects_mutations_and_privileged_access_and_remains_usable(sql):
    with closing(build_db(dataset())) as conn:
        with pytest.raises(QueryError):
            run_query(conn, sql, 1)
        assert run_query(conn, "SELECT name FROM customers ORDER BY id", 1).rows == [("Asha",), ("Ravi",)]


def test_query_wraps_sqlite_syntax_errors():
    with closing(build_db(dataset())) as conn:
        with pytest.raises(QueryError):
            run_query(conn, "SELECT no_such_column FROM customers", 1)


def test_query_allows_selecting_constant_values_from_a_cte():
    with closing(build_db(dataset())) as conn:
        assert run_query(conn, "WITH n(x) AS (VALUES (1), (2)) SELECT 'value' FROM n", 1).rows == [("value",), ("value",)]
        assert run_query(conn, "WITH n(x) AS (VALUES (1), (2)) SELECT COUNT(*) FROM n", 1).rows == [(2,)]


def test_closed_connection_error_is_wrapped_as_query_error():
    conn = build_db(dataset())
    conn.close()
    with pytest.raises(QueryError):
        run_query(conn, "SELECT 1", 1)


def test_recursive_query_times_out_and_next_query_succeeds():
    sql = "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT SUM(x) FROM n"
    with closing(build_db(dataset())) as conn:
        start = time.monotonic()
        with pytest.raises(QueryError, match="[Tt]ime|interrupt"):
            run_query(conn, sql, 0.01)
        assert time.monotonic() - start < 2
        assert run_query(conn, "SELECT COUNT(*) FROM customers", 1).rows == [(2,)]


def test_query_rejects_excessive_result_rows_instead_of_returning_partial_results():
    sql = "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<10001) SELECT x FROM n"
    with closing(build_db(dataset())) as conn:
        with pytest.raises(QueryError, match="[Rr]ow|[Ll]imit"):
            run_query(conn, sql, 2)


def test_query_bounds_native_blob_allocation():
    with closing(build_db(dataset())) as conn:
        with pytest.raises(QueryError, match="[Ll]arge|[Ll]imit|[Bb]ig"):
            run_query(conn, "SELECT zeroblob(100000000)", 1)
        assert run_query(conn, "SELECT 1", 1).rows == [(1,)]


def test_query_bounds_total_result_bytes():
    sql = "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100) SELECT zeroblob(100000) FROM n"
    with closing(build_db(dataset())) as conn:
        with pytest.raises(QueryError, match="[Ll]arge|[Ll]imit"):
            run_query(conn, sql, 2)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_query_rejects_nonpositive_or_nonfinite_timeout(timeout):
    with closing(build_db(dataset())) as conn:
        with pytest.raises(QueryError):
            run_query(conn, "SELECT 1", timeout)
