"""Derive run-level latency and metric fill from steps."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agentops.pricing import estimate_from_payload


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _merge_ms(intervals: list[tuple[datetime, datetime]]) -> float:
    if not intervals:
        return 0.0
    ordered = sorted(intervals, key=lambda x: x[0])
    total = 0.0
    cur_s, cur_e = ordered[0]
    for start, end in ordered[1:]:
        if start <= cur_e:
            if end > cur_e:
                cur_e = end
        else:
            total += (cur_e - cur_s).total_seconds() * 1000.0
            cur_s, cur_e = start, end
    total += (cur_e - cur_s).total_seconds() * 1000.0
    return total


def _intervals_for(
    steps: list[dict[str, Any]], kind: str
) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for step in steps:
        if step.get("kind") != kind:
            continue
        started = step.get("started_at")
        ended = step.get("ended_at")
        if not started or not ended:
            continue
        out.append((_parse_dt(started), _parse_dt(ended)))
    return out


def compute_run_metrics(
    payload: dict[str, Any], steps: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return derived run fields to merge into the insert row."""
    started = _parse_dt(payload["started_at"])
    ended_raw = payload.get("ended_at")
    latency = payload.get("latency_ms")
    if latency is None and ended_raw:
        ended = _parse_dt(ended_raw)
        latency = (ended - started).total_seconds() * 1000.0

    model_ms = _merge_ms(_intervals_for(steps, "llm"))
    tool_ms = _merge_ms(_intervals_for(steps, "tool"))
    human_ms = _merge_ms(_intervals_for(steps, "human"))
    busy = _merge_ms(
        _intervals_for(steps, "llm")
        + _intervals_for(steps, "tool")
        + _intervals_for(steps, "human")
    )
    wait_ms = (
        max(0.0, float(latency) - busy) if latency is not None else None
    )

    ttft = payload.get("ttft_ms")
    if ttft is None:
        for step in sorted(steps, key=lambda s: s.get("seq", 0)):
            if step.get("kind") == "llm" and step.get("ttft_ms") is not None:
                ttft = step["ttft_ms"]
                break

    def _pick(key: str, computed: float | None) -> Any:
        if key in payload and payload[key] is not None:
            return payload[key]
        return computed if steps else None

    out: dict[str, Any] = {
        "latency_ms": latency,
        "model_ms": _pick("model_ms", model_ms),
        "tool_ms": _pick("tool_ms", tool_ms),
        "human_ms": _pick("human_ms", human_ms),
        "wait_ms": _pick("wait_ms", wait_ms),
        "ttft_ms": ttft,
    }

    metric_keys = (
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
        "cost_usd",
    )
    for key in metric_keys:
        if payload.get(key) is not None:
            out[key] = payload[key]
            continue
        total = 0.0 if key == "cost_usd" else 0
        saw = False
        for step in steps:
            val = step.get(key)
            if val is None:
                continue
            saw = True
            total = total + val
        if saw:
            out[key] = total

    # Caller cost wins; else step sum; else price-table estimate.
    if out.get("cost_usd") is None:
        estimated = estimate_from_payload(payload, out)
        if estimated is not None:
            out["cost_usd"] = estimated
    return out
