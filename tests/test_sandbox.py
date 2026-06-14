"""Tests for sandboxed git worktree isolation (Phase 4.5)."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path

import pytest

from odin.improve.sandbox import GitWorktreeSandbox
from odin.improve.shell import SubprocessRunner


class RecordingRunner:
    """Records argv/stdin without running anything."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []

    async def run(
        self,
        args: Sequence[str],
        *,
        cwd: str | None = None,
        stdin: str | None = None,
        check: bool = True,
    ) -> str:
        self.calls.append(list(args))
        self.stdins.append(stdin)
        return ""


class TestSandboxCommands:
    async def test_worktree_add_and_remove(self) -> None:
        runner = RecordingRunner()
        sandbox = GitWorktreeSandbox("/repo", base="main", runner=runner)

        async with sandbox.worktree() as tree:
            assert os.path.basename(tree) == "tree"
            await sandbox.apply_diff(tree, "DIFF")

        assert runner.calls[0][:4] == ["git", "worktree", "add", "--detach"]
        assert runner.calls[0][-1] == "main"
        assert ["git", "apply", "-"] in runner.calls
        assert "DIFF" in runner.stdins
        assert runner.calls[-1][:3] == ["git", "worktree", "remove"]

    async def test_worktree_removed_even_on_error(self) -> None:
        runner = RecordingRunner()
        sandbox = GitWorktreeSandbox("/repo", runner=runner)

        with pytest.raises(ValueError):
            async with sandbox.worktree():
                raise ValueError("boom")

        assert runner.calls[-1][:3] == ["git", "worktree", "remove"]


def _git_available() -> bool:
    return shutil.which("git") is not None


@pytest.mark.skipif(not _git_available(), reason="git not available")
class TestSandboxRealGit:
    async def _init_repo(self, path: Path) -> None:
        runner = SubprocessRunner()
        await runner.run(["git", "init"], cwd=str(path))
        (path / "file.txt").write_text("hello\n")
        await runner.run(["git", "add", "file.txt"], cwd=str(path))
        await runner.run(
            [
                "git", "-c", "user.email=odin@test", "-c", "user.name=ODIN",
                "commit", "-m", "init",
            ],
            cwd=str(path),
        )

    async def test_diff_applies_in_isolation(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        await self._init_repo(repo)

        diff = (
            "--- a/file.txt\n"
            "+++ b/file.txt\n"
            "@@ -1 +1 @@\n"
            "-hello\n"
            "+hello world\n"
        )
        sandbox = GitWorktreeSandbox(str(repo))
        captured: str | None = None
        async with sandbox.worktree() as tree:
            await sandbox.apply_diff(tree, diff)
            captured = (Path(tree) / "file.txt").read_text()
            assert os.path.isdir(tree)

        # candidate change is visible only inside the worktree
        assert captured == "hello world\n"
        # the live checkout is untouched
        assert (repo / "file.txt").read_text() == "hello\n"
        # worktree is cleaned up
        assert not os.path.exists(tree)
