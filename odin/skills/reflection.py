"""Reflection memory — store *why* runs failed, not just that they failed.

After a failed or partially-failed run, this module produces a structured
post-mortem stored as a PROCEDURAL memory in MIMIR.  Future planning can
retrieve these to avoid repeating the same mistakes.
"""

from __future__ import annotations

from odin.schemas import (
    MemoryRecord,
    MemoryType,
    NodeStatus,
    PlanDAG,
    Provenance,
    VerdictRecord,
    VerifyOutcome,
)


def build_reflection(
    plan: PlanDAG,
    verdicts: list[VerdictRecord],
    session_id: str | None = None,
) -> MemoryRecord:
    """Produce a procedural-memory post-mortem for a (partially) failed run.

    The content is a structured text block summarising:
    - which steps failed and their last error,
    - which verification checks failed and why,
    - a terse "lesson" line synthesised from the above.
    """
    failed_nodes = [n for n in plan.nodes if n.status == NodeStatus.FAILED]
    failed_verdicts = [v for v in verdicts if v.outcome == VerifyOutcome.FAIL]

    parts: list[str] = [f"Goal: {plan.goal}", ""]

    if failed_nodes:
        parts.append("Failed steps:")
        for n in failed_nodes:
            error = (n.result or "no output")[:200]
            parts.append(f"  - {n.goal}: {error}")
        parts.append("")

    if failed_verdicts:
        parts.append("Failed verifications:")
        for v in failed_verdicts:
            parts.append(f"  - [{v.method}] {v.explanation[:200]}")
        parts.append("")

    # Derive a terse lesson
    lessons: list[str] = []
    tool_hints = {n.tool_hint for n in failed_nodes if n.tool_hint}
    if tool_hints:
        lessons.append(f"tools involved: {', '.join(sorted(tool_hints))}")
    methods = {v.method for v in failed_verdicts}
    if methods:
        lessons.append(f"verification failures: {', '.join(sorted(methods))}")
    if not lessons:
        lessons.append("run did not complete successfully")
    parts.append(f"Lesson: {'; '.join(lessons)}")

    tags = ["reflection", "post_mortem"]
    tags.extend(sorted(tool_hints))

    return MemoryRecord(
        memory_type=MemoryType.PROCEDURAL,
        content="\n".join(parts),
        summary=f"Post-mortem: {plan.goal[:80]}",
        provenance=[Provenance(source_type="orchestrator", source_id="reflection")],
        tags=tags,
        session_id=session_id,
    )
