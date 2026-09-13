#!/usr/bin/env python3
"""stdIO MCP proxy for donsetch HTTP MCP server.

Llama.cpp only supports stdIO MCP servers via --mcp-servers-config.
This script connects to donsetch-http:8765/mcp over HTTP (streamable)
and exposes the same tools via stdIO for llama.cpp.
"""
import asyncio
import json
import sys
import os
import httpx

DONSETCH_URL = os.environ.get("DONSETCH_URL", "http://localhost:8765/mcp")

async def call_remote(method: str, params: dict | None = None, req_id: int = 1):
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            DONSETCH_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        r.raise_for_status()
        # streamable-http may return SSE-formatted data; extract JSON
        body = r.text.strip()
        if body.startswith("data:"):
            for line in body.split("\n"):
                if line.startswith("data:"):
                    return json.loads(line[len("data:"):].strip())
        return json.loads(body)

def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

async def main():
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        try:
            req = json.loads(line.strip())
        except Exception as e:
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
            emit({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": str(e)}})

asyncio.run(main())
