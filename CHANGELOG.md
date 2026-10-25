# Changelog

## [0.1.7] - 2026-10-25

### Added

- `agentops-smoke --fail-demo` to learn intentional IngestError / HTTP 400 shapes
- Stable JSON `code` on HTTP errors (e.g. `missing_fields`, `missing_api_key`, `not_found`)

## [0.1.6] - 2026-10-25

### Added

- README troubleshooting (“出问题了？” / Something went wrong?)
- Friendlier CLI errors (`error:` + `next:`) for `agentops-http`, `agentops-alerts`, `agentops-kafka`
- Shared `agentops.cliutil.cli_exit`
- README: SQLite vs Postgres choice table (DIY storage options)

## [0.1.5] - 2026-10-25

### Added

- `agentops-smoke` console script + `scripts/smoke.py` for beginner verification
- README: who should use this, cloud deploy for other services, platform notes (Win/macOS/Linux/iOS)
- English docs: [README.en.md](./README.en.md)

## [0.1.4] - 2026-10-25

### Added

- `agentops-kafka` consumer: ingest `agentops.run` events with `emit=False` (no re-publish loop)
- `ingest_run(..., emit=False)` for sink / consumer paths

## [0.1.3] - 2026-10-24

### Added

- Optional Kafka producer (`AGENTOPS_KAFKA_BOOTSTRAP`, extra `[kafka]`)
- Optional Postgres via `connect("postgresql://…")` / `agentops-http --db` / `AGENTOPS_DATABASE_URL` (extra `[postgres]`)
- Optional SMTP email alerts (`AGENTOPS_ALERT_EMAIL` + `AGENTOPS_SMTP_*`)
- README: uv local development workflow

## [0.1.2] - 2026-10-24

### Added

- Live OpenAI example: `examples/openai_live.py` (`OPENAI_API_KEY`)
- Debug page API key field (localStorage + `X-API-Key`)
- LangGraph helpers: `traced_invoke` / `traced_ainvoke` + `examples/langgraph_wrap.py`
- Optional extras: `openai`, `langgraph`

## [0.1.1] - 2026-10-24

### Added

- `AgentOpsJournal` adapter for [agentic-loop](https://pypi.org/project/agentic-loop/) (`run_loop(..., journal=...)`)
- Example: `examples/agentic_loop_wrap.py`
- Optional extra: `pip install "agent-operations[agentic-loop]"`

### Changed

- Docs: Agentic-Loop wiring in README
- Packaging: SPDX `license = "MIT"` (setuptools warning cleanup)

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

### Install from PyPI

```powershell
python -m pip install agent-operations
```

https://pypi.org/project/agent-operations/

### Not in 0.1.0

- Postgres backend
- Kafka broker producer/consumer
- Alert email / logged-in UI
