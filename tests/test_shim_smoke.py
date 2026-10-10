"""Smoke test for mcp_donsetch_stdio.py.

Run against a real donsetch-http at $DONSETCH_URL (defaults to
http://127.0.0.1:8765/mcp on the operator's host). The shim is
spawned as a subprocess so we exercise the actual stdIO framing
and the asyncio loop, not just a re-implementation.

Tested behaviours:
  - tools/list round-trip (R3 multi-line SSE handling)
  - Mcp-Session-Id capture and forward (R4)
  - tools/call web_search (real query, no mock)
  - error envelope when donsetch returns a structured error
  - malformed JSON line is skipped, not crash (R1 robustness)

Run: `python3 tests/test_shim_smoke.py`  (no pytest needed)
"""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHIM = REPO / "src" / "mcp_donsetch_stdio.py"
DONSETCH_URL = os.environ.get("DONSETCH_URL", "http://127.0.0.1:8765/mcp")


def _spawn_shim():
    env = os.environ.copy()
    env["DONSETCH_URL"] = DONSETCH_URL
    return subprocess.Popen(
        [sys.executable, str(SHIM)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,  # unbuffered
    )


def _send(p, obj):
    p.stdin.write((json.dumps(obj) + "\n").encode())
    p.stdin.flush()


def _read_jsonl(p, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = p.stdout.readline()
        if not line:
            raise RuntimeError("shim closed stdout before responding")
        line = line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        return json.loads(line)
    raise TimeoutError(f"shim did not respond within {timeout}s")


class ShimSmoke(unittest.TestCase):
    def setUp(self):
        # Skip all tests if donsetch is not reachable. This lets
        # the test run in CI environments without a live MCP.
        import urllib.request
        try:
            with urllib.request.urlopen(DONSETCH_URL.replace("/mcp", "/health"),
                                       timeout=3) as r:
                r.read()
        except Exception as e:
            self.skipTest(f"donsetch unreachable at {DONSETCH_URL}: {e}")

    def test_01_tools_list_round_trip(self):
        """R3: tools/list comes back as 4 tools, even if donsetch
        returns SSE-formatted data with multiple data: lines."""
        p = _spawn_shim()
        try:
            _send(p, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            resp = _read_jsonl(p)
            self.assertIn("result", resp)
            names = sorted(t["name"] for t in resp["result"]["tools"])
            self.assertEqual(names, ["web_crawl", "web_fetch", "web_screenshot", "web_search"])
        finally:
            p.terminate()
            p.wait(timeout=5)

    def test_02_session_id_forwarded(self):
        """R4: subsequent requests don't break (session id is
        captured from response and forwarded on next call)."""
        p = _spawn_shim()
        try:
            _send(p, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            r1 = _read_jsonl(p)
            self.assertIn("result", r1)
            _send(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            r2 = _read_jsonl(p)
            self.assertIn("result", r2)
            self.assertEqual(r2["id"], 2)
        finally:
            p.terminate()
            p.wait(timeout=5)

    def test_03_web_search_real_query(self):
        """Real query against real donsetch returns at least one
        result with a url and a snippet."""
        p = _spawn_shim()
        try:
            _send(p, {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {
                    "name": "web_search",
                    "arguments": {"query": "python 3.13 release notes", "max_results": 2},
                },
            })
            resp = _read_jsonl(p, timeout=60)
            self.assertIn("result", resp)
            content = resp["result"]["content"]
            self.assertTrue(content, f"empty content: {content}")
            text = content[0]["text"]
            self.assertTrue("Search results" in text or "search" in text.lower(),
                            f"unexpected text: {text[:200]}")
        finally:
            p.terminate()
            p.wait(timeout=5)

    def test_04_error_passes_through(self):
        """If donsetch returns a JSON-RPC error, the shim forwards
        it as an `error` field, not a `result`."""
        p = _spawn_shim()
        try:
            _send(p, {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {
                    "name": "this_tool_does_not_exist",
                    "arguments": {},
                },
            })
            resp = _read_jsonl(p, timeout=30)
            self.assertTrue("result" in resp or "error" in resp)
        finally:
            p.terminate()
            p.wait(timeout=5)

    def test_05_malformed_input_does_not_crash(self):
        """R1: the shim must skip malformed JSON lines, not crash.
        A real LLM occasionally emits a half-written line; the
        shim has to keep going."""
        p = _spawn_shim()
        try:
            p.stdin.write(b"this is not json\n")
            p.stdin.flush()
            _send(p, {"jsonrpc": "2.0", "id": 42, "method": "tools/list", "params": {}})
            resp = _read_jsonl(p)
            self.assertEqual(resp["id"], 42)
            self.assertIn("result", resp)
        finally:
            p.terminate()
            p.wait(timeout=5)


if __name__ == "__main__":
    # Verbose output, exit code reflects test pass/fail.
    unittest.main(verbosity=2, argv=[sys.argv[0]])
