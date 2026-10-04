"""Opt-in model quality checks using the actual SQLite counterexample evidence."""
from dataclasses import replace
import json

import pytest

from bmq import hunter, llm
from bmq.config import ROOT, get_settings


@pytest.mark.ollama
@pytest.mark.parametrize('variant,expected_category', [(0, 'JOIN_TYPE'), (1, 'ON_VS_WHERE')])
def test_live_e1_explanation_matches_the_verified_missing_customer(variant, expected_category):
    exercise = json.loads((ROOT / 'data/exercises.json').read_text(encoding='utf-8'))[0]
    schema = (ROOT / 'data/schema.sql').read_text(encoding='utf-8')
    settings = get_settings()
    sql = exercise['known_wrong'][variant]['sql']
    verdict = hunter.check(exercise, sql, settings=replace(settings, hunt_order=('fuzz',)), seed=42)
    assert verdict.status == 'HIDDEN_BUG'
    explanation = llm.explain_mismatch(
        exercise['question'], schema, sql, verdict.dataset, verdict.learner_result,
        verdict.expected_result, verdict.diff, settings=settings,
    )
    assert explanation is not None
    assert explanation.mistake_type == expected_category, explanation
    prose = ' '.join(filter(None, [explanation.what_happened, explanation.nudge, explanation.hint]))
    assert any(str(row[1]) in prose for row in verdict.dataset['customers']), explanation
    assert not llm._contains_sql(prose)
