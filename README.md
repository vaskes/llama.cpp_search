# llama.cpp_search

Web search + page reading для **любой llama.cpp с tool-calling моделью** через два MCP-сервера:
- 🔍 **SearXNG** (self-hosted, JSON API) → MCP мост → `search/engines/fetch_url` tools
- 📄 **@playwright/mcp** (Microsoft official) → 24 browser tools

Стек собирается из четырёх кусков:

```
                    llama.cpp server
                    (--jinja --agent --mcp-servers-config)
                            │
              ┌─────────────┴─────────────┐
              ▼                            ▼
   ┌──────────────────┐         ┌──────────────────────┐
   │ mcp_searxng_     │         │ @playwright/mcp      │
   │ server.py        │         │  (Node 20 stdio)     │
   └────────┬─────────┘         └─────────┬────────────┘
            ▼                              ▼
      SearXNG :8888                 Chromium (headless)
```

## Quick start

### 1. Поднять SearXNG (Docker)

```bash
cd /opt/search/docker
docker compose up -d
sleep 8
curl -s "http://localhost:8888/search?q=test&format=json" | head -c 200
```

### 2. Поставить Python MCP зависимости

```bash
python3 -m venv /opt/search/venv
/opt/search/venv/bin/pip install mcp openai httpx
```

### 3. Поставить Playwright MCP (Node ≥20)

```bash
cd /opt/search
npm install @playwright/mcp
# Node 20+ обязателен (Node 18 отвергается плагином)
```

### 4. Подключить MCP к llama-server

Добавь в свой `llama-server` (тот, что у тебя уже есть в `/etc/systemd/system/llama-*.service`) **два флага**:

```bash
--jinja
--mcp-servers-config /opt/search/mcp-servers.json
```

Конкретный пример для `llama-ornith.service`:

```ini
[Service]
ExecStart=/opt/llama.cpp/build/bin/llama-server \
  --model /opt/models/Ornith-1.5-35B-A3B-Q8_0.gguf \
  --mmproj /opt/models/mmproj-Ornith-1.5-35B-A3B-bf16.gguf \
  --jinja \
  --agent \                                    # ← включает MCP-инструменты
  --mcp-servers-config /opt/search/mcp-servers.json \   # ← SearXNG + Playwright
  --ctx-size 32768 \
  --port 8080 \
  ...
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart llama-ornith
journalctl -u llama-ornith | grep "MCP warmup"
#  srv  start: MCP warmup: 'searxng' discovered 3 tools
#  srv  start: MCP warmup: 'playwright' discovered 24 tools
#  srv  setup: Added 27 MCP tools
```

### 5. Использовать из любого OpenAI-клиента

```bash
# curl
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ornith-1.5-35B-A3B",
    "messages": [{"role":"user","content":"Find recent arXiv papers on Mamba"}],
    "tools": [...],
    "max_tokens": 1500
  }'
```

Чтобы узнать **список tools** без чтения исходников:

```bash
curl http://localhost:8080/tools | jq
```

### 6. Если у тебя нет своего клиента — есть готовый `agent.py`

```bash
/opt/search/venv/bin/python /opt/search/src/agent.py "Find recent arXiv papers on Mamba"
# Ответ в stdout и в /opt/search/logs/last_answer.md
```

`agent.py` — это standalone Python-клиент, который:
1. Подключается к `http://localhost:8080/v1/chat/completions`
2. Получает список tools из `/tools` endpoint
3. Делает tool-calling loop до final answer
4. Логирует всё в `/opt/search/logs/agent.log`

**Альтернатива:** LM Studio, Open WebUI, Jan, или любой MCP-aware клиент тоже работают с теми же 27 tools.

---

## Что в репе

| Path                          | Что это                                              |
| ----------------------------- | ---------------------------------------------------- |
| `mcp-servers.json`            | MCP-конфиг для `--mcp-servers-config`                |
| `src/mcp_searxng_server.py`   | MCP-мост к SearXNG (3 tools: search/engines/fetch_url) |
| `src/agent.py`                | Standalone tool-calling клиент (нужен если нет своего) |
| `bin/playwright-mcp`          | Wrapper для @playwright/mcp (Node 20)                |
| `docker/docker-compose.yml`   | SearXNG container                                     |
| `docker/searxng/settings.yml` | SearXNG конфиг (engines без captcha)                 |
| `docs/AGENT_PROMPT.md`        | Копипастить в задание агенту                         |
| `docs/AGENT_GUIDE.md`         | Полная инструкция для LLM-агента                     |
| `docs/HUMAN_OPS.md`           | Runbook для человека                                 |
| `docs/RESTART_GOTCHA.md`      | Грабли с `Restart=on-failure`                        |

---

## Используемые движки SearXNG

API-based движки, не капчатят self-hosted:
- wikipedia, arxiv, github, wikidata
- openalex, semantic scholar, pubmed, crossref

Капчащие (DDG/Startpage/Mojeek) **отключены** в `docker/searxng/settings.yml`. Для общего web — Playwright.

---

## Грабли

- **`--jinja` обязателен** — без него tools не рендерятся в chat template
- **Node ≥20** для @playwright/mcp (Node 18 отвергается). Если есть `/opt/node20/`, используй его
- **Движки SearXNG капчатят** от server IP. Используй API-движки либо Playwright
- **`Restart=on-failure` лупит** в loop если порт занят (см. `docs/RESTART_GOTCHA.md`)
- **reasoning модели** (Ornith) сжигают max_tokens на `reasoning_content`. Ставь `max_tokens ≥ 500`

---

## Replicating on a new host

```bash
git clone https://github.com/vaskes/llama.cpp_search.git /opt/search
cd /opt/search
python3 -m venv venv && ./venv/bin/pip install mcp openai httpx
npm install @playwright/mcp
cd docker && docker compose up -d
```

Потом в свой llama-*.service добавь:
```ini
--jinja
--mcp-servers-config /opt/search/mcp-servers.json
```

Подробнее — `docs/HUMAN_OPS.md`.
