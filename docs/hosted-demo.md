# Hosted BreakMyQuery demo

This deployment uses Streamlit Community Cloud for the app and Google's Gemini API to serve the open-weight **Gemma 4** model `gemma-4-26b-a4b-it`. It does not need an Ollama server or model weights on the hosting machine. SQLite still verifies every proposed counterexample. Generated teaching hints and mistake classifications are disabled for this provider.

The owner deployed [BreakMyQuery](https://breakmyquery.streamlit.app). A signed-out browser check verified a real E1 Gemma counterexample: one customer, Alice in New York, no orders, empty learner output and expected Alice with count zero. The source caption identified Gemma and generated hints were disabled. The equivalent-query, SQL-error, saved-history, Retry and fresh-session checks also passed; see [hosted verification](hosted-verification.md) for their scope.

The hosted-provider code is public on `main` at `38365cd`. The latest anonymous repository check found `docs/`, `eval_results_gemma_api.md` and `eval_results_llama32.md` absent, so supporting links still return 404 until the owner reviews and publishes those files. The DEV entry remains unpublished.

## Account and API setup

Use one owner-controlled API project and one API key. Keep Cloud Billing disabled for the intended no-billing trial, and confirm the key's project is on the free tier in [Google AI Studio](https://aistudio.google.com/api-keys). Google currently lists Gemma 4 input and output as free of charge; project/model availability and quotas still apply. A Google AI Pro subscription is not required for this route and does not automatically increase a deployed API project's quota. [Gemma pricing](https://ai.google.dev/gemini-api/docs/pricing#gemma-4), [AI Pro versus API usage](https://ai.google.dev/gemini-api/docs/google-ai-plans)

The intended audience and billing arrangement remain unresolved. Google's current API terms permit API clients only in supported regions and require Paid Services for clients made available to users in the EEA, Switzerland or the UK. For the Gemini API, Paid Services require a project with an active billing account. The terms also require adult use. The live URL does not establish worldwide free-tier availability or approval to enable billing; hosting the app in the US does not resolve the end-user condition. [API terms](https://ai.google.dev/gemini-api/terms#use_restrictions), [available regions](https://ai.google.dev/gemini-api/docs/available-regions)

For unpaid API usage, Google may use prompts and responses to improve its products and may have them reviewed by people. The hosted app sends the exercise schema, question, submitted SQL and reference SQL to Google for dataset proposals. Use the synthetic exercises only; do not paste confidential SQL or personal data. The local Ollama workflow remains the option for keeping inference on the learner's computer. [Data handling terms](https://ai.google.dev/gemini-api/terms#unpaid-services)

## Local preview with the hosted provider

Store the key as a top-level TOML string in the ignored repository file `.streamlit/secrets.toml`, or supply `GEMINI_API_KEY` through the process environment. Never paste the key into source code, commands saved in a public guide, logs or screenshots. This is the file format, with a placeholder only:

```toml
GEMINI_API_KEY = "PASTE_YOUR_OWN_KEY_PRIVATELY"
```

From the D: repository root in PowerShell, explicitly replace any inherited Llama model selection, then run the project launcher:

```powershell
$env:BMQ_MODEL='gemma-4-26b-a4b-it'; powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -PublicDemo
```

The launcher keeps project-managed profiles, temporary files and caches under the repository. The public entrypoint forces `BMQ_MODEL_PROVIDER=gemini`, `BMQ_PUBLIC_DEMO=true`, one model round and disabled hints. No visitor API key is requested. Keep the ordinary `app.py`/Ollama setup for local practice.

## Deploy on Streamlit Community Cloud

Community Cloud is a free hosting service. Only the repository owner reviews, commits and pushes these files to GitHub, on `main`; an agent does not commit or push. Ensure the published branch includes `cloud_app.py`, `app.py`, `bmq/`, `data/`, `.streamlit/config.toml` and the dependency file. Keep `.streamlit/secrets.toml`, `.cache/`, `.venv/` and `.bmq/` out of Git. [Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)

1. Open [Streamlit Community Cloud](https://share.streamlit.io/) and create an app from the owner's GitHub repository.
2. Select branch **`main`** and entrypoint **`cloud_app.py`**.
3. In **Advanced settings**, select **Python 3.13** to match the verified local environment. Do not rely on the service's default Python version.
4. In the **Secrets** field, privately enter the top-level `GEMINI_API_KEY` TOML entry shown above. Do not place it under a section such as `[gemini]`.
5. Deploy and inspect the build log for dependency or startup failures. For a new deployment, verify the public page and model path as described below. [Deployment instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

The shared `.streamlit/config.toml` leaves server binding to the host. The Windows launcher sets `STREAMLIT_SERVER_ADDRESS=127.0.0.1` before starting Python, including public-demo previews. The deployed app's signed-out E1 interaction confirms that its page and interactive connection work with this arrangement. [Configuration precedence](https://docs.streamlit.io/develop/concepts/configuration/options), [platform configuration](https://docs.streamlit.io/deploy/streamlit-community-cloud/status#configuration)

Community Cloud controls some configuration, including setting usage statistics on, and hosts its apps in the US. Consequently the hosted demo must not claim the local workflow's offline or telemetry-free properties. [Platform limitations](https://docs.streamlit.io/deploy/streamlit-community-cloud/status)

## Budgets and session history

The provider adapter permits one request at a time per process, with up to **6 requests per rolling minute**, a conservative **12,000 input-token estimate per minute**, and **1,000 requests per rolling 24 hours**. The input estimate counts UTF-8 bytes plus overhead; it is not Google's actual tokenizer. A large request may be refused even when the provider would accept it. Calls that receive errors still consume the local admission allowance.

These are **process-local demo limits**, not authoritative Google project quotas or a billing cap. Multiple app processes and the evaluator do not share their counters; a process restart loses local counters. Do not restart processes, rotate keys, switch projects or retry requests to evade a provider allowance. Google can impose a lower effective quota. The adapter makes no automatic retries, and records a cooldown after a quota response. During an outage, failed proposal or exhausted allowance, the UI can continue with clearly attributed seeded fuzzing.

Public history contains only the latest **50 attempts in that Streamlit session**. It is kept in memory, is not written to the local SQLite journal, and is not shared between visitor sessions. A new session or server restart can lose it. SQL entry is limited to 4,000 characters. Reference queries remain out of learner-facing output, and a passing result means no counterexample was found within the search budget.

## Paced catalog evaluation

The evaluator runs **14 known-wrong queries and eight equivalent alternatives**, using independent model-only and fuzz-only hunts. The hunter receives only problem fields plus the required reference query; it does not receive the catalog's known-answer lists or authored trap datasets. One hosted round is allowed for each case. Model-hunt starts are at least **35 seconds apart**, allowing the conservative input reservation to age out naturally. Allow at least 13 minutes for all 22 cases, potentially longer with slow responses. Avoid concurrent live evaluations against the same project; their process-local counters are independent.

After storing the key privately, run a one-case smoke test from the repository root:

```powershell
$env:TEMP="$PWD\.cache\tmp"; $env:TMP=$env:TEMP; $env:PYTHONPYCACHEPREFIX="$PWD\.cache\pycache"; $env:BMQ_MODEL_PROVIDER='gemini'; $env:BMQ_MODEL='gemma-4-26b-a4b-it'; .\.venv\Scripts\python.exe .\scripts\eval_hosted.py --limit 1 --output .cache/hosted-smoke.json
```

For the full catalog, use the same environment and omit `--limit`:

```powershell
.\.venv\Scripts\python.exe .\scripts\eval_hosted.py --output .cache/hosted-evaluation.json
```

`--output` is optional and must resolve inside this repository. The CLI prints a sanitized JSON record after each case and a final summary, and optionally saves the complete JSON report. It excludes queries, datasets, raw provider text, error bodies and credentials. An interrupted run's printed cases are partial; no complete report is written.

Exit **0** means every selected method/case had verified stress candidates with no evaluation errors or false positives. It does not mean every wrong query was caught, and a `--limit` run is not full coverage. Exit **1** reports evaluation errors/false positives or a configuration/write failure. Exit **2** means at least one case produced no verified stress candidates. Zero candidates are **unmeasured**, not successful passes or model misses. Inspect `wrong_found`, `wrong_measured`, `wrong_total`, equivalent coverage and each case before quoting a result. Only a hidden bug actually found in the independent model-only hunt counts toward the model hit rate. The report does not validate teaching quality, concurrency or public hosting.

## Public URL checks and evidence

The public URL and model-found E1 case described above are verified. Deployed history/Retry, equivalent-query, SQL-error and separate-session checks passed and are recorded in [hosted verification](hosted-verification.md). The record distinguishes these deployed smoke checks from the earlier local API catalog evaluation. Neither establishes generated teaching quality or load capacity.

Publish the actual Gemma catalog report with its unsuccessful primary call and explicit follow-up; do not substitute the earlier Llama hit rate for hosted Gemma results. The owner must also publish the supporting documents before their public links can substantiate the DEV article. The separate [local verification record](live-verification.md) describes the Llama trial.
