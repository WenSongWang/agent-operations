"""HTTP API and page smoke tests."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from agentops.http import make_handler, serve


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
            self.assertIn('id="apiKey"', html)
            self.assertIn("X-API-Key", html)

    def test_handler_passes_postgres_dsn_to_connect(self) -> None:
        dsn = "postgresql://user:pass@localhost:5432/agentops"
        handler_cls = make_handler(dsn, api_keys={})
        # Instantiate without a real HTTP request: call open_db via GET setup.
        # Probe by patching connect used inside the closure.
        with mock.patch("agentops.http.connect") as m_connect:
            m_connect.return_value = mock.MagicMock()
            # Build a minimal handler instance bound to a fake request.
            handler = handler_cls.__new__(handler_cls)
            # open_db is closed over in make_handler; trigger via do_GET home
            # which does not open db — use a path that does.
            class FakeServer:
                def __init__(self) -> None:
                    pass

            handler.server = FakeServer()  # type: ignore[attr-defined]
            handler.headers = {}  # type: ignore[attr-defined]
            handler.path = "/api/runs"  # type: ignore[attr-defined]
            handler.rfile = mock.Mock()  # type: ignore[attr-defined]
            handler.wfile = mock.Mock()  # type: ignore[attr-defined]
            handler.send_response = mock.Mock()  # type: ignore[attr-defined]
            handler.send_header = mock.Mock()  # type: ignore[attr-defined]
            handler.end_headers = mock.Mock()  # type: ignore[attr-defined]
            m_connect.return_value.execute = mock.Mock()
            m_connect.return_value.close = mock.Mock()
            # list_runs will be called — patch it to avoid needing real rows API
            with mock.patch("agentops.http.list_runs", return_value=[]):
                handler.do_GET()
            m_connect.assert_called_once_with(dsn)


if __name__ == "__main__":
    unittest.main()
