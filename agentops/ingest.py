"""Validate and insert a single completed agent run."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

REQUIRED = (
    "id",
    "project",
    "agent",
    "environment",
    "name",
    "status",
    "started_at",
    "ended_at",
)

ENVIRONMENTS = frozenset({"dev", "test", "uat", "prd"})
STATUSES = frozenset({"ok", "error", "timeout", "cancelled"})
TRIGGERS = frozenset({"user", "schedule", "webhook", "agent", "api"})
FINISH_REASONS = frozenset(
    {"stop", "length", "tool_calls", "content_filter"}
)

MAX_TEXT_BYTES = 64 * 1024

# Metric fields: absent or None stays SQL NULL; explicit 0 is stored as 0.
METRIC_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "cost_usd",
)

# Columns written as-is when present (excluding required + special-cased).
OPTIONAL = (
    "latency_ms",
    "model_ms",
    "tool_ms",
    "human_ms",
    "wait_ms",
    "ttft_ms",
    "error",
    "trace_id",
    "parent_run_id",
    "session_id",
    "trigger",
    "attempt",
    "retry_of",
    "finish_reason",
    "provider",
    "model",
    "release",
    "device_model",
    "device_id",
    "os",
    "app_version",
    "host",
    "request_id",
)


class IngestError(ValueError):
    """Invalid payload or duplicate run id."""


def _as_json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _truncate_text(value: Any) -> tuple[str | None, int]:
    """UTF-8 truncate to MAX_TEXT_BYTES. Returns (text, truncated_flag)."""
    text = _as_json_text(value)
    if text is None:
        return None, 0
    raw = text.encode("utf-8")
    if len(raw) <= MAX_TEXT_BYTES:
        return text, 0
    cut = raw[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
    return cut, 1


def ingest_run(conn: sqlite3.Connection, payload: dict[str, Any]) -> str:
    """Insert one run. Returns run id. Raises IngestError on failure."""
    missing = [k for k in REQUIRED if not payload.get(k)]
    if missing:
        raise IngestError(f"missing required fields: {', '.join(missing)}")

    env = payload["environment"]
    if env not in ENVIRONMENTS:
        raise IngestError(f"invalid environment: {env!r}")

    status = payload["status"]
    if status not in STATUSES:
        raise IngestError(f"invalid status: {status!r}")

    trigger = payload.get("trigger")
    if trigger is not None and trigger not in TRIGGERS:
        raise IngestError(f"invalid trigger: {trigger!r}")

    finish = payload.get("finish_reason")
    if finish is not None and finish not in FINISH_REASONS:
        raise IngestError(f"invalid finish_reason: {finish!r}")

    row: dict[str, Any] = {k: payload[k] for k in REQUIRED}
    for key in OPTIONAL:
        if key in payload:
            row[key] = payload[key]
    for key in METRIC_FIELDS:
        if key in payload and payload[key] is not None:
            row[key] = payload[key]

    task_in, task_in_trunc = _truncate_text(payload.get("task_input"))
    task_out, task_out_trunc = _truncate_text(payload.get("task_output"))
    extra, extra_trunc = _truncate_text(payload.get("extra"))
    row["task_input"] = task_in
    row["task_input_truncated"] = task_in_trunc
    row["task_output"] = task_out
    row["task_output_truncated"] = task_out_trunc
    row["tags"] = _as_json_text(payload.get("tags"))
    row["extra"] = extra
    row["extra_truncated"] = extra_trunc
    row["ingested_at"] = datetime.now(timezone.utc).isoformat()

    columns = list(row.keys())
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO runs ({', '.join(columns)}) VALUES ({placeholders})"
    try:
        conn.execute(sql, [row[c] for c in columns])
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise IngestError(f"duplicate run id: {row['id']!r}") from exc
    return row["id"]
