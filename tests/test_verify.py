"""Tests for the verification engine — self-consistency, critic, tool-grounding."""

import pytest

from odin.routing.llm_adapter import FakeLLM
from odin.schemas import VerdictRecord, VerifyOutcome
from odin.verify.verifier import Verifier, aggregate_verdicts


class TestSelfConsistency:
    @pytest.mark.asyncio
    async def test_pass_when_answers_agree(self) -> None:
        # One structured re-derivation call; agreement decided by similarity, no judge call.
        llm = FakeLLM(responses=['{"final_answer": "42"}'])
        v = Verifier(llm)
        result = await v.self_consistency("n1", "What is 6*7?", "The answer is 42.")
        assert result.outcome == VerifyOutcome.PASS
        assert result.method == "self_consistency"

    @pytest.mark.asyncio
    async def test_fail_when_answers_disagree(self) -> None:
        llm = FakeLLM(responses=['{"final_answer": "43"}'])
        v = Verifier(llm)
        result = await v.self_consistency("n1", "What is 6*7?", "The answer is 42.")
        assert result.outcome == VerifyOutcome.FAIL

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_text_when_not_json(self) -> None:
        # No JSON: raw content is used as the re-derived answer.
        llm = FakeLLM(responses=["Paris"])
        v = Verifier(llm)
        result = await v.self_consistency("n1", "Capital of France?", "The capital is Paris")
        assert result.outcome == VerifyOutcome.PASS


class TestCritic:
    @pytest.mark.asyncio
    async def test_critic_approves(self) -> None:
        llm = FakeLLM(responses=[
            '{"has_issues": false, "issues": [], "severity": "low", "recommendation": "approve"}',
        ])
        v = Verifier(llm)
        result = await v.critic("n1", "What is 2+2?", "4")
        assert result.outcome == VerifyOutcome.PASS

    @pytest.mark.asyncio
    async def test_critic_rejects(self) -> None:
        llm = FakeLLM(responses=[
            '{"has_issues": true, "issues": ["Wrong calculation"], "severity": "high", "recommendation": "reject"}',
        ])
        v = Verifier(llm)
        result = await v.critic("n1", "What is 2+2?", "5")
        assert result.outcome == VerifyOutcome.FAIL

    @pytest.mark.asyncio
    async def test_critic_revise(self) -> None:
        llm = FakeLLM(responses=[
            '{"has_issues": true, "issues": ["Missing context"], "severity": "medium", "recommendation": "revise"}',
        ])
        v = Verifier(llm)
        result = await v.critic("n1", "Explain X", "X is a thing")
        assert result.outcome == VerifyOutcome.UNCERTAIN


class TestToolGrounding:
    @pytest.mark.asyncio
    async def test_code_matches(self) -> None:
        v = Verifier(FakeLLM())
        result = await v.tool_grounding("n1", "42", "print(6*7)")
        assert result.outcome == VerifyOutcome.PASS
        assert result.method == "tool_grounding"

    @pytest.mark.asyncio
    async def test_code_mismatch(self) -> None:
        v = Verifier(FakeLLM())
        result = await v.tool_grounding("n1", "99", "print(6*7)")
        assert result.outcome == VerifyOutcome.FAIL

    @pytest.mark.asyncio
    async def test_code_error(self) -> None:
        v = Verifier(FakeLLM())
        result = await v.tool_grounding("n1", "42", "raise ValueError('boom')")
        assert result.outcome == VerifyOutcome.FAIL


class TestAggregateVerdicts:
    def test_all_pass(self) -> None:
        verdicts = [
            VerdictRecord(node_id="n", outcome=VerifyOutcome.PASS, method="a", explanation="ok"),
            VerdictRecord(node_id="n", outcome=VerifyOutcome.PASS, method="b", explanation="ok"),
        ]
        assert aggregate_verdicts(verdicts) == VerifyOutcome.PASS

    def test_any_fail(self) -> None:
        verdicts = [
            VerdictRecord(node_id="n", outcome=VerifyOutcome.PASS, method="a", explanation="ok"),
            VerdictRecord(node_id="n", outcome=VerifyOutcome.FAIL, method="b", explanation="bad"),
        ]
        assert aggregate_verdicts(verdicts) == VerifyOutcome.FAIL

    def test_uncertain(self) -> None:
        verdicts = [
            VerdictRecord(node_id="n", outcome=VerifyOutcome.PASS, method="a", explanation="ok"),
            VerdictRecord(node_id="n", outcome=VerifyOutcome.UNCERTAIN, method="b", explanation="maybe"),
        ]
        assert aggregate_verdicts(verdicts) == VerifyOutcome.UNCERTAIN


class TestVerifyAll:
    @pytest.mark.asyncio
    async def test_verify_all_without_code(self) -> None:
        llm = FakeLLM(responses=[
            '{"final_answer": "42"}',  # self-consistency re-derive (structured)
            '{"has_issues": false, "issues": [], "recommendation": "approve"}',  # critic
        ])
        v = Verifier(llm)
        verdicts = await v.verify_all("n1", "What is 6*7?", "42")
        assert len(verdicts) == 2  # self_consistency + critic, no code

    @pytest.mark.asyncio
    async def test_verify_all_with_code(self) -> None:
        llm = FakeLLM(responses=[
            '{"final_answer": "42"}',
            '{"has_issues": false, "issues": [], "recommendation": "approve"}',
        ])
        v = Verifier(llm)
        verdicts = await v.verify_all("n1", "What is 6*7?", "42", code="print(6*7)")
        assert len(verdicts) == 3  # self_consistency + critic + tool_grounding
