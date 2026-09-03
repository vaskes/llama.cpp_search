# HUMAN_OPS — Runbook for llama.cpp_search

Это runbook для **разворачивания** на новой машине или **диагностики** на текущей.

## Что здесь

- [Hardware requirements](#hardware-requirements)
- [Установка с нуля](#установка-с-нуля)
- [Подключение MCP к твоему llama-server](#подключение-mcp-к-твоему-llama-server)
- [Диагностика](#диагностика)
- [Troubleshooting](#troubleshooting)

## Hardware requirements

| Tier       | RAM    | GPU                | Models supported                          |
| ---------- | ------ | ------------------ | ----------------------------------------- |
| Minimum    | 16 GB  | none               | Qwen3-14B Q4, Qwen3-8B Q4                 |
| Recommended| 32 GB  | none               | Qwen3-27B Q4, Ornith-35B Q4 (32K ctx)     |
| Full       | 64+ GB | NVIDIA 24+ GB VRAM | Any model, full 512K context, fast        |

> ⚠️ **Не запускай Ornith 35B Q8 на 512K context на машине с < 256 GB RAM.** OOM-kill.

## Установка с нуля

### 1. Базовый софт

```bash
# Ubuntu 24.04
sudo apt update && sudo apt install -y python3 python3-venv nodejs npm git docker.io

# Node 20+ (Playwright MCP требует)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Docker Compose v2 (включён в docker.io 24+)
docker compose version
```

### 2. llama.cpp

```bash
git clone https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp
cd /opt/llama.cpp
cmake -B build && cmake --build build --config Release -j
```

GGUF модели → `/opt/models/`.

### 3. llama.cpp_search

```bash
git clone https://github.com/vaskes/llama.cpp_search.git /opt/search
cd /opt/search
python3 -m venv venv
./venv/bin/pip install mcp openai httpx
npm install @playwright/mcp
```

### 4. SearXNG

```bash
cd /opt/search/docker
docker compose up -d
sleep 10
curl -s "http://localhost:8888/search?q=test&format=json" | head -c 200
```

Для автостарта после ребута:
```bash
sudo tee /etc/systemd/system/searxng-compose.service > /dev/null <<'EOF'
[Unit]
Description=SearXNG metasearch engine (docker compose)
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=true
WorkingDirectory=/opt/search/docker
ExecStartPre=-/usr/bin/docker compose down
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now searxng-compose.service
```

## Подключение MCP к твоему llama-server

У тебя уже есть свой `llama-ornith.service` (или `llama-qwen38.service`, и т.д.). Чтобы добавить web search:

```bash
sudo systemctl edit llama-ornith.service
```

В открывшемся editor добавь (или в основной `[Service]` секции):

```ini
[Service]
ExecStart=
ExecStart=/opt/llama.cpp/build/bin/llama-server \
  --model /opt/models/Ornith-1.5-35B-A3B-Q8_0.gguf \
  --mmproj /opt/models/mmproj-Ornith-1.5-35B-A3B-bf16.gguf \
  --jinja \
  --agent \
  --mcp-servers-config /opt/search/mcp-servers.json \
  --port 8080 \
  ...твои остальные флаги...
```

Ключевое: добавлены **только три** строчки:
- `--jinja` (обязательно для tool calling)
- `--agent` (включает MCP прокси)
- `--mcp-servers-config /opt/search/mcp-servers.json` (подключает SearXNG + Playwright)

```bash
sudo systemctl daemon-reload
sudo systemctl restart llama-ornith.service
journalctl -u llama-ornith.service -n 20 | grep "MCP"
#  srv  start: MCP warmup: 'searxng' discovered 3 tools
#  srv  start: MCP warmup: 'playwright' discovered 24 tools
#  srv  setup: Added 27 MCP tools
```

## Диагностика

### Проверить что SearXNG работает

```bash
curl -s "http://localhost:8888/search?q=python&format=json" | jq '.results | length'
# должно быть > 0
```

### Проверить что MCP подключены

```bash
curl -s http://localhost:8080/tools | jq 'length'
# 27

curl -s http://localhost:8080/tools | jq '.[] | .name' | head
# "search"
# "engines"
# "fetch_url"
# "browser_navigate"
# ...
```

### Проверить tool calling работает

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ornith-1.5-35B-A3B",
    "messages": [{"role":"user","content":"What is the weather in Tokyo? Use the tool."}],
    "tools": [{
      "type":"function",
      "function": {
        "name":"get_weather",
        "description":"Get current weather",
        "parameters":{"type":"object","properties":{"city":{"type":"string"}}}
      }
    }],
    "max_tokens": 500
  }' | jq '.choices[0].message.tool_calls[0].function'
```

Должно вернуть что-то вроде:
```json
{
  "name": "get_weather",
  "arguments": "{\"city\":\"Tokyo\"}"
}
```

## Troubleshooting

### llama-server не поднимает MCP

`journalctl -u llama-ornith` показывает `MCP warmup`?
- **Нет** — флаг `--agent` забыт или модель не с `--jinja`
- **Есть, но 0 tools** — `mcp-servers.json` неверный. Проверь синтаксис: `python3 -c "import json; print(json.load(open('/opt/search/mcp-servers.json')))"`

### SearXNG возвращает 0 результатов

API-движки должны работать всегда. Если 0:
- `docker logs searxng | tail -20` — может быть network error
- Проверь `curl "http://localhost:8888/engines"` — список активных движков

### Playwright MCP отказывается стартовать

- "Playwright requires Node.js 20" → установи Node 20+
- Браузер не запускается → добавь `--no-sandbox` в args

### `Restart=on-failure` лупит в loop

См. `docs/RESTART_GOTCHA.md`. Если два llama-сервиса дерутся за 8080 — `Restart=Prevent` или `Restart=no`.

### Tool call returns isError=True

Смотри `agent.log` или journal llama-server. Обычно:
- SearXNG вернул error → `curl "http://localhost:8888/..."` руками
- Playwright не смог открыть URL → другая страница

### model responds but ignores tools

- Модель не поддерживает tool calling (нужна Qwen3, Llama-3.x, Mistral, и т.д.)
- `--jinja` забыт → chat template не рендерит tools

## Backup and recovery

Всё что нужно для recovery:
- `/opt/search/` — код
- `/opt/llama.cpp/build/` — бинарь
- `/opt/models/` — GGUF файлы
- `/etc/systemd/system/llama-*.service` — твои юниты (НЕ перезаписывай чужие!)

Переустановка на новой машине:
```bash
rsync -av /opt/search/ newhost:/opt/search/
rsync -av /opt/models/ newhost:/opt/models/  # долго если большие
# на новой машине: поставить llama.cpp + SearXNG + добавить --mcp-servers-config
```
