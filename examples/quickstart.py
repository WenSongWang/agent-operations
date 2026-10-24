"""Minimal example: ingest one run, then print list + summary."""

from __future__ import annotations

from pathlib import Path

from agentops import connect, ingest_run, list_runs, summarize_runs

DB = Path(__file__).resolve().parent / "quickstart.db"


def main() -> None:
    if DB.exists():
        DB.unlink()

    conn = connect(DB)
    try:
        ingest_run(
            conn,
            {
                "id": "demo-run-1",
                "project": "demo",
                "agent": "assistant",
                "environment": "dev",
                "name": "say-hello",
                "status": "ok",
                "started_at": "2026-10-24T10:00:00+00:00",
                "ended_at": "2026-10-24T10:00:01+00:00",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "input_tokens": 120,
                "output_tokens": 40,
                "task_input": "Say hello",
                "task_output": "Hello!",
                "steps": [
                    {
                        "seq": 1,
                        "kind": "llm",
                        "name": "gpt-4o-mini",
                        "status": "ok",
                        "started_at": "2026-10-24T10:00:00+00:00",
                        "ended_at": "2026-10-24T10:00:01+00:00",
                        "ttft_ms": 80,
                        "input_tokens": 120,
                        "output_tokens": 40,
                    }
                ],
            },
        )
        print("runs:", list_runs(conn))
        print("summary:", summarize_runs(conn, project="demo"))
    finally:
        conn.close()
        print(f"db: {DB}")


if __name__ == "__main__":
    main()
