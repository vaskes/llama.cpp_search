# DONSETCH.md — operator's per-tool reference

[donsetch](https://github.com/dondai44423/donsetch) exposes 4
tools over MCP (streamable-HTTP at `/mcp`, stdIO via the shim
in this repo). The descriptions below mirror the upstream
schema as of donsetch v4.7.4 (October 2026).

## Discovery

List tools:

```bash
curl -sS -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

The response includes `_meta.com.donsetch/search-debug` with
per-engine timing and the intent detected (`web`, `code`, `paper`,
`news`, `entity`). Use it to spot engine degradation.

## `web_search`

Aggregated search across Bing, DuckDuckGo, Mojeek, Yahoo, Brave,
Google. Returns titles + snippets + URLs. To read a result,
follow up with `web_fetch` (give it the URL — pass the `handle`
through the `web_fetch` resolver if you want batch continuation).

### Parameters

| name | type | required | default | notes |
|------|------|----------|---------|-------|
| `query` | string | yes | — | Primary formulation |
| `query_variants` | string[] | no | — | Up to 2 alternate phrasings |
| `intent` | string | no | `auto` | `auto`/`web`/`code`/`paper`/`news`/`entity` |
| `max_results` | int | no | 7 (max 12) | Max ranked candidates to return |
| `deadline_ms` | int | no | (server default) | Hard wall-clock cap |

### Result format

```json
{
  "results": [
    {"handle": "abc123", "rank": 1, "url": "https://...", "snippet": "..."}
  ],
  "degraded": false,
  "failed_engines": 0,
  "weak": false
}
```

`degraded: true` means at least one engine failed; the result
list is still usable, but treat rankings with suspicion.
`failed_engines` is the number that 5xx'd or rate-limited.

## `web_fetch`

Read one URL (or a small batch) as clean markdown.

### Parameters

| name | type | required | default | notes |
|------|------|----------|---------|-------|
| `url` | string\|string[] | yes | — | One URL or a batch of up to 12 |
| `tier` | string | no | `auto` | `auto` (HTTP→browser escalation), `1` (HTTP only), `2` (browser only) |
| `focus` | string | no | (whole page) | Topic to extract relevant passages |
| `max_chars` | int | no | 16000 | Markdown char budget; truncated pages include `next_offset` for resumption |
| `must_contain` | string | no | — | `/regex/` or substring; returns `MATCH`/`NO-MATCH` + up to 3 excerpts |
| `actions` | object[] | no | — | Pre-read interactions (wait, click, type) — see donsetch docs |
| `deadline_ms` | int | no | (server default) | Hard wall-clock cap |
| `image_text` | bool | no | false | Extract text from up to 4 content images |
| `media` | bool | no | false | Include image alt text and source URLs |

### Result format

The text content is in `result.content[0].text` as markdown.
The same content is duplicated as JSON in `structuredContent`
when donsetch is configured with `DONSETCH_MCP__TEXT_ONLY=false`
(the configuration this repo uses).

## `web_crawl`

Multi-page crawl from a seed URL. Returns markdown or JSONL.

### Parameters

| name | type | required | default | notes |
|------|------|----------|---------|-------|
| `url` | string | yes | — | Seed URL |
| `max_pages` | int | no | 10 (cap 200) | Max pages to fetch+extract |
| `max_depth` | int | no | 2 | Max link depth from seed (0 = seed only) |
| `max_total_chars` | int | no | 60000 | Char budget across all pages |
| `per_page_max` | int | no | 8000 | Per-page markdown cap |
| `focus` | string | no | — | Topic to select relevant pages |
| `mode` | string | no | `full` | `full` (read), `map` (URL inventory only), `content` (read from seed) |
| `include_paths`/`exclude_paths` | string[] | no | — | Path globs |
| `respect_robots` | bool | no | true | Honour robots.txt |
| `dataset` | bool | no | false | Return JSONL instead of markdown |
| `deadline_s` | int | no | 120 | Hard crawl deadline in seconds |
| `resume` | string | no | — | Opaque token from a stopped crawl |

### Result format

`mode: map` returns the URL inventory first (so you can
discover scope, then fetch the few you actually need).
`mode: full` returns markdown with `next_offset` per page if
the budget was hit before all pages were processed.

## `web_screenshot`

Capture a URL as a PNG.

### Parameters

| name | type | required | default | notes |
|------|------|----------|---------|-------|
| `url` | string | yes | — | URL to capture |
| `full_page` | bool | no | false | Capture full page height, not just viewport |
| `wait_ms` | int | no | 600 | Extra settle time after load (max 5000) |

### Result format

Returns image content (`ImageContent` with base64 `data` and
`mimeType: image/png`). **The stdIO shim and the `agent.py`
test client currently drop image content silently** — they
return `(empty)` to the model. If you need this tool in
production, either:
- extend the shim to pass image content as a data: URL the
  model can see (works for vision-capable models), or
- log a clear warning that the image is being dropped.

## Error semantics (4.7.x)

donsetch 4.7.1+ follows a "failures are values" contract: the
MCP `isError` flag stays `false`, and failures are returned as
normal results whose `result._meta.com.donsetch/...` envelope
carries `ok: false` plus a stable `code` and `errorKind`. The
plain `text` field is a human-readable description of what
went wrong. **The stdIO shim and `agent.py` do not currently
parse this envelope** — they pass the text through to the
model verbatim. The model usually figures it out from the
text, but if you want machine-readable errors, you'll need
to extend the shim to look at `_meta` and surface `code`/
`errorKind` to the model.

## Versioning

This repo is pinned to whatever donsetch version is deployed
in `/opt/hound`. The shim (`src/mcp_donsetch_stdio.py`) is
version-agnostic; it just forwards JSON-RPC. New tools
upstream appear automatically in your `tools/list` response.
