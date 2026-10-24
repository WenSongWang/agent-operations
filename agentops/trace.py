"""Context manager that records running → final agent runs."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from types import TracebackType
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def usage_from_openai(response: Any) -> dict[str, Any]:
    """Extract provider/model/tokens from an OpenAI SDK response-like object."""
    out: dict[str, Any] = {"provider": "openai"}
    model = getattr(response, "model", None)
    if model:
        out["model"] = model
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
        model = response.get("model", model)
        if model:
            out["model"] = model
    if usage is None:
        return out
    if isinstance(usage, dict):
        inp = usage.get("input_tokens", usage.get("prompt_tokens"))
        outp = usage.get("output_tokens", usage.get("completion_tokens"))
        cached = usage.get("cached_tokens")
        reasoning = usage.get("reasoning_tokens")
    else:
        inp = getattr(usage, "input_tokens", None)
        if inp is None:
            inp = getattr(usage, "prompt_tokens", None)
        outp = getattr(usage, "output_tokens", None)
        if outp is None:
            outp = getattr(usage, "completion_tokens", None)
        cached = getattr(usage, "cached_tokens", None)
        reasoning = getattr(usage, "reasoning_tokens", None)
        details = getattr(usage, "prompt_tokens_details", None)
        if cached is None and details is not None:
            cached = getattr(details, "cached_tokens", None)
        out_details = getattr(usage, "completion_tokens_details", None)
        if reasoning is None and out_details is not None:
            reasoning = getattr(out_details, "reasoning_tokens", None)
    if inp is not None:
        out["input_tokens"] = int(inp)
    if outp is not None:
        out["output_tokens"] = int(outp)
    if cached is not None:
        out["cached_tokens"] = int(cached)
    if reasoning is not None:
        out["reasoning_tokens"] = int(reasoning)
    return out


class TracedRun:
    """Start a running run on enter; finalize on exit or explicit finish()."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        project: str,
        agent: str,
        environment: str,
        name: str,
        run_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        task_input: Any = None,
        **extra_fields: Any,
    ) -> None:
        from agentops.ingest import ingest_run

        self._ingest = ingest_run
        self.conn = conn
        self.run_id = run_id or str(uuid.uuid4())
        self.started_at = _now()
        self.steps: list[dict[str, Any]] = []
        self.fields: dict[str, Any] = {
            "id": self.run_id,
            "project": project,
            "agent": agent,
            "environment": environment,
            "name": name,
            "started_at": self.started_at,
            **extra_fields,
        }
        if provider is not None:
            self.fields["provider"] = provider
        if model is not None:
            self.fields["model"] = model
        if task_input is not None:
            self.fields["task_input"] = task_input
        self._finished = False

    def __enter__(self) -> TracedRun:
        self._ingest(
            self.conn,
            {
                **self.fields,
                "status": "running",
                "ended_at": None,
            },
        )
        return self

    def add_step(self, **step: Any) -> None:
        if "seq" not in step:
            step["seq"] = len(self.steps) + 1
        self.steps.append(step)

    def record_openai(
        self,
        response: Any,
        *,
        name: str | None = None,
        input_text: Any = None,
        output_text: Any = None,
    ) -> None:
        """Attach one llm step from an OpenAI chat/completions response."""
        usage = usage_from_openai(response)
        model = usage.get("model") or self.fields.get("model") or "openai"
        if usage.get("provider"):
            self.fields.setdefault("provider", usage["provider"])
        if usage.get("model"):
            self.fields.setdefault("model", usage["model"])
        for key in (
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "reasoning_tokens",
        ):
            if key in usage:
                self.fields[key] = self.fields.get(key, 0) + usage[key]
        ended = _now()
        step: dict[str, Any] = {
            "seq": len(self.steps) + 1,
            "kind": "llm",
            "name": name or str(model),
            "status": "ok",
            "started_at": self.started_at if not self.steps else ended,
            "ended_at": ended,
            **{k: usage[k] for k in usage if k.endswith("_tokens")},
        }
        if input_text is not None:
            step["input"] = input_text
        if output_text is not None:
            step["output"] = output_text
        self.steps.append(step)

    def finish(
        self,
        *,
        status: str = "ok",
        error: str | None = None,
        task_output: Any = None,
        **fields: Any,
    ) -> str:
        if self._finished:
            return self.run_id
        payload = {
            **self.fields,
            **fields,
            "status": status,
            "ended_at": _now(),
            "steps": list(self.steps),
        }
        if error is not None:
            payload["error"] = error
        if task_output is not None:
            payload["task_output"] = task_output
        self._ingest(self.conn, payload)
        self._finished = True
        return self.run_id

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._finished:
            return None
        if exc is None:
            self.finish(status="ok")
        else:
            self.finish(
                status="error",
                error=f"{exc_type.__name__ if exc_type else 'Error'}: {exc}",
            )
        return None
