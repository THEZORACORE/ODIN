"""CLI entrypoint — `odin run "<goal>"`

Wires all components together and runs the orchestration loop.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from odin.core.orchestrator import Orchestrator, OrchestratorResult
from odin.github import FakeBifrost, GhBifrost
from odin.github.bifrost import Bifrost
from odin.improve.evaluator import SandboxEvaluator
from odin.improve.muninn import Evaluator, LLMProposer, LokiDiffReviewer, Muninn
from odin.improve.rollback import Rollback
from odin.improve.telemetry import TelemetrySink
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import (
    AnthropicAdapter,
    FakeLLM,
    LLMAdapter,
    OpenAIAdapter,
)
from odin.safety.heimdall import Heimdall
from odin.schemas import ActionRisk, BenchmarkResult, BudgetState, ImprovementProposal
from odin.tools.code_interpreter import execute_python
from odin.tools.registry import ToolRegistry, ToolSpec
from odin.tools.web_search import auto_configure_search, web_search

console = Console()


def _build_llm() -> LLMAdapter:
    """Select LLM backend from environment."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[dim]Using Anthropic backend[/dim]")
        return AnthropicAdapter()
    elif os.environ.get("OPENAI_API_KEY"):
        console.print("[dim]Using OpenAI backend[/dim]")
        return OpenAIAdapter()
    else:
        console.print("[yellow]No API key found — using FakeLLM (demo mode)[/yellow]")
        return FakeLLM()


def _build_tools(heimdall: Heimdall) -> ToolRegistry:
    """Register available tools."""
    registry = ToolRegistry(heimdall)
    registry.register(ToolSpec(
        name="code_interpreter",
        description="Execute Python code in a sandboxed environment. Input: 'code' (str).",
        fn=execute_python,
        risk=ActionRisk.MEDIUM,
        parameter_schema={"code": {"type": "string", "description": "Python code to execute"}},
    ))
    registry.register(ToolSpec(
        name="web_search",
        description="Search the web. Input: 'query' (str), optional 'max_results' (int).",
        fn=web_search,
        risk=ActionRisk.LOW,
        parameter_schema={
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results", "default": 5},
        },
    ))
    return registry


def _display_result(result: OrchestratorResult) -> None:
    """Rich-formatted output."""
    status = "[green]SUCCESS[/green]" if result.success else "[red]PARTIAL/FAILED[/red]"
    console.print(Panel(
        f"[bold]Goal:[/bold] {result.goal}\n"
        f"[bold]Status:[/bold] {status}\n"
        f"[bold]Session:[/bold] {result.session_id}",
        title="ODIN — Orchestration Result",
    ))

    # Plan summary
    table = Table(title="Plan Execution")
    table.add_column("Step", style="cyan")
    table.add_column("Goal", max_width=50)
    table.add_column("Status", justify="center")
    table.add_column("Retries", justify="center")

    for node in result.plan.nodes:
        status_style = {
            "completed": "[green]✓[/green]",
            "failed": "[red]✗[/red]",
            "pending": "[yellow]○[/yellow]",
            "skipped": "[dim]—[/dim]",
        }.get(node.status.value, node.status.value)
        table.add_row(node.id, node.goal[:50], status_style, str(node.retries))

    console.print(table)

    # Verification summary
    if result.verdicts:
        v_table = Table(title="Verification Summary")
        v_table.add_column("Method")
        v_table.add_column("Outcome")
        v_table.add_column("Confidence")
        for v in result.verdicts:
            outcome_style = {
                "pass": "[green]PASS[/green]",
                "fail": "[red]FAIL[/red]",
                "uncertain": "[yellow]UNCERTAIN[/yellow]",
            }.get(v.outcome.value, v.outcome.value)
            v_table.add_row(v.method, outcome_style, f"{v.confidence:.0%}")
        console.print(v_table)

    # Budget
    b = result.budget_state
    console.print(
        f"\n[dim]Budget: {b.tokens_used}/{b.max_tokens} tokens, "
        f"{b.llm_calls_used}/{b.max_llm_calls} LLM calls, "
        f"{b.tool_calls_used}/{b.max_tool_calls} tool calls[/dim]"
    )

    # Final answer
    console.print(Panel(result.answer, title="Final Answer", border_style="green"))


async def _run_goal(
    goal: str,
    data_dir: str,
    session_id: str,
    max_tokens: int,
    max_llm_calls: int,
    max_tool_calls: int,
    max_time: float,
) -> OrchestratorResult:
    """Core async runner."""
    auto_configure_search()
    llm = _build_llm()
    budget = BudgetState(
        max_tokens=max_tokens,
        max_llm_calls=max_llm_calls,
        max_tool_calls=max_tool_calls,
        max_wall_clock_seconds=max_time,
    )
    heimdall = Heimdall(budget=budget)
    tools = _build_tools(heimdall)
    mimir = Mimir(data_dir=data_dir, llm=llm, use_chroma=True)

    orchestrator = Orchestrator(
        llm=llm,
        tools=tools,
        heimdall=heimdall,
        mimir=mimir,
        session_id=session_id,
        budget=budget,
    )

    try:
        result = await orchestrator.run(goal)
        return result
    finally:
        mimir.save()
        mimir.close()


@click.group()
def cli() -> None:
    """ODIN — Orchestrated Deductive Intelligence Network."""
    pass


@cli.command()
@click.argument("goal")
@click.option("--data-dir", default=".odin_data", help="Persistence directory")
@click.option("--session-id", default=None, help="Session ID (auto-generated if omitted)")
@click.option("--max-tokens", default=500_000, help="Max token budget")
@click.option("--max-llm-calls", default=200, help="Max LLM calls")
@click.option("--max-tool-calls", default=100, help="Max tool calls")
@click.option("--max-time", default=600.0, help="Max wall-clock seconds")
def run(
    goal: str,
    data_dir: str,
    session_id: str | None,
    max_tokens: int,
    max_llm_calls: int,
    max_tool_calls: int,
    max_time: float,
) -> None:
    """Run ODIN on a goal.

    Example: odin run "research Python async patterns, write a comparison, summarize with sources"
    """
    sid = session_id or uuid.uuid4().hex[:8]
    console.print(f"[bold blue]ODIN[/bold blue] starting session [cyan]{sid}[/cyan]")
    console.print(f"Goal: [italic]{goal}[/italic]\n")

    result = asyncio.run(_run_goal(
        goal, data_dir, sid, max_tokens, max_llm_calls, max_tool_calls, max_time
    ))
    _display_result(result)


class _DemoEvaluator:
    """Deterministic evaluator for the offline RSIP demo (no real sandbox)."""

    async def baseline(self) -> BenchmarkResult:
        return BenchmarkResult(suite="vigridr-smoke", total=3, passed=1, avg_tokens=300.0)

    async def candidate(self, proposal: ImprovementProposal) -> BenchmarkResult:
        return BenchmarkResult(suite="vigridr-smoke", total=3, passed=3, avg_tokens=180.0)


async def _run_rsip_demo() -> None:
    """Run one bounded, verified, human-gated self-improvement cycle, fully offline."""
    proposal_json = json.dumps(
        {
            "target_file": "odin/agents/freya_renderer.py",
            "rationale": "tighten the answer-rendering prompt to cite sources more reliably",
            "diff": "+ cite every claim\n- vague summary",
            "expected_metric": "pass_rate",
            "expected_metric_delta": 0.66,
            "risk": "low",
        }
    )
    review_json = json.dumps(
        {"outcome": "pass", "explanation": "scoped, safe, improves grounding", "confidence": 0.85}
    )
    llm = FakeLLM(responses=[proposal_json, review_json])

    muninn = Muninn(
        heimdall=Heimdall(),
        proposer=LLMProposer(llm),
        evaluator=_DemoEvaluator(),
        reviewer=LokiDiffReviewer(llm),
        publisher=FakeBifrost(),
    )
    outcome = await muninn.run_cycle("FREYA sometimes omits citations")

    verdict = "[green]ACCEPTED[/green]" if outcome.accepted else "[red]REJECTED[/red]"
    body = f"[bold]Decision:[/bold] {verdict}\n"
    if outcome.baseline and outcome.candidate:
        body += (
            f"[bold]VÍGRÍÐR:[/bold] pass_rate "
            f"{outcome.baseline.pass_rate:.2f} → {outcome.candidate.pass_rate:.2f}, "
            f"avg_tokens {outcome.baseline.avg_tokens:.0f} → {outcome.candidate.avg_tokens:.0f}\n"
        )
    body += "[bold]Reasons:[/bold]\n" + "\n".join(f"  • {r}" for r in outcome.reasons)
    if outcome.pr_url:
        body += f"\n[bold]PR:[/bold] {outcome.pr_url} (awaiting human review)"
    console.print(Panel(body, title="MUNINN — RSIP cycle (offline demo)", border_style="blue"))


@cli.command(name="rsip-demo")
def rsip_demo() -> None:
    """Demonstrate the self-improvement loop end-to-end, fully offline (FakeLLM)."""
    asyncio.run(_run_rsip_demo())


async def _run_rsip_live(weakness: str, repo: str, repo_dir: str, base: str) -> None:
    """Run a real RSIP cycle: real LLM, sandbox-tested candidate, BIFRÖST PR."""
    llm = _build_llm()
    publisher: Bifrost = GhBifrost(repo=repo, base=base)
    evaluator: Evaluator = SandboxEvaluator(repo_dir, base=base)
    muninn = Muninn(
        heimdall=Heimdall(),
        proposer=LLMProposer(llm),
        evaluator=evaluator,
        reviewer=LokiDiffReviewer(llm),
        publisher=publisher,
    )
    console.print(f"[dim]Running live RSIP cycle against {repo} (base {base})…[/dim]")
    outcome = await muninn.run_cycle(weakness)
    verdict = "[green]ACCEPTED[/green]" if outcome.accepted else "[red]REJECTED[/red]"
    body = f"[bold]Decision:[/bold] {verdict}\n"
    body += "[bold]Reasons:[/bold]\n" + "\n".join(f"  \u2022 {r}" for r in outcome.reasons)
    if outcome.pr_url:
        body += f"\n[bold]PR:[/bold] {outcome.pr_url} (awaiting human review)"
    console.print(Panel(body, title="MUNINN — live RSIP cycle", border_style="blue"))


@cli.command(name="rsip")
@click.argument("weakness")
@click.option("--repo", default="THEZORACORE/ODIN", help="owner/repo BIFRÖST opens the PR against")
@click.option("--repo-dir", default=".", help="local git checkout to sandbox-test in")
@click.option("--base", default="main", help="base branch / revision")
def rsip(weakness: str, repo: str, repo_dir: str, base: str) -> None:
    """Run a LIVE self-improvement cycle: tests the candidate in an isolated git
    worktree and opens a real PR via BIFRÖST (a human still merges).
    """
    asyncio.run(_run_rsip_live(weakness, repo, repo_dir, base))


@cli.command(name="rollback")
@click.option("--commit", default=None, help="commit SHA to revert (default: last RSIP commit)")
@click.option("--repo-dir", default=".", help="local git checkout")
def rollback(commit: str | None, repo_dir: str) -> None:
    """Safely undo a self-improvement: `git revert` the last RSIP commit (or --commit)."""

    async def _go() -> None:
        rb = Rollback(repo_dir)
        if commit is not None:
            await rb.revert(commit)
            console.print(f"[green]Reverted[/green] {commit}")
            return
        reverted = await rb.revert_last_rsip()
        if reverted is None:
            console.print("[yellow]No RSIP commit found to roll back.[/yellow]")
        else:
            console.print(f"[green]Reverted last RSIP commit[/green] {reverted}")

    asyncio.run(_go())


@cli.command(name="rsip-triggers")
def rsip_triggers() -> None:
    """Demonstrate telemetry-driven improvement triggers (Phase 4.1), offline."""
    sink = TelemetrySink()
    # Simulate signals an orchestration run might emit.
    sink.record("verdict_fail", detail="self_consistency", weight=1.0)
    sink.record("verdict_fail", detail="self_consistency", weight=1.0)
    sink.record("low_confidence", detail="critic", weight=0.5)
    sink.record("budget_exhausted", detail="run exhausted its budget", weight=2.0)
    triggers = sink.derive_triggers(min_score=1.0)

    table = Table(title="MUNINN — telemetry-derived improvement triggers")
    table.add_column("Score", style="cyan")
    table.add_column("Occurrences")
    table.add_column("Weakness")
    for t in triggers:
        table.add_row(f"{t.score:.1f}", str(t.occurrences), t.weakness)
    console.print(table)
    if triggers:
        console.print(
            f"[dim]Top trigger would seed: muninn.run_cycle(\"{triggers[0].weakness}\")[/dim]"
        )


@cli.command()
@click.option("--data-dir", default=".odin_data", help="Persistence directory")
def memories(data_dir: str) -> None:
    """Show stored memories."""
    mimir = Mimir(data_dir=data_dir, use_chroma=False)
    records = mimir._sqlite.all_records()
    if not records:
        console.print("[dim]No memories stored yet.[/dim]")
        return

    table = Table(title="MIMIR — Stored Memories")
    table.add_column("ID", style="cyan", max_width=12)
    table.add_column("Type")
    table.add_column("Content", max_width=60)
    table.add_column("Session")
    table.add_column("Created")

    for r in records:
        table.add_row(
            r.id, r.memory_type.value, r.content[:60],
            r.session_id or "—", r.created_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)
    mimir.close()


if __name__ == "__main__":
    cli()
