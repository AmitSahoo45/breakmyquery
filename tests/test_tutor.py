from dataclasses import replace
import importlib.util
import threading
import uuid
import shutil

from bmq import llm
from bmq.config import ROOT, Settings
from bmq.db import Result
from bmq.compare import Diff
from bmq.hunter import Verdict


def test_explanation_worker_returns_before_model_and_updates_existing_attempt(monkeypatch):
    assert importlib.util.find_spec('bmq.tutor'), 'The background explanation worker is missing.'
    from bmq import journal, tutor

    directory = ROOT / '.cache' / ('tutor-test-' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    settings = replace(Settings(), data_dir=directory)
    entered, release = threading.Event(), threading.Event()
    explanation = llm.Explanation(mistake_type='JOIN_TYPE', what_happened='A row is missing.', nudge='Why?', hint=None)
    calls = []

    def explain(*args, **kwargs):
        calls.append((args, threading.current_thread()))
        entered.set()
        assert release.wait(5)
        return explanation

    monkeypatch.setattr(llm, 'explain_mismatch', explain)
    verdict = Verdict('HIDDEN_BUG', dataset={'customers': [[1, 'A', None]], 'orders': [], 'products': [], 'order_items': []},
                      learner_result=Result(['name'], []), expected_result=Result(['name'], [('A',)]),
                      diff=Diff(False, [('A',)], []), found_by='fuzz')
    try:
        attempt_id = journal.log_attempt('e1', 'SELECT name FROM customers', verdict, settings=settings)
        future = tutor.submit_explanation('question', 'schema', 'learner query', verdict, attempt_id, settings=settings)
        assert future is not None and entered.wait(3)
        assert not future.done()
        release.set()
        assert future.result(timeout=5).explanation == explanation
        rows = journal.list_attempts(settings=settings)
        assert len(rows) == 1 and rows[0]['mistake_type'] == 'JOIN_TYPE'
        assert len(calls) == 1 and calls[0][1] is not threading.current_thread()
        assert calls[0][0][0:3] == ('question', 'schema', 'learner query')
    finally:
        release.set()
        shutil.rmtree(directory)
