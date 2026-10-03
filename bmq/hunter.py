"""Find and shrink counterexamples; only successful SQLite runs decide verdicts."""

from collections.abc import Callable
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass, field
import json
import random
import time
from typing import Literal

from bmq import llm
from bmq.compare import Diff, diff, equal
from bmq.config import ROOT, Settings, get_settings
from bmq.db import LoadError, QueryError, Result, build_db, run_query, validate_learner_sql
from bmq.fuzz import generate
from bmq.shrink import shrink


@dataclass
class Verdict:
    status: Literal['ERROR', 'WRONG_ON_SAMPLE', 'HIDDEN_BUG', 'PASSED']
    error: str | None = None
    dataset: dict | None = None
    learner_result: Result | None = None
    expected_result: Result | None = None
    diff: Diff | None = None
    found_by: Literal['sample', 'gemma', 'fuzz'] | None = None
    gemma_idea: str | None = None
    stats: dict = field(default_factory=dict)


class _ReferenceError(QueryError):
    """Keep reference-query internals out of learner-facing errors."""


def _run_pair(dataset, reference_sql, learner_sql, timeout_s, deadline=None):
    def remaining():
        budget = timeout_s if deadline is None else min(timeout_s, deadline - time.monotonic())
        if budget <= 0:
            raise QueryError('Stress-test time budget exhausted.')
        return budget

    with closing(build_db(dataset)) as conn:
        try:
            expected = run_query(conn, reference_sql, remaining())
        except QueryError as exc:
            raise _ReferenceError('The exercise could not be evaluated. Check the exercise data and configuration.') from exc
        actual = run_query(conn, learner_sql, remaining())
    return expected, actual


def check(
    exercise: dict,
    learner_sql: str,
    progress_cb: Callable[[str, str], None] | None = None,
    *,
    settings: Settings | None = None,
    seed: int = 42,
) -> Verdict:
    """Run the sample, hunt in the configured order, and return verified evidence.

    Counts called ``gemma_candidates`` and ``fuzz_tries`` include only datasets
    where both queries finished successfully. Attempts and skips are separate.
    ``PASSED`` means no counterexample was found within this search budget.
    Authored traps and known-answer fixtures are never accessed here.
    """
    settings = settings or get_settings()
    started = time.monotonic()
    stats = {
        'gemma_rounds': 0,
        'gemma_candidates': 0,
        'fuzz_tries': 0,
        'fuzz_attempts': 0,
        'skipped_candidates': 0,
        'gemma_failed_rounds': 0,
        'gemma_available': None,
        'seconds': 0.0,
    }

    def progress(stage, detail):
        if progress_cb is not None:
            progress_cb(stage, detail)

    def finish(status, **kwargs):
        stats['seconds'] = round(time.monotonic() - started, 6)
        return Verdict(status=status, stats=dict(stats), **kwargs)

    progress('sample', 'Running on sample…')
    try:
        learner_sql = validate_learner_sql(learner_sql)
    except QueryError as exc:
        return finish('ERROR', error=str(exc))

    # Only these problem fields are needed. Never copy the complete exercise
    # into a model prompt or use its validator-only answer/trap collections.
    reference_sql = exercise['reference_sql']
    order_matters = exercise.get('order_matters', False)
    sample = exercise['sample_data']

    def try_pair(dataset, deadline=None):
        try:
            return _run_pair(dataset, reference_sql, learner_sql, settings.query_timeout, deadline)
        except (QueryError, LoadError):
            return None

    def mismatch(pair):
        return pair is not None and not equal(pair[0], pair[1], order_matters)

    def counterexample(dataset, pair, found_by, idea=None):
        progress('shrink', 'Shrinking the breaking dataset…')
        small = shrink(dataset, lambda candidate: mismatch(try_pair(candidate)))
        final_pair = try_pair(small)
        if not mismatch(final_pair):
            # Timeouts or nondeterministic learner SQL cannot turn an
            # unverified final rerun into a new mismatch. Retain found evidence.
            small, final_pair = deepcopy(dataset), pair
        expected, actual = final_pair
        return finish(
            'WRONG_ON_SAMPLE' if found_by == 'sample' else 'HIDDEN_BUG',
            dataset=small,
            learner_result=actual,
            expected_result=expected,
            diff=diff(expected, actual),
            found_by=found_by,
            gemma_idea=llm.safe_text(idea) if idea else None,
        )

    try:
        sample_pair = _run_pair(sample, reference_sql, learner_sql, settings.query_timeout)
    except LoadError:
        return finish('ERROR', error='The exercise sample could not be loaded. Check the exercise data.')
    except QueryError as exc:
        return finish('ERROR', error=str(exc))
    if mismatch(sample_pair):
        return counterexample(sample, sample_pair, 'sample')

    for stage in settings.hunt_order:
        if stage == 'gemma':
            if settings.gemma_rounds == 0:
                continue
            stats['gemma_available'] = llm.model_available(settings)
            if not stats['gemma_available']:
                continue
            schema_sql = (ROOT / 'data/schema.sql').read_text(encoding='utf-8')
            tried_ideas = []
            for round_index in range(settings.gemma_rounds):
                stats['gemma_rounds'] += 1
                progress('gemma', f'Gemma is hunting for a breaking case (round {round_index + 1}/{settings.gemma_rounds})…')
                proposals = llm.propose_datasets(
                    schema_sql,
                    exercise['question'],
                    learner_sql,
                    reference_sql,
                    tried_ideas,
                    0.7 if round_index == 0 else 0.9,
                    settings=settings,
                )
                if not proposals:
                    stats['gemma_failed_rounds'] += 1
                for candidate in proposals[:3]:
                    dataset = llm.candidate_dataset(candidate, settings=settings)
                    pair = try_pair(dataset) if dataset is not None else None
                    if pair is None:
                        stats['skipped_candidates'] += 1
                    else:
                        stats['gemma_candidates'] += 1
                        if mismatch(pair):
                            return counterexample(dataset, pair, 'gemma', candidate.idea)
                    tried_ideas.append(llm.safe_text(candidate.idea))
        elif stage == 'fuzz':
            progress('fuzz', 'Stress-testing with random data…')
            pools = json.loads((ROOT / 'data/fuzz_pools.json').read_text(encoding='utf-8'))
            rng = random.Random(seed)
            deadline = time.monotonic() + settings.fuzz_seconds
            for _ in range(settings.fuzz_max):
                if time.monotonic() >= deadline:
                    break
                dataset = generate(rng, pools)
                stats['fuzz_attempts'] += 1
                pair = try_pair(dataset, deadline)
                if pair is None:
                    stats['skipped_candidates'] += 1
                    continue
                stats['fuzz_tries'] += 1
                if mismatch(pair):
                    return counterexample(dataset, pair, 'fuzz')

    return finish('PASSED')
