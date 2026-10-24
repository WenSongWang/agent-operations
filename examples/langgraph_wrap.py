"""Trace a LangGraph-style invoke without needing a real LLM.

Requires only agent-operations. For a real graph:

    from langgraph.graph import StateGraph
    from agentops import connect
    from agentops.adapters.langgraph import traced_invoke

    conn = connect("./data/agentops.db")
    result = traced_invoke(
        app,
        {"messages": [...]},
        conn=conn,
        project="demo",
        agent="support-bot",
        environment="dev",
        name="support",
        config={"configurable": {"thread_id": "1"}},
    )
"""

from __future__ import annotations

from pathlib import Path

from agentops import connect, get_run
from agentops.adapters.langgraph import traced_invoke

DB = Path(__file__).resolve().parent / "langgraph_wrap.db"


class _EchoGraph:
    def invoke(self, inputs, config=None):
        return {"ok": True, "inputs": inputs, "thread": (config or {}).get("configurable")}


def main() -> None:
    if DB.exists():
        DB.unlink()
    conn = connect(DB)
    try:
        result = traced_invoke(
            _EchoGraph(),
            {"question": "ping"},
            conn=conn,
            project="demo",
            agent="echo",
            environment="dev",
            name="echo-graph",
            run_id="lg-demo-1",
            config={"configurable": {"thread_id": "demo"}},
        )
        detail = get_run(conn, "lg-demo-1")
        print("result:", result)
        print("status:", detail and detail["status"])
        print("steps:", detail and [s["kind"] for s in detail["steps"]])
    finally:
        conn.close()
        print(f"db: {DB}")


if __name__ == "__main__":
    main()
