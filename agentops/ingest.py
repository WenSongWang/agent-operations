"""Validate and insert a single completed agent run (with steps)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from agentops.metrics import compute_run_metrics

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

STEP_REQUIRED = ("seq", "kind", "name", "status")

ENVIRONMENTS = frozenset({"dev", "test", "uat", "prd"})
STATUSES = frozenset({"ok", "error", "timeout", "cancelled"})
TRIGGERS = frozenset({"user", "schedule", "webhook", "agent", "api"})
FINISH_REASONS = frozenset(
    {"stop", "length", "tool_calls", "content_filter"}
)
STEP_KINDS = frozenset({"llm", "tool", "agent", "human"})

MAX_TEXT_BYTES = 64 * 1024

METRIC_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "cost_usd",
)

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

STEP_OPTIONAL = (
    "started_at",
    "ended_at",
    "latency_ms",
    "ttft_ms",
    "stream",
    "error_type",
    "error",
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
    text = _as_json_text(value)
    if text is None:
        return None, 0
    raw = text.encode("utf-8")
    if len(raw) <= MAX_TEXT_BYTES:
        return text, 0
    cut = raw[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
    return cut, 1


def _normalize_steps(raw_steps: Any) -> list[dict[str, Any]]:
    if raw_steps is None:
        return []
    if not isinstance(raw_steps, list):
        raise IngestError("steps must be a list")
    steps: list[dict[str, Any]] = []
    seen_seq: set[int] = set()
    for item in raw_steps:
        if not isinstance(item, dict):
            raise IngestError("each step must be an object")
        missing = [k for k in STEP_REQUIRED if k not in item or item[k] is None]
        if missing:
            raise IngestError(
                f"step missing required fields: {', '.join(missing)}"
            )
        kind = item["kind"]
        if kind not in STEP_KINDS:
            raise IngestError(f"invalid step kind: {kind!r}")
        status = item["status"]
        if status not in STATUSES:
            raise IngestError(f"invalid step status: {status!r}")
        seq = int(item["seq"])
        if seq in seen_seq:
            raise IngestError(f"duplicate step seq: {seq}")
        seen_seq.add(seq)

        row: dict[str, Any] = {
            "seq": seq,
            "kind": kind,
            "name": item["name"],
            "status": status,
        }
        for key in STEP_OPTIONAL:
            if key in item:
                row[key] = item[key]
        if "stream" in row and row["stream"] is not None:
            row["stream"] = 1 if row["stream"] else 0
        for key in METRIC_FIELDS:
            if key in item and item[key] is not None:
                row[key] = item[key]

        inp, inp_t = _truncate_text(item.get("input"))
        out, out_t = _truncate_text(item.get("output"))
        tb, tb_t = _truncate_text(item.get("traceback"))
        extra, extra_t = _truncate_text(item.get("extra"))
        row["input"] = inp
        row["input_truncated"] = inp_t
        row["output"] = out
        row["output_truncated"] = out_t
        row["traceback"] = tb
        row["traceback_truncated"] = tb_t
        row["extra"] = extra
        row["extra_truncated"] = extra_t
        steps.append(row)
    return steps


def ingest_run(conn: sqlite3.Connection, payload: dict[str, Any]) -> str:
    """Insert one run and its steps. Returns run id."""
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

    steps = _normalize_steps(payload.get("steps"))
    derived = compute_run_metrics(payload, steps)

    row: dict[str, Any] = {k: payload[k] for k in REQUIRED}
    for key in OPTIONAL:
        if key in payload:
            row[key] = payload[key]
    row.update(derived)

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
        conn.execute("BEGIN")
        conn.execute(sql, [row[c] for c in columns])
        for step in steps:
            step_row = {"run_id": row["id"], **step}
            scols = list(step_row.keys())
            conn.execute(
                f"INSERT INTO steps ({', '.join(scols)}) "
                f"VALUES ({', '.join('?' for _ in scols)})",
                [step_row[c] for c in scols],
            )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise IngestError(f"duplicate run id: {row['id']!r}") from exc
    except Exception:
        conn.rollback()
        raise
    return row["id"]
