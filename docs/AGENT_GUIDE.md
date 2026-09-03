# AGENT_GUIDE — How to use llama.cpp_search as a tool

This document is for **another LLM agent** that has been told to use this stack.

## Two ways to use the stack

### A. Shell-exec a Python client (easiest)

If you can run shell commands:

```bash
/opt/search/venv/bin/python /opt/search/src/agent.py "your question here"
```

The client:
1. Lists tools from `GET http://localhost:8080/tools`
2. Loops: prompt → model → tool_call → execute tool (via OpenAI-compat MCP under the hood) → model → final
3. Logs every step to `/opt/search/logs/agent.log`
4. Saves final answer to `/opt/search/logs/last_answer.md`

### B. Use your own OpenAI client with MCP

If you have an MCP-aware client (LM Studio, Open WebUI, custom code):

1. **Get tools**:
   ```bash
   curl -s http://localhost:8080/tools | jq '.[] | {name, description}'
   ```
2. **Make a request**:
   ```python
   from openai import OpenAI
   client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")
   resp = client.chat.completions.create(
       model="<model name>",  # whatever's running
       messages=[{"role": "user", "content": "your question"}],
       tools=<list from /tools endpoint>,
       tool_choice="auto",
       max_tokens=1500,
   )
   ```
3. **Handle `tool_calls`**: execute via your MCP client, append result as `role: "tool"` message, retry.
4. **Loop until `finish_reason == "stop"`**.

## What tools you have

After you start the agent or list `/tools`, you get 27 MCP tools:

### SearXNG MCP — 3 tools
- `search(query, max_results=5, engines="", language="")` — search the web
  - **Always pass `engines` explicitly** to get reliable results. Default engines (wikipedia,arxiv,github,wikidata,openalex,semantic scholar,pubmed,crossref) are non-captcha but limited.
  - For general web, try `"duckduckgo,startpage,brave"` — they may work depending on network.
- `engines()` — list currently enabled engines
- `fetch_url(url)` — fetch a URL and return plain text (≤ 8000 chars). **No JavaScript rendering.** Use Playwright if you need JS.

### Playwright MCP — 24 tools
Key ones:
- `browser_navigate({"url": "..."})` — open a page
- `browser_snapshot()` — get accessibility tree (YAML) of current page. Best for understanding structure.
- `browser_evaluate({"function": "() => document.body.innerText"})` — run JS in page, get result back. **Most useful for extracting text from a known page.**
- `browser_click`, `browser_type`, `browser_press_key` — interact with the page
- `browser_take_screenshot` — visual capture
- `browser_wait_for` — wait for text/time

Other tools (`browser_close`, `browser_resize`, `browser_console_messages`, `browser_tabs`, `browser_network_requests`, etc.) are situational.

## When to use this tool

Use this stack when:
- The user asks a question that requires **current information** (news, recent papers, prices, weather, recent events)
- The user wants to **read the content of a specific URL** (article, documentation page, blog post)
- The user asks you to **search the web** for something

Do NOT use this stack for:
- Questions you can answer from your own knowledge
- Math, code generation, file editing on the local host (use your own tools)
- Anything that does not require the live web

## Recommended workflows

### 1. "Find recent news about X"
```
search(query="X news", engines="duckduckgo,startpage", max_results=5)
→ if results exist: pick 2-3 most relevant
→ fetch_url(url) for the most useful one OR browser_navigate + browser_evaluate
→ summarize in the user's language
```

### 2. "Read https://example.com/article"
```
browser_navigate({"url": "https://example.com/article"})
→ if static HTML: browser_evaluate("() => document.querySelector('article, main, body').innerText")
→ if JS-rendered: browser_evaluate("() => document.body.innerText")
→ trim to relevant parts, summarize
```

### 3. "Find academic papers on topic X"
```
search(query="X", engines="arxiv", max_results=10)
→ list titles + URLs
→ if user wants a specific paper, browser_navigate to arxiv.org/abs/...
```

### 4. "What is X? (factual question)"
Most factual questions can be answered from your own knowledge. Only use the stack if:
- The question is about a recent event
- The user explicitly says "search for..."
- The user wants sources

## When things go wrong

- **search returns 0 results**: try other engines; try a broader/different query; try `fetch_url` directly to a known URL
- **browser_navigate fails**: check URL format (must include scheme); some sites block headless browsers
- **Page content is empty after navigate**: use `browser_wait_for` with `{"text": "expected text"}` then re-snapshot
- **llama-server returns "Loading model"**: wait 10–30 sec, retry. The 35B Q8_0 model on CPU takes ~1 min to load
- **Tool call returns isError=True**: pass the error to the user honestly; do not invent a result
- **MCP server not connecting**: check `journalctl -u <your-llama-service> | grep "MCP warmup"` — should show "discovered N tools" for each

## Performance

- Average full cycle: **30–90 sec** on CPU (35B Q4/Q8 @ 15 tok/s + 1–2 tool calls)
- Each tool call adds **2–15 sec** (SearXNG) or **5–20 sec** (Playwright)
- Plan for **3–5 iterations** max to stay under 2 min

## CLI examples

```bash
# basic Q&A
python /opt/search/src/agent.py "What is the capital of Japan?"

# search
python /opt/search/src/agent.py "Find recent arXiv papers on Mamba architectures"

# read a URL
python /opt/search/src/agent.py "Open https://example.com and tell me what's on it"

# longer output
python /opt/search/src/agent.py "..." --max-tokens 2000 --max-iter 6

# save answer to custom path
python /opt/search/src/agent.py "..." --out /tmp/my_answer.md
```

## Limits

- **`max-iter`** defaults to 8. If you hit it, the agent gives up and says so.
- **`max-tokens`** defaults to 800. For thinking models (like Ornith), set ≥ 500 so thinking has room.
- Results truncated to 6000 chars per tool response (then sent back to the model).

## Don't

- Don't use `search` to look up the same thing twice — use the first results
- Don't call `browser_navigate` on URLs the user didn't ask for
- Don't make up tool results — if a tool fails, say so
- Don't pass max-tokens < 500 for reasoning models — they'll spend all tokens thinking and the final answer will be empty
