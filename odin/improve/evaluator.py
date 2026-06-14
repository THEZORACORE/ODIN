"""Sandbox-backed RSIP evaluator (wires Phase 4.5 isolation into the loop).

`SandboxEvaluator` implements MUNINN's `Evaluator` protocol against a *real*
metric: it checks the base revision out into an isolated worktree, runs the
project's test suite for the baseline, then applies the candidate diff in a
fresh worktree and re-runs the suite. A candidate that breaks tests scores a
lower pass rate and is rejected — concrete proof a self-improvement doesn't
regress, with no risk to the live checkout.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from odin.improve.sandbox import GitWorktreeSandbox
from odin.improve.shell import CommandRunner, SubprocessRunner
from odin.schemas import BenchmarkResult, ImprovementProposal

_DEFAULT_CMD: tuple[str, ...] = ("python", "-m", "pytest", "-q")
_PASSED = re.compile(r"(\d+) passed")
_FAILED = re.compile(r"(\d+) failed")
_ERRORS = re.compile(r"(\d+) errors?")


def parse_pytest_summary(output: str) -> tuple[int, int]:
    """Return (passed, total) parsed from a pytest summary line."""
    passed = int(m.group(1)) if (m := _PASSED.search(output)) else 0
    failed = int(m.group(1)) if (m := _FAILED.search(output)) else 0
    errored = int(m.group(1)) if (m := _ERRORS.search(output)) else 0
    return passed, passed + failed + errored


class SandboxEvaluator:
    """Benchmarks baseline vs candidate by running tests in isolated worktrees."""

    def __init__(
        self,
        repo_dir: str,
        *,
        base: str = "HEAD",
        suite: str = "pytest",
        benchmark_cmd: Sequence[str] = _DEFAULT_CMD,
        runner: CommandRunner | None = None,
        sandbox: GitWorktreeSandbox | None = None,
    ) -> None:
        self._suite = suite
        self._cmd = list(benchmark_cmd)
        self._runner = runner or SubprocessRunner()
        self._sandbox = sandbox or GitWorktreeSandbox(repo_dir, base=base, runner=self._runner)

    async def baseline(self) -> BenchmarkResult:
        return await self._measure(diff=None)

    async def candidate(self, proposal: ImprovementProposal) -> BenchmarkResult:
        return await self._measure(diff=proposal.diff)

    async def _measure(self, *, diff: str | None) -> BenchmarkResult:
        async with self._sandbox.worktree() as tree:
            if diff:
                await self._sandbox.apply_diff(tree, diff)
            output = await self._runner.run(self._cmd, cwd=tree, check=False)
        passed, total = parse_pytest_summary(output)
        return BenchmarkResult(suite=self._suite, total=total, passed=passed)
