# Donsetch-HTTP deployment guide

> **Полная инструкция** развёртывания [donsetch-http](https://github.com/dondai44423/donsetch) MCP server
> с нуля и интеграции с llama.cpp и Open WebUI.
> Заменяет SearXNG-based MCP-stack (DEPRECATED, см. [README.md](../README.md)).

## Что такое donsetch-http

**donsetch** — это Rust MCP-сервер для AI-агентов, написанный с нуля. Делает:

- **`web_search`** — поиск через 6 движков (Bing, DDG, Brave, Mojeek, Yahoo, Google) с автоагрегацией и rerank
- **`web_fetch`** — глубокое чтение URL → markdown, с tier-2 browser escalation через Playwright (если HTTP даёт CAPTCHA)
- **`web_crawl`** — multi-page crawling одного сайта
- **`web_screenshot`** — скриншот URL в реальном браузере

Главное отличие от SearXNG:
- **Активный anti-bot обход** через настоящий Chromium headless (не User-Agent spoofing)
- **Tier-2 browser escalation** — если HTTP запрос получает CAPTCHA, donsetch автоматически запускает headless Chrome, проходит проверку и проксирует cookies обратно в HTTP tier-1
- **Без API ключей**, self-hosted, без ограничений на количество запросов

## Архитектура

```
┌──────────────────┐
│   Open WebUI     │ ←──── /tools через OpenAPI proxy ────┐
│   (3001)         │                                       │
└──────────────────┘                                       │
                                                            │
┌──────────────────┐    stdIO/JSON-RPC    ┌────────────────┐│
│   llama.cpp      │ ←───────────────────► │   donsetch-    ││
│   (8080)         │                       │   http         ││
│   Ornith 35B     │                       │   (8765/mcp)    ││
└──────────────────┘                       │   Rust + Chrome ││
                                          └────────────────┘│
                                                           │
                              6 search engines              │
                              (bing, ddg, brave, mojeek,    │
                              yahoo, google)                │
                                                           │
                              fetch → real Chromium ────────┘
                              (tier-2 browser escalation)
```

## Быстрый старт (5 минут)

```bash
# Скачать и запустить автоматический скрипт
bash /opt/search/docs/deploy_donsetch.sh
```

Скрипт спрашивает порт (default 8765) и каталог (default /opt/hound). Дальше сам:
- Клонирует donsetch
- Собирает Docker image с Chromium + Xvfb
- Стартует контейнер
- Проверяет /health

## Пошаговая установка (если хочется руками)

### Шаг 1. Зависимости на хосте

```bash
# Ubuntu 24.04+
sudo apt-get update
sudo apt-get install -y curl git xz-utils

# Docker + Compose v2
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER  # чтобы работать без sudo
# logout/login
```

### Шаг 2. Клонировать donsetch

```bash
sudo mkdir -p /opt
sudo chown $USER:$USER /opt
git clone https://github.com/dondai44423/donsetch.git /opt/hound
cd /opt/hound
```

### Шаг 3. Собрать Docker image

```bash
docker build --build-arg INSTALL_CHROME=true -t donsetch-mcp:latest .
```

Это займёт **2-5 минут** (Rust compile + download Chromium 114MB). Image получится ~1.2GB.

### Шаг 4. Настроить docker-compose.yml

Файл `docker-compose.yml` в репо уже настроен правильно. Единственная правка — открыть порт для всех интерфейсов:

```bash
sed -i s
