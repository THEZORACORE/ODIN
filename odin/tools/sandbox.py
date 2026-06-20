"""Sandbox abstraction for code execution (Phase 2.3).

Provides a pluggable sandbox interface so ODIN can run code in:
- ProcessSandbox (default): subprocess with resource limits (preexec_fn)
- ContainerSandbox: Docker-based isolation (network=none, read-only, resource caps)
- MockSandbox: deterministic, for tests

The orchestrator / tool registry uses the abstract Sandbox protocol;
callers never touch subprocess or Docker directly.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("odin.sandbox")

_MAX_OUTPUT = 50_000
_DEFAULT_TIMEOUT = 30.0


class SandboxResult:
    """Output of a sandboxed execution."""

    __slots__ = ("stdout", "stderr", "exit_code", "timed_out")

    def __init__(
        self,
        stdout: str,
        stderr: str = "",
        exit_code: int = 0,
        timed_out: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.timed_out = timed_out

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        parts = [self.stdout]
        if self.stderr:
            parts.append(f"[STDERR]\n{self.stderr}")
        if self.timed_out:
            parts.append("[TIMEOUT]")
        text = "\n".join(parts)
        if len(text) > _MAX_OUTPUT:
            text = text[:_MAX_OUTPUT] + f"\n[TRUNCATED at {_MAX_OUTPUT} chars]"
        return text.strip() or "[No output]"


class Sandbox(ABC):
    """Abstract sandbox — execute code in isolation."""

    @abstractmethod
    async def execute(self, code: str, *, timeout: float = _DEFAULT_TIMEOUT) -> SandboxResult:
        """Run Python code and return the result."""
        ...


class ProcessSandbox(Sandbox):
    """Subprocess-based sandbox with resource limits (the Phase 1 approach)."""

    async def execute(self, code: str, *, timeout: float = _DEFAULT_TIMEOUT) -> SandboxResult:
        import resource as res_mod

        def _limits() -> None:
            res_mod.setrlimit(res_mod.RLIMIT_CPU, (30, 30))
            res_mod.setrlimit(res_mod.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            res_mod.setrlimit(res_mod.RLIMIT_CORE, (0, 0))

        safe_env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(code)
            script = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
                preexec_fn=_limits if sys.platform != "win32" else None,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                return SandboxResult("", "", -1, timed_out=True)

            return SandboxResult(
                stdout=stdout_b.decode("utf-8", errors="replace"),
                stderr=stderr_b.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
            )
        finally:
            Path(script).unlink(missing_ok=True)


class ContainerSandbox(Sandbox):
    """Docker-based sandbox — full isolation via container.

    Requires Docker to be installed and accessible.  Runs code in a
    minimal Python container with:
    - --network=none (no internet)
    - --read-only (no filesystem writes except /tmp)
    - --memory / --cpus caps
    - No ambient credentials
    """

    def __init__(
        self,
        image: str = "python:3.12-slim",
        memory_limit: str = "256m",
        cpus: float = 1.0,
    ) -> None:
        self._image = image
        self._memory = memory_limit
        self._cpus = cpus

    async def execute(self, code: str, *, timeout: float = _DEFAULT_TIMEOUT) -> SandboxResult:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(code)
            script = f.name

        try:
            cmd = [
                "docker", "run", "--rm",
                "--network=none",
                "--read-only",
                "--tmpfs=/tmp:rw,noexec,size=64m",
                f"--memory={self._memory}",
                f"--cpus={self._cpus}",
                "--user=nobody",
                "-v", f"{script}:/code.py:ro",
                self._image,
                "python", "/code.py",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                return SandboxResult("", "", -1, timed_out=True)

            return SandboxResult(
                stdout=stdout_b.decode("utf-8", errors="replace"),
                stderr=stderr_b.decode("utf-8", errors="replace"),
                exit_code=proc.returncode or 0,
            )
        finally:
            Path(script).unlink(missing_ok=True)

    @staticmethod
    async def is_available() -> bool:
        """Check if Docker is accessible."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False


class MockSandbox(Sandbox):
    """Deterministic sandbox for tests — returns canned output."""

    def __init__(self, output: str = "42", exit_code: int = 0) -> None:
        self._output = output
        self._exit_code = exit_code

    async def execute(self, code: str, *, timeout: float = _DEFAULT_TIMEOUT) -> SandboxResult:
        return SandboxResult(
            stdout=self._output, stderr="", exit_code=self._exit_code
        )
