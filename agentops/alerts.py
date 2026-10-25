"""Threshold checks and webhook / email notifications for run health."""

from __future__ import annotations

import json
import os
import smtplib
import sqlite3
import ssl
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

from agentops.db import connect
from agentops.query import summarize_runs

DEFAULT_DB = Path("data") / "agentops.db"

# Tests may replace: (host, port, user, password, use_tls, msg) -> None
EmailSender = Callable[[str, int, str | None, str | None, bool, EmailMessage], None]
_email_sender: EmailSender | None = None


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


def set_email_sender(sender: EmailSender | None) -> None:
    """Override SMTP send for tests. Pass None to restore the default client."""
    global _email_sender
    _email_sender = sender


def _default_email_send(
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    use_tls: bool,
    msg: EmailMessage,
) -> None:
    if use_tls:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if user:
                smtp.login(user, password or "")
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if user:
                smtp.login(user, password or "")
            smtp.send_message(msg)


def alert_email_recipients(raw: str | None = None) -> list[str]:
    text = raw if raw is not None else os.environ.get("AGENTOPS_ALERT_EMAIL", "")
    return [p.strip() for p in text.split(",") if p.strip()]


def send_alert_email(
    alerts: list[Alert],
    summary: dict[str, Any],
    *,
    to: str | None = None,
) -> bool:
    """Send a plain-text alert mail. No-op unless recipients + SMTP host are set."""
    recipients = alert_email_recipients(to)
    host = os.environ.get("AGENTOPS_SMTP_HOST", "").strip()
    if not recipients or not host:
        return False
    port = int(os.environ.get("AGENTOPS_SMTP_PORT", "587"))
    user = os.environ.get("AGENTOPS_SMTP_USER") or None
    password = os.environ.get("AGENTOPS_SMTP_PASSWORD") or None
    from_addr = (
        os.environ.get("AGENTOPS_SMTP_FROM", "").strip()
        or user
        or "agentops@localhost"
    )
    use_tls = os.environ.get("AGENTOPS_SMTP_TLS", "1").strip() not in (
        "0",
        "false",
        "False",
        "no",
    )
    lines = [f"- {a.kind}: {a.message}" for a in alerts]
    body = (
        "agent-operations alerts\n\n"
        + "\n".join(lines)
        + f"\n\nruns={summary.get('count')}\n"
    )
    msg = EmailMessage()
    msg["Subject"] = f"[agentops] {len(alerts)} alert(s)"
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    sender = _email_sender or _default_email_send
    sender(host, port, user, password, use_tls, msg)
    return True


def check_alerts(
    conn: sqlite3.Connection,
    *,
    thresholds: Thresholds | None = None,
    webhook: str | None = None,
    email: str | None = None,
    notify: bool = True,
    project: str | None = None,
    agent: str | None = None,
    environment: str | None = None,
    started_after: str | None = None,
    started_before: str | None = None,
) -> list[Alert]:
    """Evaluate summary filters; optionally webhook and/or email alerts."""
    summary = summarize_runs(
        conn,
        project=project,
        agent=agent,
        environment=environment,
        started_after=started_after,
        started_before=started_before,
    )
    alerts = evaluate_alerts(summary, thresholds)
    if notify and alerts:
        payload = {
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
        }
        url = (
            webhook
            if webhook is not None
            else os.environ.get("AGENTOPS_ALERT_WEBHOOK")
        )
        if url:
            send_webhook(url, payload)
        send_alert_email(alerts, summary, to=email)
    return alerts


def main() -> None:
    import argparse

    from agentops.cliutil import cli_exit

    parser = argparse.ArgumentParser(description="Check agentops alert thresholds")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--webhook", default=None)
    parser.add_argument("--project", default=None)
    parser.add_argument("--agent", default=None)
    parser.add_argument("--environment", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        conn = connect(args.db)
    except ImportError as exc:
        cli_exit(
            str(exc),
            'for Postgres: pip install "agent-operations[postgres]"',
        )
    except OSError as exc:
        cli_exit(
            f"cannot open db ({exc})",
            "check --db path is writable, or set a valid AGENTOPS_DATABASE_URL",
        )
    try:
        try:
            alerts = check_alerts(
                conn,
                webhook=args.webhook,
                notify=not args.dry_run,
                project=args.project,
                agent=args.agent,
                environment=args.environment,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            cli_exit(
                f"webhook notify failed ({exc})",
                "check AGENTOPS_ALERT_WEBHOOK / --webhook URL, or use --dry-run",
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
