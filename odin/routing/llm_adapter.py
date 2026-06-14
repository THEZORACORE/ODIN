"""Provider-agnostic LLM adapter.

Supports Anthropic, OpenAI, and a deterministic FakeLLM for offline tests.
Keys are read from env vars: ANTHROPIC_API_KEY, OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from odin.schemas.common import BudgetState

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

class LLMMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str
    tokens_used: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------

class LLMAdapter(ABC):
    """Interface every LLM backend implements."""

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Complete and parse the result as JSON."""
        ...


# ---------------------------------------------------------------------------
# FakeLLM — deterministic, offline, for tests
# ---------------------------------------------------------------------------

class FakeLLM(LLMAdapter):
    """Returns canned responses for testing.  No network calls."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ["FakeLLM default response."])
        self._call_count = 0
        self.calls: list[list[LLMMessage]] = []

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        self.calls.append(messages)
        text = self._responses[self._call_count % len(self._responses)]
        self._call_count += 1
        return LLMResponse(content=text, model="fake-llm", tokens_used=len(text))

    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        resp = await self.complete(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        result: dict[str, Any] = json.loads(resp.content)
        return result


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------

class AnthropicAdapter(LLMAdapter):
    """Wraps the Anthropic Python SDK (messages API)."""

    def __init__(self, api_key: str | None = None, default_model: str = "claude-sonnet-4-20250514") -> None:  # noqa: E501
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        system_msg = ""
        api_messages: list[dict[str, str]] = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        kwargs: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": api_messages,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if stop:
            kwargs["stop_sequences"] = stop

        resp = await client.messages.create(**kwargs)
        text = resp.content[0].text if resp.content else ""
        tokens = (resp.usage.input_tokens or 0) + (resp.usage.output_tokens or 0)
        return LLMResponse(content=text, model=kwargs["model"], tokens_used=tokens)

    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        resp = await self.complete(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        cleaned = resp.content.strip()
        # Strip markdown fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        result: dict[str, Any] = json.loads(cleaned)
        return result


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------

class OpenAIAdapter(LLMAdapter):
    """Wraps the OpenAI Python SDK (chat completions)."""

    def __init__(self, api_key: str | None = None, default_model: str = "gpt-4o") -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._default_model = default_model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": api_messages,
        }
        if stop:
            kwargs["stop"] = stop

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        return LLMResponse(content=text, model=kwargs["model"], tokens_used=tokens)

    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        resp = await self.complete(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        cleaned = resp.content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        result: dict[str, Any] = json.loads(cleaned)
        return result


# ---------------------------------------------------------------------------
# Model router — cheap vs frontier
# ---------------------------------------------------------------------------

class ModelRouter:
    """Routes requests to cheap or frontier models based on task requirements."""

    def __init__(
        self,
        adapter: LLMAdapter,
        cheap_model: str = "claude-haiku-4-20250414",
        frontier_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.adapter = adapter
        self.cheap_model = cheap_model
        self.frontier_model = frontier_model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        use_frontier: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        model = self.frontier_model if use_frontier else self.cheap_model
        return await self.adapter.complete(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )

    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        use_frontier: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        model = self.frontier_model if use_frontier else self.cheap_model
        return await self.adapter.complete_json(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )


# ---------------------------------------------------------------------------
# Budget-tracked LLM wrapper
# ---------------------------------------------------------------------------

class TrackedLLM(LLMAdapter):
    """Wraps any LLMAdapter to auto-record token usage to a BudgetState.

    Every complete()/complete_json() call forwards the token count
    from the LLM response to budget.record_llm_call(tokens), so ALL
    callers (planner, executor, verifier, critic, renderer) get tracked
    without any changes to their code.
    """

    def __init__(self, inner: LLMAdapter, budget: BudgetState) -> None:
        self._inner = inner
        self._budget = budget

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        resp = await self._inner.complete(
            messages, model=model, temperature=temperature,
            max_tokens=max_tokens, stop=stop,
        )
        self._budget.record_llm_call(resp.tokens_used)
        if self._budget.is_exhausted():
            from odin.safety.heimdall import BudgetExhausted
            raise BudgetExhausted(
                f"tokens={self._budget.tokens_used}/{self._budget.max_tokens}, "
                f"llm_calls={self._budget.llm_calls_used}/{self._budget.max_llm_calls}"
            )
        return resp

    async def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        # Route through self.complete() so token tracking happens
        resp = await self.complete(
            messages, model=model, temperature=temperature, max_tokens=max_tokens,
        )
        cleaned = resp.content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        result: dict[str, Any] = json.loads(cleaned)
        return result
