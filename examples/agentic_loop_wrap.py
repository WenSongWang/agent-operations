"""Wire agent-operations into agentic-loop via AgentOpsJournal.

Requires: pip install agentic-loop agent-operations

Real usage:

    from agentic_loop.loop import run_loop
    from agentops import connect
    from agentops.adapters import AgentOpsJournal

    conn = connect("./data/agentops.db")
    journal = AgentOpsJournal(
        conn,
        project="demo",
        agent="assistant",
        environment="dev",
        runs_dir="./.agentic-loop/runs",  # also keep JSONL
    )
    terminal = run_loop(messages, tools=tools, llm=llm, journal=journal)
"""

from __future__ import annotations

from pathlib import Path

from agentops import connect, get_run
from agentops.adapters import AgentOpsJournal

DB = Path(__file__).resolve().parent / "agentic_loop_wrap.db"


def main() -> None:
    if DB.exists():
        DB.unlink()

    conn = connect(DB)
    try:
        journal = AgentOpsJournal(
            conn,
            project="demo",
            agent="assistant",
            environment="dev",
            run_id="agentic-demo-1",
            name="demo-loop",
        )
        # Simulate what agentic_loop.loop.run_loop calls on the journal:
        journal.started(
            prompt="Summarize README",
            config={"model": "gpt-4o-mini", "max_turns": 3},
        )
        journal.turn(turn=1, tool_names=["read_file"])
        journal.tool_result(
            turn=1,
            name="read_file",
            duration_ms=8.0,
            preview="# agent-operations",
        )
        journal.finished(
            terminal={
                "kind": "completed",
                "content": "Lightweight AgentOps toolkit.",
                "turns": 1,
            },
            duration_ms=42.0,
        )

        detail = get_run(conn, "agentic-demo-1")
        print("status:", detail and detail["status"])
        print("latency_ms:", detail and detail["latency_ms"])
        print("steps:", detail and [s["name"] for s in detail["steps"]])
        print("output:", detail and detail["task_output"])
    finally:
        conn.close()
        print(f"db: {DB}")


if __name__ == "__main__":
    main()
