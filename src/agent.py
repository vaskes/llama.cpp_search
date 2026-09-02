"""Minimal tool-calling agent for llama.cpp + MCP servers.

Usage:
    python agent.py "what is the capital of France?"
    python agent.py "find recent news about X" --max-iter 8
    python agent.py --prompt "..."  # explicit
"""
import argparse
import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from typing import Any

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ----- CLI -----
def parse_args():
    p = argparse.ArgumentParser(description="llama.cpp MCP agent")
    p.add_argument("prompt", nargs="*", help="User prompt (joined with space)")
    p.add_argument("--prompt", "-p", help="User prompt")
    p.add_argument("--llama-url", default=os.environ.get("LLAMA_URL", "http://localhost:8080"))
    p.add_argument("--model", default=os.environ.get("LLAMA_MODEL", "auto"))
    p.add_argument("--max-iter", type=int, default=8, help="Max tool-call iterations")
    p.add_argument("--max-tokens", type=int, default=800, help="Max tokens per generation")
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--log", default=os.environ.get("AGENT_LOG", "/opt/search/logs/agent.log"))
    p.add_argument("--out", default=os.environ.get("AGENT_OUT", "/opt/search/logs/last_answer.md"))
    p.add_argument("--no-save", action="store_true")
    return p.parse_args()


# ----- Logging -----
def log_msg(logf, kind, payload):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] {kind}: {payload}\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    if logf:
        logf.write(line)
        logf.flush()


# ----- MCP server bootstrap -----
def make_mcp_params():
    """Return list of StdioServerParameters for all MCP servers we want to attach."""
    params = []

    # SearXNG MCP (Python)
    params.append(StdioServerParameters(
        command="/opt/search/venv/bin/python",
        args=["/opt/search/src/mcp_searxng_server.py"],
        env={
            "SEARXNG_URL": os.environ.get("SEARXNG_URL", "http://localhost:8888"),
            "SEARXNG_LANG": os.environ.get("SEARXNG_LANG", "en"),
            "PATH": "/usr/bin:/bin:/opt/node20/bin",
        },
    ))

    # Playwright MCP (Node, headless)
    params.append(StdioServerParameters(
        command="/opt/node20/bin/node",
        args=[
            "/opt/search/node_modules/@playwright/mcp/cli.js",
            "--headless",
            "--isolated",
            "--no-sandbox",
            "--output-dir", "/opt/search/logs/playwright",
        ],
        env={"PATH": "/opt/node20/bin:/usr/bin:/bin", "HOME": "/home/git"},
    ))
    return params


# ----- OpenAI <-> MCP tool conversion -----
def mcp_to_openai_tool(t) -> dict:
    """Convert MCP tool to OpenAI tool schema.

    Strips fields that llama.cpp OpenAI-compat layer rejects:
      - $schema URI (not in OpenAI tool spec)
      - additionalProperties (some llama.cpp versions choke on it)
    """
    schema = dict(t.inputSchema or {"type": "object", "properties": {}})
    schema.pop("$schema", None)
    schema.pop("additionalProperties", None)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": (t.description or "").strip(),
            "parameters": schema,
        },
    }


# ----- Main loop -----
async def run_agent(args):
    # Normalize prompt to a string (argparse with nargs="*" may have set it to a list)
    if isinstance(args.prompt, list):
        prompt = " ".join(args.prompt)
    else:
        prompt = args.prompt or ""
    if not prompt:
        positional = [a for a in sys.argv[1:] if not a.startswith("-")]
        prompt = " ".join(positional)

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    logf = open(args.log, "a")
    log_msg(logf, "START", f"prompt='{prompt[:200]}' max_iter={args.max_iter} model={args.model}")

    # Connect to llama.cpp
    client = OpenAI(base_url=f"{args.llama_url}/v1", api_key="not-needed", timeout=args.timeout)
    # Pick first available model if 'auto'
    model = args.model
    if model == "auto":
        try:
            ms = client.models.list(timeout=10)
            model = ms.data[0].id
        except Exception as e:
            log_msg(logf, "ERR", f"models.list failed: {e}")
            raise

    # Start MCP servers
    sessions = []
    exit_stack = AsyncExitStack()
    all_tools = []
    for p in make_mcp_params():
        try:
            read, write = await exit_stack.enter_async_context(stdio_client(p))
            sess = await exit_stack.enter_async_context(ClientSession(read, write))
            await sess.initialize()
            sessions.append(sess)
            tools_resp = await sess.list_tools()
            for t in tools_resp.tools:
                all_tools.append((sess, t))
            log_msg(logf, "MCP", f"connected, {len(tools_resp.tools)} tools")
        except Exception as e:
            log_msg(logf, "ERR", f"MCP connect failed: {e}")

    openai_tools = [mcp_to_openai_tool(t) for _, t in all_tools]
    log_msg(logf, "TOOLS", f"{len(openai_tools)} tools exposed: {[t['function']['name'] for t in openai_tools]}")

    messages = [
        {"role": "system", "content": (
            "You are a research assistant with web search and browser tools.\n\n"
            "Rules:\n"
            "1. For simple factual questions answer directly from your own knowledge.\n"
            "2. Use search/fetch_url/browser_navigate ONLY when you need current/external information.\n"
            "3. After AT MOST 2-3 tool calls, STOP calling tools and produce a final answer.\n"
            "4. If a tool returns empty or fails, say so honestly - do not retry with the same approach.\n"
            "5. Keep the final answer concise and in the user's language."
        )},
        {"role": "user", "content": prompt},
    ]

    final = None
    for it in range(args.max_iter):
        log_msg(logf, "ITER", f"#{it+1} model={model}")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
                max_tokens=args.max_tokens,
                temperature=0.2,
            )
        except Exception as e:
            log_msg(logf, "ERR", f"chat.completions failed: {e}")
            final = f"[error: {e}]"
            break

        msg = resp.choices[0].message
        log_msg(logf, "ASSISTANT", f"content='{(msg.content or '')[:200]}' tool_calls={len(msg.tool_calls or [])}")

        # No tool calls → final answer
        if not msg.tool_calls:
            final = msg.content or ""
            break

        # Add assistant message to history
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        })

        # Execute each tool call
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except Exception:
                fn_args = {}

            log_msg(logf, "TOOL_CALL", f"{fn_name}({json.dumps(fn_args)[:200]})")
            # Find the session that owns this tool
            tool_text_result = ""
            tool_error = False
            for sess, t in all_tools:
                if t.name == fn_name:
                    try:
                        r = await sess.call_tool(fn_name, fn_args)
                        tool_error = r.isError
                        parts = []
                        for c in r.content:
                            if hasattr(c, "text") and c.text:
                                parts.append(c.text)
                        tool_text_result = "\n".join(parts) or "(empty)"
                    except Exception as e:
                        tool_text_result = f"[tool error: {e}]"
                        tool_error = True
                    break
            else:
                tool_text_result = f"[unknown tool: {fn_name}]"
                tool_error = True

            log_msg(logf, "TOOL_RESULT", f"{fn_name} → err={tool_error} len={len(tool_text_result)} preview='{tool_text_result[:120]}'")

            # Truncate very large results
            if len(tool_text_result) > 6000:
                tool_text_result = tool_text_result[:6000] + "\n[... truncated ...]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_text_result,
            })

    # Save final answer
    if final is None:
        final = "[max iterations reached without final answer]"

    log_msg(logf, "FINAL", f"len={len(final)}")
    if not args.no_save:
        with open(args.out, "w") as f:
            f.write(f"# Query\n\n{prompt}\n\n# Answer\n\n{final}\n")
        log_msg(logf, "SAVE", args.out)

    logf.close()
    await exit_stack.aclose()
    return final


def main():
    args = parse_args()
    # Hack: collect positional prompt
    if not args.prompt and args.prompt is None:
        # argparse: positional 'prompt' already handled
        pass
    # Re-parse with positional detection
    if not args.prompt and len(sys.argv) > 1:
        # If first arg doesn't start with -, treat all positional as prompt
        positional = [a for a in sys.argv[1:] if not a.startswith("-")]
        if positional:
            args.prompt = " ".join(positional)
    if not args.prompt:
        print("Usage: python agent.py 'your question here'", file=sys.stderr)
        sys.exit(1)
    final = asyncio.run(run_agent(args))
    print("\n" + "=" * 60)
    print("FINAL ANSWER:")
    print("=" * 60)
    print(final)


if __name__ == "__main__":
    main()
