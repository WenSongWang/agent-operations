"""Tests for Kafka event decode / apply (no broker)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentops.consume import (
    EventDecodeError,
    apply_run_event,
    decode_run_event,
    process_kafka_value,
    run_consumer,
)
from agentops.db import connect
from agentops.events import make_run_event
from agentops.ingest import IngestError, ingest_run
from agentops.query import get_run


def _payload(run_id: str = "c1", **extra):
    base = {
        "id": run_id,
        "project": "demo",
        "agent": "a",
        "environment": "dev",
        "name": "t",
        "status": "ok",
        "started_at": "2026-10-24T10:00:00+00:00",
        "ended_at": "2026-10-24T10:00:01+00:00",
    }
    base.update(extra)
    return base


class TestConsume(unittest.TestCase):
    def test_decode_and_apply(self) -> None:
        event = make_run_event(
            action="create",
            run_id="c1",
            status="ok",
            payload=_payload("c1"),
        )
        decoded = decode_run_event(json.dumps(event).encode("utf-8"))
        self.assertEqual(decoded["run_id"], "c1")
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agentops.db")
            try:
                run_id = apply_run_event(conn, decoded)
                self.assertEqual(run_id, "c1")
                self.assertEqual(get_run(conn, "c1")["id"], "c1")
            finally:
                conn.close()

    def test_decode_rejects_bad_type(self) -> None:
        with self.assertRaises(EventDecodeError):
            decode_run_event({"type": "other", "v": 1, "payload": {}})

    def test_emit_false_skips_kafka(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agentops.db")
            try:
                with mock.patch("agentops.ingest.emit_run_event") as emit:
                    ingest_run(conn, _payload("e1"), emit=False)
                    emit.assert_not_called()
                    ingest_run(conn, _payload("e2"), emit=True)
                    emit.assert_called_once()
            finally:
                conn.close()

    def test_run_consumer_with_poller(self) -> None:
        event = make_run_event(
            action="create",
            run_id="p1",
            status="ok",
            payload=_payload("p1"),
        )
        raw = json.dumps(event).encode("utf-8")
        bag = [raw]

        def poll() -> bytes | None:
            return bag.pop(0) if bag else None

        with tempfile.TemporaryDirectory() as tmp:
            n = run_consumer(
                db=Path(tmp) / "agentops.db",
                poller=poll,
                max_messages=5,
            )
            self.assertEqual(n, 1)
            conn = connect(Path(tmp) / "agentops.db")
            try:
                self.assertIsNotNone(get_run(conn, "p1"))
            finally:
                conn.close()

    def test_main_missing_bootstrap_prints_next(self) -> None:
        import io
        from contextlib import redirect_stderr

        from agentops import consume as consume_mod

        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENTOPS_KAFKA_BOOTSTRAP", None)
            with mock.patch(
                "sys.argv",
                ["agentops-kafka", "--db", str(Path(tempfile.mkdtemp()) / "x.db")],
            ):
                with redirect_stderr(buf):
                    with self.assertRaises(SystemExit) as ctx:
                        consume_mod.main()
        self.assertEqual(ctx.exception.code, 1)
        err = buf.getvalue()
        self.assertIn("error:", err)
        self.assertIn("next:", err)
        self.assertIn("KAFKA", err.upper())

    def test_process_duplicate_is_ingest_error(self) -> None:
        event = make_run_event(
            action="create",
            run_id="d1",
            status="ok",
            payload=_payload("d1"),
        )
        raw = json.dumps(event)
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agentops.db")
            try:
                process_kafka_value(conn, raw)
                with self.assertRaises(IngestError):
                    process_kafka_value(conn, raw)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
