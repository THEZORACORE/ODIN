"""ODIN — The Planner.

Decomposes high-level goals into a Plan-DAG of executable PlanNodes.
Uses the LLM to reason about task decomposition, dependency ordering,
and tool selection.

ODIN plans.  ODIN never executes.  Separation of duties.
"""

from __future__ import annotations

import json
from typing import Any

from odin.agents.base import BaseAgent
from odin.routing.llm_adapter import LLMMessage
from odin.schemas import (
    AgentMessage,
    AgentRole,
    NodeStatus,
    PlanDAG,
    PlanNode,
)

_SYSTEM_PROMPT = """\
You are ODIN, the master planner in an AI agent system. Your ONLY job is to
decompose a goal into a directed acyclic graph (DAG) of concrete, executable steps.

Rules:
- Each step must be specific enough for an executor agent (THOR) to complete.
- Identify dependencies between steps (which must finish before another can start).
- Suggest which tool each step should use: "code_interpreter" for computation/code,
  "web_search" for information retrieval, or "none" for pure reasoning.
- Do NOT execute anything. You only plan.
- Return a JSON array of steps. Each step has:
  {"id": "step_N", "goal": "...", "depends_on": ["step_X"], "tool_hint": "..."}
"""


class OdinPlanner(BaseAgent):
    """Decomposes goals into Plan-DAGs."""

    role = AgentRole.ODIN
    system_prompt = _SYSTEM_PROMPT

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Receive a goal, produce a plan."""
        plan = await self.create_plan(message.content)
        return self._make_response(
            to=AgentRole.THOR,
            content=f"Plan created with {len(plan.nodes)} steps for: {plan.goal}",
            plan=plan.model_dump(mode="json"),
        )

    async def create_plan(self, goal: str) -> PlanDAG:
        """Generate a Plan-DAG for the given goal."""
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=f"Decompose this goal into executable steps:\n\n{goal}",
            ),
        ]

        resp = await self._llm.complete(messages, temperature=0.2)

        nodes = self._parse_plan(resp.content, goal)
        return PlanDAG(goal=goal, nodes=nodes)

    def _parse_plan(self, llm_output: str, goal: str) -> list[PlanNode]:
        """Parse LLM output into PlanNodes.  Robust to formatting variation."""
        # Try JSON parse
        cleaned = llm_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            steps: list[dict[str, Any]] = json.loads(cleaned)
            if isinstance(steps, dict) and "steps" in steps:
                steps = steps["steps"]
        except json.JSONDecodeError:
            # Fallback: single-step plan
            return [
                PlanNode(id="step_1", goal=goal, tool_hint="none")
            ]

        nodes: list[PlanNode] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            node = PlanNode(
                id=str(step.get("id", f"step_{len(nodes) + 1}")),
                goal=str(step.get("goal", "")),
                depends_on=step.get("depends_on", []),
                tool_hint=step.get("tool_hint"),
                status=NodeStatus.PENDING,
            )
            nodes.append(node)

        return nodes if nodes else [PlanNode(id="step_1", goal=goal, tool_hint="none")]

    async def revise_plan(
        self,
        plan: PlanDAG,
        failed_node: PlanNode,
        error: str,
    ) -> PlanDAG:
        """Revise a plan when a step fails."""
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=(
                    f"The following plan step failed:\n"
                    f"Step: {failed_node.goal}\n"
                    f"Error: {error}\n\n"
                    f"Original goal: {plan.goal}\n"
                    f"Remaining steps: {[n.goal for n in plan.nodes if n.status == NodeStatus.PENDING]}\n\n"
                    "Revise the failed step. Return a JSON array of replacement steps."
                ),
            ),
        ]
        resp = await self._llm.complete(messages, temperature=0.2)
        new_nodes = self._parse_plan(resp.content, failed_node.goal)

        # Replace failed node with revised steps
        result_nodes: list[PlanNode] = []
        for n in plan.nodes:
            if n.id == failed_node.id:
                # Update dependencies: new nodes depend on same things
                for nn in new_nodes:
                    nn.depends_on = failed_node.depends_on
                result_nodes.extend(new_nodes)
            else:
                # Update references to old node
                updated_deps: list[str] = []
                for dep in n.depends_on:
                    if dep == failed_node.id:
                        updated_deps.extend(nn.id for nn in new_nodes)
                    else:
                        updated_deps.append(dep)
                n.depends_on = updated_deps
                result_nodes.append(n)

        plan.nodes = result_nodes
        return plan
