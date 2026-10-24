"""Local read/write HTTP API and a simple debug page (127.0.0.1 only)."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from agentops.auth import (
    AuthError,
    Principal,
    authenticate,
    load_api_keys,
    scope_project_filter,
)
from agentops.db import connect
from agentops.ingest import IngestError, ingest_run
from agentops.query import (
    get_run,
    list_runs,
    list_tool_failures,
    summarize_runs,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_DB = Path("data") / "agentops.db"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>agent-operations</title>
<style>
:root { --bg:#f6f4ef; --ink:#1c1b19; --muted:#5c574e; --line:#d9d2c5; --acc:#0f6b5c; }
*{box-sizing:border-box} body{margin:0;font:15px/1.45 Georgia,serif;background:var(--bg);color:var(--ink)}
header{padding:1.25rem 1.5rem;border-bottom:1px solid var(--line)}
h1{margin:0;font-size:1.4rem;letter-spacing:.02em} h1 span{color:var(--acc)}
main{display:grid;gap:1rem;padding:1rem 1.5rem 2rem}
.panel{border-top:1px solid var(--line);padding-top:.75rem}
.muted{color:var(--muted);font-size:.9rem}
.filters{display:flex;flex-wrap:wrap;gap:.5rem;align-items:end}
label{display:flex;flex-direction:column;gap:.2rem;font-size:.8rem;color:var(--muted)}
input,select,button{font:inherit;padding:.35rem .5rem}
button{background:var(--acc);color:#fff;border:0;cursor:pointer}
table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:.4rem .3rem;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:hover{background:#efeae0;cursor:pointer}
pre{white-space:pre-wrap;background:#efeae0;padding:.75rem;overflow:auto;max-height:28rem}
.stats{display:flex;flex-wrap:wrap;gap:1rem} .stat strong{display:block;font-size:1.2rem}
</style>
</head>
<body>
<header><h1>agent-<span>operations</span></h1>
<p class="muted">runs · latency · tokens · cost · quality · tool failures</p></header>
<main>
<section class="panel">
  <div class="filters">
    <label>API key<input id="apiKey" type="password" placeholder="if server requires auth" autocomplete="off"/></label>
    <label>project<input id="project"/></label>
    <label>agent<input id="agent"/></label>
    <label>environment
      <select id="environment"><option value="">any</option>
      <option>dev</option><option>test</option><option>uat</option><option>prd</option></select>
    </label>
    <label>status
      <select id="status"><option value="">any</option>
      <option>running</option><option>ok</option><option>error</option>
      <option>timeout</option><option>cancelled</option></select>
    </label>
    <button id="reload">Reload</button>
  </div>
  <p id="authHint" class="muted"></p>
</section>
<section class="panel"><h2>Summary</h2><div id="summary" class="stats muted">Loading…</div></section>
<section class="panel"><h2>Tool failures</h2><div id="failures" class="muted">Loading…</div></section>
<section class="panel"><h2>Runs</h2>
  <table><thead><tr>
    <th>started</th><th>id</th><th>agent</th><th>env</th><th>status</th>
    <th>latency</th><th>tokens</th><th>cost</th><th>quality</th><th>thumbs</th>
  </tr></thead><tbody id="runs"></tbody></table>
</section>
<section class="panel"><h2>Detail</h2><pre id="detail">Select a run.</pre></section>
</main>
<script>
const $ = (id) => document.getElementById(id);
const KEY_STORE = 'agentops.apiKey';
$('apiKey').value = localStorage.getItem(KEY_STORE) || '';
$('apiKey').addEventListener('change', () => {
  localStorage.setItem(KEY_STORE, $('apiKey').value.trim());
});
function q() {
  const p = new URLSearchParams();
  for (const k of ['project','agent','environment','status']) {
    const v = $(k).value.trim(); if (v) p.set(k, v);
  }
  return p.toString();
}
function fmt(n){ return n==null ? '—' : n; }
function apiHeaders() {
  const h = {};
  const key = $('apiKey').value.trim();
  if (key) h['X-API-Key'] = key;
  return h;
}
async function apiGet(path) {
  const resp = await fetch(path, { headers: apiHeaders() });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const msg = data.error || (resp.status + ' ' + resp.statusText);
    throw new Error(msg);
  }
  return data;
}
async function load() {
  localStorage.setItem(KEY_STORE, $('apiKey').value.trim());
  $('authHint').textContent = '';
  const qs = q();
  try {
    const [summary, runs, failures] = await Promise.all([
      apiGet('/api/runs/summary'+(qs?'?'+qs:'')),
      apiGet('/api/runs'+(qs?'?'+qs:'')),
      apiGet('/api/failures'+(qs?'?'+qs:'')),
    ]);
  $('summary').innerHTML = `
    <div class="stat"><strong>${summary.count}</strong>runs</div>
    <div class="stat"><strong>${fmt(summary.success_rate==null?null:(summary.success_rate*100).toFixed(0)+'%')}</strong>success</div>
    <div class="stat"><strong>${fmt(summary.latency_ms.p50)}</strong>p50 ms</div>
    <div class="stat"><strong>${fmt(summary.latency_ms.p95)}</strong>p95 ms</div>
    <div class="stat"><strong>${fmt(summary.latency_ms.p99)}</strong>p99 ms</div>
    <div class="stat"><strong>${fmt(summary.tokens.input)}/${fmt(summary.tokens.output)}</strong>in/out tok</div>
    <div class="stat"><strong>${fmt(summary.cost_usd.total)}</strong>cost usd</div>`;
  $('failures').innerHTML = failures.length ? `<table><thead><tr>
    <th>project</th><th>agent</th><th>env</th><th>tool</th><th>error</th><th>count</th>
    </tr></thead><tbody>${failures.map(f=>`<tr>
      <td>${f.project}</td><td>${f.agent}</td><td>${f.environment}</td>
      <td>${f.tool_name}</td><td>${f.error_type||'—'}</td><td>${f.count}</td>
    </tr>`).join('')}</tbody></table>` : 'No tool failures.';
  $('runs').innerHTML = runs.map(r => {
    const tok = (r.input_tokens??'—') + '/' + (r.output_tokens??'—');
    return `<tr data-id="${r.id}">
      <td>${r.started_at}</td><td>${r.id}</td><td>${r.agent}</td><td>${r.environment}</td>
      <td>${r.status}</td><td>${fmt(r.latency_ms)}</td><td>${tok}</td><td>${fmt(r.cost_usd)}</td>
      <td>${fmt(r.quality_score)}</td><td>${fmt(r.thumbs)}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="10">No runs.</td></tr>';
  for (const tr of $('runs').querySelectorAll('tr[data-id]')) {
    tr.onclick = async () => {
      try {
        const d = await apiGet('/api/runs/'+encodeURIComponent(tr.dataset.id));
        $('detail').textContent = JSON.stringify(d, null, 2);
      } catch (err) {
        $('detail').textContent = String(err.message || err);
      }
    };
  }
  } catch (err) {
    const msg = String(err.message || err);
    $('authHint').textContent = msg.includes('API key')
      ? 'Auth required: paste an API key above, then Reload.'
      : msg;
    $('summary').textContent = 'Failed to load.';
    $('failures').textContent = '';
    $('runs').innerHTML = '';
  }
}
$('reload').onclick = load;
load();
</script>
</body>
</html>
"""


def _json_bytes(data: Any, status: int = 200) -> tuple[int, bytes, str]:
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def make_handler(
    db_path: Path | str, api_keys: dict[str, Principal] | None = None
) -> type[BaseHTTPRequestHandler]:
    keys = api_keys if api_keys is not None else load_api_keys()
    target = str(db_path)

    def open_db() -> Any:
        return connect(target)

    class Handler(BaseHTTPRequestHandler):
        server_version = "agentops/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _query(self) -> dict[str, str]:
            qs = parse_qs(urlparse(self.path).query)
            return {k: v[0] for k, v in qs.items() if v}

        def _principal(self) -> Principal | None:
            return authenticate(self.headers, keys)

        def _filter_kwargs(self, principal: Principal | None) -> dict[str, Any]:
            q = self._query()
            out: dict[str, Any] = {}
            for key in (
                "project",
                "agent",
                "environment",
                "status",
                "started_after",
                "started_before",
            ):
                if key in q:
                    out[key] = q[key]
            if "limit" in q:
                out["limit"] = int(q["limit"])
            if "offset" in q:
                out["offset"] = int(q["offset"])
            out["project"] = scope_project_filter(
                principal, out.get("project")
            )
            return out

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            try:
                if path == "/":
                    body = PAGE_HTML.encode("utf-8")
                    self._send(200, body, "text/html; charset=utf-8")
                    return
                principal = self._principal()
                conn = open_db()
                try:
                    if path == "/api/runs":
                        rows = list_runs(
                            conn, **self._filter_kwargs(principal)
                        )
                        status, body, ctype = _json_bytes(rows)
                    elif path == "/api/runs/summary":
                        kw = self._filter_kwargs(principal)
                        kw.pop("limit", None)
                        kw.pop("offset", None)
                        status, body, ctype = _json_bytes(
                            summarize_runs(conn, **kw)
                        )
                    elif path == "/api/failures":
                        kw = self._filter_kwargs(principal)
                        kw.pop("status", None)
                        kw.pop("offset", None)
                        status, body, ctype = _json_bytes(
                            list_tool_failures(conn, **kw)
                        )
                    elif path.startswith("/api/runs/"):
                        run_id = path[len("/api/runs/") :]
                        detail = get_run(conn, run_id)
                        if detail is None:
                            status, body, ctype = _json_bytes(
                                {"error": "not found"}, 404
                            )
                        elif principal is not None:
                            try:
                                principal.require_project(detail.get("project"))
                                status, body, ctype = _json_bytes(detail)
                            except AuthError:
                                status, body, ctype = _json_bytes(
                                    {"error": "not found"}, 404
                                )
                        else:
                            status, body, ctype = _json_bytes(detail)
                    else:
                        status, body, ctype = _json_bytes(
                            {"error": "not found"}, 404
                        )
                finally:
                    conn.close()
            except AuthError as exc:
                status, body, ctype = _json_bytes({"error": str(exc)}, 401)
            except Exception as exc:  # noqa: BLE001
                status, body, ctype = _json_bytes({"error": str(exc)}, 500)
            self._send(status, body, ctype)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path != "/api/runs":
                status, body, ctype = _json_bytes({"error": "not found"}, 404)
                self._send(status, body, ctype)
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                principal = self._principal()
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise IngestError("body must be a JSON object")
                if principal is not None:
                    principal.require_project(payload.get("project"))
                conn = open_db()
                try:
                    run_id = ingest_run(conn, payload)
                finally:
                    conn.close()
                status, body, ctype = _json_bytes({"id": run_id}, 201)
            except AuthError as exc:
                status, body, ctype = _json_bytes({"error": str(exc)}, 401)
            except IngestError as exc:
                status, body, ctype = _json_bytes({"error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                status, body, ctype = _json_bytes({"error": str(exc)}, 500)
            self._send(status, body, ctype)

    return Handler


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    db_path: Path | str = DEFAULT_DB,
    api_keys: dict[str, Principal] | None = None,
) -> ThreadingHTTPServer:
    keys = api_keys if api_keys is not None else load_api_keys()
    if host not in LOOPBACK_HOSTS and not keys:
        raise ValueError(
            "non-loopback bind requires API keys "
            "(AGENTOPS_API_KEYS or AGENTOPS_API_KEYS_PATH)"
        )
    # Keep DSN strings intact (Path() mangles postgresql:// on Windows).
    handler = make_handler(db_path, keys)
    server = ThreadingHTTPServer((host, port), handler)
    return server


def main() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="agent-operations local server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--db",
        default=os.environ.get("AGENTOPS_DATABASE_URL") or str(DEFAULT_DB),
        help="SQLite path or postgresql:// DSN (env AGENTOPS_DATABASE_URL)",
    )
    args = parser.parse_args()
    server = serve(args.host, args.port, args.db)
    print(f"agent-operations on http://{args.host}:{args.port}  db={args.db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
