"""Rebuild the public SQL tables from the original 120 runs and the frozen holdout."""

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def analyze(apple, amazon):
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE inputs(label TEXT PRIMARY KEY, body TEXT NOT NULL)")
        db.executemany(
            "INSERT INTO inputs VALUES(?,?)",
            [("apple", apple.read_text("utf-8")), ("amazon", amazon.read_text("utf-8"))],
        )
        db.executescript((ROOT / "evaluation/failure_analysis.sql").read_text("utf-8"))
        totals = dict(
            db.execute("SELECT count(*) AS runs,sum(passed) AS passed FROM runs").fetchone()
        )
        unique = db.execute("SELECT count(*) FROM (SELECT DISTINCT round,id FROM runs)").fetchone()[
            0
        ]
        if totals["runs"] != unique or unique != 120:
            raise ValueError("Incomplete or duplicate historical run")
        tables = {
            name: [dict(row) for row in db.execute("SELECT * FROM " + name)]
            for name in ("reason_frequency", "by_round_task", "paired", "first_failed_stage")
        }
        if (
            sum(row["pairs"] for row in tables["paired"]) != 60
            or sum(row["runs"] for row in tables["first_failed_stage"]) != 18
        ):
            raise ValueError("Unpaired runs or incomplete holdout")
        return {"historical": totals, **tables}


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--apple", type=Path, default=ROOT / "docs/model-runs.json")
    cli.add_argument("--amazon", type=Path, default=ROOT / "docs/amazon-first.json")
    cli.add_argument("--out", type=Path, default=ROOT / "docs/sql-results.json")
    args = cli.parse_args()
    args.out.write_text(
        json.dumps(analyze(args.apple, args.amazon), ensure_ascii=False, indent=2), "utf-8"
    )
