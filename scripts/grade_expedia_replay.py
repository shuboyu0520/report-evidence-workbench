"""Grade the sealed Expedia Q3 2026 fixture against saved answers and the original PDF."""

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

# Labels used on the issuer's accepted physical pages, including alternative statements.
LABELS = {
    "E01": r"\brevenue\b",
    "E02": r"\brevenue\b",
    "E03": r"operating income",
    "E04": r"diluted",
    "E05": r"booked room nights",
    "E06": r"gross bookings",
    "E07": r"\bb2b\b",
    "E08": r"\blodging\b",
    "E09": r"free cash flow",
    "E10": r"adjusted ebitda",
    "E11": r"net income attributable",
    "E12": r"\bb2b\b",
    "E13": r"\brevenue\b",
    "E14": r"adjusted ebitda",
}
SEGMENT = {"E07": "revenue", "E08": "revenue by product", "E12": "gross bookings"}
CHINESE_Q = "一二三四"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(text):
    return " ".join(text.split()).lower()


def numbers(text):
    # A minus between two positive range endpoints is a separator. Accounting
    # parentheses are negative, even with whitespace between the USD sign and '('.
    text = re.sub(r"(?<=\d)%?\s*[-–]\s*\$?\s*(?=\d)", " to ", text)
    text = re.sub(r"\(\s*([\d,.]+)\s*\)", r"-\1", text)
    return [
        Decimal(s.replace(",", ""))
        for s in re.findall(r"[+\-−]?\d[\d,]*(?:\.\d+)?", text.replace("−", "-"))
    ]


def grade(case, response, pages, cutoff):
    answer = response.get("answer") or ""
    citations = response.get("citations") or []
    state = response.get("verification")
    if response.get("http") != 200:
        return False, "HTTP 请求失败"
    if any(
        not (
            isinstance(c["page"], int)
            and 1 <= c["page"] <= len(pages)
            and c["quote"].strip()
            and compact(c["quote"]) in pages[c["page"] - 1]
        )
        for c in citations
    ):
        return False, "答复引文未能在标注的物理页逐字核对"
    if case["kind"] == "future":
        ok = (
            state == "not_yet_disclosed"
            and not citations
            and cutoff in answer
            and case["period_end"] in answer
            and "尚未披露" in answer
        )
        return ok, "按研究截止日和完整报告期核验未来实际业绩"
    if case["kind"] == "missing":
        ok = state == "insufficient_evidence" and not citations and "没找到足够证据" in answer
        return ok, "按题目要求的地域或品牌核验资料披露范围"
    if state not in {"source_earnings_cell", "cited_draft"}:
        return False, "资料中存在答案，最终未给出有依据的结果"
    expected = [Decimal(v) for v in case["expected_values"]]
    year, quarter = case["period"].split(" Q")
    period = (
        rf"{year}\s*(?:财年|年)\s*第?\s*(?:{quarter}|{CHINESE_Q[int(quarter) - 1]})\s*(?:财季|季度)"
    )
    if not re.search(period, answer) or case["unit"] not in answer:
        return False, "最终答案的季度或单位不匹配"
    # Grade the numeric assertion, excluding the period and appended page reference.
    assertion = re.split(r"原表第|[（(]原文第", re.sub(period, "", answer), maxsplit=1)[0]
    amount_text = re.split(r"(?:实际|指引)[）)]?\s*为|(?:为|是)\s*(?=[+\-−\d$])", assertion)[-1]
    if numbers(amount_text) != expected:
        return False, "最终答案的数值、符号或区间端点不匹配"
    relevant = [c for c in citations if c["page"] in case["accepted_pages"]]
    source_text = " ".join(compact(c["quote"]) for c in relevant)
    if not re.search(LABELS[case["id"]], source_text) or not all(
        v in numbers(source_text) for v in expected
    ):
        return False, "指定原页的引文缺少指标或带符号的原值"
    if case["id"] in SEGMENT and SEGMENT[case["id"]] not in source_text:
        return False, "分项引文缺少营收或预订额的小节标题"
    if case["id"] in {"E07", "E12"}:
        wording = r"revenue|营收|收入" if case["id"] == "E07" else r"gross bookings|预订.*额"
        if "b2b" not in answer.lower() or not re.search(wording, answer, re.I):
            return False, "分项答案没有写出 B2B 和对应的业务指标"
    if case["kind"] == "guidance" and not re.search(r"指引|预计|预期|展望", answer):
        return False, "未将区间标明为指引"
    cell = next((s for s in response.get("trace", []) if s["tool"] == "read_earnings_cell"), None)
    if state == "source_earnings_cell" and (
        not cell
        or cell.get("page") not in case["accepted_pages"]
        or cell.get("year") != int(year)
        or cell.get("quarter") != int(quarter)
        or cell.get("unit") != case["unit"]
        or [Decimal(v.replace(",", "")) for v in cell.get("amounts", [])] != expected
    ):
        return False, "原表工具所选的列、单位或单元格数值与金标不匹配"
    return True, "已核对原页引文、指标范围、季度、单位及最终数值"


def main(grade_case=grade, description=__doc__):
    parser = argparse.ArgumentParser(description=description)
    for field in ("fixture", "pdf", "raw", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    fixture, run = read(args.fixture), read(args.raw)
    if (
        sha(args.fixture) != run["fixture_sha256"]
        or sha(args.pdf) != fixture["sha256"]
        or fixture["sha256"] != run["file_sha256"]
    ):
        raise ValueError("PDF or fixture differs from the evaluated input")
    pages = [compact(p.extract_text()) for p in PdfReader(args.pdf).pages]
    records = []
    for case, row in zip(fixture["cases"], run["cases"], strict=True):
        if (case["id"], case["question"]) != (row["id"], row["question"]):
            raise ValueError("Question or ordering differs from the registered set")
        passed, grade_note = grade_case(case, row, pages, fixture["as_of"])
        records.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "question": case["question"],
                "passed": passed,
                "assessment": grade_note,
                "answer": row["answer"],
                "verification": row["verification"],
                "citations": row["citations"],
                "accepted_pages": case.get("accepted_pages", []),
                "gold_example": case.get("example_source_quote", ""),
            }
        )
    if len(records) != 18:
        raise ValueError("Expected the complete set of eighteen saved answers")
    scores = {}
    for group, kinds in {
        "lookup_guidance": ("lookup", "guidance"),
        "lookup_only": ("lookup",),
        "guidance_only": ("guidance",),
        "disclosure_status": ("future", "missing"),
    }.items():
        subset = [row for row in records if row["kind"] in kinds]
        scores[group] = [sum(row["passed"] for row in subset), len(subset)]
    report = {
        "company": fixture["company"],
        "source": fixture["source"],
        "as_of": fixture["as_of"],
        "fixture_sha256": sha(args.fixture),
        "pdf_sha256": sha(args.pdf),
        "raw_sha256": sha(args.raw),
        "scores": scores,
        "cases": records,
    }
    with args.output.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(scores)


if __name__ == "__main__":
    main()
