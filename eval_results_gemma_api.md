# Gemma 4 through the Gemini API: catalog evaluation

Generated: **2026-10-04T13:09:17+00:00**. Provider: `gemini`. Model: **`gemma-4-26b-a4b-it`**.

These are live API calls from the local checkout, not measurements of a deployed web host. One project/key was used, with billing reported disabled by the owner. There was no key rotation or automatic request retry.

| Measurement | Gemma API only | Fuzz only |
|---|---:|---:|
| Wrong queries exposed | 14/14 | 14/14 |
| Wrong queries with verified stress candidates | 14/14 | 14/14 |
| Equivalent alternatives measured | 7/8 | 8/8 |
| False positives | 0 | 0 |
| Unmeasured cases | 1 | 0 |
| Evaluation errors | 0 | 0 |
| Failed model rounds | 1 | N/A |

Model-only and fuzz-only hunts were independent. The hunter received the schema, question and compared queries; it did not receive authored trap datasets or known-answer lists. SQLite verified each candidate and the final shrunk counterexample.

## Configuration

- Seed 42; one model round per case, up to three proposed datasets.
- Model hunt starts at least 35 seconds apart.
- Fuzz budget 400 datasets or 5 seconds per case.
- Query timeout 2 seconds; API timeout 45 seconds.
- Generated hints and classifications disabled; their teaching quality was not evaluated.

## Per-case results

| Exercise | Case | Gemma | Verified model candidates | Model seconds | Fuzz |
|---|---|---|---:|---:|---|
| e1_paid_orders | wrong 1 | caught | 1 | 21.538 | caught |
| e1_paid_orders | wrong 2 | caught | 1 | 16.308 | caught |
| e1_paid_orders | wrong 3 | caught | 1 | 16.337 | caught |
| e1_paid_orders | equivalent 1 | no mismatch | 3 | 15.056 | no mismatch |
| e2_not_in_pune | wrong 1 | caught | 1 | 20.803 | caught |
| e2_not_in_pune | wrong 2 | caught | 1 | 14.188 | caught |
| e2_not_in_pune | equivalent 1 | no mismatch | 3 | 18.781 | no mismatch |
| e3_paid_orders_revenue | wrong 1 | caught | 1 | 17.968 | caught |
| e3_paid_orders_revenue | wrong 2 | caught | 1 | 16.428 | caught |
| e3_paid_orders_revenue | equivalent 1 | no mismatch | 3 | 16.304 | no mismatch |
| e4_most_expensive | wrong 1 | caught | 1 | 13.711 | caught |
| e4_most_expensive | equivalent 1 | no mismatch | 3 | 13.984 | no mismatch |
| e5_cancellation_rate | wrong 1 | caught | 1 | 24.079 | caught |
| e5_cancellation_rate | equivalent 1 | unmeasured | 0 | 46.101 | no mismatch |
| e6_september_orders | wrong 1 | caught | 1 | 19.086 | caught |
| e6_september_orders | wrong 2 | caught | 1 | 19.121 | caught |
| e6_september_orders | equivalent 1 | no mismatch | 3 | 21.168 | no mismatch |
| e7_more_than_two_orders | wrong 1 | caught | 1 | 28.907 | caught |
| e7_more_than_two_orders | equivalent 1 | no mismatch | 3 | 25.493 | no mismatch |
| e8_never_paid | wrong 1 | caught | 1 | 17.892 | caught |
| e8_never_paid | wrong 2 | caught | 1 | 17.352 | caught |
| e8_never_paid | equivalent 1 | no mismatch | 3 | 17.137 | no mismatch |

## Interpretation and reproduction

### Explicit E5 follow-up

The primary run's E5 equivalent query produced no verified model candidates
after 46.101 seconds. It remains unmeasured in the table above. One separate,
explicit follow-up at **2026-10-04 13:22:46 UTC** returned **PASSED**, with three
SQLite-verified model candidates in **23.904 seconds** and no false positive.
Independent fuzzing also passed all 400 candidates. The primary report was not
overwritten; sanitized follow-up evidence is `.cache/hosted-e5-followup.json`.

Across the primary run and this one follow-up, all **14 wrong queries** and
**eight equivalent alternatives** received verified model stress candidates:
14/14 wrong queries were exposed, and there were **0/8 false positives**.
This required **23 model attempts**, including one unsuccessful primary call.
These are combined coverage figures, not a claim that the first 22 calls all
succeeded. The adapter itself performed no automatic retry.

This small, authored catalog is a regression measurement, not a general SQL accuracy guarantee. Model generation is stochastic. A passing query has survived a finite search, not been proven correct. Latencies include sample verification and shrinking, but exclude the pause between cases. Provider availability and free-tier quotas can change.

Run `scripts/eval_hosted.py` using the instructions in [the deployment guide](docs/hosted-demo.md). The sanitized machine-readable report for this run is stored locally at `.cache/hosted-evaluation.json`. No credentials, query text or raw provider errors appear in this report.
