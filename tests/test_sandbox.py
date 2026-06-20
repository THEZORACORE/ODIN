"""Tests for the sandbox abstraction (Phase 2.3)."""

from __future__ import annotations

import pytest

from odin.tools.sandbox import ContainerSandbox, MockSandbox, ProcessSandbox, SandboxResult


class TestSandboxResult:
    def test_success(self) -> None:
        r = SandboxResult("hello", exit_code=0)
        assert r.success
        assert r.output == "hello"

    def test_failure(self) -> None:
        r = SandboxResult("", "error", exit_code=1)
        assert not r.success
        assert "error" in r.output

    def test_timeout(self) -> None:
        r = SandboxResult("", "", -1, timed_out=True)
        assert not r.success
        assert "TIMEOUT" in r.output

    def test_truncation(self) -> None:
        r = SandboxResult("x" * 60_000)
        assert "TRUNCATED" in r.output

    def test_no_output(self) -> None:
        r = SandboxResult("")
        assert r.output == "[No output]"


class TestMockSandbox:
    @pytest.mark.asyncio
    async def test_returns_canned(self) -> None:
        sb = MockSandbox(output="42")
        r = await sb.execute("print(42)")
        assert r.success
        assert r.stdout == "42"

    @pytest.mark.asyncio
    async def test_custom_exit(self) -> None:
        sb = MockSandbox(output="err", exit_code=1)
        r = await sb.execute("fail")
        assert not r.success


class TestProcessSandbox:
    @pytest.mark.asyncio
    async def test_basic_exec(self) -> None:
        sb = ProcessSandbox()
        r = await sb.execute("print(2 + 2)")
        assert r.success
        assert "4" in r.stdout

    @pytest.mark.asyncio
    async def test_error(self) -> None:
        sb = ProcessSandbox()
        r = await sb.execute("raise ValueError('boom')")
        assert not r.success
        assert "boom" in r.output


class TestContainerSandbox:
    @pytest.mark.asyncio
    async def test_availability_check(self) -> None:
        # Just verify the method runs without crashing
        available = await ContainerSandbox.is_available()
        assert isinstance(available, bool)
