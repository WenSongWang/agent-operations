"""Tests for agentops.ingest."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentops.db import connect
from agentops.ingest import IngestError, ingest_run


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
    }
    payload.update(overrides)
    return payload


class TestIngest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "agentops.db")

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_ingest_success(self) -> None:
        run_id = ingest_run(self.conn, _base())
        self.assertEqual(run_id, "run-1")
        row = self.conn.execute(
            "SELECT project, agent, environment, status, latency_ms "
            "FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        self.assertEqual(row["project"], "demo")
        self.assertEqual(row["agent"], "assistant")
        self.assertEqual(row["environment"], "dev")
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["latency_ms"], 1000)

    def test_missing_required_rejected(self) -> None:
        payload = _base()
        del payload["agent"]
        with self.assertRaises(IngestError) as ctx:
            ingest_run(self.conn, payload)
        self.assertIn("agent", str(ctx.exception))

    def test_invalid_environment_rejected(self) -> None:
        with self.assertRaises(IngestError) as ctx:
            ingest_run(self.conn, _base(environment="prod"))
        self.assertIn("environment", str(ctx.exception))

    def test_invalid_status_rejected(self) -> None:
        with self.assertRaises(IngestError) as ctx:
            ingest_run(self.conn, _base(status="failed"))
        self.assertIn("status", str(ctx.exception))

    def test_duplicate_id_rejected(self) -> None:
        ingest_run(self.conn, _base())
        with self.assertRaises(IngestError) as ctx:
            ingest_run(self.conn, _base())
        self.assertIn("duplicate", str(ctx.exception))

    def test_unreported_metrics_stay_null(self) -> None:
        ingest_run(self.conn, _base())
        row = self.conn.execute(
            "SELECT input_tokens, output_tokens, cached_tokens, "
            "reasoning_tokens, cost_usd FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        for col in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "reasoning_tokens",
            "cost_usd",
        ):
            self.assertIsNone(row[col])

    def test_explicit_zero_metrics_stored(self) -> None:
        ingest_run(
            self.conn,
            _base(input_tokens=0, output_tokens=0, cost_usd=0.0),
        )
        row = self.conn.execute(
            "SELECT input_tokens, output_tokens, cost_usd "
            "FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        self.assertEqual(row["input_tokens"], 0)
        self.assertEqual(row["output_tokens"], 0)
        self.assertEqual(row["cost_usd"], 0.0)

    def test_large_task_fields_truncated(self) -> None:
        from agentops.ingest import MAX_TEXT_BYTES

        big = "x" * (MAX_TEXT_BYTES + 100)
        ingest_run(
            self.conn,
            _base(task_input=big, task_output=big, extra={"blob": big}),
        )
        row = self.conn.execute(
            "SELECT task_input, task_input_truncated, task_output, "
            "task_output_truncated, extra, extra_truncated "
            "FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        self.assertEqual(row["task_input_truncated"], 1)
        self.assertEqual(row["task_output_truncated"], 1)
        self.assertEqual(row["extra_truncated"], 1)
        self.assertLessEqual(
            len(row["task_input"].encode("utf-8")), MAX_TEXT_BYTES
        )
        self.assertLessEqual(
            len(row["task_output"].encode("utf-8")), MAX_TEXT_BYTES
        )
        self.assertLessEqual(len(row["extra"].encode("utf-8")), MAX_TEXT_BYTES)


if __name__ == "__main__":
    unittest.main()
