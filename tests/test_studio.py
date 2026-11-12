from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "studio.db", {"model": "", "ollama_url": ""})


def fields():
    return {"description": "晚餐", "amount": "100.01", "currency": "CNY", "payer": 11,
            "people": [13, 11, 12]}


def test_draft_is_separate_from_posting_and_scoped_to_session(app):
    a, b = TestClient(app), TestClient(app)
    for client in (a, b):
        assert client.post("/api/studio/session").status_code == 200
    assert 'name="studio-runtime" content="service"' in a.get("/studio/splitagent.html").text
    assert 'name="studio-runtime" content="service"' in a.get("/studio/evidence-review.html").text
    assert a.post("/api/studio/drafts/parse", json={"text": "分两笔录入。"}).json()["blocked"]
    draft = a.post("/api/studio/drafts/parse", json={
        "text": "小吴替小林和小周支付 100.01 元，三人分摊。", "proposal": fields()
    }).json()["data"]
    assert draft["payer"] is None
    assert a.get("/api/studio/entries").json() == []
    body = {"id": str(uuid4()), "data": fields()}
    first = a.post("/api/studio/entries", json=body)
    assert first.status_code == 200 and not first.json()["reused"]
    assert [x["cents"] for x in first.json()["quote"]["shares"]] == [3334, 3334, 3333]
    assert a.post("/api/studio/entries", json=body).json()["reused"]
    body["data"]["amount"] = "99.00"
    assert a.post("/api/studio/entries", json=body).status_code == 409
    assert len(a.get("/api/studio/entries").json()) == 1
    assert b.get("/api/studio/entries").json() == []
    assert TestClient(app).get("/api/studio/entries").status_code == 401


@pytest.mark.parametrize("field,value", [
    ("amount", "0"), ("amount", "22.335"), ("amount", "-11"), ("currency", "JPY"),
    ("payer", 99), ("people", [11, 11]), ("people", []), ("people", [42]),
])
def test_invalid_quote_never_creates_entry(app, field, value):
    client = TestClient(app)
    client.post("/api/studio/session")
    data = {**fields(), field: value}
    assert client.post("/api/studio/drafts/quote", json=data).status_code == 422
    assert client.post("/api/studio/entries", json={"id": str(uuid4()), "data": data}).status_code == 422
    assert client.get("/api/studio/entries").json() == []


def test_concurrent_confirmation(app):
    client = TestClient(app)
    cookie = client.post("/api/studio/session").cookies.get("studio_session")
    payload = {"id": str(uuid4()), "data": fields()}

    def confirm(_):
        with TestClient(app, cookies={"studio_session": cookie}) as session:
            response = session.post("/api/studio/entries", json=payload)
            response.raise_for_status()
            return response.json()["reused"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sorted(pool.map(confirm, range(6))) == [False, True, True, True, True, True]
    assert len(client.get("/api/studio/entries").json()) == 1
