# DONSETCH_DEPLOY.md

Step-by-step deployment of the [donsetch](https://github.com/dondai44423/donsetch)
HTTP MCP server and its stdIO bridge to `llama.cpp`.

For a fully automated version, run
[`docs/deploy_donsetch.sh`](deploy_donsetch.sh) instead — this
doc explains what it does and why.

## Prerequisites

- Linux host with Docker Engine + Docker Compose v2
- `git`, `curl`, `python3.10+` (only for the stdIO shim)
- ~2 GB free disk for the `donsetch-mcp` image
- A running `llama-server` you can restart (the final step touches
  its `--mcp-servers-config` flag)

## What you'll end up with

After all steps:

- `donsetch-mcp:latest` image built and tagged locally
- `donsetch-http` container running on `0.0.0.0:8765` (loopback
  is fine if only the same host needs it; the patch in step 4
  widens the bind so other containers on the same host can reach
  it too)
- The stdIO shim `src/mcp_donsetch_stdio.py` running under
  llama-server's `--mcp-servers-config` flag, exposing 4 tools to
  the model: `web_search`, `web_fetch`, `web_crawl`, `web_screenshot`

## Шаг 1. Pick a deploy path

The default in this doc assumes:

- donsetch source at `/opt/hound`
- listen port 8765
- the stdIO shim lives in this repo (already committed)

If you want a different layout, change the variables in step 4
and in `mcp-servers.json` together. Both are tiny.

## Шаг 2. Clone donsetch

```bash
sudo mkdir -p /opt
sudo chown $USER:$USER /opt
git clone https://github.com/dondai44423/donsetch.git /opt/hound
cd /opt/hound
```

If `/opt/hound` already exists (it does on the operator's host),
`cd /opt/hound && git pull` instead.

## Шаг 3. Build the Docker image

```bash
docker build --build-arg INSTALL_CHROME=true -t donsetch-mcp:latest .
```

This takes 2–5 minutes (Rust compile + 114 MB Chromium download).
The resulting image is ~1.2 GB.

## Шаг 4. Patch docker-compose.yml to bind 0.0.0.0:8765

The upstream compose file binds `127.0.0.1:8765:8765` (loopback
only — safe-by-default, no token auth required). The stdIO shim
in this repo still uses `127.0.0.1:8765` and works with either
binding. If you want **other containers on the same host** (the
Telegram bot in `vaskes/llama.cpp_telegram`, or the Open WebUI
sidecar) to talk to donsetch, widen the bind:

```bash
sed -i.bak "s|      - \"127.0.0.1:8765:8765\"|      - \"8765:8765\"|" docker-compose.yml
```

> If you do this, set `DONSETCH_HTTP_TOKEN` in the compose env
> before `docker compose up` — the upstream README makes this
> a hard requirement for non-loopback binds. The stdIO shim
> accepts the token via the `Authorization: Bearer` header if
> you also set `DONSETCH_TOKEN` in its env.

## Шаг 5. Start donsetch-http

```bash
docker compose --profile http up -d
sleep 5   # give the container a moment to bind
curl -sS http://127.0.0.1:8765/health
```

Expected response: `{"ok":true,"version":"..."}` or similar.

## Шаг 6. Verify the MCP transport

```bash
curl -sS -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print([t["name"] for t in d["result"]["tools"]])'
```

Expected: `['web_fetch', 'web_search', 'web_crawl', 'web_screenshot']`.

## Шаг 7. Point llama-server at the stdIO shim

Add (or merge) the `mcpServers` block from this repo's
`mcp-servers.json` into your llama-server's config dir. The
shim is a tiny Python script that proxies JSON-RPC over stdIO
to the HTTP MCP at `127.0.0.1:8765/mcp`.

For the operator's host, `llama-ornith.service` (the systemd
unit that runs `llama-server`) needs the new flag on its
ExecStart:

```bash
sudo systemctl edit llama-ornith.service
# Add under [Service]:
#   ExecStart=
#   ExecStart=/opt/llama.cpp-rocm-780m/build/bin/llama-server \
#     -m /opt/models/...gguf \
#     --port 8080 \
#     --mcp-servers-config /opt/llama.cpp_search/mcp-servers.json
#     ... (other flags you already have)
sudo systemctl daemon-reload
sudo systemctl restart llama-ornith.service
```

(The `ExecStart=` line is empty on purpose — `systemctl edit`
patches the existing ExecStart without duplicating it. Re-list
the full line with the new `--mcp-servers-config` flag.)

## Шаг 8. Verify from the model

```bash
curl -sS http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3.8-27B-Ultra-Heretic-MTP-256k",
    "messages": [{"role":"user","content":"Find MikroTik PBR configuration example"}],
    "tools": [
      {"type":"function","function":{
        "name":"web_search","description":"search",
        "parameters":{"type":"object","properties":{"query":{"type":"string"}}, "required":["query"]}
      }}
    ]
  }' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["choices"][0]["finish_reason"])'
```

Expected: `tool_calls`.

## What you can break

- **Edit `mcp-servers.json` after starting the shim.** Restart
  llama-server, not the shim (the shim has no state of its own).
- **Edit donsetch compose without `git pull`.** The `git pull`
  in step 2 is the only way new env vars / port changes get in.
  For non-trivial env changes, also rebuild the image (step 3).
- **Forget to set `DONSETCH_HTTP_TOKEN` after widening the bind.**
  The shim in this repo does not forward `Authorization` headers
  to donsetch-http by default. If you need token auth, edit
  `src/mcp_donsetch_stdio.py` to add the header.
