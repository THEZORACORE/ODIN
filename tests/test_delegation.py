"""Tests for the delegation protocol (Phase 5.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from odin.jobs.delegation import Delegator
from odin.jobs.store import JobStore
from odin.schemas import AgentRole, DelegationRequest, Job, JobStatus


@pytest.fixture()
def store(tmp_path: Path) -> JobStore:
    s = JobStore(data_dir=str(tmp_path))
    yield s
    s.close()


@pytest.fixture()
def delegator(store: JobStore) -> Delegator:
    return Delegator(store)


class TestDelegation:
    def test_creates_child_job(self, store: JobStore, delegator: Delegator) -> None:
        parent = Job(goal="big task")
        store.save(parent)
        req = DelegationRequest(
            parent_job_id=parent.id,
            sub_goal="sub-task A",
            delegated_by=AgentRole.ODIN,
        )
        child = delegator.delegate(req)
        assert child.parent_job_id == parent.id
        assert child.goal == "sub-task A"
        assert child.status == JobStatus.QUEUED
        assert "delegated" in child.tags

    def test_children_complete_empty(self, delegator: Delegator) -> None:
        assert delegator.children_complete("nonexistent") is True

    def test_children_complete_checks_all(self, store: JobStore, delegator: Delegator) -> None:
        parent = Job(goal="parent")
        store.save(parent)

        req1 = DelegationRequest(parent_job_id=parent.id, sub_goal="A")
        req2 = DelegationRequest(parent_job_id=parent.id, sub_goal="B")
        child1 = delegator.delegate(req1)
        child2 = delegator.delegate(req2)

        assert not delegator.children_complete(parent.id)

        store.mark_completed(child1.id, "ok")
        assert not delegator.children_complete(parent.id)

        store.mark_completed(child2.id, "ok")
        assert delegator.children_complete(parent.id)

    def test_children_results(self, store: JobStore, delegator: Delegator) -> None:
        parent = Job(goal="parent")
        store.save(parent)
        delegator.delegate(DelegationRequest(parent_job_id=parent.id, sub_goal="A"))
        delegator.delegate(DelegationRequest(parent_job_id=parent.id, sub_goal="B"))
        results = delegator.children_results(parent.id)
        assert len(results) == 2
