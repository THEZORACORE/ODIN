"""VÍGRÍÐR — the proving ground.

A small, deterministic benchmark harness ODIN runs against itself before and
after a self-improvement proposal.  It is the *exam* that turns "self-improvement"
into something measurable: a proposal is only accepted if it provably raises a
metric here without regressing correctness.

VÍGRÍÐR is a protected path (HEIMDALL forbids ODIN from rewriting its own exam).
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from odin.schemas import BenchmarkResult


class BenchmarkTask(BaseModel):
    """A single graded task."""

    id: str
    prompt: str
    expected: str
    match: Literal["exact", "contains"] = "exact"


class SolverOutput(BaseModel):
    """What a solver returns for one task."""

    answer: str
    tokens: int = 0
    latency_seconds: float = 0.0


class Solver(Protocol):
    """Anything that can answer a benchmark task (e.g. the ODIN agent loop)."""

    async def __call__(self, task: BenchmarkTask) -> SolverOutput: ...


def _grade(task: BenchmarkTask, answer: str) -> bool:
    if task.match == "exact":
        return answer.strip() == task.expected.strip()
    return task.expected.strip().lower() in answer.lower()


class BenchmarkSuite(BaseModel):
    """A named collection of graded tasks."""

    name: str
    tasks: list[BenchmarkTask] = Field(default_factory=list)

    async def run(self, solver: Solver) -> BenchmarkResult:
        passed = 0
        total_tokens = 0
        total_latency = 0.0
        details: list[dict[str, object]] = []

        for task in self.tasks:
            output = await solver(task)
            ok = _grade(task, output.answer)
            passed += int(ok)
            total_tokens += output.tokens
            total_latency += output.latency_seconds
            details.append(
                {
                    "task_id": task.id,
                    "passed": ok,
                    "answer": output.answer,
                    "expected": task.expected,
                    "tokens": output.tokens,
                }
            )

        n = len(self.tasks)
        return BenchmarkResult(
            suite=self.name,
            total=n,
            passed=passed,
            avg_tokens=total_tokens / n if n else 0.0,
            avg_latency_seconds=total_latency / n if n else 0.0,
            details=details,
        )


def make_default_suite() -> BenchmarkSuite:
    """A tiny built-in suite for smoke-testing the RSIP loop."""
    return BenchmarkSuite(
        name="vigridr-smoke",
        tasks=[
            BenchmarkTask(id="add", prompt="What is 2 + 2?", expected="4", match="contains"),
            BenchmarkTask(id="cap", prompt="Capital of France?", expected="Paris", match="contains"),
            BenchmarkTask(
                id="rev", prompt="Reverse the word 'odin'.", expected="nido", match="contains"
            ),
        ],
    )
