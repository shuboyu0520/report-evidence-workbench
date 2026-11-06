"""Protect amount columns when optional growth columns are empty in a PDF."""

from app.earnings_tables import lookup_request, resolve_sources

SAMPLE = """Third Quarter Results
Financial highlights for third quarter 2027
Three Months Ended September 30,
(In millions, except per share)  2026  2027  % Change  % Change (Constant Currency)
Revenue  $ 105  $ 110  5 %  2 %
GAAP Income from operations  $ 50  $ 60  20 %
Non-GAAP Operating Income (1)  $ 53  $ 63  19 %
GAAP Diluted EPS  $ 3.4  $ 1.1  (68) %
Diluted weighted-average shares outstanding  28,000  28,600  2 %
"""


def amounts(query):
    cells = resolve_sources([{"number": 1, "text": SAMPLE}], lookup_request(query))
    return [c["amounts"] for c in cells]


def test_nullable_trailing_percent_and_footnote_cannot_move_a_year():
    assert amounts("2027 年第三季度 GAAP 经营利润是多少百万美元？") == [["60"]]
    assert amounts("2027 年第三季度非 GAAP 经营利润是多少百万美元？") == [["63"]]


def test_diluted_shares_are_excluded_and_parenthesized_percent_is_not_an_amount():
    assert amounts("2027 年第三季度 GAAP 摊薄每股收益是多少美元？") == [["1.1"]]
