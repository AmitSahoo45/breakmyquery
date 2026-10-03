"""Evaluation reports must preserve coverage and never turn outages into misses."""

from copy import deepcopy
import subprocess
import sys
from uuid import uuid4

import pytest

from bmq.config import ROOT


@pytest.fixture
def report_dir():
    # Default mkdir permissions avoid the managed Windows chmod(0700) issue.
    directory = (ROOT / ".cache" / f"eval-tests-{uuid4().hex}").resolve()
    assert directory.is_relative_to(ROOT)
    directory.mkdir(parents=True)
    yield directory
    for child in directory.iterdir():
        child.unlink()
    directory.rmdir()


def report_fixture():
    """Two independent runs catch different mistakes, for a 100% union."""
    def result(found, seconds, steps, rows=None):
        return {
            "status": "HIDDEN_BUG" if found else "PASSED",
            "found": found, "seconds": seconds, "steps": steps, "rows": rows,
            "measured": True, "verified_candidates": 1,
            "unmeasured_reason": None, "skipped_candidates": 0, "failed_rounds": 0,
        }

    return {
        "generated_at": "2026-10-03T12:00:00+00:00",
        "config": {
            "model": "gemma4:e4b", "ollama_host": "http://localhost:11434",
            "gemma_rounds": 2, "fuzz_max": 400, "fuzz_seconds": 5.0,
            "query_timeout": 2.0, "ollama_timeout": 45.0,
        },
        "fuzz_only": False, "seed": 42,
        "gemma_status": "available", "fuzz_status": "available",
        "wrong_cases": [
            {"exercise": "e1", "variant": 1, "trap": "JOIN_TYPE",
             "gemma": result(True, 1.0, 1, 1), "fuzz": result(False, 2.0, 400)},
            {"exercise": "e2", "variant": 1, "trap": "NULL_COMPARISON",
             "gemma": result(False, 3.0, 2), "fuzz": result(True, 6.0, 2, 2)},
        ],
        "correct_cases": [
            {"exercise": "e1", "variant": 1,
             "gemma": result(False, 7.0, 2), "fuzz": result(False, 8.0, 400)},
        ],
    }


def test_report_uses_union_and_medians_of_wrong_query_runs():
    from scripts.eval_hunters import format_report

    text = format_report(report_fixture())
    assert "Gemma hit rate: 1/2 (50.0%)" in text
    assert "Fuzz hit rate: 1/2 (50.0%)" in text
    assert "Combined hit rate (union): 2/2 (100.0%)" in text
    assert "Gemma 2.000 s; fuzz 4.000 s" in text
    assert "Gemma: 1; fuzz: N/A" in text
    assert "Gemma: N/A; fuzz: 2" in text
    assert "False positives: 0/2" in text
    assert "not a timed combined pipeline" in text
    assert "row-minimal" in text
    assert "2026-10-03T12:00:00+00:00" in text
    assert "BMQ_MODEL='gemma4:e4b'" in text
    assert "--fuzz-only" not in text


def test_offline_report_does_not_score_gemma_as_zero_percent():
    from scripts.eval_hunters import format_report

    report = report_fixture()
    report["gemma_status"] = "unavailable"
    for case in report["wrong_cases"] + report["correct_cases"]:
        case["gemma"] = None
    text = format_report(report)
    assert "Gemma hit rate: N/A (unavailable; not run)" in text
    assert "Combined hit rate (union): N/A" in text
    assert "Available-mode union: 1/2 (50.0%)" in text
    assert "False positives: 0/1" in text
    assert "Gemma 0.000 s" not in text


def test_mid_run_outage_is_excluded_from_measured_gemma_denominator():
    from scripts.eval_hunters import format_report

    report = report_fixture()
    report["wrong_cases"][1]["gemma"]["measured"] = False
    report["wrong_cases"][1]["gemma"]["unmeasured_reason"] = "unavailable during run"
    text = format_report(report)
    assert "Gemma hit rate: 1/1 (100.0%); 1 not measured" in text
    assert "Combined hit rate (union): N/A" in text
    assert "N/A (unavailable during run)" in text


def test_main_writes_report_but_fails_on_false_positive(report_dir, monkeypatch):
    from scripts import eval_hunters

    report = report_fixture()
    report["correct_cases"][0]["fuzz"] = deepcopy(report["wrong_cases"][1]["fuzz"])
    monkeypatch.setattr(eval_hunters, "evaluate", lambda **kwargs: report)
    output = report_dir / "false-positive.md"
    assert eval_hunters.main(["--output", str(output)]) == 1
    text = output.read_text(encoding="utf-8")
    assert "False positives: 1/2" in text
    assert "e1" in text and "HIDDEN_BUG" in text


def test_main_fails_on_query_error_without_leaking_query_text(report_dir, monkeypatch):
    from scripts import eval_hunters

    report = report_fixture()
    report["wrong_cases"][0]["gemma"]["status"] = "ERROR"
    report["wrong_cases"][0]["gemma"]["found"] = False
    report["wrong_cases"][0]["gemma"]["measured"] = False
    report["wrong_cases"][0]["gemma"]["unmeasured_reason"] = "no verified candidates"
    monkeypatch.setattr(eval_hunters, "evaluate", lambda **kwargs: report)
    output = report_dir / "error.md"
    assert eval_hunters.main(["--output", str(output)]) == 1
    text = output.read_text(encoding="utf-8")
    assert "Evaluation errors: 1" in text
    assert "ERROR" in text


def test_sample_false_positive_counts_as_evaluated_even_without_stress_candidates():
    from scripts.eval_hunters import format_report

    report = report_fixture()
    result = report["correct_cases"][0]["gemma"]
    result.update(status="WRONG_ON_SAMPLE", measured=False, verified_candidates=0,
                  unmeasured_reason="no verified candidates")
    text = format_report(report)
    assert "False positives: 1/2 evaluated alternative-query runs" in text
    assert "WRONG_ON_SAMPLE" in text


def test_alternative_query_error_is_not_counted_as_evaluated():
    from scripts.eval_hunters import format_report

    report = report_fixture()
    report["correct_cases"][0]["gemma"]["status"] = "ERROR"
    text = format_report(report)
    assert "False positives: 0/1 evaluated alternative-query runs" in text
    assert "Evaluation errors: 1" in text


def test_output_escape_is_rejected_before_evaluation(monkeypatch):
    from scripts import eval_hunters

    def should_not_evaluate(**kwargs):
        pytest.fail("Output validation must precede model calls")

    monkeypatch.setattr(eval_hunters, "evaluate", should_not_evaluate)
    with pytest.raises(SystemExit) as exc:
        eval_hunters.main(["--output", "../outside-eval.md"])
    assert exc.value.code == 2


def test_cli_help_works_from_another_directory(report_dir):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/eval_hunters.py"), "--help"],
        cwd=report_dir, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--fuzz-only" in completed.stdout
    assert "--output" in completed.stdout


def test_offline_evaluation_catches_all_fourteen_and_passes_eight_alternatives(monkeypatch):
    from bmq import llm
    from bmq.config import Settings
    from scripts.eval_hunters import evaluate

    monkeypatch.setattr(llm, "model_available", lambda settings=None: False)
    report = evaluate(Settings())
    assert report["gemma_status"] == "unavailable"
    assert len(report["wrong_cases"]) == 14
    assert all(case["gemma"] is None for case in report["wrong_cases"])
    assert all(case["fuzz"]["found"] for case in report["wrong_cases"])
    assert all(case["fuzz"]["rows"] <= 6 for case in report["wrong_cases"])
    assert len(report["correct_cases"]) == 8
    assert all(case["fuzz"]["status"] == "PASSED" for case in report["correct_cases"])


def test_fuzz_only_never_contacts_model(monkeypatch):
    from bmq import llm
    from bmq.config import Settings
    from scripts.eval_hunters import evaluate, format_report

    def forbidden_model_call(settings=None):
        pytest.fail("Explicit fuzz-only evaluations must not contact Ollama")

    monkeypatch.setattr(llm, "model_available", forbidden_model_call)
    report = evaluate(Settings(fuzz_max=1), fuzz_only=True)
    assert report["gemma_status"] == "not_requested"
    assert len(report["wrong_cases"]) == 14
    assert len(report["correct_cases"]) == 8
    assert "--fuzz-only" in format_report(report)


def test_available_modes_use_separate_runs_and_never_pass_authored_traps(monkeypatch):
    from bmq import hunter, llm
    from bmq.config import Settings
    from scripts.eval_hunters import evaluate

    calls = []

    def recorded_check(exercise, learner_sql, progress_cb=None, *, settings=None, seed=42):
        assert not {"known_wrong", "known_correct", "trap_datasets"} & exercise.keys()
        assert settings.hunt_order in (("gemma",), ("fuzz",))
        assert seed == 42
        calls.append((exercise["id"], learner_sql, settings.hunt_order[0]))
        return hunter.Verdict(status="PASSED", stats={
            "gemma_rounds": 2, "gemma_candidates": 6, "fuzz_tries": 400,
            "seconds": 1.0, "gemma_available": True,
            "skipped_candidates": 0, "gemma_failed_rounds": 0,
        })

    monkeypatch.setattr(llm, "model_available", lambda settings=None: True)
    monkeypatch.setattr(hunter, "check", recorded_check)
    report = evaluate(Settings())
    assert report["gemma_status"] == "available"
    assert len(calls) == 44
    assert all(calls[index][2] == "gemma" and calls[index + 1][2] == "fuzz"
               and calls[index][:2] == calls[index + 1][:2]
               for index in range(0, 44, 2))
    assert len(report["wrong_cases"]) == 14
    assert len(report["correct_cases"]) == 8


def test_reachable_model_without_verified_candidates_is_unmeasured(monkeypatch):
    from bmq import llm
    from bmq.config import Settings
    from scripts.eval_hunters import evaluate, format_report

    monkeypatch.setattr(llm, "model_available", lambda settings=None: True)
    monkeypatch.setattr(llm, "propose_datasets", lambda *args, **kwargs: [])
    report = evaluate(Settings(fuzz_max=1))
    assert report["gemma_status"] == "available"
    for case in report["wrong_cases"] + report["correct_cases"]:
        assert case["gemma"]["measured"] is False
        assert case["gemma"]["unmeasured_reason"] == "no verified candidates"
        assert case["gemma"]["failed_rounds"] == 2
    text = format_report(report)
    assert "Gemma hit rate: N/A (no measured runs); 14 not measured" in text
    assert "Combined hit rate (union): N/A" in text
    assert "N/A (no verified candidates)" in text
    assert "44 failed model rounds" in text
    assert "Gemma hit rate: 0/14" not in text
    assert "unavailable" not in text


def test_fuzz_without_completed_pairs_is_unmeasured(monkeypatch):
    from bmq import hunter
    from bmq.config import Settings
    from scripts.eval_hunters import evaluate, format_report

    monkeypatch.setattr(hunter, "check", lambda *args, **kwargs: hunter.Verdict(
        status="PASSED", stats={"fuzz_tries": 0, "seconds": 0.1, "skipped_candidates": 3},
    ))
    report = evaluate(Settings(), fuzz_only=True)
    assert all(case["fuzz"]["measured"] is False for case in report["wrong_cases"])
    text = format_report(report)
    assert "Fuzz hit rate: N/A (no measured runs); 14 not measured" in text
    assert "66 skipped candidates" in text
