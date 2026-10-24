# Roadmap

## Phase 1 (current: `feat/phase1-mvp`)

SQLite ingest · list/filter · latency/tokens/cost summary (p50/p95/p99) · tool failure debug · loopback HTTP + read-only page.

## Later

| Step | Topic | Notes |
| :--- | :--- | :--- |
| 13 | In-progress runs | Done: `running` → final update on same `id` |
| 14 | Redaction | Done: `AGENTOPS_REDACT` / `redact=` → off\|hash\|drop |
| 15 | Postgres | Skipped for now (SQLite enough for single-host) |
| 16 | Pricing table | Done: built-in rates + `AGENTOPS_PRICING_PATH`; caller `cost_usd` wins |
| 17 | Alerts | Done: webhook on failure rate / p95 / cost (email later) |
| 18 | Kafka upgrade | Partial: `agentops.run` v1 envelope + `AGENTOPS_EVENT_OUTBOX` JSONL; broker producer later |
| 19 | Eval / quality | Optional scores, thumbs, prompt/template version columns |
| 20 | Auth / multi-tenant | API keys, project ACL; bind beyond loopback |
