"""Tests for agentops.query."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentops.db import connect
from agentops.ingest import ingest_run
from agentops.query import (
    get_run,
    list_runs,
    list_tool_failures,
    summarize_runs,
)


def _run(run_id: str, **overrides):
    payload = {
        "id": run_id,
        "project": "demo",
        "agent": "assistant",
        "environment": "dev",
        "name": "task",
        "status": "ok",
        "started_at": "2026-10-24T10:00:00+00:00",
        "ended_at": "2026-10-24T10:00:01+00:00",
        "latency_ms": 1000,
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.02,
    }
    payload.update(overrides)
    return payload


class TestQuery(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "agentops.db")
        ingest_run(
            self.conn,
            _run(
                "ok-1",
                started_at="2026-10-24T10:00:00+00:00",
                latency_ms=1000,
                ttft_ms=100,
            ),
        )
        err = _run(
            "err-1",
            status="error",
            started_at="2026-10-24T11:00:00+00:00",
            latency_ms=2000,
            steps=[
                {
                    "seq": 1,
                    "kind": "tool",
                    "name": "search",
                    "status": "error",
                    "error_type": "TimeoutError",
                    "error": "timed out",
                    "input": {"q": "x"},
                }
            ],
        )
        del err["input_tokens"]
        del err["output_tokens"]
        del err["cost_usd"]
        ingest_run(self.conn, err)

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_list_runs_newest_first_and_filter(self) -> None:
        rows = list_runs(self.conn)
        self.assertEqual([r["id"] for r in rows], ["err-1", "ok-1"])
        filtered = list_runs(self.conn, status="error")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "err-1")

    def test_summary_and_percentiles(self) -> None:
        summary = summarize_runs(self.conn, project="demo")
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["by_status"]["ok"], 1)
        self.assertEqual(summary["by_status"]["error"], 1)
        self.assertEqual(summary["success_rate"], 0.5)
        self.assertEqual(summary["tokens"]["input"], 10)
        self.assertEqual(summary["tokens"]["unreported"]["input"], 1)
        self.assertEqual(summary["cost_usd"]["unreported"], 1)
        self.assertEqual(summary["latency_ms"]["max"], 2000)
        self.assertIsNotNone(summary["latency_ms"]["p50"])

    def test_tool_failures_and_get_run(self) -> None:
        groups = list_tool_failures(self.conn)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["tool_name"], "search")
        self.assertEqual(groups[0]["error_type"], "TimeoutError")
        self.assertEqual(groups[0]["count"], 1)
        detail = get_run(self.conn, "err-1")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(len(detail["steps"]), 1)
        self.assertEqual(detail["steps"][0]["name"], "search")


if __name__ == "__main__":
    unittest.main()
