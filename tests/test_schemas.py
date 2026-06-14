"""Tests for ODIN schemas."""

from odin.schemas import (
    BudgetState,
    MemoryRecord,
    MemoryType,
    NodeStatus,
    PlanDAG,
    PlanNode,
    Provenance,
    VerdictRecord,
    VerifyOutcome,
)


class TestPlanDAG:
    def test_ready_nodes_no_deps(self) -> None:
        dag = PlanDAG(
            goal="test",
            nodes=[
                PlanNode(id="a", goal="step a"),
                PlanNode(id="b", goal="step b"),
            ],
        )
        ready = dag.ready_nodes()
        assert len(ready) == 2

    def test_ready_nodes_with_deps(self) -> None:
        dag = PlanDAG(
            goal="test",
            nodes=[
                PlanNode(id="a", goal="step a", status=NodeStatus.COMPLETED),
                PlanNode(id="b", goal="step b", depends_on=["a"]),
                PlanNode(id="c", goal="step c", depends_on=["b"]),
            ],
        )
        ready = dag.ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_is_complete(self) -> None:
        dag = PlanDAG(
            goal="test",
            nodes=[
                PlanNode(id="a", goal="a", status=NodeStatus.COMPLETED),
                PlanNode(id="b", goal="b", status=NodeStatus.COMPLETED),
            ],
        )
        assert dag.is_complete()

    def test_is_not_complete(self) -> None:
        dag = PlanDAG(
            goal="test",
            nodes=[
                PlanNode(id="a", goal="a", status=NodeStatus.COMPLETED),
                PlanNode(id="b", goal="b", status=NodeStatus.PENDING),
            ],
        )
        assert not dag.is_complete()

    def test_has_failed(self) -> None:
        dag = PlanDAG(
            goal="test",
            nodes=[
                PlanNode(id="a", goal="a", status=NodeStatus.FAILED, retries=3, max_retries=3),
            ],
        )
        assert dag.has_failed()


class TestBudgetState:
    def test_initial_not_exhausted(self) -> None:
        b = BudgetState()
        assert not b.is_exhausted()

    def test_token_exhaustion(self) -> None:
        b = BudgetState(max_tokens=100)
        b.record_llm_call(101)
        assert b.is_exhausted()

    def test_llm_call_exhaustion(self) -> None:
        b = BudgetState(max_llm_calls=2)
        b.record_llm_call(10)
        b.record_llm_call(10)
        assert b.is_exhausted()

    def test_tool_call_exhaustion(self) -> None:
        b = BudgetState(max_tool_calls=1)
        b.record_tool_call()
        assert b.is_exhausted()

    def test_depth_check(self) -> None:
        b = BudgetState(max_recursion_depth=3)
        b.current_depth = 2
        assert b.check_depth()
        b.current_depth = 3
        assert not b.check_depth()


class TestMemoryRecord:
    def test_creation_with_provenance(self) -> None:
        rec = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            content="test content",
            provenance=[Provenance(source_type="tool", source_id="web_search_1")],
        )
        assert rec.memory_type == MemoryType.EPISODIC
        assert len(rec.provenance) == 1
        assert rec.provenance[0].source_type == "tool"


class TestVerdictRecord:
    def test_creation(self) -> None:
        v = VerdictRecord(
            node_id="step_1",
            outcome=VerifyOutcome.PASS,
            method="self_consistency",
            explanation="Answers match",
        )
        assert v.outcome == VerifyOutcome.PASS
