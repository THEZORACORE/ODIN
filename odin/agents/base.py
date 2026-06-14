"""Base agent interface — all ODIN agents derive from this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from odin.routing.llm_adapter import LLMAdapter
from odin.schemas import AgentMessage, AgentRole


class BaseAgent(ABC):
    """Abstract base for ODIN agents."""

    role: AgentRole
    system_prompt: str = ""

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm

    @abstractmethod
    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Process an incoming message and return a response."""
        ...

    def _make_response(self, to: AgentRole, content: str, **meta: Any) -> AgentMessage:
        return AgentMessage(
            sender=self.role,
            receiver=to,
            content=content,
            metadata=meta,
        )
