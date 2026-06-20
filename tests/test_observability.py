"""Tests for the observability module (Phase 5.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from odin.observe.history import RunHistory, RunRecord


@pytest.fixture()
def history(tmp_path: Path) -> RunHistory:
    h = RunHistory(data_dir=str(tmp_path))
    yield h
    h.close()


def _record(**kw: object) -> RunRecord:
    defaults: dict[str, object] = {
        "id": "run_1",
        "session_id": "sess_1",
        "goal": "test goal",
        "success": True,
    }
    defaults.update(kw)
    return RunRecord(**defaults)  # type: ignore[arg-type]


class TestRunHistory:
    def test_round_trip(self, history: RunHistory) -> None:
        rec = _record()
        history.record(rec)
        recent = history.recent()
        assert len(recent) == 1
        assert recent[0].goal == "test goal"
        assert recent[0].success is True

    def test_upsert(self, history: RunHistory) -> None:
        rec = _record(tokens_used=100)
        history.record(rec)
        rec.tokens_used = 200
        history.record(rec)
        recent = history.recent()
        assert len(recent) == 1
        assert recent[0].tokens_used == 200

    def test_recent_ordering(self, history: RunHistory) -> None:
        from datetime import UTC, datetime, timedelta

        t1 = datetime(2025, 1, 1, tzinfo=UTC)
        t2 = t1 + timedelta(hours=1)
        history.record(_record(id="r1", created_at=t1))
        history.record(_record(id="r2", created_at=t2))
        recent = history.recent()
        assert recent[0].id == "r2"
        assert recent[1].id == "r1"

    def test_by_session(self, history: RunHistory) -> None:
        history.record(_record(id="r1", session_id="s1"))
        history.record(_record(id="r2", session_id="s2"))
        s1 = history.by_session("s1")
        assert len(s1) == 1
        assert s1[0].id == "r1"

    def test_limit(self, history: RunHistory) -> None:
        for i in range(10):
            history.record(_record(id=f"r{i}"))
        assert len(history.recent(limit=3)) == 3


class TestStats:
    def test_empty_stats(self, history: RunHistory) -> None:
        s = history.stats()
        assert s.get("total", 0) == 0 or s.get("total_runs", 0) == 0

    def test_aggregate_stats(self, history: RunHistory) -> None:
        history.record(_record(
            id="r1", success=True, tokens_used=100,
            llm_calls_used=5, tool_calls_used=3,
            node_count=2, nodes_completed=2, duration_seconds=1.5,
        ))
        history.record(_record(
            id="r2", success=False, tokens_used=200,
            llm_calls_used=10, tool_calls_used=7,
            node_count=3, nodes_completed=1, duration_seconds=3.0,
        ))
        s = history.stats()
        assert s["total_runs"] == 2
        assert s["success_rate"] == 0.5
        assert s["total_tokens"] == 300
        assert s["total_llm_calls"] == 15
        assert s["total_tool_calls"] == 10
        assert s["avg_duration_seconds"] == 2.25

    def test_full_node_stats(self, history: RunHistory) -> None:
        history.record(_record(
            id="r1", verdict_count=4, verdicts_passed=3, verdicts_failed=1,
        ))
        recent = history.recent()
        assert recent[0].verdicts_passed == 3
        assert recent[0].verdicts_failed == 1
