"""Delegation — spawn sub-goals as child jobs with shared memory.

When the orchestrator encounters a complex goal that should be handled
by a specialised sub-orchestration, it creates a DelegationRequest
which becomes a child Job.  The child shares the same MIMIR instance
so memories flow between parent and child.
"""

from __future__ import annotations

import logging

from odin.jobs.store import JobStore
from odin.schemas import DelegationRequest, Job, JobStatus

logger = logging.getLogger("odin.delegation")


class Delegator:
    """Creates child jobs from delegation requests."""

    def __init__(self, job_store: JobStore) -> None:
        self._store = job_store

    def delegate(self, request: DelegationRequest) -> Job:
        """Create a child job from a delegation request.

        The child job is queued with the parent's ID so it can be
        tracked and its results rolled up.
        """
        child = Job(
            goal=request.sub_goal,
            parent_job_id=request.parent_job_id,
            priority=request.priority,
            tags=["delegated", f"from:{request.delegated_by.value}"],
        )
        self._store.save(child)
        logger.info(
            "Delegated sub-goal '%s' as job %s (parent=%s)",
            request.sub_goal, child.id, request.parent_job_id,
        )
        return child

    def children_complete(self, parent_job_id: str) -> bool:
        """Check whether all child jobs of a parent are done (completed or failed)."""
        children = self._store.children(parent_job_id)
        if not children:
            return True
        return all(
            c.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
            for c in children
        )

    def children_results(self, parent_job_id: str) -> list[Job]:
        """Return all child jobs for roll-up."""
        return self._store.children(parent_job_id)
