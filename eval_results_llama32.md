# Hunter evaluation

Generated (UTC): 2026-10-04T04:09:23+00:00

Model: `llama3.2:latest`; host: `http://127.0.0.1:11435`; seed: 42.
Budgets: 2 model rounds; 400 fuzz datasets or 5.0 s per query; query timeout 2.0 s; Ollama timeout 45.0 s.

Model-only and fuzz-only are separate runs. Combined hit rate is the union of their hits, not a timed combined pipeline. Timings include sample verification and shrinking; medians below use all measured known-wrong runs, including misses.

Measured means at least one candidate completed both SQLite queries. Runs with no verified candidates are reported separately. A rate with unmeasured cases describes only that verified subset, not full-catalog performance.

## Summary

- Model hit rate: 9/14 (64.3%)
- Fuzz hit rate: 14/14 (100.0%)
- Combined hit rate (union): 14/14 (100.0%)
- Median seconds (known wrong): Model 31.910 s; fuzz 0.053 s
- False positives: 0/16 evaluated alternative-query runs (8 alternatives in the catalog)
- Evaluation errors: 0
- Model diagnostics: 0 skipped candidates; 3 failed model rounds; 80 verified candidates across wrong queries and alternatives
- Fuzz diagnostics: 0 skipped candidates; 0 failed model rounds; 3247 verified candidates across wrong queries and alternatives

## Known-wrong queries

| Exercise / variant | Trap | Model found? (rounds, seconds) | Fuzz found? (tries, seconds) | Minimal rows |
|---|---|---|---|---|
| e1_paid_orders / 1 | JOIN_TYPE | Yes (1 rounds, 17.181 s) | Yes (2 tries, 0.241 s) | Model: 1; fuzz: 1 |
| e1_paid_orders / 2 | ON_VS_WHERE | Yes (1 rounds, 17.282 s) | Yes (2 tries, 0.827 s) | Model: 1; fuzz: 1 |
| e1_paid_orders / 3 | COUNT_STAR_VS_COLUMN | Yes (1 rounds, 30.507 s) | Yes (2 tries, 0.022 s) | Model: 1; fuzz: 1 |
| e2_not_in_pune / 1 | NULL_COMPARISON | No (2 rounds, 33.312 s) | Yes (5 tries, 0.125 s) | Model: N/A; fuzz: 1 |
| e2_not_in_pune / 2 | NULL_COMPARISON | Yes (1 rounds, 18.841 s) | Yes (5 tries, 0.409 s) | Model: 1; fuzz: 1 |
| e3_paid_orders_revenue / 1 | JOIN_FANOUT | No (2 rounds, 63.686 s) | Yes (6 tries, 0.060 s) | Model: N/A; fuzz: 5 |
| e3_paid_orders_revenue / 2 | AGGREGATE_LOGIC | Yes (1 rounds, 38.689 s) | Yes (3 tries, 0.047 s) | Model: 4; fuzz: 4 |
| e4_most_expensive / 1 | TIES | Yes (1 rounds, 25.682 s) | Yes (2 tries, 0.024 s) | Model: 2; fuzz: 2 |
| e5_cancellation_rate / 1 | INTEGER_DIVISION | Yes (1 rounds, 37.133 s) | Yes (9 tries, 0.052 s) | Model: 6; fuzz: 5 |
| e6_september_orders / 1 | DATE_BOUNDARY | Yes (1 rounds, 22.369 s) | Yes (5 tries, 0.077 s) | Model: 2; fuzz: 2 |
| e6_september_orders / 2 | DATE_BOUNDARY | No (2 rounds, 83.742 s) | Yes (1 tries, 0.022 s) | Model: N/A; fuzz: 2 |
| e7_more_than_two_orders / 1 | GROUP_BY_GRAIN | No (2 rounds, 69.091 s) | Yes (3 tries, 0.054 s) | Model: N/A; fuzz: 5 |
| e8_never_paid / 1 | ANTI_JOIN | Yes (1 rounds, 17.345 s) | Yes (1 tries, 0.033 s) | Model: 1; fuzz: 3 |
| e8_never_paid / 2 | ANTI_JOIN | No (2 rounds, 38.848 s) | Yes (1 tries, 0.037 s) | Model: N/A; fuzz: 3 |

Minimal rows means row-minimal under greedy deletion, not globally smallest. A missed query is not proof of correctness. Fuzz tries count datasets where both queries completed; skipped candidates do not count as successful stress tests.

## Equivalent alternatives

The false-positive denominator includes runs with verified stress candidates or a concrete sample mismatch. Errors and runs with no verified stress candidates and no sample mismatch are excluded.

| Exercise / alternative | Model-only | Fuzz-only |
|---|---|---|
| e1_paid_orders / 1 | PASSED (2 rounds, 32.402 s) | PASSED (400 tries, 2.992 s) |
| e2_not_in_pune / 1 | PASSED (2 rounds, 31.361 s) | PASSED (400 tries, 1.447 s) |
| e3_paid_orders_revenue / 1 | PASSED (2 rounds, 62.844 s) | PASSED (400 tries, 0.988 s) |
| e4_most_expensive / 1 | PASSED (2 rounds, 54.540 s) | PASSED (400 tries, 0.742 s) |
| e5_cancellation_rate / 1 | PASSED (2 rounds, 59.690 s) | PASSED (400 tries, 0.684 s) |
| e6_september_orders / 1 | PASSED (2 rounds, 54.932 s) | PASSED (400 tries, 0.334 s) |
| e7_more_than_two_orders / 1 | PASSED (2 rounds, 60.616 s) | PASSED (400 tries, 0.359 s) |
| e8_never_paid / 1 | PASSED (2 rounds, 30.566 s) | PASSED (400 tries, 0.678 s) |

## Reproduce

Run from the repository root in PowerShell:

```powershell
$env:BMQ_MODEL='llama3.2:latest'; $env:BMQ_OLLAMA_HOST='http://127.0.0.1:11435'; $env:BMQ_GEMMA_ROUNDS='2'; $env:BMQ_FUZZ_MAX='400'; $env:BMQ_FUZZ_SECONDS='5.0'; $env:BMQ_QUERY_TIMEOUT='2.0'; $env:BMQ_OLLAMA_TIMEOUT='45.0'; .\.venv\Scripts\python.exe .\scripts\eval_hunters.py --output eval_results_llama32.md
```

Model sampling and wall-clock budgets can vary across runs; seed 42 fixes the fuzz dataset sequence. Model runs require the configured model already available in local Ollama.

## Run history

Completed after the owner restarted Docker. This report retains the completed E1–E2 measurements from the run started at 2026-10-03T18:52:35+00:00 and replaces all E3–E8 results with fresh runs started at 2026-10-04T03:57:19+00:00, using the same budgets and model. E3 was rerun in full because its first case had an interrupted model round. This is a resumed catalog evaluation, not one uninterrupted timing benchmark.
