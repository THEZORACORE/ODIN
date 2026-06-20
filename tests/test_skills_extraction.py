"""Tests for skill extraction from successful runs (Phase 3.1)."""

from __future__ import annotations

from odin.schemas import NodeStatus, PlanDAG, PlanNode
from odin.skills.extraction import extract_skill


class TestExtractSkill:
    def test_extracts_from_completed_plan(self) -> None:
        plan = PlanDAG(
            goal="research Python async patterns and summarize",
            nodes=[
                PlanNode(id="s1", goal="search web for async patterns", status=NodeStatus.COMPLETED, tool_hint="web_search"),
                PlanNode(id="s2", goal="summarize findings", status=NodeStatus.COMPLETED, tool_hint="none", depends_on=["s1"]),
            ],
        )
        skill = extract_skill(plan)
        assert skill is not None
        assert skill.name == "research Python async patterns and summarize"
        assert skill.description == plan.goal
        assert skill.steps == ["search web for async patterns", "summarize findings"]
        assert "web_search" in skill.tools_used
        assert "none" in skill.tools_used
        assert skill.preconditions == ["tool:web_search"]
        assert skill.success_count == 1

    def test_skips_failed_nodes(self) -> None:
        plan = PlanDAG(
            goal="multi-step task",
            nodes=[
                PlanNode(id="s1", goal="step one", status=NodeStatus.COMPLETED, tool_hint="code_interpreter"),
                PlanNode(id="s2", goal="step two", status=NodeStatus.FAILED, tool_hint="web_search"),
            ],
        )
        skill = extract_skill(plan)
        assert skill is not None
        assert len(skill.steps) == 1
        assert skill.steps[0] == "step one"

    def test_returns_none_when_nothing_completed(self) -> None:
        plan = PlanDAG(
            goal="doomed task",
            nodes=[
                PlanNode(id="s1", goal="fail", status=NodeStatus.FAILED),
            ],
        )
        assert extract_skill(plan) is None

    def test_multi_step_tag(self) -> None:
        plan = PlanDAG(
            goal="big task",
            nodes=[
                PlanNode(id=f"s{i}", goal=f"step {i}", status=NodeStatus.COMPLETED)
                for i in range(5)
            ],
        )
        skill = extract_skill(plan)
        assert skill is not None
        assert "multi_step" in skill.tags

    def test_deduplicates_tools(self) -> None:
        plan = PlanDAG(
            goal="code task",
            nodes=[
                PlanNode(id="s1", goal="write code", status=NodeStatus.COMPLETED, tool_hint="code_interpreter"),
                PlanNode(id="s2", goal="test code", status=NodeStatus.COMPLETED, tool_hint="code_interpreter"),
            ],
        )
        skill = extract_skill(plan)
        assert skill is not None
        assert skill.tools_used.count("code_interpreter") == 1
