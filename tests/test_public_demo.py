"""Real app/session isolation with SQLite; external model calls are stubbed."""

import json
import shutil
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from bmq import hunter, llm, tutor
from bmq.config import ROOT


E1 = json.loads((ROOT / 'data/exercises.json').read_text(encoding='utf-8'))[0]


@pytest.fixture
def public_demo(monkeypatch):
    directory = ROOT / '.cache' / ('public-app-test-' + uuid4().hex)
    directory.mkdir(parents=True)
    monkeypatch.setenv('BMQ_PUBLIC_DEMO', 'true')
    monkeypatch.setenv('BMQ_MODEL_PROVIDER', 'gemini')
    monkeypatch.setenv('BMQ_MODEL', 'gemma-4-31b-it')
    monkeypatch.setenv('BMQ_MODEL_HINTS', 'false')
    monkeypatch.setenv('BMQ_DATA_DIR', str(directory))
    monkeypatch.setenv('BMQ_HUNT_ORDER', 'fuzz')
    monkeypatch.setenv('BMQ_FUZZ_MAX', '25')
    monkeypatch.setattr(llm, 'model_available', lambda *args, **kwargs: True)

    def unexpected_hint(*args, **kwargs):
        raise AssertionError('Public sessions must not invoke disk-writing explanation workers.')

    monkeypatch.setattr(tutor, 'submit_explanation', unexpected_hint)
    yield directory
    shutil.rmtree(directory)


def start():
    app = AppTest.from_file(ROOT / 'app.py', default_timeout=20).run()
    assert not app.exception
    return app


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception
    return app


def run_sql(app, sql):
    app.text_area(key='sql_editor').set_value(sql)
    return click(app, 'Run')


def visible(app):
    return '\n'.join(str(getattr(node, 'value', '')) for node in app)


def test_public_histories_are_isolated_and_never_open_disk_journal(public_demo):
    first = run_sql(start(), E1['known_wrong'][0]['sql'])
    first.radio(key='page').set_value('My traps').run()
    assert any(button.label == 'Retry' for button in first.button)
    second = start()
    assert not any('Counterexample' in caption for caption in second.radio(key='exercise_id').proto.captions)
    second.radio(key='page').set_value('My traps').run()
    assert not any(button.label == 'Retry' for button in second.button)
    assert E1['known_wrong'][0]['sql'] not in visible(second)
    assert not (public_demo / 'journal.db').exists()
    assert len(first.session_state.session_journal.list_attempts()) == 1
    assert second.session_state.session_journal.list_attempts() == []


def test_public_rerun_and_retry_preserve_one_session_attempt(public_demo):
    sql = E1['known_wrong'][0]['sql']
    app = run_sql(start(), sql)
    app.run()
    assert len(app.session_state.session_journal.list_attempts()) == 1
    app.radio(key='page').set_value('My traps').run()
    click(app, 'Retry')
    assert app.text_area(key='sql_editor').value == sql
    assert len(app.session_state.session_journal.list_attempts()) == 1
    assert not (public_demo / 'journal.db').exists()


def test_hosted_ui_discloses_processing_and_session_lifetime(public_demo):
    app = start()
    content = visible(app)
    assert 'Model configured' in content
    assert 'Model online' not in content
    assert 'Google' in content and 'server' in content.lower()
    assert 'session' in content.lower() and '50' in content
    assert 'refresh' in content.lower() or 'reconnect' in content.lower()
    assert 'everything runs locally' not in content
    assert 'Local practice' not in content
    assert app.text_area(key='sql_editor').proto.max_chars == 4000


def test_public_rejects_oversized_sql_before_hunting_or_logging(public_demo, monkeypatch):
    from streamlit.elements.widgets.text_widgets import TextAreaSerde

    # Exercise our server guard independently of Streamlit's own truncation.
    monkeypatch.setattr(TextAreaSerde, 'deserialize',
                        lambda self, value: self.value if value is None else value)

    def unexpected_run(*args, **kwargs):
        raise AssertionError('Over-limit public SQL must be rejected before executing or sending it.')

    monkeypatch.setattr(hunter, 'check', unexpected_run)
    app = run_sql(start(), 'SELECT 1 --' + 'x' * 4000)
    assert any('4,000' in warning.value for warning in app.warning)
    assert app.session_state.session_journal.list_attempts() == []
    assert not (public_demo / 'journal.db').exists()


def test_public_keeps_sqlite_verified_model_proposal_route(public_demo, monkeypatch):
    monkeypatch.setenv('BMQ_HUNT_ORDER', 'gemma,fuzz')
    monkeypatch.setattr(llm, 'propose_datasets', lambda *args, **kwargs: [
        llm.Candidate(idea='An unmatched customer.', inserts=[
            "INSERT INTO customers VALUES (1, 'Asha', NULL)",
        ]),
    ])
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    assert 'Found by gemma-4-31b-it' in visible(app)
    assert 'Expected result' in visible(app)
    rows = app.session_state.session_journal.list_attempts()
    assert len(rows) == 1 and rows[0]['found_by'] == 'gemma'
    assert rows[0]['counterexample']['customers'] == [[1, 'Asha', None]]
    assert rows[0]['mistake_type'] is None
    assert not (public_demo / 'journal.db').exists()


def test_fallback_notice_is_visible_with_verified_fuzz_evidence(public_demo, monkeypatch):
    check = hunter.check
    note = 'AI rate limit reached. This run used random stress tests.'

    def check_with_provider_notice(*args, **kwargs):
        result = check(*args, **kwargs)
        result.stats['model_note'] = note
        return result

    monkeypatch.setattr(hunter, 'check', check_with_provider_notice)
    app = run_sql(start(), E1['known_wrong'][0]['sql'])
    assert note in visible(app)
    assert 'Found by random stress test' in visible(app)
    assert 'Expected result' in visible(app)


def test_cloud_entrypoint_keeps_fuzz_fallback_despite_inherited_model_only_order(public_demo, monkeypatch):
    monkeypatch.setenv('BMQ_HUNT_ORDER', 'gemma')
    # Register every environment value the entrypoint changes for teardown.
    monkeypatch.setenv('BMQ_GEMMA_ROUNDS', '2')
    monkeypatch.setenv('BMQ_PUBLIC_DEMO', 'false')
    monkeypatch.setenv('BMQ_MODEL_PROVIDER', 'ollama')
    monkeypatch.setenv('BMQ_MODEL_HINTS', 'true')
    monkeypatch.setattr(llm, 'propose_datasets', lambda *args, **kwargs: [])
    app = AppTest.from_file(ROOT / 'cloud_app.py', default_timeout=20).run()
    assert not app.exception
    run_sql(app, E1['known_wrong'][0]['sql'])
    assert 'Found by random stress test' in visible(app)
    rows = app.session_state.session_journal.list_attempts()
    assert len(rows) == 1 and rows[0]['found_by'] == 'fuzz'
    assert not (public_demo / 'journal.db').exists()
    assert not any(button.label == 'Nudge me' for button in app.button)
