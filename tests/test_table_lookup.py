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
