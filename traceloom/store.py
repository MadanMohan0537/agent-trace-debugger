import json
import sqlite3
from pathlib import Path

from .models import Run, Span
from .privacy import PrivacyPolicy, sanitize_run


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, task TEXT NOT NULL, success INTEGER NOT NULL, expected_failure TEXT, expires_at_ms INTEGER);
CREATE TABLE IF NOT EXISTS spans(run_id TEXT NOT NULL, span_id TEXT NOT NULL, sequence INTEGER NOT NULL,
 kind TEXT NOT NULL, name TEXT NOT NULL, started_ms INTEGER NOT NULL, duration_ms INTEGER NOT NULL,
 tokens INTEGER NOT NULL, cost_usd REAL NOT NULL, status TEXT NOT NULL, milestone TEXT,
 input_json TEXT NOT NULL, output_json TEXT NOT NULL, PRIMARY KEY(run_id,span_id));
CREATE TABLE IF NOT EXISTS privacy_events(run_id TEXT PRIMARY KEY, total_fields INTEGER NOT NULL,
 retained_fields INTEGER NOT NULL, dropped_fields INTEGER NOT NULL, redacted_values INTEGER NOT NULL);
"""


class TraceStore:
    def __init__(self, path: str | Path, policy: PrivacyPolicy = PrivacyPolicy()):
        self.path = str(path)
        self.policy = policy
        with sqlite3.connect(self.path) as db:
            db.executescript(SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(runs)")}
            if "expires_at_ms" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN expires_at_ms INTEGER")

    def ingest(self, run: Run, *, ingested_at_ms: int = 0, ttl_ms: int | None = None) -> dict:
        if ttl_ms is not None and ttl_ms <= 0:
            raise ValueError("ttl_ms must be positive")
        sequences = [span.sequence for span in run.spans]
        if len(sequences) != len(set(sequences)):
            raise ValueError("duplicate span sequence")
        run, privacy = sanitize_run(run, self.policy)
        expires_at_ms = ingested_at_ms + ttl_ms if ttl_ms is not None else None
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?)", (run.run_id, run.task, int(run.success), run.expected_failure, expires_at_ms))
            db.execute("DELETE FROM spans WHERE run_id=?", (run.run_id,))
            db.executemany("INSERT INTO spans VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                (s.run_id,s.span_id,s.sequence,s.kind,s.name,s.started_ms,s.duration_ms,s.tokens,s.cost_usd,s.status,s.milestone,
                 json.dumps(s.input,sort_keys=True),json.dumps(s.output,sort_keys=True)) for s in run.spans])
            db.execute("INSERT OR REPLACE INTO privacy_events VALUES (?,?,?,?,?)", (
                run.run_id, privacy.total_fields, privacy.retained_fields,
                privacy.dropped_fields, privacy.redacted_values,
            ))
        return privacy.to_dict()

    def purge_expired(self, now_ms: int) -> list[str]:
        """Delete expired traces deterministically using an injected clock."""
        with sqlite3.connect(self.path) as db:
            expired = [row[0] for row in db.execute(
                "SELECT run_id FROM runs WHERE expires_at_ms IS NOT NULL AND expires_at_ms<=? ORDER BY run_id",
                (now_ms,),
            )]
            for run_id in expired:
                db.execute("DELETE FROM spans WHERE run_id=?", (run_id,))
                db.execute("DELETE FROM privacy_events WHERE run_id=?", (run_id,))
                db.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
        return expired

    def privacy_summary(self) -> dict:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT COUNT(*), COALESCE(SUM(total_fields),0), COALESCE(SUM(retained_fields),0), COALESCE(SUM(dropped_fields),0), COALESCE(SUM(redacted_values),0) FROM privacy_events").fetchone()
        total = row[1]
        return {
            "runs_accounted": row[0], "total_fields": total,
            "retained_fields": row[2], "dropped_fields": row[3],
            "redacted_values": row[4],
            "retained_field_rate": round(row[2] / total, 6) if total else 1.0,
        }

    def runs(self) -> list[Run]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            result=[]
            for row in db.execute("SELECT * FROM runs ORDER BY run_id"):
                spans=tuple(Span(run_id=s["run_id"],span_id=s["span_id"],sequence=s["sequence"],kind=s["kind"],name=s["name"],
                    started_ms=s["started_ms"],duration_ms=s["duration_ms"],tokens=s["tokens"],cost_usd=s["cost_usd"],status=s["status"],
                    milestone=s["milestone"],input=json.loads(s["input_json"]),output=json.loads(s["output_json"]))
                    for s in db.execute("SELECT * FROM spans WHERE run_id=? ORDER BY sequence",(row["run_id"],)))
                result.append(Run(row["run_id"],row["task"],bool(row["success"]),spans,row["expected_failure"]))
            return result


