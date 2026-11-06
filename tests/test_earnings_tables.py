"""Exercise scope and fiscal column binding with synthetic issuers and changed values."""

import asyncio

import pytest

from app.earnings_tables import lookup_request, resolve_sources
from app.reader import from_document


def page(text, number=1):
    return {"number": number, "text": text}


COMPANY = """Second Quarter Results
Financial Highlights
GAAP Non-GAAP
(in millions, except per share data)
Q2 2028 Q2 2027 Change Q2 2028 Q2 2027 Change
Revenues $310 $290 7% $311 $289 8%
Net income $7 ($3) NM $9 $2 NM
Diluted EPS $0.48 ($0.32) NM $0.52 $0.1 NM"""
SEGMENTS = """Segment Results
AAA BBB
(in millions)
Q2 2028 Q2 2027 Change Q2 2028 Q2 2027 Change
Revenues $80 $70 14% $210 $200 5%"""
PRODUCTS = """AAA Revenue Streams1
(in millions)
Second Quarter Fiscal
2028 2027 Change 2028 2027 Change
Automotive $8 $7 14% $19 $17 12%"""
OUTLOOK = """Business Outlook
Fiscal 2029 Q1 Guidance
Revenues $1.8B - $2.4B
AAA revenues $0.5B - $0.6B
GAAP diluted EPS $0.30 - $0.35"""


@pytest.mark.parametrize(
    "question,amounts,expected_page",
    [
        ("2028 财年第二季度 GAAP 营收是多少百万美元？", ["310"], 2),
        ("2028 财年第二季度 BBB 分部收入是多少百万美元？", ["210"], 1),
        ("2027 财年第二季度 GAAP 摊薄每股收益是多少美元？", ["-0.32"], 2),
        ("2028 财年全年 AAA 汽车业务的收入是多少百万美元？", ["19"], 3),
        ("2028 财年第二季度非 GAAP 净利润是多少百万美元？", ["9"], 2),
        ("2029 财年第一季度总营收指引区间是多少亿美元？", ["18.0", "24.0"], 4),
    ],
)
def test_bind_scope_year_period_and_unit(question, amounts, expected_page):
    pages = [page(SEGMENTS), page(COMPANY, 2), page(PRODUCTS, 3), page(OUTLOOK, 4)]
    answers = resolve_sources(pages, lookup_request(question))
    assert [(c["amounts"], c["page"]) for c in answers] == [(amounts, expected_page)]
    assert answers[0]["quote"] in pages[expected_page - 1]["text"]


@pytest.mark.parametrize(
    "question,document",
    [
        ("2028 财年第二季度 GAAP 营收是多少百万美元？", SEGMENTS),
        ("2028 财年第二季度客户 ZED 贡献的营收是多少？", COMPANY),
        (
            "2028 财年第二季度 BBB 营收是多少百万美元？",
            SEGMENTS.replace("Q2 2027 Change\nRevenues", "Q2 2026 Change\nRevenues"),
        ),
        (
            "2028 财年第二季度 GAAP 营收是多少百万美元？",
            COMPANY.replace("in millions", "in millions CAD"),
        ),
        ("2029 财年第一季度实际营收是多少亿美元？", OUTLOOK),
    ],
)
def test_refuse_missing_coordinates(question, document):
    assert not resolve_sources([page(document)], lookup_request(question))


def test_conflicting_equivalent_cells_abstain_before_generation():
    tools = []
    _, state, _ = asyncio.run(
        from_document(
            None,
            None,
            [page(COMPANY), page(COMPANY.replace("$310", "$100"), 2)],
            "2028 财年第二季度 GAAP 营收是多少百万美元？",
            {},
            tools,
            [],
            [],
        )
    )
    assert state == "insufficient_evidence"
    assert tools[-1]["result"] == "conflicting_amounts"
