import asyncio
import json
import sys
import time
sys.path.insert(0, "/opt/search/src")
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_llama_basic():
    print("\n=== TEST 1: llama.cpp basic chat ===")
    client = OpenAI(base_url="http://localhost:8080/v1", api_key="none", timeout=60)
    t = time.time()
    resp = client.chat.completions.create(
        model="Ornith-1.5-35B-A3B",
        messages=[{"role": "user", "content": "What is 2+2? Just the number."}],
        max_tokens=20,
    )
    print(f"  time={time.time()-t:.1f}s")
    print(f"  answer: {resp.choices[0].message.content!r}")
    assert resp.choices[0].message.content
    print("  OK")


def test_llama_with_one_tool():
    print("\n=== TEST 2: llama.cpp with 1 tool ===")
    client = OpenAI(base_url="http://localhost:8080/v1", api_key="none", timeout=60)
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }]
    t = time.time()
    resp = client.chat.completions.create(
        model="Ornith-1.5-35B-A3B",
        messages=[{"role": "user", "content": "What is the weather in Tokyo? Use the tool."}],
        tools=tools,
        tool_choice="auto",
        max_tokens=200,
    )
    print(f"  time={time.time()-t:.1f}s")
    msg = resp.choices[0].message
    print(f"  content: {msg.content!r}")
    print(f"  tool_calls: {[(tc.function.name, tc.function.arguments) for tc in (msg.tool_calls or [])]}")
    if msg.tool_calls:
        print("  OK")
    else:
        print("  FAIL no tool call")


def test_llama_with_many_tools():
    print("\n=== TEST 3: llama.cpp with 5 tools ===")
    client = OpenAI(base_url="http://localhost:8080/v1", api_key="none", timeout=60)
    tools = [
        {"type": "function", "function": {
            "name": f"tool_{i}",
            "description": f"Tool {i}",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
        }}
        for i in range(5)
    ]
    t = time.time()
    try:
        resp = client.chat.completions.create(
            model="Ornith-1.5-35B-A3B",
            messages=[{"role": "user", "content": "Use tool_2 to get info"}],
            tools=tools,
            tool_choice="auto",
            max_tokens=100,
        )
        print(f"  time={time.time()-t:.1f}s")
        print(f"  tool_calls: {[(tc.function.name, tc.function.arguments) for tc in (resp.choices[0].message.tool_calls or [])]}")
        print("  OK")
    except Exception as e:
        print(f"  FAIL: {e}")


async def test_mcp_searxng():
    print("\n=== TEST 4: MCP searxng search ===")
    params = StdioServerParameters(
        command="/opt/search/venv/bin/python",
        args=["/opt/search/src/mcp_searxng_server.py"],
        env={"SEARXNG_URL": "http://localhost:8888", "PATH": "/usr/bin:/bin", "SEARXNG_LANG": "en"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r = await session.call_tool("search", {"query": "python", "max_results": 2, "engines": "wikipedia"})
            print(f"  isError: {r.isError}")
            for c in r.content[:2]:
                if hasattr(c, "text") and c.text:
                    try:
                        d = json.loads(c.text)
                        print(f"  result: {d.get(chr(34)+chr(116)+chr(105)+chr(116)+chr(108)+chr(101)+chr(34), chr(63))[:60]}")
                    except Exception:
                        print(f"  text: {c.text[:100]}")
            print("  OK")


async def test_mcp_playwright():
    print("\n=== TEST 5: MCP playwright navigate ===")
    params = StdioServerParameters(
        command="/opt/node20/bin/node",
        args=["/opt/search/node_modules/@playwright/mcp/cli.js", "--headless", "--isolated", "--no-sandbox"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r = await session.call_tool("browser_navigate", {"url": "https://example.com"})
            print(f"  isError: {r.isError}")
            print("  OK")


def main():
    test_llama_basic()
    test_llama_with_one_tool()
    test_llama_with_many_tools()
    asyncio.run(test_mcp_searxng())
    asyncio.run(test_mcp_playwright())


if __name__ == "__main__":
    main()
