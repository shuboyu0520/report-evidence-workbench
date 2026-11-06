"""Evaluate page/evidence retrieval against fixed, manually checked PDF facts."""

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent import search  # noqa: E402
from app.main import parse_upload  # noqa: E402


def legacy_search(pages, query, limit=5):
    """Pre-improvement implementation, retained only for reproducible comparison."""
    terms = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2}", query.lower()))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", query))
    terms.update(chinese[i : i + 2] for i in range(len(chinese) - 1))
    hits = []
    for page in pages:
        for start in range(0, len(page["text"]), 650):
            quote = page["text"][start : start + 850]
            score = sum(quote.lower().count(term) for term in terms)
            if score:
                hits.append({"page": page["number"], "quote": quote, "score": score})
    return sorted(hits, key=lambda hit: -hit["score"])[:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=ROOT / "evaluation" / "retrieval_gold.json")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--algorithm", choices=("current", "legacy"), default="current")
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    pages_by_doc = {}
    sources = {}
    for document in gold["documents"]:
        path = ROOT / document["file"]
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != document["sha256"]:
            parser.error(f"PDF hash mismatch: {path}")
        pages_by_doc[document["id"]] = parse_upload(content, path.name)
        sources[document["id"]] = document["source"]

    results = []
    for case in gold["cases"]:
        pages = pages_by_doc[case["document"]]
        target = pages[case["page"] - 1]["text"]
        evidence_lines = [
            line for line in target.splitlines()
            if case["marker"].casefold() in line.casefold() and case["value"] in line
        ]
        if not evidence_lines:
            raise AssertionError(f"Gold evidence not found on page {case['page']}: {case['id']}")
        start = time.perf_counter()
        retriever = search if args.algorithm == "current" else legacy_search
        hits = retriever(pages, case["question"], limit=5)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        if any(hit["quote"] not in pages[hit["page"] - 1]["text"] for hit in hits):
            raise AssertionError(f"Retrieved quote is not a source substring: {case['id']}")
        rank = next((i + 1 for i, hit in enumerate(hits) if hit["page"] == case["page"]), None)
        evidence_rank = next(
            (i + 1 for i, hit in enumerate(hits)
             if hit["page"] == case["page"]
             and any(line.strip() in hit["quote"] for line in evidence_lines)),
            None,
        )
        results.append({
            "id": case["id"], "document": case["document"], "question": case["question"],
            "expected_page": case["page"], "page_rank": rank,
            "evidence_rank": evidence_rank, "top_pages": [hit["page"] for hit in hits],
            "elapsed_ms": elapsed_ms,
        })
    times = sorted(item["elapsed_ms"] for item in results)
    count = len(results)
    summary = {
        "cases": count, "documents": len(pages_by_doc), "sources": sources,
        "algorithm": args.algorithm,
        "page_hit_at_1": sum(item["page_rank"] == 1 for item in results),
        "page_hit_at_5": sum(item["page_rank"] is not None for item in results),
        "evidence_hit_at_5": sum(item["evidence_rank"] is not None for item in results),
        "page_mrr": round(sum(1 / item["page_rank"] if item["page_rank"] else 0 for item in results) / count, 3),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": times[max(0, int(count * .95) - 1)],
        "limits": "Fixed local page/evidence questions; lexical retrieval only. No LLM or answer evaluation. Results may not generalize beyond these reports.",
    }
    output = {"summary": summary, "cases": results}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
