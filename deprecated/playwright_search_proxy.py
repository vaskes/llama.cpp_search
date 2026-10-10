#!/usr/bin/env python3
"""Playwright-backed web search proxy for SearXNG.

Persistent asyncio loop + single browser instance. Thread-safe handler.
Engines: bing (Playwright), marginalia (Playwright), wikipedia (REST).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

LOG = logging.getLogger("pw_search")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = int(os.environ.get("PW_SEARCH_PORT", "8889"))
PLAYWRIGHT_BROWSERS_PATH = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/home/git/.cache/ms-playwright")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", PLAYWRIGHT_BROWSERS_PATH)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

# bing returns /ck/a?... redirect URLs. Resolve them once at startup and
# at runtime via the same headless browser. Cached in this module.
_REDIRECT_CACHE: dict[str, str] = {}


async def _resolve_redirect(ctx: Any, url: str) -> str:
    if url in _REDIRECT_CACHE:
        return _REDIRECT_CACHE[url]
    if "bing.com/ck" not in url:
        return url
    page = await ctx.new_page()
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=8000)
        except Exception:
            return url
        # after redirect the address bar shows final URL
        final = page.url
        if final and final != url:
            _REDIRECT_CACHE[url] = final
        return final
    finally:
        await page.close()


# ----------------- engine implementations -----------------

async def _search_bing(ctx: Any, query: str) -> list[dict[str, str]]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}&setmkt=en-US&setlang=en"
    page = await ctx.new_page()
    out: list[dict[str, str]] = []
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            LOG.warning("bing goto: %s", e)
            return out
        # wait longer for hydration
        await page.wait_for_timeout(3000)
        items = await page.locator("li.b_algo").all()
        if not items:
            # fallback: maybe layout changed
            items = await page.locator(".b_algo").all()
        for li in items[:10]:
            try:
                a = li.locator("h2 a").first
                href = await a.get_attribute("href")
                title = (await a.inner_text() or "").strip()
            except Exception:
                continue
            if not href or not title:
                continue
            if href.startswith("/ck/") or "bing.com/ck" in href:
                if href.startswith("/"):
                    href = "https://www.bing.com" + href
                href = await _resolve_redirect(ctx, href)
            snippet = ""
            try:
                sn = li.locator(".b_caption p, .b_snippet, p.b_lineclamp").first
                if await sn.count() > 0:
                    snippet = (await sn.inner_text() or "").strip()
            except Exception:
                pass
            out.append({
                "url": href,
                "title": re.sub(r"\s+", " ", title)[:300],
                "content": re.sub(r"\s+", " ", snippet)[:400],
            })
    finally:
        await page.close()
    return out


async def _search_marginalia(ctx: Any, query: str) -> list[dict[str, str]]:
    url = f"https://search.marginalia.nu/search?query={quote_plus(query)}&profile=no-js"
    page = await ctx.new_page()
    out: list[dict[str, str]] = []
    try:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            LOG.warning("marginalia goto: %s", e)
            return out
        await page.wait_for_timeout(2500)
        items = await page.locator("article.search-result").all()
        if not items:
            items = await page.locator("article").all()
        for art in items[:10]:
            try:
                a = art.locator("h2 a, h3 a, a.title").first
                href = await a.get_attribute("href")
                title = (await a.inner_text() or "").strip()
            except Exception:
                continue
            if not href or not title:
                continue
            snippet = ""
            try:
                sn = art.locator("p, .description, .abstract").first
                if await sn.count() > 0:
                    snippet = (await sn.inner_text() or "").strip()
            except Exception:
                pass
            out.append({
                "url": href,
                "title": re.sub(r"\s+", " ", title)[:300],
                "content": re.sub(r"\s+", " ", snippet)[:400],
            })
    finally:
        await page.close()
    return out


async def _search_duckduckgo(query: str) -> list[dict[str, str]]:
    """DuckDuckGo HTML search via POST form (no JS, no Playwright needed).
    Often CAPTCHA'd but worth a fallback try.
    """
    import httpx
    out: list[dict[str, str]] = []
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"},
        ) as c:
            r = await c.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "kl": "ru-ru"},
            )
            r.raise_for_status()
            from html.parser import HTMLParser
            class _Extract(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results = []
                    self._in_result = False
                    self._current = {}
                    self._in_snippet = False
                    self._snippet = []
                    self._skip = 0
                def handle_starttag(self, tag, attrs):
                    ad = dict(attrs)
                    cls = ad.get("class", "")
                    if tag == "div" and "result" in cls:
                        self._in_result = True
                        self._current = {}
                    elif tag == "a" and self._in_result and ad.get("class") == "result__a":
                        self._current["url"] = ad.get("href", "")
                        self._current["title"] = ""
                    elif tag == "a" and self._in_result and "result__snippet" in cls:
                        self._in_snippet = True
                        self._snippet = []
                    elif tag in ("script", "style"):
                        self._skip += 1
                def handle_endtag(self, tag):
                    if tag in ("script", "style") and self._skip:
                        self._skip -= 1
                    if tag == "a" and self._in_snippet:
                        self._in_snippet = False
                        self._current["content"] = "".join(self._snippet)[:400]
                        self._snippet = []
                    elif tag == "div" and self._in_result and self._current.get("url"):
                        if self._current.get("title") and self._current.get("url"):
                            self.results.append(self._current)
                        self._in_result = False
                        self._current = {}
                def handle_data(self, data):
                    if self._skip:
                        return
                    if self._in_snippet:
                        self._snippet.append(data)
            p = _Extract()
            p.feed(r.text)
            out = p.results
    except Exception as e:
        LOG.warning("duckduckgo: %s", e)
    return out



async def _search_wikipedia(query: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "format": "json", "list": "search",
                        "srsearch": query, "srlimit": 10, "utf8": 1},
                headers={"User-Agent": USER_AGENT},
            )
            r.raise_for_status()
            data = r.json()
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
            url = f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}"
            out.append({
                "url": url,
                "title": title,
                "content": re.sub(r"\s+", " ", snippet)[:400],
            })
    except Exception as e:
        LOG.warning("wikipedia: %s", e)
    return out


# ----------------- core: persistent loop & browser -----------------

class Core:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.pw = None
        self.browser = None
        self.browser_started_at = 0.0
        self.thread: threading.Thread | None = None
        self.BROWSER_TTL = 8 * 60

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run_loop, name="pw-loop", daemon=True)
        self.thread.start()
        for _ in range(50):
            if self.loop is not None:
                return
            time.sleep(0.1)
        raise RuntimeError("loop failed to start")

    def _run_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    async def _ensure_browser(self) -> Any:
        from playwright.async_api import async_playwright
        now = time.time()
        if self.browser is not None and (now - self.browser_started_at) < self.BROWSER_TTL:
            return self.browser
        if self.pw is None:
            self.pw = await async_playwright().start()
        try:
            if self.browser is not None:
                await self.browser.close()
        except Exception:
            pass
        self.browser = await self.pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        self.browser_started_at = now
        LOG.info("browser launched")
        return self.browser

    async def _new_ctx(self) -> Any:
        browser = await self._ensure_browser()
        return await browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
            viewport={"width": 1366, "height": 768},
        )

    async def do_search(self, query: str, engines: list[str]) -> dict[str, Any]:
        browser_engines = [e for e in engines if e in ("bing", "marginalia")]
        run_ddg = "duckduckgo" in engines
        run_wiki = "wikipedia" in engines
        out: list[dict[str, str]] = []
        if browser_engines:
            ctx = await self._new_ctx()
            try:
                for eng in browser_engines:
                    try:
                        if eng == "bing":
                            r = await _search_bing(ctx, query)
                        elif eng == "marginalia":
                            r = await _search_marginalia(ctx, query)
                        else:
                            continue
                        for item in r:
                            item["engine"] = eng
                        out.extend(r)
                        LOG.info("%s: %d results", eng, len(r))
                    except Exception as e:
                        LOG.warning("engine %s crashed: %s", eng, e)
            finally:
                await ctx.close()
        if run_ddg:
            try:
                r = await _search_duckduckgo(query)
                for item in r:
                    item["engine"] = "duckduckgo"
                out.extend(r)
                LOG.info("duckduckgo: %d results", len(r))
            except Exception as e:
                LOG.warning("duckduckgo crashed: %s", e)
        if run_wiki:
            try:
                r = await _search_wikipedia(query)
                for item in r:
                    item["engine"] = "wikipedia"
                out.extend(r)
                LOG.info("wikipedia: %d results", len(r))
            except Exception as e:
                LOG.warning("wikipedia crashed: %s", e)
        seen: set[str] = set()
        deduped: list[dict[str, str]] = []
        for r in out:
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            deduped.append(r)
        return {
            "query": query,
            "results": deduped[:10],
            "answers": [],
            "corrections": [],
            "infoboxes": [],
            "suggestions": [],
            "unresponsive_engines": [],
        }

    def search_sync(self, query: str, engines: list[str], timeout: float = 60.0) -> dict[str, Any]:
        assert self.loop is not None
        fut = asyncio.run_coroutine_threadsafe(self.do_search(query, engines), self.loop)
        return fut.result(timeout=timeout)


CORE = Core()
CORE.start()


# ----------------- HTTP -----------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path == "/healthz":
            self._json(200, {"ok": True, "browser_started": CORE.browser is not None})
            return
        if u.path not in ("/", "/search"):
            self._json(404, {"error": "not found"})
            return
        qs = parse_qs(u.query)
        q = (qs.get("q") or [""])[0].strip()
        engines_param = (qs.get("engines") or [""])[0].strip()
        if not q:
            self._json(400, {"error": "missing q"})
            return
        valid = {"bing", "marginalia", "wikipedia"}
        if engines_param:
            engines = [e.strip() for e in engines_param.split(",") if e.strip() in valid]
        else:
            engines = ["bing", "wikipedia"]
        try:
            data = CORE.search_sync(q, engines, timeout=60)
            self._json(200, data)
        except Exception as e:
            LOG.exception("search failed")
            self._json(500, {"error": str(e)})


def main() -> None:
    httpd = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    LOG.info("listening on http://%s:%d (browsers=%s)", LISTEN_HOST, LISTEN_PORT, PLAYWRIGHT_BROWSERS_PATH)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
