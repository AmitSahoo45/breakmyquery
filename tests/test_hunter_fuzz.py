import json
from dataclasses import replace
from pathlib import Path

import pytest


def exercises():
    return json.loads((Path(__file__).resolve().parents[1] / 'data/exercises.json').read_text(encoding='utf-8'))


def test_all_hidden_bugs_and_alternatives():
    from bmq.config import get_settings
    from bmq.hunter import check
    settings = replace(get_settings(), hunt_order=('fuzz',), fuzz_seconds=20)
    for exercise in exercises():
        # Deliberately provide no trap datasets or known answers to the hunter.
        public = {k: v for k, v in exercise.items() if k not in ('trap_datasets', 'known_wrong', 'known_correct')}
        for wrong in exercise['known_wrong']:
            verdict = check(public, wrong['sql'], settings=settings, seed=42)
            assert verdict.status == 'HIDDEN_BUG', (exercise['id'], wrong['trap'], verdict)
            assert sum(map(len, verdict.dataset.values())) <= 6, (exercise['id'], verdict.dataset)
            assert verdict.found_by == 'fuzz'
        for correct in exercise['known_correct']:
            verdict = check(public, correct, settings=settings, seed=42)
            assert verdict.status == 'PASSED', (exercise['id'], verdict)
            assert verdict.stats['fuzz_tries'] == settings.fuzz_max


def test_error_and_wrong_sample_are_distinct():
    from bmq.config import get_settings
    from bmq.hunter import check
    settings = replace(get_settings(), hunt_order=('fuzz',))
    exercise = exercises()[0]
    assert check(exercise, 'DELETE FROM customers', settings=settings).status == 'ERROR'
    assert check(exercise, 'SELECT missing FROM customers', settings=settings).status == 'ERROR'
    assert check(exercise, 'SELECT name FROM customers', settings=settings).status == 'WRONG_ON_SAMPLE'


def test_unavailable_gemma_falls_back_to_fuzz(monkeypatch):
    from bmq import llm
    from bmq.hunter import check
    monkeypatch.setattr(llm, 'model_available', lambda settings=None: False)
    exercise = exercises()[0]
    verdict = check(exercise, exercise['known_wrong'][0]['sql'])
    assert verdict.status == 'HIDDEN_BUG'
    assert verdict.found_by == 'fuzz'
    assert verdict.stats['gemma_available'] is False


def test_verified_gemma_candidate_is_shrunk(monkeypatch):
    from bmq import llm
    from bmq.hunter import check
    from bmq.config import get_settings
    monkeypatch.setattr(llm, 'model_available', lambda settings=None: True)
    monkeypatch.setattr(llm, 'propose_datasets', lambda *a, **kw: [llm.Candidate(idea='A customer without orders', inserts=["INSERT INTO customers VALUES (1, 'Kiran', NULL)"])])
    exercise = exercises()[0]
    verdict = check(exercise, exercise['known_wrong'][0]['sql'], settings=replace(get_settings(), hunt_order=('gemma',)))
    assert verdict.status == 'HIDDEN_BUG'
    assert verdict.found_by == 'gemma'
    assert verdict.expected_result.rows == [('Kiran', 0)]
    assert verdict.learner_result.rows == []


@pytest.mark.ollama
def test_live_model_e1():
    from bmq.hunter import check
    from bmq.config import get_settings
    exercise = exercises()[0]
    verdict = check(exercise, exercise['known_wrong'][0]['sql'], settings=replace(get_settings(), hunt_order=('gemma',)))
    assert verdict.status == 'HIDDEN_BUG'
    assert verdict.found_by == 'gemma'
