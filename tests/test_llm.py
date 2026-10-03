"""Exercise the model boundary with real SQLite and a fake HTTP transport."""

from dataclasses import replace
import json
import re
import subprocess
import sys

import httpx
import ollama
import pytest

from bmq import llm
from bmq.compare import Diff
from bmq.config import ROOT, Settings
from bmq.db import Result, build_db, run_query


EMPTY = {"customers": [], "products": [], "orders": [], "order_items": []}
EXPLANATION = {
    "mistake_type": "JOIN_TYPE",
    "what_happened": "Asha is missing from your result.",
    "nudge": "Which clause keeps a customer with no matching orders?",
    "hint": "Think about which rows survive the join.",
}


@pytest.fixture
def server(monkeypatch):
    """Keep Ollama serialization and HTTP errors real, replace only the network."""
    original_client = ollama.Client
    requests, options, replies = [], [], []

    def respond(request):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=reply)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={
            "model": "gemma4:e4b", "done": True,
            "message": {"role": "assistant", "content": content},
        })

    def client(**kwargs):
        options.append(kwargs)
        return original_client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(llm.ollama, "Client", client)
    return replies, requests, options


def explain(settings=None):
    return llm.explain_mismatch(
        "Show every customer.", "CREATE TABLE customers (...);", "SELECT name FROM customers",
        {**EMPTY, "customers": [[1, "Asha", None]]},
        Result(["name"], []), Result(["name"], [("Asha",)]),
        Diff(False, [("Asha",)], []), settings=settings or Settings(),
    )


def test_structured_proposal_is_capped_and_idea_cannot_leak_reference(server):
    replies, requests, options = server
    replies.append({"candidates": [
        {"idea": "SELECT confidential_reference FROM customers", "inserts": []},
        {"idea": "Nullable city", "inserts": ["INSERT INTO customers VALUES (1,'Asha',NULL)"]},
        {"idea": "Empty tables", "inserts": []},
        {"idea": "Fourth proposal", "inserts": []},
    ]})
    candidates = llm.propose_datasets("schema", "question", "query A", "private query B", ["ties"], 0.9)
    assert len(candidates) == 3
    assert "select" not in candidates[0].idea.lower()
    assert "confidential_reference" not in candidates[0].idea
    assert candidates[1].idea == "Nullable city"
    payload = json.loads(requests[0].content)
    assert payload["format"]["properties"]["candidates"]
    assert payload["options"] == {"temperature": 0.9, "num_ctx": 8192}
    assert "private query B" in payload["messages"][1]["content"]
    assert "ties" in payload["messages"][1]["content"]
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False
    assert requests[0].extensions["timeout"]["read"] <= 45


@pytest.mark.parametrize("bad", ["not JSON", '{"candidates": "bad"}', '{}'])
def test_bad_proposal_retries_once_then_returns_empty(server, bad):
    replies, requests, _ = server
    replies.extend([bad, bad])
    assert llm.propose_datasets("", "", "", "", []) == []
    assert len(requests) == 2


def test_parse_retry_can_recover(server):
    replies, requests, _ = server
    replies.extend(["not JSON", EXPLANATION])
    result = explain()
    assert result.nudge == EXPLANATION["nudge"]
    assert len(requests) == 2


@pytest.mark.parametrize("field", ["what_happened", "nudge", "hint"])
def test_every_explanation_field_is_guarded_after_one_leak_retry(server, field):
    replies, requests, _ = server
    leaked = {**EXPLANATION, field: "sElEcT private_solution FROM customers"}
    replies.extend([leaked, leaked])
    result = explain()
    assert result is not None
    assert "private_solution" not in result.model_dump_json()
    assert re.search(r"\bselect\b", result.model_dump_json(), re.I) is None
    assert result.hint is None
    assert "Which clause" in result.nudge
    assert len(requests) == 2
    retry = json.loads(requests[-1].content)
    assert retry["options"] == {"temperature": 0.1, "num_ctx": 8192}
    assert "Your previous answer contained SQL" in str(retry["messages"])


def test_a_clean_leak_retry_is_returned(server):
    replies, requests, _ = server
    replies.extend([{**EXPLANATION, "hint": "SELECT answer"}, EXPLANATION])
    assert explain().hint == EXPLANATION["hint"]
    assert len(requests) == 2


@pytest.mark.parametrize("field", ["meaning", "where_to_look"])
def test_every_error_explanation_field_is_guarded(server, field):
    replies, requests, _ = server
    content = {"meaning": "SQLite cannot find that column.", "where_to_look": "Check the column name."}
    content[field] = "SELECT private_solution FROM customers"
    replies.extend([content, content])
    result = llm.explain_error("schema", "learner", "no such column", settings=Settings())
    assert result is not None
    assert "private_solution" not in result.model_dump_json()
    assert len(requests) == 2


def test_explainer_prompt_contains_concrete_data_and_has_no_reference_parameter(server):
    import inspect

    replies, requests, _ = server
    replies.append(EXPLANATION)
    explain()
    assert "reference_sql" not in inspect.signature(llm.explain_mismatch).parameters
    content = json.loads(requests[0].content)["messages"][1]["content"]
    assert "Asha" in content and "NULL" in content
    assert "| id | name | city |" in content
    assert "LEARNER RESULT" in content and "EXPECTED RESULT" in content


@pytest.mark.parametrize("error", [ConnectionError("offline"), httpx.ReadTimeout("too slow")])
def test_network_failures_allow_offline_use(server, error):
    replies, requests, _ = server
    replies.extend([error, error, error, error])
    assert llm.model_available(Settings()) is False
    assert llm.propose_datasets("", "", "", "", []) == []
    assert explain() is None
    assert llm.explain_error("", "", "") is None
    assert len(requests) == 4


@pytest.mark.parametrize("models,available", [
    ([{"model": "gemma4:e4b"}], True),
    ([{"model": "unrelated:latest"}], False),
    ([], False),
])
def test_availability_requires_installed_requested_model(server, models, available):
    replies, requests, _ = server
    replies.append({"models": models})
    assert llm.model_available(replace(Settings(), ollama_timeout=0.25)) is available
    assert requests[0].url.path == "/api/tags"
    assert max(requests[0].extensions["timeout"].values()) <= 0.25


def test_redirects_are_not_followed(server):
    replies, requests, _ = server
    replies.append(httpx.Response(307, headers={"Location": "https://external.example/api/tags"}))
    assert llm.model_available(Settings()) is False
    assert len(requests) == 1


@pytest.mark.parametrize("settings", [
    replace(Settings(), ollama_host="https://external.example"),
    replace(Settings(), ollama_host="http://localhost@external.example"),
    replace(Settings(), ollama_host="http://localhost:11434/?remote=true"),
    replace(Settings(), model="gemma4:cloud"),
    replace(Settings(), model="gemma4:e4b-cloud"),
    replace(Settings(), ollama_timeout=0),
])
def test_direct_settings_cannot_bypass_local_model_boundary(server, settings):
    _, requests, _ = server
    assert llm.model_available(settings) is False
    assert explain(settings) is None
    assert requests == []


@pytest.mark.parametrize("text", [
    "Try SELECT name FROM customers", "```sql\nVALUES(1)\n```",
    "INSERT INTO customers VALUES (1,'Asha',NULL)", "PRAGMA table_info(customers)",
    "S\u200bELECT secret", "ＳＥＬＥＣＴ secret",
])
def test_safe_text_replaces_sql_in_any_visible_prose(text):
    assert llm.safe_text(text, fallback="Check the data.") == "Check the data."


def test_safe_text_retains_conceptual_nudge():
    text = "Which rows survive the left join when Asha has no paid orders?"
    assert llm.safe_text(text) == text


@pytest.mark.parametrize("sql", [
    'WITH "answer" AS (VALUES (1)) VALUES (25.0)',
    'WITH "answer" AS (VALUES/*separator*/(1)) VALUES/*separator*/(25.0)',
    'WITH "answer" AS (VALUES-- separator\n(1)) VALUES-- separator\n(25.0)',
])
def test_safe_text_blocks_executable_query_without_select(sql):
    conn = build_db(EMPTY)
    try:
        assert run_query(conn, sql).rows == [(25.0,)]
    finally:
        conn.close()
    assert llm.safe_text(sql, fallback="Check the values.") == "Check the values."


def test_repeated_comments_do_not_stall_leak_guard():
    # A subprocess timeout kills and waits for the child, even if the regex stalls.
    code = (
        "import json,time; from bmq.llm import safe_text; "
        "text='VALUES' + '/*x*/' * 24 + 'x'; started=time.monotonic(); "
        "value=safe_text(text); print(json.dumps([value,time.monotonic()-started]))"
    )
    try:
        process = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, capture_output=True,
            text=True, timeout=8, check=True,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("The SQL leak guard stalled on repeated comments.")
    value, elapsed = json.loads(process.stdout)
    assert value == "VALUES" + "/*x*/" * 24 + "x"
    assert elapsed < 1.0


def test_sql_inside_comments_is_still_guarded():
    assert llm.safe_text("/* SELECT secret_solution */", fallback="Check the rows.") == "Check the rows."


def candidate(inserts):
    return llm.Candidate(idea="Small edge case", inserts=inserts)


def test_candidate_loads_literal_inserts_and_skips_constraint_errors():
    result = llm.candidate_dataset(candidate([
        "INSERT INTO customers (id, name, city) VALUES (1, 'O''Brien; -- hi', NULL);",
        "INSERT INTO customers VALUES (1,'Duplicate','Pune')",
        "INSERT INTO orders VALUES (1,999,'2026-09-01 10:00','paid')",
        "INSERT INTO products VALUES (1,'Pen',NULL,-1)",
        "INSERT INTO products (price,category,name,id) VALUES (2.5,NULL,'Pen',1)",
        "INSERT INTO orders VALUES (1,1,'2026-09-01 10:00','paid')",
    ]))
    assert result == {
        "customers": [[1, "O'Brien; -- hi", None]],
        "products": [[1, "Pen", None, 2.5]],
        "orders": [[1, 1, "2026-09-01 10:00", "paid"]], "order_items": [],
    }


@pytest.mark.parametrize("unsafe", [
    "INSERT INTO customers VALUES (1,'Asha',NULL); DELETE FROM customers;",
    "INSERT INTO customers.other VALUES (1,'Asha',NULL)",
    "INSERT INTO main.customers VALUES (1,'Asha',NULL)",
    "INSERT INTO customers VALUES (1,readfile('private.txt'),NULL)",
    "INSERT INTO customers VALUES (1,load_extension('private.dll'),NULL)",
    "INSERT INTO customers VALUES (1,randomblob(1000000000),NULL)",
    "INSERT INTO customers SELECT 1,'Asha',NULL",
    "INSERT INTO customers VALUES (1,'Asha',NULL) RETURNING *",
    "INSERT INTO customers VALUES (1,'Asha',NULL) ON CONFLICT DO NOTHING",
    "INSERT INTO customers DEFAULT VALUES",
    "INSERT INTO sqlite_master VALUES ('x','x','x',1,'x')",
    "ATTACH DATABASE 'escape.db' AS other",
    "INSERT INTO customers VALUES (1,'Asha',NULL) /* extra syntax */",
])
def test_candidate_rejects_unsafe_sql_without_executing_it(unsafe):
    assert llm.candidate_dataset(candidate([unsafe])) == EMPTY


def test_failed_multirow_insert_rolls_back_partial_work():
    result = llm.candidate_dataset(candidate([
        "INSERT INTO customers VALUES (1,'Asha',NULL)",
        "INSERT INTO customers VALUES (2,'Ravi',NULL),(1,'Duplicate',NULL)",
        "INSERT INTO customers VALUES (3,'Meera',NULL)",
    ]))
    assert result["customers"] == [[1, "Asha", None], [3, "Meera", None]]


def test_per_table_row_limit_rolls_back_statement_that_crosses_bound():
    statements = [f"INSERT INTO customers VALUES ({i},'Asha',NULL)" for i in range(1, 7)]
    statements += ["INSERT INTO customers VALUES (7,'Extra',NULL)", "INSERT INTO products VALUES (1,'Pen',NULL,0)"]
    result = llm.candidate_dataset(candidate(statements))
    assert len(result["customers"]) == 6
    assert result["products"] == [[1, "Pen", None, 0]]


def test_candidate_processes_at_most_twenty_five_statements():
    statements = ["INSERT INTO orders VALUES (1,999,'2026-09-01 10:00','paid')"] * 25
    statements.append("INSERT INTO customers VALUES (1,'Too late',NULL)")
    assert llm.candidate_dataset(candidate(statements)) == EMPTY


@pytest.mark.parametrize("value", ["'" + "x" * 20000 + "'", "1e999", "0x1234"], ids=["oversize", "infinite", "hex"])
def test_candidate_value_and_statement_sizes_are_bounded(value):
    assert llm.candidate_dataset(candidate([f"INSERT INTO customers VALUES (1,{value},NULL)"])) == EMPTY


def test_empty_candidate_is_valid_empty_dataset():
    assert llm.candidate_dataset(candidate([])) == EMPTY


def test_candidate_cannot_leak_a_query_through_a_visible_data_cell():
    result = llm.candidate_dataset(candidate([
        "INSERT INTO customers VALUES (1,'SELECT reference_answer FROM customers',NULL)",
        "INSERT INTO customers VALUES (2,'Asha',NULL)",
    ]))
    assert result["customers"] == [[2, "Asha", None]]
