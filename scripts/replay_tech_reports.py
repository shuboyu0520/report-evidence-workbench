"""Replay the ten archived reader requests against their byte-identical source files."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx


def replay(inputs, output, api):
    fixture = Path(__file__).resolve().parents[1] / "evaluation/tech-reader-original-questions.json"
    reports = json.loads(fixture.read_text("utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    with httpx.Client(base_url=api, timeout=360, trust_env=False) as client:
        for report in reports.values():
            document = inputs / report["input"]
            content = document.read_bytes()
            if hashlib.sha256(content).hexdigest() != report["sha256"]:
                raise ValueError(f"Source file changed: {document.name}")
            fields = {key: report[key] for key in ("company", "published_on", "source_url")}
            fields["calendar_year"] = str(report["calendar_year"]).lower()
            upload = client.post("/reports", data=fields, files={"file": (document.name, content)})
            upload.raise_for_status()
            report_id = upload.json()["id"]
            for case in report["cases"]:
                response = client.post(f"/reports/{report_id}/questions", json=case["request"])
                response.raise_for_status()
                record = {
                    "id": case["id"],
                    "run_at": datetime.now(UTC).isoformat(),
                    "input_sha256": report["sha256"],
                    "question": case["request"]["question"],
                    "response": response.json(),
                }
                (output / (case["id"] + ".json")).write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(record["id"], record["response"]["verification"], record["response"]["answer"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--api", required=True)
    args = parser.parse_args()
    replay(args.inputs, args.out, args.api)
