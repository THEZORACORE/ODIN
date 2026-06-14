"""Telemetry-driven improvement triggers (Phase 4.1).

RSIP shouldn't only fire when a human invokes it — ODIN should notice its own
recurring weaknesses and target them. `TelemetrySink` records run signals
(failed verifications, low-confidence verdicts, budget exhaustion, node
failures) and `derive_triggers` aggregates them into ranked `ImprovementTrigger`
weaknesses that can be fed straight into `Muninn.run_cycle`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from odin.schemas import VerdictRecord, VerifyOutcome


def _now() -> datetime:
    return datetime.now(UTC)


class TelemetryEvent(BaseModel):
    """A single observed signal worth learning from."""

    kind: str
    detail: str = ""
    weight: float = 1.0
    created_at: datetime = Field(default_factory=_now)


class ImprovementTrigger(BaseModel):
    """An aggregated weakness, ranked by accumulated signal weight."""

    weakness: str
    score: float
    occurrences: int
    evidence: list[str] = Field(default_factory=list)


# Confidence at/below this is treated as "the verifier wasn't sure".
LOW_CONFIDENCE = 0.5


class TelemetrySink:
    """Collects telemetry events and derives improvement triggers from them."""

    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []

    def record(self, kind: str, *, detail: str = "", weight: float = 1.0) -> None:
        self._events.append(TelemetryEvent(kind=kind, detail=detail, weight=weight))

    @property
    def events(self) -> list[TelemetryEvent]:
        return list(self._events)

    def record_run(
        self,
        *,
        success: bool,
        verdicts: Sequence[VerdictRecord],
        budget_exhausted: bool = False,
    ) -> None:
        """Ingest the signals from one orchestration run."""
        if budget_exhausted:
            self.record("budget_exhausted", detail="run exhausted its budget", weight=2.0)
        if not success:
            self.record("run_failed", detail="run did not complete successfully", weight=2.0)
        for v in verdicts:
            if v.outcome == VerifyOutcome.FAIL:
                self.record("verdict_fail", detail=v.method, weight=1.0)
            elif v.outcome == VerifyOutcome.UNCERTAIN:
                self.record("verdict_uncertain", detail=v.method, weight=0.5)
            if v.confidence <= LOW_CONFIDENCE:
                self.record("low_confidence", detail=v.method, weight=0.5)

    def derive_triggers(self, *, min_score: float = 1.0) -> list[ImprovementTrigger]:
        """Aggregate events into ranked weaknesses (highest score first)."""
        buckets: dict[str, list[TelemetryEvent]] = defaultdict(list)
        for event in self._events:
            buckets[self._weakness_for(event)].append(event)

        triggers: list[ImprovementTrigger] = []
        for weakness, events in buckets.items():
            score = sum(e.weight for e in events)
            if score < min_score:
                continue
            evidence = [e.detail for e in events if e.detail][:5]
            triggers.append(
                ImprovementTrigger(
                    weakness=weakness,
                    score=round(score, 2),
                    occurrences=len(events),
                    evidence=evidence,
                )
            )
        triggers.sort(key=lambda t: t.score, reverse=True)
        return triggers

    @staticmethod
    def _weakness_for(event: TelemetryEvent) -> str:
        method = event.detail or "unknown"
        mapping = {
            "verdict_fail": f"verification strategy '{method}' frequently fails — review it",
            "verdict_uncertain": f"verification strategy '{method}' is often uncertain",
            "low_confidence": f"verifier confidence is frequently low for '{method}'",
            "budget_exhausted": "runs exhaust their budget — improve planning efficiency",
            "run_failed": "runs fail to complete — harden the orchestration loop",
        }
        return mapping.get(event.kind, f"recurring signal: {event.kind}")
