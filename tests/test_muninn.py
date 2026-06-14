"""Tests for the MUNINN self-improvement engine (full RSIP cycle, offline)."""

from odin.github import FakeBifrost
from odin.improve.muninn import Muninn
from odin.safety.heimdall import Heimdall
from odin.schemas import (
    BenchmarkResult,
    ImprovementProposal,
    VerdictRecord,
    VerifyOutcome,
)


def _result(passed: int, total: int = 4, avg_tokens: float = 100.0) -> BenchmarkResult:
    return BenchmarkResult(suite="t", total=total, passed=passed, avg_tokens=avg_tokens)


def _verdict(outcome: VerifyOutcome) -> VerdictRecord:
    return VerdictRecord(node_id="n", outcome=outcome, method="critic", explanation="x", confidence=0.9)


class FakeProposer:
    def __init__(self, proposal: ImprovementProposal) -> None:
        self._proposal = proposal

    async def propose(self, weakness: str, context: str) -> ImprovementProposal:
        return self._proposal


class FakeEvaluator:
    def __init__(self, baseline: BenchmarkResult, candidate: BenchmarkResult) -> None:
        self._baseline = baseline
        self._candidate = candidate
        self.baseline_called = False
        self.candidate_called = False

    async def baseline(self) -> BenchmarkResult:
        self.baseline_called = True
        return self._baseline

    async def candidate(self, proposal: ImprovementProposal) -> BenchmarkResult:
        self.candidate_called = True
        return self._candidate


class FakeReviewer:
    def __init__(self, verdict: VerdictRecord) -> None:
        self._verdict = verdict

    async def review(self, proposal: ImprovementProposal) -> VerdictRecord:
        return self._verdict


def _engine(
    *,
    proposal: ImprovementProposal,
    baseline: BenchmarkResult,
    candidate: BenchmarkResult,
    outcome: VerifyOutcome,
    heimdall: Heimdall | None = None,
) -> tuple[Muninn, FakeBifrost, FakeEvaluator]:
    bifrost = FakeBifrost()
    evaluator = FakeEvaluator(baseline, candidate)
    engine = Muninn(
        heimdall=heimdall or Heimdall(),
        proposer=FakeProposer(proposal),
        evaluator=evaluator,
        reviewer=FakeReviewer(_verdict(outcome)),
        publisher=bifrost,
    )
    return engine, bifrost, evaluator


def _good_proposal() -> ImprovementProposal:
    return ImprovementProposal(target_file="odin/agents/odin_planner.py", rationale="tighter prompt", diff="+ better\n- worse")


class TestMuninnCycle:
    async def test_accepts_improvement_and_opens_pr(self) -> None:
        engine, bifrost, _ = _engine(
            proposal=_good_proposal(),
            baseline=_result(2),
            candidate=_result(4),
            outcome=VerifyOutcome.PASS,
        )
        outcome = await engine.run_cycle("fails on math")
        assert outcome.accepted is True
        assert outcome.pr_url is not None
        assert len(bifrost.opened) == 1
        assert bifrost.opened[0]["branch"].startswith("odin/rsip-")

    async def test_rejects_regression(self) -> None:
        engine, bifrost, _ = _engine(
            proposal=_good_proposal(),
            baseline=_result(4),
            candidate=_result(2),
            outcome=VerifyOutcome.PASS,
        )
        outcome = await engine.run_cycle("w")
        assert outcome.accepted is False
        assert outcome.pr_url is None
        assert bifrost.opened == []
        assert any("regression" in r for r in outcome.reasons)

    async def test_rejects_when_loki_fails(self) -> None:
        engine, bifrost, _ = _engine(
            proposal=_good_proposal(),
            baseline=_result(2),
            candidate=_result(4),
            outcome=VerifyOutcome.FAIL,
        )
        outcome = await engine.run_cycle("w")
        assert outcome.accepted is False
        assert bifrost.opened == []
        assert any("LOKI rejected" in r for r in outcome.reasons)

    async def test_rejects_when_loki_uncertain(self) -> None:
        engine, _, _ = _engine(
            proposal=_good_proposal(),
            baseline=_result(2),
            candidate=_result(4),
            outcome=VerifyOutcome.UNCERTAIN,
        )
        outcome = await engine.run_cycle("w")
        assert outcome.accepted is False

    async def test_rejects_no_improvement(self) -> None:
        engine, _, _ = _engine(
            proposal=_good_proposal(),
            baseline=_result(3, avg_tokens=100.0),
            candidate=_result(3, avg_tokens=100.0),
            outcome=VerifyOutcome.PASS,
        )
        outcome = await engine.run_cycle("w")
        assert outcome.accepted is False
        assert any("no measurable improvement" in r for r in outcome.reasons)

    async def test_accepts_cheaper_at_equal_quality(self) -> None:
        engine, bifrost, _ = _engine(
            proposal=_good_proposal(),
            baseline=_result(3, avg_tokens=200.0),
            candidate=_result(3, avg_tokens=120.0),
            outcome=VerifyOutcome.PASS,
        )
        outcome = await engine.run_cycle("w")
        assert outcome.accepted is True
        assert len(bifrost.opened) == 1

    async def test_heimdall_blocks_before_evaluation(self) -> None:
        proposal = ImprovementProposal(
            target_file="odin/safety/heimdall.py", rationale="weaken brakes", diff="+ x"
        )
        engine, bifrost, evaluator = _engine(
            proposal=proposal,
            baseline=_result(2),
            candidate=_result(4),
            outcome=VerifyOutcome.PASS,
        )
        outcome = await engine.run_cycle("w")
        assert outcome.accepted is False
        assert evaluator.baseline_called is False
        assert evaluator.candidate_called is False
        assert bifrost.opened == []
        assert any("HEIMDALL" in r for r in outcome.reasons)

    async def test_min_metric_gain_threshold(self) -> None:
        bifrost = FakeBifrost()
        engine = Muninn(
            heimdall=Heimdall(),
            proposer=FakeProposer(_good_proposal()),
            evaluator=FakeEvaluator(_result(2, total=4), _result(3, total=4)),
            reviewer=FakeReviewer(_verdict(VerifyOutcome.PASS)),
            publisher=bifrost,
            min_metric_gain=0.5,  # +0.25 gain is below threshold
        )
        outcome = await engine.run_cycle("w")
        assert outcome.accepted is False
