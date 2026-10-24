"""Tests for run event envelope and JSONL outbox."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentops.db import connect
from agentops.events import make_run_event
from agentops.ingest import ingest_run


class TestEvents(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
