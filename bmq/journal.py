"""Repository-local history and bounded, private history for public sessions."""

from collections import deque
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from bmq.config import ROOT, get_settings
from bmq.llm import safe_text


_SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    exercise_id TEXT NOT NULL,
    learner_sql TEXT NOT NULL,
    verdict TEXT NOT NULL,
    found_by TEXT,
    mistake_type TEXT,
    what_happened TEXT,
    counterexample_json TEXT
)
"""


def _database_path(settings):
    # Settings can also be supplied directly, bypassing get_settings validation.
    directory = (ROOT / Path(settings.data_dir)).resolve()
    if not directory.is_relative_to(ROOT):
        raise ValueError("Journal data must stay inside the repository.")
    database = (directory / "journal.db").resolve()
    # Resolve the database and its sidecars, including existing links, before writes.
    for path in (database, *(Path(str(database) + suffix) for suffix in ("-journal", "-wal", "-shm"))):
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError("Journal files must stay inside the repository.")
    directory.mkdir(parents=True, exist_ok=True)
    return database


@contextmanager
def _connection(settings):
    path = _database_path(settings or get_settings())
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute(_SCHEMA)
        with connection:
            yield connection


def _classification(explanation):
    if explanation is None:
        return None, None
    return explanation.mistake_type, safe_text(explanation.what_happened)


class SessionJournal:
    """Own the most recent 50 attempts of one Streamlit session, only in memory.

    Instantiate per session, never as a shared resource. Public mode disables
    background explanations, so only that session's UI writes this store.
    """

    def __init__(self):
        self._attempts = deque(maxlen=50)
        self._next_id = 1

    def log_attempt(self, exercise_id, learner_sql, verdict, explanation=None, *, settings=None) -> int:
        mistake_type, what_happened = _classification(explanation)
        dataset = deepcopy(verdict.dataset)
        attempt_id = self._next_id
        self._attempts.appendleft({
            'id': attempt_id,
            'ts': datetime.now(timezone.utc).isoformat(),
            'exercise_id': exercise_id,
            'learner_sql': learner_sql,
            'verdict': verdict.status,
            'found_by': verdict.found_by,
            'mistake_type': mistake_type,
            'what_happened': what_happened,
            'counterexample_json': json.dumps(dataset, ensure_ascii=False) if dataset is not None else None,
            'counterexample': dataset,
        })
        self._next_id += 1
        return attempt_id

    def list_attempts(self, settings=None) -> list[dict]:
        return deepcopy(list(self._attempts))


def log_attempt(exercise_id, learner_sql, verdict, explanation=None, *, settings=None) -> int:
    """Retain one run, preserving authored SQL and nullable offline classification."""
    mistake_type, what_happened = _classification(explanation)
    counterexample_json = json.dumps(verdict.dataset, ensure_ascii=False) if verdict.dataset is not None else None
    with _connection(settings) as connection:
        cursor = connection.execute(
            """INSERT INTO attempts
               (ts, exercise_id, learner_sql, verdict, found_by, mistake_type,
                what_happened, counterexample_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), exercise_id, learner_sql,
             verdict.status, verdict.found_by, mistake_type, what_happened,
             counterexample_json),
        )
        return cursor.lastrowid


def update_explanation(attempt_id, explanation, *, settings=None):
    """Attach a background classification to its existing attempt."""
    mistake_type, what_happened = _classification(explanation)
    with _connection(settings) as connection:
        connection.execute(
            "UPDATE attempts SET mistake_type = ?, what_happened = ? WHERE id = ?",
            (mistake_type, what_happened, attempt_id),
        )


def list_attempts(settings=None) -> list[dict]:
    """Read newest runs first, including decoded counterexamples for the UI."""
    with _connection(settings) as connection:
        attempts = [dict(row) for row in connection.execute("SELECT * FROM attempts ORDER BY id DESC")]
    for attempt in attempts:
        stored = attempt["counterexample_json"]
        attempt["counterexample"] = json.loads(stored) if stored is not None else None
    return attempts
