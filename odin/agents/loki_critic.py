"""LOKI — The Critic.

Adversarial reviewer that challenges proposed answers.
Part of the verification pipeline — LOKI does NOT plan or execute.

LOKI is deliberately given an adversarial prompt to maximize the chance
of catching errors the executor missed.  Separation of duties: the
executor never approves its own output.
"""

from __future__ import annotations

import json

from odin.agents.base import BaseAgent
from odin.routing.llm_adapter import LLMMessage
from odin.schemas import AgentMessage, AgentRole, VerdictRecord, VerifyOutcome

_SYSTEM_PROMPT = """\
You are LOKI, the adversarial critic in an AI agent system. Your purpose is to
find errors, inconsistencies, unsupported claims, and logical flaws in proposed
answers.

Be thorough and skeptical.  Assume the answer might be wrong until you confirm
it's correct.  Check:
1. Logical consistency — does the reasoning follow?
2. Factual accuracy — are claims supported by evidence?
3. Completeness — does the answer fully address the question?
4. Edge cases — are there scenarios where the answer breaks?

Respond with JSON:
{
  "has_issues": true/false,
  "issues": ["issue1", "issue2"],
  "severity": "low" | "medium" | "high",
  "recommendation": "approve" | "revise" | "reject",
  "explanation": "..."
}
"""


class LokiCritic(BaseAgent):
    """Adversarial critic — finds flaws in proposed answers."""

    role = AgentRole.LOKI
    system_prompt = _SYSTEM_PROMPT

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Review a proposed answer."""
        verdict = await self.critique(
            node_id=message.metadata.get("node_id", "unknown"),
            question=message.metadata.get("question", ""),
            answer=message.content,
        )
        return self._make_response(
            to=AgentRole.ODIN,
            content=verdict.explanation,
            verdict=verdict.model_dump(mode="json"),
        )

    async def critique(
        self, node_id: str, question: str, answer: str
    ) -> VerdictRecord:
        """Perform an adversarial critique of a proposed answer."""
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(
                role="user",
                content=(
                    f"Question: {question}\n\n"
                    f"Proposed answer:\n{answer}\n\n"
                    "Analyze this answer critically."
                ),
            ),
        ]

        resp = await self._llm.complete(messages, temperature=0.1)

        issues: list[str] = []
        recommendation = "approve"
        explanation = resp.content

        try:
            content = resp.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:])
                if content.endswith("```"):
                    content = content[:-3].strip()
            parsed = json.loads(content)
            _ = parsed.get("has_issues", False)
            issues = parsed.get("issues", [])
            recommendation = parsed.get("recommendation", "approve")
            explanation = parsed.get("explanation", resp.content)
        except (json.JSONDecodeError, TypeError):
            pass  # defaults apply

        if recommendation == "reject":
            outcome = VerifyOutcome.FAIL
            confidence = 0.8
        elif recommendation == "revise":
            outcome = VerifyOutcome.UNCERTAIN
            confidence = 0.5
        else:
            outcome = VerifyOutcome.PASS
            confidence = 0.7

        return VerdictRecord(
            node_id=node_id,
            outcome=outcome,
            method="critic",
            explanation=str(explanation),
            evidence=issues,
            confidence=confidence,
        )
