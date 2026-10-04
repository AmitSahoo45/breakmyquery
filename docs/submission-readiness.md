# Submission readiness: 4 October 2026

**Status: the public app and its deployed Gemma E1 path are verified; the DEV entry remains unpublished.** The owner deployed [BreakMyQuery](https://breakmyquery.streamlit.app), and its source is public. The friend is a new graduate hire struggling with SQL joins, and the owner confirms that a demonstration already happened. Supporting reports/docs still need owner publication, team membership remains unconfirmed, and the API audience/billing condition remains unresolved. Feedback and a recording are optional additions.

Sources checked on 4 October:

- [Official contest rules](https://dev.to/page/hacktoberfest-weekend-challenge-26-10-01-contest-rules): entry window, required entry elements, one-entry rule, judging criteria.
- [Challenge page and submission template](https://dev.to/challenges/hacktoberfest-weekend-2026-10-01): tags, attribution, team credits, language, partner categories and treatment of later commits.

The window is **2 October 2026, 07:30 IST through 5 October 2026, 12:29 IST**. The deadline is **06:59 UTC on 5 October**. Publish the DEV post before the deadline; a saved draft is insufficient.

## Requirement review

| Requirement | Current evidence | Remaining action |
|---|---|---|
| New project during the entry window | Local history starts with `a9233a4` at 3 October, 19:34:31 IST; `b43b5cc` follows at 20:00:42 IST. The unauthenticated GitHub API reports repository creation at 4 October 07:20:09 UTC, within the window. | These timestamps support the project timeline; they are not proof of when all source material was authored. Credit any earlier borrowed work. |
| Publicly accessible code | Anonymous GitHub checks confirmed [AmitSahoo45/breakmyquery](https://github.com/AmitSahoo45/breakmyquery) is public and not a fork, with `main` at owner commit `38365cd`. `cloud_app.py`, the Gemini adapter, quota controls and tests are present. | Owner reviews and publishes `docs/`, `eval_results_gemma_api.md`, `eval_results_llama32.md` and these documentation updates. The reports and checked docs URLs currently return 404 publicly. |
| Real friend or loved one | Owner confirms the friend is a new graduate hire from college who struggles with SQL joins, and that a demonstration happened. The draft now uses that account. | No quote, reaction or post-demo change was supplied; the draft makes none of those claims. |
| Open-source AI central to the project | Llama 3.2 local inference and later Gemma 4 hosted inference both produced real question/query-specific E1 datasets, verified and shrunk by SQLite. | Show the model path actually used in the submitted demo and explain its role. Keep the model/fuzz source visible. Do not portray a fuzz-only result as AI-generated. |
| Demo link or video | [The live app](https://breakmyquery.streamlit.app) opens signed out. Gemma produced a real E1 counterexample. The equivalent-query, SQL-error, saved-history, Retry and separate-tab session checks also passed. | Preserve the actual scope in [hosted verification](hosted-verification.md), including the separate audience/billing condition. A video is optional. |
| Honest quality claims | [Gemma API evaluation](../eval_results_gemma_api.md): 14/14 wrong queries, 0/8 false positives across the primary run and one explicit follow-up. Llama: 9/14. Fuzz: 14/14. [Live record](live-verification.md) documents Llama's failed hint quality. | State that hints/classifications are disabled and Gemma teaching is unevaluated. Keep the unsuccessful API call visible in the reported provenance. These small-catalog numbers are not general accuracy guarantees. |
| DEV template and required tags | The saved template matches the official structure; a [draft](dev-submission-draft.md) is prepared. | Use the official Submission Template and keep `devchallenge`, `weekendchallenge`, `hf26challenge`. Fill every draft placeholder and publish one entry. |
| Explain open innovation | Inspectable application code and replaceable open-weight models. The local workflow avoids a hosted inference API; the public-demo entrypoint uses Google's hosted Gemma API. | Describe the distinction accurately and what it enabled for this friend. Hosted SQL is sent to Google. |
| Attribution and license | MIT application license; README credits XData and links the Llama 3.2 Community License. | Confirm whether any additional non-trivial borrowed code/assets were used. Credit them if so. Application licensing does not relicense model weights. |
| English and team credit | Draft is in English. Team membership is unknown. | Confirm solo or list teammates' DEV handles. Publish only one entry for the team. |
| Partner categories | Actual Gemma 4 inference is verified on the deployed Streamlit app. | Best Use of Gemma is relevant if the owner chooses to list it. Claim only technology actually used. Agent-session sharing is optional. |
| Hosted API audience | The owner reported billing disabled. Google's terms require Paid Services for clients made available to EEA, Swiss or UK users. | Resolve the audience/service arrangement. A working public URL does not approve a billing change or establish worldwide free-tier availability; no such change is inferred. |
| Post-deadline changes | No reviewed local commit is after the deadline. README now records the reporting requirement. | Identify any later commits in README with hash, date and change description. |

## Publication-file check

An earlier focused credential-pattern check examined **57 tracked/nonignored working files**, including these submission documents, and **68 historical file versions across the then-two reachable commits**. It found no matches for the checked private-key, token and credential-assignment patterns. That snapshot predates the hosted-provider changes and is not a review of the current publication set. This is a bounded sharing check, not the deferred security scan or a guarantee that every secret/personal detail is absent.

`.bmq/`, `.cache/` and `.venv/` are ignored and are not tracked. `.gitignore` also excludes `.env.*` and `.streamlit/secrets.toml`, while allowing an intentionally sanitized `.env.example`. Review examples before publishing them. Existing local journals and artifacts were preserved.

The public repository and deployed E1 flow have now been checked without authentication. Any optional friend recording remains unreviewed until supplied; use synthetic exercise data and exclude private material or reference/corrected queries from learner-facing demonstrations.

## Suggested submission sequence

1. Confirm any applicable team credit and resolve the hosted audience arrangement. The friend's context and demo link are already included.
2. Review `dev-submission-draft.md`, remove its editorial notes, and incorporate the final deployed verification scope.
3. Owner reviews and commits/pushes the missing supporting reports/docs and updated text on `main`, then checks the formerly broken public links. No agent commits or pushes.
4. Use the official DEV template and required tags, preview the final links, and publish one entry before **5 October, 12:29 pm IST**. Confirm the published post opens signed out and retain its URL.

## Deployed app and verification scope

The owner deployed `cloud_app.py` at [breakmyquery.streamlit.app](https://breakmyquery.streamlit.app). It uses hosted Gemma 4, bounded shared API admission and session history. Local Ollama and its persistent journal remain available through `app.py`. The [hosted demo guide](hosted-demo.md) explains operation and the unresolved audience condition.

The earlier [verification record](live-verification.md) describes the Llama trial. The [hosted verification record](hosted-verification.md) distinguishes the local API/catalog checks from the deployed E1, accepted-query, error, history and session checks. Teaching quality is not inferred from counterexample generation. Supporting evidence publication and the owner-published DEV entry remain outstanding. The security scan remains explicitly deferred.
