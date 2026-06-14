"""FREYA — The Renderer.

Takes raw results from THOR + verification verdicts and produces a
final, user-facing output with citations and provenance.

FREYA reads memory but never writes to it (separation of duties).
"""

from __future__ import annotations

from odin.agents.base import BaseAgent
from odin.routing.llm_adapter import LLMMessage
from odin.schemas import (
    AgentMessage,
    AgentRole,
    PlanDAG,
    VerdictRecord,
)

_SYSTEM_PROMPT = """\
You are FREYA, the presentation agent. Your job is to take raw task results,
verification outcomes, and source information, and produce a clear, well-structured
final answer for the user.

Rules:
- Include citations for factual claims: [Source: <source_id>]
- Note the confidence level of the answer based on verification results.
- If any verification failed, clearly state what was uncertain or unverified.
- Be honest about limitations. Never claim certainty you don't have.
- Structure the output clearly with sections if the answer is complex.
"""


class FreyaRenderer(BaseAgent):
    """Produces the final cited output for the user."""

    role = AgentRole.FREYA
    system_prompt = _SYSTEM_PROMPT

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Render a final answer from raw results."""
        return self._make_response(
            to=AgentRole.ODIN,
            content=await self.render(message.content),
        )

    async def render(
        self,
        raw_results: str,
        verdicts: list[VerdictRecord] | None = None,
        plan: PlanDAG | None = None,
    ) -> str:
        """Produce a final, cited answer.

        Args:
            raw_results: Combined output from THOR executions.
            verdicts: Verification records (if any).
            plan: The original plan (for context).
        """
        verdict_summary = ""
        if verdicts:
            verdict_lines = []
            for v in verdicts:
                verdict_lines.append(
                    f"- [{v.method}] {v.outcome.value}: {v.explanation} "
                    f"(confidence: {v.confidence:.0%})"
                )
            verdict_summary = (
                "\n\nVerification results:\n" + "\n".join(verdict_lines)
            )

        plan_context = ""
        if plan:
            plan_context = f"\n\nOriginal goal: {plan.goal}"

        prompt = (
            f"Produce a clear, well-structured final answer based on these results."
            f"{plan_context}\n\n"
            f"Raw results:\n{raw_results}"
            f"{verdict_summary}\n\n"
            f"Remember to include citations and note confidence levels."
        )

        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=prompt),
        ]

        resp = await self._llm.complete(messages, temperature=0.3)
        return resp.content
