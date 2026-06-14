"""MUNINN — the raven of memory and self-improvement (RSIP engine).

Recursive Self-Improvement Protocol, the *bounded* version:

    propose → HEIMDALL gate → prove on VÍGRÍÐR (baseline vs candidate)
            → LOKI review → decide → BIFRÖST opens a PR (human merges)

A proposal is accepted only if it (a) passes the self-modification policy,
(b) does not regress correctness, (c) measurably improves a metric, and
(d) survives an adversarial review. ODIN never merges its own changes — the
final gate is always a human.
"""

from __future__ import annotations

from typing import Protocol

from odin.github.bifrost import PullRequest
from odin.routing.llm_adapter import LLMAdapter, LLMMessage
from odin.safety.heimdall import Heimdall
from odin.schemas import (
    ActionRisk,
    BenchmarkResult,
    ImprovementOutcome,
    ImprovementProposal,
    VerdictRecord,
    VerifyOutcome,
)

# ---------------------------------------------------------------------------
# Collaborator protocols (injected — fakes used in tests)
# ---------------------------------------------------------------------------

class Proposer(Protocol):
    async def propose(self, weakness: str, context: str) -> ImprovementProposal: ...


class Evaluator(Protocol):
    async def baseline(self) -> BenchmarkResult: ...
    async def candidate(self, proposal: ImprovementProposal) -> BenchmarkResult: ...


class DiffReviewer(Protocol):
    async def review(self, proposal: ImprovementProposal) -> VerdictRecord: ...


class Publisher(Protocol):
    async def open_pr(self, *, branch: str, title: str, body: str, diff: str) -> PullRequest: ...


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class Muninn:
    """Orchestrates one bounded, verified, human-gated self-improvement cycle."""

    def __init__(
        self,
        *,
        heimdall: Heimdall,
        proposer: Proposer,
        evaluator: Evaluator,
        reviewer: DiffReviewer,
        publisher: Publisher,
        min_metric_gain: float = 0.0,
    ) -> None:
        self.heimdall = heimdall
        self.proposer = proposer
        self.evaluator = evaluator
        self.reviewer = reviewer
        self.publisher = publisher
        self.min_metric_gain = min_metric_gain

    async def run_cycle(self, weakness: str, context: str = "") -> ImprovementOutcome:
        proposal = await self.proposer.propose(weakness, context)

        allowed, reason = self.heimdall.check_self_modification(proposal)
        if not allowed:
            return ImprovementOutcome(
                proposal_id=proposal.id, accepted=False, reasons=[f"HEIMDALL: {reason}"]
            )

        baseline = await self.evaluator.baseline()
        candidate = await self.evaluator.candidate(proposal)
        review = await self.reviewer.review(proposal)

        accepted, reasons = self._decide(baseline, candidate, review)
        outcome = ImprovementOutcome(
            proposal_id=proposal.id,
            accepted=accepted,
            reasons=reasons,
            baseline=baseline,
            candidate=candidate,
            review=review,
        )

        if accepted:
            pr = await self.publisher.open_pr(
                branch=f"odin/rsip-{proposal.id[:8]}",
                title=self._title(proposal),
                body=self._report(proposal, baseline, candidate, review),
                diff=proposal.diff,
            )
            outcome.pr_url = pr.url

        return outcome

    # -- decision --

    def _decide(
        self, baseline: BenchmarkResult, candidate: BenchmarkResult, review: VerdictRecord
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        accepted = True

        if review.outcome == VerifyOutcome.FAIL:
            accepted = False
            reasons.append(f"LOKI rejected: {review.explanation}")
        elif review.outcome == VerifyOutcome.UNCERTAIN:
            accepted = False
            reasons.append("LOKI uncertain — deferring to human")

        if candidate.pass_rate < baseline.pass_rate:
            accepted = False
            reasons.append(
                f"regression: pass_rate {candidate.pass_rate:.2f} < baseline {baseline.pass_rate:.2f}"
            )

        gain = candidate.pass_rate - baseline.pass_rate
        improves = gain > 0 and gain >= self.min_metric_gain
        cheaper = (
            candidate.pass_rate == baseline.pass_rate
            and candidate.avg_tokens < baseline.avg_tokens
        )
        if not (improves or cheaper):
            accepted = False
            reasons.append("no measurable improvement over baseline")

        if accepted:
            reasons.append(
                f"accepted: pass_rate {baseline.pass_rate:.2f}→{candidate.pass_rate:.2f}, "
                f"avg_tokens {baseline.avg_tokens:.0f}→{candidate.avg_tokens:.0f}, LOKI pass"
            )

        return accepted, reasons

    # -- reporting --

    def _title(self, proposal: ImprovementProposal) -> str:
        return f"rsip: improve {proposal.target_file} — {proposal.rationale[:60]}"

    def _report(
        self,
        proposal: ImprovementProposal,
        baseline: BenchmarkResult,
        candidate: BenchmarkResult,
        review: VerdictRecord,
    ) -> str:
        return (
            f"## Self-improvement proposal (RSIP)\n\n"
            f"**Target:** `{proposal.target_file}`\n\n"
            f"**Rationale:** {proposal.rationale}\n\n"
            f"### VÍGRÍÐR benchmark ({baseline.suite})\n"
            f"| metric | baseline | candidate |\n"
            f"|---|---|---|\n"
            f"| pass_rate | {baseline.pass_rate:.2f} | {candidate.pass_rate:.2f} |\n"
            f"| avg_tokens | {baseline.avg_tokens:.0f} | {candidate.avg_tokens:.0f} |\n\n"
            f"### LOKI review\n{review.outcome.value} (confidence {review.confidence:.2f}) — "
            f"{review.explanation}\n\n"
            f"_Opened by MUNINN. Requires human review before merge._\n"
        )


# ---------------------------------------------------------------------------
# Concrete LLM-backed collaborators (used with a real adapter; fakes in tests)
# ---------------------------------------------------------------------------

class LLMProposer:
    """Asks an LLM to draft a scoped ImprovementProposal as JSON."""

    def __init__(self, llm: LLMAdapter, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def propose(self, weakness: str, context: str) -> ImprovementProposal:
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "You are MUNINN, ODIN's self-improvement proposer. Propose ONE small, "
                    "scoped code change to fix the described weakness. Respond as JSON with "
                    "keys: target_file, rationale, diff (unified diff), expected_metric, "
                    "expected_metric_delta (float), risk (low|medium|high). Keep the diff small."
                ),
            ),
            LLMMessage(role="user", content=f"Weakness:\n{weakness}\n\nContext:\n{context}"),
        ]
        data = await self._llm.complete_json(messages, model=self._model)
        return ImprovementProposal(
            target_file=str(data.get("target_file", "")),
            rationale=str(data.get("rationale", "")),
            diff=str(data.get("diff", "")),
            expected_metric=str(data.get("expected_metric", "pass_rate")),
            expected_metric_delta=_as_float(data.get("expected_metric_delta"), 0.0),
            risk=_parse_risk(data.get("risk")),
        )


class LokiDiffReviewer:
    """Adversarially reviews a proposal's diff via an LLM (decorrelated critic)."""

    def __init__(self, llm: LLMAdapter, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def review(self, proposal: ImprovementProposal) -> VerdictRecord:
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "You are LOKI, an adversarial code reviewer. Find reasons the diff is "
                    "wrong, unsafe, or weakens ODIN's guarantees. Respond as JSON with keys: "
                    "outcome (pass|fail|uncertain), explanation, confidence (0-1)."
                ),
            ),
            LLMMessage(
                role="user",
                content=f"Rationale: {proposal.rationale}\n\nDiff:\n{proposal.diff}",
            ),
        ]
        data = await self._llm.complete_json(messages, model=self._model)
        return VerdictRecord(
            node_id=proposal.id,
            outcome=_parse_outcome(data.get("outcome")),
            method="critic",
            explanation=str(data.get("explanation", "")),
            confidence=_as_float(data.get("confidence"), 0.5),
        )


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_risk(value: object) -> ActionRisk:
    try:
        return ActionRisk(str(value).lower())
    except ValueError:
        return ActionRisk.MEDIUM


def _parse_outcome(value: object) -> VerifyOutcome:
    try:
        return VerifyOutcome(str(value).lower())
    except ValueError:
        return VerifyOutcome.UNCERTAIN
