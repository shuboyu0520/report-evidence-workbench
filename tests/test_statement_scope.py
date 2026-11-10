import pytest

from app.earnings_tables import lookup_request, resolve_sources


STATEMENT = """CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS
(in millions)
Three Months Ended Nine Months Ended
September 30, September 30,
2031 2030 2031 2030
Revenues
Service fees $ 22 $ 18 $ 67 $ 53
Operations 90 85 272 260
Total revenues 112 103 339 313
Expenses
Operations 54 39 115 111
Total expenses 54 39 115 111
Operating income 58 64 224 202
Interest expense (9) (8) (25) (24)
Other non-operating income (loss), net 2 4 6 8
Net income 42 40 116 111
Net income attributable to shareholders 39 36 99 98"""

BRIDGE = """RECONCILIATIONS OF NON-GAAP FINANCIAL MEASURES
NET INCOME MARGIN AND
ADJUSTED EBITDA AND ADJUSTED EBITDA MARGIN
(dollars in millions)
Three Months Ended Nine Months Ended
September 30, September 30,
2031 2030 2031 2030
Net income $ 42 $ 40 $ 116 $ 111
Interest expense 9 8 25 24
Adjusted EBITDA $ 70 $ 76 $ 220 $ 211"""


def find(question, *docs):
    texts = ["Third quarter 2031 financial results", *docs]
    pages = [{"number": i, "text": text} for i, text in enumerate(texts, 1)]
    return resolve_sources(pages, lookup_request(question))


@pytest.mark.parametrize(
    ("question", "value", "page"),
    [
        ("2031 年第三季度服务费（Service fees）收入是多少百万美元？", "22", 2),
        ("2031 年第三季度运营（Operations）列在收入项下的金额是多少百万美元？", "90", 2),
        ("2031 年第三季度合并利润表的利息费用是多少百万美元？", "-9", 2),
        ("2031 年第三季度营业利润是多少百万美元？", "58", 2),
        ("2031 年第三季度集团总费用是多少百万美元？", "54", 2),
        ("2030 年第三季度按分配给非控股权益前的合并口径，净利润是多少百万美元？", "40", 2),
        ("2031 年第三季度调整后 EBITDA 金额是多少百万美元？", "70", 3),
    ],
)
def test_statement_measure_scope_and_reconciliation_basis(question, value, page):
    (cell,) = find(question, STATEMENT, BRIDGE)
    assert cell["amounts"] == [value] and cell["page"] == page
    assert cell["quote"] in (STATEMENT, BRIDGE)[page - 2]
    if "收入" in question:
        assert cell["context_quote"] == "Revenues"


def test_missing_revenue_line_cannot_fall_back_to_total_or_an_expense():
    named = "2031 年第三季度运营（Operations）列在收入项下的金额是多少百万美元？"
    expense_only = STATEMENT.replace("Operations 90 85 272 260\n", "")
    assert find(named, expense_only) == []
    assert find("2031 年第三季度其他服务费收入是多少百万美元？", STATEMENT) == []


def test_reported_interest_expense_cannot_use_an_addback_or_move_across_a_heading():
    question = "2031 年第三季度合并利润表的利息费用是多少百万美元？"
    assert not find(question, BRIDGE)
    merged = STATEMENT.replace("Interest expense (9) (8) (25) (24)\n", "")
    merged += "\nReconciliation of net income to EBITDA\nInterest expense 9 8 25 24"
    assert not find(question, merged)
    assert find(question, STATEMENT.replace("(9) (8)", "(37) (8)"))[0]["amounts"] == ["-37"]
    assert not find("2031 年第三季度 EBITDA 调节表加回的利息费用是多少百万美元？", STATEMENT, BRIDGE)
    assert find("2031 年第三季度利息支出是多少？按利润表，别用 EBITDA 加回。", STATEMENT, BRIDGE)[0]["amounts"] == ["-9"]


def test_named_subtotal_can_precede_or_follow_the_revenue_section_description():
    assert find("2031 年第三季度利润表收入项下的运营（Operations）是多少？", STATEMENT)[0]["amounts"] == ["90"]
    assert find("2031 年第三季度服务费（Service fees）的销售额是多少？", STATEMENT)[0]["amounts"] == ["22"]


@pytest.mark.parametrize("line", ["人员总费用", "研发总费用", "营销费用合计", "运输费用总额"])
def test_scoped_expenses_are_not_consolidated_expenses(line):
    question = f"2031 年第三季度集团{line}是多少百万美元？"
    req = lookup_request(question)
    assert req is None or req.metric != "total_expenses"


@pytest.mark.parametrize(
    "term",
    [
        "personnel total expenses",
        "total expenses for personnel",
        "total expenses of the transport division",
        "营销费用合计（Total expenses）",
        "集团总费用（Total expenses），只看研发",
    ],
)
def test_explicit_total_label_does_not_cancel_a_narrower_expense_scope(term):
    assert not find(f"2031 Q3 {term} 是多少百万美元？", STATEMENT)


def test_unqualified_english_total_expenses_in_the_quarter():
    assert find("What were the consolidated total expenses in Q3 2031?", STATEMENT)[0]["amounts"] == ["54"]
