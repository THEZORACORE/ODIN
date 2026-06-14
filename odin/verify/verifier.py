"""Verification engine — the propose→check→commit loop.

Implements three verification methods:
1. Self-consistency: ask the LLM to re-derive the answer independently,
   compare for agreement.
2. Critic (LOKI): a separate LLM call with an adversarial prompt looking
   for errors, logical gaps, and unsupported claims.
3. Tool-grounding: for code/math, execute the code and compare output
   to the claimed result.

Every output is a VerdictRecord with provenance.
Verification is not optional — it is the heart of ODIN.
"""

from __future__ import annotations

import json

from odin.routing.llm_adapter import LLMAdapter, LLMMessage
from odin.schemas import VerdictRecord, VerifyOutcome
from odin.tools.code_interpreter import execute_python
from odin.verify.similarity import SemanticComparator


class Verifier:
    """Multi-strategy verification engine."""

    def __init__(self, llm: LLMAdapter, *, comparator: SemanticComparator | None = None) -> None:
        self._llm = llm
        self._comparator = comparator or SemanticComparator()

    async def verify_all(
        self,
        node_id: str,
        question: str,
        answer: str,
        *,
        code: str | None = None,
        skip_self_consistency: bool = False,
    ) -> list[VerdictRecord]:
        """Run all applicable verification strategies.

        Adaptive depth: when skip_self_consistency is True, only the critic
        pass runs (saves 1 LLM call per verification).
        """
        verdicts: list[VerdictRecord] = []

        # 1. Self-consistency (skip for trivial/summarization nodes)
        if not skip_self_consistency:
            v1 = await self.self_consistency(node_id, question, answer)
            verdicts.append(v1)

        # 2. Critic
        v2 = await self.critic(node_id, question, answer)
        verdicts.append(v2)

        # 3. Tool-grounding (only if code is provided)
        if code:
            v3 = await self.tool_grounding(node_id, answer, code)
            verdicts.append(v3)

        return verdicts

    async def self_consistency(
        self, node_id: str, question: str, answer: str
    ) -> VerdictRecord:
        """Re-derive the answer independently, then compare *deterministically*.

        The agreement decision is made by semantic similarity (not a second LLM
        judge), so the comparison itself can't silently be wrong.
        """
        prompt = (
            "You are a careful reasoner. Answer the question independently. Do NOT "
            "reference any prior answer. Think step by step, then respond with a JSON "
            'object: {"final_answer": "<concise canonical answer>", "reasoning": "..."}.\n\n'
            f"Question: {question}"
        )
        resp = await self._llm.complete(
            [LLMMessage(role="user", content=prompt)],
            temperature=0.0,
        )
        rederived = self._extract_final_answer(resp.content)

        agrees, score = self._comparator.agrees(answer, rederived)
        confidence = round(score if agrees else 1.0 - score, 2)
        explanation = (
            f"semantic similarity {score:.2f} (threshold {self._comparator.threshold:.2f}) "
            f"→ {'agree' if agrees else 'disagree'}"
        )

        return VerdictRecord(
            node_id=node_id,
            outcome=VerifyOutcome.PASS if agrees else VerifyOutcome.FAIL,
            method="self_consistency",
            explanation=explanation,
            evidence=[answer, rederived],
            confidence=confidence,
        )

    @staticmethod
    def _extract_final_answer(content: str) -> str:
        """Pull a concise answer from a JSON response, falling back to raw text."""
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            return content.strip()
        if isinstance(parsed, dict):
            final = parsed.get("final_answer") or parsed.get("answer")
            if final is not None:
                return str(final)
        return content.strip()

    async def critic(
        self, node_id: str, question: str, answer: str
    ) -> VerdictRecord:
        """LOKI critic pass — adversarial review."""
        prompt = (
            "You are LOKI, a rigorous critic. Your job is to find errors, "
            "logical gaps, unsupported claims, and factual mistakes in the "
            "following answer. Be thorough and adversarial.\n\n"
            f"Question: {question}\n\n"
            f"Proposed answer: {answer}\n\n"
            "Respond with a JSON object:\n"
            '{"has_issues": true/false, "issues": ["..."], "severity": "low|medium|high", '
            '"recommendation": "approve|revise|reject"}'
        )
        resp = await self._llm.complete(
            [LLMMessage(role="user", content=prompt)],
            temperature=0.0,
        )

        has_issues = False
        issues: list[str] = []
        recommendation = "approve"
        try:
            parsed = json.loads(resp.content)
            if isinstance(parsed, dict):
                has_issues = bool(parsed.get("has_issues", False))
                issues = parsed.get("issues", [])
                recommendation = parsed.get("recommendation", "approve")
            else:
                has_issues = "true" in resp.content.lower()
        except (json.JSONDecodeError, TypeError):
            has_issues = "true" in resp.content.lower()

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
            explanation=f"Issues: {issues}" if has_issues else "No issues found",
            evidence=issues,
            confidence=confidence,
        )

    async def tool_grounding(
        self, node_id: str, claimed_output: str, code: str
    ) -> VerdictRecord:
        """Execute code and compare output to claimed result."""
        actual_output = await execute_python(code, timeout=15)

        if "[TIMEOUT]" in actual_output:
            return VerdictRecord(
                node_id=node_id,
                outcome=VerifyOutcome.UNCERTAIN,
                method="tool_grounding",
                explanation="Code execution timed out",
                evidence=[actual_output],
                confidence=0.2,
            )

        if "[STDERR]" in actual_output and "Error" in actual_output:
            return VerdictRecord(
                node_id=node_id,
                outcome=VerifyOutcome.FAIL,
                method="tool_grounding",
                explanation=f"Code execution error: {actual_output[:500]}",
                evidence=[actual_output],
                confidence=0.8,
            )

        # Compare outputs
        claimed_clean = claimed_output.strip().lower()
        actual_clean = actual_output.strip().lower()

        # Exact match or containment
        if claimed_clean == actual_clean or claimed_clean in actual_clean or actual_clean in claimed_clean:
            return VerdictRecord(
                node_id=node_id,
                outcome=VerifyOutcome.PASS,
                method="tool_grounding",
                explanation="Code output matches claimed result",
                evidence=[actual_output, claimed_output],
                confidence=0.9,
            )

        return VerdictRecord(
            node_id=node_id,
            outcome=VerifyOutcome.FAIL,
            method="tool_grounding",
            explanation=f"Mismatch: claimed='{claimed_output[:200]}' vs actual='{actual_output[:200]}'",
            evidence=[actual_output, claimed_output],
            confidence=0.8,
        )


def aggregate_verdicts(verdicts: list[VerdictRecord]) -> VerifyOutcome:
    """Combine multiple verdicts into a single outcome.

    Policy: any FAIL → FAIL; all PASS → PASS; else UNCERTAIN.
    """
    if any(v.outcome == VerifyOutcome.FAIL for v in verdicts):
        return VerifyOutcome.FAIL
    if all(v.outcome == VerifyOutcome.PASS for v in verdicts):
        return VerifyOutcome.PASS
    return VerifyOutcome.UNCERTAIN
