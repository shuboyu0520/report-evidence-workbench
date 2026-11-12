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


@pytest.mark.parametrize("mode,values,expected", [
    ("exact", ["0", "65.75", "34.26"], [0, 6575, 3426]),
    ("percentage", ["50", "25", "25"], [5001, 2500, 2500]),
    ("ratio", ["1", "1", "4"], [1667, 1667, 6667]),
    ("percentage", ["0", "50", "50"], [0, 5001, 5000]),
    ("ratio", ["999998", "999999", "999999"], [3333, 3334, 3334]),
])
def test_uneven_preview_commit_and_reread(app, mode, values, expected):
    c = TestClient(app)
    c.post("/api/studio/session")
    data = {**fields(), "split_mode": mode, "split_values": dict(zip(["11", "12", "13"], values))}
    quoted = c.post("/api/studio/drafts/quote", json=data).json()
    assert [s["cents"] for s in quoted["shares"]] == expected
    assert c.get("/api/studio/entries").json() == []
    payload = {"id": str(uuid4()), "data": data}
    assert c.post("/api/studio/entries", json=payload).json()["quote"] == quoted
    assert c.post("/api/studio/entries", json=payload).json()["reused"]
    original = c.get("/api/studio/entries").json()[0]
    assert original["split_values"] == data["split_values"] and original["split_mode"] == mode
    payload["data"] = fields()
    assert c.post("/api/studio/entries", json=payload).status_code == 409


@pytest.mark.parametrize("mode,values", [
    ("exact", {"11":"99.99","12":"0","13":"0"}),
    ("percentage", {"11":"25","12":"75"}),
    ("percentage", {"11":"25","12":"75","13":"-1"}),
    ("percentage", {"11":"0.001","12":"100","13":"0"}),
    ("ratio", {"11":"1","12":"0","13":"2"}),
    ("ratio", {"11":"1","12":"1.5","13":"2"}),
    ("ratio", {"11":"1","12":"1","14":"2"}),
    ("", {}), ("equal", {"11":"1"}),
])
def test_incomplete_allocations_do_not_change_ledger(app, mode, values):
    c = TestClient(app)
    c.post("/api/studio/session")
    data = {**fields(), "split_mode": mode, "split_values": values}
    assert c.post("/api/studio/drafts/quote", json=data).status_code == 422
    assert c.post("/api/studio/entries", json={"id": str(uuid4()), "data": data}).status_code == 422
    assert c.get("/api/studio/entries").json() == []


@pytest.mark.parametrize("sentence,mode,expected", [
    ("小林垫付了 120 元晚餐，小林承担 80 元，小周承担 40 元。", "exact", [8000,4000]),
    ("小林付了 100.01 元房租，小周60%，小陈40%。", "percentage", [6001,4000]),
    ("小林付了 100.01 元晚餐，小陈和小周按 2:1 分摊。", "ratio", [3334,6667]),
    ("小林付了 100.01 元晚餐，按 2:1 由小陈和小周分摊。", "ratio", [3334,6667]),
    ("小林垫付房租 1,200 澳元，小林承担 60%，小周承担 40%。", "percentage", [72000,48000]),
    ("小陈付了 100 元住宿，小陈 1 份，小周 3 份。", "ratio", [7500,2500]),
    ("小林付了 100 元房租，三人按份数，小周 2 份。", "ratio", None),
    ("小林付了 99 元晚餐，小林和小周不均分，比例还没确定。", "", None),
])
def test_uneven_extraction_uses_original_terms(app, sentence, mode, expected):
    c = TestClient(app)
    response = c.post("/api/studio/drafts/parse", json={"text": sentence}).json()
    assert not response["blocked"]
    data = response["data"]
    assert data["split_mode"] == mode
    result = c.post("/api/studio/drafts/quote", json=data)
    if expected is None:
        assert result.status_code == 422
    else:
        assert [s["cents"] for s in result.json()["shares"]] == expected


@pytest.mark.parametrize("sentence", [
    "小林付了 1.2 万澳元房租，全组均分。", "小林付了 12,00 澳元房租，三人均摊。",
    "小林付了 100 澳元晚餐，小周和小吴均分。", "小林付了 100 澳元晚餐，全组均分，小陈不参加。",
    "小林付了 100 澳元晚餐，小周2份，小林1份，小陈的份额待定。",
    "小林付了100澳元晚餐，又付了100澳元房租，全组均分。",
    "小林垫付 99 澳元酒店，小周2份，小林1份，小吴也一起住，份数未定。",
])
def test_unclear_bill_never_becomes_a_ready_draft(app, sentence):
    c = TestClient(app)
    result = c.post("/api/studio/drafts/parse", json={"text": sentence}).json()
    assert result["blocked"] or c.post("/api/studio/drafts/quote", json=result["data"]).status_code == 422
