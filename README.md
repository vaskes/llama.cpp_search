# llama.cpp_search

A complete web-search + page-reading toolchain for **naked llama.cpp**.

Give any tool-capable local model the ability to:

- 🔍 **Search the web** via self-hosted [SearXNG](https://github.com/searxng/searxng)
- 📄 **Read web pages** via [@playwright/mcp](https://github.com/microsoft/playwright-mcp) (or fallback `httpx` HTML parser)
- 🛠️ **Call both as MCP tools** that llama.cpp's OpenAI-compat layer accepts

Includes a model-agnostic `systemd` unit, a Python tool-calling agent, and everything needed to reproduce on another host.

---

## Architecture

```
        ┌──────────────────────┐
user ──▶│ agent.py (Python)    │  ──▶ llama.cpp server (OpenAI-compat :8080)
        │   ↳ tool-calling loop│         ↑
        └────┬─────────────────┘         │ tool_choice=auto
             │ MCP (stdio)               │ jinja template
   ┌─────────┴──────────┐
   ▼                    ▼
┌─────────────┐  ┌────────────────────┐
│ SearXNG MCP │  │ @playwright/mcp    │
│  (Python)   │  │   (Node, headless) │
└──────┬──────┘  └─────────┬──────────┘
       │                  │
       ▼                  ▼
 SearXNG (Docker :8888)  Chromium (headless)
```

Three components talk to each other:

1. **llama.cpp** serves the model on `:8080` (must support tool calling — set `--jinja`).
2. **SearXNG MCP** (`mcp_searxng_server.py`) is a Python MCP server that proxies SearXNG's JSON API. Exposes tools: `search`, `engines`, `fetch_url`.
3. **Playwright MCP** (`@playwright/mcp`) is Microsoft's official MCP server. Exposes ~25 browser tools: `browser_navigate`, `browser_snapshot`, `browser_evaluate`, etc.
4. **agent.py** boots all three as stdio MCP servers, lists their tools, and loops: prompt → model → tool_calls → MCP results → model → ... until final answer.

---

## Quick start

### 1. Prerequisites

- Linux host with ≥16 GB RAM (32 GB recommended for 27B+ models)
- Python ≥ 3.11
- Node.js ≥ 20 (Playwright MCP refuses to run on Node 18)
- Docker + Compose v2
- llama.cpp already built and reachable (default: `http://localhost:8080`)

### 2. Run the stack

```bash
# 1. Start SearXNG (port 8888)
cd docker && docker compose up -d

# 2. Start llama.cpp with --jinja (see systemd/ for our model-agnostic unit)
sudo systemctl start llama

# 3. Use the agent
cd ..
./venv/bin/python src/agent.py "What is the capital of France?"
./venv/bin/python src/agent.py "Find recent arXiv papers on Mamba architectures"
./venv/bin/python src/agent.py "Open https://example.com and tell me what's on it"
```

The agent logs every tool call to `logs/agent.log` and saves the final answer to `logs/last_answer.md`.

### 3. Switch the model

The `llama.service` unit is **model-agnostic** — all parameters come from `/etc/default/llama-server`. To switch:

```bash
sudo cp systemd/presets/llama-qwen38-q4.env /etc/default/llama-server
sudo systemctl restart llama
```

Presets included:
- `llama-ornith.env` — original Ornith 35B at 512K ctx (needs ≥256 GB RAM or GPU)
- `llama-ornith-32k.env` — same model, 32K ctx, fits in 58 GB
- `llama-qwen38-q4.env` — Qwen3.8-27B Q4_K_M, lighter weight

See `systemd/presets/` for full list. Create your own `.env` file with the same variables.

---

## Files

| Path                          | What it is                                                |
| ----------------------------- | --------------------------------------------------------- |
| `src/agent.py`                | Tool-calling agent loop (model + MCP servers)             |
| `src/mcp_searxng_server.py`   | MCP server bridging agent ↔ SearXNG                       |
| `docker/docker-compose.yml`   | SearXNG container                                         |
| `docker/searxng/settings.yml` | SearXNG config (engines, formats, bot detection)          |
| `systemd/llama.service`       | Model-agnostic unit (installed to `/etc/systemd/system/`) |
| `systemd/presets/*.env`       | Model presets for `/etc/default/llama-server`             |
| `docs/AGENT_GUIDE.md`         | Instructions for an LLM agent to use this stack           |
| `docs/HUMAN_OPS.md`           | Operations / troubleshooting runbook                      |

---

## How the tool calling works

1. Agent collects MCP tools from both servers (27 in total).
2. Each MCP tool schema is converted to OpenAI's `function` format. We **strip `$schema` and `additionalProperties`** from the input schema — llama.cpp's OpenAI-compat layer rejects them.
3. We send `chat.completions.create(messages=..., tools=[...], tool_choice="auto")`.
4. When the model returns `tool_calls`, we look up the owning MCP session and call the tool.
5. We append the result as a `role: "tool"` message and loop.

> **Why a custom agent loop instead of using llama-server's `--agent`?**
> The built-in `--agent` mode requires a single MCP endpoint configured at server start. Our loop is portable — works with any llama-server, lets you add/remove MCP servers, and gives full control over iteration limits and logging.

---

## Known gotchas

- **SearXNG bot detection** blocks DuckDuckGo, Startpage, Mojeek from server IPs. The config in this repo enables API-based engines (Wikipedia, arXiv, GitHub, OpenAlex, Crossref, PubMed, Wikidata, Semantic Scholar) that don't captcha-block. For broader web search, use a proxy or a public SearXNG instance.
- **llama.cpp 0.3.0-dev** supports reasoning models (the response includes a `reasoning_content` field). Set `max_tokens ≥ 500` to leave room for thinking + answer.
- **MCP tool schemas** often include `"$schema"` and `"additionalProperties": false`. Strip them before sending to llama.cpp.
- **Playwright MCP** requires Node.js ≥ 20. We install `@playwright/mcp@latest` in this repo; chromium is downloaded on first `browser_navigate`.

---

## Replicating on a new host

See `docs/HUMAN_OPS.md` for step-by-step reproduction.
