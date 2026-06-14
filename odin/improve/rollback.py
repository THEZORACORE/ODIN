"""One-command rollback for RSIP-merged changes (Phase 4.10).

Self-improvement lands as ordinary git commits (via BIFRÖST PRs), so undoing one
is a `git revert` — a *new* commit that inverts the change, never history
rewriting. `Rollback` finds the most recent RSIP commit and reverts it, giving
ODIN a safe, auditable "undo the last self-modification" button.
"""

from __future__ import annotations

from odin.improve.shell import CommandRunner, SubprocessRunner

# Commit-message prefix BIFRÖST uses for self-improvement changes.
RSIP_COMMIT_PREFIX = "rsip:"


class Rollback:
    """Reverts RSIP commits via safe, non-destructive `git revert`."""

    def __init__(self, repo_dir: str, *, runner: CommandRunner | None = None) -> None:
        self._repo = repo_dir
        self._runner = runner or SubprocessRunner()

    async def last_rsip_commit(self) -> str | None:
        """Return the SHA of the most recent RSIP commit, or None."""
        out = await self._runner.run(
            [
                "git", "log", "-E",
                f"--grep=^{RSIP_COMMIT_PREFIX}",
                "--format=%H", "-n", "1",
            ],
            cwd=self._repo,
        )
        sha = out.strip()
        return sha or None

    async def revert(self, commit: str = "HEAD") -> str:
        """Revert a single commit (creates an inverse commit). Returns the SHA."""
        await self._runner.run(["git", "revert", "--no-edit", commit], cwd=self._repo)
        return commit

    async def revert_last_rsip(self) -> str | None:
        """Revert the most recent RSIP commit if one exists; return its SHA."""
        commit = await self.last_rsip_commit()
        if commit is not None:
            await self.revert(commit)
        return commit
