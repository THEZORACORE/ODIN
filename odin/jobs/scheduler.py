"""Scheduler — daemon-mode job processing for continuous operation.

Pulls queued jobs from the JobStore and executes them through the
orchestrator, one at a time (bounded concurrency).  Supports
checkpoint/resume so jobs survive restarts.
"""

from __future__ import annotations

import asyncio
import logging

from odin.core.orchestrator import Orchestrator, OrchestratorResult
from odin.jobs.store import JobStore
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import LLMAdapter
from odin.safety.heimdall import Heimdall
from odin.schemas import BudgetState, Job
from odin.skills.store import SkillStore
from odin.tools.registry import ToolRegistry

logger = logging.getLogger("odin.scheduler")


class Scheduler:
    """Pulls and executes queued jobs from the JobStore.

    Runs as a long-lived async loop (daemon mode).  Each job gets its
    own Orchestrator instance but shares the same MIMIR and SkillStore
    for cross-job memory and skill reuse.
    """

    def __init__(
        self,
        job_store: JobStore,
        llm: LLMAdapter,
        tools: ToolRegistry,
        mimir: Mimir,
        *,
        skill_store: SkillStore | None = None,
        poll_interval: float = 2.0,
        default_budget: BudgetState | None = None,
    ) -> None:
        self._store = job_store
        self._llm = llm
        self._tools = tools
        self._mimir = mimir
        self._skill_store = skill_store
        self._poll_interval = poll_interval
        self._default_budget = default_budget or BudgetState()
        self._running = False
        self._current_job: Job | None = None

    async def run_once(self) -> OrchestratorResult | None:
        """Pick the next queued job and run it. Returns None if queue empty."""
        job = self._store.next_queued()
        if job is None:
            return None
        return await self._execute_job(job)

    async def run_loop(self, *, max_jobs: int | None = None) -> list[OrchestratorResult]:
        """Process queued jobs until the queue is empty or *max_jobs* reached.

        This is the daemon loop.  Set *max_jobs* for bounded runs (testing).
        """
        self._running = True
        results: list[OrchestratorResult] = []
        processed = 0

        while self._running:
            job = self._store.next_queued()
            if job is None:
                logger.info("Queue empty, waiting %.1fs", self._poll_interval)
                await asyncio.sleep(self._poll_interval)
                # Re-check after sleep
                job = self._store.next_queued()
                if job is None:
                    logger.info("Queue still empty after poll, stopping")
                    break

            result = await self._execute_job(job)
            results.append(result)
            processed += 1

            if max_jobs is not None and processed >= max_jobs:
                logger.info("Reached max_jobs=%d, stopping", max_jobs)
                break

        self._running = False
        return results

    def stop(self) -> None:
        """Signal the daemon loop to stop after the current job."""
        self._running = False

    @property
    def current_job(self) -> Job | None:
        return self._current_job

    async def _execute_job(self, job: Job) -> OrchestratorResult:
        """Run a single job through the orchestrator."""
        self._current_job = job
        self._store.mark_running(job.id)
        logger.info("Starting job %s: %s", job.id, job.goal)

        budget = BudgetState(
            max_tokens=job.budget.max_tokens or self._default_budget.max_tokens,
            max_llm_calls=job.budget.max_llm_calls or self._default_budget.max_llm_calls,
            max_tool_calls=job.budget.max_tool_calls or self._default_budget.max_tool_calls,
            max_wall_clock_seconds=job.budget.max_wall_clock_seconds or self._default_budget.max_wall_clock_seconds,
        )
        heimdall = Heimdall(budget=budget)

        orchestrator = Orchestrator(
            llm=self._llm,
            tools=self._tools,
            heimdall=heimdall,
            mimir=self._mimir,
            session_id=job.session_id or job.id,
            budget=budget,
            skill_store=self._skill_store,
        )

        try:
            result = await orchestrator.run(job.goal)
            if result.success:
                self._store.mark_completed(job.id, result.answer[:500])
            else:
                self._store.mark_failed(job.id, result.answer[:500])
            logger.info("Job %s finished: success=%s", job.id, result.success)
            return result

        except Exception as exc:
            logger.error("Job %s crashed: %s", job.id, exc)
            self._store.mark_failed(job.id, f"Crashed: {exc}")
            # Return a failure result
            from odin.schemas import PlanDAG
            return OrchestratorResult(
                goal=job.goal,
                answer=f"Job crashed: {exc}",
                plan=PlanDAG(goal=job.goal),
                verdicts=[],
                budget_state=budget,
                success=False,
                session_id=job.session_id or job.id,
            )
        finally:
            self._current_job = None

    def enqueue(
        self,
        goal: str,
        *,
        priority: int = 0,
        tags: list[str] | None = None,
        parent_job_id: str | None = None,
        budget: BudgetState | None = None,
    ) -> Job:
        """Add a new goal to the queue."""
        job = Job(
            goal=goal,
            priority=priority,
            tags=tags or [],
            parent_job_id=parent_job_id,
            budget=budget or self._default_budget,
        )
        self._store.save(job)
        logger.info("Enqueued job %s: %s (priority=%d)", job.id, goal, priority)
        return job
