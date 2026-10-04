"""Bounded background explanations, independent of Streamlit session lifetime."""

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import sqlite3
from threading import BoundedSemaphore

from bmq import journal, llm
from bmq.config import Settings
from bmq.hunter import Verdict


@dataclass(frozen=True)
class ExplanationResult:
    explanation: llm.Explanation | None
    journal_saved: bool = True


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='bmq-explanation')
_slots = BoundedSemaphore(4)


def submit_explanation(
    question: str, schema: str, learner_sql: str, verdict: Verdict,
    attempt_id: int | None, *, settings: Settings,
) -> Future | None:
    """Queue once per attempt; cap running + queued work across sessions.

    The worker never receives reference SQL or calls a Streamlit API. It saves
    classification itself, so navigating away doesn't lose the journal update.
    """
    if not _slots.acquire(blocking=False):
        return None

    def explain_and_save():
        explanation = llm.explain_mismatch(
            question, schema, learner_sql, verdict.dataset,
            verdict.learner_result, verdict.expected_result, verdict.diff,
            settings=settings,
        )
        saved = attempt_id is not None
        if explanation is not None and attempt_id is not None:
            try:
                journal.update_explanation(attempt_id, explanation, settings=settings)
            except (OSError, sqlite3.Error, ValueError):
                saved = False
        return ExplanationResult(explanation, saved)

    try:
        future = _executor.submit(explain_and_save)
    except RuntimeError:
        _slots.release()
        return None
    future.add_done_callback(lambda _: _slots.release())
    return future

