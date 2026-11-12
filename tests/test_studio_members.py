import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

BASE = "/api/studio"


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "ledger.db", {"model": "", "ollama_url": ""})


def visitor(app):
    client = TestClient(app)
    client.post(f"{BASE}/session").raise_for_status()
    return client


def bill(**fields):
    return {
        "description": "餐费",
        "amount": "61.01",
        "currency": "CNY",
        "payer": 11,
        "people": [11, 12],
        **fields,
    }


def test_roster_names_ids_and_privacy(app):
    a, b = visitor(app), visitor(app)
    assert [r["id"] for r in a.get(f"{BASE}/members").json()] == [11, 12, 13]
    member = a.post(f"{BASE}/members", json={"name": " Ａlice "}).json()
    assert member == {"id": 14, "name": "Alice", "active": True, "version": 1}
    assert a.post(f"{BASE}/members", json={"name": "ALICE"}).status_code == 409
    assert a.post(f"{BASE}/members", json={"name": "A\nB"}).status_code == 422
    url = f"{BASE}/members/14"
    assert b.put(url, json={"version": 1, "active": False}).status_code == 404
    assert a.put(url, json={"version": 1, "name": "阿雪", "active": False}).json() == {
        "id": 14,
        "name": "阿雪",
        "active": False,
        "version": 2,
    }
    assert a.post(f"{BASE}/members", json={"name": "阿雪"}).status_code == 409
    assert a.put(url, json={"version": 1, "name": "其他"}).status_code == 409
    assert a.post(f"{BASE}/members", json={"name": "小林"}).status_code == 409
    assert a.put(url, json={"version": 2, "active": True}).json()["version"] == 3
    assert a.post(f"{BASE}/session").json()["members"]["14"] == "阿雪"
    assert "14" not in b.post(f"{BASE}/session").json()["members"]


def test_save_and_clear_unfinished_draft(app):
    a, b = visitor(app), visitor(app)
    url = f"{BASE}/draft"
    data = {"raw": "今晚聚餐", "fields": {"amount": "", "people": [11]}, "editId": None}
    empty = {"version": 0, "draft": None}
    assert a.get(url).json() == empty
    assert a.put(url, json={"version": 0, "draft": data}).json() == {"draft": data, "version": 1}
    assert b.get(url).json() == empty
    assert a.get(f"{BASE}/entries").json() == []
    with TestClient(app, cookies={"studio_session": a.cookies.get("studio_session")}) as other_tab:
        assert other_tab.get(url).json()["draft"] == data
        assert other_tab.put(url, json={"version": 0, "draft": {}}).status_code == 409
        assert other_tab.delete(url, params={"version": 0}).status_code == 409
    assert a.delete(url, params={"version": 1}).json() == {"version": 2, "draft": None}
    assert a.put(url, json={"version": 1, "draft": data}).status_code == 409
    assert a.put(url, json={"version": 2, "draft": {"note": "支" * 6000}}).status_code == 422
    assert a.get(url).json() == {"version": 2, "draft": None}
    assert TestClient(app).get(url).status_code == 401


def test_edit_retains_only_preexisting_archived_roles(app):
    a, b = visitor(app), visitor(app)
    uid = str(uuid4())
    url = f"{BASE}/entries/{uid}"
    data = bill(people=[12, 13])
    original = a.post(f"{BASE}/entries", json={"id": uid, "data": data}).json()
    for who in (11, 12):
        a.put(f"{BASE}/members/{who}", json={"version": 1, "active": False}).raise_for_status()
    assert a.post(f"{BASE}/entries", json={"id": uid, "data": data}).json()["reused"]
    assert a.post(f"{BASE}/entries", json={"id": str(uuid4()), "data": data}).status_code == 422
    for edit in [bill(payer=12, people=[12, 13]), bill(people=[11, 13])]:
        assert a.put(url, json={"version": 1, "data": edit}).status_code == 422
        assert a.post(f"{BASE}/drafts/quote?entry_id={uid}", json=edit).status_code == 422
    edit = {
        **data,
        "amount": "130.01",
        "split_mode": "ratio",
        "split_values": {"12": "2", "13": "1"},
    }
    assert a.post(f"{BASE}/drafts/quote", json=edit).status_code == 422
    preview = a.post(f"{BASE}/drafts/quote?entry_id={uid}", json=edit).json()
    assert b.post(f"{BASE}/drafts/quote?entry_id={uid}", json=edit).status_code == 404
    assert b.put(url, json={"version": 1, "data": edit}).status_code == 404
    result = a.put(url, json={"version": 1, "data": edit}).json()
    assert result["version"] == 2 and result["quote"] == preview
    assert result["id"] == original["id"] and result["created"] == original["created"]
    assert a.put(url, json={"version": 1, "data": data}).status_code == 409
    assert a.put(url, json={"version": 2, "data": edit}).json()["reused"]
    assert len(a.get(f"{BASE}/entries").json()) == 1


def test_dynamic_group_parse_and_archive_all(app):
    c = visitor(app)
    c.post(f"{BASE}/members", json={"name": "小吴"}).raise_for_status()
    raw = "小吴付了 100 元晚餐，全组均分。"
    data = c.post(f"{BASE}/drafts/parse", json={"text": raw}).json()["data"]
    assert data["payer"] == 14 and sorted(data["people"]) == [11, 12, 13, 14]
    assert c.post(f"{BASE}/drafts/quote", json=data).json()["cents"] == 10000
    explicit = c.post(
        f"{BASE}/drafts/parse",
        json={
            "text": "全组聚餐，小吴付了 100 元晚餐，仅由小林和小周均分。",
            "proposal": bill(payer=11, people=[11, 12, 13, 14]),
        },
    ).json()["data"]
    assert explicit["payer"] == 14 and sorted(explicit["people"]) == [11, 12]
    for uid in (11, 12, 13, 14):
        c.put(f"{BASE}/members/{uid}", json={"version": 1, "active": False}).raise_for_status()
    assert c.post(f"{BASE}/session").json()["members"] == {}
    assert c.post(f"{BASE}/drafts/quote", json=data).status_code == 422


def test_concurrent_writers_keep_one_revision(app):
    client = visitor(app)
    cookie = client.cookies.get("studio_session")
    uid = str(uuid4())
    client.post(f"{BASE}/entries", json={"id": uid, "data": bill()}).raise_for_status()

    def update(amount):
        with TestClient(app, cookies={"studio_session": cookie}) as tab:
            return tab.put(
                f"{BASE}/entries/{uid}", json={"version": 1, "data": bill(amount=amount)}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, ["100", "200"])) == [200, 409]
    [entry] = client.get(f"{BASE}/entries").json()
    assert entry["version"] == 2 and entry["amount"] in {"100.00", "200.00"}


def test_migrate_old_ledger_and_reopen_database(tmp_path):
    path = tmp_path / "old.db"
    token = "a" * 64
    scope = hashlib.sha256(token.encode()).hexdigest()
    uid = str(uuid4())
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE studio_sessions(scope TEXT PRIMARY KEY)")
        con.execute(
            "CREATE TABLE studio_expenses(scope TEXT,id TEXT,document TEXT,created TEXT,PRIMARY KEY(scope,id))"
        )
        con.execute("INSERT INTO studio_sessions VALUES(?)", (scope,))
        con.execute(
            "INSERT INTO studio_expenses VALUES(?,?,?,?)",
            (scope, uid, json.dumps(bill(), ensure_ascii=False, sort_keys=True), "legacy"),
        )
    config = {"model": "", "ollama_url": ""}
    with TestClient(create_app(path, config), cookies={"studio_session": token}) as client:
        [entry] = client.get(f"{BASE}/entries").json()
        assert entry["id"] == uid and entry["created"] == "legacy" and entry["version"] == 1
        result = client.post(f"{BASE}/entries", json={"id": uid, "data": bill()}).json()
        assert result["reused"] and result["version"] == 1
        client.put(f"{BASE}/members/11", json={"name": "小王", "version": 1}).raise_for_status()
        client.put(
            f"{BASE}/draft", json={"draft": {"raw": "留存"}, "version": 0}
        ).raise_for_status()
    with TestClient(create_app(path, config), cookies={"studio_session": token}) as reopened:
        assert reopened.get(f"{BASE}/members").json()[0]["name"] == "小王"
        assert reopened.get(f"{BASE}/draft").json()["draft"] == {"raw": "留存"}
