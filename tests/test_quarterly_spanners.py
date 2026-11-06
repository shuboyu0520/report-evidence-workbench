"""Synthetic reports use different years, figures, and period orders from the replay."""

import pytest

from app.earnings_tables import lookup_request, resolve_sources

GRID = """Quarterly Summary
2027 2028
Q3 Q4 Q1 Q2
Nights and
Seats Booked 41.0M 42.0M 43.0M 44.0M
Gross Booking Value $5.0B $6.5B $7.0B $8.0B
Gross Booking Value per
Night and Seats Booked
(or ADR)
$180.33 $181.44 $182.11 $183.04
Revenue $155M $160M $170M $191M
Adjusted EBITDA $9M $10M $11M $12M"""


def select(question, *texts):
    pages = [{"number": i, "text": text} for i, text in enumerate(texts, 1)]
    return resolve_sources(pages, lookup_request(question))


@pytest.mark.parametrize(
    "q,amount",
    [
        ("2027 年第四季度集团营收是多少百万美元？", "160"),
        ("2028 年第二季度预订住宿晚数（Nights and Seats Booked）是多少百万个？", "44.0"),
        ("2028 年第二季度 ADR 平均预订价格是多少美元？", "183.04"),
        ("2028 年第一季度 Gross Booking Value 是多少十亿美元？", "7.0"),
        ("2028 年第二季度调整后 EBITDA 是多少百万美元？", "12"),
    ],
)
def test_year_band_and_wrapped_metrics(q, amount):
    cells = select(q, GRID)
    assert len(cells) == 1 and cells[0]["amounts"] == [amount]
    assert " ".join(cells[0]["quote"].split()) in " ".join(GRID.split())
    assert cells[0]["header"] in GRID


@pytest.mark.parametrize("broken", ["Q3 Q4 Q2 Q3", "Q1 Q2 Q3 Q4", "Q3 Q4 Q1"])
def test_damaged_spanners_abstain(broken):
    assert not select(
        "2028 年第二季度集团营收是多少百万美元？", GRID.replace("Q3 Q4 Q1 Q2", broken)
    )


STATEMENT = """Consolidated Statements of Operations
(in millions, except per share data)
(2) Includes stock-based compensation as follows:
Three Months Ended
June 30
Six Months Ended
June 30
2027 2028 2027 2028
Revenue $123 $150 $234 $290
Costs and expenses:
Product development (2) 24 35 45 67
Net income 21 25 42 48
Net income per share:
Basic $1.14 $1.15 $2.14 $2.15
Diluted $1.10 $1.11 $2.10 $2.11
Weighted-average shares used in computing
earnings per share:
Basic 12 14 12 14
Diluted 15 17 15 17
Three Months Ended
June 30
Six Months Ended
June 30
2027 2028 2027 2028
Product development $7 $8 $11 $12
Stock-based compensation expense $8 $9 $12 $13"""


def test_main_cost_section_and_eps_do_not_use_components_or_share_count():
    cover = "Q2 2028 Shareholder Letter"
    result = select("2028 年第二季度集团产品开发费用是多少百万美元？", "", cover, STATEMENT)
    assert [(c["amounts"], c["context_quote"]) for c in result] == [(["35"], "Costs and expenses:")]
    eps = select("2028 年第二季度 GAAP 摊薄每股收益是多少美元？", "", cover, STATEMENT)
    assert [(c["amounts"], c["context_quote"]) for c in eps] == [
        (["1.11"], "Net income per share:")
    ]
    subset = STATEMENT.split("Diluted 15 17 15 17")[1]
    assert not select("2028 年第二季度集团产品开发费用是多少百万美元？", "", cover, subset)


def test_scoped_count_cannot_turn_into_currency():
    assert not select("2028 年第二季度预订住宿晚数是多少百万个？", GRID.replace("44.0M", "$44.0M"))


def test_outlook_subhead_requires_a_forecast_section_and_excludes_historical_comparisons():
    text = """Outlook
Q2 2028
¦ We expect to generate revenue of $218 million to $224 million, representing growth of 3% to 4%.
Financial Results
Q3 2028
We expect to generate revenue of $10 million to $15 million."""
    cells = select("2028 年第二季度营收指引是多少百万美元？", text)
    assert [(c["amounts"], c["header"]) for c in cells] == [(["218", "224"], "Q2 2028")]
    assert not select("2028 年第三季度营收指引是多少百万美元？", text)
