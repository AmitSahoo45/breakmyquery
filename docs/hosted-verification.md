# Hosted-provider verification, 4 October 2026

This records both the local public-entrypoint verification and the later
signed-out browser checks of the deployed Streamlit Community Cloud app.

## Implemented behavior

- Explicit Gemini provider with `gemma-4-26b-a4b-it`, one server-side project key,
  one generation per Run, no repair retries and no generated teaching content.
- Process-wide admission control: one active request, six requests/rolling
  minute, 12,000 conservatively estimated input tokens/minute and 1,000
  requests/rolling day. Provider 429 responses start a shared cooldown.
- Known model IDs and fixed HTTPS endpoint; key sent in a header. Response size
  is bounded, complete output is required, and proposals must pass Pydantic
  validation followed by the existing literal-data loader and SQLite verifier.
- Gemini's observed whole-response Markdown JSON wrapper is accepted. Extra
  prose, incomplete output and invalid schemas still fail without a repair call.
- A separate `cloud_app.py` forces model-plus-fuzz order, evidence-only mode and
  visitor-local in-memory journals capped at 50 attempts. No public journal
  database or background classification writer is used.
- The ordinary `app.py` defaults retain local Ollama and the persistent journal.
  The Windows launcher supports `-PublicDemo` and binds locally to loopback.

## Automated evidence

The integrated offline suite passed **287 tests**, with the three existing
opt-in Ollama live tests deselected. External Gemini HTTP calls are blocked by
the offline fixture; provider tests use fake keys and mocked transports.

Coverage includes API errors, redirects, timeouts, oversized input/output,
incomplete/invalid JSON, exact JSON fences, no retry, disabled explanations,
shared minute/day/concurrency limits, context-isolated notices, two separate
Streamlit sessions, rerun/Retry behavior and preservation of local journals.

After moving the local bind address into the launcher, the **16 launcher and
evaluator tests passed**. The validator confirmed **eight exercises, 14 wrong
queries and eight equivalent alternatives**.

An independent functional review found a public entrypoint configuration that
could inherit model-only hunting and lose fuzz fallback. The entrypoint now
forces `gemma,fuzz`; its AppTest regression passes. Focused re-review reported
no remaining blocking findings. This was not a security scan.

## Live model evidence

An actual model-only E1 request returned a one-customer counterexample:
**HIDDEN_BUG**, `found_by=gemma`, one verified model candidate, zero fuzz attempts,
one retained row, **15.978 seconds**. No reference/known-wrong/trap collection
was sent as an answer fixture; only the schema, question and compared queries
were provided. Sanitized local smoke output is `.cache/gemini-e1-smoke.json`.

The [paced full-catalog evaluation](../eval_results_gemma_api.md) caught
**14/14 wrong queries with Gemma**, with no false positives among **seven
measured equivalent alternatives**. The E5 equivalent case produced no usable
model output after 46.101 seconds and remains **unmeasured in that primary run**.
Fuzzing caught **14/14**, with **0/8 false positives**. Neither method reported
an evaluation error. Zero verified candidates do not count as successful passes.

One explicit E5 follow-up returned **PASSED**, three verified model candidates,
23.904 seconds and no false positive. Across that follow-up and the primary run,
Gemma measured all **14 wrong queries and eight equivalent alternatives**, caught
14/14 and produced 0/8 false positives. This took 23 model attempts, including
the unsuccessful primary E5 call; the original report remains unchanged.

## Browser and local-launch evidence

The real browser made exactly one model Run through `cloud_app.py`. Gemma
proposed a customer, Alice, with no orders. SQLite returned an empty learner
result and the expected Alice/zero-count row. The source caption named
`gemma-4-26b-a4b-it`; generated hints were absent.

- The sidebar said **Model configured**, without asserting API health from key
  presence. Google processing and session-only last-50 history were disclosed.
- Refreshing model configuration retained the displayed proof. My traps showed
  exactly one attempt, and Retry restored its SQL.
- A fresh browser tab had empty SQL and history; the original tab retained its
  attempt. The five pre-existing disk journals had unchanged file metadata.
- No browser errors were reported. The inspected full proof screenshot is
  `.cache/hosted-qa/model-proof.png`.
- After the bind-setting change, the launcher was restarted and its listening
  socket was verified as **127.0.0.1:8506**; the health endpoint returned HTTP 200.

The QA browser and both successive QA server process trees were closed. The
owner's local model container was not stopped or changed.

## Publication status

An unauthenticated request to GitHub's repository API returned HTTP 200,
`private=false`, `fork=false` and default branch `main` for
[AmitSahoo45/breakmyquery](https://github.com/AmitSahoo45/breakmyquery).
Its creation timestamp is 4 October 2026, 07:20:09 UTC. The owner subsequently
pushed the hosted implementation as commit `38365cd` and deployed the app.
The new documentation and evaluation reports still need owner review and push;
their public GitHub links returned 404 during the deployed-app review.

No Google billing change, agent commit or agent push was performed. The owner
deferred the security scan, which was not run. Public reachability does not
establish resolution of Google's regional service condition documented in
[the deployment guide](hosted-demo.md). Generated hints/classifications remain
disabled; successful proposals do not establish teaching quality.

## Deployed browser verification: 4 October, approximately 13:38–13:41 UTC

URL: **[breakmyquery.streamlit.app](https://breakmyquery.streamlit.app/)**.
The app loaded in the verification browser without a Streamlit or GitHub login.
The initial automation wait targeted the top-level document while Community
Cloud hosts the app in an iframe; the loaded app was then inspected and tested
through that iframe. This was an automation wait issue, not an app outage.

Exactly three synthetic Runs were submitted, including two model-generating
queries. There were no induced rate-limit tests or attempts to consume quota.

1. **Known E1 join mistake:** Gemma 4 26B A4B proposed Alice/New York with no
   orders. The displayed learner result was empty and the expected result was
   Alice with count zero. Attribution named `gemma-4-26b-a4b-it`, and hints stayed
   disabled. My traps displayed one saved counterexample.
2. **Equivalent E1 query:** the result was **Passed sample + 403 stress tests**,
   with no breaking case. This is finite-search evidence, not a SQL proof.
3. **Missing-table query:** the app displayed **Your query could not run** and
   SQLite's missing-table error without a generated explanation.

Retry restored the exact saved wrong query before the second Run. After the
passing/error Runs, My traps still contained the one counterexample. A new tab
had an empty editor, all exercises marked not run and an empty session history;
the original tab retained its saved counterexample. Browser error collection
was empty. The configured-model, Google processing and session-history notices
were present.

The deployed history screenshot was inspected at
`.cache/agent-browser/screenshots/screenshot-1791121258572.png`. Browser viewport
clipping means it is a verification artifact rather than a prepared submission
image. The verification browser was closed after these checks. No server-side
disk inspection, load test or security scan was performed during this deployed
smoke test, and the earlier full catalog numbers remain local API measurements.
