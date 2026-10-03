"""Prove that real exercise mistakes are exposed without reading trap fixtures."""

from contextlib import closing
import json
from pathlib import Path
import random


def test_each_paid_orders_trap_shrinks_to_at_most_two_rows():
    from bmq.compare import equal
    from bmq.db import build_db, run_query
    from bmq.shrink import shrink

    root = Path(__file__).resolve().parents[1]
    exercise = json.loads((root / 'data/exercises.json').read_text(encoding='utf-8'))[0]
    for wrong in exercise['known_wrong']:
        def still_fails(dataset):
            with closing(build_db(dataset)) as conn:
                expected = run_query(conn, exercise['reference_sql'], 2)
                actual = run_query(conn, wrong['sql'], 2)
                return not equal(expected, actual)

        small = shrink(exercise['trap_datasets'][0], still_fails)
        assert sum(map(len, small.values())) <= 2, wrong['trap']
        assert still_fails(small)


def test_seeded_fuzz_and_shrink_expose_all_exercise_mistakes():
    from bmq.compare import equal
    from bmq.db import build_db, run_query, QueryError
    from bmq.fuzz import generate
    from bmq.shrink import shrink

    root = Path(__file__).resolve().parents[1]
    exercises = json.loads((root / 'data/exercises.json').read_text(encoding='utf-8'))
    pools = json.loads((root / 'data/fuzz_pools.json').read_text(encoding='utf-8'))
    checked = 0
    for exercise in exercises:
        for wrong in exercise['known_wrong']:
            rng = random.Random(42)

            def still_fails(dataset):
                with closing(build_db(dataset)) as conn:
                    try:
                        expected = run_query(conn, exercise['reference_sql'], 2)
                        actual = run_query(conn, wrong['sql'], 2)
                    except QueryError:
                        return False
                return not equal(expected, actual, exercise['order_matters'])

            for _ in range(400):
                dataset = generate(rng, pools)
                if still_fails(dataset):
                    small = shrink(dataset, still_fails)
                    assert still_fails(small)
                    assert sum(map(len, small.values())) <= 6, (exercise['id'], wrong['trap'], small)
                    checked += 1
                    break
            else:
                raise AssertionError(f"Fuzz missed {exercise['id']}: {wrong['trap']}")
    assert checked == 14


def test_equivalent_queries_agree_on_seeded_random_data():
    from bmq.compare import equal
    from bmq.db import build_db, run_query
    from bmq.fuzz import generate

    root = Path(__file__).resolve().parents[1]
    exercises = json.loads((root / 'data/exercises.json').read_text(encoding='utf-8'))
    pools = json.loads((root / 'data/fuzz_pools.json').read_text(encoding='utf-8'))
    rng = random.Random(42)
    for _ in range(400):
        with closing(build_db(generate(rng, pools))) as conn:
            for exercise in exercises:
                expected = run_query(conn, exercise['reference_sql'], 2)
                for sql in exercise['known_correct']:
                    actual = run_query(conn, sql, 2)
                    assert equal(expected, actual, exercise['order_matters']), exercise['id']
