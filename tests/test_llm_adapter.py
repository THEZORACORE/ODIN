"""Tests for LLM adapters — FakeLLM, model router."""

import pytest

from odin.routing.llm_adapter import FakeLLM, LLMMessage, ModelRouter, TrackedLLM
from odin.schemas import BudgetState


class TestFakeLLM:
    @pytest.mark.asyncio
    async def test_returns_canned_response(self) -> None:
        llm = FakeLLM(responses=["hello world"])
        resp = await llm.complete([LLMMessage(role="user", content="hi")])
        assert resp.content == "hello world"
        assert resp.model == "fake-llm"

    @pytest.mark.asyncio
    async def test_cycles_responses(self) -> None:
        llm = FakeLLM(responses=["a", "b"])
        r1 = await llm.complete([LLMMessage(role="user", content="1")])
        r2 = await llm.complete([LLMMessage(role="user", content="2")])
        r3 = await llm.complete([LLMMessage(role="user", content="3")])
        assert r1.content == "a"
        assert r2.content == "b"
        assert r3.content == "a"  # Cycles back

    @pytest.mark.asyncio
    async def test_records_calls(self) -> None:
        llm = FakeLLM()
        await llm.complete([LLMMessage(role="user", content="test")])
        assert len(llm.calls) == 1
        assert llm.calls[0][0].content == "test"

    @pytest.mark.asyncio
    async def test_complete_json(self) -> None:
        llm = FakeLLM(responses=['{"key": "value"}'])
        result = await llm.complete_json([LLMMessage(role="user", content="json")])
        assert result == {"key": "value"}


class TestModelRouter:
    @pytest.mark.asyncio
    async def test_routes_to_cheap_by_default(self) -> None:
        llm = FakeLLM(responses=["ok"])
        router = ModelRouter(llm, cheap_model="cheap", frontier_model="frontier")
        resp = await router.complete([LLMMessage(role="user", content="hi")])
        assert resp.content == "ok"

    @pytest.mark.asyncio
    async def test_routes_to_frontier_when_requested(self) -> None:
        llm = FakeLLM(responses=["frontier response"])
        router = ModelRouter(llm, cheap_model="cheap", frontier_model="frontier")
        resp = await router.complete(
            [LLMMessage(role="user", content="complex task")],
            use_frontier=True,
        )
        assert resp.content == "frontier response"


class TestTrackedLLM:
    @pytest.mark.asyncio
    async def test_tracks_tokens_to_budget(self) -> None:
        """TrackedLLM forwards actual token counts to BudgetState."""
        budget = BudgetState(max_tokens=100_000, max_llm_calls=100)
        inner = FakeLLM(responses=["response"])  # FakeLLM tokens_used = len(text)
        tracked = TrackedLLM(inner, budget)

        resp = await tracked.complete([LLMMessage(role="user", content="hi")])
        assert resp.tokens_used == len("response")  # 8
        assert budget.tokens_used == len("response")
        assert budget.llm_calls_used == 1

    @pytest.mark.asyncio
    async def test_token_budget_exhaustion_via_tracked(self) -> None:
        """Prove budget-by-tokens triggers through TrackedLLM wrapper."""
        budget = BudgetState(max_tokens=20, max_llm_calls=100)
        inner = FakeLLM(responses=["twelve chars"])  # 12 tokens_used each
        tracked = TrackedLLM(inner, budget)

        await tracked.complete([LLMMessage(role="user", content="1")])
        assert budget.tokens_used == 12
        # Next call pushes to 24 > 20 max → exhausted
        from odin.safety.heimdall import BudgetExhausted
        with pytest.raises(BudgetExhausted):
            await tracked.complete([LLMMessage(role="user", content="2")])
