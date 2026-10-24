"""Tests for LangGraph-style traced_invoke helper."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentops.adapters.langgraph import traced_invoke
from agentops.db import connect
from agentops.query import get_run


class _FakeGraph:
    def invoke(self, inputs, config=None):
        return {"echo": inputs, "config": config}


class TestLangGraphAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "agentops.db")

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_traced_invoke_records_run(self) -> None:
        result = traced_invoke(
            _FakeGraph(),
            {"q": "hi"},
            conn=self.conn,
            project="demo",
            agent="graph",
            environment="dev",
            name="echo-graph",
            run_id="lg-1",
            config={"configurable": {"thread_id": "t1"}},
        )
        self.assertEqual(result["echo"], {"q": "hi"})
        detail = get_run(self.conn, "lg-1")
        assert detail is not None
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["name"], "echo-graph")
        self.assertEqual(len(detail["steps"]), 1)
        self.assertEqual(detail["steps"][0]["kind"], "agent")

    def test_traced_invoke_captures_error(self) -> None:
        class Boom:
            def invoke(self, inputs, config=None):
                raise RuntimeError("graph failed")

        with self.assertRaises(RuntimeError):
            traced_invoke(
                Boom(),
                {"q": "x"},
                conn=self.conn,
                project="demo",
                agent="graph",
                environment="dev",
                run_id="lg-2",
            )
        detail = get_run(self.conn, "lg-2")
        assert detail is not None
        self.assertEqual(detail["status"], "error")
        self.assertIn("graph failed", detail["error"] or "")


if __name__ == "__main__":
    unittest.main()
