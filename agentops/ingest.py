"""Validate and insert or finalize an agent run (with steps)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from agentops.events import emit_run_event
from agentops.metrics import compute_run_metrics
from agentops.redact import apply_to_run_fields, apply_to_step, resolve_mode

REQUIRED = (
    "id",
    "project",
    "agent",
    "environment",
    "name",
    "status",
    "started_at",
)

STEP_REQUIRED = ("seq", "kind", "name", "status")

ENVIRONMENTS = frozenset({"dev", "test", "uat", "prd"})
FINAL_STATUSES = frozenset({"ok", "error", "timeout", "cancelled"})
RUN_STATUSES = FINAL_STATUSES | {"running"}
STEP_STATUSES = FINAL_STATUSES
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
    "ended_at",
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
    """Invalid payload or illegal run id transition."""


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
        if status not in STEP_STATUSES:
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


def _build_row(
    payload: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    ingested_at: str,
    redact_mode: str,
) -> dict[str, Any]:
    derived = compute_run_metrics(payload, steps)
    row: dict[str, Any] = {k: payload[k] for k in REQUIRED}
    for key in OPTIONAL:
        if key in payload:
            row[key] = payload[key]
    if "ended_at" not in row:
        row["ended_at"] = None
    row.update(derived)

    task_in, task_in_trunc = _truncate_text(payload.get("task_input"))
    task_out, task_out_trunc = _truncate_text(payload.get("task_output"))
    extra, extra_trunc = _truncate_text(payload.get("extra"))
    redacted = apply_to_run_fields(
        task_input=task_in,
        task_input_truncated=task_in_trunc,
        task_output=task_out,
        task_output_truncated=task_out_trunc,
        tags=payload.get("tags"),
        mode=redact_mode,
    )
    row["task_input"] = redacted["task_input"]
    row["task_input_truncated"] = redacted["task_input_truncated"]
    row["task_output"] = redacted["task_output"]
    row["task_output_truncated"] = redacted["task_output_truncated"]
    row["tags"] = _as_json_text(redacted["tags"])
    row["extra"] = extra
    row["extra_truncated"] = extra_trunc
    row["ingested_at"] = ingested_at
    return row


def _insert_run_and_steps(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    columns = list(row.keys())
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO runs ({', '.join(columns)}) VALUES ({placeholders})"
    conn.execute(sql, [row[c] for c in columns])
    for step in steps:
        step_row = {"run_id": row["id"], **step}
        scols = list(step_row.keys())
        conn.execute(
            f"INSERT INTO steps ({', '.join(scols)}) "
            f"VALUES ({', '.join('?' for _ in scols)})",
            [step_row[c] for c in scols],
        )


def ingest_run(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    redact: str | None = None,
) -> str:
    """Insert a run, or finalize an existing running run. Returns run id.

    redact: off | hash | drop (default from AGENTOPS_REDACT, else off).
    """
    try:
        redact_mode = resolve_mode(redact)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc

    missing = [k for k in REQUIRED if not payload.get(k)]
    if missing:
        raise IngestError(f"missing required fields: {', '.join(missing)}")

    env = payload["environment"]
    if env not in ENVIRONMENTS:
        raise IngestError(f"invalid environment: {env!r}")

    status = payload["status"]
    if status not in RUN_STATUSES:
        raise IngestError(f"invalid status: {status!r}")

    if status in FINAL_STATUSES and not payload.get("ended_at"):
        raise IngestError("ended_at is required when status is final")

    trigger = payload.get("trigger")
    if trigger is not None and trigger not in TRIGGERS:
        raise IngestError(f"invalid trigger: {trigger!r}")

    finish = payload.get("finish_reason")
    if finish is not None and finish not in FINISH_REASONS:
        raise IngestError(f"invalid finish_reason: {finish!r}")

    steps = [
        apply_to_step(step, redact_mode)
        for step in _normalize_steps(payload.get("steps"))
    ]
    run_id = payload["id"]
    existing = conn.execute(
        "SELECT status, ingested_at FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    event_action: str | None = None

    try:
        conn.execute("BEGIN")
        if existing is None:
            row = _build_row(
                payload,
                steps,
                ingested_at=datetime.now(timezone.utc).isoformat(),
                redact_mode=redact_mode,
            )
            _insert_run_and_steps(conn, row, steps)
            event_action = "create"
        elif existing["status"] == "running" and status in FINAL_STATUSES:
            row = _build_row(
                payload,
                steps,
                ingested_at=existing["ingested_at"],
                redact_mode=redact_mode,
            )
            conn.execute("DELETE FROM steps WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            _insert_run_and_steps(conn, row, steps)
            event_action = "finalize"
        elif existing["status"] == "running" and status == "running":
            raise IngestError(f"run already running: {run_id!r}")
        else:
            raise IngestError(f"run already finalized: {run_id!r}")
        conn.commit()
    except IngestError:
        conn.rollback()
        raise
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise IngestError(f"duplicate run id: {run_id!r}") from exc
    except Exception:
        conn.rollback()
        raise

    if event_action is not None:
        emit_run_event(
            action=event_action,
            run_id=run_id,
            status=status,
            payload=payload,
        )
    return run_id
