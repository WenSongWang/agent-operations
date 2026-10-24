# Changelog

## [0.1.0] - 2026-10-24

First public alpha of **agent-operations**: lightweight, self-hosted AgentOps / LLMOps on SQLite.

### Highlights

- Ingest agent runs + steps; `running` → finalize on the same `id`
- Query list / summary (p50/p95/p99 latency, tokens, cost) and tool-failure grouping
- Local HTTP API + read-only debug page (`agentops-http`)
- `TracedRun` helper + OpenAI usage extraction (`examples/openai_wrap.py`)
- Optional redaction, pricing estimates, webhook alerts, JSONL event outbox
- Optional API keys with project ACL; non-loopback bind requires keys

### Install

```powershell
git clone https://github.com/WenSongWang/agent-operations.git
cd agent-operations
python -m pip install -e .
agentops-http
```

See [README.md](./README.md) for the 5-minute guide.

### Not in 0.1.0

- PyPI upload (source install only for now)
- Postgres backend
- Kafka broker producer/consumer
- Alert email / logged-in UI
