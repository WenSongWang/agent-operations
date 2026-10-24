# Changelog

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
