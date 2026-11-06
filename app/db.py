import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, company TEXT NOT NULL, filename TEXT NOT NULL,
                    digest TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company, digest)
                );
                CREATE TABLE IF NOT EXISTS pages (
                    report_id TEXT REFERENCES reports(id) ON DELETE CASCADE,
                    number INTEGER NOT NULL, text TEXT NOT NULL,
                    PRIMARY KEY(report_id, number)
                );
                CREATE TABLE IF NOT EXISTS rag_indexes (
                    report_id TEXT REFERENCES reports(id) ON DELETE CASCADE,
                    cache_key TEXT NOT NULL, dim INTEGER NOT NULL, vectors BLOB NOT NULL,
                    PRIMARY KEY(report_id, cache_key)
                );
                CREATE TABLE IF NOT EXISTS metrics (
                    report_id TEXT REFERENCES reports(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, year INTEGER NOT NULL, value TEXT NOT NULL,
                    currency TEXT NOT NULL, unit TEXT NOT NULL, scope TEXT NOT NULL,
                    page INTEGER NOT NULL, quote TEXT NOT NULL, origin TEXT NOT NULL,
                    PRIMARY KEY(report_id, name, year)
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY, report_id TEXT REFERENCES reports(id),
                    result TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS report_versions (
                    report_id TEXT PRIMARY KEY REFERENCES reports(id),
                    revision INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS metric_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id TEXT NOT NULL REFERENCES reports(id),
                    revision INTEGER NOT NULL,
                    metric_name TEXT NOT NULL, year INTEGER NOT NULL,
                    previous_json TEXT, current_json TEXT NOT NULL, reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(report_id, revision)
                );
                CREATE TRIGGER IF NOT EXISTS metric_changes_no_update
                    BEFORE UPDATE ON metric_changes BEGIN
                    SELECT RAISE(ABORT, 'metric history is append only'); END;
                CREATE TRIGGER IF NOT EXISTS metric_changes_no_delete
                    BEFORE DELETE ON metric_changes BEGIN
                    SELECT RAISE(ABORT, 'metric history is append only'); END;
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def report(self, report_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        if not row:
            raise LookupError("财报不存在")
        return dict(row)

    def pages(self, report_id):
        self.report(report_id)
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT number, text FROM pages WHERE report_id=? ORDER BY number", (report_id,)
                )
            ]

    def metrics(self, report_id):
        self.report(report_id)
        with self.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM metrics WHERE report_id=? ORDER BY name, year DESC", (report_id,)
                )
            ]

    def save_analysis(self, result):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO analyses(id,report_id,result) VALUES(?,?,?)",
                (result["id"], result["report_id"], json.dumps(result, ensure_ascii=False)),
            )

    def analysis_inputs(self, report_id):
        """One SQLite read snapshot, including the exact metric revision used."""
        with self.connect() as conn:
            conn.execute("BEGIN")
            report = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
            if report is None:
                raise LookupError("财报不存在")
            pages = [dict(r) for r in conn.execute(
                "SELECT number,text FROM pages WHERE report_id=? ORDER BY number", (report_id,)
            )]
            metrics = [dict(r) for r in conn.execute(
                "SELECT * FROM metrics WHERE report_id=? ORDER BY name,year DESC", (report_id,)
            )]
            version = conn.execute(
                "SELECT revision FROM report_versions WHERE report_id=?", (report_id,)
            ).fetchone()
        return dict(report), pages, metrics, version["revision"] if version else 0
