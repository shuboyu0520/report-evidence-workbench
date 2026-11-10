import pytest

from app.earnings_tables import data_line, lookup_request, resolve_sources

SUMMARY = """Financial Summary (in millions)
Metric Q2 2030 Q2 2029 Δ Y/Y
Revenue $4,000 $3,000 33%
Booked Room Nights 80 70 14%
Gross Bookings $18,000 $15,000 20%
Adjusted EBITDA* $520 $420 24%"""
SEGMENT = """(All figures in millions)
y/y growth
By Segment Q1-29 Q2-29 Q3-29 Q4-29 Q1-30 Q2-30 Q2-30
Gross Bookings $9 $10 $11 $12 $13 $14 40%
AAA $4 $5 $6 $7 $8 $9 80%
Revenue $7 $8 $9 $10 $11 $12 50%
AAA $3 $4 $5 $6 $7 $8 100%"""
TREND = """(All figures in millions)
Gross Bookings by product
Hardware $210 $220 $230 $240 $250 $260 18%
Revenue by product
Hardware $20 $25 $30 $35 $40 $45 80%
2029 2030 Y/Y
Q1 Q2 Q3 Q4 Q1 Q2 Growth"""
OUTLOOK = """Business Outlook
Metric Q2 2030
Revenue $3.15 - $3.30B+5-10%
Adjusted EBITDA** $450 - $470M
Metric Full Year 2030
Previous Guidance Current Guidance
Revenue $9 - $10B+8-9% $10 - $12B+10-12%"""


def cells(question, *texts):
    pages = [{"number": i, "text": t} for i, t in enumerate(texts, 1)]
    return resolve_sources(pages, lookup_request(question))


def test_summary_separates_variance_and_consolidated_scope():
    question = "2029 年第二季度全部业务的总预订额是多少百万美元？"
    (cell,) = cells(question, SUMMARY)
    assert (cell["amounts"], cell["column"]) == (["15,000"], 2)
    assert "Δ Y/Y" in cell["header"] and "(in millions)" in cell["unit_quote"]
    assert cells("2030 年第二季度预订间夜数是多少百万间夜？", SUMMARY)[0]["amounts"] == ["80"]
    assert not cells(question, SUMMARY.replace("Δ Y/Y", "Q2 2029"))
    assert not cells(question, SUMMARY.replace("in millions", "in millions CAD"))
    assert not cells("2030 年第二季度单一品牌的间夜数是多少百万间夜？", SUMMARY)


@pytest.mark.parametrize(
    ("question", "metric", "answer"),
    [
        ("2030 年第二季度 AAA 分部的收入是多少百万美元？", "Revenue", "8"),
        ("2029 年第二季度 AAA 分部的总预订额是多少百万美元？", "Gross Bookings", "5"),
    ],
)
def test_repeated_segment_requires_parent_row_and_distinct_variance_column(
    question, metric, answer
):
    (cell,) = cells(question, SEGMENT)
    assert cell["label"] == "AAA" and cell["measure_caption"] == metric
    assert cell["amounts"] == [answer] and cell["context_quote"].startswith(metric + " $")
    assert not cells(question, SEGMENT.replace("y/y growth", "Fiscal periods"))
    assert not cells(question, SEGMENT.replace("Q2-30 Q2-30", "Q2-30 Q1-30"))


def test_product_needs_matching_heading_and_ordered_footer_quarters():
    q = "2030 年第二季度硬件（Hardware）产品的营收是多少百万美元？"
    (cell,) = cells(q, TREND)
    assert (cell["amounts"], cell["context_quote"]) == (["45"], "Revenue by product")
    assert cell["header"] == "2029 2030 Y/Y\nQ1 Q2 Q3 Q4 Q1 Q2 Growth"
    assert not cells(q, TREND.replace("Q3 Q4", "Q3 Q3"))
    assert not cells(q.replace("Hardware", "Electronics"), TREND)


def test_uppercase_statement_title_is_not_a_group_of_segment_tickers():
    statement = """CONSOLIDATED STATEMENTS OF OPERATIONS
(In millions)
Three months ended
June 30,
Six months ended
June 30,
2030 2029 2030 2029
Revenue $20 $16 $40 $35
Net income $8 $6 $12 $10
Net income attributable to non-controlling interests $2 $1 $3 $2
Net income attributable to Example Co. $6 $5 $9 $8"""
    (cell,) = cells(
        "2029 年第二季度归属于母公司的净利润是多少百万美元？",
        "Second quarter 2030 results",
        statement,
    )
    assert cell["amounts"] == ["5"] and "Example Co." in cell["quote"]
    assert data_line("Free cash flow $ (12) $ (8) $ 15 $ 17")[1] == (
        "$ (12)",
        "$ (8)",
        "$ 15",
        "$ 17",
    )


@pytest.mark.parametrize("row", ["$3.30B+5-10%", "$3.30B\n+5-10%"])
def test_unlabelled_outlook_rate_matches_both_prior_year_endpoints(row):
    question = "2030 年第二季度营收同比增长的指引区间是多少？"
    outlook = OUTLOOK.replace("$3.30B+5-10%", row)
    (cell,) = cells(question, SUMMARY, outlook)
    assert cell["amounts"] == ["5", "10"] and cell["unit"] == "%"
    assert cell["quote"] in outlook and any("3,000" in c["quote"] for c in cell["basis_evidence"])
    assert not cells(question, SUMMARY.replace("$3,000", "$2,200"), outlook)
    assert not cells(question.replace("同比", "固定汇率同比"), SUMMARY, outlook)
    assert not cells(question, SUMMARY, outlook.replace("10%", "13%"))
    (amount,) = cells("2030 年第二季度调整后 EBITDA 金额指引区间是多少百万美元？", outlook)
    assert amount["amounts"] == ["450", "470"]
    assert not cells("2030 年全年调整后 EBITDA 金额指引区间是多少百万美元？", outlook)
