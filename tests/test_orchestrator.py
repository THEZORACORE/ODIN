"""Tests for the orchestration loop — the heart of ODIN.

Covers:
- Happy-path: plan → execute → verify → commit → render
- Failed verification → revise
- Budget exhaustion
- Cross-session memory persistence
"""

import json
import tempfile

import pytest

from odin.core.orchestrator import Orchestrator
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import FakeLLM
from odin.safety.heimdall import Heimdall
from odin.schemas import ActionRisk, BudgetState
from odin.tools.registry import ToolRegistry, ToolSpec
from odin.tools.web_search import web_search


def _make_tools(heimdall: Heimdall) -> ToolRegistry:
    """Register minimal tool set for testing."""
    reg = ToolRegistry(heimdall)

    async def fake_code(code: str) -> str:
        return "42"

    reg.register(ToolSpec(
        name="code_interpreter", description="Run code", fn=fake_code, risk=ActionRisk.MEDIUM,
    ))
    reg.register(ToolSpec(
        name="web_search", description="Search web", fn=web_search, risk=ActionRisk.LOW,
    ))
    return reg


class TestOrchestratorHappyPath:
    @pytest.mark.asyncio
    async def test_simple_goal(self) -> None:
        """End-to-end: plan a simple goal, execute, verify, render."""
        plan_json = json.dumps([
            {"id": "step_1", "goal": "Calculate 6*7", "depends_on": [], "tool_hint": "code_interpreter"},
        ])
        llm = FakeLLM(responses=[
            plan_json,  # ODIN planner
            "REASONING: Simple multiplication\nTOOL: code_interpreter\nTOOL_INPUT: print(6*7)\nANSWER: 42",  # THOR
            "42",  # THOR follow-up with tool output
            "42",  # Self-consistency re-derive
            '{"agrees": true, "explanation": "Both say 42"}',  # SC comparison
            '{"has_issues": false, "issues": [], "recommendation": "approve"}',  # Critic
            "The answer is 42. [Source: code_interpreter]",  # FREYA render
        ])

        with tempfile.TemporaryDirectory() as tmp:
            heimdall = Heimdall(budget=BudgetState(max_llm_calls=20, max_tool_calls=20))
            tools = _make_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            orch = Orchestrator(
                llm=llm, tools=tools, heimdall=heimdall, mimir=mimir,
                session_id="test_session",
            )
            result = await orch.run("Calculate 6 times 7")

            assert result.success
            assert len(result.plan.nodes) >= 1
            assert result.session_id == "test_session"
            mimir.close()


class TestFailedVerificationRevise:
    @pytest.mark.asyncio
    async def test_retry_on_verification_failure(self) -> None:
        """When verification fails, ODIN should retry (bounded)."""
        plan_json = json.dumps([
            {"id": "step_1", "goal": "Calculate something", "depends_on": [], "tool_hint": "code_interpreter"},
        ])
        llm = FakeLLM(responses=[
            plan_json,  # Plan
            # Attempt 1: execute + verify (fail)
            "ANSWER: wrong answer",  # THOR
            "correct answer",  # SC re-derive
            '{"agrees": false, "explanation": "Mismatch"}',  # SC comparison → FAIL
            '{"has_issues": true, "issues": ["Wrong"], "recommendation": "reject"}',  # Critic → FAIL
            # Attempt 2: execute + verify (pass)
            "ANSWER: correct answer",  # THOR retry
            "correct answer",  # SC re-derive
            '{"agrees": true, "explanation": "Match"}',  # SC comparison → PASS
            '{"has_issues": false, "issues": [], "recommendation": "approve"}',  # Critic → PASS
            "Final answer is correct. [Source: calculation]",  # FREYA
        ])

        with tempfile.TemporaryDirectory() as tmp:
            heimdall = Heimdall(budget=BudgetState(max_llm_calls=30, max_tool_calls=30))
            tools = _make_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            orch = Orchestrator(
                llm=llm, tools=tools, heimdall=heimdall, mimir=mimir,
            )
            result = await orch.run("Calculate something")

            # Should have retried and eventually succeeded
            assert result.success or len(result.verdicts) > 0
            # At least some verdicts should exist
            assert len(result.verdicts) >= 2
            mimir.close()


class TestBudgetExhaustion:
    @pytest.mark.asyncio
    async def test_stops_on_budget_exhaustion(self) -> None:
        """Orchestrator must stop when budget is exhausted."""
        plan_json = json.dumps([
            {"id": "s1", "goal": "Step 1", "depends_on": []},
            {"id": "s2", "goal": "Step 2", "depends_on": ["s1"]},
            {"id": "s3", "goal": "Step 3", "depends_on": ["s2"]},
        ])
        llm = FakeLLM(responses=[plan_json, "ANSWER: result"] * 10)

        with tempfile.TemporaryDirectory() as tmp:
            budget = BudgetState(
                max_llm_calls=3,  # Low LLM call limit triggers budget exhaustion
                max_tool_calls=1000,
                max_wall_clock_seconds=60,
            )
            heimdall = Heimdall(budget=budget)
            tools = _make_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            orch = Orchestrator(
                llm=llm, tools=tools, heimdall=heimdall, mimir=mimir,
            )
            result = await orch.run("Multi-step goal")

            assert not result.success
            assert "BUDGET EXHAUSTED" in result.answer
            mimir.close()


class TestCrossSessionMemory:
    @pytest.mark.asyncio
    async def test_memory_persists_across_runs(self) -> None:
        """Memories from one run should be readable in the next."""
        plan_json = json.dumps([
            {"id": "s1", "goal": "Remember this fact", "depends_on": []},
        ])

        with tempfile.TemporaryDirectory() as tmp:
            # Run 1: store a memory
            llm1 = FakeLLM(responses=[
                plan_json,
                "ANSWER: The important fact is X=42",
                "X=42",
                '{"agrees": true, "explanation": "Match"}',
                '{"has_issues": false, "recommendation": "approve"}',
                "Result: X=42",
            ])
            budget1 = BudgetState(max_llm_calls=20, max_tool_calls=20)
            heimdall1 = Heimdall(budget=budget1)
            tools1 = _make_tools(heimdall1)
            mimir1 = Mimir(data_dir=tmp, llm=llm1, use_chroma=False)
            orch1 = Orchestrator(
                llm=llm1, tools=tools1, heimdall=heimdall1, mimir=mimir1,
                session_id="session_1",
            )
            await orch1.run("Find X")
            mimir1.save()
            mimir1.close()

            # Run 2: verify memory exists
            mimir2 = Mimir(data_dir=tmp, use_chroma=False)
            sess_memories = mimir2.get_session_memories("session_1")
            assert len(sess_memories) >= 1
            # Check that the reflection was stored
            assert "session_1" in (sess_memories[0].session_id or "")
            mimir2.close()
