# Hunter evaluation

Generated (UTC): 2026-10-03T14:20:23+00:00

Model: `gemma4:e4b`; host: `http://localhost:11434`; seed: 42.
Budgets: 2 Gemma rounds; 400 fuzz datasets or 5.0 s per query; query timeout 2.0 s; Ollama timeout 45.0 s.

Gemma-only and fuzz-only are separate runs. Combined hit rate is the union of their hits, not a timed combined pipeline. Timings include sample verification and shrinking; medians below use all measured known-wrong runs, including misses.

Measured means at least one candidate completed both SQLite queries. Runs with no verified candidates are reported separately. A rate with unmeasured cases describes only that verified subset, not full-catalog performance.

## Summary

- Gemma hit rate: N/A (unavailable; not run); 14 not measured
- Fuzz hit rate: 14/14 (100.0%)
- Combined hit rate (union): N/A (both modes were not measured for every query)
- Available-mode union: 14/14 (100.0%); 14/14 queries measured in at least one mode
- Median seconds (known wrong): Gemma N/A; fuzz 0.036 s
- False positives: 0/8 evaluated alternative-query runs (8 alternatives in the catalog)
- Evaluation errors: 0
- Gemma diagnostics: 0 skipped candidates; 0 failed model rounds; 0 verified candidates across wrong queries and alternatives
- Fuzz diagnostics: 0 skipped candidates; 0 failed model rounds; 3247 verified candidates across wrong queries and alternatives

## Known-wrong queries

| Exercise / variant | Trap | Gemma found? (rounds, seconds) | Fuzz found? (tries, seconds) | Minimal rows |
|---|---|---|---|---|
| e1_paid_orders / 1 | JOIN_TYPE | N/A (unavailable; not run) | Yes (2 tries, 0.025 s) | Gemma: N/A; fuzz: 1 |
| e1_paid_orders / 2 | ON_VS_WHERE | N/A (unavailable; not run) | Yes (2 tries, 0.023 s) | Gemma: N/A; fuzz: 1 |
| e1_paid_orders / 3 | COUNT_STAR_VS_COLUMN | N/A (unavailable; not run) | Yes (2 tries, 0.023 s) | Gemma: N/A; fuzz: 1 |
| e2_not_in_pune / 1 | NULL_COMPARISON | N/A (unavailable; not run) | Yes (5 tries, 0.043 s) | Gemma: N/A; fuzz: 1 |
| e2_not_in_pune / 2 | NULL_COMPARISON | N/A (unavailable; not run) | Yes (5 tries, 0.043 s) | Gemma: N/A; fuzz: 1 |
| e3_paid_orders_revenue / 1 | JOIN_FANOUT | N/A (unavailable; not run) | Yes (6 tries, 0.049 s) | Gemma: N/A; fuzz: 5 |
| e3_paid_orders_revenue / 2 | AGGREGATE_LOGIC | N/A (unavailable; not run) | Yes (3 tries, 0.045 s) | Gemma: N/A; fuzz: 4 |
| e4_most_expensive / 1 | TIES | N/A (unavailable; not run) | Yes (2 tries, 0.024 s) | Gemma: N/A; fuzz: 2 |
| e5_cancellation_rate / 1 | INTEGER_DIVISION | N/A (unavailable; not run) | Yes (9 tries, 0.052 s) | Gemma: N/A; fuzz: 5 |
| e6_september_orders / 1 | DATE_BOUNDARY | N/A (unavailable; not run) | Yes (5 tries, 0.041 s) | Gemma: N/A; fuzz: 2 |
| e6_september_orders / 2 | DATE_BOUNDARY | N/A (unavailable; not run) | Yes (1 tries, 0.030 s) | Gemma: N/A; fuzz: 2 |
| e7_more_than_two_orders / 1 | GROUP_BY_GRAIN | N/A (unavailable; not run) | Yes (3 tries, 0.040 s) | Gemma: N/A; fuzz: 5 |
| e8_never_paid / 1 | ANTI_JOIN | N/A (unavailable; not run) | Yes (1 tries, 0.031 s) | Gemma: N/A; fuzz: 3 |
| e8_never_paid / 2 | ANTI_JOIN | N/A (unavailable; not run) | Yes (1 tries, 0.030 s) | Gemma: N/A; fuzz: 3 |

Minimal rows means row-minimal under greedy deletion, not globally smallest. A missed query is not proof of correctness. Fuzz tries count datasets where both queries completed; skipped candidates do not count as successful stress tests.

## Equivalent alternatives

The false-positive denominator includes runs with verified stress candidates or a concrete sample mismatch. Errors and runs with no verified stress candidates and no sample mismatch are excluded.

| Exercise / alternative | Gemma-only | Fuzz-only |
|---|---|---|
| e1_paid_orders / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.668 s) |
| e2_not_in_pune / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.582 s) |
| e3_paid_orders_revenue / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.771 s) |
| e4_most_expensive / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.737 s) |
| e5_cancellation_rate / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.614 s) |
| e6_september_orders / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.543 s) |
| e7_more_than_two_orders / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.594 s) |
| e8_never_paid / 1 | N/A (unavailable; not run) | PASSED (400 tries, 0.596 s) |

## Reproduce

Run from the repository root in PowerShell:

```powershell
$env:BMQ_MODEL='gemma4:e4b'; $env:BMQ_OLLAMA_HOST='http://localhost:11434'; $env:BMQ_GEMMA_ROUNDS='2'; $env:BMQ_FUZZ_MAX='400'; $env:BMQ_FUZZ_SECONDS='5.0'; $env:BMQ_QUERY_TIMEOUT='2.0'; $env:BMQ_OLLAMA_TIMEOUT='45.0'; .\.venv\Scripts\python.exe .\scripts\eval_hunters.py
```

Model sampling and wall-clock budgets can vary across runs; seed 42 fixes the fuzz dataset sequence. Gemma requires the configured model already available in local Ollama.
