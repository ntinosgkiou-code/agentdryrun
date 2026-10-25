"""Integration check (not part of `unittest discover`): agentdryrun's mcp-record between the OFFICIAL MCP Python SDK client and a
server written with the official SDK. Needs `pip install mcp`. Run:  python tests/integration/mcp_sdk_check.py

It fails (exit 1) unless the client gets correct tool results through the proxy AND both calls are recorded."""
import asyncio
import json
import os
import sys
import tempfile
from importlib.metadata import version

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVER = '''
try:
    from mcp.server.mcpserver import MCPServer as _Server      # mcp 2.x
except ImportError:
    from mcp.server.fastmcp import FastMCP as _Server           # mcp 1.x
mcp = _Server("demo")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp.tool()
def send_refund(customer: str, amount_eur: float) -> str:
    """Pretend to refund a customer."""
    return "refunded " + customer

if __name__ == "__main__":
    mcp.run()
'''


async def main() -> int:
    d = tempfile.mkdtemp()
    server = os.path.join(d, "server.py")
    with open(server, "w", encoding="utf-8") as f:
        f.write(SERVER)
    events = os.path.join(d, "events.jsonl")
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "agentdryrun", "mcp-record", "--out", events, "--", sys.executable, server],
                                   env=dict(os.environ, PYTHONPATH=ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            a = await s.call_tool("add", {"a": 2, "b": 3})
            b = await s.call_tool("send_refund", {"customer": "C-1", "amount_eur": 250})
    got = [json.loads(l) for l in open(events, encoding="utf-8")]
    print("mcp sdk", version("mcp"), "| tools:", tools, "| results:", a.content[0].text, "/", b.content[0].text)
    print("recorded:", [(e["tool"], e["params"]) for e in got])
    ok = (tools == ["add", "send_refund"] and a.content[0].text == "5" and b.content[0].text == "refunded C-1"
          and [(e["tool"], e["params"]) for e in got] == [("add", {"a": 2, "b": 3}), ("send_refund", {"customer": "C-1", "amount_eur": 250})])
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
