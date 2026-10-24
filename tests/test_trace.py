"""Tests for TracedRun helper."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agentops.db import connect
from agentops.query import get_run
from agentops.trace import TracedRun, usage_from_openai


class TestTrace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "agentops.db")

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_context_success_and_openai_usage(self) -> None:
        response = SimpleNamespace(
            model="gpt-4o-mini",
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=4,
                prompt_tokens_details=None,
                completion_tokens_details=None,
            ),
        )
        with TracedRun(
            self.conn,
            project="demo",
            agent="assistant",
            environment="dev",
            name="wrap",
            run_id="tr-1",
            task_input="hi",
        ) as tr:
            running = get_run(self.conn, "tr-1")
            assert running is not None
            self.assertEqual(running["status"], "running")
            tr.record_openai(response, output_text="hello")
            tr.finish(status="ok", task_output="hello")

        detail = get_run(self.conn, "tr-1")
        assert detail is not None
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["input_tokens"], 10)
        self.assertEqual(detail["output_tokens"], 4)
        self.assertEqual(detail["provider"], "openai")
        self.assertEqual(detail["model"], "gpt-4o-mini")
        self.assertEqual(len(detail["steps"]), 1)

    def test_context_captures_error(self) -> None:
        with self.assertRaises(RuntimeError):
            with TracedRun(
                self.conn,
                project="demo",
                agent="assistant",
                environment="dev",
                name="boom",
                run_id="tr-2",
            ):
                raise RuntimeError("nope")
        detail = get_run(self.conn, "tr-2")
        assert detail is not None
        self.assertEqual(detail["status"], "error")
        self.assertIn("nope", detail["error"] or "")

    def test_usage_from_dict(self) -> None:
        usage = usage_from_openai(
            {"model": "gpt-4o", "usage": {"prompt_tokens": 1, "completion_tokens": 2}}
        )
        self.assertEqual(usage["model"], "gpt-4o")
        self.assertEqual(usage["input_tokens"], 1)
        self.assertEqual(usage["output_tokens"], 2)


if __name__ == "__main__":
    unittest.main()
