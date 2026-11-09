"""Run the ordinary upload/question endpoints, saving every response before moving to the next item."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as application
from app.main import create_app


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def main():
    parser = argparse.ArgumentParser()
    for key in ("fixture", "file", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--url", default=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text("utf8"))
    raw = args.file.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != fixture["sha256"]:
        raise ValueError("Input hash differs from the pre-registered file")
    args.out.mkdir(parents=True, exist_ok=False)
    config = {
        "ollama_url": args.url,
        "model": "qwen3:4b-instruct",
        "embedding_model": "qwen3-embedding:0.6b",
        "model_options": {"temperature": 0, "seed": 42, "num_ctx": 16384, "num_predict": 1024},
    }
    with TestClient(create_app(args.out / "local.sqlite", config)) as client:
        resp = client.post(
            "/reports",
            data={
                "company": fixture["company"],
                "published_on": fixture["published_on"],
                "calendar_year": str(fixture["calendar_year"]),
                "source_url": fixture["source"],
            },
            files={"file": (args.file.name, raw)},
        )
        resp.raise_for_status()
        rid = resp.json()["id"]
        module_dir = Path(application.__file__).resolve().parent
        revision = subprocess.run(["git","-C",str(module_dir),"rev-parse","HEAD"],capture_output=True,text=True)
        source_hashes = {p.relative_to(module_dir.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(module_dir.rglob("*.py"))}
        runs = {
            "commit": revision.stdout.strip() if revision.returncode==0 else None,
            "source_sha256": source_hashes,
            "start_utc": datetime.now(timezone.utc).isoformat(),
            "file_sha256": digest,
            "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
            "config": {k: v for k, v in config.items() if k != "ollama_url"},
            "cases": [],
        }
        for case in fixture["cases"]:
            res = client.post(
                f"/reports/{rid}/questions",
                json={"mode": "reader", "question": case["question"], "as_of": fixture["as_of"]},
            )
            row = res.json()
            record = {
                k: row.get(k)
                for k in (
                    "answer",
                    "verification",
                    "citations",
                    "trace",
                    "model_trace",
                    "runtime_events",
                    "detail",
                )
            }
            record.update(id=case["id"], http=res.status_code, question=case["question"])
            runs["cases"].append(record)
            write(args.out / "results.json", runs)
            print(case["id"], res.status_code, record["verification"], record["answer"], flush=True)


if __name__ == "__main__":
    main()
