"""Threshold checks and webhook notifications for run health."""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentops.db import connect
from agentops.query import summarize_runs

DEFAULT_DB = Path("data") / "agentops.db"


@dataclass(frozen=True)
class Alert:
    kind: str
    message: str
    value: float
    threshold: float


@dataclass(frozen=True)
class Thresholds:
    failure_rate: float | None = 0.2
    p95_ms: float | None = None
    cost_usd: float | None = None
    min_runs: int = 1


def thresholds_from_env() -> Thresholds:
    def _float(name: str, default: float | None) -> float | None:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        return float(raw)

    return Thresholds(
        failure_rate=_float("AGENTOPS_ALERT_FAILURE_RATE", 0.2),
        p95_ms=_float("AGENTOPS_ALERT_P95_MS", None),
        cost_usd=_float("AGENTOPS_ALERT_COST_USD", None),
        min_runs=int(os.environ.get("AGENTOPS_ALERT_MIN_RUNS", "1")),
    )


def evaluate_alerts(
    summary: dict[str, Any], thresholds: Thresholds | None = None
) -> list[Alert]:
    """Return fired alerts for a summarize_runs() result."""
    th = thresholds or thresholds_from_env()
    count = int(summary.get("count") or 0)
    if count < th.min_runs:
        return []

    alerts: list[Alert] = []
    by_status = summary.get("by_status") or {}
    failed = int(by_status.get("error", 0)) + int(by_status.get("timeout", 0))
    failure_rate = failed / count

    if th.failure_rate is not None and failure_rate >= th.failure_rate:
        alerts.append(
            Alert(
                kind="failure_rate",
                message=(
                    f"failure rate {failure_rate:.2%} "
                    f">= {th.failure_rate:.2%}"
                ),
                value=failure_rate,
                threshold=th.failure_rate,
            )
        )

    p95 = (summary.get("latency_ms") or {}).get("p95")
    if th.p95_ms is not None and p95 is not None and float(p95) >= th.p95_ms:
        alerts.append(
            Alert(
                kind="p95_ms",
                message=f"latency p95 {p95}ms >= {th.p95_ms}ms",
                value=float(p95),
                threshold=th.p95_ms,
            )
        )

    cost = (summary.get("cost_usd") or {}).get("total")
    if (
        th.cost_usd is not None
        and cost is not None
        and float(cost) >= th.cost_usd
    ):
        alerts.append(
            Alert(
                kind="cost_usd",
                message=f"cost ${cost} >= ${th.cost_usd}",
                value=float(cost),
                threshold=th.cost_usd,
            )
        )
    return alerts


def send_webhook(url: str, payload: dict[str, Any], timeout: float = 5.0) -> None:
    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def check_alerts(
    conn: sqlite3.Connection,
    *,
    thresholds: Thresholds | None = None,
    webhook: str | None = None,
    notify: bool = True,
    project: str | None = None,
    agent: str | None = None,
    environment: str | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
) -> list[Alert]:
    """Evaluate summary filters; optionally POST alerts to webhook."""
    summary = summarize_runs(
        conn,
        project=project,
        agent=agent,
        environment=environment,
        started_after=started_after,
        started_before=started_before,
    )
    alerts = evaluate_alerts(summary, thresholds)
    url = webhook if webhook is not None else os.environ.get("AGENTOPS_ALERT_WEBHOOK")
    if notify and alerts and url:
        send_webhook(
            url,
            {
                "source": "agent-operations",
                "alerts": [asdict(a) for a in alerts],
                "summary": summary,
                "filters": {
                    "project": project,
                    "agent": agent,
                    "environment": environment,
                    "started_after": started_after,
                    "started_before": started_before,
                },
            },
        )
    return alerts


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Check agentops alert thresholds")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--webhook", default=None)
    parser.add_argument("--project", default=None)
    parser.add_argument("--agent", default=None)
    parser.add_argument("--environment", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = connect(args.db)
    try:
        alerts = check_alerts(
            conn,
            webhook=args.webhook,
            notify=not args.dry_run,
            project=args.project,
            agent=args.agent,
            environment=args.environment,
        )
    finally:
        conn.close()

    if not alerts:
        print("ok: no alerts")
        return
    for alert in alerts:
        print(f"ALERT {alert.kind}: {alert.message}")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
