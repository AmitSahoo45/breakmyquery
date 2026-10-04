"""Offline contracts for paced, sanitized hosted-model evaluation."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

from bmq.config import Settings
from bmq.hunter import Verdict


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def report_dir():
    # Match the repository's Windows-safe alternative to pytest chmod(0700).
    directory = ROOT / '.cache' / f'hosted-eval-tests-{uuid4().hex}'
    directory.mkdir(parents=True)
    yield directory
    for child in directory.rglob('*.json'):
        child.unlink()
    if (directory / '.cache').exists():
        (directory / '.cache').rmdir()
    directory.rmdir()


@pytest.fixture
def evaluator():
    script = ROOT / 'scripts' / 'eval_hosted.py'
    assert script.exists(), 'The hosted evaluator has not been implemented.'
    spec = importlib.util.spec_from_file_location('eval_hosted_under_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def settings():
    return Settings(model_provider='gemini', model='gemma-4-26b-a4b-it',
                    gemini_api_key='SECRET_SENTINEL', gemma_rounds=2)


@pytest.fixture
def catalog():
    return [{'id': 'e1', 'title': 'Example', 'question': 'Practice counts',
             'expected_columns': ['n'], 'order_matters': False,
             'reference_sql': 'SELECT 1 AS n', 'sample_data': {},
             'known_wrong': [{'sql': 'SELECT 2 AS n', 'trap': 'OTHER'}],
             'known_correct': ['SELECT 1 AS n'], 'trap_datasets': [{'private': True}],
             'private_author_notes': 'PRIVATE_SENTINEL'}]


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def verdict(status='PASSED', *, model=1, fuzz=0, source=None):
    return Verdict(status=status, found_by=source, error='SECRET_SENTINEL SELECT 9',
                   gemma_idea='PRIVATE_SENTINEL', dataset={'private': ['SELECT 8']},
                   stats={'gemma_candidates': model, 'fuzz_tries': fuzz,
                          'gemma_rounds': 1, 'gemma_failed_rounds': 0,
                          'skipped_candidates': 0, 'seconds': 2.5,
                          'model_note': 'SECRET_SENTINEL'})


def test_separate_hunts_are_paced_and_receive_only_problem_fields(evaluator, settings, catalog):
    timer = FakeTime()
    starts = []

    def check(problem, sql, *, settings, seed):
        assert set(problem) == {'id', 'title', 'question', 'expected_columns',
                                'order_matters', 'reference_sql', 'sample_data'}
        assert seed == 42
        assert settings.gemma_rounds == 1
        assert settings.model_hints is False
        if settings.hunt_order == ('gemma',):
            starts.append(timer.now)
            timer.now += 2
            return verdict('HIDDEN_BUG' if sql == 'SELECT 2 AS n' else 'PASSED', source='gemma')
        assert settings.hunt_order == ('fuzz',)
        timer.now += 3
        return verdict('HIDDEN_BUG' if sql == 'SELECT 2 AS n' else 'PASSED',
                       model=0, fuzz=4, source='fuzz')

    report = evaluator.evaluate(settings, exercises=catalog, check_fn=check,
                                clock=timer.clock, sleep=timer.sleep)
    assert starts == [0.0, 35.0]
    assert timer.waits == [30.0]
    assert report['summary']['model']['wrong_found'] == 1
    assert report['summary']['model']['equivalent_measured'] == 1
    assert report['summary']['fuzz']['wrong_found'] == 1
    serialized = json.dumps(report)
    for forbidden in ('SECRET_SENTINEL', 'PRIVATE_SENTINEL', 'SELECT', 'trap_datasets'):
        assert forbidden not in serialized


def test_slow_hunts_need_no_extra_wait(evaluator, settings, catalog):
    timer = FakeTime()

    def check(*args, **kwargs):
        timer.now += 30
        return verdict(model=1, fuzz=1)

    evaluator.evaluate(settings, exercises=catalog, check_fn=check,
                       clock=timer.clock, sleep=timer.sleep)
    assert timer.waits == []


def test_default_catalog_evaluates_all_14_wrong_and_eight_equivalent_queries(evaluator, settings):
    timer = FakeTime()
    calls = []

    def check(problem, sql, *, settings, seed):
        calls.append((problem['id'], settings.hunt_order))
        return verdict(model=1, fuzz=1)

    report = evaluator.evaluate(settings, check_fn=check, clock=timer.clock, sleep=timer.sleep)
    assert report['catalog_total'] == report['selected_total'] == 22
    assert report['partial_catalog'] is False
    assert report['summary']['model']['wrong_total'] == 14
    assert report['summary']['model']['equivalent_total'] == 8
    assert len(calls) == 44
    assert timer.now == 735.0


def test_zero_candidates_are_unmeasured_without_retry(evaluator, settings, catalog):
    timer = FakeTime()
    calls = []

    def check(*args, settings, **kwargs):
        calls.append(settings.hunt_order)
        return verdict(model=0, fuzz=0)

    report = evaluator.evaluate(settings, exercises=catalog, limit=1, check_fn=check,
                                clock=timer.clock, sleep=timer.sleep)
    assert calls == [('gemma',), ('fuzz',)]
    assert report['partial_catalog'] is True
    assert report['cases'][0]['model']['measured'] is False
    assert report['summary']['model']['wrong_measured'] == 0
    assert report['summary']['model']['unmeasured'] == 1
    assert evaluator.exit_code(report) == 2


def test_fuzz_result_cannot_count_as_a_model_found_case(evaluator, settings, catalog):
    report = evaluator.evaluate(settings, exercises=catalog, limit=1,
                                check_fn=lambda *a, **k: verdict('HIDDEN_BUG', model=2,
                                                               fuzz=3, source='fuzz'))
    assert report['cases'][0]['model']['found'] is False
    assert report['summary']['model']['wrong_found'] == 0
    assert evaluator.exit_code(report) == 1


def test_equivalent_sample_mismatch_is_a_false_positive_even_without_stress_candidates(evaluator, settings, catalog):
    catalog[0]['known_wrong'] = []
    report = evaluator.evaluate(settings, exercises=catalog,
                                check_fn=lambda *a, **k: verdict('WRONG_ON_SAMPLE', model=0,
                                                               fuzz=0, source='sample'))
    assert report['summary']['model']['false_positives'] == 1
    assert report['summary']['fuzz']['false_positives'] == 1
    assert evaluator.exit_code(report) == 1


def test_unexpected_error_is_sanitized_and_not_retried(evaluator, settings, catalog):
    calls = []

    def check(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('SECRET_SENTINEL SELECT private_data')

    report = evaluator.evaluate(settings, exercises=catalog, limit=1, check_fn=check)
    assert len(calls) == 2
    assert report['summary']['model']['errors'] == 1
    assert 'SECRET_SENTINEL' not in json.dumps(report)
    assert 'SELECT' not in json.dumps(report)
    assert evaluator.exit_code(report) == 1


@pytest.mark.parametrize('change', [{'model_provider': 'ollama'}, {'gemini_api_key': ''}])
def test_no_live_calls_for_missing_hosted_configuration(evaluator, settings, catalog, change):
    with pytest.raises(ValueError):
        evaluator.evaluate(replace(settings, **change), exercises=catalog,
                           check_fn=lambda *a, **k: pytest.fail('Unexpected model call'))


def test_cli_rejects_output_outside_repository_before_evaluation(evaluator, monkeypatch):
    monkeypatch.setattr(evaluator, 'evaluate', lambda **k: pytest.fail('Must validate path first'))
    with pytest.raises(SystemExit) as error:
        evaluator.main(['--output', '../outside-hosted-report.json'])
    assert error.value.code == 2


def test_cli_writes_sanitized_json_and_summary(evaluator, monkeypatch, report_dir, capsys, settings, catalog):
    monkeypatch.setattr(evaluator, 'ROOT', report_dir)
    report = evaluator.evaluate(settings, exercises=catalog, limit=1,
                                check_fn=lambda *a, **k: verdict(model=1, fuzz=1))

    def evaluate(**kwargs):
        kwargs['on_case'](report['cases'][0])
        return report

    monkeypatch.setattr(evaluator, 'evaluate', evaluate)
    assert evaluator.main(['--limit', '1', '--output', '.cache/hosted.json']) == 0
    saved = json.loads((report_dir / '.cache/hosted.json').read_text(encoding='utf-8'))
    assert saved == report
    output = capsys.readouterr().out
    assert 'SECRET_SENTINEL' not in output
    assert 'SELECT' not in output
    assert 'summary' in output


@pytest.mark.parametrize('limit', ['0', '-1'])
def test_cli_rejects_nonpositive_limit(evaluator, limit):
    with pytest.raises(SystemExit) as error:
        evaluator.main(['--limit', limit])
    assert error.value.code == 2
