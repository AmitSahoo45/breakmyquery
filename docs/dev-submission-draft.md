<!-- DRAFT: review the publication notes and any applicable team credit before publishing. -->
<!-- Suggested title: BreakMyQuery: find the row that breaks your SQL -->
<!-- Set these tags in the DEV editor: devchallenge, weekendchallenge, hf26challenge -->
<!-- Create the post using the official Submission Template. Copy the article below after completing it. -->
<!-- Before publication: the owner must publish the evaluation reports and docs linked below (currently 404 publicly), add any applicable team credit, and resolve the hosted API audience/billing condition. This is not a published DEV entry. -->

*This is a submission for the [Hacktoberfest Weekend Challenge: Build for a Friend](https://dev.to/challenges/hacktoberfest-weekend-2026-10-01).*

## What I Built

A SQL query can pass the sample data and still fail on a customer with no orders, a missing value, a duplicate name or a date boundary. BreakMyQuery finds a small dataset that exposes the mistake, then shows the learner's result beside the expected result.

I built it for a friend who is a new graduate hire straight out of college and is struggling with SQL joins. BreakMyQuery gives them a concrete way to see which rows a join loses or duplicates, then work out the repair themselves.

The learner gets eight SQLite exercises, an editor, concrete counterexamples and a mistake journal. Public-demo history stays within the visitor's session; local history persists on disk. They can retry a saved query and test their next idea. There is no solution-reveal button. A passing run says that no counterexample was found within its test budget; it does not call the query proven correct.

I have demonstrated it to my friend.

## Demo

[Try BreakMyQuery](https://breakmyquery.streamlit.app).

The public-demo entrypoint uses hosted Gemma 4 to propose a dataset; the local version can use Llama 3.2 through Ollama. Both have generated real counterexamples verified by SQLite. The app shrinks and displays the evidence, and the source caption distinguishes a model-found case from a random stress-test result. Model-generated hints and mistake classifications are disabled in the current demo.

In a signed-out check of the deployed app, a paid-order count matched the sample but dropped a customer with no orders. Gemma produced a counterexample that shrank to one customer, Alice in New York, with no orders. The submitted query returned no rows; the expected result contained Alice with a zero count. The app attributed the case to Gemma and showed no generated hint. The learner reasons from those rows and edits their own query.

<!-- The deployed behavior is recorded in docs/hosted-verification.md. Publish that file with the reports before using their public links. -->

## Code

[BreakMyQuery source code](https://github.com/AmitSahoo45/breakmyquery).

The public repository includes the application, exercises, tests, setup instructions and MIT license. The application code and model weights have separate licenses.

## How I Built It

The stack is Python, Streamlit, SQLite and Pydantic. The hosted provider uses the open-weight **Gemma 4 26B A4B** model through Google's Gemini API. The local provider uses Ollama; **Llama 3.2** was evaluated on the existing laptop setup.

The model receives the exercise schema, question and the two queries being compared, and proposes small datasets intended to make their results differ. The app validates the proposed data and executes both queries in SQLite. Only an observed database-result difference can become a counterexample. It then removes rows while preserving the mismatch and schema constraints.

The UI shows the data and differing results. The reference query stays out of the learner-facing output. Seeded random fuzzing provides another source of candidate datasets, and the journal keeps attempts for later practice.

The earlier local Llama trial measured both hunting methods separately on 14 deliberately wrong queries and eight equivalent alternatives:

| Method | Wrong queries exposed | False positives on alternatives |
|---|---:|---:|
| Llama 3.2 proposals, verified by SQLite | 9/14 | 0/8 |
| Seeded random fuzzing | 14/14 | 0/8 |

Fuzzing was stronger on this small catalog. The model provides a way to propose cases from the question and query; the database remains the authority on whether those cases demonstrate a bug. These results do not establish accuracy for arbitrary SQL. The evaluation report also records failed model rounds and the fact that the run was resumed after a local service interruption.

The live teaching checks exposed another limitation: Llama sometimes gave an incorrect reason for a real mismatch. I disabled generated hints and classifications in the demo and retained the verified tables and results. A model producing a valid dataset did not make its explanation trustworthy.

For the hosted version, Gemma 4 caught **14/14** wrong queries with **0/8** false
positives on equivalent alternatives. One equivalent case needed a separate
follow-up after an unusable response; the report retains that failed attempt.
This was 23 model attempts for 22 catalog cases, not a perfect first-call success
rate. Gemma's generated teaching content remains disabled and unevaluated.
See the [Gemma API evaluation](https://github.com/AmitSahoo45/breakmyquery/blob/main/eval_results_gemma_api.md).

The implementation passed 287 offline tests, with all eight exercises validated. On the deployed app, a signed-out browser verified the Gemma counterexample, a correct alternative passing 403 stress tests, a SQL error, saved history and Retry. A fresh tab had its own empty history. The [hosted verification record](https://github.com/AmitSahoo45/breakmyquery/blob/main/docs/hosted-verification.md) separates these deployed checks from the earlier local catalog evaluation. Llama's live hint-quality checks failed and remain documented as failures.

## Why Does Open Innovation Matter?

The local version runs the model and database on the learner's computer once the runtime and weights are available. For the hosted version, Gemma removes the need for every visitor to install a model or own a GPU. That version sends submitted SQL to Google and clearly discloses the API's data handling. Open model weights and open application code give us another deployment choice; hosting still has its own terms and limits.

The application code is inspectable, and the model choice is configurable. That lets the learner see how a verdict is produced and lets a future contributor evaluate another model against the same cases. SQLite supplies a reproducible check on model-generated data; the model's confidence is never the verdict.

For this project, the useful role of the open-weight model is proposing concrete tests of a learner's reasoning. The learner still has to understand the counterexample and make the repair.

The counterexample approach was inspired by [XData at IIT Bombay](https://www.cse.iitb.ac.in/infolab/XData/XData.html). Gemma 4 uses [Apache 2.0](https://ai.google.dev/gemma/apache_2); its hosted API has separate service terms. The local inference runtime is [Ollama](https://github.com/ollama/ollama), and the tested Llama weights use the [Llama 3.2 Community License](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE).

<!-- If this was a team entry, add every teammate's DEV handle here before publication. Team membership has not been confirmed; do not claim a solo entry without that confirmation. -->

<!-- Optional: add My Agent Session only if you have a reviewed public session link. -->
<!-- Optional: add Prize Categories only for technology actually used and matching the current category wording. Real Gemma inference is verified on the deployed app; Best Use of Gemma is relevant. Streamlit hosting alone does not enter the Render category. -->
