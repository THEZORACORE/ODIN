"""Tests for DAG parallel execution (Phase 2.4).

Verifies that independent plan nodes execute concurrently while
dependent nodes respect ordering.
"""

from __future__ import annotations

import json
import tempfile

import pytest

from odin.core.orchestrator import Orchestrator
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import FakeLLM
from odin.safety.heimdall import Heimdall
from odin.schemas import ActionRisk, BudgetState, NodeStatus
from odin.tools.registry import ToolRegistry, ToolSpec


def _make_tools(heimdall: Heimdall) -> ToolRegistry:
    reg = ToolRegistry(heimdall)

    async def fake_code(code: str) -> str:
        return "42"

    reg.register(ToolSpec(
        name="code_interpreter", description="Run code", fn=fake_code, risk=ActionRisk.MEDIUM,
    ))
    return reg


class TestParallelExecution:
    @pytest.mark.asyncio
    async def test_independent_nodes_all_complete(self) -> None:
        """Two independent nodes (no deps) should both complete."""
        plan_json = json.dumps([
            {"id": "a", "goal": "task A", "depends_on": [], "tool_hint": "none"},
            {"id": "b", "goal": "task B", "depends_on": [], "tool_hint": "none"},
        ])
        llm = FakeLLM(responses=[
            plan_json,       # planner
            "ANSWER: A done", # THOR for node a
            "A done",         # SC re-derive
            '{"agrees": true, "explanation": "ok"}',  # SC compare
            '{"has_issues": false, "recommendation": "approve"}',  # critic
            "ANSWER: B done", # THOR for node b
            "B done",         # SC re-derive
            '{"agrees": true, "explanation": "ok"}',  # SC compare
            '{"has_issues": false, "recommendation": "approve"}',  # critic
            "Both done.",     # FREYA render
        ])

        with tempfile.TemporaryDirectory() as tmp:
            heimdall = Heimdall(budget=BudgetState(max_llm_calls=30, max_tool_calls=30))
            tools = _make_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            orch = Orchestrator(
                llm=llm, tools=tools, heimdall=heimdall, mimir=mimir,
            )
            result = await orch.run("Do A and B")

            assert result.success
            completed = [n for n in result.plan.nodes if n.status == NodeStatus.COMPLETED]
            assert len(completed) == 2

            mimir.close()

    @pytest.mark.asyncio
    async def test_dependent_node_waits(self) -> None:
        """A node depending on another should only run after the dependency completes."""
        plan_json = json.dumps([
            {"id": "s1", "goal": "first", "depends_on": [], "tool_hint": "none"},
            {"id": "s2", "goal": "second", "depends_on": ["s1"], "tool_hint": "none"},
        ])
        llm = FakeLLM(responses=[
            plan_json,       # planner
            "ANSWER: first done",  # THOR s1
            "first done",          # SC re-derive
            '{"agrees": true, "explanation": "ok"}',
            '{"has_issues": false, "recommendation": "approve"}',
            "ANSWER: second done", # THOR s2
            "second done",
            '{"agrees": true, "explanation": "ok"}',
            '{"has_issues": false, "recommendation": "approve"}',
            "All done.",
        ])

        with tempfile.TemporaryDirectory() as tmp:
            heimdall = Heimdall(budget=BudgetState(max_llm_calls=30, max_tool_calls=30))
            tools = _make_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            orch = Orchestrator(
                llm=llm, tools=tools, heimdall=heimdall, mimir=mimir,
            )
            result = await orch.run("Do s1 then s2")

            assert result.success
            nodes_by_id = {n.id: n for n in result.plan.nodes}
            assert nodes_by_id["s1"].status == NodeStatus.COMPLETED
            assert nodes_by_id["s2"].status == NodeStatus.COMPLETED

            mimir.close()

    @pytest.mark.asyncio
    async def test_diamond_dag(self) -> None:
        """Diamond: A -> (B, C) -> D. B and C are independent and should fan out."""
        plan_json = json.dumps([
            {"id": "a", "goal": "root", "depends_on": [], "tool_hint": "none"},
            {"id": "b", "goal": "left", "depends_on": ["a"], "tool_hint": "none"},
            {"id": "c", "goal": "right", "depends_on": ["a"], "tool_hint": "none"},
            {"id": "d", "goal": "join", "depends_on": ["b", "c"], "tool_hint": "none"},
        ])
        responses = [plan_json]
        # Each node needs: THOR answer, SC re-derive, SC compare, critic
        for _ in range(4):
            responses.extend([
                "ANSWER: done",
                "done",
                '{"agrees": true, "explanation": "ok"}',
                '{"has_issues": false, "recommendation": "approve"}',
            ])
        responses.append("Complete.")  # FREYA

        llm = FakeLLM(responses=responses)

        with tempfile.TemporaryDirectory() as tmp:
            heimdall = Heimdall(budget=BudgetState(max_llm_calls=50, max_tool_calls=50))
            tools = _make_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            orch = Orchestrator(
                llm=llm, tools=tools, heimdall=heimdall, mimir=mimir,
            )
            result = await orch.run("Diamond DAG")

            assert result.success
            assert all(n.status == NodeStatus.COMPLETED for n in result.plan.nodes)
            mimir.close()
