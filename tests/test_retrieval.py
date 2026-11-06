from app.agent import guard_model_draft, search, search_terms


def test_financial_terms_ignore_generic_question_words():
    assert search_terms("What were Apple's total assets in fiscal 2025?") == {"total", "assets"}


def test_financial_statement_line_beats_policy_distractor():
    pages = [
        {
            "number": 1,
            "text": "Revenue policy\nServices revenue is recognized over time.\n" * 8,
        },
        {
            "number": 2,
            "text": "Consolidated Statements of Operations\nProducts 307,003\nServices 109,158\nTotal net sales 416,161\n",
        },
    ]
    hits = search(pages, "How much revenue did Apple report from Services in fiscal 2025?")
    assert hits[0]["page"] == 2
    assert "Services 109,158" in hits[0]["quote"]
    assert all(hit["quote"] in pages[hit["page"] - 1]["text"] for hit in hits)


def test_chinese_finance_alias_can_find_english_source():
    pages = [{"number": 1, "text": "Total net sales 416,161\n"}]
    assert search(pages, "营业收入是多少")[0]["page"] == 1


def test_model_guard_rejects_unsupported_percentage_and_page():
    trace = [{"tool": "calculate", "result": {"status": "ok", "value": "35.00"}}]
    citations = [{"page": 1, "quote": "Gross margin 35%"}]
    assert guard_model_draft("毛利率 35%，参见第 1 页。", trace, citations) == "model_draft_unverified"
    assert guard_model_draft("毛利率 99%，参见第 1 页。", trace, citations) == "model_rejected_numeric_claim"
    assert guard_model_draft("毛利率 35%，参见第 999 页。", trace, citations) == "model_rejected_citation"
