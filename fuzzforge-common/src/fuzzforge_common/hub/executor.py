"""Hub executor for managing MCP server lifecycle and tool execution.

This module provides a high-level interface for:
- Discovering tools from all registered hub servers
- Executing tools with proper error handling
- Managing the lifecycle of hub operations

"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fuzzforge_common.hub.client import HubClient, HubClientError
from fuzzforge_common.hub.models import HubServer, HubServerConfig, HubTool
from fuzzforge_common.hub.registry import HubRegistry

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


def get_logger() -> BoundLogger:
    """Get structlog logger instance.

    :returns: Configured structlog logger.

    """
    from structlog import get_logger  # noqa: PLC0415

    return cast("BoundLogger", get_logger())


class HubExecutionResult:
    """Result of a hub tool execution."""

    def __init__(
        self,
        *,
        success: bool,
        server_name: str,
        tool_name: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Initialize execution result.

        :param success: Whether execution succeeded.
        :param server_name: Name of the hub server.
        :param tool_name: Name of the executed tool.
        :param result: Tool execution result data.
        :param error: Error message if execution failed.

        """
        self.success = success
        self.server_name = server_name
        self.tool_name = tool_name
        self.result = result or {}
        self.error = error

    @property
    def identifier(self) -> str:
        """Get full tool identifier."""
        return f"hub:{self.server_name}:{self.tool_name}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        :returns: Dictionary representation.

        """
        return {
            "success": self.success,
            "identifier": self.identifier,
            "server": self.server_name,
            "tool": self.tool_name,
            "result": self.result,
            "error": self.error,
        }


class HubExecutor:
    """Executor for hub server operations.

    Provides high-level methods for discovering and executing
    tools from hub servers.

    """

    #: Hub registry instance.
    _registry: HubRegistry

    #: MCP client instance.
    _client: HubClient

    def __init__(
        self,
        config_path: Path | None = None,
        timeout: int = 300,
    ) -> None:
        """Initialize the hub executor.

        :param config_path: Path to hub-servers.json config file.
        :param timeout: Default timeout for tool execution.

        """
        self._registry = HubRegistry(config_path)
        self._client = HubClient(timeout=timeout)

    @property
    def registry(self) -> HubRegistry:
        """Get the hub registry.

        :returns: Hub registry instance.

        """
        return self._registry

    def add_server(self, config: HubServerConfig) -> HubServer:
        """Add a server to the registry.

        :param config: Server configuration.
        :returns: Created HubServer instance.

        """
        return self._registry.add_server(config)

    async def discover_all_tools(self) -> dict[str, list[HubTool]]:
        """Discover tools from all enabled servers.

        :returns: Dict mapping server names to lists of discovered tools.

        """
        logger = get_logger()
        results: dict[str, list[HubTool]] = {}

        for server in self._registry.enabled_servers:
            try:
                tools = await self._client.discover_tools(server)
                self._registry.update_server_tools(server.name, tools)
                results[server.name] = tools

            except HubClientError as e:
                logger.warning(
                    "Failed to discover tools",
                    server=server.name,
                    error=str(e),
                )
                self._registry.update_server_tools(server.name, [], error=str(e))
                results[server.name] = []

        return results

    async def discover_server_tools(self, server_name: str) -> list[HubTool]:
        """Discover tools from a specific server.

        :param server_name: Name of the server.
        :returns: List of discovered tools.
        :raises ValueError: If server not found.

        """
        server = self._registry.get_server(server_name)
        if not server:
            msg = f"Server '{server_name}' not found"
            raise ValueError(msg)

        try:
            tools = await self._client.discover_tools(server)
            self._registry.update_server_tools(server_name, tools)
            return tools

        except HubClientError as e:
            self._registry.update_server_tools(server_name, [], error=str(e))
            raise

    async def execute_tool(
        self,
        identifier: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> HubExecutionResult:
        """Execute a hub tool.

        :param identifier: Tool identifier (hub:server:tool or server:tool).
        :param arguments: Tool arguments.
        :param timeout: Execution timeout.
        :returns: Execution result.

        """
        logger = get_logger()
        arguments = arguments or {}

        # Parse identifier and find tool
        server, tool = self._registry.find_tool(identifier)

        if not server or not tool:
            # Try to parse as server:tool and discover
            parts = identifier.replace("hub:", "").split(":")
            if len(parts) == 2:  # noqa: PLR2004
                server_name, tool_name = parts
                server = self._registry.get_server(server_name)

                if server and not server.discovered:
                    # Try to discover tools first
                    try:
                        await self.discover_server_tools(server_name)
                        tool = server.get_tool(tool_name)
                    except HubClientError:
                        pass

                if server and not tool:
                    # Tool not found, but server exists - try to execute anyway
                    # The server might have the tool even if discovery failed
                    tool_name_to_use = tool_name
                else:
                    tool_name_to_use = tool.name if tool else ""

                if not server:
                    return HubExecutionResult(
                        success=False,
                        server_name=server_name,
                        tool_name=tool_name,
                        error=f"Server '{server_name}' not found",
                    )

                # Execute even if tool wasn't discovered (server might still have it)
                try:
                    result = await self._client.execute_tool(
                        server,
                        tool_name_to_use or tool_name,
                        arguments,
                        timeout=timeout,
                    )
                    return HubExecutionResult(
                        success=True,
                        server_name=server.name,
                        tool_name=tool_name_to_use or tool_name,
                        result=result,
                    )
                except HubClientError as e:
                    return HubExecutionResult(
                        success=False,
                        server_name=server.name,
                        tool_name=tool_name_to_use or tool_name,
                        error=str(e),
                    )
            else:
                return HubExecutionResult(
                    success=False,
                    server_name="unknown",
                    tool_name=identifier,
                    error=f"Invalid tool identifier: {identifier}",
                )

        # Execute the tool
        logger.info(
            "Executing hub tool",
            server=server.name,
            tool=tool.name,
            arguments=arguments,
        )

        try:
            result = await self._client.execute_tool(
                server,
                tool.name,
                arguments,
                timeout=timeout,
            )
            return HubExecutionResult(
                success=True,
                server_name=server.name,
                tool_name=tool.name,
                result=result,
            )

        except HubClientError as e:
            return HubExecutionResult(
                success=False,
                server_name=server.name,
                tool_name=tool.name,
                error=str(e),
            )

    def list_servers(self) -> list[dict[str, Any]]:
        """List all registered servers with their status.

        :returns: List of server info dicts.

        """
        servers = []
        for server in self._registry.servers:
            servers.append({
                "name": server.name,
                "identifier": server.identifier,
                "type": server.config.type.value,
                "enabled": server.config.enabled,
                "category": server.config.category,
                "description": server.config.description,
                "discovered": server.discovered,
                "tool_count": len(server.tools),
                "error": server.discovery_error,
            })
        return servers

    def list_tools(self) -> list[dict[str, Any]]:
        """List all discovered tools.

        :returns: List of tool info dicts.

        """
        tools = []
        for tool in self._registry.get_all_tools():
            tools.append({
                "identifier": tool.identifier,
                "name": tool.name,
                "server": tool.server_name,
                "description": tool.description,
                "parameters": [p.model_dump() for p in tool.parameters],
            })
        return tools

    def get_tool_schema(self, identifier: str) -> dict[str, Any] | None:
        """Get the JSON Schema for a tool's input.

        :param identifier: Tool identifier.
        :returns: JSON Schema dict or None if not found.

        """
        _, tool = self._registry.find_tool(identifier)
        if tool:
            return tool.input_schema
        return None
