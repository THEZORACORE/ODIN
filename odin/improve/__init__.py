"""ODIN self-improvement (RSIP) — MUNINN engine + VÍGRÍÐR benchmark.

Bounded, verified, human-gated recursive self-improvement.
"""

from odin.improve.benchmark import (
    BenchmarkSuite,
    BenchmarkTask,
    Solver,
    SolverOutput,
    make_default_suite,
)
from odin.improve.evaluator import SandboxEvaluator, parse_pytest_summary
from odin.improve.muninn import (
    DiffReviewer,
    Evaluator,
    LLMProposer,
    LokiDiffReviewer,
    Muninn,
    Proposer,
    Publisher,
)
from odin.improve.rollback import Rollback
from odin.improve.sandbox import GitWorktreeSandbox
from odin.improve.shell import CommandRunner, SubprocessRunner
from odin.improve.telemetry import (
    ImprovementTrigger,
    TelemetryEvent,
    TelemetrySink,
)

__all__ = [
    "BenchmarkSuite",
    "BenchmarkTask",
    "CommandRunner",
    "DiffReviewer",
    "Evaluator",
    "GitWorktreeSandbox",
    "ImprovementTrigger",
    "LLMProposer",
    "LokiDiffReviewer",
    "Muninn",
    "Proposer",
    "Publisher",
    "Rollback",
    "SandboxEvaluator",
    "Solver",
    "SolverOutput",
    "SubprocessRunner",
    "TelemetryEvent",
    "TelemetrySink",
    "make_default_suite",
    "parse_pytest_summary",
]
