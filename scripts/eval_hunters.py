"""Evaluate separate model/fuzz hunts without exposing answer SQL in the report."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmq.config import Settings, get_settings


MODES = ("gemma", "fuzz")
CONFIG_FIELDS = (
    "model", "ollama_host", "gemma_rounds", "fuzz_max", "fuzz_seconds",
    "query_timeout", "ollama_timeout",
)


def evaluate(settings: Settings | None = None, *, fuzz_only: bool = False) -> dict:
    """Return measurements for every wrong query and alternative, using seed 42.

    Each method gets an independent hunt. Initial model unavailability skips
    every Gemma run; the fuzz-only flag avoids even contacting Ollama.
    """
    from bmq import hunter, llm

    settings = settings or get_settings()
    exercises = json.loads((ROOT / "data/exercises.json").read_text(encoding="utf-8"))
    if fuzz_only:
        gemma_status = "not_requested"
    elif settings.gemma_rounds == 0:
        gemma_status = "disabled"
    else:
        gemma_status = "available" if llm.model_available(settings=settings) else "unavailable"
    fuzz_status = "available" if settings.fuzz_max > 0 and settings.fuzz_seconds > 0 else "disabled"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {field: getattr(settings, field) for field in CONFIG_FIELDS},
        "fuzz_only": fuzz_only, "seed": 42,
        "gemma_status": gemma_status, "fuzz_status": fuzz_status,
        "wrong_cases": [], "correct_cases": [],
    }

    def run(exercise, sql, mode):
        if report[f"{mode}_status"] != "available":
            return None
        verdict = hunter.check(exercise, sql, settings=replace(settings, hunt_order=(mode,)), seed=42)
        stats = verdict.stats
        verified = stats.get("gemma_candidates" if mode == "gemma" else "fuzz_tries", 0)
        reason = None
        if verified == 0:
            reason = "unavailable during run" if mode == "gemma" and stats.get("gemma_available") is False else "no verified candidates"
        return {
            "status": verdict.status,
            "found": verdict.status == "HIDDEN_BUG",
            "seconds": stats["seconds"],
            "steps": stats["gemma_rounds" if mode == "gemma" else "fuzz_tries"],
            "rows": sum(map(len, verdict.dataset.values())) if verdict.dataset is not None else None,
            "measured": verified > 0,
            "verified_candidates": verified,
            "unmeasured_reason": reason,
            "skipped_candidates": stats.get("skipped_candidates", 0),
            "failed_rounds": stats.get("gemma_failed_rounds", 0),
        }

    for exercise in exercises:
        # Evaluation owns the answers/traps; the hunter receives only its inputs.
        hunt_exercise = {key: value for key, value in exercise.items()
                         if key not in ("known_wrong", "known_correct", "trap_datasets")}
        for index, wrong in enumerate(exercise["known_wrong"], start=1):
            case = {"exercise": exercise["id"], "variant": index, "trap": wrong["trap"]}
            case.update({mode: run(hunt_exercise, wrong["sql"], mode) for mode in MODES})
            report["wrong_cases"].append(case)
        for index, sql in enumerate(exercise["known_correct"], start=1):
            case = {"exercise": exercise["id"], "variant": index}
            case.update({mode: run(hunt_exercise, sql, mode) for mode in MODES})
            report["correct_cases"].append(case)
    return report


def _measured(result):
    return result is not None and result["measured"]


def _fraction(numerator, denominator):
    return f"{numerator}/{denominator} ({100 * numerator / denominator:.1f}%)" if denominator else "N/A"


def _issues(report):
    false_positives = sum(
        result is not None and result["status"] in ("HIDDEN_BUG", "WRONG_ON_SAMPLE")
        for case in report["correct_cases"] for result in (case[mode] for mode in MODES)
    )
    errors = sum(
        result is not None and result["status"] not in ("HIDDEN_BUG", "PASSED")
        for case in report["wrong_cases"] for result in (case[mode] for mode in MODES)
    ) + sum(
        result is not None and result["status"] not in ("HIDDEN_BUG", "WRONG_ON_SAMPLE", "PASSED")
        for case in report["correct_cases"] for result in (case[mode] for mode in MODES)
    )
    return false_positives, errors


def _not_run(report, mode):
    status = report[f"{mode}_status"].replace("_", " ")
    return f"N/A ({status}; not run)"


def _cell(result, mode, report, *, alternative=False):
    if result is None:
        return _not_run(report, mode)
    if not result["measured"] and result["status"] == "PASSED":
        return f"N/A ({result['unmeasured_reason']})"
    label = result["status"] if alternative or result["status"] not in ("PASSED", "HIDDEN_BUG") else (
        "Yes" if result["found"] else "No"
    )
    unit = "rounds" if mode == "gemma" else "tries"
    return f"{label} ({result['steps']} {unit}, {result['seconds']:.3f} s)"


def format_report(report: dict) -> str:
    """Render coverage, error counts, and an explicitly untimed union of hits."""
    wrong = report["wrong_cases"]
    correct = report["correct_cases"]
    config = report["config"]
    lines = [
        "# Hunter evaluation", "", f"Generated (UTC): {report['generated_at']}", "",
        f"Model: `{config['model']}`; host: `{config['ollama_host']}`; seed: {report['seed']}.",
        f"Budgets: {config['gemma_rounds']} Gemma rounds; {config['fuzz_max']} fuzz datasets or "
        f"{config['fuzz_seconds']} s per query; query timeout {config['query_timeout']} s; "
        f"Ollama timeout {config['ollama_timeout']} s.", "",
        "Gemma-only and fuzz-only are separate runs. Combined hit rate is the union of their "
        "hits, not a timed combined pipeline. Timings include sample verification and shrinking; "
        "medians below use all measured known-wrong runs, including misses.", "",
        "Measured means at least one candidate completed both SQLite queries. Runs with no "
        "verified candidates are reported separately. A rate with unmeasured cases describes "
        "only that verified subset, not full-catalog performance.", "",
        "## Summary", "",
    ]
    medians = []
    for mode in MODES:
        measured = [case[mode] for case in wrong if _measured(case[mode])]
        label = mode.capitalize()
        if measured:
            score = _fraction(sum(result["found"] for result in measured), len(measured))
            if len(measured) != len(wrong):
                score += f"; {len(wrong) - len(measured)} not measured"
            medians.append(f"{label if mode == 'gemma' else mode} {median(result['seconds'] for result in measured):.3f} s")
        else:
            score = _not_run(report, mode) if report[f"{mode}_status"] != "available" else "N/A (no measured runs)"
            medians.append(f"{label if mode == 'gemma' else mode} N/A")
            score += f"; {len(wrong)} not measured"
        lines.append(f"- {label} hit rate: {score}")
    hits = sum(any(_measured(case[mode]) and case[mode]["found"] for mode in MODES) for case in wrong)
    complete = bool(wrong) and all(_measured(case[mode]) for case in wrong for mode in MODES)
    lines.append("- Combined hit rate (union): " + (
        _fraction(hits, len(wrong)) if complete else "N/A (both modes were not measured for every query)"
    ))
    available_cases = [case for case in wrong if any(_measured(case[mode]) for mode in MODES)]
    if not complete:
        lines.append(f"- Available-mode union: {_fraction(hits, len(available_cases))}; "
                     f"{len(available_cases)}/{len(wrong)} queries measured in at least one mode")
    lines.append(f"- Median seconds (known wrong): {'; '.join(medians)}")
    false_positives, errors = _issues(report)
    correct_runs = sum(
        result is not None and (result["status"] in ("HIDDEN_BUG", "WRONG_ON_SAMPLE")
                                or result["status"] == "PASSED" and _measured(result))
        for case in correct for result in (case[mode] for mode in MODES)
    )
    lines += [f"- False positives: {false_positives}/{correct_runs} evaluated alternative-query runs "
              f"({len(correct)} alternatives in the catalog)", f"- Evaluation errors: {errors}"]
    for mode in MODES:
        results = [case[mode] for case in wrong + correct if case[mode] is not None]
        lines.append(f"- {mode.capitalize()} diagnostics: "
                     f"{sum(result['skipped_candidates'] for result in results)} skipped candidates; "
                     f"{sum(result['failed_rounds'] for result in results)} failed model rounds; "
                     f"{sum(result['verified_candidates'] for result in results)} verified candidates "
                     "across wrong queries and alternatives")
    lines += ["", "## Known-wrong queries", "",
              "| Exercise / variant | Trap | Gemma found? (rounds, seconds) | Fuzz found? (tries, seconds) | Minimal rows |",
              "|---|---|---|---|---|"]
    for case in wrong:
        row_counts = "; ".join(
            f"{mode.capitalize() if mode == 'gemma' else mode}: " + (
                str(case[mode]["rows"]) if _measured(case[mode]) and case[mode]["found"] else "N/A"
            ) for mode in MODES
        )
        lines.append(f"| {case['exercise']} / {case['variant']} | {case['trap']} | "
                     f"{_cell(case['gemma'], 'gemma', report)} | {_cell(case['fuzz'], 'fuzz', report)} | {row_counts} |")
    lines += ["", "Minimal rows means row-minimal under greedy deletion, not globally smallest. "
              "A missed query is not proof of correctness. Fuzz tries count datasets where both "
              "queries completed; skipped candidates do not count as successful stress tests.", "",
              "## Equivalent alternatives", "",
              "The false-positive denominator includes runs with verified stress candidates or a "
              "concrete sample mismatch. Errors and runs with no verified stress candidates and no "
              "sample mismatch are excluded.", "",
              "| Exercise / alternative | Gemma-only | Fuzz-only |", "|---|---|---|"]
    for case in correct:
        lines.append(f"| {case['exercise']} / {case['variant']} | "
                     f"{_cell(case['gemma'], 'gemma', report, alternative=True)} | "
                     f"{_cell(case['fuzz'], 'fuzz', report, alternative=True)} |")
    command = "; ".join(
        f"$env:BMQ_{field.upper()}='{str(config[field]).replace(chr(39), chr(39) * 2)}'"
        for field in CONFIG_FIELDS
    )
    command += "; .\\.venv\\Scripts\\python.exe .\\scripts\\eval_hunters.py"
    if report["fuzz_only"]:
        command += " --fuzz-only"
    lines += ["", "## Reproduce", "", "Run from the repository root in PowerShell:", "",
              "```powershell", command, "```", "",
              "Model sampling and wall-clock budgets can vary across runs; seed 42 fixes the fuzz "
              "dataset sequence. Gemma requires the configured model already available in local Ollama.", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fuzz-only", action="store_true", help="Do not contact Ollama; evaluate seeded fuzzing only")
    parser.add_argument("--output", default="eval_results.md", help="Report path inside the repository (relative to its root)")
    args = parser.parse_args(argv)
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("--output must stay inside the repository")
    try:
        report = evaluate(fuzz_only=args.fuzz_only)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(format_report(report), encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1
    false_positives, errors = _issues(report)
    print(f"Wrote {output}; false positives: {false_positives}; evaluation errors: {errors}.")
    return 1 if false_positives or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
