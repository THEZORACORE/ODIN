"""Tests for HEIMDALL's self-modification policy (RSIP guardrails)."""

from odin.safety.heimdall import Heimdall, SelfModificationPolicy
from odin.schemas import ActionRisk, ImprovementProposal


def _proposal(target: str, diff: str = "+ a\n- b", risk: ActionRisk = ActionRisk.MEDIUM) -> ImprovementProposal:
    return ImprovementProposal(target_file=target, rationale="r", diff=diff, risk=risk)


class TestSelfModificationPolicy:
    def test_allows_ordinary_target(self) -> None:
        h = Heimdall()
        allowed, reason = h.check_self_modification(_proposal("odin/agents/odin_planner.py"))
        assert allowed is True
        assert "within" in reason

    def test_blocks_safety_layer(self) -> None:
        h = Heimdall()
        allowed, reason = h.check_self_modification(_proposal("odin/safety/heimdall.py"))
        assert allowed is False
        assert "protected" in reason

    def test_blocks_the_benchmark(self) -> None:
        h = Heimdall()
        allowed, _ = h.check_self_modification(_proposal("odin/improve/benchmark.py"))
        assert allowed is False

    def test_blocks_the_engine(self) -> None:
        h = Heimdall()
        allowed, _ = h.check_self_modification(_proposal("odin/improve/muninn.py"))
        assert allowed is False

    def test_blocks_oversized_diff(self) -> None:
        policy = SelfModificationPolicy(max_diff_lines=3)
        h = Heimdall(self_mod_policy=policy)
        big = "\n".join(f"+ line {i}" for i in range(10))
        allowed, reason = h.check_self_modification(_proposal("odin/x.py", diff=big))
        assert allowed is False
        assert "too large" in reason

    def test_kill_switch_blocks_everything(self) -> None:
        h = Heimdall(self_mod_policy=SelfModificationPolicy(kill_switch=True))
        allowed, reason = h.check_self_modification(_proposal("odin/agents/x.py"))
        assert allowed is False
        assert "kill-switch" in reason

    def test_irreversible_requires_human(self) -> None:
        h = Heimdall()
        allowed, reason = h.check_self_modification(
            _proposal("odin/x.py", risk=ActionRisk.IRREVERSIBLE)
        )
        assert allowed is False
        assert "irreversible" in reason

    def test_audit_log_records_decision(self) -> None:
        h = Heimdall()
        h.check_self_modification(_proposal("odin/safety/heimdall.py"))
        actions = [e["action"] for e in h.get_audit_log()]
        assert "self_mod_denied" in actions

    def test_diff_line_count_ignores_headers(self) -> None:
        diff = "--- a/f\n+++ b/f\n+ added\n- removed\n context"
        assert _proposal("odin/x.py", diff=diff).diff_line_count() == 2
