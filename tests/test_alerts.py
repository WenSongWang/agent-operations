"""Tests for alert evaluation and webhook notify."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agentops.alerts import Thresholds, check_alerts, evaluate_alerts
from agentops.db import connect
from agentops.ingest import ingest_run


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
        "cost_usd": 0.01,
    }
    payload.update(overrides)
    return payload


class TestAlerts(unittest.TestCase):
    def test_evaluate_failure_rate_and_p95(self) -> None:
        summary = {
            "count": 5,
            "by_status": {"ok": 2, "error": 3},
            "latency_ms": {"p95": 2500},
            "cost_usd": {"total": 1.5},
        }
        alerts = evaluate_alerts(
            summary,
            Thresholds(failure_rate=0.5, p95_ms=2000, cost_usd=1.0),
        )
        kinds = {a.kind for a in alerts}
        self.assertEqual(kinds, {"failure_rate", "p95_ms", "cost_usd"})

    def test_min_runs_skips(self) -> None:
        alerts = evaluate_alerts(
            {"count": 1, "by_status": {"error": 1}, "latency_ms": {}, "cost_usd": {}},
            Thresholds(failure_rate=0.1, min_runs=5),
        )
        self.assertEqual(alerts, [])

    def test_check_alerts_posts_webhook(self) -> None:
        received: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                received.append(json.loads(body.decode("utf-8")))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, fmt: str, *args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agentops.db")
            try:
                ingest_run(conn, _run("ok-1", latency_ms=100))
                ingest_run(
                    conn, _run("err-1", status="error", latency_ms=5000, cost_usd=2.0)
                )
                alerts = check_alerts(
                    conn,
                    thresholds=Thresholds(
                        failure_rate=0.4, p95_ms=1000, cost_usd=1.0
                    ),
                    webhook=f"http://127.0.0.1:{port}/hook",
                )
                self.assertTrue(alerts)
                self.assertEqual(len(received), 1)
                self.assertEqual(received[0]["source"], "agent-operations")
                self.assertTrue(received[0]["alerts"])
            finally:
                conn.close()
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
