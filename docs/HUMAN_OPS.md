# HUMAN_OPS — operator notes for the stdIO bridge

This doc covers running the stdIO bridge (`mcp_donsetch_stdio.py`)
and the upstream `donsetch-http` MCP server in production. The
target host is the operator's `llmhost2`. Most sections assume
docker compose v2 and Ubuntu 24.04.

## What runs where

| Process | Where | Started by |
|---------|-------|------------|
| `donsetch-http` | `/opt/hound`, container `donsetch-http` | docker compose (profile http) |
| stdIO bridge | spawned by llama-server per request | `--mcp-servers-config` flag |
| `llama-ornith.service` | systemd | operator (manual) |
| Telegram bot | `/opt/telegram-bot` container | docker compose |

## Restart cycle (in order)

1. `cd /opt/hound && git pull && docker compose --profile http up -d`
   — pulls newer donsetch, rebuilds image, restarts container.
   Wait 5s, then `curl http://127.0.0.1:8765/health`.
2. `sudo systemctl restart llama-ornith.service` — picks up the
   new stdIO bridge if you changed the shim, otherwise no-op.
3. `cd /opt/telegram-bot && sudo docker compose up -d --build` —
   picks up bot changes.

## Why `Restart=on-failure` is dangerous here

`Restart=on-failure` + `RestartSec=10` is a footgun for llama
services: if one crashes, systemd loops the restart. With two
`llama-*.service` units both configured that way, a single
crash on port 8080 leads to two services fighting for the port
and the loop never breaks.

**Recommendation:** `Restart=no` (or omit the line). Manual
restart is fine for a single-user bot. If you really want
auto-restart, use `Restart=on-success` with a long
`RestartSec=600` (10 min) — the model is heavy to load and a
restart loop is worse than a brief outage.

## Backup

The repo is on GitHub (private). For local safety:
- `git bundle create /opt/backups/llama.cpp_search.bundle --all`
  before any risky `git filter-repo` or mass-rewrite pass.
- `tar czf /opt/backups/llama.cpp_search.tar.gz /opt/llama.cpp_search`
  captures uncommitted local edits (e.g. mcp-servers.json
  override).

Both go to the `/opt/mavis-backups` volume.

## Sanity checks

```bash
# 1. donsetch alive
curl -sS http://127.0.0.1:8765/health
# 2. donsetch MCP transport responsive
curl -sS -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["result"]["tools"]))'
# expect: 4
# 3. stdIO shim still parses
python3 -c 'import ast; ast.parse(open("/opt/llama.cpp_search/src/mcp_donsetch_stdio.py").read())'
# 4. shim smoke test
cd /opt/llama.cpp_search && python3 tests/test_shim_smoke.py
# expect: Ran 5 tests in ... OK
```

## When to escalate

- donsetch logs are full of `degraded: true` for a single
  engine: that's one search engine blocking the operator's IP.
  Add a different engine or change egress — don't wait for
  every engine to fail.
- shim smoke test fails on `test_03_web_search_real_query` with
  timeout: the network is the bottleneck, not the shim. Check
  the upstream `donsetch-http` container for the actual
  network call stack.
- llama-server logs are full of `MCP warmup: 0 tools`: the shim
  crashed at startup. `sudo journalctl -u llama-ornith -n 50`
  for the Python traceback.
