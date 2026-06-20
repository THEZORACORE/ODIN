"""Tests for the Scheduler / daemon mode (Phase 5.3)."""

from __future__ import annotations

import json
import tempfile

import pytest

from odin.jobs.scheduler import Scheduler
from odin.jobs.store import JobStore
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import FakeLLM
from odin.safety.heimdall import Heimdall
from odin.schemas import ActionRisk, BudgetState, Job, JobStatus
from odin.tools.registry import ToolRegistry, ToolSpec


def _fake_tools(heimdall: Heimdall) -> ToolRegistry:
    reg = ToolRegistry(heimdall)

    async def fake_code(code: str) -> str:
        return "42"

    reg.register(ToolSpec(
        name="code_interpreter", description="Run code", fn=fake_code, risk=ActionRisk.MEDIUM,
    ))
    return reg


def _plan_json(goal: str = "task") -> str:
    return json.dumps([
        {"id": "s1", "goal": goal, "depends_on": [], "tool_hint": "none"},
    ])


class TestSchedulerRunOnce:
    @pytest.mark.asyncio
    async def test_processes_one_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(data_dir=tmp)
            store.save(Job(goal="do something"))

            llm = FakeLLM(responses=[
                _plan_json(), "ANSWER: done", "done",
                '{"agrees": true, "explanation": "ok"}',
                '{"has_issues": false, "recommendation": "approve"}',
                "Result.",
            ])
            budget = BudgetState(max_llm_calls=20, max_tool_calls=20)
            heimdall = Heimdall(budget=budget)
            tools = _fake_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            sched = Scheduler(
                job_store=store, llm=llm, tools=tools, mimir=mimir,
                default_budget=budget,
            )
            result = await sched.run_once()
            assert result is not None
            assert result.success

            # Job should be marked completed
            jobs = store.by_status(JobStatus.COMPLETED)
            assert len(jobs) == 1
            mimir.close()
            store.close()

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(data_dir=tmp)
            llm = FakeLLM(responses=[])
            budget = BudgetState()
            heimdall = Heimdall(budget=budget)
            tools = _fake_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            sched = Scheduler(
                job_store=store, llm=llm, tools=tools, mimir=mimir,
            )
            assert await sched.run_once() is None
            mimir.close()
            store.close()


class TestSchedulerLoop:
    @pytest.mark.asyncio
    async def test_processes_multiple_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(data_dir=tmp)
            store.save(Job(goal="task 1"))
            store.save(Job(goal="task 2"))

            responses = []
            for _ in range(2):
                responses.extend([
                    _plan_json(), "ANSWER: done", "done",
                    '{"agrees": true, "explanation": "ok"}',
                    '{"has_issues": false, "recommendation": "approve"}',
                    "Result.",
                ])
            llm = FakeLLM(responses=responses)
            budget = BudgetState(max_llm_calls=50, max_tool_calls=50)
            heimdall = Heimdall(budget=budget)
            tools = _fake_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            sched = Scheduler(
                job_store=store, llm=llm, tools=tools, mimir=mimir,
                default_budget=budget, poll_interval=0.01,
            )
            results = await sched.run_loop(max_jobs=2)
            assert len(results) == 2
            assert all(r.success for r in results)
            mimir.close()
            store.close()


class TestSchedulerEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_creates_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(data_dir=tmp)
            llm = FakeLLM(responses=[])
            budget = BudgetState()
            heimdall = Heimdall(budget=budget)
            tools = _fake_tools(heimdall)
            mimir = Mimir(data_dir=tmp, llm=llm, use_chroma=False)

            sched = Scheduler(
                job_store=store, llm=llm, tools=tools, mimir=mimir,
            )
            job = sched.enqueue("research AI", priority=5, tags=["research"])
            assert job.goal == "research AI"
            assert job.priority == 5
            assert store.get(job.id) is not None
            mimir.close()
            store.close()
