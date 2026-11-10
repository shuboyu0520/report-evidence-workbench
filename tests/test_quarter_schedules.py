import asyncio
from unittest.mock import AsyncMock

from app import reader
from app.earnings_tables import lookup_request, resolve_sources

STATEMENT = """RIVER HOTELS
INCOME STATEMENT
(In millions)
Three Months Ended
September 30,
Nine Months Ended
September 30,
2031 2030 2031 2030
Net revenues
Membership and franchise fees $ 26 $ 19 $ 63 $ 55
Marketing, reservation and loyalty 14 12 37 33
Net revenues 40 31 100 88
Expenses
Marketing, reservation and loyalty 13 11 36 32
Operating income 22 16 54 48
Interest expense, net 8 7 19 12"""

COLUMNS = """First
Quarter
Second Quarter
Third Quarter
Fourth Quarter Full Year"""

SEGMENTS = (
    """Table 3
HISTORICAL RESULTS BY SEGMENT
"""
    + COLUMNS
    + """
Retail
Adjusted EBITDA
2031 $ 90 $ 98 $ 122 n/a n/a
Central Office
Adjusted EBITDA
2031 $ (5) $ (8) $ (12) n/a n/a
Total Company
Adjusted EBITDA
2031 $ 85 $ 90 $ 110 n/a n/a
NOTE: See Table 6 for reconciliations of Total Company non-GAAP measures."""
)

RECON = (
    """Table 6
NON-GAAP RECONCILIATIONS
(In millions)
Reconciliation of net income to adjusted EBITDA:
"""
    + COLUMNS
    + """
2031
Net income $ 50 $ 47 $ 63
Adjusted EBITDA $ 85 $ 90 $ 110"""
)


def find(question, *texts):
    pages = [
        {"number": i, "text": s} for i, s in enumerate(("Third Quarter 2031 Earnings", *texts), 1)
    ]
    return resolve_sources(pages, lookup_request(question), calendar_year=True)


def test_statement_title_does_not_become_segment_columns():
    current = find("2031 年第三季度集团净营收是多少百万美元？", STATEMENT)
    previous = find("2030 年第三季度集团净营收是多少百万美元？", STATEMENT)
    assert [(row["amounts"], row["column"]) for row in current + previous] == [
        (["40"], 1),
        (["31"], 2),
    ]
    assert find("2031 年第三季度集团营业利润是多少百万美元？", STATEMENT)[0]["amounts"] == ["22"]
    question = "2031 年第三季度利润表的净利息费用是多少百万美元？"
    assert find(question, STATEMENT)[0]["amounts"] == ["8"]
    assert find(question, STATEMENT.replace("net 8 7", "net (8) 7"))[0]["amounts"] == ["-8"]
    assert not find(question, STATEMENT.replace("INCOME STATEMENT", "NON-GAAP RECONCILIATIONS"))


def test_identical_requested_caption_and_statement_label_are_displayed_once(monkeypatch):
    pages = [{"number": 1, "text": "Third Quarter 2031 Earnings"}, {"number": 2, "text": STATEMENT}]
    monkeypatch.setattr(reader, "select_json", AsyncMock(return_value={"id": 1}))
    answer, state, _ = asyncio.run(
        reader.from_document(
            None,
            {},
            pages,
            "2031 年第三季度净营收（Net revenues）是多少百万美元？",
            {},
            [],
            [],
            [],
            calendar_year=True,
        )
    )
    assert state == "source_earnings_cell" and answer.count("Net revenues") == 1


def test_named_segment_keeps_parent_measure_when_the_row_repeats_its_scope(monkeypatch):
    table = """(All figures in millions)
y/y growth
By Segment Q1-29 Q2-29 Q3-29 Q4-29 Q1-30 Q2-30 Q2-30
Gross Bookings $9 $10 $11 $12 $13 $14 40%
AAA $4 $5 $6 $7 $8 $9 80%
Revenue $7 $8 $9 $10 $11 $12 50%
AAA $3 $4 $5 $6 $7 $8 100%"""
    pages = [{"number": 1, "text": table}]
    monkeypatch.setattr(reader, "select_json", AsyncMock(return_value={"id": 1}))
    for metric, expected in (("收入", "AAA Revenue"), ("总预订额", "AAA Gross Bookings")):
        answer, state, _ = asyncio.run(
            reader.from_document(
                None,
                {},
                pages,
                f"2030 年第二季度 AAA 分部的{metric}是多少百万美元？",
                {},
                [],
                [],
                [],
                calendar_year=True,
            )
        )
        assert state == "source_earnings_cell" and expected in answer


def test_named_comma_separated_revenue_line_never_uses_its_expense_twin():
    question = "2031 年第三季度，会员计划（Marketing, reservation and loyalty）列在收入项下的金额？"
    (cell,) = find(question, STATEMENT)
    assert cell["amounts"] == ["14"] and cell["context_quote"] == "Net revenues"
    assert not find(
        question, STATEMENT.replace("Marketing, reservation and loyalty 14 12 37 33\n", "")
    )


def test_year_rows_require_source_period_scope_and_corroborated_scale():
    question = "2031 年第三季度，Central Office 分部调整后 EBITDA 是多少百万美元？"
    (cell,) = find(question, SEGMENTS, RECON)
    assert cell["page"] == 2 and cell["unit_page"] == 3 and cell["column"] == 3
    assert cell["amounts"] == ["-12"] and cell["context_quote"] == "Central Office"
    assert all(r["quote"] in [SEGMENTS, RECON][r["page"] - 2] for r in cell["basis_evidence"])
    assert find("2031 年第三季度集团调整后 EBITDA 是多少百万美元？", SEGMENTS, RECON)[0][
        "amounts"
    ] == ["110"]
    assert find(question, SEGMENTS.replace("$ (12)", "$ 14"), RECON)[0]["amounts"] == ["14"]
    assert find(question, SEGMENTS, RECON.replace("millions", "thousands"))[0]["amounts"] == [
        "-0.012"
    ]
    assert not find(question, SEGMENTS.replace("See Table 6", "See Table 5"), RECON)
    assert not find(question, SEGMENTS, RECON.replace("$ 90 $ 110", "$ 91 $ 110"))
    assert not find(question, SEGMENTS, RECON + "\n(In billions)")
    assert not find(
        question,
        SEGMENTS,
        RECON.replace("Reconciliation of net income to adjusted EBITDA:", "Historical balances:"),
    )
    assert not find(question, SEGMENTS.replace("Second Quarter", "Fourth Quarter"), RECON)
    assert not find(question.replace("Central Office", "West Office"), SEGMENTS, RECON)
    assert not find(question.replace("第三季度", "第四季度"), SEGMENTS, RECON)
