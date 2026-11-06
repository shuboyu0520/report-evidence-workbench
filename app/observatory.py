"""Local research notebook: immutable claims and append-only human reviews."""

import json
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

CREATORS = [
    {"name": "老李玩钱", "url": "https://www.youtube.com/channel/UCo2gxyermsLBSCxFHvJs0Zg"},
    {"name": "Edan深度财经", "url": None},
    {"name": "股市研究院", "url": "https://www.youtube.com/channel/UCiMhSy1HPJR-49yIj9BHS9w"},
    {"name": "NaNa说美股", "url": "https://www.youtube.com/@NaNaShuoMeiGu"},
    {"name": "视野环球财经", "url": "https://www.youtube.com/@RhinoFinance"},
    {"name": "艾登·美股智见", "url": None},
]


class Claim(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    creator: str = Field(min_length=1, max_length=100)
    symbol: str = Field(pattern=r"^[A-Z0-9.\-]{1,15}$")
    source_url: HttpUrl
    published_on: date
    review_on: date
    stance: Literal["bullish", "bearish", "neutral"]
    quote: str = Field(min_length=4, max_length=3000)
    hypothesis: str = Field(min_length=4, max_length=2000)
    is_demo: bool = False

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.review_on < self.published_on:
            raise ValueError("复盘日期不能早于观点日期")
        return self


class Review(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    verdict: Literal["supports", "contradicts", "insufficient"]
    note: str = Field(min_length=4, max_length=3000)
    report_id: str | None = Field(default=None, max_length=100)
    page: int | None = Field(default=None, ge=1)
    quote: str = Field(default="", max_length=3000)

    @model_validator(mode="after")
    def evidence_required(self):
        if self.verdict != "insufficient" or self.report_id or self.page or self.quote:
            if not self.report_id or not self.page or len(self.quote) < 4:
                raise ValueError("关联证据需要报告、页码及至少 4 字的原文")
        return self


def install_observatory(api, db):
    with db.connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS research_claims (
                id TEXT PRIMARY KEY, creator TEXT NOT NULL, symbol TEXT NOT NULL,
                source_url TEXT NOT NULL, published_on TEXT NOT NULL, review_on TEXT NOT NULL,
                stance TEXT NOT NULL, quote TEXT NOT NULL, hypothesis TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS research_reviews (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT NOT NULL REFERENCES research_claims(id),
                verdict TEXT NOT NULL, note TEXT NOT NULL,
                report_id TEXT REFERENCES reports(id), page INTEGER, quote TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS research_review_claim ON research_reviews(claim_id,seq);
        """)

    def detail(claim_id):
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM research_claims WHERE id=?", (claim_id,)).fetchone()
            if not row:
                raise HTTPException(404, "观点不存在")
            reviews = [dict(r) for r in conn.execute(
                "SELECT * FROM research_reviews WHERE claim_id=? ORDER BY seq DESC", (claim_id,)
            )]
        return {**dict(row), "reviews": reviews}

    @api.get("/observatory", include_in_schema=False)
    def workspace():
        return FileResponse(Path(__file__).parent / "static" / "observatory.html")

    @api.get("/research/creators")
    def creators():
        return CREATORS

    @api.get("/research/claims")
    def claims(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        with db.connect() as conn:
            return [dict(r) for r in conn.execute("""
                SELECT c.*, (SELECT verdict FROM research_reviews r WHERE r.claim_id=c.id
                ORDER BY seq DESC LIMIT 1) AS verdict,
                (SELECT COUNT(*) FROM research_reviews r WHERE r.claim_id=c.id) AS review_count
                FROM research_claims c ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?
            """, (limit, offset))]

    @api.post("/research/claims", status_code=201)
    def create_claim(body: Claim):
        claim_id = uuid4().hex
        values = body.model_dump(mode="json")
        with db.connect() as conn:
            conn.execute("""INSERT INTO research_claims
                (id,creator,symbol,source_url,published_on,review_on,stance,quote,hypothesis,is_demo)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (claim_id, *values.values()))
        return detail(claim_id)

    @api.get("/research/claims/{claim_id}")
    def get_claim(claim_id: str):
        return detail(claim_id)

    @api.post("/research/claims/{claim_id}/reviews", status_code=201)
    def review(claim_id: str, body: Review):
        detail(claim_id)
        with db.connect() as conn:
            if body.report_id:
                evidence = conn.execute(
                    "SELECT text FROM pages WHERE report_id=? AND number=?",
                    (body.report_id, body.page),
                ).fetchone()
                if not evidence or body.quote not in evidence["text"]:
                    raise HTTPException(422, "该报告页不存在此原文，请核对后提交")
            conn.execute("""INSERT INTO research_reviews
                (claim_id,verdict,note,report_id,page,quote) VALUES(?,?,?,?,?,?)""",
                (claim_id, body.verdict, body.note, body.report_id, body.page, body.quote))
        return detail(claim_id)

    @api.get("/research/export")
    def export():
        with db.connect() as conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM research_claims ORDER BY created_at,id")]
        payload = {"schema_version": 1, "claims": [detail(i) for i in ids]}
        return Response(json.dumps(payload, ensure_ascii=False, indent=2),
                        media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="guanzheng.json"'})
