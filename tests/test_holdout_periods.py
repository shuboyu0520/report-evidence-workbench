import pytest

from scripts.evaluate_holdout import matches_period


@pytest.mark.parametrize(("answer", "period", "expected"), [
    ("2026年第四季度，114,477 百万美元", "Q4", True),
    ("2026财年，114,477 百万美元", "Q4", False),
    ("2026年前三季度", "9M", True),
    ("2026年前三季度", "Q3", False),
    ("2026年第四季度和全年", "FY", False),
    ("2026财年第三季度，截至9月26日", "Q3", True),
    ("2026年9月26日余额", "2026-09-26", True),
    ("2026年9月27日余额", "2026-09-26", False),
])
def test_period_claim(answer, period, expected):
    assert matches_period(answer, period) is expected
