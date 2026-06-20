"""Tests for the JobStore (Phase 5.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from odin.jobs.store import JobStore
from odin.schemas import BudgetState, Job, JobStatus


@pytest.fixture()
def store(tmp_path: Path) -> JobStore:
    s = JobStore(data_dir=str(tmp_path))
    yield s
    s.close()


def _job(**kw: object) -> Job:
    defaults: dict[str, object] = {"goal": "test goal"}
    defaults.update(kw)
    return Job(**defaults)  # type: ignore[arg-type]


class TestSaveAndGet:
    def test_round_trip(self, store: JobStore) -> None:
        job = _job()
        store.save(job)
        got = store.get(job.id)
        assert got is not None
        assert got.goal == "test goal"
        assert got.status == JobStatus.QUEUED

    def test_upsert(self, store: JobStore) -> None:
        job = _job()
        store.save(job)
        job.priority = 5
        store.save(job)
        got = store.get(job.id)
        assert got is not None
        assert got.priority == 5

    def test_missing(self, store: JobStore) -> None:
        assert store.get("no") is None


class TestLifecycle:
    def test_mark_running(self, store: JobStore) -> None:
        job = _job()
        store.save(job)
        result = store.mark_running(job.id)
        assert result is not None
        assert result.status == JobStatus.RUNNING
        assert result.started_at is not None

    def test_mark_completed(self, store: JobStore) -> None:
        job = _job()
        store.save(job)
        store.mark_running(job.id)
        result = store.mark_completed(job.id, "done")
        assert result is not None
        assert result.status == JobStatus.COMPLETED
        assert result.result_summary == "done"
        assert result.completed_at is not None

    def test_mark_failed(self, store: JobStore) -> None:
        job = _job()
        store.save(job)
        result = store.mark_failed(job.id, "error")
        assert result is not None
        assert result.status == JobStatus.FAILED

    def test_cancel(self, store: JobStore) -> None:
        job = _job()
        store.save(job)
        result = store.cancel(job.id)
        assert result is not None
        assert result.status == JobStatus.CANCELLED

    def test_checkpoint(self, store: JobStore) -> None:
        job = _job()
        store.save(job)
        store.checkpoint(job.id, '{"plan": "..."}')
        got = store.get(job.id)
        assert got is not None
        assert got.checkpoint == '{"plan": "..."}'


class TestQueries:
    def test_next_queued_priority(self, store: JobStore) -> None:
        store.save(_job(goal="low", priority=0))
        high = _job(goal="high", priority=10)
        store.save(high)
        nxt = store.next_queued()
        assert nxt is not None
        assert nxt.goal == "high"

    def test_next_queued_empty(self, store: JobStore) -> None:
        assert store.next_queued() is None

    def test_by_status(self, store: JobStore) -> None:
        j1 = _job(goal="a")
        j2 = _job(goal="b")
        store.save(j1)
        store.save(j2)
        store.mark_running(j1.id)
        queued = store.by_status(JobStatus.QUEUED)
        assert len(queued) == 1
        assert queued[0].id == j2.id

    def test_all_jobs(self, store: JobStore) -> None:
        for i in range(5):
            store.save(_job(goal=f"task {i}"))
        assert len(store.all_jobs()) == 5

    def test_children(self, store: JobStore) -> None:
        parent = _job(goal="parent")
        store.save(parent)
        child = _job(goal="child", parent_job_id=parent.id)
        store.save(child)
        kids = store.children(parent.id)
        assert len(kids) == 1
        assert kids[0].id == child.id


class TestBudgetPersistence:
    def test_budget_round_trip(self, store: JobStore) -> None:
        budget = BudgetState(max_tokens=1000, max_llm_calls=5)
        job = _job(budget=budget)
        store.save(job)
        got = store.get(job.id)
        assert got is not None
        assert got.budget.max_tokens == 1000
        assert got.budget.max_llm_calls == 5
