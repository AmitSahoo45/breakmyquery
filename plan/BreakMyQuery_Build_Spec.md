# BreakMyQuery — Build Spec

For the implementing agent. Build all of this today. Follow the spec; ask only if something blocks you.

**Contest:** DEV Hacktoberfest Weekend Challenge, "Build for a Friend". Open-source AI must be at the core.
**Deadline:** Mon 5 Oct 2026, 12:29 IST. The repo must be created inside the challenge window (after 2 Oct 07:30 IST). Create a new repo; reuse no existing project code.

---

## 1. Problem

Source: r/learnSQL, "Please help me in practicing SQL".

- The learner practices on LeetCode and HackerRank and checks queries with GPT. When a query is wrong, they can't learn from the mistake. They freeze and make "silly mistakes" in interviews.
- Thread consensus: stop using AI for answers, sit with the error, ask *why*, and take notes.
- Tools recommended in the thread: SQL Case Files, sqlbook.io, SQL Climber, SQLBolt, StrataScratch, w3resource, practicewindowfunctions.com, datahelix.io, DataCamp projects. These are problem sets and datasets. None was reported to prove *why* a query is wrong.

## 2. Product

**One line:** A local SQL practice tool that never gives you the answer. When your query is wrong, it proves it with the smallest dataset that breaks it, then makes you fix it yourself.

**USP:** It catches *hidden bugs*: queries that pass the sample data but are logically wrong (NULLs, LEFT vs INNER JOIN, join fan-out, ties, integer division, date boundaries).

**Principles (non-negotiable):**
1. Never show or generate a corrected query. No "reveal solution" button.
2. Verdicts come from SQLite, never from the model. The model proposes; the database verifies.
3. Proof first, words second. Show the counterexample before any hint.
4. Remember the learner's mistakes (trap journal).
5. Honest wording. "No counterexample found" does not mean correct. The UI says "Passed sample + N stress tests", never "Correct".

## 3. Stack

- Python 3.11+, `sqlite3` (stdlib), `streamlit`, `pandas`, `pydantic` v2, `ollama` (Python client).
- Ollama (recent version) with **Gemma 4**. Default model `gemma4:e4b`; override with env `BMQ_MODEL` (e.g. `gemma4:12b`).
- Always pass `options={"num_ctx": 8192}`, because Ollama's default context window can be too small.
- No cloud calls, accounts or telemetry. Fully offline after the model is pulled.
- If Ollama is unreachable, the app must still work in fuzz-only mode and show "Gemma offline: showing counterexample only".

### 3.1 Host environment (owner has set this up)

- **OS and shell:** Windows 11. Give every command as a PowerShell one-liner.
- **Hardware:** i7-13650HX, 24 GB RAM, 8 GB discrete GPU.
- **Rule: nothing from this project is installed or written on C:.** All installs, caches, data and outputs go on D:.

| Item | Location |
|---|---|
| Repo | `D:\Projects\breakmyquery` |
| Virtual env | `D:\Projects\breakmyquery\.venv` |
| Ollama install | `D:\Ollama` |
| Ollama models | `D:\Ollama\models` (user env var `OLLAMA_MODELS` is set) |
| pip cache | `D:\pip-cache` (user env var `PIP_CACHE_DIR` is set) |
| App data (`BMQ_DATA_DIR`) | `D:\Projects\breakmyquery\.bmq` |

Rules for the agent:
- **Use the venv for everything.** Never install globally or with `--user`. Install with:
  ```powershell
  D:\Projects\breakmyquery\.venv\Scripts\python.exe -m pip install -r requirements.txt
  ```
- **Check Python first.** If `D:\Projects\breakmyquery\.venv\Scripts\python.exe --version` is below 3.11, stop and tell the owner.
- **Keep app data in the repo.** Resolve `BMQ_DATA_DIR` relative to the repo root (`Path(__file__)`), not the current working directory. Never write to `%APPDATA%`, `%LOCALAPPDATA%`, `%TEMP%` or the user profile.
- **No temp files.** SQLite stays `:memory:`. Do not use `tempfile` defaults; they resolve to C:.
- **Add `.streamlit/config.toml` to the repo** with:
  ```toml
  [server]
  headless = true

  [browser]
  gatherUsageStats = false
  ```
  This skips Streamlit's first-run prompt, which writes to the user profile, and turns off its telemetry.
- **Use only `gemma4:e4b`.** It is already pulled; do not pull other models without asking.
- **Do not use drive E:.** It is a slow USB 2.0 stick.
- **Acceptable exception:** Ollama's own small log and key files under the user profile. They are outside this project's control.

## 4. Repo layout

```
breakmyquery/
  app.py                      # Streamlit UI
  bmq/
    __init__.py
    config.py                 # env-driven settings (see §6.7)
    db.py                     # build DB from dataset, safe query execution
    compare.py                # result normalisation + multiset diff
    fuzz.py                   # random dataset generator
    shrink.py                 # minimise a failing dataset
    llm.py                    # Gemma calls: propose, explain, explain_error
    hunter.py                 # orchestration -> Verdict
    journal.py                # local mistake log
  data/
    schema.sql
    exercises.json
    fuzz_pools.json
  scripts/
    validate_exercises.py
    eval_hunters.py           # writes eval_results.md (numbers for the blog post)
  tests/
    test_db.py
    test_compare.py
    test_shrink.py
    test_hunter_fuzz.py
  .streamlit/
    config.toml               # headless + no telemetry (see §3.1)
  requirements.txt
  README.md
  LICENSE                     # MIT
  .gitignore                  # .bmq/, .venv/, __pycache__/, .pytest_cache/
```

---

## 5. Data

### 5.1 `data/schema.sql`

```sql
CREATE TABLE customers (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL,           -- NOT unique on purpose
  city TEXT                     -- nullable on purpose
);

CREATE TABLE products (
  id       INTEGER PRIMARY KEY,
  name     TEXT NOT NULL,
  category TEXT,
  price    INTEGER NOT NULL CHECK (price >= 0)
);

CREATE TABLE orders (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  order_date  TEXT NOT NULL CHECK (order_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9] [0-2][0-9]:[0-5][0-9]'),
  status      TEXT NOT NULL CHECK (status IN ('paid', 'cancelled'))
);

CREATE TABLE order_items (
  id         INTEGER PRIMARY KEY,
  order_id   INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  quantity   INTEGER NOT NULL CHECK (quantity > 0)
);
```

Load order (parents first): `customers, products, orders, order_items`.
Delete or shrink order (children first): `order_items, orders, products, customers`.

### 5.2 Dataset format

Datasets are positional rows in schema column order. All four keys are always present; empty lists are allowed.

```json
{
  "customers":   [[1, "Asha", "Pune"]],
  "products":    [],
  "orders":      [[1, 1, "2026-09-02 10:15", "paid"]],
  "order_items": []
}
```

### 5.3 `data/exercises.json` entry format

```json
{
  "id": "e1_paid_orders",
  "title": "Paid orders per customer",
  "question": "…",
  "expected_columns": ["name", "paid_orders"],
  "order_matters": false,
  "reference_sql": "…",
  "known_wrong":   [{"sql": "…", "trap": "JOIN_TYPE"}],
  "known_correct": ["…"],
  "sample_data":   { …dataset… },
  "trap_datasets": [ { …dataset… } ]
}
```

Rules:
- `reference_sql` is never sent to the browser and never sent to the explainer prompt.
- `known_wrong`, `known_correct` and `trap_datasets` are **only** used by the validator, eval and tests. The hunter must never read `trap_datasets`, because that would be cheating.
- Trap enum: `JOIN_TYPE, ON_VS_WHERE, COUNT_STAR_VS_COLUMN, NULL_COMPARISON, JOIN_FANOUT, AGGREGATE_LOGIC, TIES, INTEGER_DIVISION, DATE_BOUNDARY, GROUP_BY_GRAIN, ANTI_JOIN, OTHER`.

### 5.4 The 8 exercises

Author `sample_data` and `trap_datasets` to satisfy the constraints listed. The validator (§10) enforces them. E1 is fully worked as the format example.

**Design rule:** every `known_wrong` must return exactly the reference result on `sample_data`, so that it passes the sample. It must differ on at least one `trap_dataset`.

---

**E1 — Paid orders per customer** · columns `name, paid_orders`
Question: *Show every customer's name and how many paid orders they have. Customers with no paid orders must appear with 0.*

```sql
-- reference
SELECT c.name, COUNT(o.id) AS paid_orders
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
GROUP BY c.id, c.name;

-- known_wrong: JOIN_TYPE
SELECT c.name, COUNT(*) AS paid_orders
FROM customers c JOIN orders o ON o.customer_id = c.id
WHERE o.status = 'paid'
GROUP BY c.id, c.name;

-- known_wrong: ON_VS_WHERE
SELECT c.name, COUNT(o.id) AS paid_orders
FROM customers c LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.status = 'paid'
GROUP BY c.id, c.name;

-- known_wrong: COUNT_STAR_VS_COLUMN
SELECT c.name, COUNT(*) AS paid_orders
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
GROUP BY c.id, c.name;

-- known_correct
SELECT c.name,
       (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id AND o.status = 'paid') AS paid_orders
FROM customers c;
```

```json
"sample_data": {
  "customers": [[1,"Asha","Pune"],[2,"Ravi","Delhi"],[3,"Meera","Bhubaneswar"]],
  "products": [],
  "orders": [[1,1,"2026-09-02 10:15","paid"],[2,1,"2026-09-05 18:40","cancelled"],
             [3,2,"2026-09-07 09:00","paid"],[4,3,"2026-09-11 13:30","paid"],
             [5,3,"2026-09-12 16:05","paid"]],
  "order_items": []
},
"trap_datasets": [{
  "customers": [[1,"Asha","Pune"],[4,"Kiran",null],[5,"Dev","Delhi"]],
  "products": [],
  "orders": [[1,1,"2026-09-02 10:15","paid"],[6,4,"2026-09-15 11:00","cancelled"]],
  "order_items": []
}]
```
Expected on sample: Asha 1, Ravi 1, Meera 2. All three wrong queries match this on the sample and differ on the trap.

---

**E2 — Not in Pune** · columns `name`
Question: *List the names of customers who are not located in Pune. A customer whose city is unknown is not in Pune.*

```sql
-- reference
SELECT name FROM customers WHERE city IS NULL OR city <> 'Pune';
-- known_wrong: NULL_COMPARISON
SELECT name FROM customers WHERE city <> 'Pune';
-- known_wrong: NULL_COMPARISON
SELECT name FROM customers WHERE city NOT IN ('Pune');
-- known_correct
SELECT name FROM customers WHERE COALESCE(city, '') <> 'Pune';
```
Sample: no NULL city; at least 1 Pune and at least 2 non-Pune customers. Trap: at least 1 customer with NULL city.

---

**E3 — Paid orders and revenue** · columns `name, paid_orders, revenue`
Question: *For each customer with at least one paid order that has items, show the name, the number of those paid orders, and revenue (sum of quantity × product price). Ignore cancelled orders and orders without items.*

```sql
-- reference
SELECT c.name,
       COUNT(DISTINCT o.id)       AS paid_orders,
       SUM(oi.quantity * p.price) AS revenue
FROM customers c
JOIN orders o       ON o.customer_id = c.id AND o.status = 'paid'
JOIN order_items oi ON oi.order_id = o.id
JOIN products p     ON p.id = oi.product_id
GROUP BY c.id, c.name;

-- known_wrong: JOIN_FANOUT   (COUNT(o.id) instead of COUNT(DISTINCT o.id))
-- known_wrong: AGGREGATE_LOGIC (SUM(p.price) instead of SUM(oi.quantity * p.price))
-- known_correct: same as reference but COUNT(DISTINCT oi.order_id)
```
Sample: every paid order has exactly 1 item line with quantity 1; at least 1 cancelled order with items; at least 2 customers in the result. Trap: one paid order with 2 item lines, and one line with quantity 2.

---

**E4 — Most expensive product(s)** · columns `name, price`
Question: *Show the most expensive product. If several products share the highest price, show all of them.*

```sql
-- reference
SELECT name, price FROM products WHERE price = (SELECT MAX(price) FROM products);
-- known_wrong: TIES
SELECT name, price FROM products ORDER BY price DESC LIMIT 1;
-- known_correct
SELECT name, price FROM (
  SELECT name, price, RANK() OVER (ORDER BY price DESC) AS r FROM products
) WHERE r = 1;
```
Sample: a single product holds the max price. Trap: two products tied at the max.

---

**E5 — Cancellation rate** · columns `cancelled_pct`
Question: *What percentage of all orders are cancelled? Round to 1 decimal place.*

```sql
-- reference
SELECT ROUND(100.0 * SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) / COUNT(*), 1) AS cancelled_pct
FROM orders;
-- known_wrong: INTEGER_DIVISION
SELECT ROUND(100 * SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) / COUNT(*), 1) AS cancelled_pct
FROM orders;
-- known_correct
SELECT ROUND(AVG(CASE WHEN status = 'cancelled' THEN 100.0 ELSE 0 END), 1) AS cancelled_pct FROM orders;
```
Sample: (cancelled × 100) divides evenly by the total, e.g. 1 of 4. Trap: 1 cancelled out of 3.

---

**E6 — September 2026 paid orders** · columns `n`
Question: *How many paid orders were placed in September 2026? `order_date` is 'YYYY-MM-DD HH:MM'.*

```sql
-- reference
SELECT COUNT(*) AS n FROM orders
WHERE status = 'paid' AND order_date >= '2026-09-01' AND order_date < '2026-10-01';
-- known_wrong: DATE_BOUNDARY (misses anything on 30 Sep after 00:00)
SELECT COUNT(*) AS n FROM orders
WHERE status = 'paid' AND order_date BETWEEN '2026-09-01' AND '2026-09-30';
-- known_wrong: DATE_BOUNDARY (ignores the year)
SELECT COUNT(*) AS n FROM orders
WHERE status = 'paid' AND strftime('%m', order_date) = '09';
-- known_correct
SELECT COUNT(*) AS n FROM orders
WHERE status = 'paid' AND substr(order_date, 1, 7) = '2026-09';
```
Sample: paid orders in September 2026 but none on the 30th, all in 2026; include one paid order on `2026-08-31 23:30` and one on `2026-10-01 00:00`. Trap: a paid order on `2026-09-30 18:45`, and one on `2025-09-10 10:00`.

---

**E7 — Customers with more than 2 orders** · columns `id, name`
Question: *List the id and name of customers who placed more than 2 orders (any status).*

```sql
-- reference
SELECT c.id, c.name FROM customers c
JOIN orders o ON o.customer_id = c.id
GROUP BY c.id, c.name
HAVING COUNT(*) > 2;
-- known_wrong: GROUP_BY_GRAIN
SELECT c.id, c.name FROM customers c
JOIN orders o ON o.customer_id = c.id
GROUP BY c.name
HAVING COUNT(*) > 2;
-- known_correct
SELECT id, name FROM customers
WHERE id IN (SELECT customer_id FROM orders GROUP BY customer_id HAVING COUNT(*) > 2);
```
Sample: names are unique; at least 1 customer with 3+ orders and at least 1 with 2 or fewer. Trap: two customers both named "Ravi", one with 2 orders and one with 1.

---

**E8 — Never paid** · columns `name`
Question: *List the names of customers who have never had a paid order. Include customers who have no orders at all.*

```sql
-- reference
SELECT c.name FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id AND o.status = 'paid');
-- known_wrong: ANTI_JOIN
SELECT DISTINCT c.name FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE o.status = 'cancelled';
-- known_wrong: ANTI_JOIN
SELECT c.name FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.status <> 'paid' OR o.id IS NULL;
-- known_correct
SELECT c.name FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id AND o.status = 'paid'
WHERE o.id IS NULL;
```
Sample: every customer has at least 1 order; names are unique; each customer has either only paid orders or exactly one order, which is cancelled; at least 1 customer of each kind. Trap: a customer with no orders, and a customer with one paid and one cancelled order.

### 5.5 `data/fuzz_pools.json`

Keys are `table.column`. Duplicate values are intentional, to produce ties and duplicate names.

```json
{
  "customers.name":     ["Asha", "Ravi", "Ravi", "Meera", "Kiran"],
  "customers.city":     ["Pune", "Delhi", "Bhubaneswar", null],
  "products.name":      ["Pen", "Notebook", "Bag", "Lamp"],
  "products.category":  ["Books", "Stationery", null],
  "products.price":     [0, 100, 250, 250, 500, 500],
  "orders.order_date":  ["2025-09-10 10:00", "2026-08-31 23:30", "2026-09-01 00:00",
                         "2026-09-15 12:00", "2026-09-30 18:45", "2026-10-01 00:00"],
  "orders.status":      ["paid", "cancelled"],
  "order_items.quantity": [1, 1, 2, 3],
  "_row_counts": {
    "customers": [1, 5], "products": [1, 4], "orders": [0, 6], "order_items": [0, 6]
  }
}
```

---

## 6. Engine

### 6.1 `db.py`

- `build_db(dataset) -> sqlite3.Connection`
  - Open `:memory:`, run `PRAGMA foreign_keys = ON`, then `executescript(schema.sql)`.
  - Insert rows parent-first with parameterised `INSERT`.
  - On any constraint error, raise `LoadError`.
- `dump_dataset(conn) -> dataset`: `SELECT * FROM <table> ORDER BY id` for each table.
- `validate_learner_sql(sql) -> str`
  - Strip `--` and `/* */` comments, then strip one trailing `;`.
  - The query must start with `SELECT` or `WITH` (case-insensitive).
  - Reject any remaining `;`.
  - Raise `QueryError` with a plain message on failure.
- `run_query(conn, sql, timeout_s) -> Result(columns: list[str], rows: list[tuple])`
  - Run `PRAGMA query_only = ON` before executing.
  - Enforce the timeout with `conn.set_progress_handler(handler, 10_000)`; the handler aborts after the deadline.
  - Wrap any `sqlite3.Error` in `QueryError(str(e))`.

### 6.2 `compare.py`

- Normalise each value: `float -> round(x, 6)`. `int`, `str` and `None` are unchanged. `1 == 1.0` is acceptable.
- Ignore column names. Compare column count first.
- If `order_matters`, compare as lists; otherwise compare as `collections.Counter` of tuples.
- `diff(expected, actual) -> Diff(column_count_mismatch: bool, missing: list[tuple], extra: list[tuple])`, with multiplicity.

### 6.3 `fuzz.py`

- `generate(rng: random.Random, pools) -> dataset`
  - Row counts come from `_row_counts`. PKs are sequential from 1.
  - FK values are picked from parent ids that already exist; skip child rows if there are no parents.
  - Values come from the pools.
- Seeded and deterministic for tests (seed 42).

### 6.4 `shrink.py`

```
shrink(dataset, still_fails) -> dataset
  repeat until no change:
    for table in [order_items, orders, products, customers]:
      for each row (last to first):
        candidate = dataset without that row
        if build_db(candidate) succeeds and still_fails(candidate): dataset = candidate
```
`still_fails` rebuilds the DB, runs both queries, and returns True if the results differ. If the learner query raises an error on a candidate, return False.

### 6.5 `llm.py` (Gemma via Ollama)

- Call `ollama.chat(model, messages, format=Schema.model_json_schema(), options={"temperature": t, "num_ctx": 8192})`.
- Parse with `Schema.model_validate_json(resp.message.content)`. On a parse failure, retry once; then return `None`.
- `propose_datasets(schema_sql, question, learner_sql, reference_sql, tried_ideas, temperature) -> list[Candidate]`
  - Each candidate's INSERTs must match `^\s*INSERT\s+INTO\s+(customers|products|orders|order_items)\b` (case-insensitive). Cap at 25.
  - Run each INSERT on a fresh schema DB one at a time; skip statements that fail.
  - Convert to a canonical dataset with `dump_dataset`.
- `explain_mismatch(question, schema_sql, learner_sql, dataset, learner_result, expected_result, diff) -> Explanation | None`
  - Never pass `reference_sql`. This is a structural guarantee that the explainer cannot leak the answer.
- `explain_error(schema_sql, learner_sql, error_message) -> ErrorExplanation | None`
- Leak guard: if `nudge`, `hint` or `where_to_look` matches `(?i)\bselect\b`, retry once at temperature 0.1 with the extra instruction "Your previous answer contained SQL. Do not include any SQL."
  - If it still leaks, replace the nudge with: "Look at the row above. Which clause in your query decides whether it is kept?" and set hint to `None`.

Pydantic schemas:

```python
class Candidate(BaseModel):
    idea: str
    inserts: list[str]

class Proposal(BaseModel):
    candidates: list[Candidate]

MistakeType = Literal["JOIN_TYPE","ON_VS_WHERE","COUNT_STAR_VS_COLUMN","NULL_COMPARISON",
                      "JOIN_FANOUT","AGGREGATE_LOGIC","TIES","INTEGER_DIVISION",
                      "DATE_BOUNDARY","GROUP_BY_GRAIN","ANTI_JOIN","OTHER"]

class Explanation(BaseModel):
    mistake_type: MistakeType
    what_happened: str
    nudge: str
    hint: str

class ErrorExplanation(BaseModel):
    meaning: str
    where_to_look: str
```

### 6.6 `hunter.py`

```python
@dataclass
class Verdict:
    status: Literal["ERROR", "WRONG_ON_SAMPLE", "HIDDEN_BUG", "PASSED"]
    error: str | None
    dataset: dict | None            # minimal failing dataset (shrunk)
    learner_result: Result | None
    expected_result: Result | None
    diff: Diff | None
    found_by: Literal["sample", "gemma", "fuzz"] | None
    gemma_idea: str | None
    stats: dict                     # gemma_rounds, gemma_candidates, fuzz_tries, seconds
```

`check(exercise, learner_sql, progress_cb) -> Verdict`:
1. Validate the SQL. On failure, return `ERROR`.
2. Run on `sample_data`.
   - If the query errors, return `ERROR`.
   - If it differs from the reference, shrink the sample and return `WRONG_ON_SAMPLE` (`found_by="sample"`).
3. Hunt, in the order set by `BMQ_HUNT_ORDER` (default `gemma,fuzz`):
   - **Gemma:** up to `BMQ_GEMMA_ROUNDS` rounds (default 2), each proposing up to 3 candidates. Use temperature 0.7, then 0.9. Pass the ideas that already failed into the next round. The first candidate whose results differ wins.
   - **Fuzz:** up to `BMQ_FUZZ_MAX` datasets (default 400) or `BMQ_FUZZ_SECONDS` (default 5). The first difference wins.
   - Skip any candidate on which the reference query or the learner query errors.
4. If a difference is found, shrink it and return `HIDDEN_BUG`. Otherwise return `PASSED` with stats.

`progress_cb(stage, detail)` stages: `sample`, `gemma`, `fuzz`, `shrink`.

### 6.7 `config.py` (env overrides)

| Env | Default |
|---|---|
| `BMQ_MODEL` | `gemma4:e4b` |
| `BMQ_OLLAMA_HOST` | `http://localhost:11434` |
| `BMQ_HUNT_ORDER` | `gemma,fuzz` |
| `BMQ_GEMMA_ROUNDS` | `2` |
| `BMQ_FUZZ_MAX` | `400` |
| `BMQ_FUZZ_SECONDS` | `5` |
| `BMQ_QUERY_TIMEOUT` | `2` |
| `BMQ_DATA_DIR` | `<repo root>\.bmq` (journal location; resolved from `Path(__file__)`, not the working directory) |

---

## 7. Prompts

### 7.1 Propose (hunter only; sees both queries)

System:
```
You generate small SQLite test datasets. You are given a schema, a question, Query A and Query B.
Your only job: propose datasets on which Query A and Query B return different results.
Rules:
- Output JSON matching the schema. No text outside JSON.
- Each candidate has "idea" (one sentence naming the edge case) and "inserts" (SQLite INSERT statements).
- At most 6 rows per table and 20 INSERT statements per candidate.
- Always give explicit id values. Insert customers and products first, then orders, then order_items.
- Respect constraints: status is 'paid' or 'cancelled'; order_date is 'YYYY-MM-DD HH:MM';
  quantity > 0; price >= 0; foreign keys must reference ids you inserted.
- Make candidates different from each other and from the ideas already tried.
Edge cases worth trying: NULL values; duplicate names; ties on the maximum; a parent with zero child rows;
a parent with several child rows; one customer with mixed statuses; dates on month boundaries or late on
the last day of a month; a different year; ratios that do not divide evenly; empty tables.
```
User:
```
SCHEMA:
{schema_sql}

QUESTION:
{question}

QUERY A:
{learner_sql}

QUERY B:
{reference_sql}

IDEAS ALREADY TRIED (no difference found):
{tried_ideas or "none"}

Return up to 3 candidates.
```

### 7.2 Explain mismatch (never sees the reference query)

System:
```
You are a patient SQL tutor for a learner practising for interviews.
Hard rules:
- Never write a SQL query or a corrected version of the learner's query. Do not use the word SELECT.
- Base everything on the concrete data shown. Mention at least one specific value from the data.
- Plain English. Be brief.
Fields:
- mistake_type: the single best category.
- what_happened: max 2 sentences. Which row(s) differ and what the learner's query did to them.
- nudge: one question pointing at the clause to re-check, without saying how to fix it.
- hint: max 2 sentences naming the SQL concept involved, still without any query.
Output JSON matching the schema.
```
User:
```
QUESTION: {question}
SCHEMA: {schema_sql}
LEARNER QUERY: {learner_sql}

DATA (smallest dataset where the learner's result is wrong):
{dataset as markdown tables with column headers}

LEARNER RESULT:
{table}
EXPECTED RESULT:
{table}
ROWS MISSING FROM LEARNER RESULT: {rows or "none"}
EXTRA ROWS IN LEARNER RESULT: {rows or "none"}
```
Temperature: 0.2.

### 7.3 Explain error

System:
```
You explain SQLite error messages to a beginner. Never write a corrected query. Do not use the word SELECT.
Output JSON: meaning (max 2 sentences, plain English), where_to_look (the clause or token to check).
```
User: schema, learner query, error message. Temperature: 0.2.

---

## 8. UI (`app.py`, Streamlit)

**Sidebar**
- Exercise list with a status icon per exercise: not tried, passed, bug found.
- Page switch: Practice / My traps.
- Model status: "Gemma online (`gemma4:e4b`)" or "Gemma offline: fuzz only".

**Practice page**
1. Title and question. The schema sits in a collapsible block.
2. Sample data: one `st.dataframe` per non-empty table, with column names from `PRAGMA table_info`.
3. SQL input (`st.text_area`, monospace) and a **Run** button.
4. While running, show `st.status` with live stages: "Running on sample…", "Gemma is hunting for a breaking case (round 1/2)…", "Stress-testing with random data…", "Shrinking…".
5. Results by verdict:
   - `ERROR`: show the SQLite message. Button **Explain this error** shows `meaning` and `where_to_look`.
   - `WRONG_ON_SAMPLE`: banner "Wrong on the sample data." Show the minimal failing slice of the sample, then **Your result** vs **Expected result** side by side. Highlight missing and extra rows.
   - `HIDDEN_BUG`: banner "Your query passes the sample data — but it breaks here." Show the minimal dataset tables and Your vs Expected. Add a caption saying who found it: "Found by Gemma: {idea}" or "Found by random stress test".
   - `PASSED`: "Passed sample + {gemma_candidates + fuzz_tries} stress tests. No breaking case found." Never use the word "Correct".
6. Hint ladder (for `WRONG_ON_SAMPLE` and `HIDDEN_BUG`):
   - Level 0, shown automatically: data and results only, with no AI text.
   - **Nudge me** shows `what_happened` and `nudge`.
   - **Bigger hint** shows `hint`.
   - Never offer a solution.
   - Call `explain_mismatch` once in the background right after the verdict, so classification is ready. Reveal its text only through the buttons.

**My traps page**
- Bar chart of mistake counts by `mistake_type`.
- For each type, the latest instance: exercise title, the learner's query, the minimal dataset and `what_happened`. Include a **Retry** button.

Never render `reference_sql` anywhere.

## 9. Journal (`journal.py`)

SQLite file at `{BMQ_DATA_DIR}/journal.db`, which is gitignored.

```sql
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  exercise_id TEXT NOT NULL,
  learner_sql TEXT NOT NULL,
  verdict TEXT NOT NULL,
  found_by TEXT,
  mistake_type TEXT,            -- from Explanation; NULL if Gemma offline
  what_happened TEXT,
  counterexample_json TEXT
);
```
Log every run.

## 10. Scripts and tests

**`scripts/validate_exercises.py`** fails loudly on any violation. For each exercise:
- `sample_data` and every `trap_dataset` load without constraint errors.
- The reference returns at least 1 row on the sample.
- Every `known_wrong` equals the reference on the sample.
- Every `known_wrong` differs from the reference on at least one trap dataset.
- Every `known_correct` equals the reference on the sample and on every trap dataset.
- `expected_columns` length equals the reference column count.

**`scripts/eval_hunters.py`** writes `eval_results.md`:
- Run every `known_wrong` against the hunter twice: Gemma-only, then fuzz-only (seed 42).
- Table columns: exercise | trap | Gemma found? (round, seconds) | fuzz found? (tries, seconds) | minimal rows.
- Summary: Gemma hit rate, fuzz hit rate, combined hit rate, median seconds.
- Run every `known_correct` too; false positives must be 0.

**`tests/`** (pytest). Mark Gemma-dependent tests `@pytest.mark.ollama`; they are skipped by default.
- `test_compare`: `1 == 1.0`; float rounding; order-insensitive vs order-sensitive; column count mismatch; multiplicity in the diff.
- `test_db`: rejects `DELETE`, multi-statement input and a `PRAGMA` from the learner; the timeout aborts a recursive CTE; `query_only` blocks writes.
- `test_shrink`: E1 trap dataset with each E1 `known_wrong` shrinks to at most 2 rows and still differs.
- `test_hunter_fuzz`: fuzz-only, seed 42. Every `known_wrong` in all 8 exercises gets `HIDDEN_BUG` with at most 6 rows after shrinking. Every `known_correct` gets `PASSED`.

## 11. Acceptance criteria (definition of done)

1. `python scripts/validate_exercises.py` passes.
2. `pytest` passes, excluding tests marked `ollama`.
3. If a `known_wrong` isn't caught by fuzz, tune `fuzz_pools.json`. Do not change the exercise.
4. `.venv\Scripts\python.exe -m streamlit run app.py` runs the E1 demo flow end to end with Gemma (see §14).
5. With Ollama stopped, the app still runs in fuzz-only mode.
6. `python scripts/eval_hunters.py` produces `eval_results.md` with 0 false positives.
7. Nothing from this project is written to C:. All files created by the build and the app are under `D:\Projects\breakmyquery`.
8. README covers:
   - setup on Windows, as PowerShell one-liners: create the venv, `.venv\Scripts\python.exe -m pip install -r requirements.txt`, `ollama pull gemma4:e4b`, `.venv\Scripts\python.exe -m streamlit run app.py`
   - a note that `OLLAMA_MODELS` and `PIP_CACHE_DIR` can point to another drive
   - how it works (propose → verify → shrink → explain)
   - eval table
   - credits, including the XData project (IIT Bombay) for the idea of generating data to expose wrong SQL queries
   - the Gemma Terms of Use note
   - MIT license

## 12. Build order (today)

| # | Block | Time | Done when |
|---|---|---|---|
| 0 | Verify `ollama run gemma4:e4b "ping"` and `$env:OLLAMA_MODELS`; `git init` in `D:\Projects\breakmyquery`; check venv Python ≥ 3.11; install requirements into the venv; add `.streamlit/config.toml` | 15m | Gemma replies, venv imports all packages, nothing written to C: |
| 1 | `schema.sql`, `exercises.json` (8), `validate_exercises.py` | 75m | validator green |
| 2 | `db.py`, `compare.py`, `fuzz.py`, `shrink.py`, tests | 90m | fuzz-only acceptance test green |
| 3 | `llm.py`, `hunter.py` | 60m | Gemma finds the E1 bug from the CLI |
| 4 | `app.py`, `journal.py` | 90m | E1 demo flow works in the browser |
| 5 | `eval_hunters.py` | 30m | `eval_results.md` written |
| 6 | README, final commit | 30m | criteria 1–8 met |

## 13. Out of scope

Accounts, cloud deploy, SQL Server/Postgres dialects, free-form chat tutor, exercise generator, spaced repetition, solution reveal, mobile layout, multi-language UI.

## 14. Demo flow (for the video, ~2 min)

1. Open E1 and show the sample data.
2. Enter the INNER JOIN query (`known_wrong` JOIN_TYPE) and run it. It passes the sample, then the banner appears with a 1–2 row breaking dataset: a customer with no paid orders is missing.
3. Click **Nudge me** and show the question.
4. Change to LEFT JOIN but keep `WHERE o.status = 'paid'`. It breaks again (ON_VS_WHERE).
5. Move the filter into `ON`. The result is "Passed sample + N stress tests".
6. Open My traps: JOIN_TYPE ×1, ON_VS_WHERE ×1.
7. Turn Wi-Fi off and run again. It still works, because everything runs locally.
