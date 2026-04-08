"""FuzzForge MCP Tools."""

from fastmcp import FastMCP

from fuzzforge_mcp.tools import hub, projects, reports

mcp: FastMCP = FastMCP()

mcp.mount(projects.mcp)
mcp.mount(hub.mcp)
mcp.mount(reports.mcp)

__all__ = [
    "mcp",
]

