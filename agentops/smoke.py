"""Cross-platform beginner smoke test (Windows / macOS / Linux)."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from agentops import __version__, connect, ingest_run, summarize_runs
from agentops.http import serve
from agentops.ingest import IngestError


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


def run_fail_demo() -> int:
    """Show intentional failures so beginners learn to read errors."""
    print(f"agent-operations {__version__}  fail-demo")
    print("These errors are EXPECTED. Learn the shape, then fix real bugs the same way.\n")

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "fail-demo.db"
        conn = connect(db)
        try:
            try:
                ingest_run(conn, {"id": "incomplete"})
                print("FAIL: incomplete ingest should raise IngestError")
                return 1
            except IngestError as exc:
                print(f"ok: Python IngestError -> {exc}")

            server = serve("127.0.0.1", 0, db)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, body = _post_json(
                    f"http://127.0.0.1:{port}/api/runs",
                    {"id": "incomplete-http"},
                )
                if (
                    status != 400
                    or "error" not in body
                    or body.get("code") != "missing_fields"
                ):
                    print(
                        "FAIL: expected HTTP 400 code=missing_fields",
                        status,
                        body,
                    )
                    return 1
                print(f"ok: HTTP {status} -> {body}")
            finally:
                server.shutdown()
                server.server_close()
        finally:
            conn.close()

    print("\nfail-demo passed — when you see similar messages for real, check README troubleshooting")
    return 0


def run_smoke() -> int:
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test agent-operations (happy path or fail-demo)"
    )
    parser.add_argument(
        "--fail-demo",
        action="store_true",
        help="Show intentional IngestError / HTTP 400 so you learn error shape",
    )
    args = parser.parse_args()
    if args.fail_demo:
        return run_fail_demo()
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
