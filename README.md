# llama.cpp_search — deprecated (SearXNG-based) → use donsetch-http

> ⚠️ **Этот репозиторий deprecated.** SearXNG-based MCP-stack больше не работает: 
> все основные search engines (DDG, Bing, Startpage, Brave, Google через SearXNG) 
> блокируют российские IP-адреса через CAPTCHA. Ручные обходы (User-Agent spoofing, 
> прокси) дают маркетинговый мусор вместо результатов.
> 
> **Замена:** [donsetch-http](https://github.com/dondai44423/donsetch) — 
> Rust MCP server с Playwright headless Chrome (tier-2 browser escalation), 
> агрегирует 6 поисковиков (Bing, DDG, Mojeek, Yahoo, Brave, Google), 
> обходит CAPTCHA через настоящий браузер.

## Быстрый миграционный путь

Если у вас стоит старая версия этого стека с SearXNG:

```bash
cd /opt/search && git pull   # получить обновлённый README и скрипты

# 1. Остановить и удалить SearXNG
docker stop searxng && docker rm searxng

# 2. Задеплоить donsetch-http (см. docs/DONSETCH_DEPLOY.md)
bash docs/deploy_donsetch.sh

# 3. Подключить к llama.cpp через stdIO-прокси
# mcp-servers.json уже настроен правильно (см. в этом репо)

# 4. Перезагрузить llama-server
systemctl restart llama-ornith
```

После этого у вас:
- **4 tools** через donsetch: `web_search`, `web_fetch`, `web_crawl`, `web_screenshot`
- **Поиск по нишевым темам** (MikroTik PBR, Unreal Engine MCP, Juniper OSPF) — реальные результаты с финальными URL
- **Без CAPTCHA** благодаря tier-2 browser escalation в donsetch
- **Без API ключей**, полностью self-hosted

## Что устарело в этом репо

Следующие файлы **DEPRECATED** — оставлены только для истории:

| Path | Статус | Альтернатива |
|------|--------|--------------|
| `docker/docker-compose.yml` | ❌ SearXNG контейнер | НЕ нужен — donsetch-http это отдельный стек в /opt/hound/ |
| `docker/searxng/settings.yml` | ❌ SearXNG движки CAPTCHA'ятся | Используйте 6 движков donsetch |
| `docker/searxng/limiter.toml` | ❌ SearXNG rate limit bypass | Не нужно |
| `src/mcp_searxng_server.py` | ❌ SearXNG MCP мост | Заменён на `src/mcp_donsetch_stdio.py` |
| `bin/playwright-mcp` | ⚠️ Standalone Playwright MCP | Используйте встроенный browser в donsetch |
| `src/playwright_search_proxy.py` | ⚠️ Legacy Bing прокси | Заменён на `src/mcp_donsetch_stdio.py` |
| `src/agent.py` | ✅ Работает | Используйте — он tool-calling клиент |

**Эти файлы сохранены** в git для истории проекта, но больше не развиваются.
Новый деплой документации в `docs/DONSETCH_DEPLOY.md`.

## Что актуально и работает

| Path | Что это |
|------|---------|
| `mcp-servers.json` | ✅ Новый конфиг с `donsetch` (stdIO-прокси к HTTP MCP) |
| `src/mcp_donsetch_stdio.py` | ✅ stdIO wrapper для подключения llama.cpp к donsetch-http |
| `src/agent.py` | ✅ Tool-calling клиент (работает с любым OpenAI-compatible server) |
| `docs/DEPLOY_DONSETCH.md` | ✅ Полная инструкция развёртывания с нуля |
| `docs/QUICKSTART.md` | ✅ 5-минутный setup |

## Quickstart (новый)

```bash
# Полный деплой с нуля (все 4 компонента):
#   1. donsetch-http MCP server на порт 8765
#   2. llama.cpp с --mcp-servers-config
#   3. stdIO-прокси между ними
#   4. Open WebUI подключение через TOOL_SERVER_CONNECTIONS

bash /opt/search/docs/deploy_donsetch.sh
```

Или ручной пошаговый — см. [docs/DEPLOY_DONSETCH.md](docs/DEPLOY_DONSETCH.md).

## Архитектура (после миграции)

```
┌────────────────┐    HTTP/SSE    ┌────────────────┐
│  Open WebUI    │ ─────────────► │ donsetch-http   │
│  (3001)        │                │ (8765/mcp)      │
└────────────────┘                │ Rust + Playwright│
                                  │ + Chromium+Xvfb │
┌────────────────┐    stdIO/JSON  └─────▲──────-─┘
│  llama.cpp     │ ─────────────┘      │
│  (8080)        │ ────────► 6 search engines
│  Ornith 35B    │          (bing, ddg, mojeek,
└──────▲─────-──┘           brave, google, yahoo)
       │
       └─ OpenAI-compatible API
          (через src/agent.py или LM Studio
           или любой MCP-aware клиент)
```

## Tool calling пример

```bash
curl -sS http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Ornith-1.5-35B-A3B",
    "messages": [{"role":"user","content":"Find MikroTik PBR configuration example RouterOS 7"}],
    "stream": true,
    "max_tokens": 1500
  }'
```

Модель вызовет `donsetch__web_search`, получит реальные результаты с финальными URL 
(не redirect), затем `donsetch__web_fetch` для глубокого чтения.

## История проекта

```
v1.0 - v3.x (2024-2025): SearXNG-based агрегатор
       - Работал пока engines не блокировали
       - Wikipedia/arxiv/github работали
       - DDG/Bing/Startpage начали CAPTCHA после 2024

v4.0 (Sep 2025): MIGRATION to donsetch-http
       - SearXNG удалён как deprecated
       - Playwright headless Chrome через Rust donsetch
       - Tier-2 browser escalation через Xvfb
       - 6 поисковиков агрегируются
       - Без CAPTCHA на российских IP
```

## License

См. LICENSE в корне репозитория.

## Авторы

- Оригинальный SearXNG-based stack: vaskes
- Donsetch migration, stdIO-прокси, документация: AI-агент под управлением vaskes
- [donsetch-http](https://github.com/dondai44423/donsetch) by dondai44423 — независимый проект
