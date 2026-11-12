from app.earnings_tables import OUTPUT_UNITS, SCALE_FACTORS, lookup_request
from app.quarterly_statements import statement_cells


def cells(text, metric="集团营业收入", *, fiscal=2031, calendar=False, unit="百万美元"):
    req = lookup_request(f"EX {fiscal}财年第一季度的{metric}是多少{unit}？", issuer="EX")
    assert req is not None and not req.groups
    return statement_cells(
        [{"number": 1, "text": text}], req, calendar, SCALE_FACTORS, OUTPUT_UNITS
    )


GROUP = """Q1 2031 Summary P&L | GAAP
$ in thousands Q1’31 Q1’30 Y/Y Q4’30 Q/Q
Revenue $21,220 $18,090 Up 17% $19,600 Up 8%"""
SEGMENT = """Q1 2031 Segment Results
$ in thousands Q1’31 Q1’30 Y/Y Q4’30 Q/Q
Data Center
Net Revenue $9,200 $7,800 Up 18% $8,400 Up 10%
Gaming
Net Revenue $4,300 $3,800 Up 13% $3,400 Up 26%"""


def test_group_and_segment_have_separate_scope_and_currency_scale():
    text = GROUP + "\n" + SEGMENT
    assert [c["amounts"] for c in cells(text)] == [["21.22"]]
    (row,) = cells(text, "Data Center 数据中心分部净营收")
    assert row["amounts"] == ["9.2"]
    assert row["context_quote"] == "Data Center"
    assert row["raw_cell"] == ["$9,200"]
    assert not cells(SEGMENT)
    assert not cells(GROUP.replace("$ in thousands", "$"))
    assert not cells(GROUP.replace("$21,220", "$21.22B"))
    assert not cells(GROUP.replace("$ in thousands", "CAD in thousands"))


def test_adjacent_partial_section_does_not_borrow_preceding_title_or_unit():
    text = (
        GROUP
        + "\nData Center\n$ in thousands Q1’31 Q1’30 Y/Y Q4’30 Q/Q\nRevenue $6,000 $5,000 Up 20% $4,000 Up 50%"
    )
    assert [c["amounts"] for c in cells(text)] == [["21.22"]]
    assert not cells(GROUP.replace("Q1 2031 Summary P&L", "Data Center Summary P&L"))
    assert not cells(GROUP.replace("Q1 2031 Summary P&L | GAAP", "Q1 2031 Summary P&L | Non-GAAP"))


def test_vertical_html_table_needs_fiscal_label_and_matching_date():
    statement = """Earnings Release FY31 Q1
For the quarter ended September 30, 2030.
PRODUCT AND SERVICE OFFERINGS REVENUE
(In millions)
Three Months Ended
September 30,
2030
2029
ExampleCloud
$3,222
$2,101"""
    (row,) = cells(statement, "ExampleCloud 单项营业收入")
    assert (row["amounts"], row["quote"]) == (["3,222"], "ExampleCloud\n$3,222\n$2,101")
    assert not cells(statement, "ExampleCloud 单项营业收入", fiscal=2030)
    assert not cells(
        statement.replace("September 30,", "December 31,", 1), "ExampleCloud 单项营业收入"
    )
    assert not cells(statement)


def test_signed_cash_flow_chooses_quarter_and_rejects_ytd():
    statement = """For the quarter ended March 31, 2031.
Reconciliation of GAAP to Non-GAAP Results
($ in millions)
Three Months Ended March 31, Nine Months Ended March 31,
2031 2030 2031 2030
Free cash flow $ (590) $ 400 $ 2,101 $ 1,340"""
    (row,) = cells(statement, "自由现金流", calendar=True)
    assert row["amounts"] == ["-590"]
    assert not cells(statement.replace("Three Months", "Nine Months"), "自由现金流", calendar=True)
    assert not cells(
        statement.replace("2031 2030 2031 2030", "2031 2030 2030 2029"), "自由现金流", calendar=True
    )
