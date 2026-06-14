"""Async command runner shared by the RSIP sandbox and rollback subsystems.

A tiny `CommandRunner` abstraction so git/CLI side effects are injectable: the
real `SubprocessRunner` shells out, while tests pass a fake that records the
exact argv (no git/network needed).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol


class CommandRunner(Protocol):
    async def run(
        self,
        args: Sequence[str],
        *,
        cwd: str | None = None,
        stdin: str | None = None,
        check: bool = True,
    ) -> str: ...


class SubprocessRunner:
    """Runs commands via asyncio subprocesses, raising on non-zero exit."""

    async def run(
        self,
        args: Sequence[str],
        *,
        cwd: str | None = None,
        stdin: str | None = None,
        check: bool = True,
    ) -> str:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        payload = stdin.encode() if stdin is not None else None
        stdout, stderr = await proc.communicate(payload)
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"command {list(args)!r} failed (exit {proc.returncode}): {stderr.decode().strip()}"
            )
        # When not checking, callers (e.g. a test runner) still want the report.
        return stdout.decode() + stderr.decode()
