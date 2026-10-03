# BreakMyQuery

A local SQL practice tool that tests your query against small datasets and shows what breaks. You work out the fix yourself.

**Build status:** Phase 2 is implemented and ready for review: the local Gemma boundary, counterexample hunter and evaluation. The suite passes **172 tests**; one live-model test is excluded by default. Live Gemma validation remains pending because Ollama was unavailable. The practice UI and trap journal are Phase 3. See [build progress](plan/progress.md) and the [build spec](plan/BreakMyQuery_Build_Spec.md).

## Windows setup

Keep the repository on D: and use Python 3.11 or newer. From the repository directory in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The setup script creates `.venv`, routes installation temporary files and pip's cache to `.cache`, installs the exact versions in `requirements-lock.txt`, and checks the dependencies. Nothing is installed globally. `requirements.txt` records the supported dependency ranges.

To install the supported ranges into an existing environment, with local install/cache paths:

```powershell
$env:TEMP="$PWD\.cache\tmp"; $env:TMP=$env:TEMP; $env:PIP_CACHE_DIR="$PWD\.cache\pip"; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Verify the foundation

```powershell
.\.venv\Scripts\python.exe scripts\validate_exercises.py
```

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The validator checks sample/trap constraints, deliberately wrong queries that pass the samples, equivalent queries, and expected result widths. The engine compares result bags (including duplicate rows), generates seeded datasets and removes rows while preserving a failure and database constraints.

Verified foundation: **85 tests pass**. Seed-42 random testing exposes all 14 deliberately wrong queries with counterexamples of at most five rows, while all eight alternative queries agree with their references across 400 generated datasets. This is regression evidence, not proof that an arbitrary query is correct.

SQLite query databases live in memory. The query runner accepts one read-only query and applies execution and result-size limits. Greedy shrinking finds a **row-minimal** counterexample, not necessarily the smallest possible dataset.

## Hunt and evaluate

The hunter runs your query on the sample first. If it matches, Gemma proposes edge-case datasets and random fuzzing supplies independent stress tests. SQLite compares each result with the reference; a verified mismatch is shrunk before it is returned. The explanation call receives the problem, your query and the evidence, without the reference SQL. Hints never provide a corrected query.

The default search order is `gemma,fuzz`. If local Gemma is unavailable, the default search continues with fuzzing. Explicit `gemma`-only runs stay model-only so evaluations cannot misattribute a fuzz result to Gemma. `PASSED` means no counterexample was found within the configured budget; it does not prove correctness.

Run both evaluators, using Gemma only if the configured model is available locally:

```powershell
.\.venv\Scripts\python.exe scripts\eval_hunters.py
```

For deterministic fuzz evaluation without contacting Ollama:

```powershell
.\.venv\Scripts\python.exe scripts\eval_hunters.py --fuzz-only
```

The script writes [eval_results.md](eval_results.md). It tests every deliberately wrong query and every known equivalent query, reports row counts and timings, and exits unsuccessfully if it detects a false positive or an evaluation error. Unavailable Gemma results and runs with no verified candidates are marked as not measured. The combined hit rate is the union of separate runs, not a benchmark of combined execution time.

Latest measured results: fuzzing caught **14/14** hidden mistakes with **0/8** false positives on equivalent alternatives. Counterexamples contain **1–5 rows**. Gemma and the combined hit rate are **N/A**, because the local model was unavailable; the report includes exact budgets and timings.

The hunter API is `check(exercise, learner_sql, progress_cb=None, *, settings=None, seed=42)`. Progress stages are `sample`, `gemma`, `fuzz`, and `shrink`. Its verdict includes evidence, a diff and statistics. Only datasets on which both queries completed successfully count toward `gemma_candidates` and `fuzz_tries`; attempted and skipped datasets are recorded separately.

Model-dependent tests are excluded from the default suite. Once local Ollama has the configured model, run the live E1 check explicitly:

```powershell
.\.venv\Scripts\python.exe -m pytest -m ollama tests\test_hunter_fuzz.py
```

## Local configuration

`bmq/config.py` reads `BMQ_MODEL`, `BMQ_OLLAMA_HOST`, `BMQ_HUNT_ORDER`, `BMQ_GEMMA_ROUNDS`, `BMQ_FUZZ_MAX`, `BMQ_FUZZ_SECONDS`, `BMQ_QUERY_TIMEOUT`, `BMQ_DATA_DIR`, and `BMQ_OLLAMA_TIMEOUT`.

The model default is `gemma4:e4b`, with an 8192-token context. Ollama must use a loopback URL; proxy inheritance and redirects are disabled. `BMQ_OLLAMA_TIMEOUT` defaults to 45 seconds per model request. App data defaults to `.bmq` relative to the repository, independent of the current working directory; overrides must remain inside this repository. No model is downloaded by setup. Streamlit's checked-in configuration disables usage statistics and enables headless startup.

Model-proposed data uses literal `INSERT ... VALUES` statements targeting the four exercise tables. Executable expressions and multi-statement SQL are rejected. Accepted rows are loaded with parameters, constraints and size limits. Malformed model output, connection failures or unsafe candidates cannot decide a verdict; the database remains the verifier.

## Review workflow

Implementation happens on `main`, phase by phase. The repository owner reviews, commits and pushes each phase. Agents do not create commits or push.

The application code is licensed under [MIT](LICENSE).
