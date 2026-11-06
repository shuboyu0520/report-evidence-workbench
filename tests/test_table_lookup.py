import asyncio
import json

import httpx
import pytest

from app.table_lookup import lookup, lookup_year, read_rows


def statement(years="2022 2023 2024", cells="123  (4,567)  890"):
    return [
        {
            "number": 17,
            "text": "CONSOLIDATED STATEMENTS OF OPERATIONS\n"
            "Amounts in thousands of U.S. dollars\n" + years + "\nOperating income  " + cells,
        }
    ]


def select(monkeypatch, pages, year, choice=1):
    client = httpx.AsyncClient

    def respond(request):
        payload = json.loads(request.content)
        assert "4,567" not in payload["messages"][1]["content"]
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": json.dumps({"row": choice})}}
        )

    monkeypatch.setattr(
        "app.table_lookup.httpx.AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(respond), **kw),
    )
    return asyncio.run(
        lookup(
            pages,
            f"{year} 财年，利润表中营业利润是多少？",
            {"model": "test", "ollama_url": "http://test"},
        )
    )


@pytest.mark.parametrize(
    "years,cells",
    [("2022 2023 2024", "123  (4,567)  890"), ("2024 2023 2022", "890  (4,567)  123")],
)
def test_reads_printed_column_sign_scale_and_physical_page(monkeypatch, years, cells):
    hits, meta = select(monkeypatch, statement(years, cells), 2023)
    assert meta["value_millions"] == "-4.567" and meta["column"] == 2
    assert meta["physical_page"] == 17 and "(4,567)" in hits[0]["quote"]


@pytest.mark.parametrize(
    "year,cells,choice,status",
    [
        (2028, "123  55  99", 1, "year_absent"),
        (2023, "123  —  99", 1, "blank_cell"),
        (2023, "123  55  99", 0, "ambiguous"),
    ],
)
def test_no_numeric_claim_for_absent_or_ambiguous_cell(monkeypatch, year, cells, choice, status):
    _, meta = select(monkeypatch, statement(cells=cells), year, choice)
    assert meta["status"] == status and "value_millions" not in meta


def test_ambiguous_duplicate_and_mismatched_width(monkeypatch):
    p = statement()
    p[0]["text"] += "\nOperating income  111  222  333\nOther revenues  123  999"
    assert len(read_rows(p)) == 2
    assert select(monkeypatch, p, 2023)[1]["status"] == "ambiguous"


def test_keep_ratio_and_multi_period_questions_on_existing_path():
    assert lookup_year("2024年比2023年营业利润增长了多少？") is None
    assert lookup_year("2025 财年净利润率为多少？") is None


def test_combined_unit_and_year_header_and_reverse_order(monkeypatch):
    page = {
        "number": 12,
        "text": "Consolidated Statements of Income\n"
        "(in millions of U.S. dollars, except per share data) 2024 2023 2022\n"
        "Operating income  101  88  76",
    }
    _, meta = select(monkeypatch, [page], 2022)
    assert meta["value_millions"] == "76" and meta["column"] == 3


def test_segment_metrics_above_the_business_name():
    page = {
        "number": 30,
        "text": "The following is information about our segments (in millions):\n"
        "Year ended December 31,\n2023 2024\nRevenue:\nServices  52  60\n"
        "Operating income (loss):\nServices  4  6",
    }
    rows = read_rows([page])
    assert [(r.scope, r.label, r.values[-1]) for r in rows] == [
        ("Revenue", "Services", "60"),
        ("Operating income (loss)", "Services", "6"),
    ]


def test_regional_tables_keep_named_scope_and_unit_at_each_header():
    pages = [{"number": 8, "text": "The following table presents sales by geographic region."},
             {"number": 9, "text":
              "Northern Europe\nYear ended December 31,\n2024 2023\n(in thousands)\n"
              "Net sales $ 12,000 $ 8,000\nSubscriber count  55  30\n"
              "South America\nYear ended December 31,\n2024 2023\n(in millions)\n"
              "Net sales $ 150 $ 70\n"
              "Other markets\nYear ended December 31,\n2024 2023\nNet sales $ 10 $ 5"}]
    assert [(r.kind, r.scope, r.scale, r.values[-1]) for r in read_rows(pages)] == [
        ("geography", "Northern Europe", "thousands", "8,000"),
        ("geography", "South America", "millions", "70"),
    ]


@pytest.mark.parametrize("subject,label", [("资产", "assets"), ("负债", "liabilities")])
def test_explicit_current_subtotal_excludes_current_and_noncurrent_components(monkeypatch, subject, label):
    pages = [{"number": 6, "text": "Consolidated Balance Sheets\n(in millions of U.S. dollars)\n"
              f"2024 2023\nOther current {label}  9  8\nTotal current {label}  56  88\n"
              f"Total non-current {label}  78  79"}]
    client = httpx.AsyncClient

    def respond(req):
        menu = json.loads(json.loads(req.content)["messages"][-1]["content"])["numbered_rows"]
        assert menu.splitlines() == [f"1. balance | consolidated | Total current {label}"]
        return httpx.Response(200, json={"message": {"content": '{"row":1}'}})

    monkeypatch.setattr("app.table_lookup.httpx.AsyncClient",
                        lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    hits, meta = asyncio.run(lookup(pages, f"2023 年合并资产负债表中流动{subject}合计是多少？",
                                  {"model": "test", "ollama_url": "http://test"}))
    assert meta["value_millions"] == "88" and hits[0]["page"] == 6


@pytest.mark.parametrize("header", ["Year Ended June 30, 2024 2023", "As of Sept. 30, 2024 2023",
                                    "December 31, 2024 2023"])
def test_inline_date_and_fiscal_years(monkeypatch, header):
    pages = statement(header, "61  (4,567)")
    hits, meta = select(monkeypatch, pages, 2023)
    assert meta["requested_year"] == 2023 and meta["column"] == 2
    assert meta["value_millions"] == "-4.567" and hits[0]["page"] == 17


def test_quarterly_date_is_not_an_annual_header():
    assert not read_rows(statement("Quarter ended March 31, 2024 2023", "2  3"))


def test_geographic_rows_stop_at_next_disclosure():
    pages = [{"number": 36, "text": "Revenue, classified by geographic areas, was as follows:\n"
              "(In millions)\nYear ended April 30, 2024 2023\nOther countries  220  102\n"
              "Property by country was as follows:\n(In millions)\nApril 30, 2024 2023\n"
              "Other countries  800  900"}]
    assert [(r.scope, r.values) for r in read_rows(pages)] == [("Revenue by geography", ("220", "102"))]


@pytest.mark.parametrize("policy,expected", [
    ("Assets and liabilities recorded in foreign currencies are translated at the closing rate.",True),
    ("Assets and liabilities recorded in foreign currencies are translated. Our reporting currency is Canadian dollars.",False),
    ("Foreign exchange derivative notionals are measured in USD.",False),
])
def test_reporting_currency_inference_requires_corroboration(monkeypatch, policy, expected):
    pages = statement("Year ended June 30, 2024 2023", "$ 100  75")
    pages[0]["text"] = pages[0]["text"].replace(" of U.S. dollars","")
    pages.append({"number": 25, "text": policy+" Fluctuations in the U.S. dollar relative to other "
                  "foreign currencies had a material impact on reported revenue."})
    result = select(monkeypatch, pages, 2023)
    if expected:
        assert result[1]["currency_page"] == 25 and result[1]["currency_basis"] == "reported_results_fx_and_translation_policy"
    else:
        assert result is None
