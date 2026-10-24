"""Schema smoke tests for agentops.db."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentops.db import (
    PgCompatConnection,
    _qmark_sql,
    connect,
    is_unique_violation,
)


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

    def test_qmark_sql(self) -> None:
        self.assertEqual(
            _qmark_sql("SELECT * FROM runs WHERE id = ? AND project = ?"),
            "SELECT * FROM runs WHERE id = %s AND project = %s",
        )

    def test_is_unique_violation_sqlite(self) -> None:
        self.assertTrue(is_unique_violation(sqlite3.IntegrityError("unique")))
        self.assertFalse(is_unique_violation(ValueError("nope")))

    def test_pg_compat_begin_and_qmark(self) -> None:
        raw = mock.MagicMock()
        raw.cursor.return_value = "cursor"
        raw.execute.return_value = "exec"
        pg = PgCompatConnection(raw)
        self.assertEqual(pg.execute("BEGIN"), "cursor")
        raw.execute.assert_not_called()
        pg.execute("SELECT * FROM runs WHERE id = ?", ("r1",))
        raw.execute.assert_called_once_with(
            "SELECT * FROM runs WHERE id = %s", ("r1",)
        )

    def test_connect_routes_postgres_dsn(self) -> None:
        sentinel = object()
        with mock.patch(
            "agentops.db.connect_postgres", return_value=sentinel
        ) as m:
            out = connect("postgresql://localhost/agentops")
        self.assertIs(out, sentinel)
        m.assert_called_once_with("postgresql://localhost/agentops")


if __name__ == "__main__":
    unittest.main()
