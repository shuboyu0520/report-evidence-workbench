"""Evaluate rule-mode calculations against manually verified annual-report facts."""

import argparse
import hashlib
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument(
        "--gold", type=Path,
        default=Path(__file__).resolve().parents[1] / "evaluation" / "apple_2025_gold.json",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    content = args.pdf.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != gold["sha256"]:
        parser.error("PDF SHA-256 differs from the manually labelled report")

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "data") as temporary:
        app = create_app(db_path=Path(temporary) / "evaluation.db")
        with TestClient(app) as client:
            upload = client.post(
                "/reports", data={"company": "Apple Inc."},
                files={"file": (args.pdf.name, content, "application/pdf")},
            )
            upload.raise_for_status()
            report_id = upload.json()["id"]
            if upload.json()["metrics"] != 0:
                raise AssertionError("This evaluation assumes manual confirmation, not auto extraction")
            pages = {}
            for fact in gold["metrics"]:
                page = fact["page"]
                if page not in pages:
                    response = client.get(f"/reports/{report_id}/pages/{page}")
                    response.raise_for_status()
                    pages[page] = response.json()["text"]
                text = pages[page]
                marker = fact["marker"]
                marker_at = text.find(marker)
                if marker_at < 0:
                    raise AssertionError(f"Marker missing on PDF page {page}: {marker}")
                line_end = text.find("\n", marker_at)
                quote = text[: line_end if line_end >= 0 else len(text)]
                if len(quote) > 2000 or str(fact["year"]) not in quote or fact["source_value"] not in quote:
                    raise AssertionError(f"Manual fact not locatable: {fact['name']} {fact['year']}")
                confirmed = client.put(f"/reports/{report_id}/metrics", json={
                    "name": fact["name"], "year": fact["year"],
                    "source_value": fact["source_value"], "source_unit": "百万元",
                    "currency": "USD", "page": page, "quote": quote,
                    "scope": "consolidated_annual", "confirmed_by_user": True,
                })
                if confirmed.status_code != 200:
                    raise AssertionError(
                        f"Metric confirmation failed for {fact['name']} {fact['year']}: "
                        f"{confirmed.status_code} {confirmed.text}; quote={quote[-240:]}"
                    )

            cases = []
            for spec in gold["questions"]:
                start = time.perf_counter()
                response = client.post(
                    f"/reports/{report_id}/questions",
                    json={"question": spec["question"], "mode": "rules"},
                )
                elapsed = (time.perf_counter() - start) * 1000
                response.raise_for_status()
                result = response.json()
                calculation = next(
                    (step["result"] for step in result["trace"]
                     if step["tool"] == "calculate" and step["arguments"]["kind"] == spec["kind"]),
                    None,
                )
                if calculation is None:
                    passed = False
                    reason = "expected calculation tool was not called"
                elif "status" in spec:
                    passed = calculation["status"] == spec["status"]
                    reason = calculation.get("reason", "")
                else:
                    passed = (
                        calculation["status"] == "ok"
                        and calculation["year"] == spec["year"]
                        and calculation["value"] == spec["value"]
                        and any(c["page"] == spec["page"] for c in result["citations"])
                    )
                    reason = "" if passed else "wrong number, year or citation page"
                cases.append({
                    "question": spec["question"], "expected": spec,
                    "actual": calculation, "passed": passed,
                    "reason": reason, "elapsed_ms": round(elapsed, 2),
                })
            latencies = sorted(case["elapsed_ms"] for case in cases)
            summary = {
                "report": gold["report"], "source": gold["source"],
                "sha256": digest, "mode": "rules; 15 manually confirmed facts; no LLM",
                "cases": len(cases), "passed": sum(case["passed"] for case in cases),
                "positive": sum("value" in case["expected"] for case in cases),
                "missing_data": sum("status" in case["expected"] for case in cases),
                "median_ms": round(statistics.median(latencies), 2),
                "p95_ms": latencies[int(len(latencies) * .95) - 1],
                "limits": "One report, manually confirmed metrics, local in-process TestClient; not auto-extraction/RAG/LLM accuracy.",
            }
            output = {"summary": summary, "cases": cases}
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if summary["passed"] != summary["cases"]:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
