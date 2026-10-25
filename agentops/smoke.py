"""Cross-platform beginner smoke test (Windows / macOS / Linux)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from agentops import __version__, connect, ingest_run, summarize_runs
from agentops.http import serve


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": body}
        return exc.code, parsed


def main() -> int:
    print(f"agent-operations {__version__}  python {sys.version.split()[0]}")
    print(f"platform: {sys.platform}")

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "smoke.db"
        conn = connect(db)
        try:
            ingest_run(
                conn,
                {
                    "id": "smoke-run-1",
                    "project": "demo",
                    "agent": "assistant",
                    "environment": "dev",
                    "name": "smoke",
                    "status": "ok",
                    "started_at": "2026-10-25T04:00:00+00:00",
                    "ended_at": "2026-10-25T04:00:01+00:00",
                    "latency_ms": 1000,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cost_usd": 0.001,
                },
            )
            summary = summarize_runs(conn, project="demo")
        finally:
            conn.close()

        if summary.get("count") != 1:
            print("FAIL: ingest/summary", summary)
            return 1
        print("ok: ingest + summary")

        server = serve("127.0.0.1", 0, db)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            status, created = _post_json(
                f"http://127.0.0.1:{port}/api/runs",
                {
                    "id": "smoke-http-1",
                    "project": "demo",
                    "agent": "assistant",
                    "environment": "dev",
                    "name": "http-smoke",
                    "status": "ok",
                    "started_at": "2026-10-25T04:01:00+00:00",
                    "ended_at": "2026-10-25T04:01:01+00:00",
                },
            )
            if status != 201 or created.get("id") != "smoke-http-1":
                print("FAIL: HTTP POST", status, created)
                return 1
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=5
            ) as resp:
                html = resp.read().decode("utf-8")
                if resp.status != 200 or "agent-operations" not in html:
                    print("FAIL: debug page")
                    return 1
            print(f"ok: HTTP API + debug page (port {port})")
        finally:
            server.shutdown()
            server.server_close()

    print("smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
