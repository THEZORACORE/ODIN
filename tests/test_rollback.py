"""Tests for one-command RSIP rollback (Phase 4.10)."""

from __future__ import annotations

from collections.abc import Sequence

from odin.improve.rollback import Rollback


class ScriptedRunner:
    """Returns a canned response per matching command substring; records calls."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}
        self.calls: list[list[str]] = []

    async def run(
        self,
        args: Sequence[str],
        *,
        cwd: str | None = None,
        stdin: str | None = None,
        check: bool = True,
    ) -> str:
        self.calls.append(list(args))
        key = " ".join(args)
        for pattern, resp in self._responses.items():
            if pattern in key:
                return resp
        return ""


class TestRollback:
    async def test_last_rsip_commit_found(self) -> None:
        runner = ScriptedRunner({"git log": "abc1234\n"})
        rb = Rollback("/repo", runner=runner)
        assert await rb.last_rsip_commit() == "abc1234"

    async def test_last_rsip_commit_none(self) -> None:
        runner = ScriptedRunner({"git log": "\n"})
        rb = Rollback("/repo", runner=runner)
        assert await rb.last_rsip_commit() is None

    async def test_revert_uses_no_edit(self) -> None:
        runner = ScriptedRunner()
        rb = Rollback("/repo", runner=runner)
        await rb.revert("deadbeef")
        assert runner.calls[-1] == ["git", "revert", "--no-edit", "deadbeef"]

    async def test_revert_last_rsip_reverts_found_commit(self) -> None:
        runner = ScriptedRunner({"git log": "abc1234\n"})
        rb = Rollback("/repo", runner=runner)
        reverted = await rb.revert_last_rsip()
        assert reverted == "abc1234"
        assert ["git", "revert", "--no-edit", "abc1234"] in runner.calls

    async def test_revert_last_rsip_noop_when_none(self) -> None:
        runner = ScriptedRunner({"git log": ""})
        rb = Rollback("/repo", runner=runner)
        assert await rb.revert_last_rsip() is None
        assert not any(c[:2] == ["git", "revert"] for c in runner.calls)
