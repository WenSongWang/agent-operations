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
        self.assertIn("finalized", str(ctx.exception))

    def test_running_then_finalize(self) -> None:
        ingest_run(
            self.conn,
            _base(status="running", ended_at=None, latency_ms=None),
        )
        row = self.conn.execute(
            "SELECT status, ended_at, latency_ms, ingested_at "
            "FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        self.assertEqual(row["status"], "running")
        self.assertIsNone(row["ended_at"])
        self.assertIsNone(row["latency_ms"])
        first_ingested = row["ingested_at"]

        ingest_run(
            self.conn,
            _base(
                status="error",
                error="boom",
                steps=[
                    {
                        "seq": 1,
                        "kind": "tool",
                        "name": "search",
                        "status": "error",
                        "error_type": "RuntimeError",
                        "error": "boom",
                    }
                ],
            ),
        )
        row = self.conn.execute(
            "SELECT status, ended_at, ingested_at, error FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        self.assertEqual(row["status"], "error")
        self.assertIsNotNone(row["ended_at"])
        self.assertEqual(row["ingested_at"], first_ingested)
        self.assertEqual(row["error"], "boom")
        steps = self.conn.execute(
            "SELECT COUNT(*) AS c FROM steps WHERE run_id = ?", ("run-1",)
        ).fetchone()
        self.assertEqual(steps["c"], 1)

    def test_running_again_rejected(self) -> None:
        ingest_run(
            self.conn,
            _base(status="running", ended_at=None, latency_ms=None),
        )
        with self.assertRaises(IngestError) as ctx:
            ingest_run(
                self.conn,
                _base(status="running", ended_at=None, latency_ms=None),
            )
        self.assertIn("already running", str(ctx.exception))

    def test_final_requires_ended_at(self) -> None:
        payload = _base()
        del payload["ended_at"]
        with self.assertRaises(IngestError) as ctx:
            ingest_run(self.conn, payload)
        self.assertIn("ended_at", str(ctx.exception))

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

    def test_steps_inserted_and_truncated(self) -> None:
        from agentops.ingest import MAX_TEXT_BYTES

        big = "y" * (MAX_TEXT_BYTES + 10)
        ingest_run(
            self.conn,
            _base(
                steps=[
                    {
                        "seq": 1,
                        "kind": "tool",
                        "name": "search",
                        "status": "error",
                        "input": big,
                        "error_type": "TimeoutError",
                        "error": "timed out",
                        "traceback": big,
                    }
                ]
            ),
        )
        step = self.conn.execute(
            "SELECT name, status, input_truncated, traceback_truncated "
            "FROM steps WHERE run_id = ? AND seq = 1",
            ("run-1",),
        ).fetchone()
        self.assertEqual(step["name"], "search")
        self.assertEqual(step["status"], "error")
        self.assertEqual(step["input_truncated"], 1)
        self.assertEqual(step["traceback_truncated"], 1)

    def test_metrics_from_steps(self) -> None:
        payload = _base(
            started_at="2026-10-24T10:00:00+00:00",
            ended_at="2026-10-24T10:00:05+00:00",
            steps=[
                {
                    "seq": 1,
                    "kind": "llm",
                    "name": "gpt",
                    "status": "ok",
                    "started_at": "2026-10-24T10:00:00+00:00",
                    "ended_at": "2026-10-24T10:00:02+00:00",
                    "ttft_ms": 120,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cost_usd": 0.01,
                },
                {
                    "seq": 2,
                    "kind": "tool",
                    "name": "search",
                    "status": "ok",
                    "started_at": "2026-10-24T10:00:02+00:00",
                    "ended_at": "2026-10-24T10:00:04+00:00",
                },
            ],
        )
        del payload["latency_ms"]
        ingest_run(self.conn, payload)
        row = self.conn.execute(
            "SELECT latency_ms, model_ms, tool_ms, wait_ms, ttft_ms, "
            "input_tokens, output_tokens, cost_usd FROM runs WHERE id = ?",
            ("run-1",),
        ).fetchone()
        self.assertEqual(row["latency_ms"], 5000)
        self.assertEqual(row["model_ms"], 2000)
        self.assertEqual(row["tool_ms"], 2000)
        self.assertEqual(row["wait_ms"], 1000)
        self.assertEqual(row["ttft_ms"], 120)
        self.assertEqual(row["input_tokens"], 10)
        self.assertEqual(row["output_tokens"], 5)
        self.assertEqual(row["cost_usd"], 0.01)


if __name__ == "__main__":
    unittest.main()
