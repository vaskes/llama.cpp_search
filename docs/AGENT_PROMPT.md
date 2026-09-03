# AGENT_PROMPT — копипастить в каждое задание агенту

> Тебе доступен **web search и чтение страниц** через локальный toolchain.
> **Не выдумывай** — если данных нет, скажи честно.
> 
> **Два способа использовать:**
> 
> **A) Через Python-клиент** (если у тебя есть shell exec):
> ```bash
> /opt/search/venv/bin/python /opt/search/src/agent.py "ваш вопрос" --max-tokens 1500 --max-iter 6
> ```
> Ответ придёт в stdout и в `/opt/search/logs/last_answer.md`.
> 
> **B) Напрямую через llama-server** (если у тебя есть OpenAI-совместимый клиент):
> 1. Получи список tools: `curl http://localhost:8080/tools | jq`
> 2. Передай `tools` в `POST /v1/chat/completions`
> 3. Когда модель вернёт `tool_calls` — выполни их и верни результат в `role: "tool"` сообщении
> 4. Повторяй до `finish_reason: "stop"`
> 
> **Что под капотом:** локальный llama.cpp (модель с tool calling) + два MCP-сервера:
> - `search(query, engines="wikipedia,arxiv,github,wikidata,openalex,semantic scholar,pubmed,crossref", max_results=5)` — SearXNG
> - `fetch_url(url)` — HTML без JS
> - `browser_navigate(url)` + `browser_evaluate("() => document.body.innerText")` — Playwright (для JS-сайтов)
> 
> **Ограничения SearXNG:** DuckDuckGo / Startpage / Mojeek капчат от server IP, **не используй** — пусто. Используй только API-движки (список выше). Для общего web — Playwright.
> 
> **Когда вызывать:**
> - Свежие новости / события / цены
> - Конкретный URL — прочитать
> - Научные статьи (arXiv, OpenAlex)
> - GitHub репозитории, Wikipedia, Wikidata
> 
> **Когда НЕ вызывать** (хватит своих знаний): базовая математика, общие факты, форматирование, объяснения концепций.
> 
> **Типичные промпты:**
> ```bash
> /opt/search/venv/bin/python /opt/search/src/agent.py "Найди 3 свежие новости про X"
> /opt/search/venv/bin/python /opt/search/src/agent.py "Что написано на https://example.com/article"
> /opt/search/venv/bin/python /opt/search/src/agent.py "Найди arXiv-статьи про Mamba, дай 5 заголовков"
> /opt/search/venv/bin/python /opt/search/src/agent.py "Погода в Москве на сегодня"
> ```
> 
> **Среднее время:** 30–90 сек на запрос. Тяжёлые страницы через Playwright — до 2 мин.
