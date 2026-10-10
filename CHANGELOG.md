# Changelog

All notable changes to this project are documented here.
Format: [Semantic Versioning](https://semver.org/) + sections
per release. The repo's `git log` is the granular record;
this file is the human-readable summary.

## [v0.4.1] — 2026-10-10 — v0.4.0 re-review polish

### Fixed

  - **N1** `src/agent.py` — `exit_stack` was created inside the
    `with open(log)` block and only `aclose()`'d on the success
    path. If `models.list()` or any other early call raised, the
    MCP stdIO subprocess (shim child of `StdioServerParameters`)
    was orphaned until the asyncio loop's shutdown hook fired —
    and if the loop already shut down, never. Hoisted `exit_stack`
    to the function top, extracted the body to a `_body()`
    helper, wrapped the call in `try/finally: aclose()`. Comment
    explains why `async with AsyncExitStack` doesn't work
    directly.
  - **N2** `src/agent.py` — dead `import re` at the top of the
    file (leftover from the deleted `_search_*` helpers).
  - **N3** `docs/DONSETCH.md` — stale "image content is dropped"
    paragraph in the `web_screenshot` section. v0.4.0 fixed the
    drop in `agent.py`; this v0.4.1 also fixes the
    contradictory tail that survived v0.4.1's first attempt.
  - **N4** `README.md` — Files table listed 3 paths deleted in
    v0.4.0 (`docs/AGENT_GUIDE.md`, `docs/AGENT_PROMPT.md`,
    `deprecated/playwright_search_proxy.py`) and claimed
    `package.json` had a Playwright dep. Rewrote the table to
    match the actual manifest.
  - **N5** `src/mcp_donsetch_stdio.py` — new `httpx.AsyncClient`
    per request, no HTTP/1.1 keep-alive. Hoisted to a
    module-level singleton via `_get_client()`, `aclose()` in
    `main()`'s `finally`.
  - **N6** `src/mcp_donsetch_stdio.py` — `Mcp-Session-Id` was
    captured before `raise_for_status()`. If donsetch returned
    5xx with a `Mcp-Session-Id` (e.g. via a proxy that injects
    one), we'd cache a header from a failed response. Reordered.
  - **N7** `tests/test_shim_smoke.py` — `test_04` was
    `assertTrue("result" in resp or "error" in resp)`, which
    passes on any valid JSON-RPC response. Tightened to
    `assertIn("error", resp)` and `assertNotIn("result", resp)`.
  - **N8** `docs/DONSETCH.md` — `DONSETCH_MCP__TEXT_ONLY` env var
    mentioned with no context that it lives in donsetch's
    docker-compose env, not in the shim. Added a clarifying
    parenthetical.
  - **N9** `src/mcp_donsetch_stdio.py` — `r.text` was called
    just to check `startswith("data:")`. Now peeks at
    `r.headers.get("content-type", "")` first.

### No production behavior change

End users see the same 4 tools, same JSON-RPC, same wire format.
The 5 shim smoke tests still pass; `test_04` is now actually
exercising the error path that v0.4.0's weak assertion missed.

## [v0.4.0] — 2026-10-10 — code-review response

This release is the response to a self-review of v0.3.0. Most
changes are removal-of-rot (SearXNG-era docs, the Bing-via-
Playwright proxy) plus hardening of the shim and the test
client. **No behavior change for end users** — the production
deploy at /opt/search is unchanged.

### Fixed (B1-B5 — blockers)

- **B1** `docs/DONSETCH_DEPLOY.md` was truncated mid-`sed`
  (line 94 ended with the literal `sed -i s`). Now a full
  160-line step-by-step from clone to verify, matching the
  depth of the old `HUMAN_OPS.md` "Подключение MCP к твоему
  llama-server" section.
- **B2** Two docs referenced from `mcp-servers.json` did not
  exist (`docs/DONSETCH.md`, `docs/MIGRATION-TO-DONSETCH.md`).
  Created `docs/DONSETCH.md` as a per-tool reference (parameters,
  result shape, error semantics, version pinning). Removed the
  `MIGRATION-TO-DONSETCH.md` reference entirely — no
  migrations to support, the operator is the only user.
- **B3** `agent.py` test client was wired to a deleted SearXNG
  MCP server; the `try/except` swallowed the FileNotFoundError
  and the agent started with no search tools. Re-pointed
  `agent.py` at the `mcp_donsetch_stdio.py` shim (the only MCP
  surface in this repo now).
- **B4** `deploy_donsetch.sh` heredoc was quoted (`<<\"TIP\"`),
  so `${PORT}` was NOT expanded and the user saw literal
  `${PORT}` in the on-screen message. Unquoted, expanded.
- **B5** `deploy_donsetch.sh` used `docker logs donsetch-http`
  for the failure path. With `docker compose --profile http up`
  from `/opt/hound`, the actual container name is
  `hound-donsetch-http-1`. Switched to
  `docker compose logs --tail 30 donsetch-http` (compose-aware).

### Fixed (R1-R8 — real bugs)

- **R1** `mcp_donsetch_stdio.py` used
  `asyncio.get_event_loop().run_in_executor(...)` which
  emits `DeprecationWarning` in 3.10+ and has changed behavior
  in 3.12+. Replaced with `asyncio.get_running_loop()` in
  the new `stdin_reader()` helper.
- **R2** `run_in_executor(None, sys.stdin.readline)` allocated
  a new thread per line from the default executor. Replaced
  with `asyncio.StreamReader` via `loop.connect_read_pipe` —
  no thread per line, clean shutdown on parent close.
- **R3** SSE parser returned the **first** `data:` line of a
  response. The MCP streamable-HTTP spec allows multi-line
  `data:` events that must be joined with `\n` before JSON
  parse. Now correctly splits on blank lines (event
  boundaries) and joins `data:` lines per event.
- **R4** No `Mcp-Session-Id` round-trip. Per streamable-HTTP
  spec, the server returns a session id in
  `Mcp-Session-Id` on `initialize` and the client must send
  it on every subsequent request. Now captured from the
  response headers and forwarded.
- **R5** `agent.py` opened the log file with `open(...)` and
  only closed it on the success path. Wrapped in
  `with open(...) as logf:` so failures between open and
  close don't leak the FD.
- **R6** `agent.py` argparse declared `prompt` as both
  positional `nargs="*"` and `--prompt` flag, with a
  "whichever sets last wins" anti-pattern and a hack to
  re-scan `sys.argv`. Split into `prompt_words` (positional)
  and `prompt_str` (--prompt / -p), deleted the hack.
- **R7** `agent.py` `_tool_result_to_text` silently dropped
  image content (no `text` attribute → `"(empty)"`). Now
  emits `data:image/png;base64,...` markdown that vision
  models can read; logs a clear `WARN` if dropped.
- **R8** `agent.py` `mcp_to_openai_tool` stripped
  `additionalProperties` only at the top level. Real MCP
  schemas have it nested. New `_strip_additional_properties`
  helper recurses.

### Changed (S1-S10 — smells)

- **S1** `mcp-servers.json` used non-standard `_comment` keys.
  Dropped. The file is now 8 lines and self-documenting.
- **S2** `package.json` shipped `playwright` and
  `playwright-core` as direct deps. Neither was imported
  by anything in this repo. Replaced the whole manifest
  with a minimal `{name, version, scripts.test, dependencies: {}}`.
- **S3** `agent.py` hardcoded `/opt/search/...` paths.
  Derived from `Path(__file__).parent.parent` so the script
  works regardless of where the repo lives.
- **S4** `agent.py` did a linear `for sess, t in all_tools`
  scan to find each tool by name. Now a `dict[str, tuple]`
  with explicit duplicate-name detection.
- **S5** `agent.py` did not extract `reasoning_content` from
  the LLM response. Now logged at `REASONING` level (visible
  in `--log` but not fed back to the model).
- **S6** Added `LICENSE` (Kuduza Ai Lab framing — public
  visibility, no grant of rights) and this `CHANGELOG.md`.
- **S7** Deleted `deprecated/playwright_search_proxy.py`
  (425 lines of working but unmaintained code). The
  `deprecated/` directory is now empty and removed.
- **S8** Deleted `docs/AGENT_GUIDE.md` (167 lines,
  SearXNG-era) and `docs/AGENT_PROMPT.md` (56 lines,
  SearXNG-era). Slimmed `docs/HUMAN_OPS.md` and
  `docs/QUICKSTART.md` to focus on the active stack.
- **S9** `mcp-servers.json` and the shim both use
  `127.0.0.1:8765`. Added a comment in `deploy_donsetch.sh`
  explaining when to widen the bind (only if other containers
  on the host need it).
- **S10** `.gitignore` now excludes `*.log`, `logs/`, and
  `last_answer.md` (the `agent.py` log/output paths).

### Added

- `tests/test_shim_smoke.py` — 5 subprocess-driven tests
  against the live `donsetch-http` (skipped if MCP
  unreachable). Covers tools/list round-trip (R3),
  session id forwarding (R4), a real web_search, error
  envelope pass-through, and the malformed-JSON-line
  resilience (R1). Run with
  `python3 tests/test_shim_smoke.py` (no pytest required).

## [v0.3.0] — 2026-10-10 — thin shim to donsetch-http

Initial "thin shim" release. Removed the SearXNG-era
artifacts (docker-compose, Bing-via-Playwright proxy).
Forward-looking README that describes what the repo IS, not
what it used to be. Setup for v0.4.0's code-review response.
