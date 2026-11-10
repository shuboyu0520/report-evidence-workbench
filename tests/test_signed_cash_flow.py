import asyncio
from unittest.mock import AsyncMock

import pytest

from app import reader

TABLE = """Free Cash Flow
Three months ended
June 30,
Six months ended
June 30,
2028 2027 2028 2027
(In millions)
Operating cash flow $ (560) $ (420) $ 4,160 $ 3,105
Less: Capital expenditures (62) (38) (210) (148)
Free cash flow $ (622) $ (458) $ 3,950 $ 2,957"""
QUESTION = "2028 年第二季度单季自由现金流是多少百万美元？"


def run(monkeypatch, draft, table=TABLE, quote=None):
    pages = [
        {"number": 1, "text": "Second Quarter 2028 Financial Results"},
        {"number": 2, "text": table},
    ]
    search = ([{"page": 2, "quote": table}], {"status": "complete"})
    monkeypatch.setattr(reader, "run_search", AsyncMock(return_value=search))
    selection = {"answer": draft, "evidence": [{"page": 2, "quote": quote or table}]}
    monkeypatch.setattr(reader, "select_json", AsyncMock(return_value=selection))
    tools = []
    answer, state, refs = asyncio.run(
        reader.from_document(None, {}, pages, QUESTION, {}, tools, [], [])
    )
    return state, refs, tools[-1]


@pytest.mark.parametrize(
    "draft",
    [
        "2028 年第二季度单季自由现金流为 622 百万美元。",
        "2028 年第二季度单季自由现金流为 -458 百万美元。",
        "2028 年第二季度单季自由现金流为 3,950 百万美元。",
        "2028 年第二季度单季自由现金流为 -560 百万美元。",
        "2028 年第二季度单季自由现金流为 -622 十亿美元。",
        "2027 年第二季度单季自由现金流为 -622 百万美元。",
        "2028 年第二季度单季自由现金流指引为 -622 百万美元。",
    ],
)
def test_refuse_wrong_sign_column_metric_unit_or_year(monkeypatch, draft):
    state, refs, check = run(monkeypatch, draft)
    assert state == "insufficient_evidence" and not refs and not check["matched"]


def test_accept_original_signed_cell_and_reject_incomplete_evidence(monkeypatch):
    draft = "2028 年第二季度单季自由现金流为 −622 百万美元。"
    state, refs, check = run(monkeypatch, draft)
    assert state == "cited_draft" and refs == [{"page": 2, "quote": TABLE}]
    assert check == {"tool": "check_signed_cash_flow_cell", "matched": True}
    for incomplete in (TABLE[:TABLE.rfind("\n")], TABLE.split("(In millions)\n")[1]):
        state, refs, check = run(monkeypatch, draft, quote=incomplete)
        assert state == "insufficient_evidence" and not refs and not check["matched"]


def test_follows_source_number_and_scale(monkeypatch):
    report = TABLE.replace("(622)", "(735)").replace("(In millions)", "(In thousands)")
    for signed in ("-0.735", "负 0.735"):
        state, _, check = run(monkeypatch, f"2028 年第二季度单季自由现金流为 {signed} 百万美元。", table=report)
        assert state == "cited_draft" and check["matched"]
    state, _, check = run(monkeypatch, "2028 年第二季度单季自由现金流为 -735 百万美元。", table=report)
    assert state == "insufficient_evidence" and not check["matched"]
