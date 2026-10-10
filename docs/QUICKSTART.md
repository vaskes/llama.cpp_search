# Quickstart — 5 minutes to a working search

The full path is in [DONSETCH_DEPLOY.md](DONSETCH_DEPLOY.md). TL;DR:

```bash
# 1. Deploy donsetch-http (Rust MCP, listens on 8765)
bash /opt/llama.cpp_search/docs/deploy_donsetch.sh

# 2. Verify
curl http://127.0.0.1:8765/health
curl -sS -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print([t["name"] for t in d["result"]["tools"]])'
# expect: ['web_crawl', 'web_fetch', 'web_screenshot', 'web_search']

# 3. Wire into llama-server
#    mcp-servers.json in this repo is the config — point llama at it
#    via --mcp-servers-config /opt/llama.cpp_search/mcp-servers.json
sudo systemctl restart llama-ornith.service

# 4. Verify from the LLM
curl -sS http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"Qwen3.8-27B-Ultra-Heretic-MTP-256k",
    "messages":[{"role":"user","content":"Find MikroTik PBR configuration example"}],
    "tools":[{"type":"function","function":{
      "name":"web_search","description":"search",
      "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}
    }}]
  }' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["choices"][0]["finish_reason"])'
# expect: tool_calls
```

## What you get

- 4 MCP tools over stdIO: `web_search`, `web_fetch`, `web_crawl`, `web_screenshot`
- Search aggregated over Bing, DDG, Mojeek, Yahoo, Brave, Google
- No API keys, no CAPTCHA (tier-2 browser escalation in donsetch)
- Works on RU datacenter IPs (the old SearXNG stack didn't)

If something breaks, see [HUMAN_OPS.md](HUMAN_OPS.md) → Sanity
checks first.
