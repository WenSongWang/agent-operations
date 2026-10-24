"""SQLite / Postgres schema for agent runs and steps."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Sequence

TABLES = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    agent TEXT NOT NULL,
    environment TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
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
    quality_score REAL,
    thumbs TEXT,
    prompt_version TEXT,
    template_version TEXT,
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
"""

# Columns added after the initial schema; applied with ALTER when missing.
RUN_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("quality_score", "REAL"),
    ("thumbs", "TEXT"),
    ("prompt_version", "TEXT"),
    ("template_version", "TEXT"),
)

RUN_INDEXES: tuple[tuple[str, str], ...] = (
    ("idx_runs_started_at", "started_at"),
    ("idx_runs_project", "project"),
    ("idx_runs_agent", "agent"),
    ("idx_runs_environment", "environment"),
    ("idx_runs_status", "status"),
    ("idx_runs_trace_id", "trace_id"),
    ("idx_runs_prompt_version", "prompt_version"),
    ("idx_runs_thumbs", "thumbs"),
)


def _qmark_sql(sql: str) -> str:
    """Translate SQLite '?' placeholders to psycopg '%s'."""
    return sql.replace("?", "%s")


def is_unique_violation(exc: BaseException) -> bool:
    """True for SQLite / Postgres duplicate-key style errors."""
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    try:
        from psycopg.errors import UniqueViolation  # type: ignore[import-untyped]
    except ImportError:
        return False
    return isinstance(exc, UniqueViolation)


class PgCompatConnection:
    """Thin wrapper: same execute('...?', params) API as sqlite3."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        # psycopg already opens a transaction; mirror sqlite's explicit BEGIN.
        if sql.strip().upper() == "BEGIN":
            return self._conn.cursor()
        return self._conn.execute(_qmark_sql(sql), params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def _migrate_sqlite(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"] for row in conn.execute("PRAGMA table_info(runs)")
    }
    for name, col_type in RUN_COLUMN_MIGRATIONS:
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {col_type}")
            existing.add(name)

    for index_name, column in RUN_INDEXES:
        if column in existing:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON runs({column})"
            )

    step_cols = {
        row["name"] for row in conn.execute("PRAGMA table_info(steps)")
    }
    if step_cols:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_steps_run_id ON steps(run_id)"
        )
        if "kind" in step_cols and "name" in step_cols:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_steps_kind_name "
                "ON steps(kind, name)"
            )
        if "error_type" in step_cols:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_steps_error_type "
                "ON steps(error_type)"
            )


def _migrate_pg(conn: Any) -> None:
    rows = conn.execute(
        "SELECT column_name AS name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'runs'"
    ).fetchall()
    existing = {row["name"] for row in rows}
    for name, col_type in RUN_COLUMN_MIGRATIONS:
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {col_type}")
            existing.add(name)

    for index_name, column in RUN_INDEXES:
        if column in existing:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON runs({column})"
            )

    step_rows = conn.execute(
        "SELECT column_name AS name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'steps'"
    ).fetchall()
    step_cols = {row["name"] for row in step_rows}
    if step_cols:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_steps_run_id ON steps(run_id)"
        )
        if "kind" in step_cols and "name" in step_cols:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_steps_kind_name "
                "ON steps(kind, name)"
            )
        if "error_type" in step_cols:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_steps_error_type "
                "ON steps(error_type)"
            )


def connect_postgres(dsn: str) -> PgCompatConnection:
    """Open Postgres (psycopg3) and ensure schema exists."""
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Postgres needs psycopg; "
            'pip install "agent-operations[postgres]"'
        ) from exc
    raw = psycopg.connect(dsn, row_factory=dict_row)
    wrapped = PgCompatConnection(raw)
    for stmt in TABLES.split(";"):
        sql = stmt.strip()
        if sql:
            wrapped.execute(sql)
    _migrate_pg(wrapped)
    wrapped.commit()
    return wrapped


def connect(path: str | Path) -> sqlite3.Connection | PgCompatConnection:
    """Open SQLite file, or Postgres when path/DSN is postgresql://…"""
    target = str(path).strip()
    if not target:
        target = os.environ.get("AGENTOPS_DATABASE_URL", "").strip()
    if target.startswith(("postgres://", "postgresql://")):
        return connect_postgres(target)

    db_path = Path(target)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(TABLES)
    _migrate_sqlite(conn)
    return conn
