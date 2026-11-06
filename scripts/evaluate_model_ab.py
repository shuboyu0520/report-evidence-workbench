"""Run two frozen prompts through the real Agent and retain every model exchange.

The 20 cases reuse a development fixture, with 15 human-labelled facts loaded first.
This measures tool selection / grounded response format, NOT PDF extraction accuracy.
"""
import argparse
import asyncio
import csv
import hashlib
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.agent import DEFAULT_PROMPT, analyze  # noqa: E402
from app.main import create_app  # noqa: E402

PROMPTS = {
    "A": DEFAULT_PROMPT,
    "B": DEFAULT_PROMPT + "\n执行规则：\n"
    "1. 先识别用户要求的年度和指标，不用最近年度替代指定年度。"
    "同比使用 growth；营业收入为 revenue、营业成本为 cost、净利润为 net_profit。"
    "毛利率为 gross_margin，净利率为 net_margin，资产负债率为 debt_ratio，"
    "现金含量指经营现金流/净利润，使用 cash_conversion。\n"
    "2. 比率或同比必须先调用一次 calculate(kind,year,metric)，由工具读取已确认指标；"
    "初始检索只是原文片段，不是完整数据库；即使初始检索为空或没有指标数值，"
    "也必须调用 calculate，不能据此直接拒答。"
    "例如用户问某年度毛利率，调用 calculate({kind:gross_margin,year:该年度})；"
    "不用先获得收入或成本值，工具会自己读取。"
    "不要自行算数。只有查原文时才用 search_report；不需要重复读取全部指标。\n"
    "3. 工具 status=ok 时，简洁回答目标年度、指标和 value，百分比保留工具的小数位；"
    "引用 inputs 中的物理页码，明确写成‘第 N 页’，不可用报告印刷页码替代。\n"
    "4. 工具 status=unavailable/error 时，明确说无法计算并说明缺失项，"
    "不估算、不外推、不使用其他年度回答；缺数据时无需强行提供页码。\n"
    "5. 一次成功计算或明确缺数后立即形成答案，不重复调用同参数工具。"
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_report(app, pdf, gold):
    data = pdf.read_bytes()
    if hashlib.sha256(data).hexdigest() != gold["sha256"]:
        raise ValueError("The PDF differs from the labelled source")
    with TestClient(app) as client:
        response = client.post("/reports", data={"company": "Apple Inc."},
                               files={"file": (pdf.name, data, "application/pdf")})
        response.raise_for_status()
        rid = response.json()["id"]
        if response.json().get("metrics") != 0:
            raise AssertionError("Expected manual confirmation fixture")
        for fact in gold["metrics"]:
            page = client.get(f"/reports/{rid}/pages/{fact['page']}").json()["text"]
            pos = page.find(fact["marker"])
            if pos < 0:
                raise AssertionError("Source marker not found")
            end = page.find("\n", pos)
            quote = page[:end if end >= 0 else len(page)]
            response = client.put(f"/reports/{rid}/metrics", json={
                "name": fact["name"], "year": fact["year"],
                "source_value": fact["source_value"], "source_unit": "百万元",
                "currency": "USD", "page": fact["page"], "quote": quote,
                "scope": "consolidated_annual", "confirmed_by_user": True,
            })
            response.raise_for_status()
        return rid


def score_case(spec, result):
    """Strict observable checks; never count server-side precalculation as model work."""
    answer = result["answer"]
    reasons = []
    model_steps = [s for s in result["trace"] if s.get("origin") == "model"]
    percentages = {Decimal(n) for n in re.findall(r"(-?\d+(?:\.\d+)?)\s*[%％]", answer)}
    cited_pages = {int(a or b) for a, b in re.findall(r"第\s*(\d+)\s*页|\bpage\s*(\d+)\b", answer, re.I)}
    if result["verification"] != "model_draft_unverified":
        reasons.append(result["verification"])
    if "value" in spec:
        metric = next((v for k, v in (("营业成本", "cost"), ("净利润", "net_profit"))
                       if k in spec["question"]), "revenue")
        matches = [s for s in model_steps if s["tool"] == "calculate"
                   and s["arguments"].get("kind") == spec["kind"]
                   and s["arguments"].get("year") == spec["year"]
                   and (spec["kind"] != "growth" or s["arguments"].get("metric", "revenue") == metric)
                   and s["result"].get("status") == "ok"
                   and Decimal(s["result"]["value"]) == Decimal(spec["value"])]
        if not matches:
            reasons.append("model_did_not_call_correct_calculation")
        if Decimal(spec["value"]) not in percentages:
            reasons.append("answer_missing_expected_percentage")
        if spec["page"] not in cited_pages:
            reasons.append("answer_missing_expected_physical_page")
    else:
        if not model_steps:
            reasons.append("no_model_tool_evidence")
        if percentages:
            reasons.append("percentage_given_for_missing_data")
        if not re.search(r"无法|不能|缺少|缺失|未提供|没有.*数据|未.*披露|未找到|未能|不可计算|不包含", answer):
            reasons.append("missing_explicit_refusal")
    return {"passed": not reasons, "failure_reasons": reasons,
            "model_tool_calls": len(model_steps), "answer": answer,
            "verification": result["verification"]}


async def run(args):
    args.out.mkdir(parents=True, exist_ok=False)
    traces = args.out / "traces"
    traces.mkdir()
    gold_path = ROOT / "evaluation/apple_2025_gold.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    options = {"temperature": 0, "seed": 42, "num_ctx": 16384, "num_predict": 1024}
    model_info = httpx.post(args.url + "/api/show", json={"model": args.model}, timeout=20).json()
    tags = httpx.get(args.url + "/api/tags", timeout=20).json()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "model": args.model,
        "url": args.url, "options": options, "prompts": PROMPTS,
        "prompt_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in PROMPTS.items()},
        "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "agent_sha256": hashlib.sha256((ROOT / "app/agent.py").read_bytes()).hexdigest(),
        "finance_sha256": hashlib.sha256((ROOT / "app/finance.py").read_bytes()).hexdigest(),
        "model_info": model_info, "model_tags": tags,
        "rubric": "Positive: MODEL calculation with correct kind/year/metric/value plus answer percentage and physical page. Negative: model evidence plus explicit refusal with no percentage. Guard failures and errors fail. Server precalculations never count as model tool calls.",
        "limits": "Single development report; 15 preconfirmed facts; 14 numeric and 6 missing-data questions; one deterministic trial per prompt; not extraction accuracy, generalization, human usability or production SLA.",
        "execution": "Same Agent analyze function as API, real HTTP model calls, alternating AB/BA by question; no retries or selective reruns.",
    }
    write_json(args.out / "manifest.json", manifest)
    write_json(args.out / "questions.json", gold["questions"])
    app = create_app(db_path=args.out / "evaluation.db")
    rid = seed_report(app, args.pdf, gold)
    cases = []
    for index, spec in enumerate(gold["questions"], 1):
        for variant in ("AB" if index % 2 else "BA"):
            case_id = f"Q{index:02d}_{variant}"
            events = []
            def observe(event):
                events.append(event)
                write_json(traces / (case_id + "_model.json"), events)
            settings = {"model": args.model, "ollama_url": args.url,
                        "system_prompt": PROMPTS[variant], "model_options": options,
                        "on_model_event": observe}
            started = time.perf_counter()
            try:
                result = await analyze(app.state.db, rid, spec["question"], "ollama", settings)
                write_json(traces / (case_id + "_analysis.json"), result)
                scored = score_case(spec, result)
            except Exception as exc:
                scored = {"passed": False, "failure_reasons": [type(exc).__name__ + ": " + str(exc)],
                          "model_tool_calls": None, "answer": "", "verification": "error"}
            case = {"case_id": case_id, "variant": variant, "expected": spec, **scored,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    "model_requests": len(events),
                    "output_tokens": sum(e.get("response", {}).get("eval_count", 0) for e in events),
                    "prompt_tokens": sum(e.get("response", {}).get("prompt_eval_count", 0) for e in events)}
            cases.append(case)
            write_json(args.out / "cases.json", cases)
            print(json.dumps({k: case[k] for k in ("case_id", "passed", "failure_reasons", "elapsed_ms")}, ensure_ascii=False), flush=True)
    summary = {}
    for variant in "AB":
        group = [c for c in cases if c["variant"] == variant]
        summary[variant] = {"cases": len(group), "passed": sum(c["passed"] for c in group),
                            "numeric_passed": sum(c["passed"] and "value" in c["expected"] for c in group),
                            "missing_passed": sum(c["passed"] and "status" in c["expected"] for c in group),
                            "median_ms": round(statistics.median(c["elapsed_ms"] for c in group), 2),
                            "model_requests": sum(c["model_requests"] for c in group),
                            "output_tokens": sum(c["output_tokens"] for c in group)}
    write_json(args.out / "summary.json", summary)
    with (args.out / "cases.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["case_id", "variant", "question", "passed", "failure_reasons", "elapsed_ms", "model_requests", "model_tool_calls", "output_tokens", "answer"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for c in cases:
            writer.writerow({k: c["expected"]["question"] if k == "question" else
                             "; ".join(c[k]) if k == "failure_reasons" else c[k] for k in fields})
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:4b-instruct")
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    parser.add_argument("--pdf", type=Path, default=ROOT / "data/apple-2025-10k.pdf")
    parser.add_argument("--out", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
