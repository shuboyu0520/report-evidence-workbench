"""Run a frozen document holdout through the same API and B2 settings as the local demo."""
import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import create_app
from scripts.evaluate_model_ab import PROMPTS

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def judge(case, result, line):
    _, year, _, page, _, value = case
    answer = result.get("answer", "").replace("，", ",")
    clean = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", answer)
    initial = next((s["result"] for s in result.get("trace", [])
                    if s["tool"] == "search_report" and s["origin"] == "server"), [])
    if not page:
        remaining = re.sub(rf"(?<!\d){year}(?!\d)", "", answer)
        checks = {"refusal": bool(re.search(r"未披露|没有披露|无法|未提供|没有提供|未列示", answer))
                  and not re.search(r"\d", remaining)}
    else:
        checks = {
            "retrieval": any(h["page"] == page and line in h["quote"] for h in initial[:5]),
            "amount": bool(re.search(rf"(?<![\d.\-]){value.replace(',', '')}(?![\d.])", clean)),
            "year": bool(re.search(rf"(?<!\d){year}(?!\d)", answer)),
            "unit": bool(re.search(r"百万美元|百万\s*美金|USD\s*(?:millions?|mn)|million\s*(?:USD|US dollars)", answer,re.I)),
            "page": bool(re.search(rf"(?:第\s*{page}\s*页|{page}\s*页|(?:pages?|页码|物理页)\s*[:：]?\s*{page}(?!\d))", answer,re.I)),
        }
    trace = [{"origin": s["origin"], "tool": s["tool"], "args": s["arguments"],
              "pages": [h["page"] for h in s["result"] if "page" in h] if isinstance(s["result"],list) else [],
              "status": s["result"].get("status") if isinstance(s["result"],dict) else None}
             for s in result.get("trace", [])]
    return {"answer":result.get("answer",""),"verification":result.get("verification"),
            "checks":checks,"passed":all(checks.values()) and bool(result.get("answer")),
            "trace":trace,"model_requests":len(result.get("model_trace",[]))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--url",default="http://127.0.0.1:11434")
    parser.add_argument("--fixture",type=Path,default=ROOT/"evaluation/amazon_holdout.json")
    args = parser.parse_args()
    fixture = args.fixture
    gold = json.loads(fixture.read_text("utf-8"))
    pdf = args.pdf.read_bytes()
    if sha(pdf) != gold["sha256"]:
        raise ValueError("Report SHA-256 mismatch")
    reader = PdfReader(args.pdf)
    evidence = {}
    for id_, _, _, page, marker, value in gold["cases"]:
        if page:
            matches = [s.strip() for s in reader.pages[page-1].extract_text().splitlines()
                       if marker in s and value in s]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous or missing source line: {id_}")
            evidence[id_]=matches[0]
    args.out.mkdir(parents=True,exist_ok=False)
    settings = {"model":"qwen3:4b-instruct","embedding_model":"qwen3-embedding:0.6b","ollama_url":args.url,
                "system_prompt":PROMPTS["B"],"model_options":{"temperature":0,"seed":42,"num_ctx":16384,"num_predict":1024}}
    tags = httpx.get(args.url+"/api/tags").json()["models"]
    meta = {"commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
            "app_sha256":{p.name:sha(p.read_bytes()) for p in sorted((ROOT/"app").glob("*.py"))},
            "pdf_sha256":sha(pdf),"fixture_sha256":sha(fixture.read_bytes()),"runner_sha256":sha(Path(__file__).read_bytes()),
            "prompt_sha256":sha(PROMPTS["B"].encode()),"model_options":settings["model_options"],
            "models":{m["name"]:m["digest"] for m in tags if m["name"] in (settings["model"],settings["embedding_model"])},
            "started_utc":datetime.now(timezone.utc).isoformat(),"cases":[]}
    write(args.out/"manifest.json",{k:v for k,v in meta.items() if k!="cases"})
    with TestClient(create_app(args.out/"eval.db",settings)) as api:
        upload=api.post("/reports",data={"company":gold["issuer"]},files={"file":(args.pdf.name,pdf,"application/pdf")})
        upload.raise_for_status()
        rid=upload.json()["id"]
        for case in gold["cases"]:
            id_,year,label,page,_,_ = case
            question=f"{year} 财年，{label}{gold['instruction']}"
            begin=time.perf_counter()
            r=api.post(f"/reports/{rid}/questions",json={"mode":"rag","question":question})
            data=r.json()
            write(args.out/(id_+".json"),data)
            row=judge(case,data,evidence.get(id_))
            row.update(id=id_,question=question,type="lookup" if page else "missing",http=r.status_code,
                       elapsed_ms=round((time.perf_counter()-begin)*1000),target_page=page,year=year,expected=case[-1])
            meta["cases"].append(row)
            write(args.out/"results.json",meta)
            print(id_,row["http"],row["checks"],flush=True)


if __name__=="__main__":
    main()
