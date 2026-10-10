# llama.cpp_search — stdIO bridge to donsetch-http

> Personal deploy of the stdIO wrapper that lets
> `llama.cpp --mcp-servers-config` talk to
> [donsetch-http](https://github.com/dondai44423/donsetch) at
> `127.0.0.1:8765`. donsetch does the actual work; this repo
> only exists because llama.cpp's stdIO-MCP convention needs
> a small Python wrapper that speaks the right framing.

## Files

| Path | What it is |
|------|------------|
| `mcp-servers.json` | stdIO config for `llama.cpp --mcp-servers-config` |
| `src/mcp_donsetch_stdio.py` | stdIO wrapper: forwards MCP calls to donsetch-http |
| `src/agent.py` | OpenAI-compatible tool-calling test client |
| `docs/deploy_donsetch.sh` | One-shot deploy script for fresh installs |
| `docs/DONSETCH_DEPLOY.md` | Full deploy walkthrough |
| `docs/QUICKSTART.md` | 5-minute setup |
| `docs/HUMAN_OPS.md` | Operator notes |
| `docs/AGENT_GUIDE.md` | Notes for AI agents working on this stack |
| `docs/AGENT_PROMPT.md` | Snippet to paste into agent tasks |
| `docs/RESTART_GOTCHA.md` | Things to know about restarts |
| `package.json` + `package-lock.json` | Playwright dep (kept for the stdIO wrapper's browser fallback) |
| `deprecated/playwright_search_proxy.py` | Old Bing-via-Playwright proxy, kept for history. Safe to delete. |

## Quickstart

See `docs/DONSETCH_DEPLOY.md`. TL;DR:

```bash
# 1. Deploy donsetch-http (Rust MCP, listens on 8765)
cd /opt/hound && git pull && docker compose --profile http up -d

# 2. Point llama.cpp at the stdIO wrapper
llama-server --mcp-servers-config /opt/llama.cpp_search/mcp-servers.json ...

# 3. Verify
curl http://127.0.0.1:8765/mcp -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Why this repo still exists

Two files (`src/mcp_donsetch_stdio.py` and `mcp-servers.json`)
are the only thing that depends on llama.cpp's stdIO-MCP
convention. When donsetch upstream ships a stdIO variant (or
this whole thing moves into operator dotfiles), the repo can
go private or be deleted.
