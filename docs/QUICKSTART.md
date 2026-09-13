# Quickstart — 5 минут до работающего поиска

## TL;DR

```bash
# 1. Deploy donsetch-http (Rust MCP server с Playwright)
bash /opt/search/docs/deploy_donsetch.sh

# 2. Добавить в /opt/search/mcp-servers.json (уже есть):
#    {
#      "donsetch": {
#        "command": "/opt/search/venv/bin/python",
#        "args": ["/opt/search/src/mcp_donsetch_stdio.py"],
#        "env": {"DONSETCH_URL": "http://127.0.0.1:8765/mcp"}
#      }
#    }

# 3. Добавить в ExecStart llama-ornith.service:
#    --mcp-servers-config /opt/search/mcp-servers.json

# 4. systemctl restart llama-ornith

# 5. Тест:
curl -sS http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"Ornith-1.5-35B-A3B-Uncensored\",\"messages\":[{\"role\":\"user\",\"content\":\"Find MikroTik PBR configuration example\"}],\"max_tokens\":1500}"
```

## Что ты получишь

- 4 tools через stdIO MCP: `web_search`, `web_fetch`, `web_crawl`, `web_screenshot`
- Поиск через 6 движков без CAPTCHA (Bing, DDG, Mojeek, Yahoo, Brave, Google)
- Без API ключей
- Работает на российском IP (где SearXNG-based стек уже мёртв)

## Troubleshooting за 30 секунд

```bash
# Проверить что donsetch-http жив
curl -sS http://127.0.0.1:8765/health

# Проверить что llama видит tools
journalctl -u llama-ornith | grep "MCP warmup"

# Проверить что open-webui видит tools (если используется)
sqlite3 /opt/agent-workspace/.open-webui-data/webui.db \
  "SELECT value FROM config WHERE key=\"tool_server.connections\";"
```

Если что-то не работает — читай полную инструкцию в [DONSETCH_DEPLOY.md](DONSETCH_DEPLOY.md).
