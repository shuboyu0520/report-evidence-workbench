from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import reader
from app.main import create_app


@pytest.mark.parametrize(
    ("question", "calendar_year", "expected"),
    [
        ("2026 年第四季度实际营收？", True, "2026-12-31"),
        ("2026 年第四季度实际营收？", False, None),
        ("2026 年第三季度实际营收？", True, None),
        ("2026 年第四季度指引？", True, None),
        ("2026 年第四季度和第二季度的实际营收？", True, None),
        ("期间结束日 2026-12-27 的实际营收？", False, "2026-12-27"),
        ("期间结束日 2026-22-45 的实际营收？", False, None),
    ],
)
def test_cutoff_requires_positive_period_evidence(question, calendar_year, expected):
    end = reader.future_end(question, date(2026, 11, 6), calendar_year)
    assert (end.isoformat() if end else None) == expected


@pytest.fixture
def api(tmp_path):
    return TestClient(
        create_app(tmp_path / "test.sqlite", {"model": "fake", "ollama_url": "http://invalid.test"})
    )


def upload(api, company, day, body=b"Consolidated statement. Revenue 215 million."):
    response = api.post(
        "/reports",
        data={"company": company, "published_on": day, "calendar_year": "true"},
        files={"file": ("input.txt", body)},
    )
    response.raise_for_status()
    return response.json()["id"]


def test_status_does_not_need_model_and_is_exportable(api):
    rid = upload(api, "Co", "2026-10-15")
    result = api.post(
        f"/reports/{rid}/questions",
        json={"mode": "reader", "question": "2026 年第四季度实际营收？", "as_of": "2026-11-06"},
    ).json()
    assert result["verification"] == "not_yet_disclosed"
    assert not result["model_trace"] and result["trace"][0]["period_end"] == "2026-12-31"
    assert (
        api.get(f"/analyses/{result['id']}/export").json()["analysis"]["question"]
        == result["question"]
    )


def test_absence_in_search_is_not_absence_of_disclosure(api, monkeypatch):
    async def no_hits(*args):
        return [], {"status": "complete"}

    monkeypatch.setattr(reader, "retrieve", no_hits)
    rid = upload(api, "Co", "2026-10-15")
    result = api.post(
        f"/reports/{rid}/questions", json={"mode": "reader", "question": "第三季度的悉尼收入呢？"}
    ).json()
    assert result["verification"] == "insufficient_evidence" and "未披露" not in result["answer"]


def test_comparison_rejects_future_or_duplicate_sources(api):
    a, b = upload(api, "early", "2026-10-15"), upload(api, "later", "2026-10-29")
    for sources in ({"company": a, "peer": b}, {"company": a, "peer": a}):
        res = api.post(
            "/reader/compare",
            json={"sources": sources, "as_of": "2026-10-26", "question": "比较营收"},
        )
        assert res.status_code == 422


def test_metadata_on_repeat_upload_is_consistent(api):
    rid = upload(api, "Co", "2026-10-15")
    assert upload(api, "Co", "2026-10-15") == rid
    response = api.post(
        "/reports",
        data={"company": "Co", "published_on": "2027-01-01"},
        files={"file": ("x.txt", b"Consolidated statement. Revenue 215 million.")},
    )
    assert response.status_code == 409


def test_public_reader_and_private_sample_are_available(api):
    assert "台积电这一季" in api.get("/reader").text
    assert "919.77" in api.get("/reader/case.txt").text
