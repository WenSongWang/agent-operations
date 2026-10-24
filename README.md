# agent-operations

Open-source **Agent Operations** (AgentOps / LLMOps) toolkit — trace runs, track latency / tokens / cost, and debug tool failures.

Lightweight and self-hostable. Default storage is one SQLite file. No ClickHouse required.

| 项 | 值 |
| :--- | :--- |
| Python | ≥ 3.11 |
| Install | `pip install agent-operations`（或源码 `pip install -e .`） |
| Default UI | http://127.0.0.1:8787 |
| Default DB | `./data/agentops.db` |

## 5 分钟上手

### 1. 安装

```powershell
python -m pip install agent-operations
```

从源码开发：

```powershell
git clone https://github.com/WenSongWang/agent-operations.git
cd agent-operations
python -m pip install -e .
python -m unittest discover -s tests -v
```

### 2. 用 Python 写入一条 run

```python
from agentops import connect, ingest_run

conn = connect("./data/agentops.db")
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
    # cost_usd 可省略：会按内置单价估算
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

或直接跑示例：

```powershell
python examples/quickstart.py
python examples/openai_wrap.py
```

### 2b. 更省事：用 `TracedRun`（推荐）

不用手写 `running` / 终态时间戳；OpenAI 响应可直接抽 token：

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

异常退出时会自动记成 `status=error`。完整示例见 `examples/openai_wrap.py`。

### 2c. 接 Agentic-Loop

```powershell
pip install "agent-operations[agentic-loop]"
```

把 `AgentOpsJournal` 传给 `run_loop(..., journal=...)`（与官方 JSONL journal 同接口）：

```python
from agentops import connect
from agentops.adapters import AgentOpsJournal

conn = connect("./data/agentops.db")
journal = AgentOpsJournal(
    conn,
    project="demo",
    agent="assistant",
    environment="dev",
    runs_dir="./.agentic-loop/runs",  # 可选：同时写 agentic-loop JSONL
)
# terminal = run_loop(messages, tools=tools, llm=llm, journal=journal)
```

可运行示意：`python examples/agentic_loop_wrap.py`。

### 3. 启动本机服务与页面

```powershell
agentops-http
# 等价：python -m agentops.http
```

浏览器打开 http://127.0.0.1:8787  

### 4. 用 HTTP / curl 上报

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

查询：

```powershell
curl -s "http://127.0.0.1:8787/api/runs?project=demo"
curl -s "http://127.0.0.1:8787/api/runs/summary?project=demo"
curl -s "http://127.0.0.1:8787/api/failures?project=demo"
curl -s "http://127.0.0.1:8787/api/runs/run-002"
```

## API 一览

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `GET` | `/` | 只读调试页 |
| `POST` | `/api/runs` | 写入 / 终态更新一条 run |
| `GET` | `/api/runs` | 列表（可按 project/agent/environment/status/时间筛选） |
| `GET` | `/api/runs/summary` | 次数、成功率、token/费用、p50/p95/p99 |
| `GET` | `/api/runs/{id}` | 单条详情（含 steps） |
| `GET` | `/api/failures` | 工具失败归并 |

### 必填字段（run）

`id`, `project`, `agent`, `environment`, `name`, `status`, `started_at`  

终态（`ok` / `error` / `timeout` / `cancelled`）还要 `ended_at`。  
`status=running` 时可省略 `ended_at`；同一 `id` 再报终态会覆盖更新。

### 常用可选字段

| 字段 | 说明 |
| :--- | :--- |
| `latency_ms` / `ttft_ms` | 耗时；不传则尽量从时间戳 / steps 推算 |
| `input_tokens` / `output_tokens` / `cached_tokens` / `reasoning_tokens` | token；未上报保持空，不是 0 |
| `cost_usd` | 费用；不传则按 `provider`+`model` 估算 |
| `provider` / `model` | 厂商与模型 |
| `steps` | 步骤列表（排错用） |
| `quality_score` | 0–1 |
| `thumbs` | `up` / `down` |
| `prompt_version` / `template_version` | 提示词 / 模板版本 |
| `tags` | JSON，如 `{"end_user_id":"..."}` |
| `extra` | 备用 JSON |

步骤必填：`seq`, `kind`, `name`, `status`。

## 可选能力

### 脱敏

```powershell
$env:AGENTOPS_REDACT = "hash"   # off | hash | drop
```

作用于 `task_input` / `task_output`、步骤 `input` / `output` / `traceback`、`tags.end_user_id`。

### 价目表

未传 `cost_usd` 时用内置单价估算。自定义 JSON（键为 `provider/model`）：

```powershell
$env:AGENTOPS_PRICING_PATH = ".\pricing.json"
```

### 告警（适合 cron）

```powershell
$env:AGENTOPS_ALERT_WEBHOOK = "https://example.com/hook"
$env:AGENTOPS_ALERT_FAILURE_RATE = "0.2"
$env:AGENTOPS_ALERT_P95_MS = "3000"
$env:AGENTOPS_ALERT_COST_USD = "10"
agentops-alerts --db .\data\agentops.db
```

有告警时退出码 `2`。`--dry-run` 只打印不 POST。

### 事件 outbox（Kafka 预留）

```powershell
$env:AGENTOPS_EVENT_OUTBOX = ".\data\events.jsonl"
```

每次成功写入追加一行 `agentops.run` v1 事件（`create` / `finalize`）。

### API Key（外网绑定前必配）

```powershell
$env:AGENTOPS_API_KEYS = '{"dev-key":{"projects":["demo"]},"admin":{"projects":["*"]}}'
agentops-http --host 0.0.0.0 --port 8787
```

请求头：`Authorization: Bearer <key>` 或 `X-API-Key: <key>`。  
未配置密钥时：仅建议本机 `127.0.0.1`，接口开放。非 loopback 绑定必须配置密钥。

## 限制（请先读）

| 限制 | 说明 |
| :--- | :--- |
| Alpha | 接口可能继续演进；生产使用请自行评估 |
| SQLite | 默认单机文件库；多机共享库尚未提供（Postgres 在路线图） |
| 自报数据 | 延迟 / token / 费用依赖调用方或估算，不是云厂商账单 |
| 非全链路 APM | 聚焦 agent run + steps，不是通用分布式 tracing |
| Kafka | 目前只有 JSONL outbox，没有内置 broker |
| 页面 | 只读调试页；配置了 API Key 后，浏览器调 API 需自行带密钥 |
| 安装渠道 | PyPI：`pip install agent-operations`；版本见 [PyPI 0.1.0](https://pypi.org/project/agent-operations/0.1.0/) / tag `v0.1.0` |

更细的后续项见 [ROADMAP.md](./ROADMAP.md)。

## 开发

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```

库入口常用符号：`connect`, `ingest_run`, `list_runs`, `summarize_runs`, `get_run`, `list_tool_failures`。
