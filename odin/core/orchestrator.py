"""Orchestration loop — the beating heart of ODIN.

Implements the full cycle from the spec:
plan → schedule → delegate → verify → commit/revise → reflect → consolidate

Bounded retries at every stage.  Budget-checked throughout.
No runaway loops — recursion depth and wall-clock are capped.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from odin.agents.freya_renderer import FreyaRenderer
from odin.agents.loki_critic import LokiCritic
from odin.agents.odin_planner import OdinPlanner
from odin.agents.thor_executor import ThorExecutor
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import LLMAdapter, TrackedLLM
from odin.safety.heimdall import BudgetExhausted, Heimdall
from odin.schemas import (
    BudgetState,
    NodeStatus,
    PlanDAG,
    PlanNode,
    VerdictRecord,
    VerifyOutcome,
)
from odin.skills.extraction import extract_skill
from odin.skills.reflection import build_reflection
from odin.skills.store import SkillStore
from odin.tools.registry import ToolRegistry
from odin.verify.verifier import Verifier, aggregate_verdicts

logger = logging.getLogger("odin.orchestrator")


class OrchestratorResult:
    """Final output of an orchestration run."""

    def __init__(
        self,
        goal: str,
        answer: str,
        plan: PlanDAG,
        verdicts: list[VerdictRecord],
        budget_state: BudgetState,
        success: bool,
        session_id: str,
    ) -> None:
        self.goal = goal
        self.answer = answer
        self.plan = plan
        self.verdicts = verdicts
        self.budget_state = budget_state
        self.success = success
        self.session_id = session_id


class Orchestrator:
    """Main orchestration engine.

    Wires together ODIN (planner), THOR (executor), LOKI (critic),
    FREYA (renderer), MIMIR (memory), and HEIMDALL (safety).
    """

    MAX_PLAN_REVISIONS = 3

    def __init__(
        self,
        llm: LLMAdapter,
        tools: ToolRegistry,
        heimdall: Heimdall,
        mimir: Mimir,
        *,
        session_id: str = "default",
        budget: BudgetState | None = None,
        skill_store: SkillStore | None = None,
    ) -> None:
        self._tools = tools
        self._heimdall = heimdall
        self._mimir = mimir
        self._session_id = session_id
        self._plan_revisions = 0
        self._skill_store = skill_store
        self._revision_lock = asyncio.Lock()

        if budget:
            self._heimdall.budget = budget

        # Wrap LLM with budget-tracked proxy so ALL calls auto-record tokens
        tracked = TrackedLLM(llm, self._heimdall.budget)
        self._llm: LLMAdapter = tracked

        # Initialize agents — all share the tracked LLM
        self._planner = OdinPlanner(tracked)
        self._executor = ThorExecutor(tracked, tools)
        self._critic = LokiCritic(tracked)
        self._renderer = FreyaRenderer(tracked)
        self._verifier = Verifier(tracked)

    async def run(self, goal: str) -> OrchestratorResult:
        """Execute the full orchestration loop for a goal.

        Steps:
        1. Plan: decompose goal into a DAG
        2. Schedule: determine execution order from DAG dependencies
        3. Delegate: execute each ready node via THOR
        4. Verify: self-consistency + LOKI critic + tool-grounding
        5. Commit or Revise: accept verified results or retry
        6. Reflect: store episodic memory of what happened
        7. Consolidate: produce final answer via FREYA
        """
        logger.info("Starting orchestration for goal: %s", goal)
        all_verdicts: list[VerdictRecord] = []
        node_results: dict[str, str] = {}
        plan = PlanDAG(goal=goal)

        try:
            # --- 1. PLAN (with skill retrieval) ---
            logger.info("Phase: PLAN")
            skill_hints = None
            if self._skill_store is not None:
                skill_hints = self._skill_store.find(goal) or None
                if skill_hints:
                    logger.info("Retrieved %d matching skills for planning", len(skill_hints))
            plan = await self._planner.create_plan(goal, skill_hints=skill_hints)
            self._mimir.store_working("current_plan", plan.model_dump_json())
            logger.info("Plan created: %d nodes", len(plan.nodes))

            # --- 2-5. SCHEDULE → DELEGATE → VERIFY → COMMIT/REVISE ---
            max_iterations = len(plan.nodes) * (PlanNode.model_fields["max_retries"].default + 1) * (self.MAX_PLAN_REVISIONS + 1) + 10
            iteration = 0
            while not plan.is_complete() and not plan.has_failed():
                iteration += 1
                if iteration > max_iterations:
                    logger.warning("Max orchestration iterations reached (%d)", max_iterations)
                    break
                self._check_budget()

                ready = plan.ready_nodes()
                if not ready:
                    if plan.has_failed():
                        break
                    # Deadlock: no ready nodes, no completed path
                    logger.error("Plan deadlocked — no ready nodes")
                    break

                if len(ready) == 1:
                    await self._execute_and_verify(
                        ready[0], plan, all_verdicts, node_results
                    )
                else:
                    logger.info("Parallel fan-out: %d independent nodes", len(ready))
                    await asyncio.gather(*(
                        self._execute_and_verify(
                            node, plan, all_verdicts, node_results
                        )
                        for node in ready
                    ))

            # --- 6. REFLECT + SKILL EXTRACTION ---
            logger.info("Phase: REFLECT")
            await self._reflect(goal, plan, node_results, all_verdicts)

            if plan.is_complete() and self._skill_store is not None:
                skill = extract_skill(plan)
                if skill is not None:
                    self._skill_store.save(skill)
                    logger.info("Extracted skill: %s", skill.name)
            else:
                self._store_reflection(plan, all_verdicts)

            # --- 7. CONSOLIDATE ---
            logger.info("Phase: CONSOLIDATE")
            combined_results = "\n\n".join(
                f"[Step: {nid}]\n{res}" for nid, res in node_results.items()
            )
            answer = await self._renderer.render(
                combined_results, verdicts=all_verdicts, plan=plan
            )

            success = plan.is_complete()
            logger.info("Orchestration complete. success=%s", success)

            return OrchestratorResult(
                goal=goal,
                answer=answer,
                plan=plan,
                verdicts=all_verdicts,
                budget_state=self._heimdall.budget,
                success=success,
                session_id=self._session_id,
            )

        except BudgetExhausted as e:
            logger.warning("Budget exhausted: %s", e)
            self._store_reflection(plan, all_verdicts)
            combined = "\n\n".join(
                f"[Step: {nid}]\n{res}" for nid, res in node_results.items()
            )
            answer = (
                f"[BUDGET EXHAUSTED] Partial results:\n\n{combined}\n\n"
                f"Budget state: {e.detail}"
            )
            return OrchestratorResult(
                goal=goal,
                answer=answer,
                plan=plan,
                verdicts=all_verdicts,
                budget_state=self._heimdall.budget,
                success=False,
                session_id=self._session_id,
            )

    async def _execute_and_verify(
        self,
        node: PlanNode,
        plan: PlanDAG,
        all_verdicts: list[VerdictRecord],
        node_results: dict[str, str],
    ) -> bool:
        """Execute a single node with the verify→commit/revise loop.

        Returns True if execution should continue, False if plan has failed.
        """
        node.status = NodeStatus.IN_PROGRESS
        node.updated_at = datetime.now(UTC)
        logger.info("Executing node %s: %s", node.id, node.goal)

        while node.retries <= node.max_retries:
            self._check_budget()

            # --- DELEGATE ---
            try:
                result = await self._executor.execute_node(node)
            except Exception as e:
                result = f"Execution error: {e}"

            # --- VERIFY ---
            self._check_budget()
            logger.info("Verifying node %s (attempt %d)", node.id, node.retries + 1)
            verdicts = await self._verify_result(node, result)
            all_verdicts.extend(verdicts)
            self._check_budget()
            outcome = aggregate_verdicts(verdicts)

            if outcome == VerifyOutcome.PASS:
                # --- COMMIT ---
                node.status = NodeStatus.COMPLETED
                node.result = result
                node.updated_at = datetime.now(UTC)
                node_results[node.id] = result
                logger.info("Node %s verified and committed", node.id)
                return True

            elif outcome == VerifyOutcome.FAIL:
                # --- REVISE ---
                node.retries += 1
                if node.retries > node.max_retries:
                    node.status = NodeStatus.FAILED
                    node.result = f"Failed after {node.max_retries} retries. Last: {result}"
                    node.updated_at = datetime.now(UTC)
                    node_results[node.id] = node.result
                    logger.warning("Node %s failed after max retries", node.id)

                    # Try plan revision (bounded, serialised under lock)
                    async with self._revision_lock:
                        if self._plan_revisions < self.MAX_PLAN_REVISIONS:
                            error = "; ".join(v.explanation for v in verdicts if v.outcome == VerifyOutcome.FAIL)
                            try:
                                plan = await self._planner.revise_plan(plan, node, error)
                                self._plan_revisions += 1
                                logger.info("Plan revised after node %s failure (%d/%d)", node.id, self._plan_revisions, self.MAX_PLAN_REVISIONS)
                            except Exception:
                                logger.error("Plan revision failed for node %s", node.id)
                        else:
                            logger.warning("Max plan revisions reached (%d), not revising", self.MAX_PLAN_REVISIONS)
                    return True  # Continue with other nodes

                logger.info("Node %s failed verification, retrying (%d/%d)", node.id, node.retries, node.max_retries)

            else:
                # UNCERTAIN — accept with caveat
                node.status = NodeStatus.COMPLETED
                node.result = f"[UNCERTAIN] {result}"
                node.updated_at = datetime.now(UTC)
                node_results[node.id] = node.result
                logger.info("Node %s accepted with UNCERTAIN verdict", node.id)
                return True

        return True

    async def _verify_result(
        self, node: PlanNode, result: str
    ) -> list[VerdictRecord]:
        """Run verification strategies on a node result.

        Adaptive depth (spec §4.1): skip self-consistency on trivial nodes
        (tool_hint="none", e.g. summarization steps) to reduce verification
        cost.  Self-consistency is most valuable for tool-using nodes where
        the LLM might hallucinate about tool output.
        """
        code = None
        if node.tool_hint == "code_interpreter" and "```python" in result:
            lines = result.split("```python")
            if len(lines) > 1:
                code_block = lines[1].split("```")[0]
                code = code_block.strip()

        # Adaptive: skip self-consistency for non-tool summarization nodes
        skip_self_consistency = node.tool_hint in ("none", None, "")
        return await self._verifier.verify_all(
            node_id=node.id,
            question=node.goal,
            answer=result,
            code=code,
            skip_self_consistency=skip_self_consistency,
        )

    async def _reflect(
        self,
        goal: str,
        plan: PlanDAG,
        results: dict[str, str],
        verdicts: list[VerdictRecord],
    ) -> None:
        """Store episodic memory of this run."""
        summary_parts = [f"Goal: {goal}"]
        for node in plan.nodes:
            status = node.status.value
            result_preview = (results.get(node.id, "N/A"))[:200]
            summary_parts.append(f"  [{status}] {node.goal}: {result_preview}")

        verdict_summary = f"\nVerification: {len(verdicts)} checks, " + \
            f"pass={sum(1 for v in verdicts if v.outcome == VerifyOutcome.PASS)}, " + \
            f"fail={sum(1 for v in verdicts if v.outcome == VerifyOutcome.FAIL)}"
        summary_parts.append(verdict_summary)

        self._mimir.store_episodic(
            content="\n".join(summary_parts),
            source_type="orchestrator",
            source_id=f"run_{self._session_id}",
            tags=["orchestration_run", "reflection"],
            session_id=self._session_id,
        )

    def _store_reflection(
        self, plan: PlanDAG, verdicts: list[VerdictRecord]
    ) -> None:
        """Store a post-mortem for a failed/partial run."""
        if plan.has_failed() or not plan.is_complete():
            reflection = build_reflection(plan, verdicts, session_id=self._session_id)
            self._mimir.store(reflection)
            logger.info("Stored reflection memory for failed run")

    def _check_budget(self) -> None:
        if self._heimdall.budget.is_exhausted():
            raise BudgetExhausted("Budget check failed during orchestration")
