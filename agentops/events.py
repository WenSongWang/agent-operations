"""Run event envelope, JSONL outbox, and optional Kafka producer."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

EVENT_TYPE = "agentops.run"
EVENT_VERSION = 1
DEFAULT_KAFKA_TOPIC = "agentops.run"

# Tests may replace this; signature: (topic, value_bytes, bootstrap, client_id) -> None
KafkaSender = Callable[[str, bytes, str, str], None]
_kafka_sender: KafkaSender | None = None


def make_run_event(
    *,
    action: str,
    run_id: str,
    status: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build the v1 run event published to outbox / Kafka."""
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


def kafka_bootstrap() -> str | None:
    raw = os.environ.get("AGENTOPS_KAFKA_BOOTSTRAP", "").strip()
    return raw or None


def set_kafka_sender(sender: KafkaSender | None) -> None:
    """Override Kafka send for tests. Pass None to restore the default client."""
    global _kafka_sender
    _kafka_sender = sender


def _default_kafka_send(
    topic: str, value: bytes, bootstrap: str, client_id: str
) -> None:
    try:
        from kafka import KafkaProducer  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised when extra missing
        raise ImportError(
            "Kafka publish needs kafka-python; "
            'pip install "agent-operations[kafka]"'
        ) from exc
    producer = KafkaProducer(
        bootstrap_servers=[s.strip() for s in bootstrap.split(",") if s.strip()],
        client_id=client_id,
    )
    try:
        future = producer.send(topic, value)
        future.get(timeout=10)
    finally:
        producer.close()


def publish_kafka(event: dict[str, Any]) -> bool:
    """Publish event JSON to Kafka. No-op unless AGENTOPS_KAFKA_BOOTSTRAP is set."""
    bootstrap = kafka_bootstrap()
    if not bootstrap:
        return False
    topic = os.environ.get("AGENTOPS_KAFKA_TOPIC", DEFAULT_KAFKA_TOPIC).strip() or (
        DEFAULT_KAFKA_TOPIC
    )
    client_id = os.environ.get("AGENTOPS_KAFKA_CLIENT_ID", "agentops").strip() or (
        "agentops"
    )
    value = json.dumps(event, ensure_ascii=False, default=str).encode("utf-8")
    sender = _kafka_sender or _default_kafka_send
    sender(topic, value, bootstrap, client_id)
    return True


def emit_run_event(
    *,
    action: str,
    run_id: str,
    status: str,
    payload: dict[str, Any],
    outbox: str | Path | None = None,
) -> dict[str, Any]:
    """Create event, optionally append outbox and/or publish to Kafka."""
    event = make_run_event(
        action=action, run_id=run_id, status=status, payload=payload
    )
    append_outbox(event, outbox)
    publish_kafka(event)
    return event
