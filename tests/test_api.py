import io
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.main import MAX_BYTES, create_app

DEMO = (Path(__file__).parents[1] / "examples" / "demo-report.txt").read_bytes()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "test.db"))) as c:
        yield c


def upload(client, content=DEMO, company="演示公司", filename="report.txt"):
    return client.post("/reports", data={"company": company}, files={"file": (filename, content)})


def ask(client, report_id, question, mode="rules"):
    return client.post(f"/reports/{report_id}/questions", json={"question": question, "mode": mode})


def test_full_upload_calculation_and_history(client):
    response = upload(client)
    assert response.status_code == 201
    report = response.json()
    assert report["metrics"] == 12
    result = ask(client, report["id"], "2025 年营业收入同比增长率和毛利率是多少？").json()
    assert "20.00%" in result["answer"]
    assert "35.00%" in result["answer"]
    assert result["verification"] == "tool_results_only"
    assert len(result["citations"]) > 0
    assert all(c["quote"] in DEMO.decode() for c in result["citations"])
    saved = client.get("/analyses/" + result["id"])
    assert saved.json() == result
    revenue = next(
        m
        for m in client.get("/reports/" + report["id"]).json()["metrics"]
        if m["name"] == "revenue" and m["year"] == 2025
    )
    assert revenue["value"] == "1200000000"


def test_deduplicate_and_company_boundary(client):
    first, second = upload(client).json(), upload(client).json()
    assert second["id"] == first["id"] and second["deduplicated"]
    assert upload(client, company="另一公司").json()["id"] != first["id"]


def test_missing_data_is_not_invented(client):
    report_id = upload(client).json()["id"]
    result = ask(client, report_id, "2023 年营业收入同比增长率").json()
    assert "无法计算" in result["answer"]
    assert not any(
        "value" in step["result"] for step in result["trace"] if step["tool"] == "calculate"
    )


def test_retrieval_only_and_no_evidence(client):
    report_id = upload(client).json()["id"]
    result = ask(client, report_id, "原材料价格风险因素").json()
    assert any("原材料" in c["quote"] for c in result["citations"])
    assert "未自动生成" in result["answer"]
    result = ask(client, report_id, "xyznonexistentkeyword").json()
    assert result["citations"] == []
    assert "无法回答" in result["answer"]


@pytest.mark.parametrize(
    "content,filename",
    [
        (b"", "empty.txt"),
        (b"\xff\xfe", "bad.txt"),
        (b"x", "x.exe"),
        (b"invalid", "broken.pdf"),
        (b"x" * (MAX_BYTES + 1), "large.txt"),
    ],
)
def test_invalid_upload_is_rejected(client, content, filename):
    r = upload(client, content=content, filename=filename)
    assert r.status_code in (413, 422)
    assert client.get("/reports").json() == []


def make_pdf(text=None, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 30 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_text_pdf_retrieval(client):
    response = upload(client, make_pdf("Revenue increased in 2025"), filename="report.pdf")
    assert response.status_code == 201
    assert response.json()["metrics"] == 0
    result = ask(client, response.json()["id"], "Revenue").json()
    assert "Revenue increased" in result["citations"][0]["quote"]


@pytest.mark.parametrize("encrypted", [False, True])
def test_empty_or_encrypted_pdf_rejected(client, encrypted):
    r = upload(client, make_pdf(encrypted=encrypted), filename="report.pdf")
    assert r.status_code == 422


def metric_payload(**changes):
    value = {
        "name": "revenue",
        "year": 2025,
        "source_value": "120000",
        "source_unit": "万元",
        "currency": "CNY",
        "page": 1,
        "quote": "营业收入 | 120000 | 100000",
        "scope": "consolidated_annual",
        "confirmed_by_user": True,
    }
    return {**value, **changes}


def test_human_confirmation_persists_and_dedup_does_not_overwrite(client):
    report_id = upload(client).json()["id"]
    path = f"/reports/{report_id}/metrics"
    assert client.put(path, json=metric_payload()).status_code == 200
    assert upload(client).json()["deduplicated"]
    facts = client.get(f"/reports/{report_id}").json()["metrics"]
    assert (
        next(m for m in facts if m["name"] == "revenue" and m["year"] == 2025)["origin"]
        == "human_confirmed"
    )


def test_confirmation_ignores_unclosed_parenthesized_number_in_quote(client):
    text = "Years ended (2025 and 2024)\nTotal net sales 416,161 391,035\n"
    report_id = upload(client, content=text.encode(), filename="annual.txt").json()["id"]
    payload = metric_payload(
        source_value="416,161", source_unit="百万元", currency="USD", quote=text
    )
    response = client.put(f"/reports/{report_id}/metrics", json=payload)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"quote": "伪造的财报原文"},
        {"source_value": "120001"},
        {"page": 999},
        {"year": 2023},
        {"confirmed_by_user": False},
        {"source_value": "NaN"},
    ],
)
def test_invalid_human_confirmation(client, changes):
    report_id = upload(client).json()["id"]
    assert (
        client.put(f"/reports/{report_id}/metrics", json=metric_payload(**changes)).status_code
        == 422
    )


def test_not_found_validation_and_home(client):
    for path in ("/reports/missing", "/reports/missing/pages/1", "/analyses/missing"):
        assert client.get(path).status_code == 404
    assert ask(client, "missing", "营业收入").status_code == 404
    report_id = upload(client).json()["id"]
    assert ask(client, report_id, "  ").status_code == 422
    assert ask(client, report_id, "营业收入", "unknown").status_code == 422
    assert client.get(f"/reports/{report_id}/pages/0").status_code == 404
    assert client.get("/reports?limit=101").status_code == 422
    assert client.get("/health").json()["status"] == "ok"
    assert "财报分析工作台" in client.get("/").text
    assert client.get("/openapi.json").status_code == 200


def test_ollama_not_configured(client):
    report_id = upload(client).json()["id"]
    assert ask(client, report_id, "风险因素", "ollama").status_code == 422


def test_ollama_tool_loop_and_recording(tmp_path, monkeypatch):
    real_client = httpx.AsyncClient
    payloads = []
    observed = []

    def responder(request):
        import json

        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "calculate",
                            "arguments": {"kind": "gross_margin", "year": 2025},
                        }
                    },
                    {"function": {"name": "run_shell", "arguments": {"cmd": "bad"}}},
                ],
            }
        else:
            message = {"role": "assistant", "content": "毛利率 35.00%，参见第 1 页。"}
        return httpx.Response(200, json={"message": message})

    monkeypatch.setattr(
        "app.agent.httpx.AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(responder), **kw),
    )
    with TestClient(
        create_app(
            str(tmp_path / "llm.db"), {"model": "test-model", "ollama_url": "http://model.invalid",
                                    "system_prompt": "frozen evaluation prompt",
                                    "model_options": {"temperature": 0, "seed": 42},
                                    "on_model_event": observed.append}
        )
    ) as c:
        report_id = upload(c).json()["id"]
        response = ask(c, report_id, "分析盈利能力", "ollama")
        assert response.status_code == 200
        result = response.json()
        assert result["verification"] == "model_draft_unverified"
        assert any(
            s["tool"] == "calculate" and s["result"].get("value") == "35.00"
            for s in result["trace"]
        )
        assert any(
            s["result"].get("status") == "error"
            for s in result["trace"]
            if isinstance(s["result"], dict)
        )
        assert len(payloads) == 2
        assert payloads[1]["messages"][-1]["role"] == "tool"
        assert payloads[0]["messages"][0]["content"] == "frozen evaluation prompt"
        assert payloads[0]["options"] == {"temperature": 0, "seed": 42}
        assert result["trace"][0]["origin"] == "server"
        assert all(s["origin"] == "model" for s in result["trace"][1:])
        assert len(result["model_trace"]) == len(observed) == 2
        assert len(observed[0]["request"]["messages"]) == 3
        assert len(observed[1]["request"]["messages"]) == 6
        assert c.get("/analyses/" + result["id"]).json()["model_trace"] == observed


@pytest.mark.parametrize(
    "draft,expected",
    [
        ("毛利率 99%，参见第 1 页。", "model_rejected_numeric_claim"),
        ("毛利率 35%，参见第 999 页。", "model_rejected_citation"),
    ],
)
def test_model_draft_guard_fails_closed(tmp_path, monkeypatch, draft, expected):
    real_client = httpx.AsyncClient

    def responder(request):
        return httpx.Response(200, json={"message": {"role": "assistant", "content": draft}})

    monkeypatch.setattr(
        "app.agent.httpx.AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(responder), **kw),
    )
    with TestClient(
        create_app(str(tmp_path / "guard.db"), {"model": "test", "ollama_url": "http://model.invalid"})
    ) as c:
        report_id = upload(c).json()["id"]
        result = ask(c, report_id, "2025 年毛利率是多少？", "ollama").json()
        assert result["verification"] == expected
        assert draft not in result["answer"]
        assert c.get("/analyses/" + result["id"]).json() == result


@pytest.mark.parametrize("failure", ["timeout", "bad_json", "bad_message", "budget"])
def test_model_failures_and_budget(tmp_path, monkeypatch, failure):
    real_client = httpx.AsyncClient

    def responder(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "bad_json":
            return httpx.Response(200, content=b"invalid")
        if failure == "bad_message":
            return httpx.Response(200, json={"message": []})
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "tool_calls": [{"function": {"name": "list_metrics", "arguments": {}}}],
                }
            },
        )

    monkeypatch.setattr(
        "app.agent.httpx.AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(responder), **kw),
    )
    with TestClient(
        create_app(
            str(tmp_path / "failed.db"),
            {"model": "test-model", "ollama_url": "http://model.invalid"},
        )
    ) as c:
        report_id = upload(c).json()["id"]
        r = ask(c, report_id, "分析盈利能力", "ollama")
        if failure == "budget":
            assert r.status_code == 200
            assert r.json()["verification"] == "tool_budget_exhausted"
        else:
            assert r.status_code in (422, 502)
