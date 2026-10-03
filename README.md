# BreakMyQuery

A local SQL practice tool that tests your query against small datasets and shows what breaks. You work out the fix yourself.

**Build status:** Phase 1 is ready for review: the environment, eight exercises and SQLite engine. The Gemma hunter, practice UI and trap journal are later phases. See [build progress](plan/progress.md) and the [build spec](plan/BreakMyQuery_Build_Spec.md).

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

## Local configuration

`bmq/config.py` reads `BMQ_MODEL`, `BMQ_OLLAMA_HOST`, `BMQ_HUNT_ORDER`, `BMQ_GEMMA_ROUNDS`, `BMQ_FUZZ_MAX`, `BMQ_FUZZ_SECONDS`, `BMQ_QUERY_TIMEOUT`, `BMQ_DATA_DIR`, and `BMQ_OLLAMA_TIMEOUT`.

The model default is `gemma4:e4b`. Ollama must use a loopback URL. App data defaults to `.bmq` relative to the repository, independent of the current working directory; overrides must remain inside this repository. No model is downloaded by setup. Streamlit's checked-in configuration disables usage statistics and enables headless startup.

## Review workflow

Implementation happens on `main`, phase by phase. The repository owner reviews, commits and pushes each phase. Agents do not create commits or push.

The application code is licensed under [MIT](LICENSE).
