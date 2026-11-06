from scripts.evaluate_model_ab import score_case


def fixture(origin="model"):
    spec = {"question": "2025年毛利率是多少？", "kind": "gross_margin", "year": 2025,
            "value": "46.91", "page": 32}
    result = {"answer": "2025年毛利率46.91%，第32页。", "verification": "model_draft_unverified",
              "trace": [{"origin": origin, "tool": "calculate",
                         "arguments": {"kind": "gross_margin", "year": 2025},
                         "result": {"status": "ok", "value": "46.91"}}]}
    return spec, result


def test_server_precalculation_cannot_pass_as_model_selection():
    spec, result = fixture("server")
    score = score_case(spec, result)
    assert not score["passed"]
    assert "model_did_not_call_correct_calculation" in score["failure_reasons"]
    assert score["model_tool_calls"] == 0


def test_answer_must_have_expected_value_and_physical_page():
    spec, result = fixture()
    assert score_case(spec, result)["passed"]
    result["answer"] = "2025年毛利率46.91%，第30页。"
    assert not score_case(spec, result)["passed"]
    result["answer"] = "2025年毛利率46.90%，第32页。"
    assert not score_case(spec, result)["passed"]


def test_refusal_cannot_contain_estimated_percentage():
    spec, result = fixture()
    spec.pop("value")
    spec["status"] = "unavailable"
    result["answer"] = "缺少数据，无法计算，但预计增长5%。"
    assert "percentage_given_for_missing_data" in score_case(spec, result)["failure_reasons"]
