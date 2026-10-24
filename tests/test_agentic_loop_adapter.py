"""Tests for agentic-loop journal adapter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentops.adapters.agentic_loop import AgentOpsJournal
from agentops.db import connect
from agentops.query import get_run


class TestAgenticLoopAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "agentops.db")

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_journal_running_then_finished(self) -> None:
        journal = AgentOpsJournal(
            self.conn,
            project="demo",
            agent="loop",
            environment="dev",
            run_id="al-1",
            name="triage",
        )
        journal.started(prompt="Summarize README", config={"model": "gpt-4o-mini"})
        running = get_run(self.conn, "al-1")
        assert running is not None
        self.assertEqual(running["status"], "running")

        journal.tool_result(
            turn=1, name="read_file", duration_ms=12.5, preview="ok"
        )
        journal.finished(
            terminal={"kind": "completed", "content": "done", "turns": 1},
            duration_ms=100.0,
        )
        detail = get_run(self.conn, "al-1")
        assert detail is not None
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["latency_ms"], 100.0)
        self.assertEqual(detail["model"], "gpt-4o-mini")
        self.assertEqual(len(detail["steps"]), 1)
        self.assertEqual(detail["steps"][0]["name"], "read_file")

    def test_error_terminal(self) -> None:
        journal = AgentOpsJournal(
            self.conn, project="demo", agent="loop", environment="dev", run_id="al-2"
        )
        journal.started(prompt="x", config={})
        journal.finished(
            terminal={"kind": "error", "error": "boom", "turns": 0},
            duration_ms=5,
        )
        detail = get_run(self.conn, "al-2")
        assert detail is not None
        self.assertEqual(detail["status"], "error")
        self.assertEqual(detail["error"], "boom")


if __name__ == "__main__":
    unittest.main()
