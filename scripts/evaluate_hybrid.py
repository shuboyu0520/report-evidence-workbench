"""Paired evidence-line evaluation. Run from project root with python -m scripts.evaluate_hybrid."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.agent import search
from app.main import create_app
from app.retrieval import MODEL, VERSION, embed, get_index

PARAPHRASES = {
    "2025-sales": "苹果在这一财年把所有商品和服务卖出去，一共收了多少钱？",
    "2025-rd": "苹果 2025 财年为开发新技术和产品花了多少？",
    "2025-cash": "苹果 2025 财年的主营业务实际带来了多少现金？",
    "meta-assets": "截至 2024 年底，这家公司控制的全部经济资源有多少？",
    "meta-liabilities": "这家公司在 2024 年底一共承担多少尚需偿付的义务？",
    "meta-marketing": "Meta 在 2024 年为推广产品与销售花了多少钱？",
}


async def run(args):
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    settings = {"model": "qwen3:4b-instruct", "embedding_model": MODEL, "ollama_url": args.url}
    app = create_app(out / "index.db", settings)
    all_cases, docs = [], {}
    for subset, filename in [
        ("Apple EN", "retrieval_gold.json"),
        ("Meta EN", "retrieval_holdout_meta.json"),
    ]:
        gold = json.loads((Path("evaluation") / filename).read_text(encoding="utf-8"))
        docs.update({d["id"]: d for d in gold["documents"]})
        for case in gold["cases"]:
            all_cases.append(dict(case, subset=subset))
            if case["id"] in PARAPHRASES:
                all_cases.append(
                    dict(
                        case,
                        id=case["id"] + "-zh",
                        subset="Chinese paraphrases",
                        question=PARAPHRASES[case["id"]],
                    )
                )
    records = []
    with TestClient(app) as api:
        async with httpx.AsyncClient(timeout=150) as http:
            for doc_id, doc in docs.items():
                pdf = Path(doc["file"])
                content = pdf.read_bytes()
                assert hashlib.sha256(content).hexdigest() == doc["sha256"]
                upload = api.post(
                    "/reports",
                    data={"company": doc_id},
                    files={"file": (pdf.name, content, "application/pdf")},
                )
                upload.raise_for_status()
                rid = upload.json()["id"]
                report, pages, _, _ = app.state.db.analysis_inputs(rid)
                index, digest = await get_index(http, app.state.db, report, pages, args.url, MODEL)
                print(doc_id, len(index.chunks), "indexed", flush=True)
                for case in [c for c in all_cases if c["document"] == doc_id]:
                    question = case["question"]
                    vector = (
                        await embed(
                            http,
                            args.url,
                            MODEL,
                            [
                                "Instruct: Retrieve the annual report passage that supports the question.\nQuery: "
                                + question
                            ],
                        )
                    )[0]
                    branches = index.rank(question, vector)
                    branches["table_lexical"] = search(pages, question)
                    evidence = [
                        line.strip()
                        for line in pages[case["page"] - 1]["text"].splitlines()
                        if case["marker"].lower() in line.lower() and case["value"] in line
                    ]
                    assert evidence
                    results = {}
                    for branch, hits in branches.items():
                        for hit in hits:
                            assert hit["quote"] in pages[hit["page"] - 1]["text"]
                        rank = next(
                            (
                                i
                                for i, h in enumerate(hits, 1)
                                if h["page"] == case["page"]
                                and any(line in h["quote"] for line in evidence)
                            ),
                            None,
                        )
                        results[branch] = {"rank": rank, "pages": [h["page"] for h in hits]}
                    records.append(
                        {
                            "id": case["id"],
                            "subset": case["subset"],
                            "question": question,
                            "target_page": case["page"],
                            "report": doc_id,
                            "results": results,
                        }
                    )
                if doc_id == "apple-2025":
                    real = api.post(
                        f"/reports/{rid}/questions",
                        json={
                            "mode": "rag",
                            "question": "苹果 2025 财年研发费用为多少百万美元？请查找原文并给出物理页码。",
                        },
                    )
                    real.raise_for_status()
                    answer = real.json()
                    (out / "end-to-end.json").write_text(
                        json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
    summary = {}
    for subset in ("Apple EN", "Meta EN", "Chinese paraphrases"):
        group = [r for r in records if r["subset"] == subset]
        scores = {}
        for branch in ("table_lexical", "bm25", "dense", "hybrid"):
            ranks = [r["results"][branch]["rank"] for r in group]
            scores[branch] = {
                "hit_at_5": sum(r is not None for r in ranks),
                "n": len(group),
                "mrr_at_5": round(sum(1 / r for r in ranks if r) / len(group), 3),
            }
        summary[subset] = scores
    payload = {
        "model": MODEL,
        "digest": digest,
        "chunking": VERSION,
        "rrf_k": 60,
        "candidate_depth": 40,
        "summary": summary,
        "cases": records,
        "documents": list(docs.values()),
        "limits": "Fixed reports. Six Chinese questions reuse annotated facts. Table baseline uses line windows; other three use identical 800-character chunks. Measures retrieval, not generated-answer accuracy.",
    }
    (out / "retrieval-results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("data/hybrid-evaluation"))
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    asyncio.run(run(parser.parse_args()))
