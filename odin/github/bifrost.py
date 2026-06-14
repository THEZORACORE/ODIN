"""BIFRÖST — atomic, gated GitHub engine.

Turns an accepted ImprovementProposal into a *pull request* (never a direct push
to a protected branch). Every self-improvement is therefore reviewable and
git-revertible by a human — the human gate in the RSIP loop.

`GhBifrost` shells out to the `gh` CLI. `FakeBifrost` records calls for offline
tests so the whole RSIP loop can be exercised with zero network/side effects.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from pydantic import BaseModel


class PullRequest(BaseModel):
    """Result of opening a PR."""

    number: int | None = None
    url: str
    branch: str
    title: str


class Bifrost(ABC):
    """Interface for publishing a change as a reviewable PR."""

    @abstractmethod
    async def open_pr(self, *, branch: str, title: str, body: str, diff: str) -> PullRequest:
        ...


class FakeBifrost(Bifrost):
    """Records PR requests without touching git/GitHub. For tests and dry runs."""

    def __init__(self, base_url: str = "https://example.invalid/pr") -> None:
        self._base_url = base_url
        self.opened: list[dict[str, str]] = []

    async def open_pr(self, *, branch: str, title: str, body: str, diff: str) -> PullRequest:
        number = len(self.opened) + 1
        self.opened.append({"branch": branch, "title": title, "body": body, "diff": diff})
        return PullRequest(
            number=number, url=f"{self._base_url}/{number}", branch=branch, title=title
        )


class GhBifrost(Bifrost):
    """Opens a real PR via the `gh` CLI.

    Applies the proposal's diff on a fresh branch, commits, pushes, and opens a
    PR against ``base``. Never merges — merge is the human gate.
    """

    def __init__(self, repo: str, base: str = "main", remote: str = "origin") -> None:
        self.repo = repo
        self.base = base
        self.remote = remote

    async def open_pr(self, *, branch: str, title: str, body: str, diff: str) -> PullRequest:
        await self._git("checkout", "-b", branch)
        await self._apply_diff(diff)
        await self._git("commit", "-am", title)
        await self._git("push", "-u", self.remote, branch)
        url = await self._run(
            "gh", "pr", "create",
            "--repo", self.repo,
            "--base", self.base,
            "--head", branch,
            "--title", title,
            "--body", body,
        )
        return PullRequest(url=url.strip(), branch=branch, title=title)

    async def _apply_diff(self, diff: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "git", "apply", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(diff.encode())
        if proc.returncode != 0:
            raise RuntimeError(f"git apply failed: {stderr.decode()}")

    async def _git(self, *args: str) -> str:
        return await self._run("git", *args)

    async def _run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"command {args!r} failed: {stderr.decode()}")
        return stdout.decode()
