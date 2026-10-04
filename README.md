# BreakMyQuery

A SQL practice tutor that finds small datasets which break your query. Inspect the evidence and work out the repair yourself. Eight SQLite exercises cover joins, NULLs, aggregation, ties, arithmetic, dates and anti-joins. Run locally with Ollama or preview the public-demo entrypoint with hosted Gemma 4.

The hosted **Gemma 4** evaluation catches **14/14 deliberately wrong queries**, with **0/8 false positives** across equivalent alternatives. One equivalent case needed a separate follow-up after the primary call returned no usable output; [the Gemma API report](eval_results_gemma_api.md) preserves both results. The earlier local trial caught **9/14 with Llama 3.2**; seeded fuzzing caught **14/14**, with **0/8 false positives**. See [Llama trial results](eval_results_llama32.md), [build progress](plan/progress.md) and [the local demo guide](docs/demo.md).

**Use evidence-only mode for the Llama demo.** Live checks found incorrect hints and mistake classifications from this model. Set `BMQ_MODEL_HINTS=false` as shown below; SQLite-verified counterexamples, results, history and Retry remain available.

## Challenge submission

Prepared for the [Hacktoberfest Weekend Challenge: Build for a Friend](https://dev.to/challenges/hacktoberfest-weekend-2026-10-01). The submission deadline is **5 October 2026 at 12:29 pm IST (06:59 UTC)**. The official rules accept a deployed demo **or a video**, plus a code link. The verified AI demonstration uses local Llama 3.2 dataset proposals; a fuzz-only recording does not demonstrate that model path.

See the [submission readiness review](docs/submission-readiness.md) and [DEV post draft](docs/dev-submission-draft.md). The [code repository](https://github.com/AmitSahoo45/breakmyquery) is public. A deployed demo/video link and the friend's actual problem still need to be added before publication. Real feedback and resulting changes are optional additions to strengthen the write-up. The draft is not a published entry.

Any commits made after the challenge deadline must be listed here with their hashes, dates and a description of what changed. The local commits reviewed on 4 October are within the entry period; this statement does not verify when a GitHub repository was created.

## Windows setup

Keep this checkout on D: at `D:\Projects\24-HacktoberFest-2026\01-Launch-Week-Challenge`. Use Python 3.11 or newer; development uses Python 3.13. From the repository root in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Setup creates `.venv`, sends installation temporary files and pip's cache to `.cache`, installs `requirements-lock.txt`, and checks dependencies. It does not install Ollama or download models. `requirements.txt` records supported dependency ranges. If setting up manually, establish repository-local paths before creating the environment:

```powershell
New-Item -ItemType Directory -Force -Path .cache\tmp, .cache\pip | Out-Null
$env:TEMP="$PWD\.cache\tmp"; $env:TMP=$env:TEMP; $env:PIP_CACHE_DIR="$PWD\.cache\pip"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

To install supported ranges instead of pinned versions, after the same path initialization:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the app with its repository-local launcher:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Open `http://127.0.0.1:8501`. Stop with Ctrl+C. Streamlit arguments are forwarded, for example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 --server.port=8502
```

The direct local entry point is `.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1`. Use the launcher above to initialize repository-local temporary, profile and cache paths and enforce loopback binding before Streamlit starts.

To use only fuzzing for counterexample hunting:

```powershell
$env:BMQ_HUNT_ORDER='fuzz'; powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

`BMQ_HUNT_ORDER` controls hunting; the app can still check local model availability and offer optional model explanations when online. With Ollama stopped, fuzzing remains usable and hints are unavailable. The default `gemma,fuzz` search also continues with fuzzing when the configured model is unavailable. The internal `gemma` mode name means the configured local model, including Llama; it is retained for compatibility. Explicit hunter API/evaluation `gemma`-only runs stay model-only; the app uses fuzzing when its model status is offline. Clear a previous fuzz-only override before returning to the default:

```powershell
Remove-Item Env:BMQ_HUNT_ORDER -ErrorAction SilentlyContinue
```

## Hosted Gemma preview and deployment

Put one `GEMINI_API_KEY` in the ignored `.streamlit/secrets.toml`, then preview the public entrypoint:

```powershell
$env:BMQ_MODEL='gemma-4-26b-a4b-it'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -PublicDemo
```

This uses Google's API for open-weight Gemma 4 dataset proposals. SQLite verifies them on the app server; seeded fuzzing handles missed cases and provider failures. Hints and classifications remain disabled. Each visitor has an isolated in-memory history of up to 50 attempts, which can disappear on reconnect or restart. Submitted SQL is sent to Google; do not submit private information.

The single-key adapter has shared per-process admission limits, one active request and no automatic retries. It does not rotate accounts. Free API quotas are not a worldwide hosting permission: Google's terms require Paid Services for clients available to EEA, Swiss or UK users. Review the [deployment guide](docs/hosted-demo.md) before sharing a public link. No billing change or public deployment has been performed by the agent.

## Existing Llama 3.2 trial (no download)

The owner authorized testing the already-installed `llama3.2:latest` on 4 October 2026. This checkout includes a launcher for this machine's existing Docker Desktop Ollama image and `rag-ollama` source container. It copies only the selected model's existing manifest/blobs into `.cache/ollama/models`, checks newly copied blobs against their SHA-256 digests, and starts a separate GPU-enabled server on `127.0.0.1:11435`. It never pulls an image or model and leaves the original service on port 11434 running.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local-model.ps1 -Warmup
$env:BMQ_MODEL='llama3.2:latest'
$env:BMQ_OLLAMA_HOST='http://127.0.0.1:11435'
$env:BMQ_HUNT_ORDER='gemma,fuzz'
$env:BMQ_MODEL_HINTS='false'
$env:BMQ_DATA_DIR='.bmq/demo-llama32-evidence'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

`-Warmup` preloads the existing model with the app's 8192-token context before the app starts. The first CUDA initialization took about 111 seconds on this machine and exceeded the app's normal 45-second request timeout; warmup has its own bounded 240-second timeout. After warmup the live E1 model-only test passed in 25 seconds. An online status only confirms availability, not readiness or generation quality. See [Ollama's preload guidance](https://docs.ollama.com/faq#how-can-i-preload-a-model-into-ollama-to-get-faster-response-times).

The dedicated container has a read-only root filesystem, repository bind mounts for model/runtime/temp/profile data, and Docker logging disabled; the attached client's logs are in `.cache/ollama/runtime`. Docker Desktop still manages its own engine metadata. The launcher is specific to the existing local image, source container, GPU and Docker Desktop Linux engine; it is not a fresh-machine installer.

Check or stop only this project's server:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local-model.ps1 -Status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local-model.ps1 -Stop
```

The trial uses an explicit environment override; the code default remains `gemma4:e4b`. Model status and counterexample attribution show the configured model. Llama weights use the [Llama 3.2 Community License](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE).

This demo disables generated nudges, larger hints, error explanations and new mistake classifications. My traps hides historical model text and labels in this mode without deleting them. Each new Run still saves the submitted query, verdict and counterexample. The separate demo directory keeps the failed hint-quality trial out of the recording. To demonstrate only fuzzing with fast, seeded results, change `BMQ_HUNT_ORDER` to `fuzz`; keep hints disabled even while Ollama is online.

## Optional local Gemma

Use an existing local Ollama installation. Review [Gemma 4's official license](https://ai.google.dev/gemma/apache_2) before downloading or using its weights. The following commands are a user-run setup option; no model has been pulled as part of implementation.

Ollama's server process must receive the model-directory setting before it starts. A running desktop/tray server does not inherit environment changes in this shell. Stop that server first, then use a dedicated PowerShell terminal from the repository root:

```powershell
New-Item -ItemType Directory -Force -Path .cache\tmp, .cache\profile, .cache\appdata, .cache\localappdata, .cache\ollama\models | Out-Null
$env:TEMP="$PWD\.cache\tmp"; $env:TMP=$env:TEMP
$env:USERPROFILE="$PWD\.cache\profile"; $env:APPDATA="$PWD\.cache\appdata"; $env:LOCALAPPDATA="$PWD\.cache\localappdata"
$env:OLLAMA_MODELS="$PWD\.cache\ollama\models"; $env:OLLAMA_HOST='127.0.0.1:11434'
ollama serve
```

In a second repository-root terminal, initialize the same local paths and fetch/check the default model:

```powershell
$env:TEMP="$PWD\.cache\tmp"; $env:TMP=$env:TEMP
$env:USERPROFILE="$PWD\.cache\profile"; $env:APPDATA="$PWD\.cache\appdata"; $env:LOCALAPPDATA="$PWD\.cache\localappdata"
$env:OLLAMA_MODELS="$PWD\.cache\ollama\models"; $env:OLLAMA_HOST='127.0.0.1:11434'
ollama pull gemma4:e4b
ollama run gemma4:e4b "ping"
```

Then start `scripts\run.ps1`. The app defaults to `gemma4:e4b` with an 8192-token context. Once dependencies and model weights are present, inference and fuzzing run locally without internet access. See [Ollama's environment/model-directory guidance](https://docs.ollama.com/faq).

## How it works

1. **Propose:** run the learner query on the sample, then ask the configured model for edge-case datasets and generate seeded random datasets. Hunting does not use the authored trap fixtures.
2. **Verify:** SQLite executes the reference and learner queries on each accepted dataset. Result comparison preserves duplicate-row counts; column aliases do not affect equality. Model output never decides the verdict.
3. **Shrink:** greedily remove rows while preserving the mismatch and database constraints. The result is **row-minimal under deletion**, not guaranteed globally smallest.
4. **Explain:** show the breaking tables and differing result rows before optional nudges and hints. The explanation request receives the problem, learner query and evidence, without reference SQL. Visible model text is checked for query leakage; this does not establish factual accuracy. Set `BMQ_MODEL_HINTS=false` for evidence-only practice. When explanations are unavailable, the evidence remains usable with a clear hints-unavailable message.

**PASSED means no counterexample was found within the budget, not proof of correctness.** A sample mismatch is shown immediately. SQL errors and unsafe input are reported separately. The editor accepts one read-only SQLite query, with execution and result-size limits. Queries run against in-memory databases.

The **My traps** view stores attempts so you can revisit a mistake and retry it. In local mode, the SQLite journal includes your submitted SQL and evidence and persists between restarts. Public-demo mode uses isolated session memory instead.

## Measured evaluation

The [completed 4 October Llama evaluation](eval_results_llama32.md) covers **all 14 wrong queries and eight equivalent alternatives in both modes**, with no unmeasured cases. Completed E1–E2 measurements were retained from the earlier run; E3–E8 were rerun after the owner restarted Docker. The report records this history explicitly.

| Measurement | Llama 3.2 only | Fuzz only |
|---|---|---|
| Known wrong queries caught | 9/14 (64.3%) | 14/14 (100%) |
| False positives on equivalent alternatives | 0/8 | 0/8 |
| Median time per known wrong query | 31.910 s | 0.053 s |
| Verified stress datasets across the catalog | 80 | 3247 |

The combined union is **14/14**, with **0 evaluation errors**. Three model rounds returned no usable proposal; those failures remain in the diagnostics. Llama missed one NULL-comparison variant, join fanout, one date-boundary variant, duplicate-name grouping and one anti-join variant. This small catalog and its resumed-run timings are local measurements, not a general quality or performance guarantee.

Llama-only and fuzz-only are independent evaluation runs. Keep `BMQ_HUNT_ORDER=gemma,fuzz` for the trial app: SQLite verifies every candidate, and fuzzing can catch model misses. A model being online does not make its proposals or teaching explanations reliable.

**Hint-quality result: failed.** On E1's verified missing-customer counterexamples, Llama assigned grouping/counting categories instead of the demonstrated join/filter cause. Both live quality gates in `tests/test_live_tutor.py` failed. Prompt and response-format diagnostics did not establish a reliable correction, so those experimental prompt changes were discarded. The owner chose an evidence-only demo; generated hints and classifications are not accepted as demo-ready. See [live verification](docs/live-verification.md).

The checked-in [eval_results.md](eval_results.md), generated **2026-10-03 17:20:09 UTC**, reports seed 42, 400 fuzz datasets or five seconds per query, two Gemma rounds, a two-second query timeout and a 45-second Ollama timeout.

| Measurement | Gemma-only | Fuzz-only |
|---|---|---|
| Known wrong queries caught | N/A: local model unavailable | 14/14 (100%) |
| False positives on equivalent alternatives | N/A | 0/8 |
| Median time per known wrong query | N/A | 0.020 s |
| Rows in shrunk counterexamples | N/A | 1-5 |

For that historical local-Gemma run, the combined hit rate is **N/A** because both modes were not measured for every query. The available-mode union is 14/14. Timings include sample verification and shrinking; they describe that run, not a general performance guarantee. Fourteen wrong queries and eight alternatives are a small regression catalog. The later hosted Gemma verification is separate; generated teaching quality has not been accepted for either demo model.

## Verification

Before invoking Python directly, set temporary paths in the repository:

```powershell
New-Item -ItemType Directory -Force -Path .cache\tmp, .cache\profile | Out-Null
$env:TEMP="$PWD\.cache\tmp"; $env:TMP=$env:TEMP; $env:USERPROFILE="$PWD\.cache\profile"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts\validate_exercises.py
.\.venv\Scripts\python.exe scripts\eval_hunters.py --fuzz-only
```

The validator checks exercise constraints, sample agreement, trap divergence, equivalent alternatives and result widths. Pytest excludes tests marked `ollama` by default. Evaluation overwrites `eval_results.md` unless `--output` supplies another repository-local path; `--fuzz-only` does not contact Ollama. To evaluate both modes, run `scripts\eval_hunters.py` without that flag; an unavailable model is reported as unmeasured. Evaluation fails on false positives or errors. Its exit code alone does not establish model coverage or an acceptable hit rate; inspect the report's unmeasured cases and per-mode results.

With the configured model already available locally, run the live hunter test explicitly:

```powershell
.\.venv\Scripts\python.exe -m pytest -m ollama tests\test_hunter_fuzz.py
```

The human browser/demo checks are described in [docs/demo.md](docs/demo.md). A server startup check alone does not verify browser interaction or live model quality.

The separate live teaching-quality gates can be run with `-m ollama tests/test_live_tutor.py`. They currently fail with this Llama model and remain useful acceptance checks for a future model. They are excluded from the default offline suite, not marked as passing or expected failures.

## Configuration and local files

| Environment variable | Default |
|---|---|
| `BMQ_MODEL` | `gemma4:e4b` |
| `BMQ_OLLAMA_HOST` | `http://localhost:11434` (loopback only) |
| `BMQ_MODEL_PROVIDER` | `ollama`; public entrypoint forces `gemini` |
| `BMQ_PUBLIC_DEMO` | `false`; public entrypoint forces `true` for session-only history |
| `GEMINI_API_KEY` | Server-side secret, used only by the explicit Gemini provider |
| `BMQ_HUNT_ORDER` | `gemma,fuzz` |
| `BMQ_MODEL_HINTS` | `true`; set `false` for the approved evidence-only demo |
| `BMQ_GEMMA_ROUNDS` | `2` |
| `BMQ_FUZZ_MAX` | `400` |
| `BMQ_FUZZ_SECONDS` | `5` |
| `BMQ_QUERY_TIMEOUT` | `2` seconds |
| `BMQ_OLLAMA_TIMEOUT` | `45` seconds per request |
| `BMQ_DATA_DIR` | `.bmq` under this repository |

Data-directory overrides must stay inside the repository. Model requests disable inherited proxies and redirects. The launcher changes to the repository root, uses `.venv\Scripts\python.exe`, and sets `TEMP`, `TMP`, `PIP_CACHE_DIR`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `PYTHONPYCACHEPREFIX` and `OLLAMA_MODELS` to paths inside `.cache`. Python console output uses UTF-8. The checked-in `.streamlit/config.toml` controls headless, loopback startup, and usage statistics are disabled. Run it as the separate PowerShell process shown above so these environment changes remain scoped to the app process.

`OLLAMA_MODELS` and `PIP_CACHE_DIR` are configurable storage locations; this project's workflow requires them to remain within this D: checkout. The launcher fixes those paths locally, and optional Ollama commands do the same. `.venv`, `.cache` and `.bmq` are ignored by Git. The launcher does not relocate an already-running Ollama server or control unrelated software.

## Credits and license

Inspired by [XData at IIT Bombay](https://www.cse.iitb.ac.in/infolab/XData/XData.html), which generates datasets designed to expose SQL query mistakes. BreakMyQuery uses SQLite verification, fuzzing and optional model proposals.

Application code is licensed under [MIT](LICENSE). Model weights have their own license: Google's current [Gemma Terms of Use](https://ai.google.dev/gemma/terms) directs Gemma 4 users to the [Apache 2.0 Gemma 4 license](https://ai.google.dev/gemma/apache_2). If you override the model, check that model's applicable terms.

Work proceeds on `main` according to [plan/implementation.md](plan/implementation.md). The repository owner reviews, commits and pushes; agents do not commit or push.
