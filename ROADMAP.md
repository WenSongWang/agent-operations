# Roadmap

## Phase 1 (current: `feat/phase1-mvp`)

SQLite ingest · list/filter · latency/tokens/cost summary (p50/p95/p99) · tool failure debug · loopback HTTP + read-only page.

## Later

| Step | Topic | Notes |
| :--- | :--- | :--- |
| 13 | In-progress runs | Done: `running` → final update on same `id` |
| 14 | Redaction | Done: `AGENTOPS_REDACT` / `redact=` → off\|hash\|drop |
| 15 | Postgres | Optional backend; schema aligned with SQLite |
| 16 | Pricing table | Estimate `cost_usd` from provider+model; caller override still wins |
| 17 | Alerts | Webhook/email on failure rate, p95, cost spikes |
| 18 | Kafka upgrade | Multi-host high-throughput ingest via topics; direct write path remains |
| 19 | Eval / quality | Optional scores, thumbs, prompt/template version columns |
| 20 | Auth / multi-tenant | API keys, project ACL; bind beyond loopback |
