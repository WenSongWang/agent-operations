"""Trace an OpenAI-style call with TracedRun (works without the openai package).

Real usage with the official SDK:

    from openai import OpenAI
    from agentops import connect, TracedRun

    conn = connect("./data/agentops.db")
    client = OpenAI()
    with TracedRun(
        conn,
        project="demo",
        agent="assistant",
        environment="dev",
        name="chat",
        task_input="Say hi",
    ) as tr:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say hi"}],
        )
        text = resp.choices[0].message.content
        tr.record_openai(resp, output_text=text)
        tr.finish(task_output=text)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agentops import TracedRun, connect, get_run

DB = Path(__file__).resolve().parent / "openai_wrap.db"


def main() -> None:
    if DB.exists():
        DB.unlink()

    # Fake OpenAI response shape — replace with a real client call in production.
    fake_response = SimpleNamespace(
        model="gpt-4o-mini",
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=5,
            prompt_tokens_details=None,
            completion_tokens_details=None,
        ),
    )

    conn = connect(DB)
    try:
        with TracedRun(
            conn,
            project="demo",
            agent="assistant",
            environment="dev",
            name="say-hi",
            run_id="openai-wrap-1",
            task_input="Say hi",
        ) as tr:
            # ... call OpenAI here ...
            text = "Hi there!"
            tr.record_openai(fake_response, output_text=text)
            tr.finish(task_output=text)

        detail = get_run(conn, "openai-wrap-1")
        print("status:", detail and detail["status"])
        print("tokens:", detail and detail["input_tokens"], detail and detail["output_tokens"])
        print("cost_usd:", detail and detail["cost_usd"])
        print("steps:", detail and len(detail["steps"]))
    finally:
        conn.close()
        print(f"db: {DB}")


if __name__ == "__main__":
    main()
