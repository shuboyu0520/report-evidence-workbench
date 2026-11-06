import pytest

from app.agent import guard_model_draft


@pytest.mark.parametrize("answer,expected", [
    ("2024年营业成本同比增长率为-1.77%，第32页。", "model_draft_unverified"),
    ("2024年营业成本同比增长率为1.77%，第32页。", "model_rejected_numeric_claim"),
])
def test_negative_percentage_after_chinese_text(answer, expected):
    trace = [{"tool": "calculate", "result": {"status": "ok", "value": "-1.77"}}]
    assert guard_model_draft(answer, trace, [{"page": 32}]) == expected
