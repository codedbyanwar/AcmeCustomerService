"""MCP-protocol entrypoint for the Sales runtime.

AgentCore exposes an MCP runtime's tools through a gateway `httpRuntime` target.
Customer Service (via the gateway) discovers and calls the `sales` tool here,
which drives the existing Strands Sales agent and returns its reply.

Run locally:  python mcp_server.py   (serves MCP on http://0.0.0.0:8000/mcp)
Deployed:     protocol=MCP runtime; the gateway advertises `sales` as a tool.
"""

from mcp.server.fastmcp import FastMCP

from main import get_or_create_agent

# AgentCore MCP runtimes must bind 0.0.0.0:8000 and serve stateless streamable HTTP.
mcp = FastMCP(host="0.0.0.0", port=8000, stateless_http=True)


@mcp.tool()
def sales(prompt: str) -> str:
    """Handle an Acme Telco Sales request: re-contracting, device offers,
    discount negotiation (with manager approval), OTP verification, and order
    placement. Pass the customer's full request (and any account/device/discount
    context) as `prompt`. Returns the Sales agent's reply.
    """
    agent = get_or_create_agent()
    result = agent(prompt)
    # Strands Agent result -> plain text.
    try:
        return result.message["content"][0]["text"]
    except Exception:
        return str(result)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
