"""Validate a same-question Booking replay against the frozen fixture and original PDF."""

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text):
    return " ".join(text.split()).casefold()


def numeric_tokens(text):
    return {
        Decimal(token.replace(",", ""))
        for token in re.findall(r"(?<![.\d])[-+]?\d[\d,]*(?:\.\d+)?", text)
    }


def grade(gold, result, pages, cutoff):
    answer = result["answer"] or ""
    refs = result["citations"] or []
    state = result["verification"]
    if result["http"] != 200:
        return False, "HTTP failure"
    if any(
        not 0 < c["page"] <= len(pages)
        or not c["quote"].strip()
        or normalized(c["quote"]) not in pages[c["page"] - 1]
        for c in refs
    ):
        return False, "Citation not found on its physical page"
    if gold["kind"] == "future":
        return (
            state == "not_yet_disclosed"
            and cutoff in answer
            and "2026-12-31" in answer
            and "尚未披露" in answer
            and not refs
            and "美元" not in answer
        ), "Quarter-end disclosure gate"
    if gold["kind"] == "missing":
        return (
            state == "insufficient_evidence"
            and "没找到足够证据" in answer
            and not refs
            and not re.search(r"\d", answer)
        ), "Unsupported scope"
    if state == "insufficient_evidence":
        return False, "Insufficient evidence returned for answerable task"
    relevant = [c for c in refs if c["page"] in gold["accepted_pages"]]
    wanted = [Decimal(v.replace(",", "")) for v in gold["value"].split("–")]
    if (
        not relevant
        or not all(v in numeric_tokens(answer) for v in wanted)
        or gold["unit"] not in answer
    ):
        return False, "Wrong page, value or requested unit"
    if gold["kind"] == "expense" and gold["metric"] == "Personnel":
        correct = any(
            "personnel, including stock-based compensation" in normalized(c["quote"])
            and wanted[0] in numeric_tokens(c["quote"])
            for c in relevant
        )
        return (
            correct and all(s in answer for s in ("2026年第三季度", "人员费用", "含股权激励"))
        ), "Personnel total and included share-based cost"
    cell = next((t for t in result["trace"] if t["tool"] == "read_earnings_cell"), {})
    label = ("per diluted common share" if gold["metric"] == "GAAP diluted earnings per share"
             else gold["metric"].lower())
    period = re.search(r"(20\d{2})\s*年\s*第([一二三四])季度",gold["question"])
    if not period:
        return False,"Expected fiscal period missing from fixture"
    year, quarter = int(period[1]), "一二三四".index(period[2])+1
    row_supported = any(
        label in normalized(c["quote"])
        and normalized(c["quote"]) == normalized(cell.get("quote", ""))
        and all(value in numeric_tokens(c["quote"]) for value in wanted)
        for c in relevant
    )
    correct = (
        state == "source_earnings_cell"
        and row_supported
        and cell.get("page") in gold["accepted_pages"]
        and cell.get("year") == year
        and cell.get("quarter") == quarter
        and cell.get("unit") == gold["unit"]
        and cell.get("column") == (2 if year == 2025 else 1)
        and [Decimal(v.replace(",", "")) for v in cell.get("amounts", [])] == wanted
        and f"{year} 财年第{quarter}季度" in answer
        and ("指引" if gold["kind"]=="guidance" else "实际") in answer
    )
    if gold["kind"] in {"cash","adjusted"}:
        bridge = normalized(cell.get("context_quote",""))
        correct = (correct and normalized(cell.get("label","")) == label
                   and "reconciliation of" in bridge and bridge.endswith("to "+label)
                   and "(in millions" in normalized(cell.get("unit_quote",""))
                   and cell.get("unit_page")==10
                   and any(c["page"]==10 and c["quote"]==cell["unit_quote"] for c in refs)
                   and "three months ended" in normalized(cell.get("header",""))
                   and any(c["page"]==11 and c["quote"]==cell["header"] for c in refs))
        return correct,"Reconciliation total, quarter column and adjacent schedule unit checked"
    if gold["kind"]=="guidance":
        basis = "固定汇率同比" if "Constant Currency" in gold["metric"] else "报告口径同比"
        header = normalized(cell.get("header",""))
        correct = (correct and normalized(cell.get("label",""))==label and basis in answer
                   and cell.get("basis")==basis and "year-over-year" in header
                   and f"q{quarter} {year}" in header
                   and any(c["page"] in gold["accepted_pages"] and c["quote"]==cell["header"] for c in refs)
                   and [x.strip() for x in cell.get("raw_cell",[])]==[f"{v}%" for v in wanted]
                   and "guidance" in normalized(cell.get("context_quote","")))
        return correct,"Both original percentage endpoints, Q4 column, YoY basis and currency basis checked"
    return correct, "Metric, source row, physical page, period, column and unit checked"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("fixture", "pdf", "first", "replay", "output"):
        parser.add_argument("--" + arg, required=True, type=Path)
    parser.add_argument("--previous", type=Path, help="Optional raw replay immediately before the current repair")
    args = parser.parse_args()
    fixture, first, replay = [
        json.loads(p.read_text("utf8")) for p in (args.fixture, args.first, args.replay)
    ]
    assert sha(args.pdf) == fixture["sha256"] == replay["file_sha256"] == first["file_sha256"]
    assert sha(args.fixture) == replay["fixture_sha256"] == first["fixture_sha256"]
    assert first["config"] == replay["config"]
    previous=json.loads(args.previous.read_text("utf8")) if args.previous else first
    assert previous["config"]==replay["config"] and previous["file_sha256"]==replay["file_sha256"]
    assert previous["fixture_sha256"]==replay["fixture_sha256"]
    pages = [normalized(p.extract_text() or "") for p in PdfReader(args.pdf).pages]
    rows = []
    for g, old, prior, new in zip(fixture["cases"], first["cases"], previous["cases"],replay["cases"], strict=True):
        assert (
            g["id"] == old["id"] == prior["id"] == new["id"]
            and g["question"] == old["question"] == prior["question"] == new["question"]
        )
        passed, note = grade(g, new, pages, fixture["as_of"])
        rows.append(
            {
                "id": g["id"],
                "question": g["question"],
                "kind": g["kind"],
                "passed": bool(passed),
                "reason": note,
                "first_answer": old["answer"],
                "previous_answer": prior["answer"],
                "previous_passed": bool(grade(g,prior,pages,fixture["as_of"])[0]),
                "answer": new["answer"],
                "verification": new["verification"],
                "citations": new["citations"],
                "model_trace": new["model_trace"],
                "tools": new["trace"],
            }
        )
    scores = {}
    prior_scores={}
    for label, subset in (("lookup_guidance",[r for r in rows if r["kind"] not in {"future","missing"}]),
                          ("disclosure_status",[r for r in rows if r["kind"] in {"future","missing"}])):
        scores[label] = [sum(row["passed"] for row in subset), len(subset)]
        prior_scores[label]=[sum(row["previous_passed"] for row in subset),len(subset)]
    project = Path(__file__).resolve().parents[1]
    data = {
        "cohort": "same-question development replay of previously exposed Booking first-run fixture",
        "source": fixture["source"],
        "sha256_pdf": sha(args.pdf),
        "sha256_fixture": sha(args.fixture),
        "as_of": fixture["as_of"],
        "replay_start_utc": replay["start_utc"],
        "base_commit": replay["commit"],
        "config": replay["config"],
        "source_sha256": replay.get("source_sha256") or {
            name: sha(project / name) for name in ("app/earnings_tables.py", "app/reader.py")
        },
        "sha256_raw_replay": sha(args.replay),
        "sha256_first_run": sha(args.first),
        "sha256_previous_run": sha(args.previous or args.first),
        "previous_scores":prior_scores,
        "scores": scores,
        "cases": rows,
    }
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(scores), "failed:", [r["id"] for r in rows if not r["passed"]])


if __name__ == "__main__":
    main()
