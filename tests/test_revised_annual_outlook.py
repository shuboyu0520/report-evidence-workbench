import pytest

from app.earnings_tables import lookup_request, resolve_sources


COVER = """Raises Full-Year 2032 Adjusted EBITDA and RevPAR Outlook
We announce results for the three months ended June 30, 2032."""
OUTLOOK = """Outlook
We are updating our full-year outlook as follows:
Prior Outlook  Updated Outlook
Year-over-year global RevPAR growth (c)  (old)   (new)
Adjusted EBITDA $81 - $89 million  $85 - $93 million
(c) Represents constant currency basis; on a reported basis, growth would be 7% to 8%."""
OUTLOOK = OUTLOOK.replace("(old)", "1% - 2%").replace("(new)", "4% - 5%")
REGIONS = """Three Months
Ended
June 30,
Constant Currency
% Change (b)
Regional RevPAR Growth
International
North (a) $ 52.61 (8%)
South 39.42 5
Nine Months Ended June 30, 2032
Constant Currency % Change
Regional RevPAR Growth
International
North (a) $ 49.84 (2%)"""
RATE = "本次更新后，管理层预计 2032 全年全球 RevPAR 固定汇率同比增长区间是多少？"
MONEY = "管理层对 2032 全年调整后 EBITDA 最新指引为多少百万美元？"
ROOM = "2032 年第二季度北区（North）RevPAR 水平是多少美元？"


def run(q, table, cover=COVER, calendar=True):
    request = lookup_request(q)
    pages = [{"number": 1, "text": cover}, {"number": 2, "text": table}]
    return resolve_sources(pages, request, calendar_year=calendar) if request else []


def test_annual_outlook_resolves_by_column_title_year_and_footnote():
    (rate,) = run(RATE, OUTLOOK)
    assert rate["column"] == 2 and rate["quarter"] is None and rate["amounts"] == ["4", "5"]
    assert rate["unit"] == "%" and "固定汇率" in rate["basis"]
    for ref in rate["basis_evidence"]:
        assert ref["quote"] in {1: COVER, 2: OUTLOOK}[ref["page"]]
    assert run(RATE.replace("本次更新后", "此前"), OUTLOOK)[0]["amounts"] == ["1", "2"]
    (amount,) = run(MONEY, OUTLOOK)
    assert amount["amounts"] == ["85", "93"] and amount["unit"] == "百万美元"
    assert run(MONEY.replace("最新", "上次"), OUTLOOK)[0]["amounts"] == ["81", "89"]
    assert not run(RATE.replace("2032", "2031"), OUTLOOK)
    assert not run(RATE, OUTLOOK, cover="Year ended June 30, 2032")
    assert not run(RATE, OUTLOOK.replace("(c) Represents", "(d) Represents"))
    assert not run(
        RATE,
        OUTLOOK.replace("Represents constant currency basis", "Represents reported currency basis"),
    )
    assert not run(MONEY, OUTLOOK.replace("$85", "CA$85"))
    assert not run(
        MONEY, OUTLOOK.replace("Prior Outlook  Updated Outlook", "Updated Outlook  Updated Outlook")
    )
    assert not run(MONEY, OUTLOOK.replace("$93", "$82"))


@pytest.mark.parametrize(
    ("question", "value"), [(ROOM, "52.61"), (ROOM.replace("North", "South"), "39.42")]
)
def test_regional_amount_uses_quarter_and_level_column(question, value):
    (cell,) = run(question, REGIONS)
    assert cell["amounts"] == [value] and cell["unit"] == "美元/可售客房"
    assert cell["quote"] in REGIONS and cell["header"] in REGIONS
    assert not run(question, REGIONS.replace("2032", "2031"))
    assert not run(question, REGIONS, calendar=False)
    assert not run(question, REGIONS.replace("$ 52.61", "EUR 52.61"))
    assert not run(question, REGIONS.replace("Three Months", "Nine Months"))
    assert not run(question.replace("RevPAR", "可比酒店 RevPAR"), REGIONS)
