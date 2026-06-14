"""Tool registry — function-calling interface for ODIN agents.

All tool calls route through HEIMDALL before execution.
Tools register themselves with name, description, and a callable.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from odin.safety.heimdall import Heimdall, make_tool_result_from_error
from odin.schemas import (
    ActionRisk,
    AgentRole,
    ToolRequest,
    ToolResult,
)

ToolCallable = Callable[..., Awaitable[str]]


class ToolSpec:
    """Metadata + callable for a registered tool."""

    def __init__(
        self,
        name: str,
        description: str,
        fn: ToolCallable,
        risk: ActionRisk = ActionRisk.LOW,
        parameter_schema: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.fn = fn
        self.risk = risk
        self.parameter_schema = parameter_schema or {}


class ToolRegistry:
    """Central tool registry.  Agents request tools; Heimdall gates them."""

    def __init__(self, heimdall: Heimdall) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._heimdall = heimdall

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get_tool_descriptions(self) -> list[dict[str, Any]]:
        """Return tool metadata for LLM function-calling prompts."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameter_schema,
                "risk": t.risk.value,
            }
            for t in self._tools.values()
        ]

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        requester: AgentRole,
    ) -> ToolResult:
        """Gate through Heimdall, then execute."""
        spec = self._tools.get(tool_name)
        if spec is None:
            return ToolResult(
                request_id="unknown",
                tool_name=tool_name,
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}",
            )

        request = ToolRequest(
            tool_name=tool_name,
            arguments=arguments,
            requester=requester,
            risk_level=spec.risk,
        )

        try:
            self._heimdall.gate(request)
        except Exception as e:
            return make_tool_result_from_error(request, e)

        t0 = time.monotonic()
        try:
            output = await spec.fn(**arguments)
            elapsed = time.monotonic() - t0
            return ToolResult(
                request_id=request.id,
                tool_name=tool_name,
                success=True,
                output=output,
                execution_time_seconds=elapsed,
            )
        except Exception as e:
            elapsed = time.monotonic() - t0
            return ToolResult(
                request_id=request.id,
                tool_name=tool_name,
                success=False,
                output="",
                error=f"{type(e).__name__}: {e}",
                execution_time_seconds=elapsed,
            )
