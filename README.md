# agent-operations

Open-source Agent Operations (AgentOps / LLMOps) toolkit — trace runs, track latency / tokens / cost, and debug tool failures.

Lightweight and self-hostable. Default storage is a single SQLite file. No ClickHouse. Kafka broker is optional later; an event outbox is available now.

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

Event outbox (Kafka-ready, no broker):

```powershell
$env:AGENTOPS_EVENT_OUTBOX = ".\data\events.jsonl"
```

Each successful ingest appends one `agentops.run` v1 JSON line (`create` / `finalize`). A future Kafka producer can publish the same envelope to a topic; SQLite direct write stays the default path.

Quality (optional on ingest): `quality_score` (0–1), `thumbs` (`up`|`down`), `prompt_version`, `template_version`.

Auth (optional):

```powershell
$env:AGENTOPS_API_KEYS = '{"dev-key":{"projects":["demo"]}, "admin":{"projects":["*"]}}'
python -m agentops.http --host 0.0.0.0 --port 8787
```

Send `Authorization: Bearer <key>` or `X-API-Key: <key>` on `/api/*`. Without keys configured, the server stays loopback-only and open (local mode). Non-loopback bind requires keys.
