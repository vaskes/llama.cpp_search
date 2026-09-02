"""SearXNG MCP server — exposes web search via Model Context Protocol (stdio)."""
import os
import sys
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("searxng")
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")
DEFAULT_LANG = os.environ.get("SEARXNG_LANG", "ru")
DEFAULT_ENGINES = os.environ.get(
    "SEARXNG_DEFAULT_ENGINES",
    "wikipedia,arxiv,github,wikidata,openalex,semantic scholar,pubmed,crossref",
)
DEFAULT_TIMEOUT = float(os.environ.get("SEARXNG_TIMEOUT", "15"))


@mcp.tool()
async def search(
    query: str,
    max_results: int = 5,
    engines: str = "",
    language: str = "",
) -> list[dict]:
    """Search the web via SearXNG.

    Args:
        query: search query string.
        max_results: max number of results to return (default 5).
        engines: comma-separated engine list (e.g. "wikipedia,arxiv"). Empty = all enabled.
        language: language code (default uses instance default, e.g. "en"/"ru").

    Returns:
        list of {title, url, snippet, engine}.
    """
    params = {
        "q": query,
        "format": "json",
        "language": language or DEFAULT_LANG,
        "safesearch": "0",
    }
    if engines:
        params["engines"] = engines
    elif DEFAULT_ENGINES:
        params["engines"] = DEFAULT_ENGINES

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as c:
        r = await c.get(f"{SEARXNG_URL}/search", params=params)
        r.raise_for_status()
        data = r.json()

    out = []
    for x in data.get("results", [])[:max_results]:
        out.append({
            "title": x.get("title", ""),
            "url": x.get("url", ""),
            "snippet": x.get("content", ""),
            "engine": x.get("engine", ""),
        })
    return out


@mcp.tool()
async def engines() -> list[str]:
    """List enabled SearXNG engines."""
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{SEARXNG_URL}/config")
        r.raise_for_status()
        cfg = r.json()
    eng = cfg.get("engines", [])
    # SearXNG 2026.x returns engines as list[dict]
    if isinstance(eng, list):
        return sorted([e.get("name", "?") for e in eng if not e.get("disabled")])
    return sorted([k for k, v in eng.items() if not v.get("disabled")])


@mcp.tool()
async def fetch_url(url: str) -> str:
    """Fetch a URL and return plain text (truncated).

    Useful fallback when you need content from a page without a browser.
    """
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
    ) as c:
        r = await c.get(url)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "html" not in ctype and "xml" not in ctype and "text" not in ctype:
            return f"[non-text content: {ctype}, {len(r.content)} bytes]"

    from html.parser import HTMLParser
    class T(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self.skip = 0
        def handle_starttag(self, t, a):
            if t in ("script", "style", "noscript"): self.skip += 1
            if t in ("p", "br", "div", "li", "h1", "h2", "h3", "h4"): self.parts.append("\n")
        def handle_endtag(self, t):
            if t in ("script", "style", "noscript"): self.skip -= 1
            if t in ("p", "div", "li", "h1", "h2", "h3", "h4"): self.parts.append("\n")
        def handle_data(self, d):
            if not self.skip: self.parts.append(d)

    p = T()
    p.feed(r.text)
    text = "".join(p.parts)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text[:8000]


if __name__ == "__main__":
    mcp.run(transport="stdio")
