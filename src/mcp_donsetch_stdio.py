#!/usr/bin/env python3
"""stdIO MCP proxy for donsetch HTTP MCP server.

Llama.cpp's --mcp-servers-config expects stdIO MCP servers.
This script connects to donsetch-http:8765/mcp over HTTP
(streamable) and re-exposes the same tools via stdIO for
llama.cpp. The shim is a thin forwarder — every JSON-RPC
method and every tool is passed through unchanged.

Requires Python 3.10+ (uses `dict | None` and structural
pattern matching).
"""
import asyncio
import json
import os
import sys
from typing import Any

import httpx

DONSETCH_URL = os.environ.get("DONSETCH_URL", "http://127.0.0.1:8765/mcp")
# Per-streamable-HTTP spec: a session-id is returned in the
# Mcp-Session-Id header on the initialize response and must be
# sent on every subsequent request. We capture and forward it.
_session_id: str | None = None


async def call_remote(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """POST a JSON-RPC request to the donsetch HTTP transport.

    Returns the parsed JSON-RPC response dict (with either
    `result` or `error`). MCP streamable-HTTP may reply with
    server-sent events; in that case we extract the JSON event
    payload (joined per the SSE spec for multi-line data fields).
    """
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    global _session_id
    if _session_id is not None:
        # Forward the session id on every request after initialize
        # so the server can correlate the calls.
        headers["Mcp-Session-Id"] = _session_id

    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(DONSETCH_URL, json=payload, headers=headers)
        # Capture the session id from the response if this is the
        # first request. The server only sets it after a successful
        # initialize; subsequent calls carry the value we already
        # cached above.
        sid = r.headers.get("Mcp-Session-Id")
        if sid and not _session_id:
            _session_id = sid
        r.raise_for_status()
        # Streamable-HTTP may return SSE-formatted body. A single
        # SSE event can have multiple `data:` lines that must be
        # joined with `\n` before JSON parsing. We split on blank
        # lines (event boundaries), accumulate `data:` lines per
        # event, and parse the first event that has any.
        body = r.text
        if body.startswith("data:"):
            for event_block in body.split("\n\n"):
                data_lines = []
                for line in event_block.split("\n"):
                    if line.startswith("data:"):
                        data_lines.append(line[len("data:"):].lstrip())
                if data_lines:
                    return json.loads("\n".join(data_lines))
            # No data: lines anywhere in the SSE body — server-side
            # protocol error. Fall through to plain-JSON parse.
        return json.loads(body)


def emit(obj: dict) -> None:
    """Write one JSON-RPC message to stdout, newline-terminated."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


async def stdin_reader() -> asyncio.StreamReader:
    """Attach an asyncio StreamReader to sys.stdin.

    Replaces the per-line run_in_executor pattern (which created
    a new thread per readline and could leak threads on parent
    close). connect_read_pipe is a single setup call; each read
    is then just `await reader.readline()`.
    """
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=2**20)  # 1 MiB per line cap
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    return reader


async def main() -> None:
    reader = await stdin_reader()
    while True:
        line = await reader.readline()
        if not line:  # EOF — parent closed stdin
            return
        try:
            req = json.loads(line.decode("utf-8", errors="replace").strip())
        except json.JSONDecodeError:
            # Malformed request: don't crash, just skip. A well-
            # behaved parent will close stdin if it gives up.
            continue
        method = req.get("method", "")
        params = req.get("params")
        rid = req.get("id", 1)
        try:
            result = await call_remote(method, params, rid)
            if "result" in result:
                emit({"jsonrpc": "2.0", "id": rid, "result": result["result"]})
            elif "error" in result:
                emit({"jsonrpc": "2.0", "id": rid, "error": result["error"]})
            else:
                emit({"jsonrpc": "2.0", "id": rid, "result": None})
        except Exception as e:
            emit({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32000, "message": f"[shim] {type(e).__name__}: {e}"}})


if __name__ == "__main__":
    asyncio.run(main())
