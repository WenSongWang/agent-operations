"""Tests for run event envelope, JSONL outbox, and Kafka publish hook."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentops.db import connect
from agentops.events import (
    emit_run_event,
    make_run_event,
    publish_kafka,
    set_kafka_sender,
)
from agentops.ingest import ingest_run


class TestEvents(unittest.TestCase):
    def tearDown(self) -> None:
        set_kafka_sender(None)

    def test_make_run_event_shape(self) -> None:
        event = make_run_event(
            action="create",
            run_id="r1",
            status="ok",
            payload={"id": "r1"},
        )
        self.assertEqual(event["type"], "agentops.run")
        self.assertEqual(event["v"], 1)
        self.assertEqual(event["action"], "create")
        self.assertEqual(event["run_id"], "r1")
        self.assertIn("emitted_at", event)

    def test_ingest_appends_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "events.jsonl"
            db = Path(tmp) / "agentops.db"
            conn = connect(db)
            try:
                with mock.patch.dict(os.environ, {"AGENTOPS_EVENT_OUTBOX": str(outbox)}):
                    ingest_run(
                        conn,
                        {
                            "id": "r1",
                            "project": "demo",
                            "agent": "a",
                            "environment": "dev",
                            "name": "t",
                            "status": "ok",
                            "started_at": "2026-10-24T10:00:00+00:00",
                            "ended_at": "2026-10-24T10:00:01+00:00",
                        },
                    )
                lines = outbox.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)
                event = json.loads(lines[0])
                self.assertEqual(event["action"], "create")
                self.assertEqual(event["run_id"], "r1")
            finally:
                conn.close()

    def test_publish_kafka_noop_without_bootstrap(self) -> None:
        sent: list[tuple] = []
        set_kafka_sender(lambda *a: sent.append(a))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENTOPS_KAFKA_BOOTSTRAP", None)
            self.assertFalse(publish_kafka({"type": "agentops.run", "run_id": "r1"}))
        self.assertEqual(sent, [])

    def test_emit_publishes_kafka_when_configured(self) -> None:
        sent: list[tuple] = []
        set_kafka_sender(lambda *a: sent.append(a))
        env = {
            "AGENTOPS_KAFKA_BOOTSTRAP": "localhost:9092",
            "AGENTOPS_KAFKA_TOPIC": "agentops.test",
            "AGENTOPS_KAFKA_CLIENT_ID": "test-client",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            event = emit_run_event(
                action="create",
                run_id="r2",
                status="ok",
                payload={"id": "r2"},
            )
        self.assertEqual(len(sent), 1)
        topic, value, bootstrap, client_id = sent[0]
        self.assertEqual(topic, "agentops.test")
        self.assertEqual(bootstrap, "localhost:9092")
        self.assertEqual(client_id, "test-client")
        self.assertEqual(json.loads(value.decode("utf-8"))["run_id"], event["run_id"])


if __name__ == "__main__":
    unittest.main()
