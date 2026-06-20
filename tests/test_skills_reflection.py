"""Tests for reflection memory — post-mortems from failed runs (Phase 3.4)."""

from __future__ import annotations

from odin.schemas import (
    MemoryType,
    NodeStatus,
    PlanDAG,
    PlanNode,
    VerdictRecord,
    VerifyOutcome,
)
from odin.skills.reflection import build_reflection


class TestBuildReflection:
    def test_captures_failed_steps(self) -> None:
        plan = PlanDAG(
            goal="deploy to production",
            nodes=[
                PlanNode(id="s1", goal="build", status=NodeStatus.COMPLETED),
                PlanNode(
                    id="s2", goal="deploy", status=NodeStatus.FAILED,
                    tool_hint="code_interpreter",
                    result="timeout connecting to server",
                ),
            ],
        )
        record = build_reflection(plan, verdicts=[], session_id="sess-1")
        assert record.memory_type == MemoryType.PROCEDURAL
        assert "deploy" in record.content
        assert "timeout" in record.content
        assert record.session_id == "sess-1"
        assert "post_mortem" in record.tags

    def test_captures_failed_verdicts(self) -> None:
        plan = PlanDAG(
            goal="research task",
            nodes=[PlanNode(id="s1", goal="search", status=NodeStatus.COMPLETED)],
        )
        verdicts = [
            VerdictRecord(
                node_id="s1", outcome=VerifyOutcome.FAIL,
                method="self_consistency", explanation="answers diverged",
                confidence=0.3,
            ),
        ]
        record = build_reflection(plan, verdicts)
        assert "self_consistency" in record.content
        assert "answers diverged" in record.content

    def test_lesson_includes_tools_and_methods(self) -> None:
        plan = PlanDAG(
            goal="code task",
            nodes=[
                PlanNode(
                    id="s1", goal="write code", status=NodeStatus.FAILED,
                    tool_hint="code_interpreter", result="syntax error",
                ),
            ],
        )
        verdicts = [
            VerdictRecord(
                node_id="s1", outcome=VerifyOutcome.FAIL,
                method="tool_grounding", explanation="code failed to execute",
                confidence=0.1,
            ),
        ]
        record = build_reflection(plan, verdicts)
        assert "code_interpreter" in record.content
        assert "tool_grounding" in record.content
        assert "Lesson:" in record.content

    def test_summary_is_set(self) -> None:
        plan = PlanDAG(
            goal="a very long goal description that should be truncated in the summary",
            nodes=[PlanNode(id="s1", goal="x", status=NodeStatus.FAILED, result="err")],
        )
        record = build_reflection(plan, [])
        assert record.summary is not None
        assert record.summary.startswith("Post-mortem:")
