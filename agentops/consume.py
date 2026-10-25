"""Consume agentops.run Kafka events into the local DB (no re-emit)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from agentops.db import connect
from agentops.events import DEFAULT_KAFKA_TOPIC, EVENT_TYPE, EVENT_VERSION, kafka_bootstrap
from agentops.ingest import IngestError, ingest_run

DEFAULT_DB = Path("data") / "agentops.db"
DEFAULT_GROUP = "agentops-ingest"

# Tests inject: yields message value bytes (or None to stop).
MessagePoller = Callable[[], bytes | None]


class EventDecodeError(ValueError):
    """Kafka payload is not a valid agentops.run v1 event."""


def decode_run_event(raw: bytes | str | dict[str, Any]) -> dict[str, Any]:
    """Parse and validate an agentops.run v1 envelope."""
    if isinstance(raw, dict):
        event = raw
    else:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EventDecodeError(f"invalid JSON: {exc}") from exc
    if not isinstance(event, dict):
        raise EventDecodeError("event must be a JSON object")
    if event.get("type") != EVENT_TYPE:
        raise EventDecodeError(f"unexpected type: {event.get('type')!r}")
    if event.get("v") != EVENT_VERSION:
        raise EventDecodeError(f"unsupported version: {event.get('v')!r}")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise EventDecodeError("payload must be an object")
    return event


def apply_run_event(conn: Any, event: dict[str, Any]) -> str:
    """Write event.payload via ingest_run without re-publishing."""
    return ingest_run(conn, event["payload"], emit=False)


def process_kafka_value(conn: Any, raw: bytes | str) -> str:
    """Decode one message and ingest. Raises EventDecodeError / IngestError."""
    return apply_run_event(conn, decode_run_event(raw))


def _kafka_poller(
    bootstrap: str, topic: str, group_id: str, client_id: str
) -> MessagePoller:
    try:
        from kafka import KafkaConsumer  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Kafka consume needs kafka-python; "
            'pip install "agent-operations[kafka]"'
        ) from exc
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=[s.strip() for s in bootstrap.split(",") if s.strip()],
        group_id=group_id,
        client_id=client_id,
        enable_auto_commit=True,
        auto_offset_reset="earliest",
        consumer_timeout_ms=1000,
    )

    def poll() -> bytes | None:
        for msg in consumer:
            return msg.value
        return None

    poll.close = consumer.close  # type: ignore[attr-defined]
    return poll


def run_consumer(
    *,
    db: str | Path = DEFAULT_DB,
    bootstrap: str | None = None,
    topic: str | None = None,
    group_id: str | None = None,
    poller: MessagePoller | None = None,
    max_messages: int | None = None,
) -> int:
    """Poll Kafka (or poller) and ingest. Returns number of applied messages."""
    servers = (bootstrap or kafka_bootstrap() or "").strip()
    if poller is None and not servers:
        raise ValueError(
            "AGENTOPS_KAFKA_BOOTSTRAP (or bootstrap=) is required"
        )
    topic_name = (
        topic
        or os.environ.get("AGENTOPS_KAFKA_TOPIC", DEFAULT_KAFKA_TOPIC).strip()
        or DEFAULT_KAFKA_TOPIC
    )
    group = (
        group_id
        or os.environ.get("AGENTOPS_KAFKA_GROUP", DEFAULT_GROUP).strip()
        or DEFAULT_GROUP
    )
    client_id = (
        os.environ.get("AGENTOPS_KAFKA_CLIENT_ID", "agentops-consumer").strip()
        or "agentops-consumer"
    )
    own_poller = poller is None
    poll = poller or _kafka_poller(servers, topic_name, group, client_id)
    conn = connect(db)
    applied = 0
    try:
        while max_messages is None or applied < max_messages:
            raw = poll()
            if raw is None:
                if max_messages is not None:
                    break
                continue
            try:
                process_kafka_value(conn, raw)
                applied += 1
            except (EventDecodeError, IngestError) as exc:
                print(f"skip: {exc}")
    finally:
        conn.close()
        if own_poller and hasattr(poll, "close"):
            poll.close()  # type: ignore[attr-defined]
    return applied


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Consume agentops.run Kafka events into the local DB"
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("AGENTOPS_DATABASE_URL") or str(DEFAULT_DB),
        help="SQLite path or postgresql:// DSN",
    )
    parser.add_argument(
        "--bootstrap",
        default=None,
        help="Kafka bootstrap (default AGENTOPS_KAFKA_BOOTSTRAP)",
    )
    parser.add_argument("--topic", default=None)
    parser.add_argument("--group", default=None, dest="group_id")
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Stop after N applied messages (default: run forever)",
    )
    args = parser.parse_args()
    n = run_consumer(
        db=args.db,
        bootstrap=args.bootstrap,
        topic=args.topic,
        group_id=args.group_id,
        max_messages=args.max_messages,
    )
    print(f"applied {n} message(s)")


if __name__ == "__main__":
    main()
