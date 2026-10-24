"""Read-side queries: list, summary, percentiles, failures, detail."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any


def _filters_sql(
    project: str | None = None,
    agent: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if project is not None:
        clauses.append("project = ?")
        args.append(project)
    if agent is not None:
        clauses.append("agent = ?")
        args.append(agent)
    if environment is not None:
        clauses.append("environment = ?")
        args.append(environment)
    if status is not None:
        clauses.append("status = ?")
        args.append(status)
    if started_after is not None:
        clauses.append("started_at >= ?")
        args.append(started_after)
    if started_before is not None:
        clauses.append("started_at <= ?")
        args.append(started_before)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, args


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if data.get("tags"):
        try:
            data["tags"] = json.loads(data["tags"])
        except json.JSONDecodeError:
            pass
    if data.get("extra"):
        try:
            data["extra"] = json.loads(data["extra"])
        except json.JSONDecodeError:
            pass
    return data


def list_runs(
    conn: sqlite3.Connection,
    *,
    project: str | None = None,
    agent: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where, args = _filters_sql(
        project, agent, environment, status, started_after, started_before
    )
    sql = (
        "SELECT * FROM runs"
        f"{where} ORDER BY started_at DESC LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, [*args, limit, offset]).fetchall()
    return [_row_to_dict(r) for r in rows]


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (len(sorted_vals) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_vals[low]
    weight = rank - low
    return sorted_vals[low] * (1 - weight) + sorted_vals[high] * weight


def summarize_runs(
    conn: sqlite3.Connection,
    *,
    project: str | None = None,
    agent: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
) -> dict[str, Any]:
    where, args = _filters_sql(
        project, agent, environment, status, started_after, started_before
    )
    rows = conn.execute(f"SELECT * FROM runs{where}", args).fetchall()
    total = len(rows)
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    ok = by_status.get("ok", 0)
    success_rate = (ok / total) if total else None

    def _sum(col: str) -> float:
        return float(sum(r[col] for r in rows if r[col] is not None))

    def _missing(col: str) -> int:
        return sum(1 for r in rows if r[col] is None)

    latency = sorted(
        float(r["latency_ms"]) for r in rows if r["latency_ms"] is not None
    )
    ttft = sorted(
        float(r["ttft_ms"]) for r in rows if r["ttft_ms"] is not None
    )

    model_ms = _sum("model_ms")
    tool_ms = _sum("tool_ms")
    human_ms = _sum("human_ms")

    return {
        "count": total,
        "by_status": by_status,
        "success_rate": success_rate,
        "tokens": {
            "input": _sum("input_tokens"),
            "output": _sum("output_tokens"),
            "cached": _sum("cached_tokens"),
            "reasoning": _sum("reasoning_tokens"),
            "unreported": {
                "input": _missing("input_tokens"),
                "output": _missing("output_tokens"),
                "cached": _missing("cached_tokens"),
                "reasoning": _missing("reasoning_tokens"),
            },
        },
        "cost_usd": {
            "total": _sum("cost_usd"),
            "unreported": _missing("cost_usd"),
        },
        "latency_ms": {
            "p50": _percentile(latency, 0.50),
            "p95": _percentile(latency, 0.95),
            "p99": _percentile(latency, 0.99),
            "max": latency[-1] if latency else None,
        },
        "ttft_ms": {
            "p50": _percentile(ttft, 0.50),
            "p95": _percentile(ttft, 0.95),
            "p99": _percentile(ttft, 0.99),
            "max": ttft[-1] if ttft else None,
        },
        "model_ms_total": model_ms,
        "tool_ms_total": tool_ms,
        "human_ms_total": human_ms,
    }


def list_tool_failures(
    conn: sqlite3.Connection,
    *,
    project: str | None = None,
    agent: str | None = None,
    environment: str | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["s.kind = 'tool'", "s.status = 'error'"]
    args: list[Any] = []
    if project is not None:
        clauses.append("r.project = ?")
        args.append(project)
    if agent is not None:
        clauses.append("r.agent = ?")
        args.append(agent)
    if environment is not None:
        clauses.append("r.environment = ?")
        args.append(environment)
    if started_after is not None:
        clauses.append("r.started_at >= ?")
        args.append(started_after)
    if started_before is not None:
        clauses.append("r.started_at <= ?")
        args.append(started_before)
    where = " AND ".join(clauses)
    sql = f"""
        SELECT r.project, r.agent, r.environment, s.name AS tool_name,
               COALESCE(s.error_type, '') AS error_type, COUNT(*) AS count
        FROM steps s
        JOIN runs r ON r.id = s.run_id
        WHERE {where}
        GROUP BY r.project, r.agent, r.environment, s.name, s.error_type
        ORDER BY count DESC
        LIMIT ?
    """
    rows = conn.execute(sql, [*args, limit]).fetchall()
    return [dict(r) for r in rows]


def get_run(
    conn: sqlite3.Connection, run_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return None
    data = _row_to_dict(row)
    steps = conn.execute(
        "SELECT * FROM steps WHERE run_id = ? ORDER BY seq ASC", (run_id,)
    ).fetchall()
    data["steps"] = []
    for step in steps:
        item = dict(step)
        if item.get("extra"):
            try:
                item["extra"] = json.loads(item["extra"])
            except json.JSONDecodeError:
                pass
        data["steps"].append(item)
    return data
