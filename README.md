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
| Path | Purpose |
|------|---------|
| `src/mcp_donsetch_stdio.py` | The stdIO bridge. Spawned by `llama-server --mcp-servers-config`. Forwards JSON-RPC to donsetch-http at 127.0.0.1:8765/mcp. |
| `src/agent.py` | Test client: a small tool-calling agent loop that talks to llama-server's OpenAI-compat endpoint and the MCP shim. Used for ad-hoc smoke tests; production goes through llama-server's `--mcp-servers-config`. |
| `mcp-servers.json` | stdIO MCP config: declares the single MCP server (the shim) with its absolute path. Read by `llama-server --mcp-servers-config`. |
| `docs/DONSETCH.md` | Per-tool reference for the 4 tools (`web_search`, `web_fetch`, `web_crawl`, `web_screenshot`): parameters, return shape, error semantics, version pinning. |
| `docs/DONSETCH_DEPLOY.md` | Step-by-step deploy of donsetch-http: prereqs, clone, build, run, verify, "what you can break". |
| `docs/deploy_donsetch.sh` | The deploy script referenced by `DONSETCH_DEPLOY.md`. One-shot. |
| `docs/QUICKSTART.md` | 5-minute end-to-end walk from clean host to first search. |
| `docs/HUMAN_OPS.md` | Operator notes: restart cycle, systemd pitfalls, backup, sanity checks, escalation paths. |
| `docs/RESTART_GOTCHA.md` | Why `Restart=on-failure` is dangerous for heavy llama services. |
| `tests/test_shim_smoke.py` | 5 subprocess-driven tests against the live donsetch-http (skipped if unreachable). |
| `package.json` | Minimal manifest: `scripts.test` and an empty `dependencies`. There is no Playwright dep, no `package-lock.json`, no Node code in this repo. |
| `LICENSE` | Custom Kuduza Ai Lab license: public visibility, no grant of rights, no ML training, Russian jurisdiction. |
| `CHANGELOG.md` | Per-release Added/Changed/Fixed. Semantic versioning. |

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
