from decimal import Decimal

import pytest

from app.agent import dispatch, rule_calls
from app.finance import calculate, extract_metrics, numeric


def fact(name, year, value, **changes):
    return {
        "name": name,
        "year": year,
        "value": str(value),
        "currency": "CNY",
        "unit": "元",
        "scope": "consolidated_annual",
        "page": 1,
        "quote": "test evidence",
        **changes,
    }


@pytest.mark.parametrize(
    "kind,a,b,expected",
    [
        ("growth", ("revenue", 2025, 120), ("revenue", 2024, 100), "20.00"),
        ("gross_margin", ("revenue", 2025, 120), ("cost", 2025, 78), "35.00"),
        ("net_margin", ("net_profit", 2025, 18), ("revenue", 2025, 120), "15.00"),
        ("debt_ratio", ("total_liabilities", 2025, 80), ("total_assets", 2025, 200), "40.00"),
        ("cash_conversion", ("operating_cash_flow", 2025, 15), ("net_profit", 2025, 18), "83.33"),
    ],
)
def test_calculations(kind, a, b, expected):
    assert calculate([fact(*a), fact(*b)], kind, 2025)["value"] == expected


@pytest.mark.parametrize("prior", [0, -100])
def test_nonpositive_base_not_misleading(prior):
    result = calculate([fact("revenue", 2025, 120), fact("revenue", 2024, prior)], "growth", 2025)
    assert result["status"] == "unavailable"
    assert "分母非正" in result["reason"]


@pytest.mark.parametrize(
    "change", [{"currency": "USD"}, {"unit": "万元"}, {"scope": "parent_annual"}]
)
def test_scope_unit_and_currency_must_match(change):
    result = calculate(
        [fact("revenue", 2025, 120), fact("revenue", 2024, 100, **change)], "growth", 2025
    )
    assert result["status"] == "unavailable"


@pytest.mark.parametrize(
    "value,expected", [("1,200.25", "1200.25"), ("(200)", "-200"), ("−5", "-5")]
)
def test_numeric_formats(value, expected):
    assert numeric(value) == Decimal(expected)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e10", "1元", "9" * 25])
def test_invalid_numbers(value):
    with pytest.raises(ValueError):
        numeric(value)


def test_ambiguous_duplicate_tables_no_silent_overwrite():
    text = (
        "口径：合并\n期间：年度\n单位：万元\n币种：CNY\n项目 | 2025\n营业收入 | 120\n营业收入 | 100"
    )
    facts, warnings = extract_metrics([{"number": 1, "text": text}])
    assert facts == [] and "重复" in warnings[0]


def test_missing_metadata_and_parent_scope_do_not_extract():
    for text in (
        "项目 | 2025\n营业收入 | 120",
        "口径：合并\n期间：年度\n单位：万元\n币种：CNY\n母公司\n项目 | 2025\n营业收入 | 120",
    ):
        assert extract_metrics([{"number": 1, "text": text}])[0] == []


@pytest.mark.parametrize(
    "name,args",
    [
        ("shell", {}),
        ("calculate", {"kind": "growth", "year": True}),
        ("search_report", {"query": "a", "report_id": "other"}),
        ("list_metrics", {"report_id": "other"}),
    ],
)
def test_tool_allowlist_and_current_report_scope(name, args):
    with pytest.raises(ValueError):
        dispatch(name, args, [], [])


def test_extreme_valid_amounts_do_not_overflow_decimal_precision():
    result = calculate(
        [
            fact("revenue", 2025, "99999999999999999999999900000000"),
            fact("revenue", 2024, "0.000001"),
        ],
        "growth",
        2025,
    )
    assert result["status"] == "ok"


def test_unknown_growth_metric_is_not_silently_mapped_to_revenue():
    assert rule_calls("2025 年用户数同比增长", []) == []


def test_missing_year_is_not_confused_with_required_existing_year():
    result = calculate([fact("revenue", 2025, 120)], "growth", 2026)
    assert result["missing"] == [("revenue", 2026)]
    assert result["available"] == [("revenue", 2025)]
    assert "2026" in result["reason"] and "2025" not in result["reason"]
