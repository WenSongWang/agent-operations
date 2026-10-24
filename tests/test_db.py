"""Schema smoke tests for agentops.db."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from agentops.db import connect


class TestDb(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "agentops.db"
        self.conn = connect(self.db_path)

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_connect_creates_runs_and_steps(self) -> None:
        tables = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("runs", tables)
        self.assertIn("steps", tables)

    def test_runs_has_filter_columns(self) -> None:
        cols = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(runs)")
        }
        for name in (
            "id",
            "project",
            "agent",
            "environment",
            "status",
            "started_at",
            "latency_ms",
            "model_ms",
            "tool_ms",
            "human_ms",
            "wait_ms",
            "ttft_ms",
            "extra",
            "ingested_at",
        ):
            self.assertIn(name, cols)

    def test_steps_primary_key_is_run_id_seq(self) -> None:
        info = list(self.conn.execute("PRAGMA table_info(steps)"))
        pk = {row["name"] for row in info if row["pk"]}
        self.assertEqual(pk, {"run_id", "seq"})

    def test_filter_indexes_exist(self) -> None:
        indexes = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        for name in (
            "idx_runs_started_at",
            "idx_runs_project",
            "idx_runs_agent",
            "idx_runs_environment",
            "idx_runs_status",
        ):
            self.assertIn(name, indexes)

    def test_reconnect_is_idempotent(self) -> None:
        self.conn.close()
        again = connect(self.db_path)
        try:
            n = again.execute(
                "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table'"
            ).fetchone()["c"]
            self.assertGreaterEqual(n, 2)
        finally:
            again.close()


if __name__ == "__main__":
    unittest.main()
