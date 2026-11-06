import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def run(tmp_path, monkeypatch, fetch, replies, **options):
    payloads = []
    original = httpx.AsyncClient

    def chat(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"role": "assistant", **replies[len(payloads) - 1]}}
        )

    monkeypatch.setattr("app.agent.retrieve", fetch)
    monkeypatch.setattr(
        "app.agent.httpx.AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(chat), **kw),
    )
    config = {"model": "local", "ollama_url": "http://model.invalid", **options}
    with TestClient(create_app(tmp_path / "test.db", config)) as api:
        rid = api.post(
            "/reports", data={"company": "demo"}, files={"file": ("sample.txt", b"evidence")}
        ).json()["id"]
        response = api.post(f"/reports/{rid}/questions", json={"question": "查证据", "mode": "rag"})
        response.raise_for_status()
        answer = response.json()
        assert api.get("/analyses/" + answer["id"] + "/export").json()["analysis"] == answer
    return answer, payloads


def lookup(query):
    return {"tool_calls": [{"function": {"name": "search_report", "arguments": {"query": query}}}]}


@pytest.mark.parametrize("origin", ["server", "model"])
@pytest.mark.parametrize("recover", [True, False])
def test_search_timeout_retries_once_then_recovers_or_stops(tmp_path, monkeypatch, origin, recover):
    attempts = []

    async def fetch(db, report, pages, query, settings):
        attempts.append(query)
        target = "查证据" if origin == "server" else "另一条证据"
        if query == target and (not recover or attempts.count(target) == 1):
            raise httpx.ReadTimeout("injected")
        return [{"page": 1, "quote": "evidence"}], {}

    replies = ([lookup("另一条证据")] if origin == "model" else []) + [{"content": "见第 1 页。"}]
    result, payloads = run(tmp_path, monkeypatch, fetch, replies)
    assert [e["action"] for e in result["runtime_events"]] == (
        ["retry"] if recover else ["retry", "stop"]
    )
    assert all(e["origin"] == origin for e in result["runtime_events"])
    assert result["verification"] == ("model_draft_unverified" if recover else "tool_timeout")
    assert len(payloads) == (origin == "model") + int(recover)


def test_wall_clock_deadline_cancels_slow_search(tmp_path, monkeypatch):
    cancelled = []

    async def slow(*args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    result, payloads = run(tmp_path, monkeypatch, slow, [], search_timeout_s=0.01)
    assert len(cancelled) == 2 and not payloads and result["verification"] == "tool_timeout"


def test_duplicate_model_search_stops_before_second_execution(tmp_path, monkeypatch):
    calls = []

    async def fetch(db, report, pages, query, settings):
        calls.append(query)
        return [], {}

    result, payloads = run(tmp_path, monkeypatch, fetch, [lookup("同一问题"), lookup("同一问题")])
    assert calls == ["查证据", "同一问题"] and len(payloads) == 2
    assert result["runtime_events"][-1]["event"] == "repeated_tool"
    assert result["verification"] == "tool_budget_exhausted"


@pytest.mark.parametrize(
    "cited,expected", [(1, "model_draft_unverified"), (3, "model_rejected_citation")]
)
def test_context_keeps_best_complete_quote_and_checks_visible_pages(
    tmp_path, monkeypatch, cited, expected
):
    async def fetch(*args):
        return [{"page": i, "quote": "evidence " + str(i) + "Q" * 1200} for i in (1, 2, 3)], {}

    result, payloads = run(
        tmp_path, monkeypatch, fetch, [{"content": f"见第 {cited} 页。"}], context_bytes=3700
    )
    content = payloads[0]["messages"][2]["content"]
    sent = json.loads(content.split("：", 1)[1])
    assert sent[0] == {"page": 1, "quote": "evidence 1" + "Q" * 1200}
    assert 3 not in [h["page"] for h in sent]
    assert len(json.dumps(payloads[0], ensure_ascii=False, separators=(",", ":")).encode()) <= 3700
    assert result["verification"] == expected and result["runtime_events"][0]["dropped_hits"] > 0


def test_irreducible_context_stops_without_model_request(tmp_path, monkeypatch):
    async def fetch(*args):
        return [{"page": 1, "quote": "cannot drop the only evidence"}], {}

    result, payloads = run(tmp_path, monkeypatch, fetch, [], context_bytes=64)
    assert result["verification"] == "context_budget_exhausted" and not payloads
