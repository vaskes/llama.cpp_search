# AGENT_PROMPT — копипастить в каждое задание агенту

> Тебе доступен **web search и чтение страниц** через локальный toolchain.
> Запускай через shell exec. **Не выдумывай** — если данных нет, скажи честно.
> 
> **Команда:**
> ```
> cd /opt/search && ./venv/bin/python src/agent.py "ваш вопрос" --max-tokens 1500 --max-iter 6
> ```
> 
> **Что под капотом:** локальный llama.cpp (модель Ornith-1.5-35B-A3B) с двумя MCP-серверами:
> - `search(query, engines="wikipedia,arxiv,github,wikidata,openalex,semantic scholar,pubmed,crossref", max_results=5)` — SearXNG
> - `fetch_url(url)` — HTML без JS
> - `browser_navigate(url)` + `browser_evaluate("() => document.body.innerText")` — Playwright (полноценный браузер, для JS-сайтов)
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
> ./venv/bin/python src/agent.py "Найди 3 свежие новости про X"
> ./venv/bin/python src/agent.py "Что написано на https://example.com/article"
> ./venv/bin/python src/agent.py "Найди arXiv-статьи про Mamba, дай 5 заголовков"
> ./venv/bin/python src/agent.py "Погода в Москве на сегодня"
> ```
> 
> **Среднее время:** 30–90 сек на запрос. Тяжёлые страницы через Playwright — до 2 мин.
