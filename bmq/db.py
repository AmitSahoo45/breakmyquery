"""Constrained, in-memory SQLite datasets and read-only learner queries."""

from collections.abc import Mapping
from dataclasses import dataclass
import math
from pathlib import Path
import re
import sqlite3
import time


TABLE_COLUMNS = {
    "customers": ("id", "name", "city"),
    "products": ("id", "name", "category", "price"),
    "orders": ("id", "customer_id", "order_date", "status"),
    "order_items": ("id", "order_id", "product_id", "quantity"),
}
TABLES = tuple(TABLE_COLUMNS)
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "data" / "schema.sql"
MAX_SQL_BYTES = 100_000
MAX_VALUE_BYTES = 1_000_000
MAX_RESULT_ROWS = 10_000
MAX_RESULT_BYTES = 4_000_000
MAX_DATASET_ROWS = 1_000


class LoadError(ValueError):
    """The proposed dataset does not fit the exercise schema."""


class QueryError(ValueError):
    """A learner query is invalid, unsafe, or exceeds execution limits."""


@dataclass
class Result:
    columns: list[str]
    rows: list[tuple]


def table_columns() -> dict[str, tuple[str, ...]]:
    """Return schema column order without exposing mutable shared state."""
    return dict(TABLE_COLUMNS)


def _limits(conn: sqlite3.Connection) -> None:
    # LENGTH bounds native SQLite allocations such as zeroblob/randomblob;
    # the progress handler alone cannot interrupt the middle of a function.
    for category, limit in (
        (sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES),
        (sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_SQL_BYTES),
        (sqlite3.SQLITE_LIMIT_COLUMN, 200),
        (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100),
        (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 50),
        (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
    ):
        conn.setlimit(category, min(conn.getlimit(category), limit))


def _validate_dataset(dataset) -> None:
    if not isinstance(dataset, Mapping) or set(dataset) != set(TABLES):
        raise LoadError("A dataset must contain exactly customers, products, orders, and order_items.")
    total_rows = 0
    total_bytes = 0
    for table in TABLES:
        rows = dataset[table]
        if not isinstance(rows, (list, tuple)):
            raise LoadError(f"{table} must contain a list of rows.")
        total_rows += len(rows)
        if total_rows > MAX_DATASET_ROWS:
            raise LoadError("Dataset exceeds the row limit.")
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != len(TABLE_COLUMNS[table]):
                raise LoadError(f"Each {table} row needs {len(TABLE_COLUMNS[table])} values in schema order.")
            for value in row:
                if value is not None and not isinstance(value, (int, float, str)):
                    raise LoadError("Dataset values must be numbers, text, or null.")
                if isinstance(value, float) and not math.isfinite(value):
                    raise LoadError("Dataset numbers must be finite.")
                total_bytes += len(value.encode("utf-8")) if isinstance(value, str) else 8
                if total_bytes > MAX_RESULT_BYTES:
                    raise LoadError("Dataset exceeds the size limit.")


def build_db(dataset) -> sqlite3.Connection:
    """Load one independent dataset; the caller owns and must close the connection."""
    _validate_dataset(dataset)
    conn = sqlite3.connect(":memory:")
    try:
        _limits(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -4096")
        conn.execute("PRAGMA max_page_count = 4096")
        conn.execute("PRAGMA trusted_schema = OFF")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        for table in TABLES:
            placeholders = ", ".join("?" for _ in TABLE_COLUMNS[table])
            conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", dataset[table])
        conn.commit()
        return conn
    except (sqlite3.Error, OverflowError, ValueError, OSError) as exc:
        conn.close()
        raise LoadError(str(exc)) from exc
    except BaseException:
        conn.close()
        raise


def dump_dataset(conn: sqlite3.Connection) -> dict[str, list[list]]:
    return {
        table: [list(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
        for table in TABLES
    }


def validate_learner_sql(sql: str) -> str:
    """Strip real comments and one terminator, respecting SQL quoted literals."""
    if not isinstance(sql, str) or not sql.strip():
        raise QueryError("Enter one SELECT or WITH query.")
    if "\x00" in sql or len(sql.encode("utf-8")) > MAX_SQL_BYTES:
        raise QueryError("Query contains a null character or exceeds the size limit.")
    output: list[str] = []
    unquoted: list[str] = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            index = len(sql) if end == -1 else end
            output.append(" ")
            unquoted.append(" ")
        elif sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end == -1:
                raise QueryError("Close the block comment with */.")
            index = end + 2
            output.append(" ")
            unquoted.append(" ")
        elif char in ("'", '"', "`", "["):
            start = index
            closing = "]" if char == "[" else char
            index += 1
            while index < len(sql):
                if sql[index] == closing:
                    if closing != "]" and index + 1 < len(sql) and sql[index + 1] == closing:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            else:
                raise QueryError("Close the quoted text or identifier.")
            output.append(sql[start:index])
            unquoted.append(" " * (index - start))
        else:
            output.append(char)
            unquoted.append(char)
            index += 1
    cleaned = "".join(output).strip()
    visible = "".join(unquoted).strip()
    if cleaned.endswith(";") and visible.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
        visible = visible[:-1].rstrip()
    if ";" in visible:
        raise QueryError("Run one query at a time; extra semicolons are not allowed.")
    if not re.match(r"(?:SELECT|WITH)\b", cleaned, flags=re.IGNORECASE):
        raise QueryError("Only SELECT or WITH queries are allowed.")
    return cleaned


def _read_only_authorizer(action, arg1, arg2, database, source):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        if arg1 in TABLES:
            return sqlite3.SQLITE_OK
        # COUNT(*) and constant projections can produce a READ with no
        # database. The dataset has only our four tables and SQLite's
        # catalogs; reject the catalogs and PRAGMA tables before allowing
        # these synthetic CTE reads.
        if database is None and not (arg1 or "").lower().startswith(("pragma_", "sqlite_")):
            return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() not in {
        "load_extension", "readfile", "writefile", "eval", "fts3_tokenizer",
    }:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run_query(conn: sqlite3.Connection, sql: str, timeout_s: float = 2.0) -> Result:
    """Execute a bounded read-only query, returning all rows or a QueryError."""
    cleaned = validate_learner_sql(sql)
    if not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise QueryError("Query timeout must be a finite positive number.")
    deadline = time.monotonic() + timeout_s
    cursor = None
    authorizer_installed = False
    progress_installed = False

    def expired():
        return time.monotonic() >= deadline

    try:
        _limits(conn)
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_read_only_authorizer)
        authorizer_installed = True
        conn.set_progress_handler(expired, 10_000)
        progress_installed = True
        cursor = conn.execute(cleaned)
        columns = [column[0] for column in cursor.description]
        rows = []
        result_bytes = 0
        for row in cursor:
            if expired():
                raise QueryError("Query timed out. Try a smaller query.")
            if len(rows) >= MAX_RESULT_ROWS:
                raise QueryError("Query exceeds the result row limit.")
            result_bytes += sum(
                len(value.encode("utf-8")) if isinstance(value, str)
                else len(value) if isinstance(value, bytes)
                else 8
                for value in row
            )
            if result_bytes > MAX_RESULT_BYTES:
                raise QueryError("Query result is too large; reduce the output to stay within the size limit.")
            rows.append(tuple(row))
        if expired():
            raise QueryError("Query timed out. Try a smaller query.")
        return Result(columns=columns, rows=rows)
    except sqlite3.Error as exc:
        message = "Query timed out. Try a smaller query." if expired() else str(exc)
        raise QueryError(message) from exc
    except MemoryError as exc:
        raise QueryError("Query exceeds SQLite's memory limits.") from exc
    finally:
        if cursor is not None:
            cursor.close()
        if progress_installed:
            conn.set_progress_handler(None, 0)
        if authorizer_installed:
            conn.set_authorizer(None)
