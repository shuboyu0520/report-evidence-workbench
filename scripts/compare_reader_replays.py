"""Compare replay answers, physical-page citations and disclosure states with archived runs."""

import argparse
import hashlib
import json
from pathlib import Path


def compare(before, after):
    previous = json.loads(before.read_text("utf8"))
    current = json.loads(after.read_text("utf8"))
    for field in ("fixture_sha256", "file_sha256", "config"):
        if previous[field] != current[field]:
            raise ValueError(f"Replays differ in {field}: {after}")
    rows = []
    for old, new in zip(previous["cases"], current["cases"], strict=True):
        if old["id"] != new["id"] or old["question"] != new["question"]:
            raise ValueError(f"Questions differ: {after}")
        if old["http"] != 200 or new["http"] != 200:
            raise ValueError(f"Request failed for {new['id']}: {after}")
        changed = [key for key in ("answer", "verification", "citations") if old[key] != new[key]]
        rows.append({"id": old["id"], "changed": changed})
    return {
        "same": sum(not row["changed"] for row in rows),
        "total": len(rows),
        "fixture_sha256": current["fixture_sha256"],
        "pdf_sha256": current["file_sha256"],
        "prior_run_sha256": hashlib.sha256(before.read_bytes()).hexdigest(),
        "replay_sha256": hashlib.sha256(after.read_bytes()).hexdigest(),
        "replay_start_utc": current["start_utc"],
        "config": current["config"],
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", action="append", nargs=3, metavar=("COHORT", "PRIOR", "REPLAY"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cohorts = {key: compare(Path(old), Path(new)) for key, old, new in args.pair}
    summary = {
        "same": sum(run["same"] for run in cohorts.values()),
        "total": sum(run["total"] for run in cohorts.values()),
        "checked_fields": ["answer", "verification", "citations (full content and physical page)"],
        "cohorts": cohorts,
    }
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf8")
    print(f"{summary['same']} / {summary['total']} identical")


if __name__ == "__main__":
    main()
