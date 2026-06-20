"""FORSETI — Structured multi-agent debate & consensus (8.3).

Named after the Norse god of justice and reconciliation.  Agents argue
opposing positions; a judge evaluates arguments and renders a ruling
with reasoning.  This produces more reliable answers than any single
agent on contested or ambiguous questions.

Debate flow:
1. Proposer states a position
2. Opponent challenges with counter-arguments
3. Proposer rebuts
4. Judge evaluates both sides and rules
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from odin.routing.llm_adapter import LLMAdapter, LLMMessage

logger = logging.getLogger("odin.society.debate")


class DebateRound(BaseModel):
    """One round of argument in a debate."""

    round_number: int
    proposer_argument: str
    opponent_argument: str


class DebateResult(BaseModel):
    """The outcome of a structured debate."""

    question: str
    rounds: list[DebateRound]
    ruling: str
    reasoning: str
    confidence: float = 0.0
    winner: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class DebateJudge:
    """FORSETI — run a structured debate between agents.

    Uses separate LLM calls for proposer, opponent, and judge roles.
    Can use different models for true decorrelation.
    """

    def __init__(
        self,
        proposer: LLMAdapter,
        opponent: LLMAdapter,
        judge: LLMAdapter,
        rounds: int = 2,
    ) -> None:
        self._proposer = proposer
        self._opponent = opponent
        self._judge = judge
        self._rounds = rounds

    async def debate(self, question: str) -> DebateResult:
        """Run a full debate and return the judge's ruling."""
        rounds: list[DebateRound] = []
        context: list[str] = [f"Question: {question}"]

        for i in range(self._rounds):
            # Proposer argues
            proposer_prompt = (
                "You are arguing FOR the following question.\n"
                "Context so far:\n" + "\n".join(context) +
                f"\n\nRound {i + 1}: Make your strongest argument."
            )
            prop_response = await self._proposer.complete([
                LLMMessage(role="system", content="You are a skilled debater arguing FOR the proposition."),
                LLMMessage(role="user", content=proposer_prompt),
            ])
            prop_arg = prop_response.content
            context.append(f"Proposer (round {i + 1}): {prop_arg}")

            # Opponent counters
            opponent_prompt = (
                "You are arguing AGAINST the following question.\n"
                "Context so far:\n" + "\n".join(context) +
                f"\n\nRound {i + 1}: Counter the proposer's argument."
            )
            opp_response = await self._opponent.complete([
                LLMMessage(role="system", content="You are a skilled debater arguing AGAINST the proposition."),
                LLMMessage(role="user", content=opponent_prompt),
            ])
            opp_arg = opp_response.content
            context.append(f"Opponent (round {i + 1}): {opp_arg}")

            rounds.append(DebateRound(
                round_number=i + 1,
                proposer_argument=prop_arg,
                opponent_argument=opp_arg,
            ))

        # Judge evaluates
        judge_prompt = (
            f"You are an impartial judge evaluating a debate.\n"
            f"Question: {question}\n\n"
            f"Debate transcript:\n" + "\n".join(context[1:]) +
            "\n\nRender your ruling: which side has the stronger argument? "
            "State your conclusion, explain your reasoning, and indicate your confidence (0-100%)."
        )
        judge_response = await self._judge.complete([
            LLMMessage(role="system", content="You are FORSETI, an impartial judge. Evaluate arguments on their merits."),
            LLMMessage(role="user", content=judge_prompt),
        ])

        ruling = judge_response.content
        confidence = self._extract_confidence(ruling)
        winner = self._extract_winner(ruling)

        return DebateResult(
            question=question,
            rounds=rounds,
            ruling=ruling,
            reasoning=ruling,
            confidence=confidence,
            winner=winner,
        )

    @staticmethod
    def _extract_confidence(text: str) -> float:
        """Extract confidence percentage from judge's text."""
        import re
        match = re.search(r"(\d{1,3})%", text)
        if match:
            return min(int(match.group(1)) / 100.0, 1.0)
        return 0.5

    @staticmethod
    def _extract_winner(text: str) -> str:
        """Heuristic: who did the judge side with?"""
        lower = text.lower()
        prop_signals = ["proposer", "for the proposition", "in favor", "agree"]
        opp_signals = ["opponent", "against the proposition", "disagree", "contra"]
        prop_score = sum(1 for s in prop_signals if s in lower)
        opp_score = sum(1 for s in opp_signals if s in lower)
        if prop_score > opp_score:
            return "proposer"
        if opp_score > prop_score:
            return "opponent"
        return "undecided"
