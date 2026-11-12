"""Check signed USD amounts and source cells independently of the reader implementation."""

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader

from scripts.grade_expedia_replay import compact


def read_pages(path):
    if path.suffix == ".txt":
        return [(path.read_text("utf-8"),)]
    return [
        (page.extract_text() or "", page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False) or "")
        for page in PdfReader(path).pages
    ]


def grade(case, record, pages):
    expected = case["expected_usd_millions"]
    answer = record["answer"].replace(",", "").replace("−", "-").replace("负 ", "-").replace("负", "-")
    amounts = re.findall(r"(?<![\d.])(-?\d+(?:\.\d+)?)\s*百万美元", answer)
    if not amounts and record["verification"] == "insufficient_evidence":
        return "abstained"
    if [Decimal(value) for value in amounts] != [expected]:
        return "mismatch"
    number = f"{abs(expected):,}"
    signed = rf"(?:\(\s*{number}\s*\)|[−-]\s*{number})" if expected < 0 else number
    cell = re.compile(rf"\b{case['source_row_label']}\b(?:\s|[$]|[,\d])+?{signed}(?![\d,])", re.I)
    for citation in record.get("citations", []):
        page = citation["page"]
        if page not in case["accepted_source_pages"]:
            continue
        quote = compact(citation["quote"])
        if cell.search(quote) and any(quote in compact(text) for text in pages[page-1]):
            return "matched"
    return "mismatch"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--runs", required=True, type=Path)
    args = parser.parse_args()
    fixture = Path(__file__).resolve().parents[1] / "evaluation/tech-reader-original-questions.json"
    for report in json.loads(fixture.read_text("utf-8")).values():
        path = args.inputs / report["input"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == report["sha256"]
        pages = read_pages(path)
        for case in report["cases"]:
            row = json.loads((args.runs / (case["id"] + ".json")).read_text("utf-8"))
            assert row["input_sha256"] == report["sha256"] and row["question"] == case["request"]["question"]
            print(case["id"], grade(case, row["response"], pages))


if __name__ == "__main__":
    main()
