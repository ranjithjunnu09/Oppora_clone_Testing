"""
SQLite run history.

Every run is persisted so a GPT-4.1-mini baseline captured today can be
compared against an open-model run next week. Single-user, local: plain
sqlite3, no ORM, no migrations framework.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

# Defaults next to this file. Override with OPPORA_DB_PATH when the repo lives
# on a network share or mounted volume — SQLite needs real file locking, which
# some mounted filesystems do not provide (you get "disk I/O error" on write).
DB_PATH = Path(os.environ.get("OPPORA_DB_PATH") or Path(__file__).resolve().parent / "runs.db")
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                      TEXT PRIMARY KEY,
    feature_id              TEXT NOT NULL,
    model                   TEXT NOT NULL,
    base_url                TEXT,
    status                  TEXT NOT NULL,
    created_at              REAL NOT NULL,
    finished_at             REAL,
    inputs_json             TEXT NOT NULL,
    result_json             TEXT,
    error                   TEXT,
    call_count              INTEGER DEFAULT 0,
    total_prompt_tokens     INTEGER DEFAULT 0,
    total_cached_tokens     INTEGER DEFAULT 0,
    total_completion_tokens INTEGER DEFAULT 0,
    total_cost_usd          REAL DEFAULT 0,
    total_latency_ms        INTEGER DEFAULT 0,
    calls_json              TEXT,
    batch_id                TEXT,
    quality_score           REAL,
    quality_json            TEXT,
    repeat_index            INTEGER DEFAULT 0,
    is_baseline             INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_feature ON runs(feature_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_batch   ON runs(batch_id);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# Columns added after the first release. CREATE TABLE IF NOT EXISTS does not
# alter an existing table, so an older runs.db would break with "no such
# column" without this. Additive only — no data is ever dropped.
_MIGRATIONS: list[tuple[str, str]] = [
    ("quality_score", "REAL"),
    ("quality_json", "TEXT"),
    ("repeat_index", "INTEGER DEFAULT 0"),
    ("is_baseline", "INTEGER DEFAULT 0"),
]


def _migrate(conn: sqlite3.Connection) -> list[str]:
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(runs)")}
    applied = []
    for column, decl in _MIGRATIONS:
        if column not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {decl}")
            applied.append(column)
    return applied


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _lock, _connect() as conn:
            conn.executescript(_SCHEMA)
            added = _migrate(conn)
            if added:
                print(f"[db] migrated runs.db, added columns: {', '.join(added)}")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"Could not initialise the run database at {DB_PATH} ({exc}). "
            "If the repo is on a network share or mounted volume, point "
            "OPPORA_DB_PATH at a local path instead, e.g. "
            "OPPORA_DB_PATH=C:\\Users\\you\\oppora-runs.db"
        ) from exc


def create_run(
    run_id: str,
    feature_id: str,
    model: str,
    inputs: dict,
    base_url: str | None = None,
    batch_id: str | None = None,
    repeat_index: int = 0,
) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """INSERT INTO runs (id, feature_id, model, base_url, status, created_at,
                                 inputs_json, batch_id, repeat_index)
               VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)""",
            (run_id, feature_id, model, base_url, time.time(),
             json.dumps(inputs, default=str), batch_id, repeat_index),
        )


def finish_run(
    run_id: str,
    result: Any,
    metrics: dict,
    status: str = "succeeded",
    error: str | None = None,
    quality: dict | None = None,
) -> None:
    """`status` may be 'degraded': the adapter returned without raising, but at
    least one underlying LLM call failed. Several feature files swallow
    exceptions and return None, so a run can otherwise look like a clean pass
    while carrying an empty result."""
    with _lock, _connect() as conn:
        conn.execute(
            """UPDATE runs SET status=?, finished_at=?, result_json=?,
                   call_count=?, total_prompt_tokens=?, total_cached_tokens=?,
                   total_completion_tokens=?, total_cost_usd=?, total_latency_ms=?,
                   calls_json=?, error=?
                   , quality_score=?, quality_json=?
               WHERE id=?""",
            (
                status,
                time.time(),
                json.dumps(result, default=str),
                metrics.get("call_count", 0),
                metrics.get("total_prompt_tokens", 0),
                metrics.get("total_cached_tokens", 0),
                metrics.get("total_completion_tokens", 0),
                metrics.get("total_cost_usd", 0.0),
                metrics.get("total_latency_ms", 0),
                json.dumps(metrics.get("calls", []), default=str),
                error,
                (quality or {}).get("score"),
                json.dumps(quality, default=str) if quality else None,
                run_id,
            ),
        )


def fail_run(run_id: str, error: str, metrics: dict | None = None) -> None:
    metrics = metrics or {}
    with _lock, _connect() as conn:
        conn.execute(
            """UPDATE runs SET status='failed', finished_at=?, error=?,
                   call_count=?, total_cost_usd=?, total_latency_ms=?, calls_json=?
               WHERE id=?""",
            (
                time.time(),
                error,
                metrics.get("call_count", 0),
                metrics.get("total_cost_usd", 0.0),
                metrics.get("total_latency_ms", 0),
                json.dumps(metrics.get("calls", []), default=str),
                run_id,
            ),
        )


def _row_to_dict(row: sqlite3.Row, include_heavy: bool = False) -> dict:
    d = dict(row)
    d["inputs"] = json.loads(d.pop("inputs_json") or "{}")
    result_json = d.pop("result_json", None)
    calls_json = d.pop("calls_json", None)
    quality_json = d.pop("quality_json", None)
    # quality_score stays on the row for cheap history/aggregate queries; the
    # full per-check report is only unpacked for detail views.
    if include_heavy:
        d["result"] = json.loads(result_json) if result_json else None
        d["calls"] = json.loads(calls_json) if calls_json else []
        d["quality"] = json.loads(quality_json) if quality_json else None
    return d


def get_run(run_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _row_to_dict(row, include_heavy=True) if row else None


def list_runs(feature_id: str | None = None, limit: int = 100) -> list[dict]:
    sql = "SELECT * FROM runs"
    params: list = []
    if feature_id:
        sql += " WHERE feature_id=?"
        params.append(feature_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_batch(batch_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE batch_id=? ORDER BY created_at ASC", (batch_id,)
        ).fetchall()
    return [_row_to_dict(r, include_heavy=True) for r in rows]


def set_baseline(run_id: str) -> None:
    """Pin one run per feature as the reference every other run is measured
    against. Migration decisions need a fixed comparison point, not whichever
    run happened to be first in the batch."""
    with _lock, _connect() as conn:
        row = conn.execute("SELECT feature_id FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return
        conn.execute("UPDATE runs SET is_baseline=0 WHERE feature_id=?", (row["feature_id"],))
        conn.execute("UPDATE runs SET is_baseline=1 WHERE id=?", (run_id,))


def get_baseline(feature_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE feature_id=? AND is_baseline=1", (feature_id,)
        ).fetchone()
    return _row_to_dict(row, include_heavy=True) if row else None


def stats() -> dict:
    with _connect() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS total_runs,
                      COALESCE(SUM(total_cost_usd), 0)  AS total_cost_usd,
                      COALESCE(SUM(call_count), 0)      AS total_calls,
                      COALESCE(SUM(total_prompt_tokens + total_completion_tokens), 0) AS total_tokens
               FROM runs"""
        ).fetchone()
    return dict(row)


def delete_all() -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM runs")
