"""Tests for ingest-time redaction."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agentops.db import connect
from agentops.ingest import ingest_run


def _base(**overrides):
    payload = {
        "id": "run-1",
        "project": "demo",
        "agent": "assistant",
        "environment": "dev",
        "name": "hello",
        "status": "ok",
        "started_at": "2026-10-24T10:00:00+00:00",
        "ended_at": "2026-10-24T10:00:01+00:00",
        "latency_ms": 1000,
        "task_input": "user secret question",
        "task_output": "model answer",
        "tags": {"end_user_id": "user-42", "locale": "zh"},
        "steps": [
            {
                "seq": 1,
                "kind": "tool",
                "name": "search",
                "status": "ok",
                "input": {"q": "secret"},
                "output": "hits",
            }
        ],
    }
    payload.update(overrides)
    return payload


class TestRedact(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "agentops.db")

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_hash_mode(self) -> None:
        ingest_run(self.conn, _base(), redact="hash")
        row = self.conn.execute(
            "SELECT task_input, task_output, tags, task_input_truncated "
            "FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        expected = "sha256:" + hashlib.sha256(
            b"user secret question"
        ).hexdigest()
        self.assertEqual(row["task_input"], expected)
        self.assertTrue(row["task_output"].startswith("sha256:"))
        self.assertEqual(row["task_input_truncated"], 0)
        tags = json.loads(row["tags"])
        self.assertTrue(tags["end_user_id"].startswith("sha256:"))
        self.assertEqual(tags["locale"], "zh")
        step = self.conn.execute(
            "SELECT input, output FROM steps WHERE run_id = ?", ("run-1",)
        ).fetchone()
        self.assertTrue(step["input"].startswith("sha256:"))
        self.assertTrue(step["output"].startswith("sha256:"))

    def test_drop_mode(self) -> None:
        ingest_run(self.conn, _base(id="run-2"), redact="drop")
        row = self.conn.execute(
            "SELECT task_input, task_output, tags FROM runs WHERE id = ?",
            ("run-2",),
        ).fetchone()
        self.assertIsNone(row["task_input"])
        self.assertIsNone(row["task_output"])
        tags = json.loads(row["tags"])
        self.assertNotIn("end_user_id", tags)
        self.assertEqual(tags["locale"], "zh")
        step = self.conn.execute(
            "SELECT input, output FROM steps WHERE run_id = ?", ("run-2",)
        ).fetchone()
        self.assertIsNone(step["input"])
        self.assertIsNone(step["output"])


if __name__ == "__main__":
    unittest.main()
