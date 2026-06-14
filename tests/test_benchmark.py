"""Tests for the VÍGRÍÐR benchmark harness."""

from odin.improve.benchmark import (
    BenchmarkSuite,
    BenchmarkTask,
    SolverOutput,
    make_default_suite,
)


def _suite() -> BenchmarkSuite:
    return BenchmarkSuite(
        name="t",
        tasks=[
            BenchmarkTask(id="a", prompt="2+2?", expected="4", match="contains"),
            BenchmarkTask(id="b", prompt="cap fr?", expected="Paris", match="contains"),
        ],
    )


class TestBenchmark:
    async def test_all_pass(self) -> None:
        answers = {"a": "4", "b": "It is Paris"}

        async def solver(task: BenchmarkTask) -> SolverOutput:
            return SolverOutput(answer=answers[task.id], tokens=10)

        result = await _suite().run(solver)
        assert result.total == 2
        assert result.passed == 2
        assert result.pass_rate == 1.0
        assert result.avg_tokens == 10.0

    async def test_partial_fail(self) -> None:
        async def solver(task: BenchmarkTask) -> SolverOutput:
            return SolverOutput(answer="wrong", tokens=5)

        result = await _suite().run(solver)
        assert result.passed == 0
        assert result.pass_rate == 0.0

    async def test_exact_match_is_strict(self) -> None:
        suite = BenchmarkSuite(
            name="x", tasks=[BenchmarkTask(id="e", prompt="?", expected="4", match="exact")]
        )

        async def solver(task: BenchmarkTask) -> SolverOutput:
            return SolverOutput(answer="the answer is 4")

        result = await suite.run(solver)
        assert result.passed == 0  # contains 4 but not exact

    async def test_default_suite_shape(self) -> None:
        suite = make_default_suite()
        assert suite.name == "vigridr-smoke"
        assert len(suite.tasks) == 3
