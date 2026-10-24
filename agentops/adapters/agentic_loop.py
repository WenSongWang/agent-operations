"""Adapter: agentic-loop RunJournal → agent-operations ingest."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_from_terminal(terminal: dict[str, Any]) -> str:
    kind = str(terminal.get("kind") or "").lower()
    if kind in {"completed"}:
        return "ok"
    if kind in {"aborted"}:
        return "cancelled"
    return "error"


class AgentOpsJournal:
    """Duck-typed journal for ``agentic_loop.loop.run_loop(..., journal=...)``.

    Also mirrors events to the built-in JSONL journal when ``runs_dir`` is set.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        project: str = "default",
        agent: str = "agentic-loop",
        environment: str = "dev",
        name: str | None = None,
        run_id: str | None = None,
        runs_dir: str | Path | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        from agentops.ingest import ingest_run

        self._ingest = ingest_run
        self.conn = conn
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.project = project
        self.agent = agent
        self.environment = environment
        self.name = name or "agentic-loop-run"
        self.provider = provider
        self.model = model
        self.started_at = _now()
        self.steps: list[dict[str, Any]] = []
        self._task_input: str | None = None
        self._finished = False
        self._inner = None
        if runs_dir is not None:
            from agentic_loop.observability.journal import RunJournal

            self._inner = RunJournal(Path(runs_dir), run_id=self.run_id)

    def started(self, *, prompt: str, config: dict[str, Any]) -> None:
        self._task_input = prompt
        if self.provider is None and isinstance(config, dict):
            self.provider = config.get("provider") or config.get("llm_provider")
        if self.model is None and isinstance(config, dict):
            self.model = config.get("model")
        payload: dict[str, Any] = {
            "id": self.run_id,
            "project": self.project,
            "agent": self.agent,
            "environment": self.environment,
            "name": self.name,
            "status": "running",
            "started_at": self.started_at,
            "task_input": prompt,
        }
        if self.provider:
            payload["provider"] = self.provider
        if self.model:
            payload["model"] = self.model
        self._ingest(self.conn, payload)
        if self._inner is not None:
            self._inner.started(prompt=prompt, config=config)

    def turn(self, *, turn: int, tool_names: list[str]) -> None:
        if self._inner is not None:
            self._inner.turn(turn=turn, tool_names=tool_names)

    def tool_result(
        self, *, turn: int, name: str, duration_ms: float, preview: str
    ) -> None:
        ended = _now()
        self.steps.append(
            {
                "seq": len(self.steps) + 1,
                "kind": "tool",
                "name": name,
                "status": "ok",
                "latency_ms": duration_ms,
                "ended_at": ended,
                "output": preview,
                "extra": {"turn": turn},
            }
        )
        if self._inner is not None:
            self._inner.tool_result(
                turn=turn, name=name, duration_ms=duration_ms, preview=preview
            )

    def finished(self, *, terminal: dict[str, Any], duration_ms: float) -> None:
        if self._finished:
            return
        status = _status_from_terminal(terminal)
        payload: dict[str, Any] = {
            "id": self.run_id,
            "project": self.project,
            "agent": self.agent,
            "environment": self.environment,
            "name": self.name,
            "status": status,
            "started_at": self.started_at,
            "ended_at": _now(),
            "latency_ms": duration_ms,
            "task_input": self._task_input,
            "task_output": terminal.get("content"),
            "error": terminal.get("error"),
            "steps": list(self.steps),
            "extra": {"terminal": terminal, "turns": terminal.get("turns")},
        }
        if self.provider:
            payload["provider"] = self.provider
        if self.model:
            payload["model"] = self.model
        self._ingest(self.conn, payload)
        self._finished = True
        if self._inner is not None:
            self._inner.finished(terminal=terminal, duration_ms=duration_ms)
