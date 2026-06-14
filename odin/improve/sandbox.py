"""Sandboxed git worktree isolation for RSIP candidate testing (Phase 4.5).

A candidate self-improvement diff must be tried *without* touching the live
working tree. `GitWorktreeSandbox` checks out the base revision into a throwaway
`git worktree`, applies the diff there, and removes it afterwards — so MUNINN can
benchmark a candidate in isolation and the main checkout is never mutated.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from odin.improve.shell import CommandRunner, SubprocessRunner


class GitWorktreeSandbox:
    """Creates and tears down isolated git worktrees for candidate diffs."""

    def __init__(
        self,
        repo_dir: str,
        *,
        base: str = "HEAD",
        runner: CommandRunner | None = None,
    ) -> None:
        self._repo = repo_dir
        self._base = base
        self._runner = runner or SubprocessRunner()

    @asynccontextmanager
    async def worktree(self) -> AsyncIterator[str]:
        """Yield a path to an isolated checkout of ``base``; always cleaned up."""
        parent = tempfile.mkdtemp(prefix="odin-rsip-")
        tree = os.path.join(parent, "tree")
        await self._runner.run(
            ["git", "worktree", "add", "--detach", tree, self._base], cwd=self._repo
        )
        try:
            yield tree
        finally:
            try:
                await self._runner.run(
                    ["git", "worktree", "remove", "--force", tree], cwd=self._repo
                )
            finally:
                shutil.rmtree(parent, ignore_errors=True)

    async def apply_diff(self, tree: str, diff: str) -> None:
        """Apply a unified diff inside the worktree (no commit)."""
        await self._runner.run(["git", "apply", "-"], cwd=tree, stdin=diff)
