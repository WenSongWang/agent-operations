"""Tests for API key auth and project ACL."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from agentops.auth import AuthError, load_api_keys, scope_project_filter
from agentops.http import serve


class TestAuthUnit(unittest.TestCase):
    def test_load_and_scope(self) -> None:
        keys = load_api_keys(
            '{"k1": {"name": "demo-key", "projects": ["demo"]}}'
        )
        principal = keys["k1"]
        self.assertEqual(scope_project_filter(principal, None), "demo")
        with self.assertRaises(AuthError):
            scope_project_filter(principal, "other")

    def test_wildcard(self) -> None:
        keys = load_api_keys('{"k": {"projects": ["*"]}}')
        self.assertTrue(keys["k"].allows_project("anything"))


class TestAuthHttp(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "agentops.db"
        keys = load_api_keys(
            '{"secret": {"projects": ["demo"]}, "other": {"projects": ["x"]}}'
        )
        self.server = serve("127.0.0.1", 0, db, api_keys=keys)
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
        self,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[int, dict | list]:
        data = None
        hdrs = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path, data=data, headers=hdrs, method=method
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_missing_key_is_401(self) -> None:
        status, body = self._json("GET", "/api/runs")
        self.assertEqual(status, 401)
        self.assertIn("API key", body["error"])

    def test_ingest_allowed_project(self) -> None:
        status, created = self._json(
            "POST",
            "/api/runs",
            {
                "id": "a1",
                "project": "demo",
                "agent": "assistant",
                "environment": "dev",
                "name": "hello",
                "status": "ok",
                "started_at": "2026-10-24T10:00:00+00:00",
                "ended_at": "2026-10-24T10:00:01+00:00",
            },
            headers={"Authorization": "Bearer secret"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], "a1")

        status, rows = self._json(
            "GET", "/api/runs", headers={"X-API-Key": "secret"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(rows), 1)

    def test_ingest_wrong_project_rejected(self) -> None:
        status, body = self._json(
            "POST",
            "/api/runs",
            {
                "id": "b1",
                "project": "demo",
                "agent": "assistant",
                "environment": "dev",
                "name": "hello",
                "status": "ok",
                "started_at": "2026-10-24T10:00:00+00:00",
                "ended_at": "2026-10-24T10:00:01+00:00",
            },
            headers={"Authorization": "Bearer other"},
        )
        self.assertEqual(status, 401)
        self.assertIn("project", body["error"])

    def test_non_loopback_requires_keys(self) -> None:
        with self.assertRaises(ValueError):
            serve("0.0.0.0", 0, Path(self._tmp.name) / "x.db", api_keys={})


if __name__ == "__main__":
    unittest.main()
