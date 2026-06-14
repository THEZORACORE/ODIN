"""Tests for tools — code interpreter, web search, registry."""

import pytest

from odin.safety.heimdall import Heimdall
from odin.schemas import ActionRisk, AgentRole, BudgetState
from odin.tools.code_interpreter import execute_python
from odin.tools.registry import ToolRegistry, ToolSpec
from odin.tools.web_search import MockSearchAdapter, SearchResult, web_search


class TestCodeInterpreter:
    @pytest.mark.asyncio
    async def test_simple_execution(self) -> None:
        result = await execute_python("print(2 + 2)")
        assert "4" in result

    @pytest.mark.asyncio
    async def test_multiline(self) -> None:
        code = "x = 10\ny = 20\nprint(x + y)"
        result = await execute_python(code)
        assert "30" in result

    @pytest.mark.asyncio
    async def test_error_captured(self) -> None:
        result = await execute_python("raise ValueError('test error')")
        assert "ValueError" in result

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        result = await execute_python("import time; time.sleep(60)", timeout=2)
        assert "TIMEOUT" in result

    @pytest.mark.asyncio
    async def test_no_output(self) -> None:
        result = await execute_python("x = 1")
        assert result == "[No output]"


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_mock_search(self) -> None:
        result = await web_search("test query")
        assert "test query" in result
        assert "Mock result" in result

    @pytest.mark.asyncio
    async def test_custom_mock_results(self) -> None:
        from odin.tools.web_search import set_search_adapter
        adapter = MockSearchAdapter(results=[
            SearchResult(title="Custom", url="https://custom.com", snippet="Custom result"),
        ])
        set_search_adapter(adapter)
        result = await web_search("custom")
        assert "Custom" in result
        # Reset to default
        set_search_adapter(MockSearchAdapter())


class TestToolRegistry:
    @pytest.mark.asyncio
    async def test_execute_registered_tool(self) -> None:
        h = Heimdall()
        reg = ToolRegistry(h)

        async def my_tool(x: str) -> str:
            return f"result: {x}"

        reg.register(ToolSpec(
            name="web_search",
            description="test",
            fn=my_tool,
            risk=ActionRisk.LOW,
        ))
        result = await reg.execute("web_search", {"x": "hello"}, AgentRole.THOR)
        assert result.success
        assert result.output == "result: hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self) -> None:
        h = Heimdall()
        reg = ToolRegistry(h)
        result = await reg.execute("nonexistent", {}, AgentRole.THOR)
        assert not result.success
        assert "Unknown tool" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_blocked_by_heimdall(self) -> None:
        budget = BudgetState(max_tool_calls=0)
        h = Heimdall(budget=budget)
        reg = ToolRegistry(h)

        async def dummy() -> str:
            return "ok"

        reg.register(ToolSpec(name="web_search", description="test", fn=dummy))
        result = await reg.execute("web_search", {}, AgentRole.THOR)
        assert not result.success
        assert "BudgetExhausted" in (result.error or "")
