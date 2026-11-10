from app.earnings_tables import lookup_request, resolve_sources
from app.reader import amount_tokens

TABLE = """Comparable and Currency Neutral System-Wide Hotel Operating Statistics
Three Months Ended June 30,
Occupancy ADR RevPAR
2030 vs. 2029 2030 vs. 2029 2030 vs. 2029
System-wide 80.0 % 1.5 % pts. $ 150 0.5 % $ 120 2.4 %
Region
North 42.0 % 1.0 % pts. $ 145 1.5 % $ 60.90 2.5 %
Pacific 70 (1.2) 140 1.2 98 3.6
Brand(1)
Pacific 60.0 % 1.2 % pts. $ 140 1.2 % $ 84 3.6 %"""
NARRATIVE = """Outlook
Full Year 2030
• Adjusted EBITDA is projected to be between $90 million and $110 million.
Fourth Quarter 2030
• System-wide comparable RevPAR, on a currency neutral basis, is projected to increase between 1.2 percent and 1.8
percent compared to the fourth quarter of 2029.
• Adjusted EBITDA is projected to be between $20 million and $40 million."""
BRIDGE = """Outlook: Net Income and Adjusted EBITDA
(in millions)
Three Months Ending
December 31, 2030
Low Case High Case
Net income $ 11 $ 22
Interest expense 2 4
Adjusted EBITDA $ 20 $ 40
Year Ending
December 31, 2030
Low Case High Case
Adjusted EBITDA $ 90 $ 110"""
REGION = "按地区统计，2030 年第二季度可比酒店太平洋区（Pacific）的 RevPAR 是多少美元？"
OCCUPANCY = "2030 年第二季度全系统可比酒店入住率的百分比水平是多少？"
PCT = "2030 年第四季度全系统可比酒店 RevPAR 固定汇率同比增幅的指引区间是多少？"
EBITDA = "预计 2030 年第四季度调整后 EBITDA 金额区间是多少百万美元？"


def cells(question, *texts, calendar_year=True):
    pages = [{"number": i, "text": text} for i, text in enumerate(texts, 1)]
    return resolve_sources(pages, lookup_request(question), calendar_year=calendar_year)


def test_stats_bind_period_measure_level_region_and_unit_witness():
    assert cells(OCCUPANCY, TABLE)[0]["amounts"] == ["80.0"]
    (c,) = cells(REGION, TABLE, TABLE.replace("Three Months", "Nine Months"))
    assert (c["amounts"], c["unit"], c["column"], c["page"]) == (["98"], "美元/可售客房", 5, 1)
    assert c["basis_evidence"] == [{"page": 1, "quote": "Region"}]
    for quote in (c["quote"], c["unit_quote"], c["context_quote"], c["header"]):
        assert quote and quote in TABLE
    assert cells(REGION.replace("地区统计", "品牌统计"), TABLE)[0]["amounts"] == ["84"]
    assert not cells(OCCUPANCY, TABLE, calendar_year=False)
    assert not cells(REGION.replace("Pacific", "Islands"), TABLE)
    assert not cells(REGION, TABLE.replace("2030 vs. 2029", "2030 vs. 2028", 1))
    assert not cells(REGION, TABLE.replace("$ 60.90", "CAD 60.90"))
    assert not cells(REGION, TABLE.replace(" $ 60.90", " 60.90"))
    assert not cells(REGION, TABLE.replace("June 30", "March 31"))
    assert not cells(OCCUPANCY.replace("百分比水平", "百分点"), TABLE)
    assert not cells(OCCUPANCY.replace("全系统", "全系统亚太区"), TABLE)


def test_percent_spelling_and_currency_basis_are_independent_checks():
    assert amount_tokens("1.2%") == amount_tokens("1.2 percent") == {"1.2%"}
    assert amount_tokens("1.2 percentage points") == amount_tokens("1.2 % pts.") == {"1.2pp"}
    assert amount_tokens("1.2%") != amount_tokens("1.2 percentage points")
    (c,) = cells(PCT, NARRATIVE)
    assert c["amounts"] == ["1.2", "1.8"] and c["header"] in NARRATIVE and c["quote"] in NARRATIVE
    assert not cells(PCT, NARRATIVE.replace("currency neutral", "reported currency"))
    assert not cells(PCT, NARRATIVE.replace("quarter of 2029", "quarter of 2028"))
    assert not cells(PCT, NARRATIVE.replace("1.8\npercent", "1.8\npercentage points"))
    assert not cells(PCT.replace("第四季度", "第一季度"), NARRATIVE)


def test_quarter_outlook_corroborated_by_prose_and_separate_low_high_columns():
    actual = cells(EBITDA, NARRATIVE, BRIDGE)
    assert len(actual) == 2 and all(c["amounts"] == ["20", "40"] for c in actual)
    assert any(c["header"].endswith("Low Case High Case") and c["header"] in BRIDGE for c in actual)
    assert cells(EBITDA, BRIDGE.replace("$ 40", "$ 45"))[0]["amounts"] == ["20", "45"]
    assert not cells(EBITDA, BRIDGE.replace("(in millions)", "(in millions CAD)"))
    assert not cells(EBITDA, BRIDGE.replace("Three Months Ending", "Year Ending"))
    assert not cells(EBITDA, BRIDGE.replace("Low Case High Case", "High Case Low Case"))
    assert not cells(EBITDA, BRIDGE, calendar_year=False)
