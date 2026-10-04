"""Real journal persistence, updates, and repository-contained writes."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import os
import shutil
import subprocess
from uuid import uuid4

import pytest

from bmq.config import ROOT, Settings
from bmq.hunter import Verdict
from bmq.llm import Explanation


@pytest.fixture
def journal_settings():
    directory = (ROOT / ".cache" / f"journal-tests-{uuid4().hex}").resolve()
    assert directory.is_relative_to(ROOT)
    directory.mkdir(parents=True)
    yield Settings(data_dir=directory)
    shutil.rmtree(directory)


def explanation(text="Kiran has no paid order and disappears."):
    return Explanation(mistake_type="JOIN_TYPE", what_happened=text,
                       nudge="Which clause keeps Kiran?", hint=None)


@pytest.mark.parametrize("status", ["ERROR", "WRONG_ON_SAMPLE", "HIDDEN_BUG", "PASSED"])
def test_logs_each_verdict_without_inventing_offline_classification(journal_settings, status):
    from bmq.journal import list_attempts, log_attempt

    authored_sql = "  SELECT 'learner''s query; DROP TABLE attempts'  -- as authored\n"
    before = datetime.now(timezone.utc)
    attempt_id = log_attempt("e1' ; DROP TABLE attempts; --", authored_sql,
                             Verdict(status=status), settings=journal_settings)
    after = datetime.now(timezone.utc)
    attempt = list_attempts(journal_settings)[0]
    assert attempt["id"] == attempt_id
    assert attempt["exercise_id"] == "e1' ; DROP TABLE attempts; --"
    assert attempt["learner_sql"] == authored_sql
    assert attempt["verdict"] == status
    assert attempt["mistake_type"] is None
    assert attempt["what_happened"] is None
    assert attempt["counterexample"] is None
    timestamp = datetime.fromisoformat(attempt["ts"])
    assert timestamp.utcoffset() == timezone.utc.utcoffset(timestamp)
    assert before <= timestamp <= after


def test_counterexample_round_trips_nulls_and_returns_newest_first(journal_settings):
    from bmq.journal import list_attempts, log_attempt

    dataset = {"customers": [[4, "Kiran", None]], "products": [],
               "orders": [], "order_items": []}
    old_id = log_attempt("e1", "first", Verdict(status="PASSED"), settings=journal_settings)
    new_id = log_attempt("e1", "second", Verdict(status="HIDDEN_BUG", dataset=dataset,
                         found_by="fuzz"), explanation(), settings=journal_settings)
    attempts = list_attempts(journal_settings)
    assert [attempt["id"] for attempt in attempts] == [new_id, old_id]
    assert attempts[0]["counterexample"] == dataset
    assert attempts[0]["found_by"] == "fuzz"
    assert attempts[0]["mistake_type"] == "JOIN_TYPE"
    assert attempts[0]["what_happened"] == "Kiran has no paid order and disappears."


def test_background_explanation_updates_existing_attempt_once(journal_settings):
    from bmq.journal import list_attempts, log_attempt, update_explanation

    attempt_id = log_attempt("e1", "SELECT name FROM customers", Verdict(status="HIDDEN_BUG"),
                             settings=journal_settings)
    original = list_attempts(journal_settings)[0]
    update_explanation(attempt_id, explanation(), settings=journal_settings)
    update_explanation(attempt_id, explanation("Kiran is missing from your result."),
                       settings=journal_settings)
    attempts = list_attempts(journal_settings)
    assert len(attempts) == 1
    assert attempts[0]["id"] == attempt_id
    assert attempts[0]["ts"] == original["ts"]
    assert attempts[0]["learner_sql"] == original["learner_sql"]
    assert attempts[0]["mistake_type"] == "JOIN_TYPE"
    assert attempts[0]["what_happened"] == "Kiran is missing from your result."


def test_model_sql_is_guarded_on_insert_and_background_update(journal_settings):
    from bmq.journal import list_attempts, log_attempt, update_explanation

    attempt_id = log_attempt("e1", "SELECT name FROM customers", Verdict(status="HIDDEN_BUG"),
                             explanation("Use SELECT name FROM customers."), settings=journal_settings)
    first = list_attempts(journal_settings)[0]
    assert "SELECT" not in first["what_happened"]
    assert first["learner_sql"] == "SELECT name FROM customers"
    update_explanation(attempt_id, explanation("```sql\nSELECT 1\n```"), settings=journal_settings)
    assert "SELECT" not in list_attempts(journal_settings)[0]["what_happened"]


def test_thread_calls_use_independent_connections(journal_settings):
    from bmq.journal import list_attempts, log_attempt, update_explanation

    list_attempts(journal_settings)
    def run(number):
        attempt_id = log_attempt("e1", str(number), Verdict(status="HIDDEN_BUG"),
                                 settings=journal_settings)
        update_explanation(attempt_id, explanation(), settings=journal_settings)
        return attempt_id
    with ThreadPoolExecutor(max_workers=4) as workers:
        attempt_ids = list(workers.map(run, range(12)))
    attempts = list_attempts(journal_settings)
    assert len(set(attempt_ids)) == len(attempts) == 12
    assert {attempt["learner_sql"] for attempt in attempts} == {str(n) for n in range(12)}
    assert all(attempt["mistake_type"] == "JOIN_TYPE" for attempt in attempts)
    # No connection remains open, preventing deletion or moving on Windows.
    database = journal_settings.data_dir / "journal.db"
    database.rename(database.with_suffix(".moved"))


def test_relative_direct_settings_uses_repo_root_not_cwd(journal_settings, monkeypatch):
    from bmq.journal import list_attempts, log_attempt

    monkeypatch.chdir(journal_settings.data_dir)
    relative = journal_settings.data_dir.relative_to(ROOT) / "nested"
    settings = replace(journal_settings, data_dir=relative)
    log_attempt("e1", "SELECT 1", Verdict(status="PASSED"), settings=settings)
    assert (ROOT / relative / "journal.db").is_file()
    assert len(list_attempts(settings)) == 1


@pytest.mark.parametrize("operation", ["log", "update", "list"])
def test_direct_settings_cannot_escape_repo(journal_settings, operation):
    from bmq.journal import list_attempts, log_attempt, update_explanation

    outside = ROOT.parent / f"journal-must-not-exist-{uuid4().hex}"
    settings = replace(journal_settings, data_dir=outside)
    with pytest.raises(ValueError, match="repository"):
        if operation == "log":
            log_attempt("e1", "SELECT 1", Verdict(status="PASSED"), settings=settings)
        elif operation == "update":
            update_explanation(1, explanation(), settings=settings)
        else:
            list_attempts(settings)
    assert not outside.exists()


@pytest.mark.parametrize("name", ["journal.db", "journal.db-journal", "journal.db-wal", "journal.db-shm"])
def test_existing_journal_link_cannot_escape_repo(journal_settings, name):
    from bmq.journal import log_attempt

    outside = ROOT.parent / f"journal-must-not-exist-{uuid4().hex}.db"
    link = journal_settings.data_dir / name
    junction = False
    try:
        os.symlink(outside, link)
    except OSError:
        if os.name != "nt":
            raise
        # Windows junctions exercise real resolved paths without symlink privilege.
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(ROOT.parent)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        junction = True
    try:
        with pytest.raises(ValueError, match="repository"):
            log_attempt("e1", "SELECT 1", Verdict(status="PASSED"), settings=journal_settings)
        assert not outside.exists()
    finally:
        if junction:
            os.rmdir(link)
        else:
            link.unlink()
