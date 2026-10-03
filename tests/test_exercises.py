"""Regression checks for authored exercises and the catalog validator."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def catalog():
    return json.loads((ROOT / "data" / "exercises.json").read_text(encoding="utf-8"))


def test_authored_catalog_has_all_queries_and_validates(catalog):
    from scripts.validate_exercises import validate_exercises

    assert len(catalog) == 8
    assert sum(len(exercise["known_wrong"]) for exercise in catalog) == 14
    assert sum(len(exercise["known_correct"]) for exercise in catalog) == 8
    validate_exercises(catalog)


@pytest.mark.parametrize("dataset_key", ["sample_data", "trap_datasets"])
def test_validator_rejects_invalid_foreign_keys(catalog, dataset_key):
    from scripts.validate_exercises import ValidationError, validate_exercise

    exercise = catalog[0]
    dataset = exercise[dataset_key]
    if dataset_key == "trap_datasets":
        dataset = dataset[0]
    dataset["orders"][0][1] = 999
    with pytest.raises(ValidationError, match="e1_paid_orders.*load"):
        validate_exercise(exercise)


def test_validator_requires_nonempty_reference_sample(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    exercise = catalog[0]
    exercise["reference_sql"] = "SELECT name, 0 AS paid_orders FROM customers WHERE 0"
    with pytest.raises(ValidationError, match="reference.*no rows"):
        validate_exercise(exercise)


def test_validator_requires_wrong_query_to_pass_sample(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    exercise = catalog[0]
    exercise["known_wrong"][0]["sql"] = "SELECT name, 999 FROM customers"
    with pytest.raises(ValidationError, match="known_wrong.*sample"):
        validate_exercise(exercise)


def test_validator_requires_a_breaking_trap_for_each_wrong_query(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    exercise = catalog[0]
    exercise["known_wrong"][0]["sql"] = exercise["reference_sql"]
    with pytest.raises(ValidationError, match="known_wrong.*never differs"):
        validate_exercise(exercise)


@pytest.mark.parametrize("only_fails_on_trap", [False, True])
def test_validator_rejects_invalid_alternative(catalog, only_fails_on_trap):
    from scripts.validate_exercises import ValidationError, validate_exercise

    exercise = catalog[0]
    exercise["known_correct"] = [
        exercise["known_wrong"][0]["sql"]
        if only_fails_on_trap
        else "SELECT name, 999 FROM customers"
    ]
    with pytest.raises(ValidationError, match="known_correct.*differs"):
        validate_exercise(exercise)


def test_validator_rejects_wrong_expected_column_count(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    exercise = catalog[0]
    exercise["expected_columns"] = ["name"]
    with pytest.raises(ValidationError, match="expected_columns"):
        validate_exercise(exercise)


def test_validator_reports_query_errors_with_exercise_and_query(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    exercise = catalog[0]
    exercise["known_wrong"][0]["sql"] = "SELECT missing_column FROM customers"
    with pytest.raises(ValidationError, match=r"e1_paid_orders.*known_wrong\[0\].*query"):
        validate_exercise(exercise)


def test_validator_rejects_duplicate_ids(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercises

    with pytest.raises(ValidationError, match="duplicate.*e1_paid_orders"):
        validate_exercises([catalog[0], copy.deepcopy(catalog[0])])


def test_validator_rejects_unknown_trap_labels(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    catalog[0]["known_wrong"][0]["trap"] = "TYPO"
    with pytest.raises(ValidationError, match="trap category"):
        validate_exercise(catalog[0])


def test_validator_checks_sample_design_even_when_sql_still_matches(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    # The two NULL mistakes still pass with only one non-Pune customer,
    # but the supplied sample must have at least two non-Pune customers.
    exercise = catalog[1]
    exercise["sample_data"]["customers"].pop()
    with pytest.raises(ValidationError, match="sample design"):
        validate_exercise(exercise)


def test_validator_preserves_the_required_calendar_boundaries(catalog):
    from scripts.validate_exercises import ValidationError, validate_exercise

    # Removing August leaves all query equivalence checks green, but loses
    # an explicitly required boundary example for the learner.
    exercise = catalog[5]
    exercise["sample_data"]["orders"].pop(0)
    with pytest.raises(ValidationError, match="sample design"):
        validate_exercise(exercise)


def test_validator_cli_works_outside_repository_root():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_exercises.py")],
        cwd=ROOT / "data",
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "8 exercises" in completed.stdout
    assert "14 known-wrong" in completed.stdout
