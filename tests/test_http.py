"""HTTP API and page smoke tests."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agentops.http import serve


class TestHttp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "agentops.db"
        self.server = serve("127.0.0.1", 0, db)
        self.port = self.server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self._thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def _json(
        self, method: str, path: str, body: dict | None = None
    ) -> tuple[int, dict | list]:
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_post_and_get_runs(self) -> None:
        status, created = self._json(
            "POST",
            "/api/runs",
            {
                "id": "http-1",
                "project": "demo",
                "agent": "assistant",
                "environment": "dev",
                "name": "hello",
                "status": "ok",
                "started_at": "2026-10-24T10:00:00+00:00",
                "ended_at": "2026-10-24T10:00:01+00:00",
                "latency_ms": 1000,
                "input_tokens": 3,
                "cost_usd": 0.01,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], "http-1")

        status, rows = self._json("GET", "/api/runs?project=demo")
        self.assertEqual(status, 200)
        self.assertEqual(len(rows), 1)

        status, summary = self._json("GET", "/api/runs/summary")
        self.assertEqual(status, 200)
        self.assertEqual(summary["count"], 1)

        status, detail = self._json("GET", "/api/runs/http-1")
        self.assertEqual(status, 200)
        self.assertEqual(detail["id"], "http-1")

    def test_invalid_ingest_is_400(self) -> None:
        status, body = self._json("POST", "/api/runs", {"id": "x"})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_home_page(self) -> None:
        with urllib.request.urlopen(self.base + "/") as resp:
            html = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertIn("agent-operations", html)
            self.assertIn("/api/runs/summary", html)


if __name__ == "__main__":
    unittest.main()
