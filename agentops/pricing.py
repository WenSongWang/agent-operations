"""Estimate run cost_usd from provider/model token rates."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# USD per 1,000,000 tokens. Approximate public list prices for local estimates.
DEFAULT_RATES: dict[tuple[str, str], dict[str, float]] = {
    ("openai", "gpt-4o-mini"): {
        "input": 0.15,
        "output": 0.60,
        "cached": 0.075,
        "reasoning": 0.0,
    },
    ("openai", "gpt-4o"): {
        "input": 2.50,
        "output": 10.00,
        "cached": 1.25,
        "reasoning": 0.0,
    },
    ("anthropic", "claude-3-5-sonnet"): {
        "input": 3.00,
        "output": 15.00,
        "cached": 0.30,
        "reasoning": 0.0,
    },
    ("anthropic", "claude-sonnet-4"): {
        "input": 3.00,
        "output": 15.00,
        "cached": 0.30,
        "reasoning": 0.0,
    },
}


def _norm(provider: str | None, model: str | None) -> tuple[str, str]:
    return (provider or "").strip().lower(), (model or "").strip().lower()


def load_rates(path: str | Path | None = None) -> dict[tuple[str, str], dict[str, float]]:
    """Merge DEFAULT_RATES with optional JSON file (env AGENTOPS_PRICING_PATH)."""
    rates = dict(DEFAULT_RATES)
    raw_path = path if path is not None else os.environ.get("AGENTOPS_PRICING_PATH")
    if not raw_path:
        return rates
    data = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pricing file must be a JSON object")
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        if "/" in key:
            provider, model = key.split("/", 1)
        else:
            provider, model = "", key
        rates[_norm(provider, model)] = {
            "input": float(value.get("input", 0)),
            "output": float(value.get("output", 0)),
            "cached": float(value.get("cached", 0)),
            "reasoning": float(value.get("reasoning", 0)),
        }
    return rates


def lookup_rate(
    provider: str | None,
    model: str | None,
    rates: dict[tuple[str, str], dict[str, float]] | None = None,
) -> dict[str, float] | None:
    table = rates if rates is not None else load_rates()
    p, m = _norm(provider, model)
    if not m:
        return None
    return table.get((p, m)) or table.get(("", m))


def estimate_cost_usd(
    *,
    provider: str | None,
    model: str | None,
    input_tokens: int | float | None = None,
    output_tokens: int | float | None = None,
    cached_tokens: int | float | None = None,
    reasoning_tokens: int | float | None = None,
    rates: dict[tuple[str, str], dict[str, float]] | None = None,
) -> float | None:
    """Return USD estimate, or None if rate/tokens unavailable."""
    rate = lookup_rate(provider, model, rates)
    if rate is None:
        return None
    parts = (
        (input_tokens, "input"),
        (output_tokens, "output"),
        (cached_tokens, "cached"),
        (reasoning_tokens, "reasoning"),
    )
    if all(v is None for v, _ in parts):
        return None
    total = 0.0
    for tokens, kind in parts:
        if tokens is None:
            continue
        total += float(tokens) * rate.get(kind, 0.0) / 1_000_000.0
    return total


def estimate_from_payload(
    payload: dict[str, Any],
    tokens: dict[str, Any],
    rates: dict[tuple[str, str], dict[str, float]] | None = None,
) -> float | None:
    return estimate_cost_usd(
        provider=payload.get("provider"),
        model=payload.get("model"),
        input_tokens=tokens.get("input_tokens"),
        output_tokens=tokens.get("output_tokens"),
        cached_tokens=tokens.get("cached_tokens"),
        reasoning_tokens=tokens.get("reasoning_tokens"),
        rates=rates,
    )
