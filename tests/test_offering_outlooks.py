"""Offering names repeat under different measures; outlook ranges also appear in prose."""

import pytest

from app.earnings_tables import lookup_request, resolve_sources

PAGE = """Second Quarter Results
Results by Offering and Segment
Gross Bookings
Three Months Ended June 30,
(in millions)  2027  2028  Change
Gross Bookings:
River Express  $110  $120  9%
Harbor  210  220  5%
Revenue
Three Months Ended June 30,
(in millions)  2027  2028  Change
Revenue:
River Express  $11  $12  9%
Harbor  21  22  5%
Outlook for Q3 2028
For Q3 2028, we anticipate:
• Gross Bookings of $950 million to
$1.1 billion, representing growth of 12% to 16%.
• Non-GAAP EPS of $0.72 to $0.81, representing growth of 5% to 7%.
Third Quarter Results
• GAAP EPS of $8 to $9.
"""


def select(q, text=PAGE):
    return resolve_sources([{"number": 7, "text": text}], lookup_request(q))


@pytest.mark.parametrize(
    "name,query,amount,heading",
    [
        ("River Express", "总预订额（Gross Bookings）", "120", "Gross Bookings"),
        ("River Express", "营收", "12", "Revenue"),
        ("Harbor", "营收", "22", "Revenue"),
        ("Harbor", "总预订额", "220", "Gross Bookings"),
    ],
)
def test_measure_and_printed_offering_must_both_match(name, query, amount, heading):
    cells = select(f"2028 年第二季度 {name} 业务的{query}是多少百万美元？")
    assert [(c["amounts"], c["measure_caption"]) for c in cells] == [([amount], heading)]
    assert name in cells[0]["quote"]


@pytest.mark.parametrize(
    "text,expected",
    [
        (PAGE, ["950", "1,100.0"]),
        (
            PAGE.replace("$950 million to\n$1.1 billion", "$0.95 to $1.1 billion"),
            ["950.00", "1,100.0"],
        ),
    ],
)
def test_wrapped_outlook_uses_both_currency_bounds_and_ignores_growth(text, expected):
    cells = select("2028 年第三季度总预订额指引区间是多少百万美元？", text)
    assert [c["amounts"] for c in cells] == [expected]
    for key in ("quote", "header"):
        assert " ".join(cells[0][key].split()) in " ".join(text.split())


def test_eps_keeps_per_share_units():
    cells = select("2028 年第三季度非 GAAP 每股收益指引是多少美元？")
    assert [(c["amounts"], c["unit"]) for c in cells] == [(["0.72", "0.81"], "美元/股")]


@pytest.mark.parametrize(
    "q",
    [
        "2028 年第三季度 GAAP 每股收益指引是多少美元？",
        "2027 年第三季度非 GAAP 每股收益指引是多少美元？",
        "2028 年第一季度总预订额指引是多少十亿美元？",
        "2028 年第二季度 Ghost 业务的营收是多少百万美元？",
        "2028 年第二季度单独来自悉尼市的 River Express 业务的营收是多少百万美元？",
    ],
)
def test_wrong_basis_period_or_slice_has_no_eligible_evidence(q):
    assert not select(q)


def test_do_not_substitute_bookings_for_missing_revenue_or_take_a_reversed_range():
    assert not select(
        "2028 年第二季度 Harbor 业务的营收是多少百万美元？", PAGE.split("\nRevenue\n")[0]
    )
    assert not select(
        "2028 年第三季度总预订额指引是多少百万美元？", PAGE.replace("$950 million", "$1.4 billion")
    )
