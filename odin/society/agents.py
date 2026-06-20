"""DRAUPNIR & SLEIPNIR — Sub-agent lifecycle & parallel execution (8.4, 8.5).

DRAUPNIR (the ring that replicates): spawn scoped sub-agents on demand,
reclaim them, enforce hard lifecycle and budget caps.

SLEIPNIR (Odin's 8-legged horse): concurrent sub-task execution across
multiple sub-agents with result aggregation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from odin.routing.llm_adapter import LLMAdapter, LLMMessage
from odin.schemas import BudgetState

logger = logging.getLogger("odin.society.agents")


class SubAgent(BaseModel):
    """A scoped sub-agent with its own budget and lifecycle."""

    id: str
    name: str
    role: str
    budget: BudgetState = Field(default_factory=BudgetState)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "active"
    result: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentPool:
    """DRAUPNIR + SLEIPNIR — spawn, run, and reclaim sub-agents.

    Manages a pool of sub-agents with:
    - Hard budget caps per agent (DRAUPNIR lifecycle control)
    - Concurrent execution (SLEIPNIR parallelism)
    - Result aggregation
    """

    def __init__(
        self,
        llm: LLMAdapter,
        max_agents: int = 8,
        default_budget: BudgetState | None = None,
    ) -> None:
        self._llm = llm
        self._max_agents = max_agents
        self._default_budget = default_budget or BudgetState(
            max_tokens=5000, max_llm_calls=10, max_tool_calls=5,
        )
        self._agents: dict[str, SubAgent] = {}

    def spawn(self, agent_id: str, name: str, role: str, budget: BudgetState | None = None) -> SubAgent:
        """Spawn a new sub-agent (DRAUPNIR)."""
        if len(self._agents) >= self._max_agents:
            self._reclaim_completed()
        if len(self._agents) >= self._max_agents:
            raise RuntimeError(f"Agent pool full ({self._max_agents} max)")

        agent = SubAgent(
            id=agent_id,
            name=name,
            role=role,
            budget=budget or self._default_budget.model_copy(),
        )
        self._agents[agent_id] = agent
        logger.info("Spawned sub-agent: %s (%s)", name, role)
        return agent

    def reclaim(self, agent_id: str) -> SubAgent | None:
        """Reclaim a sub-agent (DRAUPNIR)."""
        agent = self._agents.pop(agent_id, None)
        if agent:
            agent.status = "reclaimed"
            logger.info("Reclaimed sub-agent: %s", agent.name)
        return agent

    async def delegate(self, agent_id: str, task: str, system_prompt: str = "") -> str:
        """Delegate a task to a specific sub-agent."""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Sub-agent {agent_id} not found")
        if agent.status != "active":
            raise RuntimeError(f"Sub-agent {agent_id} is {agent.status}")
        if agent.budget.is_exhausted():
            agent.status = "budget_exhausted"
            raise RuntimeError(f"Sub-agent {agent_id} budget exhausted")

        messages = [
            LLMMessage(role="system", content=system_prompt or f"You are {agent.name}, role: {agent.role}"),
            LLMMessage(role="user", content=task),
        ]
        response = await self._llm.complete(messages)
        agent.budget.record_llm_call(response.tokens_used)
        agent.result = response.content
        return response.content

    async def fan_out(
        self,
        tasks: list[tuple[str, str]],
        system_prompt: str = "",
    ) -> list[tuple[str, str]]:
        """SLEIPNIR — execute multiple tasks concurrently across sub-agents.

        Args:
            tasks: [(agent_id, task_description), ...]
            system_prompt: shared system prompt

        Returns:
            [(agent_id, result), ...]
        """
        async def _run(agent_id: str, task: str) -> tuple[str, str]:
            try:
                result = await self.delegate(agent_id, task, system_prompt)
                return agent_id, result
            except Exception as e:
                return agent_id, f"[ERROR] {e}"

        results = await asyncio.gather(
            *[_run(aid, task) for aid, task in tasks]
        )
        return list(results)

    def get_agent(self, agent_id: str) -> SubAgent | None:
        return self._agents.get(agent_id)

    def active_agents(self) -> list[SubAgent]:
        return [a for a in self._agents.values() if a.status == "active"]

    def stats(self) -> dict[str, int]:
        active = sum(1 for a in self._agents.values() if a.status == "active")
        total_tokens = sum(a.budget.tokens_used for a in self._agents.values())
        return {
            "total_agents": len(self._agents),
            "active_agents": active,
            "max_agents": self._max_agents,
            "total_tokens_used": total_tokens,
        }

    def _reclaim_completed(self) -> None:
        """Auto-reclaim completed or exhausted agents."""
        to_reclaim = [
            aid for aid, a in self._agents.items()
            if a.status in ("completed", "budget_exhausted", "reclaimed")
        ]
        for aid in to_reclaim:
            del self._agents[aid]
