"""Tests for the multi-agent society subsystem (Phase 8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from odin.routing.llm_adapter import FakeLLM
from odin.schemas import BudgetState
from odin.society.agents import AgentPool
from odin.society.debate import DebateJudge, DebateResult
from odin.society.ensemble import EnsembleAnswer, EnsembleResult, EnsembleRunner
from odin.society.ratatoskr import AgentMessage, MessageBus

# ---------------------------------------------------------------------------
# 8.1 RATATOSKR — message bus
# ---------------------------------------------------------------------------


class TestMessageBus:
    @pytest.fixture()
    def bus(self, tmp_path: Path) -> MessageBus:
        b = MessageBus(data_dir=str(tmp_path))
        yield b
        b.close()

    def test_publish_and_history(self, bus: MessageBus) -> None:
        msg = AgentMessage(id="m1", topic="planning", sender="odin", content="Start plan")
        bus.publish(msg)
        h = bus.history("planning")
        assert len(h) == 1
        assert h[0].content == "Start plan"

    def test_subscribe_cursor(self, bus: MessageBus) -> None:
        bus.publish(AgentMessage(id="m1", topic="t", sender="a", content="first"))
        msgs = bus.subscribe("t", "sub1")
        assert len(msgs) == 1

        bus.publish(AgentMessage(id="m2", topic="t", sender="b", content="second"))
        msgs = bus.subscribe("t", "sub1")
        assert len(msgs) == 1
        assert msgs[0].content == "second"

        # No new messages
        msgs = bus.subscribe("t", "sub1")
        assert len(msgs) == 0

    def test_thread(self, bus: MessageBus) -> None:
        bus.publish(AgentMessage(id="root", topic="t", sender="a", content="question"))
        bus.publish(AgentMessage(id="reply1", topic="t", sender="b", content="answer", in_reply_to="root"))
        thread = bus.get_thread("root")
        assert len(thread) == 2

    def test_topics(self, bus: MessageBus) -> None:
        bus.publish(AgentMessage(id="m1", topic="alpha", sender="a", content="x"))
        bus.publish(AgentMessage(id="m2", topic="beta", sender="a", content="y"))
        t = bus.topics()
        assert "alpha" in t
        assert "beta" in t

    def test_stats(self, bus: MessageBus) -> None:
        bus.publish(AgentMessage(id="m1", topic="t", sender="a", content="x"))
        s = bus.stats()
        assert s["messages"] == 1
        assert s["topics"] == 1
        assert s["senders"] == 1


# ---------------------------------------------------------------------------
# 8.2 VÉ & VILI — ensembles
# ---------------------------------------------------------------------------


class TestEnsembleRunner:
    @pytest.mark.asyncio
    async def test_single_reasoner(self) -> None:
        llm = FakeLLM(responses=["The answer is 42."])
        runner = EnsembleRunner([("r1", llm)])
        result = await runner.ask("What is the answer?")
        assert isinstance(result, EnsembleResult)
        assert len(result.answers) == 1
        assert result.agreement_ratio == 1.0

    @pytest.mark.asyncio
    async def test_multiple_reasoners(self) -> None:
        llm1 = FakeLLM(responses=["The answer is 42."])
        llm2 = FakeLLM(responses=["42 is the answer."])
        llm3 = FakeLLM(responses=["I think the answer is 42."])
        runner = EnsembleRunner([("r1", llm1), ("r2", llm2), ("r3", llm3)])
        result = await runner.ask("What is the answer?")
        assert len(result.answers) == 3
        assert result.consensus  # non-empty
        assert result.agreement_ratio > 0

    @pytest.mark.asyncio
    async def test_aggregation_picks_most_similar(self) -> None:
        answers = [
            EnsembleAnswer(reasoner_id="a", answer="yes it is correct", confidence=1.0),
            EnsembleAnswer(reasoner_id="b", answer="yes it is right", confidence=1.0),
            EnsembleAnswer(reasoner_id="c", answer="no completely wrong", confidence=1.0),
        ]
        consensus, ratio = EnsembleRunner._aggregate(answers)
        # a and b are more similar to each other than to c
        assert consensus in ("yes it is correct", "yes it is right")


# ---------------------------------------------------------------------------
# 8.3 FORSETI — debate & consensus
# ---------------------------------------------------------------------------


class TestDebateJudge:
    @pytest.mark.asyncio
    async def test_debate_runs(self) -> None:
        proposer = FakeLLM(responses=["I argue for: strong evidence supports this."] * 3)
        opponent = FakeLLM(responses=["I argue against: the evidence is weak."] * 3)
        judge = FakeLLM(responses=["The proposer has the stronger argument. Confidence: 75%."])
        dj = DebateJudge(proposer, opponent, judge, rounds=1)

        result = await dj.debate("Is the sky blue?")
        assert isinstance(result, DebateResult)
        assert len(result.rounds) == 1
        assert result.confidence == 0.75
        assert result.ruling

    @pytest.mark.asyncio
    async def test_multi_round(self) -> None:
        proposer = FakeLLM(responses=["For argument."] * 5)
        opponent = FakeLLM(responses=["Against argument."] * 5)
        judge = FakeLLM(responses=["Undecided. 50%."])
        dj = DebateJudge(proposer, opponent, judge, rounds=3)

        result = await dj.debate("Test question")
        assert len(result.rounds) == 3

    def test_extract_confidence(self) -> None:
        assert DebateJudge._extract_confidence("Confidence: 80%") == 0.8
        assert DebateJudge._extract_confidence("No percentage here") == 0.5

    def test_extract_winner(self) -> None:
        assert DebateJudge._extract_winner("The proposer wins") == "proposer"
        assert DebateJudge._extract_winner("The opponent wins") == "opponent"
        assert DebateJudge._extract_winner("Unclear") == "undecided"


# ---------------------------------------------------------------------------
# 8.4–8.5 DRAUPNIR & SLEIPNIR — sub-agents & parallel execution
# ---------------------------------------------------------------------------


class TestAgentPool:
    @pytest.mark.asyncio
    async def test_spawn_and_delegate(self) -> None:
        llm = FakeLLM(responses=["Task completed successfully."])
        pool = AgentPool(llm, max_agents=4)
        pool.spawn("a1", "Worker-1", "analyst")
        result = await pool.delegate("a1", "Analyze this data")
        assert "Task completed" in result

    @pytest.mark.asyncio
    async def test_fan_out(self) -> None:
        llm = FakeLLM(responses=["Result A", "Result B", "Result C"])
        pool = AgentPool(llm, max_agents=4)
        pool.spawn("a1", "W1", "analyst")
        pool.spawn("a2", "W2", "analyst")
        pool.spawn("a3", "W3", "analyst")

        results = await pool.fan_out([("a1", "Task 1"), ("a2", "Task 2"), ("a3", "Task 3")])
        assert len(results) == 3
        agent_ids = [r[0] for r in results]
        assert "a1" in agent_ids

    def test_pool_cap(self) -> None:
        llm = FakeLLM(responses=[])
        pool = AgentPool(llm, max_agents=2)
        pool.spawn("a1", "W1", "r")
        pool.spawn("a2", "W2", "r")
        with pytest.raises(RuntimeError, match="pool full"):
            pool.spawn("a3", "W3", "r")

    def test_reclaim(self) -> None:
        llm = FakeLLM(responses=[])
        pool = AgentPool(llm, max_agents=2)
        pool.spawn("a1", "W1", "r")
        agent = pool.reclaim("a1")
        assert agent is not None
        assert agent.status == "reclaimed"
        assert len(pool.active_agents()) == 0

    @pytest.mark.asyncio
    async def test_budget_exhaustion(self) -> None:
        llm = FakeLLM(responses=["ok"])
        tiny_budget = BudgetState(max_tokens=1, max_llm_calls=1, max_tool_calls=1)
        pool = AgentPool(llm, max_agents=4)
        pool.spawn("a1", "W1", "r", budget=tiny_budget)
        await pool.delegate("a1", "first task")
        with pytest.raises(RuntimeError, match="budget exhausted"):
            await pool.delegate("a1", "second task")

    def test_stats(self) -> None:
        llm = FakeLLM(responses=[])
        pool = AgentPool(llm, max_agents=4)
        pool.spawn("a1", "W1", "analyst")
        s = pool.stats()
        assert s["total_agents"] == 1
        assert s["active_agents"] == 1
        assert s["max_agents"] == 4
