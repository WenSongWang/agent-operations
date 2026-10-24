"""Live OpenAI chat example traced with TracedRun.

Requires:
  pip install openai agent-operations
  set OPENAI_API_KEY=...

Optional:
  OPENAI_BASE_URL   # e.g. a compatible gateway
  OPENAI_MODEL      # default gpt-4o-mini
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agentops import TracedRun, connect, get_run

DB = Path(__file__).resolve().parent / "openai_live.db"
PROMPT = os.environ.get("AGENTOPS_DEMO_PROMPT", "Say hi in one short sentence.")


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Missing OPENAI_API_KEY. Set it, then re-run.", file=sys.stderr)
        return 2

    try:
        from openai import OpenAI
    except ImportError:
        print('Install openai first: pip install openai', file=sys.stderr)
        return 2

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.environ.get("OPENAI_BASE_URL")
    client_kwargs: dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    if DB.exists():
        DB.unlink()

    conn = connect(DB)
    run_id = "openai-live-1"
    try:
        with TracedRun(
            conn,
            project="demo",
            agent="assistant",
            environment="dev",
            name="openai-live",
            run_id=run_id,
            provider="openai",
            model=model,
            task_input=PROMPT,
        ) as tr:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": PROMPT}],
            )
            text = (resp.choices[0].message.content or "").strip()
            tr.record_openai(resp, input_text=PROMPT, output_text=text)
            tr.finish(task_output=text)

        detail = get_run(conn, run_id)
        print("status:", detail and detail["status"])
        print("model:", detail and detail["model"])
        print("tokens:", detail and detail["input_tokens"], detail and detail["output_tokens"])
        print("cost_usd:", detail and detail["cost_usd"])
        print("output:", detail and detail["task_output"])
        print(f"db: {DB}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
