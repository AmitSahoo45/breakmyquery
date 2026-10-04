"""Exercise the rendered application with real SQLite and journal storage."""

from concurrent.futures import Future
import json
import shutil
import uuid

import pytest
from streamlit.testing.v1 import AppTest

from bmq import llm
from bmq.config import ROOT


EXERCISES = json.loads((ROOT / 'data/exercises.json').read_text(encoding='utf-8'))
E1 = EXERCISES[0]


@pytest.fixture
def app_env(monkeypatch):
    path = ROOT / '.cache' / ('app-test-' + uuid.uuid4().hex)
    path.mkdir(parents=True)
    monkeypatch.setenv('BMQ_PUBLIC_DEMO', 'false')
    monkeypatch.setenv('BMQ_MODEL_PROVIDER', 'ollama')
    monkeypatch.setenv('BMQ_DATA_DIR', str(path))
    monkeypatch.setenv('BMQ_HUNT_ORDER', 'fuzz')
    monkeypatch.setenv('BMQ_MODEL_HINTS', 'true')
    monkeypatch.setenv('BMQ_FUZZ_MAX', '25')
    monkeypatch.setattr(llm, 'model_available', lambda *a, **kw: False)
    yield path
    shutil.rmtree(path)


def start():
    assert (ROOT / 'app.py').is_file(), 'The practice app has not been implemented.'
    app = AppTest.from_file(ROOT / 'app.py', default_timeout=20).run()
    assert not app.exception
    return app


def click(app, label):
    next(b for b in app.button if b.label == label).click().run()
    assert not app.exception
    return app


def run_sql(app, sql):
    app.text_area(key='sql_editor').set_value(sql)
    return click(app, 'Run')


def visible(app):
    return '\n'.join(str(getattr(node, 'value', '')) for node in app)


@pytest.mark.parametrize('online', [True, False])
def test_sidebar_identifies_the_configured_model(app_env, monkeypatch, online):
    monkeypatch.setenv('BMQ_MODEL', 'llama3.2:latest')
    monkeypatch.setattr(llm, 'model_available', lambda *a, **kw: online)
    text = visible(start())
    assert 'llama3.2:latest' in text
    assert ('Model online' if online else 'Model offline') in text
    assert 'Gemma' not in text


def test_offline_proof_journals_once_and_retry_restores_query(app_env):
    from bmq import journal

    app = start()
    assert 'Model offline: fuzz only' in visible(app)
    assert E1['reference_sql'] not in visible(app)
    sql = E1['known_wrong'][0]['sql']
    run_sql(app, sql)
    assert 'but it breaks here' in visible(app)
    assert 'Expected result' in visible(app)
    assert any('Missing' in str(frame.value) for frame in app.dataframe)
    assert len(journal.list_attempts()) == 1
    app.run()
    assert len(journal.list_attempts()) == 1
    app.radio(key='page').set_value('My traps').run()
    assert 'Unclassified' in visible(app)
    click(app, 'Retry')
    assert app.radio(key='page').value == 'Practice'
    assert app.text_area(key='sql_editor').value == sql
    assert len(journal.list_attempts()) == 1


@pytest.mark.parametrize('sql,banner', [
    ('DELETE FROM customers', 'Your query could not run.'),
    ('SELECT name FROM customers', 'Wrong on the sample data.'),
    ('SELECT 1, 1 FROM customers', 'Wrong on the sample data.'),
])
def test_errors_and_sample_mismatches_remain_usable(app_env, sql, banner):
    from bmq import journal

    app = run_sql(start(), sql)
    assert banner in visible(app)
    assert len(journal.list_attempts()) == 1
    assert E1['reference_sql'] not in visible(app)


def test_pass_wording_and_exercise_drafts(app_env):
    app = run_sql(start(), E1['known_correct'][0])
    assert 'Passed sample + 25 stress tests. No breaking case found.' in visible(app)
    assert not any('Correct' in str(x.value) for x in app.success)
    app.radio(key='exercise_id').set_value(EXERCISES[1]['id']).run()
    assert app.text_area(key='sql_editor').value == ''
    app.text_area(key='sql_editor').set_value('SELECT city FROM customers').run()
    app.radio(key='exercise_id').set_value(E1['id']).run()
    assert app.text_area(key='sql_editor').value == E1['known_correct'][0]


def test_result_survives_sidebar_status_label_update(app_env):
    app = start()
    options_before_run = app.radio(key='exercise_id').options.copy()
    run_sql(app, E1['known_wrong'][0]['sql'])
    assert 'but it breaks here' in visible(app)
    # Radio values serialize as formatted labels; status must not alter them.
    assert app.radio(key='exercise_id').options == options_before_run
    app.radio(key='exercise_id').set_value(E1['id']).run()
    assert 'but it breaks here' in visible(app)
    assert app.session_state.attempt is not None


def test_unsent_draft_survives_page_navigation(app_env):
    app = start()
    app.text_area(key='sql_editor').set_value('SELECT name FROM customers').run()
    app.radio(key='page').set_value('My traps').run()
    app.radio(key='page').set_value('Practice').run()
    assert app.text_area(key='sql_editor').value == 'SELECT name FROM customers'


def test_draft_survives_exercise_switching_while_editor_is_hidden(app_env):
    app = start()
    app.text_area(key='sql_editor').set_value('SELECT name FROM customers').run()
    app.radio(key='page').set_value('My traps').run()
    app.radio(key='exercise_id').set_value(EXERCISES[1]['id']).run()
    app.radio(key='exercise_id').set_value(E1['id']).run()
    app.radio(key='page').set_value('Practice').run()
    assert app.text_area(key='sql_editor').value == 'SELECT name FROM customers'


def test_retry_preserves_a_different_exercises_unsent_draft(app_env):
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    app.radio(key='exercise_id').set_value(EXERCISES[1]['id']).run()
    app.text_area(key='sql_editor').set_value('SELECT city FROM customers').run()
    app.radio(key='page').set_value('My traps').run()
    click(app, 'Retry')
    app.radio(key='exercise_id').set_value(EXERCISES[1]['id']).run()
    assert app.text_area(key='sql_editor').value == 'SELECT city FROM customers'


def test_offline_app_uses_fuzz_even_when_model_only_order_is_configured(app_env, monkeypatch):
    monkeypatch.setenv('BMQ_HUNT_ORDER', 'gemma')
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    assert 'but it breaks here' in visible(app)
    assert 'Found by random stress test' in visible(app)


def test_error_explanation_is_only_requested_once_on_demand(app_env, monkeypatch):
    monkeypatch.setattr(llm, 'model_available', lambda *a, **kw: True)
    calls = []

    def explain(*args, **kwargs):
        calls.append(args)
        return llm.ErrorExplanation(meaning='The table was not found.', where_to_look='Check the table name.')

    monkeypatch.setattr(llm, 'explain_error', explain)
    app = run_sql(start(), 'SELECT * FROM missing_table')
    assert not calls
    click(app, 'Explain this error')
    assert 'The table was not found.' in visible(app)
    click(app, 'Explain this error')
    assert len(calls) == 1


def test_background_hint_is_hidden_until_requested_and_never_repeated(app_env, monkeypatch):
    from bmq import tutor

    monkeypatch.setattr(llm, 'model_available', lambda *a, **kw: True)
    future = Future()
    submissions = []

    def submit(*args, **kwargs):
        submissions.append((args, kwargs))
        return future

    monkeypatch.setattr(tutor, 'submit_explanation', submit)
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    assert len(submissions) == 1
    assert 'Preparing' in visible(app)
    future.set_result(tutor.ExplanationResult(llm.Explanation(
        mistake_type='JOIN_TYPE', what_happened='A customer disappeared.',
        nudge='Which rows survive?', hint='Think about preserving unmatched rows.',
    )))
    app.run()
    assert 'A customer disappeared.' not in visible(app)
    click(app, 'Nudge me')
    assert 'A customer disappeared.' in visible(app)
    assert 'Think about preserving unmatched rows.' not in visible(app)
    click(app, 'Bigger hint')
    assert 'Think about preserving unmatched rows.' in visible(app)
    app.run()
    assert len(submissions) == 1


def test_untrusted_model_text_is_plain_and_sql_guarded(app_env, monkeypatch):
    from bmq import tutor

    monkeypatch.setattr(llm, 'model_available', lambda *a, **kw: True)
    future = Future()
    future.set_result(tutor.ExplanationResult(llm.Explanation(
        mistake_type='JOIN_TYPE', what_happened='![remote](https://example.com/pixel)',
        nudge='SELECT secret FROM solution', hint='VALUES (42)',
    )))
    monkeypatch.setattr(tutor, 'submit_explanation', lambda *a, **kw: future)
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    click(app, 'Nudge me')
    assert any('![remote]' in x.value for x in app.text)
    assert not any('![remote]' in x.value for x in app.markdown)
    assert 'SELECT secret' not in visible(app)
    click(app, 'Bigger hint')
    assert 'VALUES (42)' not in visible(app)


def test_evidence_only_keeps_verified_model_hunting_without_hints_or_classification(app_env, monkeypatch):
    from bmq import journal, tutor

    monkeypatch.setenv('BMQ_MODEL_HINTS', 'false')
    monkeypatch.setenv('BMQ_HUNT_ORDER', 'gemma,fuzz')
    monkeypatch.setattr(llm, 'model_available', lambda *a, **kw: True)
    proposals = []
    hint_calls = []

    def propose(*args, **kwargs):
        proposals.append(args)
        return [llm.Candidate(idea='Model idea stays hidden.', inserts=[
            "INSERT INTO customers VALUES (1, 'Asha', NULL)",
        ])]

    def unexpected_hint(*args, **kwargs):
        hint_calls.append(args)

    monkeypatch.setattr(llm, 'propose_datasets', propose)
    monkeypatch.setattr(tutor, 'submit_explanation', unexpected_hint)
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    assert proposals
    assert not hint_calls, 'Evidence-only mode must not request model explanations.'
    assert 'but it breaks here' in visible(app)
    assert 'Model hints are off' in visible(app)
    assert 'Reveal a nudge' not in visible(app)
    assert 'Model idea stays hidden.' not in visible(app)
    assert not any(button.label == 'Nudge me' for button in app.button)
    rows = journal.list_attempts()
    assert len(rows) == 1 and rows[0]['found_by'] == 'gemma'
    assert rows[0]['mistake_type'] is None and rows[0]['what_happened'] is None
    app.run()
    app.radio(key='page').set_value('My traps').run()
    assert 'Evidence only' in visible(app)
    click(app, 'Retry')
    assert app.text_area(key='sql_editor').value == E1['known_wrong'][0]['sql']
    assert len(journal.list_attempts()) == 1


def test_evidence_only_hides_error_explanations_and_saved_model_text(app_env, monkeypatch):
    from bmq import journal

    # Preserve historical classifications in storage while hiding generated text.
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    journal.update_explanation(journal.list_attempts()[0]['id'], llm.Explanation(
        mistake_type='GROUP_BY_GRAIN', what_happened='An unreliable historical explanation.',
        nudge='A historical question?', hint=None,
    ))
    app.radio(key='exercise_id').set_value(EXERCISES[1]['id']).run()
    run_sql(app, EXERCISES[1]['known_wrong'][0]['sql'])
    journal.update_explanation(journal.list_attempts()[0]['id'], llm.Explanation(
        mistake_type='NULL_COMPARISON', what_happened='A second historical explanation.',
        nudge='Another question?', hint=None,
    ))
    monkeypatch.setenv('BMQ_MODEL_HINTS', 'false')
    monkeypatch.setattr(llm, 'model_available', lambda *a, **kw: True)
    app = start()
    app.radio(key='page').set_value('My traps').run()
    assert 'An unreliable historical explanation.' not in visible(app)
    assert 'GROUP_BY_GRAIN' not in visible(app)
    assert 'A second historical explanation.' not in visible(app)
    assert len([button for button in app.button if button.label == 'Retry']) == 2
    saved = journal.list_attempts()
    assert {row['mistake_type'] for row in saved} == {'GROUP_BY_GRAIN', 'NULL_COMPARISON'}
    first_exercise_attempt = next(row for row in saved if row['exercise_id'] == E1['id'])
    app.button(key=f'retry_{first_exercise_attempt["id"]}').click().run()
    assert app.text_area(key='sql_editor').value == E1['known_wrong'][0]['sql']
    assert len(journal.list_attempts()) == 2
    app.radio(key='page').set_value('Practice').run()
    run_sql(app, 'SELECT * FROM missing_table')
    assert 'Your query could not run.' in visible(app)
    assert not any(button.label == 'Explain this error' for button in app.button)

