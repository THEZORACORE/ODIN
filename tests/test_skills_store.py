"""Tests for the SkillStore (Phase 3.2 / 3.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from odin.schemas import Skill
from odin.skills.store import SkillStore


@pytest.fixture()
def store(tmp_path: Path) -> SkillStore:
    s = SkillStore(data_dir=str(tmp_path))
    yield s
    s.close()


def _make_skill(**overrides: object) -> Skill:
    defaults: dict[str, object] = {
        "name": "research task",
        "description": "research Python async patterns",
        "steps": ["search web", "summarize results"],
        "tools_used": ["web_search"],
        "tags": ["web_search"],
    }
    defaults.update(overrides)
    return Skill(**defaults)  # type: ignore[arg-type]


class TestSaveAndGet:
    def test_round_trip(self, store: SkillStore) -> None:
        skill = _make_skill()
        store.save(skill)
        got = store.get(skill.id)
        assert got is not None
        assert got.name == skill.name
        assert got.steps == skill.steps
        assert got.tools_used == ["web_search"]

    def test_upsert_overwrites(self, store: SkillStore) -> None:
        skill = _make_skill()
        store.save(skill)
        skill.name = "updated"
        store.save(skill)
        got = store.get(skill.id)
        assert got is not None
        assert got.name == "updated"

    def test_get_missing_returns_none(self, store: SkillStore) -> None:
        assert store.get("nonexistent") is None


class TestFind:
    def test_matches_by_description(self, store: SkillStore) -> None:
        store.save(_make_skill(description="research Python async patterns"))
        store.save(_make_skill(name="deploy", description="deploy to production"))
        results = store.find("Python async")
        assert len(results) == 1
        assert "Python" in results[0].description

    def test_empty_query_returns_empty(self, store: SkillStore) -> None:
        store.save(_make_skill())
        assert store.find("") == []

    def test_excludes_retired_by_default(self, store: SkillStore) -> None:
        skill = _make_skill()
        store.save(skill)
        store.retire(skill.id)
        assert store.find("research") == []
        assert len(store.find("research", include_retired=True)) == 1


class TestScoring:
    def test_record_outcome_updates_stats(self, store: SkillStore) -> None:
        skill = _make_skill()
        store.save(skill)

        store.record_outcome(skill.id, success=True, cost_tokens=100.0, latency_seconds=1.0)
        got = store.get(skill.id)
        assert got is not None
        assert got.success_count == 1
        assert got.usage_count == 1
        assert got.avg_cost_tokens == pytest.approx(100.0)

        store.record_outcome(skill.id, success=False, cost_tokens=200.0, latency_seconds=2.0)
        got = store.get(skill.id)
        assert got is not None
        assert got.failure_count == 1
        assert got.usage_count == 2
        assert got.avg_cost_tokens == pytest.approx(150.0)
        assert got.success_rate == pytest.approx(0.5)

    def test_record_outcome_missing_skill(self, store: SkillStore) -> None:
        assert store.record_outcome("nope", success=True) is None


class TestRetire:
    def test_retire_marks_skill(self, store: SkillStore) -> None:
        skill = _make_skill()
        store.save(skill)
        result = store.retire(skill.id)
        assert result is not None
        assert result.retired is True

    def test_retire_missing(self, store: SkillStore) -> None:
        assert store.retire("nope") is None


class TestListing:
    def test_all_active_excludes_retired(self, store: SkillStore) -> None:
        s1 = _make_skill(name="a", description="alpha task")
        s2 = _make_skill(name="b", description="beta task")
        store.save(s1)
        store.save(s2)
        store.retire(s1.id)
        active = store.all_active()
        assert len(active) == 1
        assert active[0].id == s2.id

    def test_all_skills_includes_retired(self, store: SkillStore) -> None:
        s1 = _make_skill(name="a", description="alpha task")
        s2 = _make_skill(name="b", description="beta task")
        store.save(s1)
        store.save(s2)
        store.retire(s1.id)
        assert len(store.all_skills()) == 2
