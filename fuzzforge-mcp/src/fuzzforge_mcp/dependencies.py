"""Dependency injection helpers for FuzzForge MCP."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from fastmcp.server.dependencies import get_context
from fuzzforge_runner import Runner, Settings

from fuzzforge_mcp.exceptions import FuzzForgeMCPError

if TYPE_CHECKING:
    from fastmcp import Context


def get_settings() -> Settings:
    """Get MCP server settings from context.

    :return: Settings instance.
    :raises FuzzForgeMCPError: If settings not available.

    """
    context: Context = get_context()
    if context.request_context is None:
        message: str = "Request context not available"
        raise FuzzForgeMCPError(message)
    return cast("Settings", context.request_context.lifespan_context)


def get_project_path() -> Path:
    """Get the current project path.

    :return: Path to the current project.

    """
    settings: Settings = get_settings()
    return Path(settings.project.default_path)


def get_runner() -> Runner:
    """Get a configured Runner instance.

    :return: Runner instance configured from MCP settings.

    """
    settings: Settings = get_settings()
    return Runner(settings)
