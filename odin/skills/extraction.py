"""Skill extraction — distill a successful run into a reusable Skill.

After a verified, successful orchestration run, this module inspects the
completed PlanDAG and extracts a procedural Skill: a named sequence of
steps with the tools they used.  Only successful runs produce skills;
failed runs produce reflection memories instead (see reflection.py).
"""

from __future__ import annotations

from odin.schemas import NodeStatus, PlanDAG, Skill


def extract_skill(plan: PlanDAG) -> Skill | None:
    """Distill a completed PlanDAG into a reusable Skill.

    Returns ``None`` if the plan has no completed nodes (nothing to learn from).
    """
    completed = [n for n in plan.nodes if n.status == NodeStatus.COMPLETED]
    if not completed:
        return None

    # Derive a short name from the goal (first 80 chars)
    name = plan.goal[:80].strip()

    # Steps: ordered list of what was done
    steps = [n.goal for n in completed]

    # Tools used (deduplicated, order-preserving)
    seen: set[str] = set()
    tools: list[str] = []
    for n in completed:
        hint = n.tool_hint or "none"
        if hint not in seen:
            seen.add(hint)
            tools.append(hint)

    # Preconditions: which tools must be available
    preconditions = [f"tool:{t}" for t in tools if t != "none"]

    # Tags: derived from tool usage for search matching
    tags = list(tools)
    if len(completed) > 3:
        tags.append("multi_step")

    return Skill(
        name=name,
        description=plan.goal,
        steps=steps,
        preconditions=preconditions,
        tools_used=tools,
        tags=tags,
        success_count=1,
    )
