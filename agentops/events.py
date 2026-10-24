"""Run event envelope and optional JSONL outbox (Kafka-ready, no broker)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_TYPE = "agentops.run"
EVENT_VERSION = 1


def make_run_event(
    *,
    action: str,
    run_id: str,
    status: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build the v1 run event that a future Kafka producer would publish."""
    return {
        "type": EVENT_TYPE,
        "v": EVENT_VERSION,
        "action": action,
        "run_id": run_id,
        "status": status,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def outbox_path(path: str | Path | None = None) -> Path | None:
    raw = path if path is not None else os.environ.get("AGENTOPS_EVENT_OUTBOX")
    if not raw:
        return None
    return Path(raw)


def append_outbox(
    event: dict[str, Any], path: str | Path | None = None
) -> Path | None:
    """Append one JSON line. No-op unless path/env is set. Returns file path."""
    target = outbox_path(path)
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, default=str)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return target


def emit_run_event(
    *,
    action: str,
    run_id: str,
    status: str,
    payload: dict[str, Any],
    outbox: str | Path | None = None,
) -> dict[str, Any]:
    """Create event and optionally append to the outbox file."""
    event = make_run_event(
        action=action, run_id=run_id, status=status, payload=payload
    )
    append_outbox(event, outbox)
    return event
