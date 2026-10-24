"""SQLite schema for agent runs and steps."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    agent TEXT NOT NULL,
    environment TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    latency_ms REAL,
    model_ms REAL,
    tool_ms REAL,
    human_ms REAL,
    wait_ms REAL,
    ttft_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_tokens INTEGER,
    reasoning_tokens INTEGER,
    cost_usd REAL,
    error TEXT,
    task_input TEXT,
    task_input_truncated INTEGER NOT NULL DEFAULT 0,
    task_output TEXT,
    task_output_truncated INTEGER NOT NULL DEFAULT 0,
    trace_id TEXT,
    parent_run_id TEXT,
    session_id TEXT,
    trigger TEXT,
    attempt INTEGER,
    retry_of TEXT,
    finish_reason TEXT,
    provider TEXT,
    model TEXT,
    release TEXT,
    device_model TEXT,
    device_id TEXT,
    os TEXT,
    app_version TEXT,
    host TEXT,
    request_id TEXT,
    tags TEXT,
    extra TEXT,
    extra_truncated INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    latency_ms REAL,
    ttft_ms REAL,
    stream INTEGER,
    input TEXT,
    input_truncated INTEGER NOT NULL DEFAULT 0,
    output TEXT,
    output_truncated INTEGER NOT NULL DEFAULT 0,
    error_type TEXT,
    error TEXT,
    traceback TEXT,
    traceback_truncated INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_tokens INTEGER,
    reasoning_tokens INTEGER,
    cost_usd REAL,
    extra TEXT,
    extra_truncated INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, seq),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON runs(agent);
CREATE INDEX IF NOT EXISTS idx_runs_environment ON runs(environment);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_trace_id ON runs(trace_id);
CREATE INDEX IF NOT EXISTS idx_steps_run_id ON steps(run_id);
CREATE INDEX IF NOT EXISTS idx_steps_kind_name ON steps(kind, name);
CREATE INDEX IF NOT EXISTS idx_steps_error_type ON steps(error_type);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open SQLite and ensure schema exists."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
