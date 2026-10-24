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
