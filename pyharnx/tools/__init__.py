"""Built-in capabilities and the registry that declares them to the model."""

from pyharnx.tools.base import (
    AgentTool,
    ExecutionMode,
    FunctionTool,
    ToolContext,
    ToolResult,
    fail,
    ok,
    tool,
)
from pyharnx.tools.fs import FILESYSTEM_TOOLS
from pyharnx.tools.registry import ToolRegistry
from pyharnx.tools.search import SEARCH_TOOLS
from pyharnx.tools.shell import SHELL_TOOLS
from pyharnx.tools.skills import skill
from pyharnx.tools.web import WEB_TOOLS

#: Everything built in. The CLI narrows this with the configured tool list.
BUILTIN_TOOLS: tuple[AgentTool, ...] = (
    FILESYSTEM_TOOLS + SHELL_TOOLS + SEARCH_TOOLS + WEB_TOOLS + (skill,)
)


def default_registry() -> ToolRegistry:
    """A registry holding every built-in tool."""
    return ToolRegistry(BUILTIN_TOOLS)


__all__ = [
    "BUILTIN_TOOLS",
    "AgentTool",
    "ExecutionMode",
    "FunctionTool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "default_registry",
    "fail",
    "ok",
    "tool",
]
