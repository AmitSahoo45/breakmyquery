# E1 demo and acceptance checks

This is a recording guide and manual checklist. See [build progress](../plan/progress.md) for recorded browser and model evidence; a checklist alone does not establish that a gate passed. The original Gemma evaluation remains historical and unmeasured for that model.

## Preparation

Run [Windows setup](../README.md#windows-setup) once. For the approved Llama evidence-only demo, run these commands from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local-model.ps1 -Warmup
$env:BMQ_MODEL='llama3.2:latest'
$env:BMQ_OLLAMA_HOST='http://127.0.0.1:11435'
$env:BMQ_HUNT_ORDER='gemma,fuzz'
$env:BMQ_MODEL_HINTS='false'
$env:BMQ_DATA_DIR='.bmq/demo-llama32-evidence'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Open `http://127.0.0.1:8501`. Confirm **Evidence-only mode · model hints off** in the sidebar. SQLite verifies every proposed dataset. The displayed source identifies whether Llama or fuzzing found the counterexample. The model search can take roughly a minute or longer; wait for **Run finished** instead of clicking Run again. A fast recording can use `BMQ_HUNT_ORDER=fuzz` while retaining `BMQ_MODEL_HINTS=false`.

Llama's live explanation/classification quality checks failed. This demo deliberately omits generated hints and mistake labels; see [the verification record](live-verification.md). Previous journals are preserved. Use a new repository-local `BMQ_DATA_DIR` when you want an empty history.

For a completely offline session, stop your local model service separately and use:

```powershell
$env:BMQ_HUNT_ORDER='fuzz'; $env:BMQ_MODEL_HINTS='false'; $env:BMQ_DATA_DIR='.bmq/demo-offline'; powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Select **Paid orders per customer** in **Practice**. The internal `gemma` hunt mode invokes the configured model, including Llama; it does not change the visible model attribution.

## Two-minute walkthrough

1. Show the question, schema and sample tables. Every sample customer has a paid order, so the sample alone misses an important edge case.
2. Enter this deliberately wrong query and click **Run**:

   ```sql
   SELECT c.name, COUNT(*) AS paid_orders
   FROM customers c JOIN orders o ON o.customer_id = c.id
   WHERE o.status = 'paid'
   GROUP BY c.id, c.name;
   ```

   This is an intentionally incorrect starting point, not a solution. It matches the sample, then seeded fuzzing finds a customer with no paid orders who disappears from the learner result.
3. Show **The breaking case**, the learner/expected result tables, and the missing/extra row markers. The expected output is evidence, not reference SQL. Explain that the displayed case has been shrunk while preserving the mismatch; it is row-minimal under deletion.
4. Show **Model hints are off** and reason from the tables. There is no generated nudge or larger hint in this demo.
5. Describe the conceptual repair without displaying a corrected query: preserve customers without matching paid orders, apply the paid-order restriction without discarding preserved customers, and count matched nullable order identifiers so the preserved empty match contributes zero. All three ideas matter; changing only the join still leaves filtering and counting pitfalls. Let the learner make the edits privately, then show their next verdict and stress-test count.
6. Open **My traps**, inspect the **Evidence only** counts and latest counterexample for each exercise, and use **Retry** to return its saved wrong query to the editor. New attempts have no model classification. Opening this page or using Retry does not add another Run.
7. Say what a pass means: no counterexample was found in this run's budget. It does not prove correctness. Once dependencies and any model are available locally, repeat with networking off to demonstrate local operation.

Do not open `data/exercises.json` during a learner-facing recording: it contains author reference queries and fixtures. Do not reveal a corrected query in the UI, hints, terminal capture or video.

## Manual verification gates

| Check | Passing observation |
|---|---|
| Offline startup | App loads with Ollama stopped and `BMQ_HUNT_ORDER=fuzz` |
| E1 hidden mistake | Incorrect query above passes sample, then shows a concrete smaller mismatch |
| Evidence before hints | Breaking tables and marked differing rows are visible before any nudge |
| Evidence-only demo | Model hints are off; no generated hint, idea, error explanation or mistake label is shown |
| Error handling | Invalid or write SQL produces an error; app remains usable |
| Journal | Each Run adds one attempt; opening hints or rerunning the page does not duplicate it |
| Retry | Saved exercise and learner SQL return to Practice without an automatic new run |
| Restart | Demo attempts remain in My traps after stopping and restarting the app |
| Live configured model | Model status is online; proposal work is observed; source and counts are honest; teaching quality is reported separately |
| Model unavailable | Default mode continues with fuzz and preserves evidence; unavailable hints are clearly reported |
| Privacy | No reference/corrected query appears in visible output; browser and model connect locally |

Record the command, model/version, seed/budgets, result source, any failure and the observed result when completing these gates. Live model validation is separate from automated mock-model tests and from Streamlit server startup.
