"""Tests for telemetry-driven improvement triggers (Phase 4.1)."""

from odin.improve.telemetry import TelemetrySink
from odin.schemas import VerdictRecord, VerifyOutcome


class TestDeriveTriggers:
    def test_aggregates_and_ranks_by_score(self) -> None:
        sink = TelemetrySink()
        sink.record("verdict_fail", detail="self_consistency")
        sink.record("verdict_fail", detail="self_consistency")
        sink.record("budget_exhausted", detail="oom", weight=2.0)

        triggers = sink.derive_triggers(min_score=1.0)

        assert [t.score for t in triggers] == sorted(
            [t.score for t in triggers], reverse=True
        )
        top = triggers[0]
        assert "self_consistency" in top.weakness
        assert top.score == 2.0
        assert top.occurrences == 2

    def test_min_score_filters_weak_signals(self) -> None:
        sink = TelemetrySink()
        sink.record("low_confidence", detail="critic", weight=0.5)
        assert sink.derive_triggers(min_score=1.0) == []
        assert len(sink.derive_triggers(min_score=0.5)) == 1

    def test_evidence_is_capped(self) -> None:
        sink = TelemetrySink()
        for i in range(10):
            sink.record("verdict_fail", detail=f"method-{i}-x")
        # All share the kind→weakness mapping bucket only if detail matches;
        # distinct details produce distinct buckets, so use identical detail.
        sink2 = TelemetrySink()
        for _ in range(10):
            sink2.record("verdict_fail", detail="self_consistency")
        trigger = sink2.derive_triggers()[0]
        assert len(trigger.evidence) == 5


class TestRecordRun:
    def test_failed_run_with_verdicts(self) -> None:
        sink = TelemetrySink()
        verdicts = [
            VerdictRecord(
                node_id="n1", outcome=VerifyOutcome.FAIL, method="self_consistency",
                explanation="x", confidence=0.2,
            ),
            VerdictRecord(
                node_id="n2", outcome=VerifyOutcome.PASS, method="critic",
                explanation="ok", confidence=0.9,
            ),
        ]
        sink.record_run(success=False, verdicts=verdicts, budget_exhausted=True)

        kinds = {e.kind for e in sink.events}
        assert "run_failed" in kinds
        assert "budget_exhausted" in kinds
        assert "verdict_fail" in kinds
        assert "low_confidence" in kinds  # the FAIL verdict had confidence 0.2

    def test_clean_run_produces_no_triggers(self) -> None:
        sink = TelemetrySink()
        verdicts = [
            VerdictRecord(
                node_id="n1", outcome=VerifyOutcome.PASS, method="self_consistency",
                explanation="ok", confidence=0.95,
            ),
        ]
        sink.record_run(success=True, verdicts=verdicts, budget_exhausted=False)
        assert sink.derive_triggers() == []
