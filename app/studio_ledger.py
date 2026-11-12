"""Session-private roster, editable expenses, and recoverable draft storage."""

import json
import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, StrictBool

from .studio_splits import MEMBERS, DraftFields, split_quote


class NewMember(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class MemberEdit(BaseModel):
    version: int = Field(ge=1, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    active: StrictBool | None = None


class NewEntry(BaseModel):
    id: UUID
    data: DraftFields


class EntryEdit(BaseModel):
    version: int = Field(ge=1, strict=True)
    data: DraftFields


class DraftSave(BaseModel):
    version: int = Field(ge=0, strict=True)
    draft: dict


def seed_members(con, scope):
    con.executemany(
        "INSERT INTO studio_members(scope,id,name,name_key) VALUES(?,?,?,?)",
        [(scope, uid, name, name.casefold()) for uid, name in MEMBERS.items()],
    )


def initialize_ledger(db):
    with db.connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS studio_sessions (scope TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS studio_expenses (
                scope TEXT NOT NULL REFERENCES studio_sessions(scope),
                id TEXT NOT NULL, document TEXT NOT NULL, created TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(scope,id)
            );
            CREATE TABLE IF NOT EXISTS studio_members (
                scope TEXT NOT NULL REFERENCES studio_sessions(scope),
                id INTEGER NOT NULL, name TEXT NOT NULL, name_key TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(scope,id), UNIQUE(scope,name_key)
            );
            CREATE TABLE IF NOT EXISTS studio_drafts (
                scope TEXT PRIMARY KEY REFERENCES studio_sessions(scope),
                version INTEGER NOT NULL, document TEXT
            );
        """)
        con.execute("BEGIN IMMEDIATE")
        if "version" not in {
            row["name"] for row in con.execute("PRAGMA table_info(studio_expenses)")
        }:
            con.execute("ALTER TABLE studio_expenses ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        missing = con.execute(
            "SELECT scope FROM studio_sessions s WHERE NOT EXISTS "
            "(SELECT 1 FROM studio_members m WHERE m.scope=s.scope)"
        ).fetchall()
        for row in missing:
            seed_members(con, row["scope"])


def active_names(con, scope):
    return dict(
        con.execute(
            "SELECT id,name FROM studio_members WHERE scope=? AND active=1 ORDER BY id", (scope,)
        )
    )


def member_view(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "active": bool(row["active"]),
        "version": row["version"],
    }


def normalized_name(con, scope, proposed, uid=None):
    if any(unicodedata.category(ch).startswith("C") for ch in proposed):
        raise HTTPException(422, "成员姓名不能包含控制字符。")
    name = unicodedata.normalize("NFKC", proposed).strip()
    if not 1 <= len(name) <= 32:
        raise HTTPException(422, "成员姓名需为 1 至 32 个字符。")
    owner = con.execute(
        "SELECT id FROM studio_members WHERE scope=? AND name_key=?", (scope, name.casefold())
    ).fetchone()
    if owner and owner["id"] != uid:
        raise HTTPException(409, "已有同名成员。如已移出，可在名单中恢复。")
    return name


def expense_row(con, scope, uid):
    return con.execute(
        "SELECT * FROM studio_expenses WHERE scope=? AND id=?", (scope, str(uid))
    ).fetchone()


def expense_view(row):
    return {
        "id": row["id"],
        **json.loads(row["document"]),
        "created": row["created"],
        "version": row["version"],
    }


def expense_quote(con, scope, data, previous=None):
    names = active_names(con, scope)
    if previous:
        historic = json.loads(previous["document"])
        retained = set(data.people).intersection(historic["people"])
        if data.payer == historic["payer"]:
            retained.add(data.payer)
        if (data.payer not in names and data.payer != historic["payer"]) or (
            set(data.people) - names.keys() - set(historic["people"])
        ):
            raise HTTPException(422, "已移出的成员仅可保留原账单中的角色。")
        if retained - names.keys():
            rows = con.execute(
                "SELECT id,name FROM studio_members WHERE scope=? AND active=0", (scope,)
            )
            names.update((r["id"], r["name"]) for r in rows if r["id"] in retained)
    return split_quote(data, names)


def serialize_expense(data, cents):
    canonical = data.model_dump()
    if data.split_mode == "equal":
        # Older confirmations use the same serialized form for idempotent retries.
        canonical.pop("split_mode")
        canonical.pop("split_values")
    canonical.update(
        amount=f"{cents // 100}.{cents % 100:02}",
        people=sorted(data.people),
        description=data.description.strip(),
    )
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True)


def draft_view(con, scope):
    row = con.execute(
        "SELECT version,document FROM studio_drafts WHERE scope=?", (scope,)
    ).fetchone()
    if not row:
        return {"version": 0, "draft": None}
    return {
        "version": row["version"],
        "draft": json.loads(row["document"]) if row["document"] else None,
    }


def change_draft(db, scope, expected, document):
    with db.connect() as con:
        con.execute("BEGIN IMMEDIATE")
        current = draft_view(con, scope)
        if current["version"] != expected:
            raise HTTPException(409, "草稿已在其他页面修改，请重新读取。")
        if document is None and current["draft"] is None:
            return current
        con.execute(
            "INSERT INTO studio_drafts(scope,version,document) VALUES(?,?,?) "
            "ON CONFLICT(scope) DO UPDATE SET version=excluded.version,document=excluded.document",
            (scope, expected + 1, document),
        )
        return draft_view(con, scope)


def install_ledger_routes(api, db, session, require_session):
    @api.get("/api/studio/members")
    def list_members(request: Request, response: Response):
        scope = require_session(request)
        response.headers["Cache-Control"] = "no-store"
        with db.connect() as con:
            return [
                member_view(r)
                for r in con.execute(
                    "SELECT * FROM studio_members WHERE scope=? ORDER BY id", (scope,)
                )
            ]

    @api.post("/api/studio/members")
    def add_member(body: NewMember, request: Request):
        scope = require_session(request)
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            name = normalized_name(con, scope, body.name)
            uid = con.execute(
                "SELECT COALESCE(MAX(id),10)+1 FROM studio_members WHERE scope=?", (scope,)
            ).fetchone()[0]
            con.execute(
                "INSERT INTO studio_members(scope,id,name,name_key) VALUES(?,?,?,?)",
                (scope, uid, name, name.casefold()),
            )
            return {"id": uid, "name": name, "active": True, "version": 1}

    @api.put("/api/studio/members/{uid}")
    def update_member(uid: int, body: MemberEdit, request: Request):
        scope = require_session(request)
        if body.name is None and body.active is None:
            raise HTTPException(422, "请提供新的姓名或成员状态。")
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = con.execute(
                "SELECT * FROM studio_members WHERE scope=? AND id=?", (scope, uid)
            ).fetchone()
            if not old:
                raise HTTPException(404, "找不到这个成员。")
            if body.version != old["version"]:
                raise HTTPException(409, "成员名单已在其他页面修改，请刷新。")
            name = old["name"] if body.name is None else normalized_name(con, scope, body.name, uid)
            active = bool(old["active"]) if body.active is None else body.active
            if name == old["name"] and active == bool(old["active"]):
                return member_view(old)
            version = old["version"] + 1
            con.execute(
                "UPDATE studio_members SET name=?,name_key=?,active=?,version=? WHERE scope=? AND id=?",
                (name, name.casefold(), active, version, scope, uid),
            )
            return {"id": uid, "name": name, "active": active, "version": version}

    @api.get("/api/studio/draft")
    def read_draft(request: Request, response: Response):
        scope = require_session(request)
        response.headers["Cache-Control"] = "no-store"
        with db.connect() as con:
            return draft_view(con, scope)

    @api.put("/api/studio/draft")
    def save_draft(body: DraftSave, request: Request):
        scope = require_session(request)
        document = json.dumps(body.draft, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(document.encode("utf-8")) > 16_384:
            raise HTTPException(422, "草稿超过 16 KiB，请缩短说明。")
        return change_draft(db, scope, body.version, document)

    @api.delete("/api/studio/draft")
    def clear_draft(request: Request, version: int = Query(ge=0)):
        return change_draft(db, require_session(request), version, None)

    @api.post("/api/studio/drafts/quote")
    def preview(data: DraftFields, request: Request, entry_id: UUID | None = None):
        scope = require_session(request) if entry_id else session(request)
        if not scope:
            return split_quote(data)
        with db.connect() as con:
            old = expense_row(con, scope, entry_id) if entry_id else None
            if entry_id and not old:
                raise HTTPException(404, "找不到这笔账单。")
            return expense_quote(con, scope, data, old)

    @api.get("/api/studio/entries")
    def entries(request: Request, response: Response):
        scope = require_session(request)
        response.headers["Cache-Control"] = "no-store"
        with db.connect() as con:
            rows = con.execute(
                "SELECT * FROM studio_expenses WHERE scope=? ORDER BY created DESC,id", (scope,)
            )
            return [expense_view(r) for r in rows]

    @api.post("/api/studio/entries")
    def confirm(body: NewEntry, request: Request):
        scope = require_session(request)
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = expense_row(con, scope, body.id)
            quote = expense_quote(con, scope, body.data, old)
            document = serialize_expense(body.data, quote["cents"])
            if old and old["document"] != document:
                raise HTTPException(409, "相同草稿已按其他内容入账。")
            if not old:
                con.execute(
                    "INSERT INTO studio_expenses(scope,id,document,created) VALUES(?,?,?,?)",
                    (scope, str(body.id), document, datetime.now(UTC).isoformat()),
                )
            return {
                **expense_view(old or expense_row(con, scope, body.id)),
                "quote": quote,
                "reused": bool(old),
            }

    @api.put("/api/studio/entries/{uid}")
    def edit_entry(uid: UUID, body: EntryEdit, request: Request):
        scope = require_session(request)
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = expense_row(con, scope, uid)
            if not old:
                raise HTTPException(404, "找不到这笔账单。")
            if body.version != old["version"]:
                raise HTTPException(409, "账单已在其他页面修改，请重新读取。")
            quote = expense_quote(con, scope, body.data, old)
            document = serialize_expense(body.data, quote["cents"])
            if document == old["document"]:
                return {**expense_view(old), "quote": quote, "reused": True}
            con.execute(
                "UPDATE studio_expenses SET document=?,version=version+1 WHERE scope=? AND id=?",
                (document, scope, str(uid)),
            )
            return {**expense_view(expense_row(con, scope, uid)), "quote": quote, "reused": False}
