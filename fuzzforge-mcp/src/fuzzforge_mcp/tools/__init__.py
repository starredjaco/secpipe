"""FuzzForge MCP Tools."""

from fastmcp import FastMCP

from fuzzforge_mcp.tools import hub, modules, projects, workflows

mcp: FastMCP = FastMCP()

mcp.mount(modules.mcp)
mcp.mount(projects.mcp)
mcp.mount(workflows.mcp)
mcp.mount(hub.mcp)

__all__ = [
    "mcp",
]

