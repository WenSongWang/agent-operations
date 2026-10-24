"""Adapter helpers for LangGraph / LangChain-style graphs."""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from agentops.trace import TracedRun


def _stringify(value: Any, *, limit: int = 4000) -> str:
    text = value if isinstance(value, str) else repr(value)
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def traced_invoke(
    graph: Any,
    inputs: Any,
    *,
    conn: sqlite3.Connection,
    project: str,
    agent: str,
    environment: str = "dev",
    name: str = "langgraph-run",
    run_id: str | None = None,
    config: dict[str, Any] | None = None,
    invoke: Callable[..., Any] | None = None,
    **traced_fields: Any,
) -> Any:
    """Run ``graph.invoke`` (or custom ``invoke``) inside a TracedRun.

    Works with any object that has ``.invoke(inputs, config=...)``.
    """
    call = invoke or graph.invoke
    with TracedRun(
        conn,
        project=project,
        agent=agent,
        environment=environment,
        name=name,
        run_id=run_id,
        task_input=inputs,
        **traced_fields,
    ) as tr:
        try:
            if config is None:
                result = call(inputs)
            else:
                result = call(inputs, config=config)
        except TypeError:
            # Some callables take config only as kwargs / positional variants.
            result = call(inputs, config) if config is not None else call(inputs)
        tr.add_step(
            kind="agent",
            name=name,
            status="ok",
            output=_stringify(result),
        )
        tr.finish(status="ok", task_output=result)
        return result


def traced_ainvoke(
    graph: Any,
    inputs: Any,
    *,
    conn: sqlite3.Connection,
    project: str,
    agent: str,
    environment: str = "dev",
    name: str = "langgraph-run",
    run_id: str | None = None,
    config: dict[str, Any] | None = None,
    **traced_fields: Any,
):
    """Async variant of ``traced_invoke`` for ``graph.ainvoke``."""

    async def _run() -> Any:
        with TracedRun(
            conn,
            project=project,
            agent=agent,
            environment=environment,
            name=name,
            run_id=run_id,
            task_input=inputs,
            **traced_fields,
        ) as tr:
            if config is None:
                result = await graph.ainvoke(inputs)
            else:
                try:
                    result = await graph.ainvoke(inputs, config=config)
                except TypeError:
                    result = await graph.ainvoke(inputs, config)
            tr.add_step(
                kind="agent",
                name=name,
                status="ok",
                output=_stringify(result),
            )
            tr.finish(status="ok", task_output=result)
            return result

    return _run()
