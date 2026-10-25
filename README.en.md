# agent-operations

[中文](./README.md) | **English**

Open-source **Agent Operations** (AgentOps / LLMOps) toolkit — trace runs, track latency / tokens / cost, and debug tool failures.

Lightweight and self-hostable. Default storage is one SQLite file. No ClickHouse required.

| Item | Value |
| :--- | :--- |
| Python | ≥ 3.11 |
| Install | `pip install agent-operations` (or `pip install -e .` from source) |
| Default UI | http://127.0.0.1:8787 |
| Default DB | `./data/agentops.db` |

## Who should use this / who should not

One line: a **minimal self-hosted agent run ledger**, not a full LLMOps cloud platform.

| A good fit if… | Prefer something else (e.g. Langfuse / cloud consoles) if… |
| :--- | :--- |
| You already have agent code and only need runs / steps / latency / tokens / cost / failures | You want a polished team UI, prompt experiments, click-ops analytics |
| You want localhost or private network — no SaaS signup, no ClickHouse | You want max tutorials, hosted collection, easy Google answers |
| A single `pip` package into your existing loop is enough | You need multi-region ingest and vendor billing reconciliation |
| One-host SQLite is fine; grow into Postgres later | You need product-grade multi-tenant login from day one |

Beginner path: `pip install agent-operations` → `agentops-smoke` (expect `smoke passed`) → `examples/quickstart.py` → `agentops-http` → then consider cloud deploy.

### Platforms (Windows / macOS / Linux / iOS)

| Environment | Local install OK? | Notes |
| :--- | :--- | :--- |
| Windows | Yes | PowerShell / cmd; Python 3.11+ and [uv](https://github.com/astral-sh/uv) recommended |
| macOS | Yes | Terminal; same as above |
| Linux | Yes | Distro or official Python 3.11+ |
| iPhone / iPad (iOS) | **Not an install target** | Cannot `pip install` the server on-device; Safari can open a **deployed** debug page; apps act as HTTP **clients** only |

Core dependency is **Python 3.11+** on the three desktop OSes. After cloud deploy, any HTTPS client (including iOS apps) can post runs without installing this package locally.

## Choosing a database (SQLite / Postgres)

“Multiple options” here means **you pick the storage** to trade difficulty and cost for scale — not commercial SKUs.

| Choose | When | Cost / difficulty | How |
| :--- | :--- | :--- | :--- |
| **SQLite** (default) | Localhost, single node, light write load | Lowest: no extra middleware | `connect("./data/agentops.db")` or `agentops-http --db ...` |
| **Postgres** | Several services share one ledger, managed cloud DB, normal backup/replica needs | Medium: one DB instance + `pip install "agent-operations[postgres]"` | `connect("postgresql://…")` / `--db` / `AGENTOPS_DATABASE_URL` |
| **MySQL, etc.** | You already run MySQL and refuse Postgres | — | **Not supported yet**; add only when needed |

Start with SQLite. Move to Postgres only when you need multi-writer sharing or a mandated managed database.

## Deploy on a cloud host for other services

Yes. Other agents do **not** need this library on their machines — only HTTP access to your `agentops-http`, then `POST` runs.

```text
[agent on cloud A] --HTTPS POST /api/runs--> [your agentops-http + DB]
[worker on cloud B] --same------------------┘
```

Minimal cloud steps (any VPS / container):

```powershell
pip install "agent-operations[postgres]"   # Postgres for multi-host; SQLite OK for single node + disk
$env:AGENTOPS_API_KEYS = '{"svc-a":{"projects":["demo"]},"admin":{"projects":["*"]}}'
# Shared DB:
# $env:AGENTOPS_DATABASE_URL = "postgresql://user:pass@host:5432/agentops"
agentops-http --host 0.0.0.0 --port 8787 --db $env:AGENTOPS_DATABASE_URL
```

Put Nginx / Caddy in front for **HTTPS**; expose 443 only. Caller example:

```powershell
curl -s https://agentops.example.com/api/runs `
  -H "X-API-Key: svc-a" -H "Content-Type: application/json" `
  -d '{"id":"run-cloud-1","project":"demo","agent":"assistant","environment":"prd","name":"job","status":"ok","started_at":"2026-10-25T04:00:00+00:00","ended_at":"2026-10-25T04:00:01+00:00"}'
```

Cloud checklist:

| Topic | Note |
| :--- | :--- |
| Auth | Non-loopback bind **requires** API keys; treat keys as secrets |
| DB | SQLite = single instance + persistent disk; multi-writer → Postgres |
| Role | Ledger only — does not call OpenAI for you |
| Safety | Do not expose `0.0.0.0` on the public internet without HTTPS / keys |

## 5-minute start

### 1. Install and smoke

```powershell
python -m pip install agent-operations
agentops-smoke
# From a git checkout: python scripts/smoke.py
```

`smoke passed` means the local path works (same command on Win / macOS / Linux).

From source (recommended: **uv**):

```powershell
git clone https://github.com/WenSongWang/agent-operations.git
cd agent-operations
uv venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
uv pip install -e ".[agentic-loop,openai,langgraph]"
python -m unittest discover -s tests -v
```

Without uv: `python -m venv .venv`, activate, then `python -m pip install -e ".[agentic-loop,openai,langgraph]"`.

### 2. Ingest a run from Python

Default SQLite file; for Postgres use a DSN (`pip install "agent-operations[postgres]"`):

```python
from agentops import connect, ingest_run

conn = connect("./data/agentops.db")
# conn = connect("postgresql://user:pass@localhost:5432/agentops")
ingest_run(conn, {
    "id": "run-001",
    "project": "demo",
    "agent": "assistant",
    "environment": "dev",          # dev | test | uat | prd
    "name": "answer-question",
    "status": "ok",                # running | ok | error | timeout | cancelled
    "started_at": "2026-10-24T10:00:00+00:00",
    "ended_at": "2026-10-24T10:00:02+00:00",
    "provider": "openai",
    "model": "gpt-4o-mini",
    "input_tokens": 100,
    "output_tokens": 50,
    # cost_usd optional: estimated from built-in rates when omitted
    "steps": [
        {
            "seq": 1,
            "kind": "llm",         # llm | tool | agent | human
            "name": "gpt-4o-mini",
            "status": "ok",
            "started_at": "2026-10-24T10:00:00+00:00",
            "ended_at": "2026-10-24T10:00:02+00:00",
            "input_tokens": 100,
            "output_tokens": 50,
        }
    ],
})
conn.close()
```

Or run examples:

```powershell
python examples/quickstart.py
python examples/openai_wrap.py
```

### 2b. Easier: `TracedRun` (recommended)

No manual `running` / final timestamps; OpenAI responses can fill tokens:

```python
from agentops import connect, TracedRun

conn = connect("./data/agentops.db")
with TracedRun(
    conn,
    project="demo",
    agent="assistant",
    environment="dev",
    name="chat",
    task_input="Say hi",
) as tr:
    # resp = client.chat.completions.create(...)
    # tr.record_openai(resp, output_text=resp.choices[0].message.content)
    tr.finish(task_output="hi")
conn.close()
```

Exceptions become `status=error`. Fake response demo: `examples/openai_wrap.py`.

Live call (`OPENAI_API_KEY` + `pip install openai`):

```powershell
$env:OPENAI_API_KEY = "sk-..."
# optional: $env:OPENAI_BASE_URL / $env:OPENAI_MODEL
python examples/openai_live.py
```

### 2c. Agentic-Loop

```powershell
pip install "agent-operations[agentic-loop]"
```

Pass `AgentOpsJournal` to `run_loop(..., journal=...)`.

```python
from agentops import connect
from agentops.adapters import AgentOpsJournal

conn = connect("./data/agentops.db")
journal = AgentOpsJournal(
    conn,
    project="demo",
    agent="assistant",
    environment="dev",
    runs_dir="./.agentic-loop/runs",
)
# terminal = run_loop(messages, tools=tools, llm=llm, journal=journal)
```

Runnable sketch: `python examples/agentic_loop_wrap.py`.

### 2d. LangGraph

```python
from agentops import connect
from agentops.adapters.langgraph import traced_invoke

conn = connect("./data/agentops.db")
result = traced_invoke(
    app,
    {"messages": [...]},
    conn=conn,
    project="demo",
    agent="support-bot",
    environment="dev",
    name="support",
    config={"configurable": {"thread_id": "1"}},
)
```

No-LLM sketch: `python examples/langgraph_wrap.py`.

### 3. Local server + page

```powershell
agentops-http
# Postgres: agentops-http --db "postgresql://..."
# or AGENTOPS_DATABASE_URL
```

Open http://127.0.0.1:8787  

### 4. HTTP / curl ingest

```powershell
curl -s http://127.0.0.1:8787/api/runs -Method POST -ContentType "application/json" -Body @'
{
  "id": "run-002",
  "project": "demo",
  "agent": "assistant",
  "environment": "dev",
  "name": "via-http",
  "status": "ok",
  "started_at": "2026-10-24T11:00:00+00:00",
  "ended_at": "2026-10-24T11:00:01+00:00",
  "latency_ms": 1000,
  "input_tokens": 10,
  "output_tokens": 5
}
'@
```

Query:

```powershell
curl -s "http://127.0.0.1:8787/api/runs?project=demo"
curl -s "http://127.0.0.1:8787/api/runs/summary?project=demo"
curl -s "http://127.0.0.1:8787/api/failures?project=demo"
curl -s "http://127.0.0.1:8787/api/runs/run-002"
```

## API overview

| Method | Path | Purpose |
| :--- | :--- | :--- |
| `GET` | `/` | Read-only debug page |
| `POST` | `/api/runs` | Create / finalize a run |
| `GET` | `/api/runs` | List (filter by project/agent/environment/status/time) |
| `GET` | `/api/runs/summary` | Counts, success rate, tokens/cost, p50/p95/p99 |
| `GET` | `/api/runs/{id}` | Detail including steps |
| `GET` | `/api/failures` | Grouped tool failures |

### Required run fields

`id`, `project`, `agent`, `environment`, `name`, `status`, `started_at`  

Final statuses also need `ended_at`.  
`status=running` may omit `ended_at`; the same `id` can be finalized later.

### Common optional fields

| Field | Notes |
| :--- | :--- |
| `latency_ms` / `ttft_ms` | Derived from timestamps / steps when omitted |
| `input_tokens` / `output_tokens` / … | Unreported stays null, not zero |
| `cost_usd` | Estimated from `provider`+`model` when omitted |
| `steps` | For debugging |
| `quality_score` / `thumbs` / versions / `tags` / `extra` | Quality and metadata |

Step required: `seq`, `kind`, `name`, `status`.

## Optional features

### Redaction

```powershell
$env:AGENTOPS_REDACT = "hash"   # off | hash | drop
```

### Pricing

```powershell
$env:AGENTOPS_PRICING_PATH = ".\pricing.json"
```

### Alerts (cron-friendly)

```powershell
$env:AGENTOPS_ALERT_WEBHOOK = "https://example.com/hook"
$env:AGENTOPS_ALERT_FAILURE_RATE = "0.2"
$env:AGENTOPS_ALERT_EMAIL = "ops@example.com"
$env:AGENTOPS_SMTP_HOST = "smtp.example.com"
agentops-alerts --db .\data\agentops.db
```

Exit code `2` when alerts fire. `--dry-run` prints only.

### Event outbox / Kafka

```powershell
$env:AGENTOPS_EVENT_OUTBOX = ".\data\events.jsonl"
$env:AGENTOPS_KAFKA_BOOTSTRAP = "localhost:9092"
agentops-kafka --db .\data\agentops.db
```

Consumer uses `emit=False` (no re-publish loop). Needs `pip install "agent-operations[kafka]"`.

### API keys (required before public bind)

```powershell
$env:AGENTOPS_API_KEYS = '{"dev-key":{"projects":["demo"]},"admin":{"projects":["*"]}}'
agentops-http --host 0.0.0.0 --port 8787
```

Headers: `Authorization: Bearer <key>` or `X-API-Key: <key>`.

## Something went wrong?

Use this symptom → check table first; if still stuck, include the **full error text**.

| Symptom | Check |
| :--- | :--- |
| `agentops-smoke` / `agentops-http` not found | Installed (`pip install agent-operations`)? venv activated? On Windows try `python -m agentops.smoke` / `python -m agentops.http` |
| Smoke fails or HTTP unreachable | Local firewall; re-run `agentops-smoke` and read any `FAIL:` line |
| Page loads but empty / auth hint | If `AGENTOPS_API_KEYS` is set, paste the same key on the debug page and Reload; send `X-API-Key` or `Authorization: Bearer …` |
| POST `/api/runs` → 400 | Read JSON `error`: missing fields, bad `environment`/`status`, or final status without `ended_at` are most common |
| “duplicate” / already finalized | One create per `id`; a `running` run can be finalized once. Use a new `id` or `GET /api/runs/{id}` |
| Crash on `--host 0.0.0.0` | Non-loopback bind requires `AGENTOPS_API_KEYS` |
| Missing `kafka-python` / `psycopg` | `pip install "agent-operations[kafka]"` or `[postgres]` |
| SQLite / permission errors | Is the `--db` directory writable? Avoid read-only disks; multi-process writers on one SQLite file can lock |
| Cloud 502 / unreachable | Security group; listening on `127.0.0.1` only; reverse proxy target port |
| Kafka consumer prints `skip:` | Invalid `agentops.run` v1 JSON or payload failed the same ingest rules |

Quick check:

```powershell
python -c "import agentops; print(agentops.__version__)"
agentops-smoke
```

## Limits

| Limit | Notes |
| :--- | :--- |
| Alpha | APIs may evolve |
| DB | SQLite default; Postgres via DSN / `AGENTOPS_DATABASE_URL` |
| Self-reported metrics | Not vendor invoices |
| Not full APM | Agent runs + steps only |
| Kafka | Optional producer/consumer; no embedded broker |
| UI | Read-only debug page |
| Install | PyPI: https://pypi.org/project/agent-operations/ / tag `v0.1.6` |

See [ROADMAP.md](./ROADMAP.md).

## Development

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[agentic-loop,openai,langgraph]"
python -m unittest discover -s tests -v
agentops-smoke
agentops-http
```

Common exports: `connect`, `ingest_run`, `list_runs`, `summarize_runs`, `get_run`, `list_tool_failures`, `TracedRun`.
