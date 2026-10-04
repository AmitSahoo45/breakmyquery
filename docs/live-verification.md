# 4 October 2026 verification

The owner approved an **evidence-only demo** after the existing Llama model failed teaching-quality checks. Counterexample generation, SQLite verification, shrinking, history and Retry are the accepted demo scope. Generated hints and mistake classifications are disabled in the demo; their quality gate did not pass.

## Model and catalog

- Existing `llama3.2:latest`, 3.2B Q4_K_M, Ollama 0.15.1, loopback endpoint `127.0.0.1:11435`.
- Model manifest: `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`.
- The owner restarted the existing container. The project's `start-local-model.ps1 -Warmup` completed successfully against it. No model or image was downloaded.
- [Completed catalog report](../eval_results_llama32.md): Llama **9/14**, fuzz **14/14**, false positives **0/8 per method**, no unmeasured cases, zero evaluation errors. Three model rounds returned no usable proposal.
- Completed E1–E2 measurements were retained; E3–E8 were rerun in full after the restart, using the same model and budgets. Timings are from a resumed evaluation, not a single uninterrupted benchmark.

## Teaching quality: failed

The real model was given a verified, shrunk E1 dataset with one customer, Meera, and no orders. The learner returned no rows; the expected output contained Meera with a count of zero.

Both cases in `tests/test_live_tutor.py` failed with the production prompt: the inner-join and outer-join/WHERE variants received incorrect `GROUP_BY_GRAIN` classifications and explanations. The original browser trial also saved an incorrect grouping explanation into its journal. This proves that generation and persistence worked, but does not establish a useful tutor.

Additional prompt, field-order and plain-response diagnostics continued to produce incorrect claims or categories. These experimental prompt changes were discarded. There is no hard-coded exercise classifier or hidden reference query in the explanation path.

The two opt-in live quality tests remain failing acceptance gates for this Llama model. They are excluded by the normal `ollama` marker selection; they have not been weakened or marked as successful. A future model should pass them before generated teaching content is accepted. This is a scoped E1 result, not a quantified accuracy claim for every exercise.

## Evidence-only app

The browser session uses the normal launcher with:

```powershell
$env:BMQ_MODEL='llama3.2:latest'
$env:BMQ_OLLAMA_HOST='http://127.0.0.1:11435'
$env:BMQ_HUNT_ORDER='gemma,fuzz'
$env:BMQ_MODEL_HINTS='false'
$env:BMQ_DATA_DIR='.bmq/live-evidence-20261004'
```

The internal `gemma` mode/statistic names invoke the configured model. Visible attribution correctly identifies Llama. QA journals are separate from the clean recording directory in [the demo guide](demo.md).

Verified browser behavior:

- E1 inner-join mistake: a model-generated, SQLite-verified one-customer counterexample; learner empty, expected count zero. Exactly one journal entry, with null classification/explanation.
- E1 outer-join/WHERE mistake: a second model-generated, SQLite-verified one-customer counterexample. The proof survives a model-status refresh. Exactly two entries, both unclassified.
- The sidebar displays **Evidence-only mode · model hints off**. No nudge, larger hint or model idea is offered. The model source caption does not invite a disabled nudge.
- My traps survives an app restart; Retry restores the saved query without adding another attempt. Evidence-only history groups the latest counterexample by exercise and hides historical model prose/categories without deleting stored data.
- A real-browser result-loss defect was fixed: exercise radio values now use stable titles, with status in separate captions. A regression reproduced changing labels before the fix.
- The equivalent E1 alternative reports **Passed sample + 406 stress tests**, with no breaking case. This count is verified model candidates plus fuzz datasets; it is not a proof of correctness. The browser wait helper initially reached its 25-second polling limit, then the same Run completed normally; it was not submitted twice.
- A query naming a missing table reports the SQLite error and offers no model error-explanation button. The four deliberate Runs produce exactly four rows: two hidden bugs, one pass and one error. All four have null model classification/explanation.
- A final app restart retains all four rows. My traps shows two saved counterexamples and restores the latest wrong query through Retry; the read-only journal assertion remains at four rows after navigation and Retry.
- No browser errors were reported. Proof and history screenshots were inspected in `.cache/browser-qa/`; the accepted-query input is not included in learner-facing documentation.

## Automated verification

- Full offline suite: **226 passed, 3 deselected in 39.54 seconds**. The deselected cases are the live hunter test and two live teaching-quality tests.
- Exercise validator: **8 exercises, 14 known-wrong queries and 8 equivalent alternatives validated**.
- Focused app/config checks: **20 passed**, including evidence-only request suppression, preserved model hunting, hidden historical explanations, per-exercise Retry and stable sidebar values.
- Scoped independent functional review found a history-grouping regression and confirmed the fix. No outstanding functional findings remained in that scope. The broader Phase 3/4 review is recorded in [progress](../plan/progress.md).

No security scan was run; the owner explicitly deferred it. No commits, pushes, feature branches or worktrees were created.

The QA browser and app process tree were closed after verification. The owner's model container was left running. Use [the demo launch commands](demo.md#preparation) to start a separate recording journal.
