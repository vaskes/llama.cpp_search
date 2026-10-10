# llama.cpp_search — thin shim around donsetch-http

> **Historical note (2026-10).** This repo started as a
> SearXNG + Playwright MCP stack. That approach is dead: every
> keyless search engine CAPTCHA-blocks Russian IPs through
> SearXNG proxies, and Bing-by-Playwright gave marketing
> garbage instead of real results.
>
> The working stack is now
> **[donsetch-http](https://github.com/dondai44423/donsetch)** —
> a Rust MCP server with built-in tier-2 headless browser that
> aggregates 6 keyless engines (Bing, DDG, Mojeek, Yahoo, Brave,
> Google) and solves CAPTCHAs with a real browser. It is
> deployed at `/opt/hound` and exposed on port 8765.
>
> This repo is now a thin shim: it provides the stdIO wrapper
> that lets llama.cpp's `--mcp-servers-config` talk to
> donsetch-http, plus a `deploy_donsetch.sh` for fresh installs.
> See `docs/DONSETCH_DEPLOY.md` for the actual deploy steps.
>
> **TODO 2026-12:** archive this repo. The two files that matter
> (`src/mcp_donsetch_stdio.py`, `mcp-servers.json`) can move into
> the donsetch repo or the operator's dotfiles; the rest is
> history. After the archive, the GitHub link from
> `vaskes/llama.cpp_telegram` should switch to a docs page in
> donsetch or the operator's wiki.

## What this repo contains now

| Path | Status | What it is |
|------|--------|------------|
| `mcp-servers.json` | ✅ | stdIO config for `llama.cpp --mcp-servers-config` |
| `src/mcp_donsetch_stdio.py` | ✅ | stdIO wrapper: forwards MCP calls to donsetch-http at `127.0.0.1:8765` |
| `src/agent.py` | ✅ | OpenAI-compatible tool-calling test client |
| `docs/deploy_donsetch.sh` | ✅ | One-shot deploy script for fresh installs |
| `docs/DONSETCH_DEPLOY.md` | ✅ | Full deploy walkthrough |
| `docs/QUICKSTART.md` | ✅ | 5-minute setup |
| `docs/HUMAN_OPS.md` | ✅ | Operator notes |
| `docs/AGENT_GUIDE.md` | ✅ | Notes for AI agents working on this stack |
| `docs/AGENT_PROMPT.md` | ✅ | Snippet to paste into agent tasks |
| `docs/RESTART_GOTCHA.md` | ✅ | Things to know about restarts |
| `package.json` + `package-lock.json` | ✅ | Playwright dependency (used by stdIO wrapper for browser fallback) |
| `deprecated/docker-searxng/` | ❌ | Old SearXNG compose file. **Does not work** — engines block RU IPs. Kept for history. |
| `deprecated/playwright_search_proxy.py` | ❌ | Old Bing-via-Playwright proxy. Replaced by donsetch's built-in browser. Kept for history. |

## Quickstart (donsetch stack)

The full working setup is in `docs/DONSETCH_DEPLOY.md`. TL;DR:

\`\`\`bash
# 1. Deploy donsetch-http (Rust MCP, listens on 8765)
cd /opt/hound && git pull && docker compose --profile http up -d

# 2. Point llama.cpp at the stdIO wrapper
#    (mcp-servers.json in this repo is the config)
llama-server --mcp-servers-config /opt/llama.cpp_search/mcp-servers.json ...

# 3. Verify
curl http://127.0.0.1:8765/mcp -X POST -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
\`\`\`

## Why this repo is still here

Three reasons:
1. The `src/mcp_donsetch_stdio.py` wrapper is the only piece that
   depends on llama.cpp's stdIO-MCP convention; the upstream
   donsetch project only ships the HTTP server.
2. `docs/deploy_donsetch.sh` is the single-file install recipe
   that operators actually run.
3. Historical context — every commit in `git log` documents the
   migration path, and newcomers often want to see "why not just
   SearXNG" answered.

Once those three things move into a maintained location
(operator's dotfiles repo, or the donsetch upstream), this repo
is archive-only.
