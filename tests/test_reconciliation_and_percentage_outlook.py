import pytest

from app.earnings_tables import lookup_request, resolve_sources
from app.growth_guidance import growth_column_positions


DATES = "Three Months Ended\nJune 30,\nSix Months Ended\nJune 30,\n2028 2027 2028 2027"
ANCHOR = "Net income $ 100 $ 99 $ 300 $ 299"
OPENING = f"""RECONCILIATION OF NET INCOME TO ADJUSTED NET INCOME
{DATES}
{ANCHOR}
Adjusted net income $ 131 $ 109 $ 451 $ 375
6
Reconciliation of GAAP to Non-GAAP
Financial Information
(In thousands, except per share data)(1)
(Unaudited)"""
CONTINUED = f"""RECONCILIATION OF NET INCOME TO ADJUSTED EBITDA
{DATES}
{ANCHOR}
(i) Change in fair value of an adjustment for a new
contract $ 13 $ 15 $ 19 $ 20
Adjusted EBITDA $ 120 $ 150 $ 355 $ 365
RECONCILIATION OF OPERATING CASH FLOW
TO FREE CASH FLOW
{DATES}
Operating cash flow $ 172 $ 191 $ 270 $ 301
Free cash flow $ 140 $ 160 $ 211 $ 288
TTM Free cash flow $ 810 $ 820 $ 990 $ 910
7
(Unaudited)"""


def doc_pages(*texts):
    return [dict(number=i, text=text) for i, text in enumerate(("Second quarter 2028 results", *texts), 1)]


@pytest.mark.parametrize(
    ("metric", "value"), [("单季自由现金流", "0.16"), ("调整后 EBITDA", "0.15")]
)
def test_continued_scale_and_previous_year_with_wrapped_intermediate_lines(metric, value):
    request = lookup_request(f"2027 年第二季度{metric}是多少百万美元？")
    candidates = resolve_sources(doc_pages(OPENING, CONTINUED), request)
    assert len(candidates) == 1
    cell = candidates[0]
    assert (cell["year"], cell["quarter"], cell["column"], cell["amounts"]) == (2027, 2, 2, [value])
    assert cell["page"] == 3 and cell["unit_page"] == 2
    assert cell["unit_quote"] in OPENING and cell["quote"] in CONTINUED
    assert cell["header"] == DATES


@pytest.mark.parametrize(
    "alteration",
    [
        lambda p: p.replace(ANCHOR, ANCHOR.replace("100", "104")),
        lambda p: p.replace("June 30", "September 30"),
        lambda p: p + "\nAmounts in billions",
        lambda p: p.replace("Net income $", "Net income CAD $"),
        lambda p: p.replace("RECONCILIATION OF NET INCOME", "UNRELATED SUMMARY"),
    ],
)
def test_no_unsupported_scale_across_sections(alteration):
    req = lookup_request("2028 年第二季度调整后 EBITDA 是多少百万美元？")
    assert not resolve_sources(doc_pages(OPENING, alteration(CONTINUED)), req)


def test_no_carry_across_an_intervening_page():
    req = lookup_request("2028 年第二季度调整后 EBITDA 是多少百万美元？")
    assert not resolve_sources(doc_pages(OPENING, "Notes", CONTINUED), req)


def grid(*rows):
    return "\n".join(f"{label:52}{q:<24}{fy}" for label, q, fy in rows)


def guide_data(sparse_annual=False, positions=True):
    hdr = "(Growth is on a year-over-year basis)"
    layout = grid(
        (hdr, "Q2 2028", "FY 2028"),
        (
            "Room Nights Growth",
            "" if sparse_annual else "2% - 4%",
            "8% - 9%" if sparse_annual else "",
        ),
        ("Gross Bookings Growth", "3% - 5%", "8% - 9%"),
        ("Constant Currency Gross Bookings Growth", "6% - 8%", "High Single Digits"),
    )
    lines = [" ".join(line.split()) for line in layout.splitlines()]
    page = dict(number=2, text="Financial Outlook\n" + "\n".join(lines))
    if positions:
        page["growth_columns"] = growth_column_positions(layout)
    return [page]


def test_sparse_outlook_needs_evidence_of_column_and_fy_cannot_answer_quarter():
    req = lookup_request("2028 年第二季度间夜数同比增长指引区间是多少？")
    assert resolve_sources(guide_data(), req)[0]["amounts"] == ["2", "4"]
    assert not resolve_sources(guide_data(positions=False), req)
    assert not resolve_sources(guide_data(sparse_annual=True), req)


def test_reported_constant_currency_and_annual_columns():
    pages = guide_data()
    for basis, values in [("固定汇率", ["6", "8"]), ("", ["3", "5"])]:
        req = lookup_request(f"2028 年第二季度{basis}总预订额同比增长指引区间是多少？")
        (cell,) = resolve_sources(pages, req)
        assert cell["amounts"] == values and cell["unit"] == "%" and cell["column"] == 1
        assert cell["quote"] in pages[0]["text"] and "year-over-year" in cell["header"]
    req = lookup_request("2028 全年固定汇率总预订额同比增长指引区间是多少？")
    assert not resolve_sources(pages, req)
    wrong = guide_data()
    wrong[0]["text"] = wrong[0]["text"].replace("year-over-year", "quarter-over-quarter")
    assert not resolve_sources(
        wrong, lookup_request("2028 年第二季度间夜数同比增长指引区间是多少？")
    )
