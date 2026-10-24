# agent-operations

Open-source Agent Operations (AgentOps / LLMOps) toolkit — trace runs, track latency / tokens / cost, and debug tool failures.

Lightweight and self-hostable. Default storage is a single SQLite file. No ClickHouse, no Kafka in v1.

## Phase 1 (this branch)

- Ingest completed runs + steps into SQLite
- List / filter runs; latency · tokens · cost summary (incl. p50/p95/p99)
- Failure grouping for tool debug
- Local HTTP API + a read-only page (`127.0.0.1` only)

## Later (upgrade path)

Running → final status updates, redaction, Postgres, pricing tables, alerts, **Kafka** (multi-host ingest), eval/quality, multi-tenant auth.

## Quick start

```powershell
$env:PYTHONPATH = "."
python -m unittest discover -s tests -v
python -m agentops.http
```

Default DB: `./data/agentops.db`

Redaction (optional): set `AGENTOPS_REDACT=off|hash|drop`, or pass `redact=` to `ingest_run`. Affects `task_input` / `task_output`, step `input` / `output` / `traceback`, and `tags.end_user_id`.

Pricing (optional): if `cost_usd` is omitted, estimate from `provider` + `model` + tokens using built-in rates (or JSON at `AGENTOPS_PRICING_PATH`). Explicit `cost_usd` always wins.

Alerts (optional):

```powershell
$env:AGENTOPS_ALERT_WEBHOOK = "https://example.com/hook"
$env:AGENTOPS_ALERT_FAILURE_RATE = "0.2"
$env:AGENTOPS_ALERT_P95_MS = "3000"
$env:AGENTOPS_ALERT_COST_USD = "10"
python -m agentops.alerts --db .\data\agentops.db
```

Exit code `2` when alerts fire. Use `--dry-run` to print without POSTing.
