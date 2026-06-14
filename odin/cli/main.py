"""CLI entrypoint — `odin run "<goal>"`

Wires all components together and runs the orchestration loop.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from odin.core.orchestrator import Orchestrator, OrchestratorResult
from odin.memory.mimir import Mimir
from odin.routing.llm_adapter import (
    AnthropicAdapter,
    FakeLLM,
    LLMAdapter,
    OpenAIAdapter,
)
from odin.safety.heimdall import Heimdall
from odin.schemas import ActionRisk, BudgetState
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
