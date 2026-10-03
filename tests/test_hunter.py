"""Orchestration boundaries: only SQLite differences count as evidence."""

from dataclasses import replace
import json

import pytest

from bmq.config import ROOT, get_settings
from bmq.db import QueryError, validate_learner_sql


def exercise():
    return json.loads((ROOT / 'data/exercises.json').read_text(encoding='utf-8'))[0]


def test_sample_mismatch_returns_proof_without_contacting_model(monkeypatch):
    from bmq import hunter, llm

    def unexpected(*args, **kwargs):
        pytest.fail('Sample failure must not call the model')

    monkeypatch.setattr(llm, 'model_available', unexpected)
    events = []
    verdict = hunter.check(exercise(), 'SELECT name FROM customers', lambda stage, detail: events.append(stage))
    assert verdict.status == 'WRONG_ON_SAMPLE'
    assert verdict.found_by == 'sample'
    assert verdict.diff.column_count_mismatch
    assert verdict.dataset is not None
    assert events == ['sample', 'shrink']
    assert verdict.stats['gemma_rounds'] == 0


def test_fuzz_only_never_contacts_model_or_reads_answer_fixtures(monkeypatch):
    from bmq import hunter, llm

    class GuardedExercise(dict):
        def __getitem__(self, key):
            assert key not in ('trap_datasets', 'known_wrong', 'known_correct')
            return super().__getitem__(key)

        def get(self, key, default=None):
            assert key not in ('trap_datasets', 'known_wrong', 'known_correct')
            return super().get(key, default)

    def unexpected(*args, **kwargs):
        pytest.fail('Fuzz-only must not contact Ollama')

    monkeypatch.setattr(llm, 'model_available', unexpected)
    ex = exercise()
    verdict = hunter.check(GuardedExercise(ex), ex['known_wrong'][0]['sql'], settings=replace(get_settings(), hunt_order=('fuzz',)))
    assert verdict.status == 'HIDDEN_BUG'
    assert verdict.stats['gemma_available'] is None


def test_errored_generated_queries_do_not_count_as_stress_tests(monkeypatch):
    from bmq import hunter

    ex = exercise()
    run_query = hunter.run_query

    def fail_generated(conn, sql, timeout_s):
        if conn.execute('SELECT COUNT(*) FROM customers').fetchone()[0] != 3:
            raise QueryError('synthetic query timeout')
        return run_query(conn, sql, timeout_s)

    # A one-customer dataset cannot be the three-customer sample.
    monkeypatch.setattr(hunter, 'generate', lambda *args: {'customers': [[1, 'Asha', None]], 'products': [], 'orders': [], 'order_items': []})
    monkeypatch.setattr(hunter, 'run_query', fail_generated)
    verdict = hunter.check(ex, ex['known_correct'][0], settings=replace(get_settings(), hunt_order=('fuzz',), fuzz_max=3))
    assert verdict.status == 'PASSED'
    assert verdict.stats['fuzz_attempts'] == 3
    assert verdict.stats['fuzz_tries'] == 0
    assert verdict.stats['skipped_candidates'] == 3


def test_zero_time_budget_runs_no_random_queries():
    from bmq.hunter import check
    ex = exercise()
    verdict = check(ex, ex['known_correct'][0], settings=replace(get_settings(), hunt_order=('fuzz',), fuzz_seconds=0))
    assert verdict.status == 'PASSED'
    assert verdict.stats['fuzz_tries'] == 0
    assert verdict.stats['fuzz_attempts'] == 0


def test_configured_order_stops_before_gemma_when_fuzz_finds_bug(monkeypatch):
    from bmq import hunter, llm

    def unexpected(*args, **kwargs):
        pytest.fail('Already proven bugs need no further hunt')

    monkeypatch.setattr(llm, 'model_available', unexpected)
    ex = exercise()
    verdict = hunter.check(ex, ex['known_wrong'][0]['sql'], settings=replace(get_settings(), hunt_order=('fuzz', 'gemma')))
    assert verdict.status == 'HIDDEN_BUG'
    assert verdict.found_by == 'fuzz'


def test_gemma_rounds_carry_failed_ideas_and_count_verified_candidates(monkeypatch):
    from bmq import hunter, llm

    calls = []

    def propose(*args, **kwargs):
        calls.append((list(args[4]), args[5]))
        if len(calls) == 1:
            return [llm.Candidate(idea='An empty database', inserts=[])]
        return [llm.Candidate(idea='Customer without an order', inserts=["INSERT INTO customers VALUES (1, 'Kiran', NULL)"])]

    monkeypatch.setattr(llm, 'model_available', lambda settings=None: True)
    monkeypatch.setattr(llm, 'propose_datasets', propose)
    ex = exercise()
    events = []
    verdict = hunter.check(ex, ex['known_wrong'][0]['sql'], lambda stage, detail: events.append(stage), settings=replace(get_settings(), hunt_order=('gemma',)))
    assert verdict.status == 'HIDDEN_BUG'
    assert calls == [([], 0.7), (['An empty database'], 0.9)]
    assert verdict.stats['gemma_candidates'] == 2
    assert verdict.stats['gemma_rounds'] == 2
    assert events == ['sample', 'gemma', 'gemma', 'shrink']


def test_empty_gemma_rounds_fall_back(monkeypatch):
    from bmq import hunter, llm
    monkeypatch.setattr(llm, 'model_available', lambda settings=None: True)
    monkeypatch.setattr(llm, 'propose_datasets', lambda *args, **kwargs: [])
    ex = exercise()
    verdict = hunter.check(ex, ex['known_wrong'][0]['sql'])
    assert verdict.status == 'HIDDEN_BUG'
    assert verdict.found_by == 'fuzz'
    assert verdict.stats['gemma_candidates'] == 0
    assert verdict.stats['gemma_failed_rounds'] == 2


def test_at_most_three_candidates_per_gemma_round(monkeypatch):
    from bmq import hunter, llm
    monkeypatch.setattr(llm, 'model_available', lambda settings=None: True)
    monkeypatch.setattr(llm, 'propose_datasets', lambda *args, **kwargs: [llm.Candidate(idea='Empty tables', inserts=[])] * 10)
    ex = exercise()
    verdict = hunter.check(ex, ex['known_correct'][0], settings=replace(get_settings(), hunt_order=('gemma',), gemma_rounds=1))
    assert verdict.status == 'PASSED'
    assert verdict.stats['gemma_candidates'] == 3


def test_learner_error_on_gemma_candidate_is_skipped(monkeypatch):
    from bmq import hunter, llm
    ex = exercise()
    original = hunter.run_query

    def execute(conn, sql, timeout_s):
        if validate_learner_sql(sql) == validate_learner_sql(ex['known_correct'][0]) and conn.execute('SELECT COUNT(*) FROM customers').fetchone()[0] == 1:
            raise QueryError('candidate-only failure')
        return original(conn, sql, timeout_s)

    monkeypatch.setattr(hunter, 'run_query', execute)
    monkeypatch.setattr(llm, 'model_available', lambda settings=None: True)
    monkeypatch.setattr(llm, 'propose_datasets', lambda *args, **kwargs: [llm.Candidate(idea='Single customer', inserts=["INSERT INTO customers VALUES(1, 'Kiran', NULL)"])])
    verdict = hunter.check(ex, ex['known_correct'][0], settings=replace(get_settings(), hunt_order=('gemma',), gemma_rounds=1))
    assert verdict.status == 'PASSED'
    assert verdict.stats['gemma_candidates'] == 0
    assert verdict.stats['skipped_candidates'] == 1


def test_invalid_sample_is_an_error_without_exposing_reference():
    from bmq.hunter import check
    ex = exercise()
    ex['reference_sql'] = 'SELECT secret_reference_column FROM customers'
    verdict = check(ex, 'SELECT name FROM customers')
    assert verdict.status == 'ERROR'
    assert 'secret_reference_column' not in verdict.error


def test_order_sensitive_mismatch_is_not_discarded():
    from bmq.hunter import check
    ex = exercise()
    ex['reference_sql'] = 'SELECT name FROM customers ORDER BY name ASC'
    ex['order_matters'] = True
    verdict = check(ex, 'SELECT name FROM customers ORDER BY name DESC')
    assert verdict.status == 'WRONG_ON_SAMPLE'
    assert verdict.expected_result.rows != verdict.learner_result.rows
    assert not verdict.diff.missing and not verdict.diff.extra
