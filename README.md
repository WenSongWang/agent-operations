# agent-operations

**中文** | [English](./README.en.md)

Open-source **Agent Operations** (AgentOps / LLMOps) toolkit — trace runs, track latency / tokens / cost, and debug tool failures.

Lightweight and self-hostable. Default storage is one SQLite file. No ClickHouse required.

| 项 | 值 |
| :--- | :--- |
| Python | ≥ 3.11 |
| Install | `pip install agent-operations`（或源码 `pip install -e .`） |
| Default UI | http://127.0.0.1:8787 |
| Default DB | `./data/agentops.db` |

## 什么人该用 / 不该用

一句话：这是**最小可自托管的 Agent 运行账本**，不是完整的 LLMOps 云平台。

| 更适合你，如果… | 更该选别的（如 Langfuse / 云厂商控制台），如果… |
| :--- | :--- |
| 已有 agent 代码，只想记 run / steps / 延迟 / token / 费用 / 失败 | 要漂亮的团队 UI、Prompt 实验、人人点选的分析台 |
| 想本机或内网跑，不想注册 SaaS、不想养 ClickHouse | 要开箱即用、教程最多、出问题好搜 |
| `pip` 一个包就能塞进现有循环 | 要托管采集、多区域、厂商级账单对账 |
| 单机 SQLite 就够；长大再迁 Postgres | 一上来就要多租户产品级登录与权限中心 |

小白路径建议：本机 `pip install agent-operations` → `agentops-smoke`（应打印 `smoke passed`）→ `examples/quickstart.py` → `agentops-http` 看页面；确认有用再考虑云上部署。

### 系统要求（Windows / macOS / Linux / iOS）

| 环境 | 能否顺利用 | 说明 |
| :--- | :--- | :--- |
| Windows | 可以 | PowerShell / cmd；推荐 Python 3.11+ 与 [uv](https://github.com/astral-sh/uv) |
| macOS | 可以 | Terminal；同上 |
| Linux | 可以 | 发行版自带或官方 Python 3.11+ |
| iPhone / iPad (iOS) | **不作为安装端** | 不能在手机里 `pip install` 跑服务；手机浏览器可打开**你已部署好的**调试页；App 只能当 HTTP **客户端**上报 run |

核心依赖是 **Python 3.11+**，三桌面系统等价。云上部署后，任意能发 HTTPS 的客户端（含 iOS App）都能用，与本机是否装过本包装无关。

## 部署到云给其它服务用

可以。其它云上的 agent **不**用把库装进对方机器里；只要能 HTTP 访问你的 `agentops-http`，把 run `POST` 过来即可。

```text
[云 A 上的 agent] --HTTPS POST /api/runs--> [你部署的 agentops-http + DB]
[云 B 上的 worker] --同上-------------------┘
```

最小云上步骤（任意 VPS / 容器均可）：

```powershell
pip install "agent-operations[postgres]"   # 多机或托管库时建议 Postgres；单机也可用 SQLite 盘
$env:AGENTOPS_API_KEYS = '{"svc-a":{"projects":["demo"]},"admin":{"projects":["*"]}}'
# 多实例共享库时：
# $env:AGENTOPS_DATABASE_URL = "postgresql://user:pass@host:5432/agentops"
agentops-http --host 0.0.0.0 --port 8787 --db $env:AGENTOPS_DATABASE_URL
```

前面加 Nginx / Caddy 做 **HTTPS**，对外只暴露 443。调用方示例：

```powershell
curl -s https://agentops.example.com/api/runs `
  -H "X-API-Key: svc-a" -H "Content-Type: application/json" `
  -d '{"id":"run-cloud-1","project":"demo","agent":"assistant","environment":"prd","name":"job","status":"ok","started_at":"2026-10-25T04:00:00+00:00","ended_at":"2026-10-25T04:00:01+00:00"}'
```

云上注意：

| 点 | 说明 |
| :--- | :--- |
| 鉴权 | 非本机绑定**必须**配置 API key；密钥当密码保管 |
| 库 | SQLite = 单实例 + 持久盘；多机写同一数据用 Postgres |
| 职责 | 只记账本，不替你调 OpenAI；各服务仍直连自己的 LLM |
| 安全 | 不要把 `--host 0.0.0.0` 裸奔在公网无 HTTPS / 无密钥 |

## 5 分钟上手

### 1. 安装并冒烟

```powershell
python -m pip install agent-operations
agentops-smoke
# 源码树也可用：python scripts/smoke.py
```

看到 `smoke passed` 即本机链路正常（Win / macOS / Linux 同一命令）。

从源码开发（推荐 **uv**）：

```powershell
git clone https://github.com/WenSongWang/agent-operations.git
cd agent-operations
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[agentic-loop,openai,langgraph]"
python -m unittest discover -s tests -v
```

没有 uv 时：`python -m venv .venv`，激活后用 `python -m pip install -e ".[agentic-loop,openai,langgraph]"`。

### 2. 用 Python 写入一条 run

默认 SQLite 文件；Postgres 时把路径换成 DSN（需 `pip install "agent-operations[postgres]"`）：

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

异常退出时会自动记成 `status=error`。假响应示意：`examples/openai_wrap.py`。

真实调用（需 `OPENAI_API_KEY` + `pip install openai`）：

```powershell
$env:OPENAI_API_KEY = "sk-..."
# 可选：$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
# 可选：$env:OPENAI_MODEL = "gpt-4o-mini"
python examples/openai_live.py
```

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

### 2d. 接 LangGraph

```python
from agentops import connect
from agentops.adapters.langgraph import traced_invoke

conn = connect("./data/agentops.db")
result = traced_invoke(
    app,  # any object with .invoke / use traced_ainvoke for .ainvoke
    {"messages": [...]},
    conn=conn,
    project="demo",
    agent="support-bot",
    environment="dev",
    name="support",
    config={"configurable": {"thread_id": "1"}},
)
```

示意（无 LLM）：`python examples/langgraph_wrap.py`。

### 3. 启动本机服务与页面

```powershell
agentops-http
# 等价：python -m agentops.http
# Postgres（需 agent-operations[postgres]）：
# agentops-http --db "postgresql://user:pass@localhost:5432/agentops"
# 或 $env:AGENTOPS_DATABASE_URL = "postgresql://..."
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
# 可选：同时发邮件（stdlib SMTP）
$env:AGENTOPS_ALERT_EMAIL = "ops@example.com"
$env:AGENTOPS_SMTP_HOST = "smtp.example.com"
# $env:AGENTOPS_SMTP_PORT = "587"
# $env:AGENTOPS_SMTP_USER = "..."
# $env:AGENTOPS_SMTP_PASSWORD = "..."
# $env:AGENTOPS_SMTP_FROM = "agentops@example.com"
# $env:AGENTOPS_SMTP_TLS = "1"
agentops-alerts --db .\data\agentops.db
```

有告警时退出码 `2`。`--dry-run` 只打印，不 webhook / 不发信。

### 事件 outbox / Kafka

```powershell
$env:AGENTOPS_EVENT_OUTBOX = ".\data\events.jsonl"
# 可选：同时发到 Kafka（需 pip install "agent-operations[kafka]"）
$env:AGENTOPS_KAFKA_BOOTSTRAP = "localhost:9092"
# $env:AGENTOPS_KAFKA_TOPIC = "agentops.run"          # 默认
# $env:AGENTOPS_KAFKA_CLIENT_ID = "agentops"          # 默认
```

每次成功写入追加一行 `agentops.run` v1 事件（`create` / `finalize`）；若配置了 bootstrap 则再 publish 同一 JSON。

另开进程消费写入本地库（不会再次 emit，避免回环）：

```powershell
# $env:AGENTOPS_KAFKA_GROUP = "agentops-ingest"   # 默认
agentops-kafka --db .\data\agentops.db
# agentops-kafka --max-messages 100
```

### API Key（外网绑定前必配）

```powershell
$env:AGENTOPS_API_KEYS = '{"dev-key":{"projects":["demo"]},"admin":{"projects":["*"]}}'
agentops-http --host 0.0.0.0 --port 8787
```

请求头：`Authorization: Bearer <key>` 或 `X-API-Key: <key>`。  
未配置密钥时：仅建议本机 `127.0.0.1`，接口开放。非 loopback 绑定必须配置密钥。

调试页有 **API key** 输入框（存浏览器 `localStorage`），Reload 时自动带 `X-API-Key`。

## 出问题了？

按下面「现象 → 先查什么」自查；仍不行再带上**完整报错原文**提问。

| 现象 | 先查什么 |
| :--- | :--- |
| `agentops-smoke` / `agentops-http` 不是命令 | 是否已 `pip install agent-operations`、是否激活了虚拟环境；Win 可试 `python -m agentops.smoke` / `python -m agentops.http` |
| `smoke` 失败或 HTTP 连不上 | 是否被防火墙拦截本机回环；换一台终端再跑 `agentops-smoke`；看输出里的 `FAIL:` 行 |
| 页面能开但数据空 / 提示 Auth | 服务若配置了 `AGENTOPS_API_KEYS`，在调试页填同一 key 再 Reload；请求头用 `X-API-Key` 或 `Authorization: Bearer …` |
| POST `/api/runs` 返回 400 | 读 JSON 里的 `error`：缺字段、非法 `environment`/`status`、终态缺 `ended_at` 最常见；对照上文「必填字段」 |
| POST 返回「duplicate」/ already finalized | 同一 `id` 只能创建一次；`running` 只能再报一次终态。换新 `id` 或先查 `GET /api/runs/{id}` |
| `--host 0.0.0.0` 启动直接报错 | 非本机绑定必须设置 `AGENTOPS_API_KEYS`（见上文「API Key」） |
| 提示需要 `kafka-python` / `psycopg` | `pip install "agent-operations[kafka]"` 或 `[postgres]` |
| SQLite / 文件权限错误 | `--db` 目录是否可写；不要把 DB 放在只读盘；多进程同时写同一 SQLite 文件可能锁库 |
| 云上 502 / 连不上 | 安全组是否放行；是否只监听了 `127.0.0.1`；反代 HTTPS 是否指到 `agentops-http` 端口 |
| Kafka 消费一直 `skip:` | 看 skip 后的原因：JSON 不是 `agentops.run` v1，或 payload 校验失败（与 ingest 相同规则） |

快速自检命令：

```powershell
python -c "import agentops; print(agentops.__version__)"
agentops-smoke
```

## 限制（请先读）

| 限制 | 说明 |
| :--- | :--- |
| Alpha | 接口可能继续演进；生产使用请自行评估 |
| DB | 默认 SQLite；也可 `connect` / `agentops-http --db` / `AGENTOPS_DATABASE_URL` 用 `postgresql://…`（需 `[postgres]`） |
| 自报数据 | 延迟 / token / 费用依赖调用方或估算，不是云厂商账单 |
| 非全链路 APM | 聚焦 agent run + steps，不是通用分布式 tracing |
| Kafka | JSONL outbox + 可选 producer / `agentops-kafka` consumer；无内置 broker |
| 页面 | 只读调试页；可填 API key 后查询 |
| 安装渠道 | PyPI：`pip install agent-operations`；版本见 [PyPI](https://pypi.org/project/agent-operations/) / tag `v0.1.5` |

更细的后续项见 [ROADMAP.md](./ROADMAP.md)。

## 开发

推荐用 uv 虚拟环境（本机已可用 `uv`）：

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[agentic-loop,openai,langgraph]"
uv pip install build twine   # 仅发版需要
python -m unittest discover -s tests -v
agentops-http
```

验证 PyPI 包时另建干净环境，例如：

```powershell
uv venv .venv-release --clear
.\.venv-release\Scripts\Activate.ps1
uv pip install "agent-operations==0.1.5"
```

库入口常用符号：`connect`, `ingest_run`, `list_runs`, `summarize_runs`, `get_run`, `list_tool_failures`, `TracedRun`。
