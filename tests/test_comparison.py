import asyncio

import pytest

from app import comparison


def section(role, answer, verified="cited_draft"):
    return {
        "role": role,
        "result": {
            "answer": answer,
            "citations": [{"page": 1, "quote": answer}],
            "verification": verified,
        },
    }


def test_single_supported_source_cannot_produce_comparison():
    results = [section("company", "营收 11 美元"), section("peer", "缺证", "insufficient_evidence")]
    assert (
        asyncio.run(comparison.summarize(results, "对照两家公司", {}))["status"]
        == "insufficient_evidence"
    )


@pytest.mark.parametrize(
    ("text", "roles", "expected"),
    [
        ("两家公司各披露营收 11 美元与 9 美元", ["company", "peer"], "draft"),
        ("营收 999 美元", ["company", "peer"], "insufficient_evidence"),
        ("两家公司均报告增长", ["company", "unseen"], "insufficient_evidence"),
    ],
)
def test_summary_checks_referenced_sources_and_figures(monkeypatch, text, roles, expected):
    async def select(*args):
        return {"text": text, "roles": roles}

    monkeypatch.setattr(comparison, "select_json", select)
    rows = [section("company", "营收 11 美元"), section("peer", "营收 9 美元")]
    assert asyncio.run(comparison.summarize(rows, "比较营收", {}))["status"] == expected
