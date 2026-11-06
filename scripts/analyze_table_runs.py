"""Rebuild the lookup failure breakdown from public per-question traces."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    query = (ROOT / "evaluation/table_failure_stages.sql").read_text(encoding="utf-8")
    runs = (ROOT / "docs/table-audit.json").read_text(encoding="utf-8")
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute(query, {"runs": runs})]
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
