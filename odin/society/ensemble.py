"""VÉ & VILI — Ensemble reasoners (8.2).

N independent reasoners answer the same question; results are aggregated
to cancel decorrelated errors (majority vote, consistency check, or
weighted merge).  Can span model families for true decorrelation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

from odin.routing.llm_adapter import LLMAdapter, LLMMessage

logger = logging.getLogger("odin.society.ensemble")


class EnsembleAnswer(BaseModel):
    """One reasoner's answer."""

    reasoner_id: str
    answer: str
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnsembleResult(BaseModel):
    """Aggregated ensemble output."""

    question: str
    answers: list[EnsembleAnswer]
    consensus: str
    agreement_ratio: float
    method: str = "majority"


class EnsembleRunner:
    """VÉ & VILI — run N independent reasoners and aggregate.

    Each "reasoner" is an LLMAdapter instance (can be different model
    families for decorrelation).
    """

    def __init__(self, reasoners: list[tuple[str, LLMAdapter]]) -> None:
        """Init with named reasoners: [(name, adapter), ...]"""
        self._reasoners = reasoners

    async def ask(
        self,
        question: str,
        system_prompt: str = "Answer concisely and accurately.",
    ) -> EnsembleResult:
        """Ask all reasoners concurrently and aggregate answers."""
        tasks = [
            self._query_reasoner(name, adapter, question, system_prompt)
            for name, adapter in self._reasoners
        ]
        answers = await asyncio.gather(*tasks)

        consensus, agreement = self._aggregate(answers)
        return EnsembleResult(
            question=question,
            answers=answers,
            consensus=consensus,
            agreement_ratio=agreement,
        )

    async def _query_reasoner(
        self,
        name: str,
        adapter: LLMAdapter,
        question: str,
        system_prompt: str,
    ) -> EnsembleAnswer:
        """Query a single reasoner."""
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=question),
        ]
        response = await adapter.complete(messages)
        return EnsembleAnswer(
            reasoner_id=name,
            answer=response.content,
            confidence=1.0,
            metadata={"model": response.model, "tokens": response.tokens_used},
        )

    @staticmethod
    def _aggregate(answers: list[EnsembleAnswer]) -> tuple[str, float]:
        """Majority vote by content similarity.

        Simple approach: pick the longest answer that appears most similar
        to others (by word overlap).  Returns (consensus_answer, agreement_ratio).
        """
        if not answers:
            return "", 0.0
        if len(answers) == 1:
            return answers[0].answer, 1.0

        # Score each answer by average word overlap with all others
        def word_set(text: str) -> set[str]:
            return set(text.lower().split())

        scores: list[float] = []
        for i, a in enumerate(answers):
            ws_a = word_set(a.answer)
            overlaps: list[float] = []
            for j, b in enumerate(answers):
                if i == j:
                    continue
                ws_b = word_set(b.answer)
                union = ws_a | ws_b
                overlap = len(ws_a & ws_b) / len(union) if union else 0.0
                overlaps.append(overlap)
            scores.append(sum(overlaps) / len(overlaps) if overlaps else 0.0)

        best_idx = scores.index(max(scores))
        agreement = max(scores) if scores else 0.0
        return answers[best_idx].answer, round(agreement, 3)
