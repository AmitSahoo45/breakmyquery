# BreakMyQuery Implementation Plan

> Use superpowers:executing-plans with independent tasks delegated in parallel.

**Goal:** Build the local SQL counterexample tutor described in `plan/BreakMyQuery_Build_Spec.md`.
**Architecture:** Streamlit invokes an in-memory SQLite verifier, model candidate generation and seeded random fuzzing, then row-deletion shrinking. A local SQLite journal remembers attempts. Model explanations never receive reference SQL.
**Tech stack:** Python 3.13, SQLite, Streamlit, pandas, Pydantic v2, Ollama.
**Spec:** `plan/BreakMyQuery_Build_Spec.md` (authoritative).

## Global constraints and rulings

- User explicitly requested checking the supplied build spec and starting implementation; its opening says to build and ask only for blockers.
- Use this actual D: workspace rather than the stale `D:\Projects\breakmyquery` location. All project-controlled writes, install caches and temporary build files remain under this repository. No app temporary files.
- Work directly on `main`, as explicitly requested by the user. There is no existing code/branch requiring a second worktree. The initial unborn feature branch was renamed to `main`.
- Implement and verify phase by phase. Only the user commits and pushes to GitHub, after their review. The agent must not commit, push, or create feature branches.
- Local inference only. Default `gemma4:e4b`, context 8192. Do not pull models.
- Never show a corrected query or reference SQL. SQLite decides verdicts. Offline mode remains fully usable.
- Honest wording: passed stress tests do not prove correctness; greedy shrinking is row-minimal, not globally smallest.
- E1 demo also needs counting the nullable order id after changing the join.
- First review checkpoint combines Tasks 1–2 (foundation, core engine and validated exercises). Then pause for the owner's review and commit; see `plan/progress.md`.
- Verified pool tuning: random order counts `[0,5]` instead of `[0,6]` avoid E5's single-row-shrink local minimum exceeding six total rows. Sample/trap fixtures and shrink algorithm stay as specified.

## Review focus

- SQL comments inside literals and bounded recursive/output-heavy queries: database tests.
- Model SQL leaks in any visible field and unsafe INSERTs: model boundary tests.
- Gemma unavailable, invalid JSON, and timeouts: model and hunter tests.
- Reference and trap datasets never passed to learner-visible outputs or used for hunting: hunter/UI tests.
- Journal writes and Streamlit reruns: config/journal and application tests.

### Task 1: Runtime and core engine

Files: requirements, configuration, `bmq/db.py`, `compare.py`, `fuzz.py`, `shrink.py`, and their tests.
Interfaces: `Result(columns, rows)`, `build_db(dataset)`, `run_query(conn, sql, timeout_s)`, `validate_learner_sql(sql)`, `dump_dataset(conn)`, `compare.equal(expected, actual, order_matters=False)`, `diff(expected, actual)`, `generate(rng, pools)`, `shrink(dataset, still_fails)`.
- [x] Write and run failing safety/comparison/shrink tests.
- [x] Implement read-only, bounded SQLite execution, bag comparison, valid deterministic fuzz datasets and constraint-preserving row shrinking.
- [x] Run `.venv\Scripts\python.exe -m pytest tests/test_db.py tests/test_compare.py tests/test_shrink.py`; expect all pass. Full suite also passed: 85 tests.

### Task 2: Exercises and validator

Files: `data/schema.sql`, `exercises.json`, `fuzz_pools.json`, `scripts/validate_exercises.py`.
Consumes Task 1 database and comparison interfaces. Produces eight exercises with all fields from the spec.
- [x] Author all samples, traps, 14 known-wrong queries and eight alternatives.
- [x] Validator checks constraints, sample equivalence, trap divergence, equivalent queries and column counts.
- [x] Run `.venv\Scripts\python.exe scripts/validate_exercises.py`; eight valid exercises verified.

### Task 3: Model boundary and hunter

Files: `bmq/llm.py`, `hunter.py`, model/hunter tests, `scripts/eval_hunters.py`.
Consumes core and data. Produces spec Verdict; `check(exercise, learner_sql, progress_cb=None, *, settings=None, seed=42)`.
Settings: immutable dataclass in `bmq/config.py`, fields model, ollama_host, hunt_order (tuple), gemma_rounds, fuzz_max, fuzz_seconds, query_timeout, data_dir, ollama_timeout. `get_settings()` reads environment; `ROOT` is repository path.
Model: spec signatures plus optional `settings`; `candidate_dataset(candidate)` verifies INSERTs, `model_available(settings=None)` reports availability. `Explanation.hint` may be None. All visible prose passes leak guard.
- [ ] Write failing offline, malformed model output, leakage, candidate verification and full seeded hunter tests.
- [ ] Implement propose/verify/shrink with honest counts and explicit unavailable-model status.
- [ ] Run hunter/model tests; all 14 wrong queries caught, all eight alternatives pass, six rows maximum per counterexample.
- [ ] Generate eval report; Gemma unavailable is reported as unavailable, never a measured success.

### Task 4: Practice app and journal

Files: `app.py`, `bmq/journal.py`, `tests/test_app.py`, journal/config tests.
Consumes verdict/model interfaces. Background worker returns explanations; it never calls Streamlit. Journal API: `log_attempt(exercise_id, learner_sql, verdict, explanation=None, *, settings=None) -> int`, `update_explanation(attempt_id, explanation, *, settings=None)`, `list_attempts(settings=None) -> list[dict]`.
- [ ] Write and run failing journal and Streamlit interaction tests.
- [ ] Build exercise sidebar, sample/schema, SQL editor, proof before hints, status stages and My traps with retry.
- [ ] Verify E1 offline through AppTest; verify live model when available. Every run logs exactly once.

### Task 5: Delivery

Files: README, MIT LICENSE, eval report, PowerShell setup/run scripts.
- [ ] Document setup, model terms, XData attribution, measured evaluation and known limitations.
- [ ] Run full pytest suite, exercise validator, eval and Streamlit startup check.
- [ ] Independent final review; fix material findings and repeat affected verification.
- [ ] Leave verified work on `main` for user review and user-owned commits/pushes; report any unavailable live checks.
