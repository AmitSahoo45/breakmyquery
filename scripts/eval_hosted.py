"""Evaluate hosted Gemma and seeded fuzzing independently, without logging SQL."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmq.config import GEMINI_MODELS, get_settings


START_INTERVAL_SECONDS = 35.0
PROBLEM_FIELDS = ('id', 'title', 'question', 'expected_columns', 'order_matters',
                  'reference_sql', 'sample_data')
STATUSES = ('ERROR', 'WRONG_ON_SAMPLE', 'HIDDEN_BUG', 'PASSED')


def _run(check_fn, exercise, sql, settings, mode):
    """Allowlist report fields; neither provider text nor exceptions are copied."""
    try:
        verdict = check_fn(exercise, sql, settings=replace(settings, hunt_order=(mode,)), seed=42)
        stats = verdict.stats
        status = verdict.status if verdict.status in STATUSES else 'ERROR'
        verified = int(stats.get('gemma_candidates' if mode == 'gemma' else 'fuzz_tries', 0))
        found = status == 'HIDDEN_BUG' and verdict.found_by == mode and verified > 0
        source_error = status == 'HIDDEN_BUG' and not found
        return {
            'status': status, 'found': found, 'measured': verified > 0,
            'verified_candidates': verified,
            'unmeasured_reason': None if verified > 0 else 'no_verified_candidates',
            'seconds': round(float(stats.get('seconds', 0)), 6),
            'rounds': int(stats.get('gemma_rounds', 0)) if mode == 'gemma' else 0,
            'failed_rounds': int(stats.get('gemma_failed_rounds', 0)) if mode == 'gemma' else 0,
            'skipped_candidates': int(stats.get('skipped_candidates', 0)),
            'execution_error': status == 'ERROR' or source_error,
        }
    except Exception:
        # Never serialize raw provider errors, which may contain a key/prompt.
        return {'status': 'ERROR', 'found': False, 'measured': False,
                'verified_candidates': 0, 'unmeasured_reason': 'execution_error',
                'seconds': None, 'rounds': 0, 'failed_rounds': 0,
                'skipped_candidates': 0, 'execution_error': True}


def _summary(cases):
    summary = {}
    for mode in ('model', 'fuzz'):
        wrong = [case[mode] for case in cases if case['kind'] == 'wrong']
        equivalent = [case[mode] for case in cases if case['kind'] == 'equivalent']
        all_results = wrong + equivalent
        summary[mode] = {
            'wrong_found': sum(result['found'] for result in wrong),
            'wrong_measured': sum(result['measured'] for result in wrong),
            'wrong_total': len(wrong),
            'equivalent_measured': sum(result['measured'] for result in equivalent),
            'equivalent_total': len(equivalent),
            'false_positives': sum(result['status'] in ('HIDDEN_BUG', 'WRONG_ON_SAMPLE')
                                   for result in equivalent),
            'unmeasured': sum(not result['measured'] for result in all_results),
            'errors': sum(result['execution_error'] for result in all_results)
                      + sum(result['status'] == 'WRONG_ON_SAMPLE' for result in wrong),
            'verified_candidates': sum(result['verified_candidates'] for result in all_results),
            'failed_rounds': sum(result['failed_rounds'] for result in all_results),
        }
    return summary


def evaluate(settings=None, *, exercises=None, limit=None, check_fn=None,
             clock=None, sleep=None, on_case=None):
    """Run at most one hosted request per case and never reset/retry quotas.

    The default catalog has 14 wrong queries and eight equivalent alternatives.
    The supplied clock, sleep and checker also permit deterministic offline tests.
    """
    from bmq import hunter

    settings = settings or get_settings()
    if settings.model_provider != 'gemini' or settings.model not in GEMINI_MODELS:
        raise ValueError('Configure the Gemini provider with a supported hosted Gemma model.')
    if not settings.gemini_api_key.strip():
        raise ValueError('A Gemini API key must be configured outside source code.')
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
        raise ValueError('The case limit must be a positive integer.')
    settings = replace(settings, gemma_rounds=1, model_hints=False)
    check_fn = check_fn or hunter.check
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    if exercises is None:
        exercises = json.loads((ROOT / 'data/exercises.json').read_text(encoding='utf-8'))
    selected = []
    for exercise in exercises:
        problem = {key: exercise[key] for key in PROBLEM_FIELDS if key in exercise}
        for index, wrong in enumerate(exercise['known_wrong'], 1):
            selected.append((problem, wrong['sql'], 'wrong', index))
        for index, sql in enumerate(exercise['known_correct'], 1):
            selected.append((problem, sql, 'equivalent', index))
    total = len(selected)
    if limit is not None:
        selected = selected[:limit]
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'provider': 'gemini', 'model': settings.model, 'seed': 42,
        'model_rounds_per_case': 1, 'model_start_interval_seconds': START_INTERVAL_SECONDS,
        'fuzz_max': settings.fuzz_max, 'fuzz_seconds': settings.fuzz_seconds,
        'query_timeout_seconds': settings.query_timeout,
        'model_timeout_seconds': min(settings.ollama_timeout, 45.0),
        'catalog_total': total, 'selected_total': len(selected),
        'partial_catalog': len(selected) < total, 'cases': [],
    }
    previous_start = None
    for exercise, sql, kind, variant in selected:
        if previous_start is not None:
            while (remaining := previous_start + START_INTERVAL_SECONDS - clock()) > 0:
                sleep(remaining)
        previous_start = clock()
        case = {'exercise': exercise['id'], 'kind': kind, 'variant': variant}
        case['model'] = _run(check_fn, exercise, sql, settings, 'gemma')
        case['fuzz'] = _run(check_fn, exercise, sql, settings, 'fuzz')
        report['cases'].append(case)
        if on_case is not None:
            on_case(case)
    report['summary'] = _summary(report['cases'])
    return report


def exit_code(report):
    """Missed wrong queries are findings; errors and incomplete coverage differ."""
    if any(result['false_positives'] or result['errors'] for result in report['summary'].values()):
        return 1
    if any(result['unmeasured'] for result in report['summary'].values()):
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, help='Evaluate only the first N catalog cases (smoke test)')
    parser.add_argument('--output', help='Optional JSON report path inside this repository')
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error('--limit must be positive')
    output = None
    if args.output:
        output = (ROOT / args.output).resolve()
        if not output.is_relative_to(ROOT.resolve()):
            parser.error('--output must stay inside the repository')
    try:
        report = evaluate(limit=args.limit,
                          on_case=lambda case: print(json.dumps({'case': case}), flush=True))
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(json.dumps({'summary': report['summary'], 'partial_catalog': report['partial_catalog']}), flush=True)
        return exit_code(report)
    except KeyboardInterrupt:
        print('Evaluation interrupted; emitted cases are partial and no complete report was written.', file=sys.stderr)
        return 130
    except Exception:
        print('Hosted evaluation failed. Check provider configuration and repository paths; error details are omitted.',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
