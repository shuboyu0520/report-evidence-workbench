import hashlib
import io
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field, HttpUrl
from pypdf import PdfReader
from pypdf.constants import UserAccessPermissions
from starlette.concurrency import run_in_threadpool

from .agent import analyze
from .db import Database
from .finance import FACTORS, extract_metrics, numeric
from .observatory import install_observatory
from .reader import CASE_DIGESTS, CASE_TEXT, compare_reports, read_report
from .table_headers import YEAR_GROUP, segment_headers, year_then_columns

MAX_BYTES = 15 * 1024 * 1024


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    mode: Literal["rules", "ollama", "rag", "reader"] = "rules"
    as_of: date | None = None


class Comparison(BaseModel):
    sources: dict[Literal["company", "peer", "market", "policy"], str]
    as_of: date
    question: str = Field(min_length=2, max_length=800)


class ConfirmedMetric(BaseModel):
    name: Literal[
        "revenue", "cost", "net_profit", "operating_cash_flow", "total_assets", "total_liabilities"
    ]
    year: int = Field(ge=2000, le=2099)
    source_value: str = Field(max_length=40)
    source_unit: Literal["元", "万元", "百万元", "亿元"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    page: int = Field(ge=1)
    quote: str = Field(min_length=4, max_length=2000)
    scope: Literal["consolidated_annual"]
    confirmed_by_user: Literal[True]
    expected_revision: int | None = Field(default=None, ge=0)
    reason: str = Field(default="人工确认指标", min_length=1, max_length=500)


def parse_upload(content, filename):
    columns = {}
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("TXT 必须使用 UTF-8 编码") from None
        texts = text.split("\f")
    elif suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                if not reader.decrypt("") or not ((reader.user_access_permissions or 0) & UserAccessPermissions.EXTRACT):
                    raise ValueError("PDF 需要打开密码或未授权提取文本")
            if len(reader.pages) > 500:
                raise ValueError("最多支持 500 页")
            texts = [page.extract_text() or "" for page in reader.pages]
            for i, text in enumerate(texts):
                if re.search(r"reportable segments?|segment reporting|(?:our|company's|operating) segments\b|\beach division\b", text, re.I) and any(
                    YEAR_GROUP.fullmatch(s.strip()) for s in text.splitlines()
                ):
                    layout = reader.pages[i].extract_text(extraction_mode="layout", layout_mode_space_vertically=False)
                    labels = {**year_then_columns(text), **segment_headers(layout)}
                    if labels:
                        columns[i+1] = labels
        except ValueError:
            raise
        except Exception:
            raise ValueError("PDF 解析失败，请确认文件完整且包含文本层") from None
    else:
        raise ValueError("只支持 PDF 或 UTF-8 TXT")
    if len(texts) > 500 or sum(map(len, texts)) > 3_000_000:
        raise ValueError("报告页数或文本长度超出限制")
    if not any(t.strip() for t in texts):
        raise ValueError("未提取到文字；扫描件请先进行 OCR")
    pages = [{"number": i, "text": text} for i, text in enumerate(texts, 1)]
    for page in pages:
        if page["number"] in columns:
            page["segment_columns"] = columns[page["number"]]
    return pages


def create_app(db_path=None, settings=None):
    api = FastAPI(title="Financial Report Agent", version="0.1.0")
    db = Database(db_path or os.getenv("DATABASE_PATH", "data/financial-agent.db"))
    config = settings or {
        "model": os.getenv("OLLAMA_MODEL", ""),
        "ollama_url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
        "embedding_model": os.getenv("OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b"),
    }
    api.state.db = db
    install_observatory(api, db)

    @api.get("/reader", include_in_schema=False)
    def reader_home():
        from .reader_view import reader_html
        return HTMLResponse(reader_html(live=True))

    @api.get("/reader/case.txt", include_in_schema=False)
    def reader_case():
        return Response(CASE_TEXT, media_type="text/plain")

    @api.post("/reader/compare")
    async def reader_compare(body: Comparison):
        try:
            return {"as_of": body.as_of, "sections": await compare_reports(
                db, body.sources, body.as_of, body.question, config)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, "模型服务调用失败，请稍后重试。") from exc

    @api.exception_handler(LookupError)
    async def missing_handler(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @api.get("/", include_in_schema=False)
    def home():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @api.get("/review.js", include_in_schema=False)
    def review_script():
        return FileResponse(Path(__file__).parent / "static" / "review.js")

    @api.get("/health")
    def health():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "model_configured": bool(config["model"])}

    @api.post("/reports", status_code=201)
    async def upload(company: str = Form(min_length=1, max_length=100), file: UploadFile = File(),
                     published_on: date | None = Form(None), calendar_year: bool = Form(False),
                     source_url: HttpUrl | None = Form(None)):
        try:
            content = await file.read(MAX_BYTES + 1)
        finally:
            await file.close()
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "文件不能超过 15 MiB")
        if not company.strip():
            raise HTTPException(422, "公司名称不能为空")
        filename = (file.filename or "report").replace("\\", "/").split("/")[-1]
        try:
            pages = await run_in_threadpool(parse_upload, content, filename)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        facts, warnings = extract_metrics(pages)
        digest, report_id = hashlib.sha256(content).hexdigest(), uuid4().hex
        with db.connect() as conn:
            # Serialize duplicate detection and insertion in the same transaction.
            conn.execute("BEGIN IMMEDIATE")
            duplicate = conn.execute(
                "SELECT id FROM reports WHERE company=? AND digest=?", (company.strip(), digest)
            ).fetchone()
            if published_on:
                metadata = (published_on.isoformat(), int(calendar_year), str(source_url or ""))
                if duplicate:
                    previous = conn.execute("SELECT published_on,calendar_year,url FROM reader_context WHERE report_id=?",
                                            (duplicate["id"],)).fetchone()
                    if previous and tuple(previous) != metadata:
                        raise HTTPException(409, "相同资料已有不同的日期或来源记录，请先核对文件。")
                    conn.execute("INSERT OR IGNORE INTO reader_context VALUES(?,?,?,?)", (duplicate["id"], *metadata))
            if duplicate:
                db.save_column_headers(conn, duplicate["id"], pages)
                return {
                    "id": duplicate["id"],
                    "deduplicated": True,
                    "warnings": ["相同公司和文件已存在；原报告及人工修订保持不变。"],
                }
            conn.execute(
                "INSERT INTO reports(id,company,filename,digest) VALUES(?,?,?,?)",
                (report_id, company.strip(), filename, digest),
            )
            if published_on:
                conn.execute("INSERT INTO reader_context VALUES(?,?,?,?)", (report_id, *metadata))
            conn.executemany(
                "INSERT INTO pages(report_id,number,text) VALUES(?,?,?)",
                [(report_id, p["number"], p["text"]) for p in pages],
            )
            db.save_column_headers(conn, report_id, pages)
            for fact in facts:
                conn.execute(
                    """INSERT INTO metrics(report_id,name,year,value,currency,unit,
                              scope,page,quote,origin) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        report_id,
                        *[
                            fact[k]
                            for k in (
                                "name",
                                "year",
                                "value",
                                "currency",
                                "unit",
                                "scope",
                                "page",
                                "quote",
                                "origin",
                            )
                        ],
                    ),
                )
        return {
            "id": report_id,
            "pages": len(pages),
            "metrics": len(facts),
            "deduplicated": False,
            "warnings": warnings,
        }

    @api.get("/reports")
    def reports(limit: int = 20, offset: int = 0):
        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, "limit 应为 1–100，offset 不得为负")
        with db.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM reports ORDER BY created_at DESC,id LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            ]

    @api.get("/reports/{report_id}")
    def report(report_id: str):
        report, _, metrics, revision = db.analysis_inputs(report_id)
        return {**report, "metrics": metrics, "revision": revision}

    @api.get("/reports/{report_id}/metrics/history")
    def metric_history(report_id: str):
        db.report(report_id)
        with db.connect() as conn:
            items = [dict(r) for r in conn.execute(
                "SELECT * FROM metric_changes WHERE report_id=? ORDER BY revision DESC",
                (report_id,),
            )]
        for item in items:
            item["previous"] = json.loads(item.pop("previous_json") or "null")
            item["current"] = json.loads(item.pop("current_json"))
        return items

    @api.get("/reports/{report_id}/pages/{page}")
    def report_page(report_id: str, page: int):
        pages = db.pages(report_id)
        if not 1 <= page <= len(pages):
            raise HTTPException(404, "页码不存在")
        return pages[page - 1]

    @api.put("/reports/{report_id}/metrics")
    def confirm_metric(report_id: str, metric: ConfirmedMetric):
        if not metric.reason.strip():
            raise HTTPException(422, "请填写确认或修订说明")
        pages = db.pages(report_id)
        if metric.page > len(pages):
            raise HTTPException(422, "页码不存在")
        text = pages[metric.page - 1]["text"]
        if metric.quote not in text or str(metric.year) not in text:
            raise HTTPException(422, "引文或年度无法在指定页定位")
        try:
            value = numeric(metric.source_value)
            normalized_quote = metric.quote.replace("−", "-").replace("，", ",")
            candidates = re.findall(r"\(?-?\d[\d,]*(?:\.\d+)?\)?", normalized_quote)
            found = False
            for candidate in candidates:
                try:
                    if numeric(candidate) == value:
                        found = True
                        break
                except ValueError:
                    continue
            if not found:
                raise ValueError("引文中没有对应数值")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        # Semantic label, unit, currency and scope are a HUMAN assertion, not machine verified.
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR IGNORE INTO report_versions(report_id) VALUES(?)", (report_id,)
            )
            revision = conn.execute(
                "SELECT revision FROM report_versions WHERE report_id=?", (report_id,)
            ).fetchone()["revision"]
            if metric.expected_revision is not None and metric.expected_revision != revision:
                raise HTTPException(409, "指标已被其他页面修改，请重新加载后核对；你的输入尚未保存。")
            previous = conn.execute(
                "SELECT * FROM metrics WHERE report_id=? AND name=? AND year=?",
                (report_id, metric.name, metric.year),
            ).fetchone()
            conn.execute(
                """INSERT INTO metrics(report_id,name,year,value,currency,unit,scope,
                         page,quote,origin) VALUES(?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(report_id,name,year) DO UPDATE SET value=excluded.value,
                         currency=excluded.currency,unit=excluded.unit,scope=excluded.scope,
                         page=excluded.page,quote=excluded.quote,origin=excluded.origin""",
                (
                    report_id,
                    metric.name,
                    metric.year,
                    str(value * FACTORS[metric.source_unit]),
                    metric.currency,
                    "元",
                    metric.scope,
                    metric.page,
                    metric.quote,
                    "human_confirmed",
                ),
            )
            current = dict(conn.execute(
                "SELECT * FROM metrics WHERE report_id=? AND name=? AND year=?",
                (report_id, metric.name, metric.year),
            ).fetchone())
            conn.execute(
                "INSERT INTO metric_changes(report_id,revision,metric_name,year,"
                "previous_json,current_json,reason) VALUES(?,?,?,?,?,?,?)",
                (report_id, revision + 1, metric.name, metric.year,
                 json.dumps(dict(previous), ensure_ascii=False) if previous else None,
                 json.dumps(current, ensure_ascii=False), metric.reason.strip()),
            )
            conn.execute(
                "UPDATE report_versions SET revision=? WHERE report_id=?", (revision + 1, report_id)
            )
        return {
            "status": "saved",
            "revision": revision + 1,
            "warning": "仅核验引文及数值存在；语义、单位和口径由确认者负责。",
        }

    @api.post("/reports/{report_id}/questions")
    async def question(report_id: str, body: Question):
        if not body.question.strip():
            raise HTTPException(422, "问题不能为空")
        try:
            if body.mode == "reader" or (body.mode == "rag" and db.report(report_id)["digest"] in CASE_DIGESTS):
                return await read_report(db, report_id, body.question, config, body.as_of)
            return await analyze(db, report_id, body.question, body.mode, config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
            raise HTTPException(502, "模型服务不可用或响应格式错误，请检查服务与模型配置") from exc

    @api.get("/analyses/{analysis_id}")
    def analysis_result(analysis_id: str):
        with db.connect() as conn:
            row = conn.execute("SELECT result FROM analyses WHERE id=?", (analysis_id,)).fetchone()
        if not row:
            raise HTTPException(404, "分析记录不存在")
        return json.loads(row["result"])

    @api.get("/analyses/{analysis_id}/export")
    def export_analysis(analysis_id: str):
        result = analysis_result(analysis_id)
        report, _, _, revision = db.analysis_inputs(result["report_id"])
        snapshot = result.get("input_snapshot")
        exported = {
            "schema_version": 1,
            "analysis": result,
            "report_source": report,
            "current_metric_revision": revision,
            "inputs_changed": None if snapshot is None else snapshot["revision"] != revision,
            "notice": "旧分析保留当时输入；修订指标后请重新分析。来源与计算可复核，不代表模型文字已验证。",
        }
        return Response(
            json.dumps(exported, ensure_ascii=False, indent=2), media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="analysis-evidence.json"'},
        )

    return api
