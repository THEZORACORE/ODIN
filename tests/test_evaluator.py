"""Tests for the sandbox-backed RSIP evaluator."""

from __future__ import annotations

from collections.abc import Sequence

from odin.improve.evaluator import SandboxEvaluator, parse_pytest_summary
from odin.improve.sandbox import GitWorktreeSandbox
from odin.schemas import ImprovementProposal


class TestParse:
    def test_all_passed(self) -> None:
        assert parse_pytest_summary("109 passed in 2.57s") == (109, 109)

    def test_failures_and_errors(self) -> None:
        assert parse_pytest_summary("1 failed, 2 passed, 1 error in 0.1s") == (2, 4)

    def test_no_tests(self) -> None:
        assert parse_pytest_summary("no tests ran") == (0, 0)


class SeqRunner:
    """Returns queued outputs for the benchmark command; '' for git plumbing."""

    def __init__(self, pytest_outputs: list[str]) -> None:
        self._outputs = list(pytest_outputs)
        self.calls: list[list[str]] = []

    async def run(
        self,
        args: Sequence[str],
        *,
        cwd: str | None = None,
        stdin: str | None = None,
        check: bool = True,
    ) -> str:
        self.calls.append(list(args))
        if "pytest" in args:
            return self._outputs.pop(0)
        return ""


class TestSandboxEvaluator:
    async def test_baseline_and_candidate(self) -> None:
        runner = SeqRunner(["3 passed in 0.1s", "1 failed, 2 passed in 0.1s"])
        sandbox = GitWorktreeSandbox("/repo", runner=runner)
        evaluator = SandboxEvaluator("/repo", runner=runner, sandbox=sandbox)

        baseline = await evaluator.baseline()
        assert baseline.passed == 3
        assert baseline.pass_rate == 1.0

        proposal = ImprovementProposal(
            target_file="odin/x.py", rationale="r", diff="+ a\n- b"
        )
        candidate = await evaluator.candidate(proposal)
        assert candidate.passed == 2
        assert candidate.total == 3

        # the candidate run applied the diff inside the worktree; the baseline didn't
        assert ["git", "apply", "-"] in runner.calls
