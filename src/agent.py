"""Minimal tool-calling agent for llama.cpp + the stdIO MCP shim.

This is a test client for the donsetch stdIO bridge. Production
deployments use llama-server's --mcp-servers-config flag, which
spawns `mcp_donsetch_stdio.py` as a child process — that's the
real integration path. This file is the equivalent of that
integration but for an OpenAI-Python client: same tool surface,
same JSON-RPC plumbing, but in user-space for ad-hoc testing.

Usage:
    python agent.py "what is the capital of France?"
    python agent.py --prompt "find recent news about X" --max-iter 4
"""
import argparse
import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Resolve the shim path relative to THIS file, not /opt/search.
# The shim lives at src/mcp_donsetch_stdio.py next to this script.
REPO_ROOT = Path(__file__).resolve().parent.parent
SHIM = REPO_ROOT / "src" / "mcp_donsetch_stdio.py"


# ----- CLI -----
def parse_args():
    p = argparse.ArgumentParser(description="llama.cpp MCP test agent")
    # Use separate dest names so positional and --prompt don't
    # write to the same attribute. Avoids the argparse anti-pattern
    # of "whichever sets last wins" (R6).
    p.add_argument("prompt_words", nargs="*",
                   help="User prompt (joined with space)")
    p.add_argument("--prompt", "-p", dest="prompt_str",
                   help="User prompt (explicit)")
    p.add_argument("--llama-url",
                   default=os.environ.get("LLAMA_URL", "http://localhost:8080"))
    p.add_argument("--model", default=os.environ.get("LLAMA_MODEL", "auto"))
    # 4 (not 8) because the system prompt says "AT MOST 2-3 tool
    # calls". --max-iter is the safety ceiling, the system prompt
    # is the actual knob. The previous default of 8 let the agent
    # wander well past the prompt's recommended budget.
    p.add_argument("--max-iter", type=int, default=4,
                   help="Max tool-call iterations (safety ceiling)")
    p.add_argument("--max-tokens", type=int, default=800)
    p.add_argument("--timeout", type=int, default=60)
    # Logs go next to this script, not /opt/search.
    p.add_argument("--log", default=str(REPO_ROOT / "logs" / "agent.log"))
    p.add_argument("--out", default=str(REPO_ROOT / "logs" / "last_answer.md"))
    p.add_argument("--no-save", action="store_true")
    return p.parse_args()


# ----- Logging -----
def log_msg(logf, kind, payload):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] {kind}: {payload}\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    if logf is not None:
        logf.write(line)
        logf.flush()


# ----- MCP server bootstrap -----
def make_mcp_params():
    """Return the stdIO MCP server definitions we want to attach.

    The stdIO shim `mcp_donsetch_stdio.py` is the entire MCP
    surface this agent needs — it talks to the upstream
    donsetch-http at 127.0.0.1:8765/mcp and exposes 4 tools
    (web_search, web_fetch, web_crawl, web_screenshot). The
    shim is co-located with this script in the same repo, so
    we don't hardcode /opt/search/...; the path is derived
    from __file__.
    """
    return [
        StdioServerParameters(
            command=sys.executable,
            args=[str(SHIM)],
            env={
                "DONSETCH_URL": os.environ.get("DONSETCH_URL",
                                              "http://127.0.0.1:8765/mcp"),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            },
        ),
    ]


# ----- OpenAI <-> MCP tool conversion -----
def _strip_additional_properties(node):
    """Recursively remove `additionalProperties` from any dict.

    Some llama.cpp OpenAI-compat layers reject the
    `additionalProperties: false` constraint that MCP schemas
    often carry. We strip it at every level so the schema
    doesn't choke the model server.
    """
    if isinstance(node, dict):
        node.pop("additionalProperties", None)
        for v in node.values():
            _strip_additional_properties(v)
    elif isinstance(node, list):
        for v in node:
            _strip_additional_properties(v)
    return node


def mcp_to_openai_tool(t) -> dict:
    """Convert one MCP tool into the OpenAI tools[].function shape."""
    schema = dict(t.inputSchema or {"type": "object", "properties": {}})
    schema.pop("$schema", None)
    _strip_additional_properties(schema)
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
def _truncate_for_model(text: str, max_chars: int = 6000) -> str:
    """Cut tool result text to ~max_chars at the last newline so
    we don't break URLs or sentences mid-token."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Try to cut at the last newline to avoid breaking tokens.
    last_nl = cut.rfind("\n")
    if last_nl > max_chars * 0.7:
        cut = cut[:last_nl]
    return cut + "\n[... truncated ...]"


def _tool_result_to_text(content_blocks, fn_name: str, logf) -> str:
    """Convert MCP tool result content blocks to a text string
    the LLM can read. Image content is preserved as a data:
    URL the model can see if it's vision-capable; otherwise we
    log a clear warning. The previous code dropped image
    blocks silently and returned "(empty)" to the model (R7).
    """
    parts = []
    for c in content_blocks:
        # MCP Python SDK: text blocks have .text; image blocks
        # have .data (base64) and .mimeType.
        text = getattr(c, "text", None)
        if text:
            parts.append(text)
            continue
        data = getattr(c, "data", None)
        mime = getattr(c, "mimeType", None)
        if data and mime and mime.startswith("image/"):
            data_url = f"data:{mime};base64,{data}"
            parts.append(f"![{fn_name} result]({data_url})")
            log_msg(logf, "WARN", f"{fn_name} returned image content; "
                                 f"emitted as data: URL")
            continue
        # Other content types (audio, resource, etc.) — not
        # currently supported by donsetch, but be explicit.
        log_msg(logf, "WARN", f"{fn_name} returned unknown content "
                             f"type: {type(c).__name__}")
    return "\n".join(parts) or "(empty)"


async def _body(args, prompt, logf, exit_stack):
    """Body of run_agent() extracted so the with-block can wrap
    the call in try/finally for exit_stack cleanup. Receives the
    log file and exit_stack from the caller.
    """

    log_msg(logf, "START",
            f"prompt='{prompt[:200]}' max_iter={args.max_iter} "
            f"model={args.model}")

    client = OpenAI(base_url=f"{args.llama_url}/v1",
                    api_key="not-needed", timeout=args.timeout)
    model = args.model
    if model == "auto":
        try:
            ms = client.models.list(timeout=10)
            model = ms.data[0].id
        except Exception as e:
            log_msg(logf, "ERR", f"models.list failed: {e}")
            raise

    # Connect to MCP servers (donsetch stdIO shim only).
    sessions = []
    # name -> (session, tool) for O(1) lookup AND duplicate-name
    # detection (R8 + S4). The previous linear scan silently
    # picked the first match if two servers registered the same
    # tool name.
    tools_by_name: dict[str, tuple[ClientSession, object]] = {}
    for p in make_mcp_params():
        try:
            read, write = await exit_stack.enter_async_context(
                stdio_client(p))
            sess = await exit_stack.enter_async_context(
                ClientSession(read, write))
            await sess.initialize()
            sessions.append(sess)
            tools_resp = await sess.list_tools()
            for t in tools_resp.tools:
                if t.name in tools_by_name:
                    log_msg(logf, "ERR",
                            f"tool '{t.name}' registered by TWO servers; "
                            f"keeping the first")
                    continue
                tools_by_name[t.name] = (sess, t)
            log_msg(logf, "MCP",
                    f"connected, {len(tools_resp.tools)} tools")
        except Exception as e:
            log_msg(logf, "ERR", f"MCP connect failed: {e}")

    all_tools = list(tools_by_name.values())
    openai_tools = [mcp_to_openai_tool(t) for _, t in all_tools]
    log_msg(logf, "TOOLS",
            f"{len(openai_tools)} tools exposed: "
            f"{[t['function']['name'] for t in openai_tools]}")

    messages = [
        {"role": "system", "content": (
            "You are a research assistant with web search and browser tools.\n\n"
            "Rules:\n"
            "1. For simple factual questions answer directly from your own knowledge.\n"
            "2. Use search/fetch/crawl/screenshot ONLY when you need current/external information.\n"
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
        # Dump reasoning_content to log if present (S5). For a
        # research agent we don't want to burn output tokens on
        # the model's thinking, but the operator may want to
        # see it when debugging. Goes to log only.
        rc = getattr(msg, "reasoning_content", None)
        if rc:
            log_msg(logf, "REASONING", f"len={len(rc)} preview='{rc[:200]}'")
        log_msg(logf, "ASSISTANT",
                f"content='{(msg.content or '')[:200]}' "
                f"tool_calls={len(msg.tool_calls or [])}")

        if not msg.tool_calls:
            final = msg.content or ""
            break

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except Exception:
                fn_args = {}

            log_msg(logf, "TOOL_CALL",
                    f"{fn_name}({json.dumps(fn_args)[:200]})")
            if fn_name not in tools_by_name:
                tool_text = f"[unknown tool: {fn_name}]"
                log_msg(logf, "WARN", f"unknown tool '{fn_name}'")
            else:
                sess, _ = tools_by_name[fn_name]
                try:
                    r = await sess.call_tool(fn_name, fn_args)
                    tool_text = _tool_result_to_text(r.content, fn_name, logf)
                    if r.isError:
                        log_msg(logf, "TOOL_ERR",
                                f"{fn_name} returned isError=True")
                except Exception as e:
                    tool_text = f"[tool error: {e}]"
                    log_msg(logf, "ERR",
                            f"{fn_name} call failed: {e}")

            log_msg(logf, "TOOL_RESULT",
                    f"{fn_name} -> len={len(tool_text)} "
                    f"preview='{tool_text[:120]}'")

            tool_text = _truncate_for_model(tool_text)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_text,
            })

    if final is None:
        final = "[max iterations reached without final answer]"

    log_msg(logf, "FINAL", f"len={len(final)}")
    if not args.no_save:
        with open(args.out, "w") as f:
            f.write(f"# Query\n\n{prompt}\n\n# Answer\n\n{final}\n")
        log_msg(logf, "SAVE", args.out)
    return final

async def run_agent(args):
    # Resolve prompt from either source (R6 fix).
    prompt = args.prompt_str or " ".join(args.prompt_words) or ""
    if not prompt:
        print("Usage: python agent.py 'your question here'", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    # Use a context manager so the log file is always closed, even
    # on exceptions (R5 fix). The previous code opened logf and
    # only closed it on the success path, leaking the FD on the
    # many failure paths between open and close.
    # N1: exit_stack is hoisted above the with-block so aclose() in
    # the finally clause runs even if the body raises. AsyncExitStack
    # does NOT support `async with` directly; manual try/finally is
    # the canonical pattern.
    exit_stack = AsyncExitStack()
    # R5: with-block closes the log FD on any exit path.
    with open(args.log, "a") as logf:
        try:
            return await _body(args, prompt, logf, exit_stack)
        finally:
            await exit_stack.aclose()


def main():
    args = parse_args()
    final = asyncio.run(run_agent(args))
    print("\n" + "=" * 60)
    print("FINAL ANSWER:")
    print("=" * 60)
    print(final)


if __name__ == "__main__":
    main()
