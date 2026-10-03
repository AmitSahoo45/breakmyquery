# Build progress

Workflow: work on `main`. The owner alone reviews, commits and pushes.
Spec: `plan/BreakMyQuery_Build_Spec.md`. Execution detail: `plan/implementation.md`.

## Phase 1: Foundation, SQLite engine and exercises

Completed and committed by the owner as `a9233a4` (`Phase 1 : add SQL engine and eight validated exercises`). Combines build-spec blocks 0–2.

- Environment: Python 3.13.7; `.venv` created under the actual D: workspace.
- Dependency installation complete; imports and `pip check` passed. Exact versions recorded in `requirements-lock.txt`.
- Local Ollama check: unavailable at `http://localhost:11434`; no model installed or pulled.
- All controlled install temporary files and pip cache redirected to `.cache` under the repository.
- Config tests: 2 passed (repository-relative data path and local host/path restrictions).
- Core engine and eight exercise datasets implemented.
- Full suite: `.venv\Scripts\python.exe -m pytest -q` — **85 passed**.
- Validator: `.venv\Scripts\python.exe scripts\validate_exercises.py` — **8 exercises, 14 known-wrong queries and 8 alternative queries validated**.
- Seed-42 integration: every known-wrong query exposed within 9 random datasets; largest shrunk counterexample 5 rows. Every E1 trap shrinks to at most 2 rows.
- All 8 alternative queries agree with their references across 400 seeded datasets.
- Streamlit configuration loaded and verified: telemetry false, headless true, bind address `127.0.0.1`.
- Independent review checked configuration/setup, exercises with raw SQLite, and core behavior. CTE authorization and catalog-count access issues were fixed and regression-tested; no Important/Critical findings remain.

### Ruling: order-count pool

Changed only the random pool's maximum order count from 6 to 5. A six-order cancellation-rate counterexample can be irreducible under the specified single-row shrink algorithm: removing one row makes a denominator of 5, giving an integer percentage and hiding the bug. With its parent rows, it exceeded the six-row acceptance bound. The adjusted pool meets the bound for all 14 seeded regression queries. Exercise sample/trap fixtures and the shrink algorithm are unchanged.

### Review scope

- Environment/setup: `.gitignore`, `.streamlit/config.toml`, `requirements.txt`, `requirements-lock.txt`, `pytest.ini`, `scripts/setup.ps1`.
- Engine: `bmq/config.py`, `db.py`, `compare.py`, `fuzz.py`, `shrink.py`.
- Content and validation: `data/`, `scripts/validate_exercises.py`, `tests/`.
- Workflow/docs: `AGENTS.md`, `README.md`, `LICENSE`, this progress record and implementation plan.

The hunter test draft was restored for Phase 2. Future journal test drafts remain in ignored `.cache/deferred-phase2/` until the UI/journal phase.

## Phase 2: Model integration, hunter and evaluation

Implemented and ready for owner review, with live Gemma validation pending. Base commit: `a9233a4`. Phase 1 baseline rerun: **85 passed**. All work remains on `main`; the owner alone commits and pushes.

- Model boundary: Pydantic structured responses, local Ollama with finite timeouts, safe INSERT candidates, guarded explanations. Real Ollama client serialization is tested with mocked HTTP transport.
- Hunter: sample → configured Gemma/fuzz order → verify → shrink; never reads authored trap/known-answer fixtures.
- Evaluation: separate Gemma-only and fuzz-only results, known-wrong hit rates, known-correct false positives, and explicit unavailable/no-verified-candidate coverage.
- Interfaces checked: `Settings` matches both model and hunter; `Result`, `Diff`, `generate` and `shrink` match the core APIs; evaluation consumes the shared `Verdict` and statistics.
- Ruling: only successfully compared datasets count in `gemma_candidates`/`fuzz_tries`; `fuzz_attempts` and `skipped_candidates` preserve accounting for rejected/errored candidates.
- Ruling: model INSERTs may be restricted to literal `VALUES` and executed with parameters to exclude executable expressions while retaining the specified candidate format.
- Local model preflight: localhost:11434 refused the connection; `D:\Ollama` absent. No models installed/pulled. Live verification remains pending availability; the explicitly marked live test was not run.

### Phase 2 verification

- `.venv\Scripts\python.exe -m pytest -q` — **172 passed, 1 deselected** (the live Ollama test).
- `.venv\Scripts\python.exe scripts\validate_exercises.py` — all **8 exercises, 14 wrong queries and 8 alternatives** validate.
- `.venv\Scripts\python.exe scripts\eval_hunters.py` — wrote `eval_results.md`; **14/14 fuzz hits**, **0/8 false positives**, **0 evaluation errors**, maximum **5 rows**. All eight alternatives completed 400 stress tests each.
- Gemma-only and full combined hit rates are **N/A (unavailable)**. They were not measured or replaced with fuzz-derived scores.
- Default E1 offline smoke check returned `HIDDEN_BUG`, `found_by=fuzz`, after 2 stress tests: one customer with no orders; learner result empty, expected count 0.
- Final independent review: **87 phase-2 tests passed, one live test deselected**; no remaining Important/Critical findings.
- Review fixes: exclude zero-verification runs from coverage; preserve sample mismatch/error accounting; catch valid `VALUES` queries in every model-text/data-cell guard; replace ambiguous comment matching with linear scanning and a bounded subprocess regression.
- `git diff --check` passed. No agent commits, pushes or branch changes.

### Phase 2 review scope

- `bmq/llm.py`, `bmq/hunter.py`.
- `scripts/eval_hunters.py`, `eval_results.md`.
- `tests/test_llm.py`, `tests/test_hunter.py`, `tests/test_hunter_fuzz.py`, `tests/test_eval_hunters.py`.
- README, implementation plan and this progress record.

Stop at the Phase 2 review checkpoint. Streamlit and journal stay in Phase 3. Live Gemma verification remains an explicit outstanding check once the local service/model is available.

## Later phases

3. Streamlit practice UI, hints and local trap journal.
4. Full app verification, documentation and final evaluation.

No commits or pushes have been made by the agent.
