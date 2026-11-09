import pytest

from app.earnings_tables import lookup_request, resolve_sources

SUMMARY = """The company reported third quarter 2028 results compared to the third quarter of 2027.
Q3 2028
(#) (Δ Y/Y)
Revenue $1.2B (5%)
Gross Bookings $5.4B 7%
Room Nights 64M 2%
"""
STATEMENT = """Three Months Ended
September 30,
Nine Months Ended
September 30,
2028 2027 2028 2027
Partner revenues $ 815 $ 701 $ 2,799 $ 2,409
Agency revenues 405 599 1,604 1,479
Total revenues 1,220 1,300 4,403 3,888
Net income $ 58 $ 70 $ 200 $ 274
Net income applicable to common stockholders per diluted common share $ 1.01 $ 1.21 $ 3.2 $ 3.9
8
Unaudited Consolidated Statements of
Operations
(In millions, except per share data)"""


def select(question, *pages):
    return resolve_sources(
        [{"number": i, "text": text} for i, text in enumerate(pages, 1)], lookup_request(question)
    )


def test_trailing_statement_caption_is_verbatim_and_keeps_quarter_and_ytd_separate():
    cells = select("2027 年第三季度集团总营收是多少百万美元？", SUMMARY, STATEMENT)
    assert [(c["page"], c["amounts"], c["column"]) for c in cells] == [(2, ["1,300"], 2)]
    assert cells[0]["unit_quote"] == "(In millions, except per share data)"
    assert cells[0]["unit_quote"] in STATEMENT


def test_rounding_and_per_share_measures_do_not_substitute_for_exact_totals():
    cells = select("2028 年第三季度集团营收是多少百万美元？请给精确金额。", SUMMARY, STATEMENT)
    assert [c["amounts"] for c in cells] == [["1,220"]]
    cells = select("2028 年第三季度集团净利润是多少百万美元？", SUMMARY, STATEMENT)
    assert [c["amounts"] for c in cells] == [["58"]]
    summary_with_eps = SUMMARY + "GAAP EPS $1.06 5%\n"
    diluted = select("2028 年第三季度 GAAP 摊薄每股收益是多少美元？", summary_with_eps, STATEMENT)
    assert [(c["page"], c["amounts"]) for c in diluted] == [(2, ["1.01"])]


def test_unlabelled_sales_category_never_falls_back_to_group_total():
    assert not select("2028 年第三季度代理模式的收入是多少百万美元？", SUMMARY, STATEMENT)
    cells = select(
        "2028 年第三季度合作模式的营收（Partner revenues）是多少百万美元？", SUMMARY, STATEMENT
    )
    assert [(c["label"], c["amounts"]) for c in cells] == [("Partner revenues", ["815"])]


@pytest.mark.parametrize(
    "source",
    [
        STATEMENT.replace("2028 2027 2028 2027", "2028 2027\n2028 2027 2028 2027"),
        STATEMENT.replace("Three Months Ended", "(in thousands)\nThree Months Ended"),
        STATEMENT.replace("Unaudited Consolidated Statements of", "Market discussion of"),
    ],
)
def test_scope_or_units_must_be_unambiguous(source):
    assert not any(
        "unit_quote" in c
        for c in select("2028 年第三季度集团净利润是多少百万美元？", SUMMARY, source)
    )


def test_value_and_growth_columns_bind_to_the_nearest_explicit_fiscal_period():
    assert not select("2027 年第三季度总预订额是多少十亿美元？", SUMMARY)
    assert [c["amounts"] for c in select("2028 年第三季度总预订额是多少十亿美元？", SUMMARY)] == [
        ["5.4"]
    ]
    counts = select("2028 年第三季度间夜数是多少百万间夜？", SUMMARY)
    assert [(c["amounts"], c["unit"]) for c in counts] == [(["64"], "百万间夜")]
    assert lookup_request("2028 年第三季度间夜数是多少百万美元？") is None
